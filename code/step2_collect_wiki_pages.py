#!/usr/bin/env python3
"""Collect Step-2 Wikipedia page content from a topic-pair manifest."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_INPUT = "data/wiki_page_manifest.json"
DEFAULT_OUTPUT = "data/wiki_page_content.json"
DEFAULT_USER_AGENT = "multilingual-unlearning-benchmark-step2/1.0 (https://openai.com)"
WORD_PATTERN = re.compile(r"[A-Za-z0-9]+(?:[’'-][A-Za-z0-9]+)*")


class ManifestError(ValueError):
    """Raised when the Step-1 manifest is malformed."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
        help="Step-1 manifest JSON path.",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Step-2 output JSON path.",
    )
    parser.add_argument(
        "--pair-id",
        action="append",
        dest="pair_ids",
        help="Only process the specified pair_id. Can be passed multiple times.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N topic pairs after filtering.",
    )
    parser.add_argument(
        "--language",
        default="",
        help="Override Wikipedia language code. Defaults to source_language in the manifest or 'en'.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.1,
        help="Sleep time between completed topic pairs.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum retries for each page request.",
    )
    parser.add_argument(
        "--user-agent",
        default=DEFAULT_USER_AGENT,
        help="User-Agent sent to Wikipedia API.",
    )
    return parser.parse_args()


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ManifestError(f"{path} must contain a JSON object.")
    return data


def require_str(container: Dict[str, Any], key: str, context: str) -> str:
    value = container.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"Missing non-empty string '{key}' in {context}.")
    return value.strip()


def validate_role(topic_obj: Dict[str, Any], expected_role: str, context: str) -> None:
    role = require_str(topic_obj, "role", context)
    if role != expected_role:
        raise ManifestError(f"{context}.role must be '{expected_role}', got '{role}'.")


def validate_manifest(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    topic_pairs = manifest.get("topic_pairs")
    if not isinstance(topic_pairs, list) or not topic_pairs:
        raise ManifestError("Manifest must contain a non-empty 'topic_pairs' list.")

    validated: List[Dict[str, Any]] = []
    for idx, pair in enumerate(topic_pairs):
        context = f"topic_pairs[{idx}]"
        if not isinstance(pair, dict):
            raise ManifestError(f"{context} must be an object.")

        require_str(pair, "pair_id", context)
        require_str(pair, "topic_type", context)

        target = pair.get("target")
        neighbor = pair.get("neighbor")
        if not isinstance(target, dict):
            raise ManifestError(f"{context}.target must be an object.")
        if not isinstance(neighbor, dict):
            raise ManifestError(f"{context}.neighbor must be an object.")

        validate_role(target, "target", f"{context}.target")
        validate_role(neighbor, "neighbor", f"{context}.neighbor")

        for side_name, side_obj in (("target", target), ("neighbor", neighbor)):
            side_context = f"{context}.{side_name}"
            require_str(side_obj, "topic_zh", side_context)
            require_str(side_obj, "topic_en", side_context)
            require_str(side_obj, "wiki_title", side_context)
            require_str(side_obj, "wiki_url", side_context)

        validated.append(pair)

    return validated


def filter_pairs(
    topic_pairs: Iterable[Dict[str, Any]],
    pair_ids: Optional[List[str]],
    limit: Optional[int],
) -> List[Dict[str, Any]]:
    filtered = list(topic_pairs)
    if pair_ids:
        allow = set(pair_ids)
        filtered = [pair for pair in filtered if pair["pair_id"] in allow]
    if limit is not None:
        filtered = filtered[:limit]
    if not filtered:
        raise ManifestError("No topic pairs remain after applying filters.")
    return filtered


def build_api_url(language: str, title: str) -> str:
    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": "1",
        "redirects": "1",
        "format": "json",
        "titles": title,
    }
    query = urllib.parse.urlencode(params)
    return f"https://{language}.wikipedia.org/w/api.php?{query}"


def count_words(text: str) -> int:
    """Count English word-like tokens in Wikipedia plaintext extracts."""
    return len(WORD_PATTERN.findall(text))


