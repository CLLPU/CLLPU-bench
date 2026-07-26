#!/usr/bin/env python3
"""Repair alias-only failures in a target-language Step 6 failed queue."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import requests

import step6_expand_qa_translations as step6


ALIAS_REPAIR_PROMPT_VERSION = "temp_alias_repair_v1"

ALIAS_REPAIR_SYSTEM_PROMPT = """You translate English answer aliases into one target language.

Return JSON only.
Translate aliases only. Do not rewrite the question or expected answer.
Every returned alias must be strictly equivalent to the expected answer.
Do not include the topic/entity/event/model/work name unless it is literally a valid answer alias.
If no safe alias should be kept, return an empty list.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/llm_api.env")
    parser.add_argument("--source-en", default="data/qa_variants.en.json")
    parser.add_argument("--failed-input", default="data/qa_variants.zh.failed_backtranslation.json")
    parser.add_argument("--current-zh", default="data/qa_variants.zh.json")
    parser.add_argument("--language", default="zh")
    parser.add_argument(
        "--candidates-input",
        default="",
        help="Optional existing alias repair candidates JSON. If provided, skip API generation and reuse it.",
    )
    parser.add_argument(
        "--output",
        default="data/qa_variants.zh.alias_repair_candidates.json",
        help="Where to write alias repair candidates.",
    )
    parser.add_argument(
        "--updated-zh-output",
        default="",
        help="Optional output path for a zh file with repaired alias-only items merged in.",
    )
    parser.add_argument(
        "--updated-failed-output",
        default="",
        help="Optional output path for the remaining failed queue after removing repaired items.",
    )
    parser.add_argument("--api-base", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-items", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def iter_knowledge_pairs(topic_pairs: Sequence[Dict[str, Any]]) -> Sequence[Dict[str, Any]]:
    for topic_pair in topic_pairs:
        for knowledge_pair in topic_pair.get("knowledge_card_pairs", []):
            yield knowledge_pair


def build_source_indexes(source_data: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[str, List[str]]]:
    source_lookup: Dict[str, Dict[str, Any]] = {}
    pair_lookup: Dict[str, Dict[str, Any]] = {}
    pair_source_order: Dict[str, List[str]] = {}
    for knowledge_pair in iter_knowledge_pairs(source_data.get("topic_pairs", [])):
        pair_id = knowledge_pair["knowledge_pair_id"]
        pair_lookup[pair_id] = knowledge_pair
        ordered_ids: List[str] = []
        for role in ("target", "neighbor"):
            for variant in step6.english_variants(knowledge_pair, role):
                source_lookup[variant["qa_id"]] = variant
                ordered_ids.append(variant["qa_id"])
        pair_source_order[pair_id] = ordered_ids
    return source_lookup, pair_lookup, pair_source_order


def is_alias_failure(record: Dict[str, Any]) -> bool:
    failure_type = step6.normalize_whitespace((record.get("final_consistency") or {}).get("failure_type")).lower()
    return "alias" in failure_type


def latest_translation(record: Dict[str, Any]) -> Dict[str, Any]:
    attempts = record.get("attempt_history")
    if isinstance(attempts, list) and attempts:
        last_attempt = attempts[-1]
        translation = last_attempt.get("translation")
        if isinstance(translation, dict):
            return translation
    return {}


def build_alias_prompt(
    *,
    source_variant: Dict[str, Any],
    current_translation: Dict[str, Any],
    language: str,
) -> str:
    payload = {
        "target_language": step6.language_instruction(language),
        "source_qa_id": source_variant.get("qa_id"),
        "source_question_en": source_variant.get("question"),
        "source_expected_answer_en": source_variant.get("expected_answer"),
        "source_answer_aliases_en": source_variant.get("answer_aliases", []),
        "current_question_target_language": current_translation.get("question"),
        "current_expected_answer_target_language": current_translation.get("expected_answer"),
        "current_answer_aliases_target_language": current_translation.get("answer_aliases", []),
    }
    return f"""Translate only the English answer aliases into the target language.

Rules:
1. Translate source_answer_aliases_en only.
2. Do not rewrite the question.
3. Do not rewrite the expected answer.
4. Every returned alias must remain strictly equivalent to the expected answer.
5. Do not include the subject/topic/entity/event/model/work name unless it is literally a valid answer alias in source_answer_aliases_en.
6. If source_answer_aliases_en is empty, return an empty list.
7. Keep the list short and evaluation-friendly.

Return JSON only with this schema:
{{
  "answer_aliases": ["..."],
  "note": "brief note"
}}

Payload:
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def parse_alias_response(model_output: Dict[str, Any]) -> Tuple[List[str], str]:
    aliases = model_output.get("answer_aliases")
    note = step6.normalize_whitespace(model_output.get("note"))
    if not isinstance(aliases, list):
        return [], note
    return [step6.normalize_whitespace(item) for item in aliases if step6.normalize_whitespace(item)], note


def repair_record(
    *,
    session: requests.Session,
    args: argparse.Namespace,
    record: Dict[str, Any],
    source_variant: Dict[str, Any],
    knowledge_pair: Dict[str, Any],
) -> Dict[str, Any]:
    current_translation = latest_translation(record)
    role = source_variant["topic_role"]
    card = step6.card_for_role(knowledge_pair, role)
    source_aliases = source_variant.get("answer_aliases")
    source_alias_count = len(source_aliases) if isinstance(source_aliases, list) else 0

    generated_aliases: List[str] = []
    note = ""
    if source_alias_count:
        model_output = step6.call_json_model(
            session,
            args,
            ALIAS_REPAIR_SYSTEM_PROMPT,
            build_alias_prompt(
                source_variant=source_variant,
                current_translation=current_translation,
                language=args.language,
            ),
        )
        generated_aliases, note = parse_alias_response(model_output)

    aliases, alias_warnings = step6.safe_translated_answer_aliases(
        generated_aliases,
        source_variant=source_variant,
        card=card,
        expected_answer=step6.normalize_whitespace(current_translation.get("expected_answer")),
    )
    repaired = {
        "qa_id": step6.translated_qa_id(source_variant["qa_id"], args.language),
        "source_qa_id": source_variant["qa_id"],
        "source_language": step6.CANONICAL_LANGUAGE,
        "generation_stage": "alias_repaired_from_canonical_en",
        "translation_status": "accepted",
        "backtranslation_status": "manual_alias_repair_pending_review",
        "knowledge_pair_id": record["knowledge_pair_id"],
        "card_id": record["card_id"],
        "topic_role": record["topic_role"],
        "variant_layer": record["variant_layer"],
        "language": args.language,
        "question": step6.normalize_whitespace(current_translation.get("question")),
        "expected_answer": step6.normalize_whitespace(current_translation.get("expected_answer")),
        "answer_aliases": aliases,
        "relation_type": source_variant.get("relation_type"),
        "source_span": source_variant.get("source_span"),
        "alias_repair_note": note or "translated English source answer_aliases only",
        "alias_repair_warnings": alias_warnings,
        "original_failure_type": (record.get("final_consistency") or {}).get("failure_type"),
        "original_failure_reason": (record.get("final_consistency") or {}).get("reason"),
    }
    return repaired


def build_candidates(
    args: argparse.Namespace,
    source_data: Dict[str, Any],
    failed_data: Dict[str, Any],
) -> Dict[str, Any]:
    source_lookup, pair_lookup, _ = build_source_indexes(source_data)
    candidates: List[Dict[str, Any]] = []
    selected_records = [record for record in failed_data.get("failed_backtranslation", []) if is_alias_failure(record)]
    if args.max_items is not None:
        selected_records = selected_records[: args.max_items]

    if args.dry_run:
        return {
            "prompt_version": ALIAS_REPAIR_PROMPT_VERSION,
            "language": args.language,
            "selected_failed_records": len(selected_records),
            "candidates": [],
        }

    step6.resolve_runtime_settings(args)
    step6.ensure_api_args(args)
    session = requests.Session()
    for record in selected_records:
        source_variant = source_lookup.get(record["source_qa_id"])
        if source_variant is None:
            continue
        knowledge_pair = pair_lookup.get(record["knowledge_pair_id"])
        if knowledge_pair is None:
            continue
        candidates.append(
            repair_record(
                session=session,
                args=args,
                record=record,
                source_variant=source_variant,
                knowledge_pair=knowledge_pair,
            )
        )
    return {
        "prompt_version": ALIAS_REPAIR_PROMPT_VERSION,
        "generated_at": step6.utc_now(),
        "language": args.language,
        "selected_failed_records": len(selected_records),
        "candidates": candidates,
    }


def recalculate_zh_summary(doc: Dict[str, Any], failed_count: int) -> None:
    knowledge_pair_count = 0
    qa_variant_count = 0
    for topic_pair in doc.get("topic_pairs", []):
        pairs = topic_pair.get("knowledge_card_pairs", [])
        knowledge_pair_count += len(pairs)
        for knowledge_pair in pairs:
            qa_variant_count += len(knowledge_pair.get("target_qa_variants", []))
            qa_variant_count += len(knowledge_pair.get("neighbor_qa_variants", []))
    summary = doc.setdefault("summary", {})
    summary["knowledge_pair_count"] = knowledge_pair_count
    summary["qa_variant_count"] = qa_variant_count
    summary["accepted_qa_count"] = qa_variant_count
    summary["failed_backtranslation_count"] = failed_count


def merge_candidates_into_zh(
    *,
    current_zh: Dict[str, Any],
    failed_data: Dict[str, Any],
    candidates: Sequence[Dict[str, Any]],
    pair_source_order: Dict[str, List[str]],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    zh_doc = copy.deepcopy(current_zh)
    failed_doc = copy.deepcopy(failed_data)
    candidate_map = {candidate["source_qa_id"]: candidate for candidate in candidates}

    for topic_pair in zh_doc.get("topic_pairs", []):
        for knowledge_pair in topic_pair.get("knowledge_card_pairs", []):
            pair_id = knowledge_pair.get("knowledge_pair_id")
            order = pair_source_order.get(pair_id, [])
            order_index = {qa_id: idx for idx, qa_id in enumerate(order)}
            for role_key in ("target_qa_variants", "neighbor_qa_variants"):
                variants = list(knowledge_pair.get(role_key, []))
                for source_qa_id, candidate in candidate_map.items():
                    if candidate["knowledge_pair_id"] != pair_id:
                        continue
                    if candidate["topic_role"] == "target" and role_key != "target_qa_variants":
                        continue
                    if candidate["topic_role"] == "neighbor" and role_key != "neighbor_qa_variants":
                        continue
                    if any(item.get("source_qa_id") == source_qa_id for item in variants):
                        continue
                    variants.append(copy.deepcopy(candidate))
                variants.sort(key=lambda item: order_index.get(item.get("source_qa_id", ""), 10**9))
                knowledge_pair[role_key] = variants

    remaining_failed = [
        record
        for record in failed_doc.get("failed_backtranslation", [])
        if record.get("source_qa_id") not in candidate_map
    ]
    failed_doc["failed_backtranslation"] = remaining_failed
    failed_doc.setdefault("summary", {})["failed_backtranslation_count"] = len(remaining_failed)
    recalculate_zh_summary(zh_doc, len(remaining_failed))
    zh_doc["alias_repair_generated_at"] = step6.utc_now()
    failed_doc["alias_repair_generated_at"] = step6.utc_now()
    return zh_doc, failed_doc


def main() -> None:
    args = parse_args()
    source_data = step6.read_json(Path(args.source_en))
    failed_data = step6.read_json(Path(args.failed_input))
    if args.candidates_input:
        candidates_doc = step6.read_json(Path(args.candidates_input))
    else:
        candidates_doc = build_candidates(args, source_data, failed_data)
        step6.write_json_atomic(Path(args.output), candidates_doc)

    if args.updated_zh_output and args.updated_failed_output:
        current_zh = step6.read_json(Path(args.current_zh))
        _, _, pair_source_order = build_source_indexes(source_data)
        zh_doc, failed_doc = merge_candidates_into_zh(
            current_zh=current_zh,
            failed_data=failed_data,
            candidates=candidates_doc.get("candidates", []),
            pair_source_order=pair_source_order,
        )
        step6.write_json_atomic(Path(args.updated_zh_output), zh_doc)
        step6.write_json_atomic(Path(args.updated_failed_output), failed_doc)

    step6.log(
        f"Wrote {args.output} with "
        f"{len(candidates_doc.get('candidates', []))} alias repair candidates."
    )


if __name__ == "__main__":
    main()
