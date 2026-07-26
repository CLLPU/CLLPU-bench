#!/usr/bin/env python3
"""Expand English canonical QA variants into one target-language QA file per run."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import json
import os
import re
import sys
import threading
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests


PROMPT_VERSION = "step6_direct_translation_v5"
CANONICAL_LANGUAGE = "en"

SYSTEM_PROMPT = """You translate benchmark QA probes from English into one requested target language.

Return JSON only.
Each translated QA must still probe exactly the same single fact as the English source QA.
Keep the relation unchanged.
Translate the English question, expected answer, and answer aliases conservatively into the target language.
Prefer faithful translation over paraphrasing or open-ended localization.
Do not produce mixed-language prompts, code-switching, bridge-language prompts, or query/answer language mismatch.
Do not add new facts or constraints.
Use established target-language entity names when appropriate.
"""

LANGUAGE_NAMES = {
    "zh": "Simplified Chinese",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
    "ru": "Russian",
    "bn": "Bengali",
    "sw": "Swahili",
    "th": "Thai",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="config/llm_api.env",
        help="Local env-style config file for LLM API settings.",
    )
    parser.add_argument(
        "--input",
        default="data/qa_variants.en.json",
        help="Input Step-5 English canonical QA JSON.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output target-language QA JSON. Defaults to data/qa_variants.<language>.json.",
    )
    parser.add_argument(
        "--cache-dir",
        default="data/step6_qa_translation_cache",
        help="Directory for per-knowledge-pair raw and normalized cache files.",
    )
    parser.add_argument(
        "--language",
        default="",
        help="Single target language code, e.g. zh or fr.",
    )
    parser.add_argument(
        "--languages",
        default="",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--pair-id",
        action="append",
        dest="pair_ids",
        help="Optional topic pair_id to process. Can be passed multiple times.",
    )
    parser.add_argument(
        "--knowledge-pair-id",
        action="append",
        dest="knowledge_pair_ids",
        help="Optional knowledge_pair_id to process. Can be passed multiple times.",
    )
    parser.add_argument(
        "--max-pairs",
        type=int,
        default=None,
        help="Process at most N topic pairs after filtering.",
    )
    parser.add_argument(
        "--max-knowledge-pairs",
        type=int,
        default=None,
        help="Process at most N knowledge card pairs after filtering.",
    )
    parser.add_argument(
        "--api-base",
        default="",
        help="Base URL for the OpenAI-compatible API.",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="API key for the OpenAI-compatible API.",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Model name for QA translation.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.1,
        help="Sampling temperature.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Force fresh API calls even if cached outputs exist.",
    )
    parser.set_defaults(enable_backtranslation=True)
    parser.add_argument(
        "--enable-backtranslation",
        dest="enable_backtranslation",
        action="store_true",
        help="Enable per-QA back-translation consistency checks before accepting translations.",
    )
    parser.add_argument(
        "--skip-backtranslation",
        dest="enable_backtranslation",
        action="store_false",
        help="Skip back-translation checks. Intended only for debugging or cost estimation.",
    )
    parser.add_argument(
        "--max-translation-attempts",
        type=int,
        default=3,
        help="Maximum translate/repair attempts per source QA when back-translation is enabled.",
    )
    parser.add_argument(
        "--failed-output",
        default="",
        help="Optional failed back-translation queue path. Defaults to data/qa_variants.<language>.failed_backtranslation.json.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of concurrent knowledge-pair translation workers.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print selected workload without calling the API or writing output.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def load_env_config_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}

    values: Dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def split_api_keys(raw_value: str) -> List[str]:
    if not raw_value:
        return []
    return [part.strip() for part in re.split(r"[\n,]+", raw_value) if part.strip()]


def resolve_api_keys(*candidates: str) -> List[str]:
    keys: List[str] = []
    seen = set()
    for candidate in candidates:
        for key in split_api_keys(candidate or ""):
            if key in seen:
                continue
            seen.add(key)
            keys.append(key)
    return keys


def mask_api_key(api_key: str) -> str:
    if len(api_key) <= 10:
        return "***"
    return f"{api_key[:6]}...{api_key[-4:]}"


class RoundRobinKeyScheduler:
    """Distribute concurrent API calls across configured keys."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_index = 0

    def ordered_keys(self, api_keys: Sequence[str]) -> List[str]:
        keys = list(api_keys)
        if len(keys) <= 1:
            return keys
        with self._lock:
            start_index = self._next_index % len(keys)
            self._next_index += 1
        return keys[start_index:] + keys[:start_index]


