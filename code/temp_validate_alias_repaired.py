#!/usr/bin/env python3
"""Validate alias-repaired target-language QA entries via back-translation only."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import requests

import step6_expand_qa_translations as step6


VALIDATION_PROMPT_VERSION = "temp_alias_repair_validation_v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/llm_api.env")
    parser.add_argument("--source-en", default="data/qa_variants.en.json")
    parser.add_argument("--repaired-zh", default="data/qa_variants.zh.alias_repaired.json")
    parser.add_argument("--candidates-input", default="data/qa_variants.zh.alias_repair_candidates.json")
    parser.add_argument(
        "--output",
        default="data/qa_variants.zh.alias_repaired.validation.json",
        help="Validation summary output for repaired alias entries.",
    )
    parser.add_argument("--language", default="zh")
    parser.add_argument("--api-base", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--checkpoint-every", type=int, default=25)
    parser.add_argument("--max-items", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def iter_knowledge_pairs(topic_pairs: Sequence[Dict[str, Any]]) -> Sequence[Dict[str, Any]]:
    for topic_pair in topic_pairs:
        for knowledge_pair in topic_pair.get("knowledge_card_pairs", []):
            yield knowledge_pair


def build_source_indexes(source_data: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    source_lookup: Dict[str, Dict[str, Any]] = {}
    pair_lookup: Dict[str, Dict[str, Any]] = {}
    for knowledge_pair in iter_knowledge_pairs(source_data.get("topic_pairs", [])):
        pair_lookup[knowledge_pair["knowledge_pair_id"]] = knowledge_pair
        for role in ("target", "neighbor"):
            for variant in step6.english_variants(knowledge_pair, role):
                source_lookup[variant["qa_id"]] = variant
    return source_lookup, pair_lookup


def build_repaired_lookup(repaired_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for knowledge_pair in iter_knowledge_pairs(repaired_data.get("topic_pairs", [])):
        for role_key in ("target_qa_variants", "neighbor_qa_variants"):
            for variant in knowledge_pair.get(role_key, []):
                source_qa_id = step6.normalize_whitespace(variant.get("source_qa_id"))
                if source_qa_id:
                    lookup[source_qa_id] = variant
    return lookup


def validate_one(
    *,
    args: argparse.Namespace,
    source_variant: Dict[str, Any],
    repaired_variant: Dict[str, Any],
    knowledge_pair: Dict[str, Any],
) -> Dict[str, Any]:
    source_qa_id = source_variant["qa_id"]
    session = requests.Session()
    backtranslation_output = step6.call_json_model(
        session,
        args,
        step6.SYSTEM_PROMPT,
        step6.build_backtranslation_prompt(repaired_variant, args.language),
    )
    backtranslation = step6.parse_backtranslation_object(backtranslation_output, source_qa_id)
    consistency_output = step6.call_json_model(
        session,
        args,
        step6.SYSTEM_PROMPT,
        step6.build_consistency_prompt(knowledge_pair, source_variant, repaired_variant, backtranslation),
    )
    consistency = step6.parse_consistency_object(consistency_output)
    return {
        "source_qa_id": source_qa_id,
        "knowledge_pair_id": source_variant.get("knowledge_pair_id"),
        "topic_role": source_variant.get("topic_role"),
        "variant_layer": source_variant.get("variant_layer"),
        "question": repaired_variant.get("question"),
        "expected_answer": repaired_variant.get("expected_answer"),
        "answer_aliases": repaired_variant.get("answer_aliases", []),
        "backtranslation_en": backtranslation,
        "consistency": consistency,
    }


def write_checkpoint(
    *,
    output_path: Path,
    args: argparse.Namespace,
    selected_items: int,
    results: Sequence[Dict[str, Any]],
    errors: Sequence[Dict[str, Any]],
) -> None:
    passed = sum(1 for item in results if item.get("consistency", {}).get("is_consistent"))
    failed = sum(1 for item in results if not item.get("consistency", {}).get("is_consistent"))
    payload = {
        "prompt_version": VALIDATION_PROMPT_VERSION,
        "generated_at": step6.utc_now(),
        "language": args.language,
        "summary": {
            "selected_items": selected_items,
            "validated_items": len(results),
            "passed_count": passed,
            "failed_count": failed,
            "error_count": len(errors),
        },
        "results": list(results),
        "errors": list(errors),
    }
    step6.write_json_atomic(output_path, payload)


def main() -> None:
    args = parse_args()
    source_data = step6.read_json(Path(args.source_en))
    repaired_data = step6.read_json(Path(args.repaired_zh))
    candidates_data = step6.read_json(Path(args.candidates_input))

    source_lookup, pair_lookup = build_source_indexes(source_data)
    repaired_lookup = build_repaired_lookup(repaired_data)
    selected_ids = [
        step6.normalize_whitespace(item.get("source_qa_id"))
        for item in candidates_data.get("candidates", [])
        if step6.normalize_whitespace(item.get("source_qa_id"))
    ]
    if args.max_items is not None:
        selected_ids = selected_ids[: args.max_items]

    if args.dry_run:
        step6.write_json_atomic(
            Path(args.output),
            {
                "prompt_version": VALIDATION_PROMPT_VERSION,
                "language": args.language,
                "selected_items": len(selected_ids),
            },
        )
        return

    step6.resolve_runtime_settings(args)
    step6.ensure_api_args(args)
    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    work_items = []
    for source_qa_id in selected_ids:
        source_variant = source_lookup.get(source_qa_id)
        repaired_variant = repaired_lookup.get(source_qa_id)
        if source_variant is None or repaired_variant is None:
            errors.append(
                {
                    "source_qa_id": source_qa_id,
                    "error": "missing source or repaired variant",
                }
            )
            continue
        knowledge_pair = pair_lookup.get(source_variant["knowledge_pair_id"])
        if knowledge_pair is None:
            errors.append(
                {
                    "source_qa_id": source_qa_id,
                    "error": "missing knowledge pair",
                }
            )
            continue
        work_items.append((source_qa_id, source_variant, repaired_variant, knowledge_pair))

    output_path = Path(args.output)
    completed = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(
                validate_one,
                args=args,
                source_variant=source_variant,
                repaired_variant=repaired_variant,
                knowledge_pair=knowledge_pair,
            ): (source_qa_id, source_variant.get("knowledge_pair_id"))
            for source_qa_id, source_variant, repaired_variant, knowledge_pair in work_items
        }
        for future in as_completed(futures):
            source_qa_id, knowledge_pair_id = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    {
                        "source_qa_id": source_qa_id,
                        "knowledge_pair_id": knowledge_pair_id,
                        "error": str(exc),
                    }
                )
            completed += 1
            if completed % max(1, args.checkpoint_every) == 0:
                write_checkpoint(
                    output_path=output_path,
                    args=args,
                    selected_items=len(selected_ids),
                    results=results,
                    errors=errors,
                )

    write_checkpoint(
        output_path=output_path,
        args=args,
        selected_items=len(selected_ids),
        results=results,
        errors=errors,
    )
    passed = sum(1 for item in results if item.get("consistency", {}).get("is_consistent"))
    failed = sum(1 for item in results if not item.get("consistency", {}).get("is_consistent"))
    step6.log(f"Wrote {args.output} with {passed} passed, {failed} failed, and {len(errors)} errors.")


if __name__ == "__main__":
    main()
