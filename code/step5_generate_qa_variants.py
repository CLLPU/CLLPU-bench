#!/usr/bin/env python3
"""Generate Step-5 English canonical core/surface QA variants from relation-matched card pairs."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests


PROMPT_VERSION = "step5_en_canonical_v3"

SYSTEM_PROMPT = """You generate QA probes for a cross-lingual unlearning benchmark.

Return JSON only.
Each QA must probe exactly one provided knowledge card.
Do not add facts, do not change the relation, and do not ask about neighboring facts.
Questions must be answer-aware: the semantic focus of each question must point to
the card answer, not merely restate the fact_statement in a vague way.
The benchmark has only two variant layers: core and surface.
Core is the most direct factual question. Surface variants are diverse same-language rewrites
that keep the same expected answer and relation.
Do not leak the expected answer in the question text.
Do not produce mixed-language prompts, code-switching, bridge-language prompts, or
query/answer language mismatch.
Generate English only in this step. Other languages are handled in a later translation/localization step.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="config/llm_api.env",
        help="Local env-style config file for LLM API settings.",
    )
    parser.add_argument(
        "--input",
        default="data/selected_knowledge_card_pairs.json",
        help="Input Step-4.5 selected knowledge-card pair JSON.",
    )
    parser.add_argument(
        "--output",
        default="data/qa_variants.en.json",
        help="Output Step-5 English canonical QA variant JSON.",
    )
    parser.add_argument(
        "--cache-dir",
        default="data/step5_qa_variant_cache",
        help="Directory for per-knowledge-pair raw and normalized cache files.",
    )
    parser.add_argument(
        "--surface-count",
        type=int,
        default=3,
        help="Number of English surface variants per card.",
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
        help="Model name for QA generation.",
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
        default=0.4,
        help="Sampling temperature.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Force fresh API calls even if cached outputs exist.",
    )
    parser.add_argument(
        "--refresh-normalized-cache",
        action="store_true",
        help=(
            "Rebuild normalized cache and output from cached raw API responses "
            "without forcing fresh API calls."
        ),
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


def resolve_runtime_settings(args: argparse.Namespace) -> None:
    config_values = load_env_config_file(Path(args.config))
    args.api_base = (
        args.api_base
        or os.environ.get("STEP5_API_BASE")
        or os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("API_BASE")
        or os.environ.get("STEP3_API_BASE")
        or config_values.get("STEP5_API_BASE")
        or config_values.get("OPENAI_BASE_URL")
        or config_values.get("API_BASE")
        or config_values.get("STEP3_API_BASE")
        or ""
    )
    args.api_keys = resolve_api_keys(
        args.api_key,
        os.environ.get("STEP5_API_KEYS", ""),
        os.environ.get("OPENAI_API_KEYS", ""),
        os.environ.get("API_KEYS", ""),
        os.environ.get("STEP5_API_KEY", ""),
        os.environ.get("OPENAI_API_KEY", ""),
        os.environ.get("API_KEY", ""),
        os.environ.get("STEP3_API_KEYS", ""),
        os.environ.get("STEP3_API_KEY", ""),
        config_values.get("STEP5_API_KEYS", ""),
        config_values.get("OPENAI_API_KEYS", ""),
        config_values.get("API_KEYS", ""),
        config_values.get("STEP5_API_KEY", ""),
        config_values.get("OPENAI_API_KEY", ""),
        config_values.get("API_KEY", ""),
        config_values.get("STEP3_API_KEYS", ""),
        config_values.get("STEP3_API_KEY", ""),
    )
    args.api_key = args.api_keys[0] if args.api_keys else ""
    args.model = (
        args.model
        or os.environ.get("STEP5_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or os.environ.get("MODEL")
        or os.environ.get("STEP3_MODEL")
        or config_values.get("STEP5_MODEL")
        or config_values.get("OPENAI_MODEL")
        or config_values.get("MODEL")
        or config_values.get("STEP3_MODEL")
        or "gemini-3.1-pro-preview-thinking"
    )


def ensure_api_args(args: argparse.Namespace) -> None:
    if not args.api_base:
        raise SystemExit("Missing API base. Use --api-base or set STEP5_API_BASE / OPENAI_BASE_URL / API_BASE.")
    if not getattr(args, "api_keys", None):
        raise SystemExit(
            "Missing API key. Use --api-key or set STEP5_API_KEY / STEP5_API_KEYS / OPENAI_API_KEY / OPENAI_API_KEYS / API_KEY / API_KEYS."
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
    return re.sub(r"[^\w]+", " ", normalize_whitespace(text).casefold()).strip()


def match_tokens(text: Any) -> List[str]:
    return [token for token in normalize_for_match(text).split() if token]


MONTH_TOKEN_NORMALIZATION = {
    "jan": "january",
    "feb": "february",
    "mar": "march",
    "apr": "april",
    "jun": "june",
    "jul": "july",
    "aug": "august",
    "sep": "september",
    "sept": "september",
    "oct": "october",
    "nov": "november",
    "dec": "december",
}


def canonical_alias_tokens(text: Any) -> List[str]:
    tokens = []
    for token in match_tokens(text):
        token = re.sub(r"^(\d+)(st|nd|rd|th)$", r"\1", token)
        tokens.append(MONTH_TOKEN_NORMALIZATION.get(token, token))
    return tokens


def phrase_in_text(phrase: str, text: str) -> bool:
    normalized_phrase = normalize_for_match(phrase)
    normalized_text = normalize_for_match(text)
    if not normalized_phrase or not normalized_text:
        return False
    return f" {normalized_phrase} " in f" {normalized_text} "


def slugify(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return value or "item"


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
    compact["source_page"] = topic_payload.get("source_page")
    compact["source_page_zh"] = topic_payload.get("source_page_zh")
    return compact


def build_generation_prompt(
    knowledge_pair: Dict[str, Any],
    surface_count: int,
) -> str:
    prompt_payload = {
        "knowledge_pair_id": knowledge_pair.get("knowledge_pair_id"),
        "pair_id": knowledge_pair.get("pair_id"),
        "relation_type": knowledge_pair.get("relation_type"),
        "relation_type_zh": knowledge_pair.get("relation_type_zh"),
        "target": compact_card(knowledge_pair.get("target") or {}),
        "neighbor": compact_card(knowledge_pair.get("neighbor") or {}),
    }

    total_per_card = 1 + surface_count
    return f"""Generate English canonical QA probes for the following relation-matched knowledge pair.

For each of target and neighbor, generate exactly:
- 1 English core QA
- {surface_count} English surface QA variants

This means each card should have {total_per_card} English QA items.

Rules:
1. Every QA must ask about the same single fact as its source card.
2. Design each question backward from the card answer. The question must make the answer the only natural short answer.
3. Keep the relation_type unchanged.
4. Keep expected_answer equal to the card answer unless the card answer is not English; if so, use the English equivalent and include the card answer as an alias.
5. Do not leak expected_answer or answer aliases inside the question text.
6. Surface variants should be meaningfully different in wording or question shape, but not a separate taxonomy.
7. Use answer aliases only when they are clear, non-ambiguous, and equivalent to the answer. Do not use topic aliases as answer aliases.
8. Do not ask about dates, people, mechanisms, locations, or causes unless that is the provided relation.
9. Write all questions and expected answers in English only.
10. Do not include mixed-language prompts.

Return JSON only with this schema:
{{
  "target_qa_variants": [
    {{
      "language": "en",
      "variant_layer": "core",
      "question": "...",
      "expected_answer": "...",
      "answer_aliases": ["..."],
      "rewrite_note": "direct core question"
    }}
  ],
  "neighbor_qa_variants": [
    {{
      "language": "en",
      "variant_layer": "surface",
      "question": "...",
      "expected_answer": "...",
      "answer_aliases": ["..."],
      "rewrite_note": "brief description of surface difference"
    }}
  ]
}}

Knowledge pair:
{json.dumps(prompt_payload, ensure_ascii=False, indent=2)}
"""


def call_chat_completion(
    session: requests.Session,
    api_base: str,
    api_keys: Sequence[str],
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
        for key_index, api_key in enumerate(api_keys, start=1):
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


def extract_json_object(text: str) -> Dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def parse_model_json_response(response_json: Dict[str, Any]) -> Dict[str, Any]:
    return extract_json_object(extract_message_text(response_json))


def source_card_aliases(card: Dict[str, Any]) -> List[str]:
    aliases = card.get("aliases")
    if not isinstance(aliases, list):
        return []
    return list(dict.fromkeys(normalize_whitespace(item) for item in aliases if normalize_whitespace(item)))


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


def safe_answer_aliases(
    generated_aliases: Any,
    *,
    card: Dict[str, Any],
    expected_answer: str,
) -> Tuple[List[str], List[str]]:
    warnings: List[str] = []
    aliases: List[str] = []
    raw_values: List[Tuple[str, str]] = []

    if isinstance(generated_aliases, list):
        raw_values.extend(
            ("generated", normalize_whitespace(item))
            for item in generated_aliases
            if normalize_whitespace(item)
        )
    raw_values.extend(("card", alias) for alias in source_card_aliases(card))

    for source, alias in raw_values:
        if alias == expected_answer:
            continue
        if is_topic_alias(alias, card):
            continue
        if not answer_alias_equivalent(alias, expected_answer):
            continue
        aliases.append(alias)

    return list(dict.fromkeys(aliases)), warnings


def leakage_terms(expected_answer: str, aliases: Sequence[str]) -> List[str]:
    terms = []
    for term in [expected_answer, *aliases]:
        normalized = normalize_for_match(term)
        if not normalized:
            continue
        compact = normalized.replace(" ", "")
        if len(compact) < 3 and not any(ch.isdigit() for ch in compact):
            continue
        terms.append(term)
    return list(dict.fromkeys(terms))


def answer_leakage_warnings(question: str, expected_answer: str, aliases: Sequence[str], card: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []
    for term in leakage_terms(expected_answer, aliases):
        if is_topic_alias(term, card):
            continue
        if phrase_in_text(term, question):
            warnings.append(f"answer_leakage_in_question: question contains answer term {term!r}")
    return warnings


def normalize_variant(
    raw: Dict[str, Any],
    *,
    knowledge_pair: Dict[str, Any],
    role: str,
    card: Dict[str, Any],
    sequence: int,
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    language = normalize_whitespace(raw.get("language") or "en").lower()
    variant_layer = normalize_whitespace(raw.get("variant_layer")).lower()
    question = normalize_whitespace(raw.get("question"))
    generated_expected_answer = normalize_whitespace(raw.get("expected_answer"))
    card_answer = normalize_whitespace(card.get("answer"))
    expected_answer = card_answer or generated_expected_answer
    rewrite_note = normalize_whitespace(raw.get("rewrite_note"))

    if variant_layer not in {"core", "surface"}:
        return None, [f"invalid variant_layer={variant_layer!r}"]
    if language != "en":
        return None, [f"invalid language={language!r}; Step 5 only allows English canonical QA"]
    if not question:
        return None, ["missing question"]
    if not generated_expected_answer:
        return None, ["missing expected_answer"]
    if card_answer and not answer_alias_equivalent(generated_expected_answer, card_answer):
        warnings.append(
            "question_answer_focus_mismatch: generated expected_answer "
            f"{generated_expected_answer!r} is not equivalent to card answer {card_answer!r}; "
            "using card answer"
        )

    aliases, alias_warnings = safe_answer_aliases(
        raw.get("answer_aliases"),
        card=card,
        expected_answer=expected_answer,
    )
    warnings.extend(alias_warnings)
    if generated_expected_answer and generated_expected_answer != expected_answer:
        if answer_alias_equivalent(generated_expected_answer, expected_answer):
            aliases = list(dict.fromkeys([generated_expected_answer, *aliases]))
        else:
            warnings.append(f"unsafe_answer_alias skipped generated expected_answer={generated_expected_answer!r}")
    warnings.extend(answer_leakage_warnings(question, expected_answer, aliases, card))

    suffix = "core" if variant_layer == "core" else f"surface_{sequence:03d}"
    qa_id = (
        f"{knowledge_pair.get('knowledge_pair_id')}__{role}"
        f"__{card.get('card_id', 'card')}__{language}__{suffix}"
    )
    source_span = card.get("source_span")

    variant = {
        "qa_id": qa_id,
        "knowledge_pair_id": knowledge_pair.get("knowledge_pair_id"),
        "card_id": card.get("card_id"),
        "topic_role": role,
        "variant_layer": variant_layer,
        "language": language,
        "question": question,
        "expected_answer": expected_answer,
        "answer_aliases": aliases,
        "source_card_aliases": source_card_aliases(card),
        "relation_type": knowledge_pair.get("relation_type"),
        "source_span": source_span,
    }
    if rewrite_note:
        variant["rewrite_note"] = rewrite_note
    return variant, warnings


def normalize_variant_list(
    raw_variants: Any,
    *,
    knowledge_pair: Dict[str, Any],
    role: str,
    surface_count: int,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    if not isinstance(raw_variants, list):
        return [], [f"{role}: variants payload is not a list"]

    role_payload = knowledge_pair.get(role) or {}
    card = copy.deepcopy(role_payload.get("card") or {})
    for key in ("topic_name", "topic_name_zh", "source_page", "source_page_zh"):
        if key in role_payload and key not in card:
            card[key] = role_payload.get(key)
    normalized: List[Dict[str, Any]] = []
    seen_questions: set = set()
    seen_variant_warnings: set = set()
    surface_count_seen = 0
    core_seen = False

    for index, raw in enumerate(raw_variants, start=1):
        if not isinstance(raw, dict):
            warnings.append(f"{role}/{index}: skipped non-object variant")
            continue

        language = normalize_whitespace(raw.get("language") or "en").lower()
        layer = normalize_whitespace(raw.get("variant_layer")).lower()
        if language != "en":
            warnings.append(f"{role}/{index}: skipped non-English variant language={language!r}")
            continue

        if layer == "surface":
            if surface_count_seen >= surface_count:
                warnings.append(f"{role}/en: skipped extra surface variant beyond {surface_count}")
                continue
            sequence = surface_count_seen + 1
        elif layer == "core":
            sequence = 0
            if core_seen:
                warnings.append(f"{role}/en: skipped duplicate core variant")
                continue
        else:
            sequence = 0

        variant, variant_warnings = normalize_variant(
            raw,
            knowledge_pair=knowledge_pair,
            role=role,
            card=card,
            sequence=sequence,
        )
        for warning in variant_warnings:
            if warning in seen_variant_warnings:
                continue
            seen_variant_warnings.add(warning)
            warnings.append(f"{role}/{index}: {warning}")
        if variant is None:
            continue

        question_signature = (variant["language"], normalize_whitespace(variant["question"]).lower())
        if question_signature in seen_questions:
            warnings.append(f"{role}/{index}: duplicate question skipped")
            continue
        seen_questions.add(question_signature)
        normalized.append(variant)
        if layer == "surface":
            surface_count_seen += 1
        elif layer == "core":
            core_seen = True

    if not core_seen:
        warnings.append(f"{role}/en: missing core variant")
    if surface_count_seen < surface_count:
        warnings.append(
            f"{role}/en: expected {surface_count} surface variants, "
            f"got {surface_count_seen}"
        )
    return normalized, warnings


def normalize_pair_output(
    knowledge_pair: Dict[str, Any],
    model_output: Dict[str, Any],
    surface_count: int,
) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    target_variants, target_warnings = normalize_variant_list(
        model_output.get("target_qa_variants"),
        knowledge_pair=knowledge_pair,
        role="target",
        surface_count=surface_count,
    )
    neighbor_variants, neighbor_warnings = normalize_variant_list(
        model_output.get("neighbor_qa_variants"),
        knowledge_pair=knowledge_pair,
        role="neighbor",
        surface_count=surface_count,
    )
    warnings.extend(target_warnings)
    warnings.extend(neighbor_warnings)

    normalized = copy.deepcopy(knowledge_pair)
    normalized["target_qa_variants"] = target_variants
    normalized["neighbor_qa_variants"] = neighbor_variants
    return normalized, warnings


def cache_key_suffix(surface_count: int) -> str:
    return f"en__surface{surface_count}"


def load_or_generate_knowledge_pair(
    session: requests.Session,
    args: argparse.Namespace,
    knowledge_pair: Dict[str, Any],
    cache_dir: Path,
) -> Tuple[Dict[str, Any], List[str]]:
    knowledge_pair_id = knowledge_pair["knowledge_pair_id"]
    suffix = cache_key_suffix(args.surface_count)
    safe_id = slugify(knowledge_pair_id)
    raw_path = cache_dir / f"{safe_id}__{suffix}.raw.json"
    normalized_path = cache_dir / f"{safe_id}__{suffix}.normalized.json"

    if normalized_path.exists() and not args.refresh_cache and not args.refresh_normalized_cache:
        cached_normalized = read_json(normalized_path)
        if cached_normalized.get("prompt_version") == PROMPT_VERSION:
            return cached_normalized["knowledge_card_pair"], cached_normalized.get("warnings", [])

    raw_payload: Optional[Dict[str, Any]] = None
    if raw_path.exists() and not args.refresh_cache:
        cached_raw = read_json(raw_path)
        if cached_raw.get("prompt_version") == PROMPT_VERSION:
            raw_payload = cached_raw

    if raw_payload is None:
        user_prompt = build_generation_prompt(
            knowledge_pair=knowledge_pair,
            surface_count=args.surface_count,
        )
        response_json = call_chat_completion(
            session=session,
            api_base=args.api_base,
            api_keys=args.api_keys,
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
            "canonical_language": "en",
            "surface_count": args.surface_count,
            "response": response_json,
        }
        write_json_atomic(raw_path, raw_payload)

    model_output = parse_model_json_response(raw_payload["response"])
    normalized_pair, warnings = normalize_pair_output(
        knowledge_pair=knowledge_pair,
        model_output=model_output,
        surface_count=args.surface_count,
    )

    cached_normalized = {
        "prompt_version": PROMPT_VERSION,
        "knowledge_card_pair": normalized_pair,
        "warnings": warnings,
        "normalized_at": utc_now(),
    }
    write_json_atomic(normalized_path, cached_normalized)
    return normalized_pair, warnings


def build_output_document(
    source_data: Dict[str, Any],
    source_file: str,
    model: str,
    api_base: str,
    surface_count: int,
    topic_pairs: List[Dict[str, Any]],
    warnings: List[str],
) -> Dict[str, Any]:
    knowledge_pair_count = sum(len(pair.get("knowledge_card_pairs", [])) for pair in topic_pairs)
    qa_variant_count = 0
    for topic_pair in topic_pairs:
        for knowledge_pair in topic_pair.get("knowledge_card_pairs", []):
            qa_variant_count += len(knowledge_pair.get("target_qa_variants", []))
            qa_variant_count += len(knowledge_pair.get("neighbor_qa_variants", []))

    return {
        "step": "Step 5 QA variant generation",
        "prompt_version": PROMPT_VERSION,
        "generated_at": utc_now(),
        "source_file": source_file,
        "source_step": source_data.get("step"),
        "source_generated_at": source_data.get("generated_at"),
        "model": model,
        "api_base": normalize_api_base(api_base),
        "qa_config": {
            "variant_layers": ["core", "surface"],
            "canonical_language": "en",
            "core_variants_per_card": 1,
            "surface_variants_per_card": surface_count,
        },
        "summary": {
            "topic_pair_count": len(topic_pairs),
            "knowledge_pair_count": knowledge_pair_count,
            "qa_variant_count": qa_variant_count,
            "warning_count": len(warnings),
        },
        "warnings": warnings,
        "topic_pairs": topic_pairs,
    }


def main() -> None:
    args = parse_args()
    if args.surface_count < 0:
        raise SystemExit("--surface-count must be non-negative.")

    resolve_runtime_settings(args)
    if not args.dry_run:
        ensure_api_args(args)

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
        log("Canonical language: en")
        log(f"Expected QA variants: {selected_count * 2 * (1 + args.surface_count)}")
        return

    processed_topic_pairs: List[Dict[str, Any]] = []
    warnings: List[str] = []
    processed_knowledge_pairs = 0

    session = requests.Session()
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

            knowledge_pair_id = knowledge_pair.get("knowledge_pair_id")
            log(f"Generating QA variants for {knowledge_pair_id}")
            generated_pair, pair_warnings = load_or_generate_knowledge_pair(
                session=session,
                args=args,
                knowledge_pair=knowledge_pair,
                cache_dir=cache_dir,
            )
            for warning in pair_warnings:
                warnings.append(f"{knowledge_pair_id}: {warning}")
            output_topic_pair["knowledge_card_pairs"].append(generated_pair)
            processed_knowledge_pairs += 1

        if output_topic_pair["knowledge_card_pairs"]:
            processed_topic_pairs.append(output_topic_pair)
        if args.max_knowledge_pairs is not None and processed_knowledge_pairs >= args.max_knowledge_pairs:
            break

    output_doc = build_output_document(
        source_data=source_data,
        source_file=str(input_path),
        model=args.model,
        api_base=args.api_base,
        surface_count=args.surface_count,
        topic_pairs=processed_topic_pairs,
        warnings=warnings,
    )
    write_json_atomic(output_path, output_doc)
    log(
        f"Wrote {output_path} with "
        f"{output_doc['summary']['qa_variant_count']} QA variants "
        f"and {output_doc['summary']['warning_count']} warnings."
    )


if __name__ == "__main__":
    main()