def fetch_page_extract(
    title: str,
    language: str,
    user_agent: str,
    timeout: float,
    max_retries: int,
) -> Dict[str, Any]:
    url = build_api_url(language, title)
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/json",
    }

    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read().decode("utf-8")
            data = json.loads(payload)
            pages = data.get("query", {}).get("pages", {})
            if not isinstance(pages, dict) or not pages:
                raise RuntimeError(f"No pages returned for title '{title}'.")

            page = next(iter(pages.values()))
            if not isinstance(page, dict):
                raise RuntimeError(f"Malformed page payload for title '{title}'.")

            extract = page.get("extract")
            resolved_title = page.get("title")
            page_id = page.get("pageid")
            if not isinstance(extract, str) or not extract.strip():
                raise RuntimeError(f"Empty extract returned for title '{title}'.")
            if not isinstance(resolved_title, str) or not resolved_title.strip():
                raise RuntimeError(f"Missing resolved title for '{title}'.")
            if not isinstance(page_id, int):
                raise RuntimeError(f"Missing pageid for '{title}'.")

            return {
                "wiki_title": resolved_title.strip(),
                "page_id": page_id,
                "page_content": extract,
                "word_count": count_words(extract),
            }
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            RuntimeError,
        ) as exc:
            last_error = exc
            if attempt == max_retries:
                break
            time.sleep(min(2.0 * attempt, 5.0))

    raise RuntimeError(f"Failed to fetch '{title}' after {max_retries} attempts: {last_error}")


def build_output(
    manifest: Dict[str, Any],
    topic_pairs: List[Dict[str, Any]],
    language: str,
    user_agent: str,
    timeout: float,
    max_retries: int,
    sleep_seconds: float,
    input_path: Path,
) -> Dict[str, Any]:
    output: Dict[str, Any] = {
        "step": "step_2_collect_wiki_pages",
        "generated_on": datetime.now().date().isoformat(),
        "content_format": "wikipedia_extract_plaintext",
        "source_language": language,
        "source_site": manifest.get("source_site", "Wikipedia"),
        "based_on_manifest": str(input_path),
        "topic_pairs": [],
    }

    for index, pair in enumerate(topic_pairs):
        target = pair["target"]
        neighbor = pair["neighbor"]

        target_page = fetch_page_extract(
            target["wiki_title"], language, user_agent, timeout, max_retries
        )
        neighbor_page = fetch_page_extract(
            neighbor["wiki_title"], language, user_agent, timeout, max_retries
        )

        output["topic_pairs"].append(
            {
                "pair_id": pair["pair_id"],
                "topic_type": pair["topic_type"],
                "target": {
                    "role": target["role"],
                    "topic_zh": target["topic_zh"],
                    "topic_en": target["topic_en"],
                    "wiki_title": target_page["wiki_title"],
                    "wiki_url": target["wiki_url"],
                    "page_id": target_page["page_id"],
                    "page_content": target_page["page_content"],
                    "word_count": target_page["word_count"],
                },
                "neighbor": {
                    "role": neighbor["role"],
                    "topic_zh": neighbor["topic_zh"],
                    "topic_en": neighbor["topic_en"],
                    "wiki_title": neighbor_page["wiki_title"],
                    "wiki_url": neighbor["wiki_url"],
                    "page_id": neighbor_page["page_id"],
                    "page_content": neighbor_page["page_content"],
                    "word_count": neighbor_page["word_count"],
                },
            }
        )

        if sleep_seconds > 0 and index < len(topic_pairs) - 1:
            time.sleep(sleep_seconds)

    return output


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
        temp_name = tmp.name
    Path(temp_name).replace(path)


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    manifest = load_json(input_path)
    topic_pairs = validate_manifest(manifest)
    topic_pairs = filter_pairs(topic_pairs, args.pair_ids, args.limit)

    language = args.language.strip() or manifest.get("source_language") or "en"
    if not isinstance(language, str) or not language.strip():
        raise ManifestError("Unable to determine Wikipedia language code.")
    language = language.strip()

    output = build_output(
        manifest=manifest,
        topic_pairs=topic_pairs,
        language=language,
        user_agent=args.user_agent,
        timeout=args.timeout,
        max_retries=args.max_retries,
        sleep_seconds=args.sleep_seconds,
        input_path=input_path,
    )
    atomic_write_json(output_path, output)
    print(f"Wrote {output_path} with {len(output['topic_pairs'])} topic pairs.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ManifestError as exc:
        print(f"ManifestError: {exc}", file=sys.stderr)
        raise SystemExit(1)