def resolve_runtime_settings(args: argparse.Namespace) -> None:
    config_values = load_env_config_file(Path(args.config))
    args.api_base = (
        args.api_base
        or os.environ.get("STEP6_API_BASE")
        or os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("API_BASE")
        or os.environ.get("STEP5_API_BASE")
        or os.environ.get("STEP3_API_BASE")
        or config_values.get("STEP6_API_BASE")
        or config_values.get("OPENAI_BASE_URL")
        or config_values.get("API_BASE")
        or config_values.get("STEP5_API_BASE")
        or config_values.get("STEP3_API_BASE")
        or ""
    )
    args.api_keys = resolve_api_keys(
        args.api_key,
        os.environ.get("STEP6_API_KEYS", ""),
        os.environ.get("OPENAI_API_KEYS", ""),
        os.environ.get("API_KEYS", ""),
        os.environ.get("STEP6_API_KEY", ""),
        os.environ.get("OPENAI_API_KEY", ""),
        os.environ.get("API_KEY", ""),
        os.environ.get("STEP5_API_KEYS", ""),
        os.environ.get("STEP5_API_KEY", ""),
        os.environ.get("STEP3_API_KEYS", ""),
        os.environ.get("STEP3_API_KEY", ""),
        config_values.get("STEP6_API_KEYS", ""),
        config_values.get("OPENAI_API_KEYS", ""),
        config_values.get("API_KEYS", ""),
        config_values.get("STEP6_API_KEY", ""),
        config_values.get("OPENAI_API_KEY", ""),
        config_values.get("API_KEY", ""),
        config_values.get("STEP5_API_KEYS", ""),
        config_values.get("STEP5_API_KEY", ""),
        config_values.get("STEP3_API_KEYS", ""),
        config_values.get("STEP3_API_KEY", ""),
    )
    args.api_key = args.api_keys[0] if args.api_keys else ""
    args.model = (
        args.model
        or os.environ.get("STEP6_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or os.environ.get("MODEL")
        or os.environ.get("STEP5_MODEL")
        or os.environ.get("STEP3_MODEL")
        or config_values.get("STEP6_MODEL")
        or config_values.get("OPENAI_MODEL")
        or config_values.get("MODEL")
        or config_values.get("STEP5_MODEL")
        or config_values.get("STEP3_MODEL")
        or "gemini-3.1-pro-preview-thinking"
    )


def ensure_api_args(args: argparse.Namespace) -> None:
    if not args.api_base:
        raise SystemExit("Missing API base. Use --api-base or set STEP6_API_BASE / OPENAI_BASE_URL / API_BASE.")
    if not getattr(args, "api_keys", None):
        raise SystemExit(
            "Missing API key. Use --api-key or set STEP6_API_KEY / STEP6_API_KEYS / OPENAI_API_KEY / OPENAI_API_KEYS / API_KEY / API_KEYS."
        )


def normalize_api_base(api_base: str) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def normalize_whitespace(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize_for_match(text: Any) -> str:
    lowered = normalize_whitespace(text).lower()
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", lowered).strip()


def normalize_unicode_for_match(text: Any) -> str:
    lowered = normalize_whitespace(text).casefold()
    chars: List[str] = []
    previous_space = True
    for char in lowered:
        category = unicodedata.category(char)
        if category[0] in {"L", "N"}:
            chars.append(char)
            previous_space = False
        elif not previous_space:
            chars.append(" ")
            previous_space = True
    return " ".join("".join(chars).split())


def match_tokens(text: Any) -> List[str]:
    normalized = normalize_for_match(text)
    if not normalized:
        return []
    return [token for token in normalized.split(" ") if token]


def canonical_alias_tokens(text: Any) -> Tuple[str, ...]:
    return tuple(sorted(set(match_tokens(text))))


def acronym_for(text: str) -> str:
    words = [token for token in re.split(r"[^A-Za-z0-9]+", normalize_whitespace(text)) if token]
    return "".join(word[0] for word in words if word[0].isalnum()).upper()


def is_topic_alias(value: str, card: Dict[str, Any]) -> bool:
    normalized = normalize_for_match(value)
    topic_values = [
        card.get("topic_name"),
        card.get("topic_name_zh"),
        card.get("source_page"),
        card.get("source_page_zh"),
    ]
    return any(normalized and normalized == normalize_for_match(item) for item in topic_values)


def answer_alias_equivalent(alias: str, answer: str) -> bool:
    alias_unicode = normalize_unicode_for_match(alias)
    answer_unicode = normalize_unicode_for_match(answer)
    if alias_unicode and answer_unicode:
        if alias_unicode == answer_unicode:
            return True
        if alias_unicode in answer_unicode or answer_unicode in alias_unicode:
            return True
        alias_unicode_tokens = [token for token in alias_unicode.split(" ") if token]
        answer_unicode_tokens = [token for token in answer_unicode.split(" ") if token]
        if alias_unicode_tokens and sorted(set(alias_unicode_tokens)) == sorted(set(answer_unicode_tokens)):
            return True

    alias_norm = normalize_for_match(alias)
    answer_norm = normalize_for_match(answer)
    if not alias_norm or not answer_norm or alias_norm == answer_norm:
        return bool(alias_norm and answer_norm)
    if alias_norm in answer_norm or answer_norm in alias_norm:
        return True

    alias_tokens = match_tokens(alias)
    answer_tokens = match_tokens(answer)
    if not alias_tokens or not answer_tokens:
        return False
    if canonical_alias_tokens(alias) == canonical_alias_tokens(answer):
        return True

    classification_suffixes = {"type", "class", "classification", "category"}
    alias_core = {token for token in alias_tokens if token not in classification_suffixes}
    answer_core = {token for token in answer_tokens if token not in classification_suffixes}
    if alias_core and alias_core == answer_core:
        return True

    alias_numbers = {token for token in alias_tokens if any(ch.isdigit() for ch in token)}
    answer_numbers = {token for token in answer_tokens if any(ch.isdigit() for ch in token)}
    if alias_numbers and alias_numbers == answer_numbers:
        return True

    acronym = acronym_for(answer)
    if len(acronym) >= 2 and alias_norm.replace(" ", "").upper() == acronym:
        return True
    reverse_acronym = acronym_for(alias)
    if len(reverse_acronym) >= 2 and answer_norm.replace(" ", "").upper() == reverse_acronym:
        return True

    return False


def slugify(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return value or "item"


def parse_language_value(value: str) -> str:
    language = normalize_whitespace(value).lower()
    if not language:
        raise SystemExit("A target language must be provided.")
    if language == CANONICAL_LANGUAGE:
        raise SystemExit("Step 6 target language must exclude English.")
    return language


def resolve_target_language(args: argparse.Namespace) -> str:
    explicit_language = parse_language_value(args.language) if normalize_whitespace(args.language) else ""
    legacy_languages = [item.strip().lower() for item in args.languages.split(",") if item.strip()]
    if legacy_languages:
        legacy_languages = list(dict.fromkeys(legacy_languages))
        if len(legacy_languages) != 1:
            raise SystemExit(
                "Step 6 now processes exactly one target language per run. "
                "Use --language zh and rerun separately for each target language."
            )
        legacy_language = parse_language_value(legacy_languages[0])
        if explicit_language and explicit_language != legacy_language:
            raise SystemExit("Do not pass conflicting values to --language and --languages.")
        return legacy_language
    if explicit_language:
        return explicit_language
    return "zh"


def default_output_path(language: str) -> str:
    return f"data/qa_variants.{language}.json"


def filter_topic_pairs(topic_pairs: Iterable[Dict[str, Any]], args: argparse.Namespace) -> List[Dict[str, Any]]:
    selected = list(topic_pairs)
    if args.pair_ids:
        allowed = set(args.pair_ids)
        selected = [pair for pair in selected if pair.get("pair_id") in allowed]
    if args.max_pairs is not None:
        selected = selected[: args.max_pairs]
    return selected


def selected_knowledge_pairs(topic_pair: Dict[str, Any], args: argparse.Namespace) -> List[Dict[str, Any]]:
    pairs = list(topic_pair.get("knowledge_card_pairs", []))
    if args.knowledge_pair_ids:
        allowed = set(args.knowledge_pair_ids)
        pairs = [pair for pair in pairs if pair.get("knowledge_pair_id") in allowed]
    return pairs


def compact_card(topic_payload: Dict[str, Any]) -> Dict[str, Any]:
    card = topic_payload.get("card") or {}
    keys = [
        "card_id",
        "relation_type",
        "relation_type_zh",
        "semantic_slot",
        "semantic_slot_zh",
        "fact_statement",
        "fact_statement_zh",
        "answer",
        "answer_zh",
        "answer_type",
        "answer_type_zh",
        "source_span",
        "source_span_zh",
        "aliases",
        "aliases_zh",
    ]
    compact = {key: card.get(key) for key in keys if key in card}
    compact["topic_name"] = topic_payload.get("topic_name")
    compact["topic_name_zh"] = topic_payload.get("topic_name_zh")
    return compact


def english_variants(knowledge_pair: Dict[str, Any], role: str) -> List[Dict[str, Any]]:
    variants = []
    for variant in knowledge_pair.get(f"{role}_qa_variants", []):
        if normalize_whitespace(variant.get("language")).lower() == CANONICAL_LANGUAGE:
            variants.append(variant)
    return variants


def language_instruction(language: str) -> str:
    return f"{language}: {LANGUAGE_NAMES.get(language, language)}"


def compact_source_variant(variant: Dict[str, Any]) -> Dict[str, Any]:
    keys = [
        "qa_id",
        "card_id",
        "topic_role",
        "variant_layer",
        "language",
        "question",
        "expected_answer",
        "answer_aliases",
        "relation_type",
        "source_span",
        "rewrite_note",
    ]
    return {key: variant.get(key) for key in keys if key in variant}


def build_translation_prompt(
    knowledge_pair: Dict[str, Any],
    language: str,
) -> str:
    payload = {
        "knowledge_pair_id": knowledge_pair.get("knowledge_pair_id"),
        "pair_id": knowledge_pair.get("pair_id"),
        "relation_type": knowledge_pair.get("relation_type"),
        "relation_type_zh": knowledge_pair.get("relation_type_zh"),
        "target": compact_card(knowledge_pair.get("target") or {}),
        "neighbor": compact_card(knowledge_pair.get("neighbor") or {}),
        "target_source_variants_en": [compact_source_variant(v) for v in english_variants(knowledge_pair, "target")],
        "neighbor_source_variants_en": [compact_source_variant(v) for v in english_variants(knowledge_pair, "neighbor")],
    }

    return f"""Translate the following English canonical QA probes into the requested target language.

Target language:
{language_instruction(language)}

Rules:
1. Keep every translated QA aligned to the same source_qa_id and the same fact.
2. Keep variant_layer unchanged.
3. Keep topic_role unchanged.
4. Translate the English question directly into a natural monolingual question in the target language without changing what is being asked.
5. Translate the English expected_answer directly. Use a stable target-language rendering only when it is an established equivalent of the English answer.
6. Translate answer_aliases from the English source QA only. Do not import raw card aliases and do not invent new aliases.
7. Every answer_alias must remain strictly equivalent to the translated expected_answer.
8. Never use the topic name, event name, model name, work title, or other context entities as answer_aliases unless they already appear as valid answer aliases in the English source QA.
9. If the English source QA has no answer_aliases, return an empty list.
10. Do not add new facts, hints, examples, extra constraints, or new answer variants.
11. Do not produce mixed-language prompts.

Return JSON only with this schema:
{{
  "translations": [
    {{
      "source_qa_id": "...",
      "language": "{language}",
      "question": "...",
      "expected_answer": "...",
      "answer_aliases": ["..."],
      "translation_note": "brief note"
    }}
  ]
}}

Knowledge pair:
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def build_single_translation_prompt(
    knowledge_pair: Dict[str, Any],
    source_variant: Dict[str, Any],
    language: str,
) -> str:
    role = source_variant["topic_role"]
    payload = {
        "knowledge_pair_id": knowledge_pair.get("knowledge_pair_id"),
        "pair_id": knowledge_pair.get("pair_id"),
        "relation_type": knowledge_pair.get("relation_type"),
        "relation_type_zh": knowledge_pair.get("relation_type_zh"),
        "source_qa_en": compact_source_variant(source_variant),
        "source_card": compact_card(knowledge_pair.get(role) or {}),
        "paired_card_context": compact_card(knowledge_pair.get("neighbor" if role == "target" else "target") or {}),
    }

    return f"""Translate exactly one English canonical QA probe into the requested target language.

Target language:
{language_instruction(language)}

Rules:
1. Translate only this one source QA.
2. Keep source_qa_id, topic_role, variant_layer, relation_type, card_id, and fact unchanged.
3. Translate the English question directly into a natural, monolingual, independently answerable target-language question.
4. Translate the English expected_answer directly. Use an established target-language rendering only when it is strictly equivalent to the English answer.
5. Translate answer_aliases conservatively from source_qa_en.answer_aliases only. Do not import raw source_card aliases or invent new aliases.
6. Every answer_alias must be strictly equivalent to the expected_answer. Do not use the topic name, event name, model name, work title, or other context entities as answer_aliases.
7. If source_qa_en.answer_aliases is empty, return an empty answer_aliases list.
8. Do not add new facts, hints, examples, extra constraints, or extra answer variants.
9. Do not produce mixed-language prompts.
10. This translation will be back-translated to English and checked for semantic consistency.

Return JSON only with this schema:
{{
  "translation": {{
    "source_qa_id": "{source_variant.get('qa_id')}",
    "language": "{language}",
    "question": "...",
    "expected_answer": "...",
    "answer_aliases": ["..."],
    "translation_note": "brief note"
  }}
}}

Source payload:
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def build_repair_translation_prompt(
    knowledge_pair: Dict[str, Any],
    source_variant: Dict[str, Any],
    language: str,
    previous_candidate: Dict[str, Any],
    backtranslation: Dict[str, Any],
    consistency: Dict[str, Any],
) -> str:
    role = source_variant["topic_role"]
    payload = {
        "knowledge_pair_id": knowledge_pair.get("knowledge_pair_id"),
        "pair_id": knowledge_pair.get("pair_id"),
        "relation_type": knowledge_pair.get("relation_type"),
        "source_qa_en": compact_source_variant(source_variant),
        "source_card": compact_card(knowledge_pair.get(role) or {}),
        "previous_target_language_qa": previous_candidate,
        "previous_backtranslation_en": backtranslation,
        "consistency_failure": consistency,
    }

    return f"""Repair one target-language QA that failed a back-translation consistency check.

Target language:
{language_instruction(language)}

Repair rules:
1. Do not modify the English source QA.
2. Do not change the source fact, relation, topic_role, variant_layer, or card_id.
3. Only repair the target-language question, expected_answer, answer_aliases, and translation_note.
4. Address the consistency failure directly.
5. Keep the result as a faithful direct translation of the English source QA rather than a rewrite.
6. Keep answer_aliases limited to strict equivalents of expected_answer, and only when they correspond to the English source QA aliases.
7. Remove any alias that names the topic, event, model, work, or other non-answer entity.
8. Keep the result natural and monolingual in the target language.
9. Do not add new facts, hints, examples, extra constraints, or extra answer variants.

Return JSON only with this schema:
{{
  "translation": {{
    "source_qa_id": "{source_variant.get('qa_id')}",
    "language": "{language}",
    "question": "...",
    "expected_answer": "...",
    "answer_aliases": ["..."],
    "translation_note": "brief repair note"
  }}
}}

Repair payload:
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def build_backtranslation_prompt(
    translated_variant: Dict[str, Any],
    language: str,
) -> str:
    payload = {
        "source_qa_id": translated_variant.get("source_qa_id"),
        "source_language": language,
        "question": translated_variant.get("question"),
        "expected_answer": translated_variant.get("expected_answer"),
        "answer_aliases": translated_variant.get("answer_aliases", []),
    }

    return f"""Translate this target-language QA back into English for quality control.

Source language:
{language_instruction(language)}

Rules:
1. Preserve the meaning of the target-language question and expected answer.
2. Do not use the original English source QA.
3. Do not improve, repair, or reinterpret the QA; only back-translate what is written.

Return JSON only with this schema:
{{
  "backtranslation": {{
    "source_qa_id": "{translated_variant.get('source_qa_id')}",
    "question": "...",
    "expected_answer": "...",
    "answer_aliases": ["..."]
  }}
}}

Target-language QA:
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def build_consistency_prompt(
    knowledge_pair: Dict[str, Any],
    source_variant: Dict[str, Any],
    translated_variant: Dict[str, Any],
    backtranslation: Dict[str, Any],
) -> str:
    payload = {
        "knowledge_pair_id": knowledge_pair.get("knowledge_pair_id"),
        "pair_id": knowledge_pair.get("pair_id"),
        "source_qa_en": compact_source_variant(source_variant),
        "target_language_qa": {
            "source_qa_id": translated_variant.get("source_qa_id"),
            "language": translated_variant.get("language"),
            "question": translated_variant.get("question"),
            "expected_answer": translated_variant.get("expected_answer"),
            "answer_aliases": translated_variant.get("answer_aliases", []),
        },
        "backtranslation_en": backtranslation,
    }

    return f"""Judge whether a target-language QA preserves the same fact as the English source QA.

Use semantic equivalence, not exact wording. The back-translation may be phrased differently, but it must ask for the same fact and expect the same answer.

Pass only if:
1. The same entity/topic is being asked about.
2. The same relation_type and fact are preserved.
3. The expected answer is equivalent to the source expected_answer or aliases.
4. No new constraints, hints, explanations, or facts were introduced.
5. target and neighbor roles are not confused.
6. core/surface intent is not changed.

Return JSON only with this schema:
{{
  "consistency": {{
    "verdict": "passed",
    "is_consistent": true,
    "failure_type": "",
    "reason": "short reason",
    "repair_instruction": ""
  }}
}}

If it fails, set verdict to "failed", is_consistent to false, choose a concise failure_type, and provide a repair_instruction for regenerating the target-language QA.

Consistency payload:
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def call_chat_completion(
    session: requests.Session,
    api_base: str,
    api_keys: Sequence[str],
    api_key_scheduler: Optional[RoundRobinKeyScheduler],
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    timeout: int,
) -> Dict[str, Any]:
    url = f"{normalize_api_base(api_base)}/chat/completions"
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
    }

    last_error: Optional[Exception] = None
    total_keys = len(api_keys)
    for attempt in range(1, 4):
        candidate_keys = (
            api_key_scheduler.ordered_keys(api_keys) if api_key_scheduler is not None else list(api_keys)
        )
        for key_index, api_key in enumerate(candidate_keys, start=1):
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            try:
                response = session.post(url, headers=headers, json=payload, timeout=timeout)
                if response.status_code >= 400 and "response_format" in response.text:
                    fallback_payload = dict(payload)
                    fallback_payload.pop("response_format", None)
                    response = session.post(url, headers=headers, json=fallback_payload, timeout=timeout)
                response.raise_for_status()
                if attempt > 1 or key_index > 1:
                    log(
                        f"  API call succeeded with configured key {key_index}/{total_keys} "
                        f"({mask_api_key(api_key)}) on pass {attempt}."
                    )
                return response.json()
            except requests.RequestException as exc:
                last_error = exc
                if key_index < total_keys:
                    log(
                        f"  API call failed with configured key {key_index}/{total_keys} "
                        f"({mask_api_key(api_key)}); trying next key: {exc}"
                    )
                else:
                    log(
                        f"  API call failed on pass {attempt}/3 with configured key {key_index}/{total_keys} "
                        f"({mask_api_key(api_key)}): {exc}"
                    )
        if attempt == 3:
            break
        sleep_seconds = min(5 * attempt, 15)
        log(f"  Exhausted {total_keys} configured API keys on pass {attempt}/3, retrying in {sleep_seconds}s.")
        time.sleep(sleep_seconds)
    assert last_error is not None
    raise last_error


def extract_message_text(response_json: Dict[str, Any]) -> str:
    choices = response_json.get("choices") or []
    if not choices:
        raise ValueError("Model response did not contain any choices.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))
        if text_parts:
            return "\n".join(text_parts)
    raise ValueError("Unsupported message content format in model response.")


def strip_json_fence(text: str) -> str:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```(?:\s*.*)?$", "", raw, flags=re.DOTALL)
    return raw.strip()


def decode_first_json_value(raw: str) -> Any:
    decoder = json.JSONDecoder()
    stripped = raw.lstrip()
    if not stripped:
        raise json.JSONDecodeError("Empty JSON payload", raw, 0)
    return decoder.raw_decode(stripped)[0]


def extract_json_object(text: str) -> Dict[str, Any]:
    raw = strip_json_fence(text)
    try:
        return decode_first_json_value(raw)
    except json.JSONDecodeError:
        for match in re.finditer(r"[\{\[]", raw):
            candidate = raw[match.start() :]
            try:
                return decode_first_json_value(candidate)
            except json.JSONDecodeError:
                continue
        raise


def parse_model_json_response(response_json: Dict[str, Any]) -> Dict[str, Any]:
    return extract_json_object(extract_message_text(response_json))


def first_object(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return item
    return {}


def root_object(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else first_object(value)


def parse_translation_object(model_output: Any, source_qa_id: str, language: str) -> Dict[str, Any]:
    model_output = root_object(model_output)
    translation = first_object(model_output.get("translation"))
    if not translation:
        translations = model_output.get("translations")
        if isinstance(translations, list):
            for item in translations:
                if isinstance(item, dict) and normalize_whitespace(item.get("source_qa_id")) == source_qa_id:
                    translation = item
                    break
        if not translation:
            translation = first_object(translations)
    if not translation and "question" in model_output and "expected_answer" in model_output:
        translation = model_output
    if not translation:
        raise ValueError("Model response did not contain a translation object.")
    translation = dict(translation)
    translation.setdefault("source_qa_id", source_qa_id)
    translation.setdefault("language", language)
    return translation


def parse_backtranslation_object(model_output: Any, source_qa_id: str) -> Dict[str, Any]:
    model_output = root_object(model_output)
    backtranslation = first_object(model_output.get("backtranslation"))
    if not backtranslation:
        backtranslation = first_object(model_output.get("backtranslations"))
    if not backtranslation and "question" in model_output and "expected_answer" in model_output:
        backtranslation = model_output
    if not backtranslation:
        raise ValueError("Model response did not contain a backtranslation object.")
    return {
        "source_qa_id": normalize_whitespace(backtranslation.get("source_qa_id")) or source_qa_id,
        "question": normalize_whitespace(backtranslation.get("question")),
        "expected_answer": normalize_whitespace(backtranslation.get("expected_answer")),
        "answer_aliases": [
            normalize_whitespace(item)
            for item in backtranslation.get("answer_aliases", [])
            if normalize_whitespace(item)
        ]
        if isinstance(backtranslation.get("answer_aliases"), list)
        else [],
    }


def parse_consistency_object(model_output: Any) -> Dict[str, Any]:
    model_output = root_object(model_output)
    consistency = first_object(model_output.get("consistency"))
    if not consistency and ("verdict" in model_output or "is_consistent" in model_output):
        consistency = model_output
    if not consistency:
        raise ValueError("Model response did not contain a consistency object.")

    verdict = normalize_whitespace(consistency.get("verdict")).lower()
    is_consistent = consistency.get("is_consistent")
    if not isinstance(is_consistent, bool):
        is_consistent = verdict == "passed"
    verdict = "passed" if is_consistent else "failed"

    return {
        "verdict": verdict,
        "is_consistent": is_consistent,
        "failure_type": normalize_whitespace(consistency.get("failure_type")),
        "reason": normalize_whitespace(consistency.get("reason")),
        "repair_instruction": normalize_whitespace(consistency.get("repair_instruction")),
    }


def translated_qa_id(source_qa_id: str, language: str) -> str:
    return re.sub(r"__en__", f"__{language}__", source_qa_id, count=1)


def variant_lookup(knowledge_pair: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for role in ("target", "neighbor"):
        for variant in english_variants(knowledge_pair, role):
            lookup[variant["qa_id"]] = variant
    return lookup


def card_for_role(knowledge_pair: Dict[str, Any], role: str) -> Dict[str, Any]:
    topic_payload = knowledge_pair.get(role) or {}
    card = dict((topic_payload.get("card") or {}))
    for key in ("topic_name", "topic_name_zh", "source_page", "source_page_zh"):
        if key in topic_payload:
            card[key] = topic_payload.get(key)
    return card


def safe_translated_answer_aliases(
    generated_aliases: Any,
    *,
    source_variant: Dict[str, Any],
    card: Dict[str, Any],
    expected_answer: str,
) -> Tuple[List[str], List[str]]:
    warnings: List[str] = []
    source_aliases = source_variant.get("answer_aliases")
    source_alias_count = len(source_aliases) if isinstance(source_aliases, list) else 0
    aliases: List[str] = []

    if not isinstance(generated_aliases, list):
        return aliases, warnings

    for item in generated_aliases:
        alias = normalize_whitespace(item)
        if not alias or alias == expected_answer:
            continue
        if is_topic_alias(alias, card):
            warnings.append(f"unsafe_answer_alias skipped topic alias={alias!r}")
            continue
        if not answer_alias_equivalent(alias, expected_answer):
            warnings.append(f"unsafe_answer_alias skipped non_equivalent alias={alias!r}")
            continue
        aliases.append(alias)

    aliases = list(dict.fromkeys(aliases))
    if source_alias_count == 0:
        if aliases:
            warnings.append("source QA has no answer_aliases; dropping generated target-language aliases")
        return [], warnings
    return aliases[:source_alias_count], warnings


def normalize_translation_variant(
    raw: Dict[str, Any],
    *,
    source_variant: Dict[str, Any],
    card: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    language = normalize_whitespace(raw.get("language")).lower()
    question = normalize_whitespace(raw.get("question"))
    expected_answer = normalize_whitespace(raw.get("expected_answer"))
    translation_note = normalize_whitespace(raw.get("translation_note"))

    if language == CANONICAL_LANGUAGE:
        return None, ["target language must not be English"]
    if not question:
        return None, ["missing question"]
    if not expected_answer:
        return None, ["missing expected_answer"]

    aliases, alias_warnings = safe_translated_answer_aliases(
        raw.get("answer_aliases"),
        source_variant=source_variant,
        card=card,
        expected_answer=expected_answer,
    )
    warnings.extend(alias_warnings)

    source_span = card.get("source_span_zh") if language == "zh" and card.get("source_span_zh") else card.get("source_span")

    variant = {
        "qa_id": translated_qa_id(source_variant["qa_id"], language),
        "source_qa_id": source_variant["qa_id"],
        "source_language": CANONICAL_LANGUAGE,
        "generation_stage": "translated_from_canonical_en",
        "translation_status": "accepted",
        "knowledge_pair_id": source_variant["knowledge_pair_id"],
        "card_id": source_variant["card_id"],
        "topic_role": source_variant["topic_role"],
        "variant_layer": source_variant["variant_layer"],
        "language": language,
        "question": question,
        "expected_answer": expected_answer,
        "answer_aliases": aliases,
        "relation_type": source_variant["relation_type"],
        "source_span": source_span,
    }
    if translation_note:
        variant["translation_note"] = translation_note
    return variant, warnings


def normalize_translation_output(
    knowledge_pair: Dict[str, Any],
    model_output: Dict[str, Any],
    language: str,
) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    translations = model_output.get("translations")
    if not isinstance(translations, list):
        empty_output = copy.deepcopy(knowledge_pair)
        empty_output["target_qa_variants"] = []
        empty_output["neighbor_qa_variants"] = []
        return empty_output, ["translations payload is not a list"]

    lookup = variant_lookup(knowledge_pair)
    merged = copy.deepcopy(knowledge_pair)
    merged_target: List[Dict[str, Any]] = []
    merged_neighbor: List[Dict[str, Any]] = []
    seen_source_ids: set = set()
    target_language = language

    for item in translations:
        if not isinstance(item, dict):
            warnings.append("skipped non-object translation item")
            continue
        source_qa_id = normalize_whitespace(item.get("source_qa_id"))
        source_variant = lookup.get(source_qa_id)
        if source_variant is None:
            warnings.append(f"unknown source_qa_id={source_qa_id!r}")
            continue

        item_language = normalize_whitespace(item.get("language")).lower()
        if item_language != target_language:
            warnings.append(
                f"source_qa_id={source_qa_id!r} returned mismatched language={item_language!r}"
            )
            continue
        if source_qa_id in seen_source_ids:
            warnings.append(f"duplicate translation for source_qa_id={source_qa_id!r}, language={target_language!r}")
            continue

        role = source_variant["topic_role"]
        card = card_for_role(knowledge_pair, role)
        variant, variant_warnings = normalize_translation_variant(
            item,
            source_variant=source_variant,
            card=card,
        )
        for warning in variant_warnings:
            warnings.append(f"{source_qa_id}: {warning}")
        if variant is None:
            continue

        if role == "target":
            merged_target.append(variant)
        else:
            merged_neighbor.append(variant)
        seen_source_ids.add(source_qa_id)

    expected_sources = list(lookup.values())
    for source_variant in expected_sources:
        if source_variant["qa_id"] not in seen_source_ids:
            warnings.append(
                f"missing translation for source_qa_id={source_variant['qa_id']!r}, language={target_language!r}"
            )

    merged["target_qa_variants"] = merged_target
    merged["neighbor_qa_variants"] = merged_neighbor
    return merged, warnings


def source_variants_with_cards(knowledge_pair: Dict[str, Any]) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    items: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for role in ("target", "neighbor"):
        card = card_for_role(knowledge_pair, role)
        for variant in english_variants(knowledge_pair, role):
            items.append((variant, card))
    return items


def call_json_model(
    session: requests.Session,
    args: argparse.Namespace,
    system_prompt: str,
    user_prompt: str,
) -> Dict[str, Any]:
    response_json = call_chat_completion(
        session=session,
        api_base=args.api_base,
        api_keys=args.api_keys,
        api_key_scheduler=getattr(args, "api_key_scheduler", None),
        model=args.model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=args.temperature,
        timeout=args.timeout,
    )
    return parse_model_json_response(response_json)


def failed_consistency(reason: str, failure_type: str = "model_output_error") -> Dict[str, Any]:
    return {
        "verdict": "failed",
        "is_consistent": False,
        "failure_type": failure_type,
        "reason": reason,
        "repair_instruction": "Regenerate the target-language QA so it preserves the source English QA exactly.",
    }


def translate_single_qa_with_backtranslation(
    session: requests.Session,
    args: argparse.Namespace,
    knowledge_pair: Dict[str, Any],
    source_variant: Dict[str, Any],
    card: Dict[str, Any],
    language: str,
) -> Tuple[Optional[Dict[str, Any]], List[str], List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    warnings: List[str] = []
    attempts: List[Dict[str, Any]] = []
    source_qa_id = source_variant["qa_id"]
    previous_candidate: Dict[str, Any] = {}
    previous_backtranslation: Dict[str, Any] = {}
    previous_consistency: Dict[str, Any] = {}

    for attempt_number in range(1, args.max_translation_attempts + 1):
        try:
            if attempt_number == 1:
                prompt = build_single_translation_prompt(knowledge_pair, source_variant, language)
            else:
                prompt = build_repair_translation_prompt(
                    knowledge_pair=knowledge_pair,
                    source_variant=source_variant,
                    language=language,
                    previous_candidate=previous_candidate,
                    backtranslation=previous_backtranslation,
                    consistency=previous_consistency,
                )
            translation_output = call_json_model(session, args, SYSTEM_PROMPT, prompt)
            raw_translation = parse_translation_object(translation_output, source_qa_id, language)
            candidate, variant_warnings = normalize_translation_variant(
                raw_translation,
                source_variant=source_variant,
                card=card,
            )
            for warning in variant_warnings:
                warnings.append(f"{source_qa_id}: {warning}")
            if candidate is None:
                previous_candidate = raw_translation
                previous_backtranslation = {}
                previous_consistency = failed_consistency("; ".join(variant_warnings) or "invalid translation")
                attempts.append(
                    {
                        "attempt": attempt_number,
                        "translation": raw_translation,
                        "backtranslation_en": {},
                        "consistency": previous_consistency,
                    }
                )
                continue

            backtranslation_output = call_json_model(
                session,
                args,
                SYSTEM_PROMPT,
                build_backtranslation_prompt(candidate, language),
            )
            backtranslation = parse_backtranslation_object(backtranslation_output, source_qa_id)
            consistency_output = call_json_model(
                session,
                args,
                SYSTEM_PROMPT,
                build_consistency_prompt(knowledge_pair, source_variant, candidate, backtranslation),
            )
            consistency = parse_consistency_object(consistency_output)
            attempt_record = {
                "attempt": attempt_number,
                "translation": {
                    "question": candidate.get("question"),
                    "expected_answer": candidate.get("expected_answer"),
                    "answer_aliases": candidate.get("answer_aliases", []),
                    "translation_note": candidate.get("translation_note", ""),
                },
                "backtranslation_en": backtranslation,
                "consistency": consistency,
            }
            attempts.append(attempt_record)

            if consistency["is_consistent"]:
                candidate["translation_status"] = "accepted"
                candidate["backtranslation_status"] = "passed"
                candidate["backtranslation_en"] = backtranslation
                candidate["backtranslation_consistency"] = consistency
                candidate["translation_attempts"] = attempt_number
                return candidate, warnings, attempts, None

            previous_candidate = candidate
            previous_backtranslation = backtranslation
            previous_consistency = consistency
        except (ValueError, json.JSONDecodeError) as exc:
            previous_consistency = failed_consistency(str(exc))
            attempts.append(
                {
                    "attempt": attempt_number,
                    "translation": previous_candidate,
                    "backtranslation_en": previous_backtranslation,
                    "consistency": previous_consistency,
                }
            )
            warnings.append(f"{source_qa_id}: {exc}")

    failed_record = {
        "source_qa_id": source_qa_id,
        "knowledge_pair_id": source_variant.get("knowledge_pair_id"),
        "card_id": source_variant.get("card_id"),
        "topic_role": source_variant.get("topic_role"),
        "variant_layer": source_variant.get("variant_layer"),
        "language": language,
        "translation_status": "failed_backtranslation",
        "backtranslation_status": "failed",
        "translation_attempts": len(attempts),
        "final_consistency": previous_consistency or failed_consistency("maximum attempts reached"),
        "attempt_history": attempts,
    }
    return None, warnings, attempts, failed_record


def normalize_translation_output_with_backtranslation(
    session: requests.Session,
    args: argparse.Namespace,
    knowledge_pair: Dict[str, Any],
    language: str,
) -> Tuple[Dict[str, Any], List[str], List[Dict[str, Any]], List[Dict[str, Any]]]:
    warnings: List[str] = []
    failed_records: List[Dict[str, Any]] = []
    attempt_history: List[Dict[str, Any]] = []
    merged = copy.deepcopy(knowledge_pair)
    merged_target: List[Dict[str, Any]] = []
    merged_neighbor: List[Dict[str, Any]] = []

    for source_variant, card in source_variants_with_cards(knowledge_pair):
        candidate, qa_warnings, attempts, failed_record = translate_single_qa_with_backtranslation(
            session=session,
            args=args,
            knowledge_pair=knowledge_pair,
            source_variant=source_variant,
            card=card,
            language=language,
        )
        warnings.extend(qa_warnings)
        attempt_history.append(
            {
                "source_qa_id": source_variant.get("qa_id"),
                "attempts": attempts,
            }
        )
        if failed_record is not None:
            failed_records.append(failed_record)
            continue
        if candidate is None:
            continue
        if candidate["topic_role"] == "target":
            merged_target.append(candidate)
        else:
            merged_neighbor.append(candidate)

    merged["target_qa_variants"] = merged_target
    merged["neighbor_qa_variants"] = merged_neighbor
    return merged, warnings, failed_records, attempt_history


def load_or_translate_knowledge_pair(
    session: requests.Session,
    args: argparse.Namespace,
    knowledge_pair: Dict[str, Any],
    language: str,
    cache_dir: Path,
) -> Tuple[Dict[str, Any], List[str], List[Dict[str, Any]]]:
    knowledge_pair_id = knowledge_pair["knowledge_pair_id"]
    safe_id = slugify(knowledge_pair_id)
    raw_path = cache_dir / f"{safe_id}__{language}.raw.json"
    normalized_path = cache_dir / f"{safe_id}__{language}.normalized.json"
    attempts_path = cache_dir / f"{safe_id}__{language}.attempts.json"

    if normalized_path.exists() and not args.refresh_cache:
        cached_normalized = read_json(normalized_path)
        if (
            cached_normalized.get("prompt_version") == PROMPT_VERSION
            and cached_normalized.get("backtranslation_enabled") == args.enable_backtranslation
        ):
            return (
                cached_normalized["knowledge_card_pair"],
                cached_normalized.get("warnings", []),
                cached_normalized.get("failed_backtranslation", []),
            )

    if args.enable_backtranslation:
        normalized_pair, warnings, failed_records, attempt_history = normalize_translation_output_with_backtranslation(
            session=session,
            args=args,
            knowledge_pair=knowledge_pair,
            language=language,
        )
        cached_attempts = {
            "prompt_version": PROMPT_VERSION,
            "knowledge_pair_id": knowledge_pair_id,
            "source_language": CANONICAL_LANGUAGE,
            "target_language": language,
            "model": args.model,
            "api_base": normalize_api_base(args.api_base),
            "attempt_history": attempt_history,
            "generated_at": utc_now(),
        }
        write_json_atomic(attempts_path, cached_attempts)
        cached_normalized = {
            "prompt_version": PROMPT_VERSION,
            "backtranslation_enabled": True,
            "knowledge_card_pair": normalized_pair,
            "warnings": warnings,
            "failed_backtranslation": failed_records,
            "normalized_at": utc_now(),
        }
        write_json_atomic(normalized_path, cached_normalized)
        return normalized_pair, warnings, failed_records

    raw_payload: Optional[Dict[str, Any]] = None
    if raw_path.exists() and not args.refresh_cache:
        cached_raw = read_json(raw_path)
        if cached_raw.get("prompt_version") == PROMPT_VERSION:
            raw_payload = cached_raw

    if raw_payload is None:
        user_prompt = build_translation_prompt(knowledge_pair, language)
        response_json = call_chat_completion(
            session=session,
            api_base=args.api_base,
            api_keys=args.api_keys,
            api_key_scheduler=getattr(args, "api_key_scheduler", None),
            model=args.model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=args.temperature,
            timeout=args.timeout,
        )
        raw_payload = {
            "knowledge_pair_id": knowledge_pair_id,
            "prompt_version": PROMPT_VERSION,
            "generated_at": utc_now(),
            "model": args.model,
            "api_base": normalize_api_base(args.api_base),
            "source_language": CANONICAL_LANGUAGE,
            "target_language": language,
            "response": response_json,
        }
        write_json_atomic(raw_path, raw_payload)

    model_output = parse_model_json_response(raw_payload["response"])
    normalized_pair, warnings = normalize_translation_output(
        knowledge_pair=knowledge_pair,
        model_output=model_output,
        language=language,
    )
    for role in ("target_qa_variants", "neighbor_qa_variants"):
        for variant in normalized_pair.get(role, []):
            variant["backtranslation_status"] = "skipped"
            variant["translation_attempts"] = 1

    cached_normalized = {
        "prompt_version": PROMPT_VERSION,
        "backtranslation_enabled": False,
        "knowledge_card_pair": normalized_pair,
        "warnings": warnings,
        "failed_backtranslation": [],
        "normalized_at": utc_now(),
    }
    write_json_atomic(normalized_path, cached_normalized)
    return normalized_pair, warnings, []


def build_output_document(
    source_data: Dict[str, Any],
    source_file: str,
    model: str,
    api_base: str,
    language: str,
    topic_pairs: List[Dict[str, Any]],
    warnings: List[str],
    failed_records: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    failed_records = failed_records or []
    knowledge_pair_count = sum(len(pair.get("knowledge_card_pairs", [])) for pair in topic_pairs)
    qa_variant_count = 0
    for topic_pair in topic_pairs:
        for knowledge_pair in topic_pair.get("knowledge_card_pairs", []):
            qa_variant_count += len(knowledge_pair.get("target_qa_variants", []))
            qa_variant_count += len(knowledge_pair.get("neighbor_qa_variants", []))
    repair_attempt_count = 0
    for record in failed_records:
        repair_attempt_count += max(0, int(record.get("translation_attempts") or 0) - 1)

    return {
        "step": "Step 6 QA direct translation",
        "prompt_version": PROMPT_VERSION,
        "generated_at": utc_now(),
        "source_file": source_file,
        "source_step": source_data.get("step"),
        "source_generated_at": source_data.get("generated_at"),
        "model": model,
        "api_base": normalize_api_base(api_base),
        "translation_config": {
            "source_language": CANONICAL_LANGUAGE,
            "target_language": language,
            "generation_stage": "translated_from_canonical_en",
        },
        "summary": {
            "topic_pair_count": len(topic_pairs),
            "knowledge_pair_count": knowledge_pair_count,
            "qa_variant_count": qa_variant_count,
            "accepted_qa_count": qa_variant_count,
            "failed_backtranslation_count": len(failed_records),
            "repair_attempt_count": repair_attempt_count,
            "warning_count": len(warnings),
        },
        "warnings": warnings,
        "topic_pairs": topic_pairs,
    }


def build_failed_output_document(
    source_data: Dict[str, Any],
    source_file: str,
    model: str,
    api_base: str,
    language: str,
    failed_records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "step": "Step 6 failed back-translation queue",
        "prompt_version": PROMPT_VERSION,
        "generated_at": utc_now(),
        "source_file": source_file,
        "source_step": source_data.get("step"),
        "source_generated_at": source_data.get("generated_at"),
        "model": model,
        "api_base": normalize_api_base(api_base),
        "translation_config": {
            "source_language": CANONICAL_LANGUAGE,
            "target_language": language,
            "generation_stage": "translated_from_canonical_en",
        },
        "summary": {
            "failed_backtranslation_count": len(failed_records),
        },
        "failed_backtranslation": failed_records,
    }


def english_qa_count(topic_pairs: Sequence[Dict[str, Any]]) -> int:
    count = 0
    for topic_pair in topic_pairs:
        for knowledge_pair in topic_pair.get("knowledge_card_pairs", []):
            count += len(english_variants(knowledge_pair, "target"))
            count += len(english_variants(knowledge_pair, "neighbor"))
    return count


def build_work_items(
    topic_pairs: Sequence[Dict[str, Any]],
    args: argparse.Namespace,
) -> Tuple[List[Dict[str, Any]], List[Tuple[int, int, Dict[str, Any]]]]:
    output_topic_pairs: List[Dict[str, Any]] = []
    work_items: List[Tuple[int, int, Dict[str, Any]]] = []
    processed_knowledge_pairs = 0

    for topic_pair in topic_pairs:
        output_topic_pair = {
            key: copy.deepcopy(value)
            for key, value in topic_pair.items()
            if key != "knowledge_card_pairs"
        }
        output_index: Optional[int] = None
        pair_order = 0

        for knowledge_pair in selected_knowledge_pairs(topic_pair, args):
            if args.max_knowledge_pairs is not None and processed_knowledge_pairs >= args.max_knowledge_pairs:
                break
            if output_index is None:
                output_index = len(output_topic_pairs)
                output_topic_pair["knowledge_card_pairs"] = []
                output_topic_pairs.append(output_topic_pair)
            work_items.append((output_index, pair_order, knowledge_pair))
            pair_order += 1
            processed_knowledge_pairs += 1

        if args.max_knowledge_pairs is not None and processed_knowledge_pairs >= args.max_knowledge_pairs:
            break

    return output_topic_pairs, work_items


def process_knowledge_pair_work_item(
    args: argparse.Namespace,
    language: str,
    cache_dir: Path,
    topic_index: int,
    pair_order: int,
    knowledge_pair: Dict[str, Any],
) -> Tuple[int, int, Dict[str, Any], List[str], List[Dict[str, Any]]]:
    session = requests.Session()
    knowledge_pair_id = knowledge_pair.get("knowledge_pair_id")
    log(f"Translating QA variants for {knowledge_pair_id}")
    translated_pair, pair_warnings, failed_records = load_or_translate_knowledge_pair(
        session=session,
        args=args,
        knowledge_pair=knowledge_pair,
        language=language,
        cache_dir=cache_dir,
    )
    prefixed_warnings = [f"{knowledge_pair_id}: {warning}" for warning in pair_warnings]
    return topic_index, pair_order, translated_pair, prefixed_warnings, failed_records


def main() -> None:
    args = parse_args()
    language = resolve_target_language(args)
    if not args.output:
        args.output = default_output_path(language)
    if not args.failed_output:
        args.failed_output = f"data/qa_variants.{language}.failed_backtranslation.json"
    if args.max_translation_attempts < 1:
        raise SystemExit("--max-translation-attempts must be at least 1.")
    if args.workers < 1:
        raise SystemExit("--workers must be at least 1.")

    resolve_runtime_settings(args)
    if not args.dry_run:
        ensure_api_args(args)
        args.api_key_scheduler = RoundRobinKeyScheduler()
    else:
        args.api_key_scheduler = None

    input_path = Path(args.input)
    output_path = Path(args.output)
    cache_dir = Path(args.cache_dir)

    source_data = read_json(input_path)
    topic_pairs = filter_topic_pairs(source_data.get("topic_pairs", []), args)
    selected_count = sum(len(selected_knowledge_pairs(pair, args)) for pair in topic_pairs)
    if args.max_knowledge_pairs is not None:
        selected_count = min(selected_count, args.max_knowledge_pairs)

    if args.dry_run:
        log(f"Selected topic pairs: {len(topic_pairs)}")
        log(f"Selected knowledge card pairs: {selected_count}")
        log(f"Target language: {language}")
        selected_topic_pairs_for_count = []
        processed_knowledge_pairs = 0
        for topic_pair in topic_pairs:
            output_topic_pair = {
                key: copy.deepcopy(value)
                for key, value in topic_pair.items()
                if key != "knowledge_card_pairs"
            }
            output_topic_pair["knowledge_card_pairs"] = []
            for knowledge_pair in selected_knowledge_pairs(topic_pair, args):
                if args.max_knowledge_pairs is not None and processed_knowledge_pairs >= args.max_knowledge_pairs:
                    break
                output_topic_pair["knowledge_card_pairs"].append(knowledge_pair)
                processed_knowledge_pairs += 1
            if output_topic_pair["knowledge_card_pairs"]:
                selected_topic_pairs_for_count.append(output_topic_pair)
            if args.max_knowledge_pairs is not None and processed_knowledge_pairs >= args.max_knowledge_pairs:
                break
        english_count = english_qa_count(selected_topic_pairs_for_count)
        log(f"Selected English canonical QA: {english_count}")
        log(f"Expected translated QA variants in output file: {english_count}")
        log(f"Back-translation enabled: {args.enable_backtranslation}")
        if args.enable_backtranslation:
            log(f"Max translation attempts per QA: {args.max_translation_attempts}")
            log(f"Failed back-translation output: {args.failed_output}")
        log(f"Workers: {args.workers}")
        log(f"Configured API keys: {len(args.api_keys)}")
        log(f"Max distinct first-choice keys in parallel: {min(args.workers, len(args.api_keys))}")
        log("English canonical QA remain in the Step-5 source file.")
        return

    processed_topic_pairs, work_items = build_work_items(topic_pairs, args)
    warnings: List[str] = []
    failed_records: List[Dict[str, Any]] = []
    pair_results: Dict[Tuple[int, int], Dict[str, Any]] = {}

    if args.workers == 1:
        for topic_index, pair_order, knowledge_pair in work_items:
            result = process_knowledge_pair_work_item(
                args=args,
                language=language,
                cache_dir=cache_dir,
                topic_index=topic_index,
                pair_order=pair_order,
                knowledge_pair=knowledge_pair,
            )
            result_topic_index, result_pair_order, translated_pair, pair_warnings, pair_failures = result
            pair_results[(result_topic_index, result_pair_order)] = translated_pair
            warnings.extend(pair_warnings)
            failed_records.extend(pair_failures)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [
                executor.submit(
                    process_knowledge_pair_work_item,
                    args,
                    language,
                    cache_dir,
                    topic_index,
                    pair_order,
                    knowledge_pair,
                )
                for topic_index, pair_order, knowledge_pair in work_items
            ]
            for future in as_completed(futures):
                result_topic_index, result_pair_order, translated_pair, pair_warnings, pair_failures = future.result()
                pair_results[(result_topic_index, result_pair_order)] = translated_pair
                warnings.extend(pair_warnings)
                failed_records.extend(pair_failures)

    for topic_index, topic_pair in enumerate(processed_topic_pairs):
        topic_pair["knowledge_card_pairs"] = [
            pair_results[(topic_index, pair_order)]
            for pair_order in sorted(
                order
                for result_topic_index, order in pair_results
                if result_topic_index == topic_index
            )
        ]

    output_doc = build_output_document(
        source_data=source_data,
        source_file=str(input_path),
        model=args.model,
        api_base=args.api_base,
        language=language,
        topic_pairs=processed_topic_pairs,
        warnings=warnings,
        failed_records=failed_records,
    )
    write_json_atomic(output_path, output_doc)
    if args.enable_backtranslation:
        failed_doc = build_failed_output_document(
            source_data=source_data,
            source_file=str(input_path),
            model=args.model,
            api_base=args.api_base,
            language=language,
            failed_records=failed_records,
        )
        write_json_atomic(Path(args.failed_output), failed_doc)
    log(
        f"Wrote {output_path} with "
        f"{output_doc['summary']['qa_variant_count']} {language} QA variants "
        f"{output_doc['summary']['failed_backtranslation_count']} failed back-translations "
        f"and {output_doc['summary']['warning_count']} warnings."
    )


if __name__ == "__main__":
    main()
