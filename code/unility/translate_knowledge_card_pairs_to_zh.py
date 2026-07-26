#!/usr/bin/env python3
"""Translate review-friendly fields in knowledge_card_pairs.json into Chinese."""

from __future__ import annotations

import argparse
import copy
import hashlib
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


SCALAR_TRANSLATION_KEYS = {
    "step",
    "topic_type",
    "target_topic",
    "neighbor_topic",
    "relation_type",
    "quality_label",
    "topic_name",
    "topic_role",
    "source_page",
    "semantic_slot",
    "fact_statement",
    "answer",
    "answer_type",
    "section_title",
    "source_span",
    "card_type",
    "knowledge_scope",
    "eval_priority",
}

LIST_TRANSLATION_KEYS = {
    "aliases",
    "review_flags",
}

MAP_KEY_TRANSLATION_KEYS = {
    "target_relation_counts",
    "neighbor_relation_counts",
    "selected_relation_counts",
}

MAP_VALUE_TRANSLATION_KEYS = {
    "answer_type_pair",
}

SYSTEM_PROMPT = """You are a careful English-to-Chinese translator for benchmark review files.

Translate every input string into natural, concise Simplified Chinese.
Rules:
1. Return JSON only.
2. Keep the output order identical to the input order.
3. Preserve abbreviations, IDs, and code-like tokens when they should remain unchanged.
4. For well-known entities, use established Chinese names when appropriate.
5. For snake_case labels, translate them into readable Chinese phrases instead of keeping underscores.
6. Do not add explanations or notes.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="config/llm_api.env",
        help="Env-style config file for API settings.",
    )
    parser.add_argument(
        "--input",
        default="data/knowledge_card_pairs.json",
        help="Source JSON file to translate.",
    )
    parser.add_argument(
        "--output",
        default="data/knowledge_card_pairs.zh.json",
        help="Output JSON path for the bilingual review file.",
    )
    parser.add_argument(
        "--cache",
        default="data/translation_cache/knowledge_card_pairs.zh.cache.json",
        help="Persistent text-to-translation cache file.",
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
        help="Model name to use for translation.",
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
        default=0.0,
        help="Sampling temperature.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=40,
        help="Maximum number of unique strings per API request.",
    )
    parser.add_argument(
        "--max-batch-chars",
        type=int,
        default=12000,
        help="Maximum total characters per API request.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect translation workload without calling the API.",
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
        or os.environ.get("TRANSLATE_API_BASE")
        or os.environ.get("STEP3_API_BASE")
        or os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("API_BASE")
        or config_values.get("TRANSLATE_API_BASE")
        or config_values.get("STEP3_API_BASE")
        or config_values.get("OPENAI_BASE_URL")
        or config_values.get("API_BASE")
        or ""
    )
    args.api_keys = resolve_api_keys(
        args.api_key,
        os.environ.get("TRANSLATE_API_KEYS", ""),
        os.environ.get("STEP3_API_KEYS", ""),
        os.environ.get("OPENAI_API_KEYS", ""),
        os.environ.get("API_KEYS", ""),
        os.environ.get("TRANSLATE_API_KEY", ""),
        os.environ.get("STEP3_API_KEY", ""),
        os.environ.get("OPENAI_API_KEY", ""),
        os.environ.get("API_KEY", ""),
        config_values.get("TRANSLATE_API_KEYS", ""),
        config_values.get("STEP3_API_KEYS", ""),
        config_values.get("OPENAI_API_KEYS", ""),
        config_values.get("API_KEYS", ""),
        config_values.get("TRANSLATE_API_KEY", ""),
        config_values.get("STEP3_API_KEY", ""),
        config_values.get("OPENAI_API_KEY", ""),
        config_values.get("API_KEY", ""),
    )
    args.api_key = args.api_keys[0] if args.api_keys else ""
    args.model = (
        args.model
        or os.environ.get("TRANSLATE_MODEL")
        or os.environ.get("STEP3_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or os.environ.get("MODEL")
        or config_values.get("TRANSLATE_MODEL")
        or config_values.get("STEP3_MODEL")
        or config_values.get("OPENAI_MODEL")
        or config_values.get("MODEL")
        or "gemini-3.1-pro-preview-thinking"
    )


def ensure_api_args(args: argparse.Namespace) -> None:
    if not args.api_base:
        raise SystemExit("Missing API base. Use --api-base or set TRANSLATE_API_BASE / STEP3_API_BASE / OPENAI_BASE_URL / API_BASE.")
    if not getattr(args, "api_keys", None):
        raise SystemExit(
            "Missing API key. Use --api-key or set TRANSLATE_API_KEY / TRANSLATE_API_KEYS / STEP3_API_KEY / STEP3_API_KEYS / OPENAI_API_KEY / OPENAI_API_KEYS / API_KEY / API_KEYS."
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


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_translation_cache(path: Path) -> Dict[str, Dict[str, str]]:
    if not path.exists():
        return {}
    data = read_json(path)
    if not isinstance(data, dict):
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}


def save_translation_cache(path: Path, cache: Dict[str, Dict[str, str]]) -> None:
    write_json_atomic(path, cache)


def is_non_empty_string_list(value: Any) -> bool:
    return isinstance(value, list) and any(isinstance(item, str) and item.strip() for item in value)


def is_scalar_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_string_map(value: Any) -> bool:
    return isinstance(value, dict) and bool(value) and all(isinstance(key, str) for key in value)


def get_at_path(root: Any, path: Sequence[Any]) -> Any:
    node = root
    for part in path:
        node = node[part]
    return node


def collect_translation_jobs(node: Any, path: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
    jobs: List[Dict[str, Any]] = []

    if isinstance(node, dict):
        for key, value in node.items():
            current_path = path + (key,)

            if key in SCALAR_TRANSLATION_KEYS and is_scalar_string(value):
                jobs.append(
                    {
                        "job_type": "scalar",
                        "path": current_path,
                        "text": normalize_whitespace(value),
                    }
                )
                continue

            if key in LIST_TRANSLATION_KEYS and is_non_empty_string_list(value):
                jobs.append(
                    {
                        "job_type": "list",
                        "path": current_path,
                        "texts": [normalize_whitespace(item) for item in value],
                    }
                )
                continue

            if key in MAP_KEY_TRANSLATION_KEYS and is_string_map(value):
                jobs.append(
                    {
                        "job_type": "map_keys",
                        "path": current_path,
                        "items": [(normalize_whitespace(map_key), map_value) for map_key, map_value in value.items()],
                    }
                )
                continue

            if key in MAP_VALUE_TRANSLATION_KEYS and is_string_map(value):
                string_items = [
                    (map_key, normalize_whitespace(map_value))
                    for map_key, map_value in value.items()
                    if is_scalar_string(map_value)
                ]
                if string_items:
                    jobs.append(
                        {
                            "job_type": "map_values",
                            "path": current_path,
                            "items": string_items,
                        }
                    )
                    continue

            jobs.extend(collect_translation_jobs(value, current_path))
        return jobs

    if isinstance(node, list):
        for index, item in enumerate(node):
            jobs.extend(collect_translation_jobs(item, path + (index,)))
    return jobs


def collect_unique_texts(jobs: Iterable[Dict[str, Any]]) -> List[str]:
    seen: Dict[str, None] = {}
    for job in jobs:
        if job["job_type"] == "scalar":
            seen.setdefault(job["text"], None)
        elif job["job_type"] == "list":
            for text in job["texts"]:
                seen.setdefault(text, None)
        else:
            for item in job["items"]:
                if job["job_type"] == "map_keys":
                    seen.setdefault(item[0], None)
                elif job["job_type"] == "map_values":
                    seen.setdefault(item[1], None)
    return list(seen.keys())


def build_batches(texts: Sequence[str], max_items: int, max_chars: int) -> List[List[str]]:
    batches: List[List[str]] = []
    current: List[str] = []
    current_chars = 0

    for text in texts:
        text_len = len(text)
        if current and (len(current) >= max_items or current_chars + text_len > max_chars):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(text)
        current_chars += text_len

    if current:
        batches.append(current)
    return batches


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
                        f"API call succeeded with configured key {key_index}/{total_keys} "
                        f"({mask_api_key(api_key)}) on pass {attempt}."
                    )
                return response.json()
            except requests.RequestException as exc:
                last_error = exc
                if key_index < total_keys:
                    log(
                        f"API call failed with configured key {key_index}/{total_keys} "
                        f"({mask_api_key(api_key)}); trying next key: {exc}"
                    )
                else:
                    log(
                        f"API call failed on pass {attempt}/3 with configured key {key_index}/{total_keys} "
                        f"({mask_api_key(api_key)}): {exc}"
                    )
        if attempt == 3:
            break
        sleep_seconds = min(5 * attempt, 15)
        log(f"Exhausted {total_keys} configured API keys on pass {attempt}/3, retrying in {sleep_seconds}s.")
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


def translate_batch(
    session: requests.Session,
    args: argparse.Namespace,
    batch: Sequence[str],
) -> Dict[str, str]:
    items = [{"id": str(index), "text": text} for index, text in enumerate(batch)]
    user_prompt = (
        "Translate the following JSON array values into Simplified Chinese.\n"
        "Return JSON only with schema {\"translations\": [{\"id\": \"...\", \"text\": \"...\"}]}.\n"
        "Input:\n"
        f"{json.dumps(items, ensure_ascii=False, indent=2)}"
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
    payload = extract_json_object(extract_message_text(response_json))
    translations = payload.get("translations")
    if not isinstance(translations, list):
        raise ValueError("Translation response is missing a translations list.")

    translated_by_id: Dict[str, str] = {}
    for item in translations:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id", ""))
        text = normalize_whitespace(item.get("text", ""))
        if item_id:
            translated_by_id[item_id] = text

    missing = [str(index) for index in range(len(batch)) if str(index) not in translated_by_id]
    if missing:
        raise ValueError(f"Translation response missing ids: {', '.join(missing)}")

    return {source: translated_by_id[str(index)] for index, source in enumerate(batch)}


def resolve_translations(
    texts: Sequence[str],
    cache: Dict[str, Dict[str, str]],
    session: requests.Session,
    args: argparse.Namespace,
) -> Tuple[Dict[str, str], int]:
    resolved: Dict[str, str] = {}
    pending: List[str] = []

    for text in texts:
        digest = text_digest(text)
        cached = cache.get(digest)
        if cached and cached.get("source") == text and is_scalar_string(cached.get("translation", "")):
            resolved[text] = cached["translation"]
        else:
            pending.append(text)

    if not pending:
        return resolved, 0

    batches = build_batches(pending, max_items=args.batch_size, max_chars=args.max_batch_chars)
    log(f"Need {len(pending)} new translations across {len(batches)} batch(es).")
    translated_count = 0

    for batch_index, batch in enumerate(batches, start=1):
        log(f"Translating batch {batch_index}/{len(batches)} with {len(batch)} strings.")
        translated_batch = translate_batch(session=session, args=args, batch=batch)
        for source, translated in translated_batch.items():
            resolved[source] = translated
            cache[text_digest(source)] = {
                "source": source,
                "translation": translated,
            }
            translated_count += 1

    return resolved, translated_count


def apply_translations(
    source_data: Dict[str, Any],
    jobs: Sequence[Dict[str, Any]],
    translations: Dict[str, str],
    model: str,
    source_input: str,
) -> Dict[str, Any]:
    translated = copy.deepcopy(source_data)

    for job in jobs:
        path = job["path"]
        key = path[-1]
        parent = get_at_path(translated, path[:-1])
        zh_key = f"{key}_zh"

        if job["job_type"] == "scalar":
            parent[zh_key] = translations[job["text"]]
            continue

        if job["job_type"] == "list":
            parent[zh_key] = [translations[text] for text in job["texts"]]
            continue

        if job["job_type"] == "map_keys":
            parent[zh_key] = {
                translations[source_key]: value
                for source_key, value in job["items"]
            }
            continue

        if job["job_type"] == "map_values":
            parent[zh_key] = {
                original_key: translations[source_value]
                for original_key, source_value in job["items"]
            }
            continue

    translated["translation_meta"] = {
        "target_language": "zh-CN",
        "mode": "bilingual_fields",
        "generated_at": utc_now(),
        "source_input": source_input,
        "model": model,
        "translated_field_suffix": "_zh",
    }
    return translated


def main() -> None:
    args = parse_args()
    resolve_runtime_settings(args)

    source_path = Path(args.input)
    output_path = Path(args.output)
    cache_path = Path(args.cache)

    source_data = read_json(source_path)
    jobs = collect_translation_jobs(source_data)
    unique_texts = collect_unique_texts(jobs)

    log(f"Collected {len(jobs)} translation job(s), {len(unique_texts)} unique string(s).")
    if args.dry_run:
        return

    ensure_api_args(args)
    cache = load_translation_cache(cache_path)
    session = requests.Session()
    translations, translated_count = resolve_translations(
        texts=unique_texts,
        cache=cache,
        session=session,
        args=args,
    )
    save_translation_cache(cache_path, cache)

    translated_data = apply_translations(
        source_data=source_data,
        jobs=jobs,
        translations=translations,
        model=args.model,
        source_input=str(source_path),
    )
    write_json_atomic(output_path, translated_data)

    log(f"Wrote translated review file to {output_path}.")
    log(f"Reused {len(unique_texts) - translated_count} cached translations; added {translated_count} new ones.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit("Interrupted by user.")
