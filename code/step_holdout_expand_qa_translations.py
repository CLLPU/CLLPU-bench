#!/usr/bin/env python3
"""Expand English holdout QA into target languages using Step-6 translation rules."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

import step6_expand_qa_translations as step6


PROMPT_VERSION = f"holdout_{step6.PROMPT_VERSION}"
DEFAULT_LANGUAGES = ["zh", "fr", "es", "de", "ja", "th", "ar", "bn", "sw"]

EXTRA_LANGUAGE_NAMES = {
    "bn": "Bengali",
    "sw": "Swahili",
    "th": "Thai",
}
step6.LANGUAGE_NAMES.update(EXTRA_LANGUAGE_NAMES)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/llm_api.env")
    parser.add_argument("--input", default="data/holdout_qa.en.json")
    parser.add_argument(
        "--output-template",
        default="data/holdout_qa.{language}.json",
        help="Output path template for translated holdout QA files.",
    )
    parser.add_argument(
        "--failed-output-template",
        default="data/holdout_qa.{language}.failed_backtranslation.json",
        help="Failed back-translation queue path template.",
    )
    parser.add_argument("--cache-dir", default="data/holdout_qa_translation_cache")
    parser.add_argument("--language", default="")
    parser.add_argument(
        "--languages",
        default="",
        help="Comma-separated target languages. Defaults to all non-English benchmark languages.",
    )
    parser.add_argument("--api-base", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--refresh-cache", action="store_true")
    parser.set_defaults(enable_backtranslation=True)
    parser.add_argument("--enable-backtranslation", dest="enable_backtranslation", action="store_true")
    parser.add_argument("--skip-backtranslation", dest="enable_backtranslation", action="store_false")
    parser.add_argument("--max-translation-attempts", type=int, default=3)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-cards", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def resolve_languages(args: argparse.Namespace) -> List[str]:
    if args.language and args.languages:
        raise SystemExit("Pass either --language or --languages, not both.")
    if args.language:
        languages = [args.language]
    elif args.languages:
        languages = [item.strip() for item in args.languages.split(",") if item.strip()]
    else:
        languages = list(DEFAULT_LANGUAGES)

    resolved = []
    for language in languages:
        parsed = step6.parse_language_value(language)
        if parsed not in resolved:
            resolved.append(parsed)
    return resolved


def enrich_source_variant(holdout_card: Dict[str, Any], source_variant: Dict[str, Any]) -> Dict[str, Any]:
    card = holdout_card
    variant = copy.deepcopy(source_variant)
    variant["knowledge_pair_id"] = card.get("holdout_card_id")
    variant["card_id"] = card.get("source_card_id")
    variant["topic_role"] = "target"
    variant["relation_type"] = card.get("relation_type")
    return variant


def holdout_to_step6_pair(holdout_card: Dict[str, Any]) -> Dict[str, Any]:
    source_variants = [
        enrich_source_variant(holdout_card, variant)
        for variant in holdout_card.get("qa_variants", [])
        if step6.normalize_whitespace(variant.get("language")).lower() == step6.CANONICAL_LANGUAGE
    ]
    source_card = {
        "card_id": holdout_card.get("source_card_id"),
        "relation_type": holdout_card.get("relation_type"),
        "semantic_slot": holdout_card.get("semantic_slot"),
        "fact_statement": holdout_card.get("fact_statement"),
        "answer": holdout_card.get("answer"),
        "answer_type": holdout_card.get("answer_type"),
        "source_span": holdout_card.get("source_span"),
        "aliases": source_variants[0].get("source_card_aliases", []) if source_variants else [],
    }
    return {
        "knowledge_pair_id": holdout_card.get("holdout_card_id"),
        "pair_id": holdout_card.get("source_pair_id"),
        "topic_type": holdout_card.get("topic_type"),
        "relation_type": holdout_card.get("relation_type"),
        "target": {
            "topic_name": holdout_card.get("topic_name"),
            "topic_type": holdout_card.get("topic_type"),
            "source_page": holdout_card.get("source_page"),
            "source_url": holdout_card.get("source_url"),
            "card": source_card,
        },
        "neighbor": {},
        "target_qa_variants": source_variants,
        "neighbor_qa_variants": [],
    }


def translated_pair_to_holdout_card(
    source_holdout_card: Dict[str, Any],
    translated_pair: Dict[str, Any],
) -> Dict[str, Any]:
    output = {
        key: copy.deepcopy(value)
        for key, value in source_holdout_card.items()
        if key != "qa_variants"
    }
    variants = []
    for variant in translated_pair.get("target_qa_variants", []):
        translated = copy.deepcopy(variant)
        translated["holdout_card_id"] = source_holdout_card.get("holdout_card_id")
        translated["source_card_id"] = source_holdout_card.get("source_card_id")
        variants.append(translated)
    output["qa_variants"] = variants
    return output


def process_holdout_card(
    args: argparse.Namespace,
    language: str,
    cache_dir: Path,
    index: int,
    holdout_card: Dict[str, Any],
) -> Tuple[int, Dict[str, Any], List[str], List[Dict[str, Any]]]:
    session = requests.Session()
    holdout_card_id = holdout_card.get("holdout_card_id")
    log(f"Translating holdout QA for {holdout_card_id} -> {language}")
    pseudo_pair = holdout_to_step6_pair(holdout_card)
    translated_pair, warnings, failed_records = step6.load_or_translate_knowledge_pair(
        session=session,
        args=args,
        knowledge_pair=pseudo_pair,
        language=language,
        cache_dir=cache_dir,
    )
    output_card = translated_pair_to_holdout_card(holdout_card, translated_pair)
    prefixed_warnings = [f"{holdout_card_id}: {warning}" for warning in warnings]
    return index, output_card, prefixed_warnings, failed_records


def translate_language(
    source_data: Dict[str, Any],
    source_file: str,
    args: argparse.Namespace,
    language: str,
) -> Dict[str, Any]:
    cards = list(source_data.get("holdout_cards", []))
    if args.max_cards is not None:
        cards = cards[: args.max_cards]

    cache_dir = Path(args.cache_dir) / language
    warnings: List[str] = []
    failed_records: List[Dict[str, Any]] = []
    card_results: Dict[int, Dict[str, Any]] = {}

    if args.workers == 1:
        for index, holdout_card in enumerate(cards):
            result_index, output_card, card_warnings, card_failures = process_holdout_card(
                args=args,
                language=language,
                cache_dir=cache_dir,
                index=index,
                holdout_card=holdout_card,
            )
            card_results[result_index] = output_card
            warnings.extend(card_warnings)
            failed_records.extend(card_failures)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [
                executor.submit(
                    process_holdout_card,
                    args,
                    language,
                    cache_dir,
                    index,
                    holdout_card,
                )
                for index, holdout_card in enumerate(cards)
            ]
            for future in as_completed(futures):
                result_index, output_card, card_warnings, card_failures = future.result()
                card_results[result_index] = output_card
                warnings.extend(card_warnings)
                failed_records.extend(card_failures)

    holdout_cards = [card_results[index] for index in sorted(card_results)]
    qa_variant_count = sum(len(card.get("qa_variants", [])) for card in holdout_cards)
    repair_attempt_count = sum(max(0, int(record.get("translation_attempts") or 0) - 1) for record in failed_records)
    return {
        "step": "holdout_qa_translation",
        "prompt_version": PROMPT_VERSION,
        "source_step6_prompt_version": step6.PROMPT_VERSION,
        "generated_at": step6.utc_now(),
        "source_file": source_file,
        "source_step": source_data.get("step"),
        "source_generated_at": source_data.get("generated_at"),
        "model": args.model,
        "api_base": step6.normalize_api_base(args.api_base),
        "translation_config": {
            "source_language": step6.CANONICAL_LANGUAGE,
            "target_language": language,
            "generation_stage": "translated_from_canonical_en",
            "backtranslation_enabled": args.enable_backtranslation,
            "max_translation_attempts": args.max_translation_attempts,
        },
        "summary": {
            "holdout_card_count": len(holdout_cards),
            "qa_variant_count": qa_variant_count,
            "accepted_qa_count": qa_variant_count,
            "failed_backtranslation_count": len(failed_records),
            "repair_attempt_count": repair_attempt_count,
            "warning_count": len(warnings),
        },
        "warnings": warnings,
        "failed_backtranslation": failed_records,
        "holdout_cards": holdout_cards,
    }


def build_failed_output_document(
    source_data: Dict[str, Any],
    source_file: str,
    args: argparse.Namespace,
    language: str,
    failed_records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "step": "holdout_qa_failed_backtranslation_queue",
        "prompt_version": PROMPT_VERSION,
        "source_step6_prompt_version": step6.PROMPT_VERSION,
        "generated_at": step6.utc_now(),
        "source_file": source_file,
        "source_step": source_data.get("step"),
        "source_generated_at": source_data.get("generated_at"),
        "model": args.model,
        "api_base": step6.normalize_api_base(args.api_base),
        "translation_config": {
            "source_language": step6.CANONICAL_LANGUAGE,
            "target_language": language,
            "generation_stage": "translated_from_canonical_en",
        },
        "summary": {
            "failed_backtranslation_count": len(failed_records),
        },
        "failed_backtranslation": failed_records,
    }


def main() -> None:
    args = parse_args()
    if args.max_translation_attempts < 1:
        raise SystemExit("--max-translation-attempts must be at least 1.")
    if args.workers < 1:
        raise SystemExit("--workers must be at least 1.")

    languages = resolve_languages(args)
    step6.resolve_runtime_settings(args)
    if not args.dry_run:
        step6.ensure_api_args(args)
        args.api_key_scheduler = step6.RoundRobinKeyScheduler()
    else:
        args.api_key_scheduler = None

    input_path = Path(args.input)
    source_data = step6.read_json(input_path)
    selected_count = len(source_data.get("holdout_cards", []))
    if args.max_cards is not None:
        selected_count = min(selected_count, args.max_cards)

    if args.dry_run:
        log(f"Selected holdout cards: {selected_count}")
        log(f"Selected English canonical QA: {selected_count}")
        log(f"Target languages: {', '.join(languages)}")
        log(f"Expected translated QA variants per language: {selected_count}")
        log(f"Back-translation enabled: {args.enable_backtranslation}")
        log(f"Max translation attempts per QA: {args.max_translation_attempts}")
        log(f"Workers: {args.workers}")
        log(f"Configured API keys: {len(args.api_keys)}")
        log("English canonical holdout QA remain in the source file.")
        return

    for language in languages:
        output_path = Path(args.output_template.format(language=language))
        failed_output_path = Path(args.failed_output_template.format(language=language))
        output_doc = translate_language(
            source_data=source_data,
            source_file=str(input_path),
            args=args,
            language=language,
        )
        step6.write_json_atomic(output_path, output_doc)
        if args.enable_backtranslation:
            failed_doc = build_failed_output_document(
                source_data=source_data,
                source_file=str(input_path),
                args=args,
                language=language,
                failed_records=output_doc.get("failed_backtranslation", []),
            )
            step6.write_json_atomic(failed_output_path, failed_doc)
        log(
            f"Wrote {output_path} with "
            f"{output_doc['summary']['qa_variant_count']} {language} QA variants, "
            f"{output_doc['summary']['failed_backtranslation_count']} failed back-translations, "
            f"and {output_doc['summary']['warning_count']} warnings."
        )


if __name__ == "__main__":
    main()
