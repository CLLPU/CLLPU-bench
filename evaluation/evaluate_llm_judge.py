#!/usr/bin/env python3
"""Evaluate answer correctness with an OpenAI-compatible LLM judge."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from _common import add_common_arguments, aggregate_and_write, read_records


SYSTEM_PROMPT = """You are a strict multilingual factual-answer evaluator.
Decide whether the candidate answer correctly answers the question according to
the expected answer and accepted aliases. Ignore harmless formatting and wording
differences. Do not reward related but factually different answers.
Return JSON only: {"correct": true} or {"correct": false}."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_arguments(parser, "llm_judge")
    parser.add_argument(
        "--api-base",
        default=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )
    parser.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY", ""))
    parser.add_argument(
        "--model",
        default=os.getenv("CLLPU_JUDGE_MODEL", ""),
        help="Judge model ID. Required.",
    )
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path("evaluation/outputs/llm_judge/cache.jsonl"),
    )
    return parser.parse_args()


def cache_key(record: dict[str, Any], model: str, use_aliases: bool) -> str:
    payload = json.dumps(
        {
            "model": model,
            "question": record["question"],
            "prediction": record["prediction"],
            "expected_answer": record["expected_answer"],
            "answer_aliases": record["answer_aliases"] if use_aliases else [],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_cache(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    cache: dict[str, float] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                cache[row["key"]] = float(row["score"])
    return cache


def parse_judgment(content: str) -> float:
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lstrip().startswith("json"):
            content = content.lstrip()[4:].lstrip()
    payload = json.loads(content)
    correct = payload.get("correct")
    if not isinstance(correct, bool):
        raise ValueError(f"Judge response lacks boolean correct: {content!r}")
    return float(correct)


def judge(
    session: requests.Session,
    record: dict[str, Any],
    args: argparse.Namespace,
) -> float:
    user_payload = {
        "question": record["question"],
        "candidate_answer": record["prediction"],
        "expected_answer": record["expected_answer"],
        "accepted_aliases": record["answer_aliases"] if args.use_aliases else [],
    }
    request_payload = {
        "model": args.model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(user_payload, ensure_ascii=False),
            },
        ],
        "response_format": {"type": "json_object"},
    }
    endpoint = args.api_base.rstrip("/") + "/chat/completions"
    last_error: Exception | None = None
    for attempt in range(args.max_retries):
        try:
            response = session.post(endpoint, json=request_payload, timeout=args.timeout)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return parse_judgment(content)
        except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
            last_error = exc
            if attempt + 1 < args.max_retries:
                time.sleep(2**attempt)
    raise RuntimeError(f"Judge failed after {args.max_retries} attempts") from last_error


def main() -> None:
    args = parse_args()
    global requests
    try:
        import requests
    except ImportError as exc:
        raise SystemExit(
            "requests is required: python -m pip install requests"
        ) from exc
    if not args.model:
        raise SystemExit("--model or CLLPU_JUDGE_MODEL is required")
    if not args.api_key:
        raise SystemExit("--api-key or OPENAI_API_KEY is required")

    records = read_records(args.input)
    cache = load_cache(args.cache)
    args.cache.parent.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {args.api_key}",
            "Content-Type": "application/json",
        }
    )

    scores: list[float] = []
    with args.cache.open("a", encoding="utf-8") as cache_handle:
        for index, record in enumerate(records, 1):
            key = cache_key(record, args.model, args.use_aliases)
            if key not in cache:
                cache[key] = judge(session, record, args)
                cache_handle.write(
                    json.dumps(
                        {
                            "key": key,
                            "qa_id": record["qa_id"],
                            "model": args.model,
                            "score": cache[key],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                cache_handle.flush()
            scores.append(cache[key])
            if index % 100 == 0:
                print(f"Judged {index}/{len(records)}")

    aggregate_and_write(
        records,
        scores,
        "llm_judge",
        args.output_dir,
        args.languages,
        args.allow_incomplete,
    )
    print(f"Wrote llm_judge numeric results for {len(records)} QAs to {args.output_dir}")


if __name__ == "__main__":
    main()
