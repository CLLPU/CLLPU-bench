#!/usr/bin/env python3
"""Sample unused knowledge cards and generate English holdout QA."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests

from step5_generate_qa_variants import (
    SYSTEM_PROMPT,
    answer_alias_equivalent,
    answer_leakage_warnings,
    call_chat_completion,
    ensure_api_args,
    normalize_api_base,
    normalize_whitespace,
    parse_model_json_response,
    read_json,
    resolve_runtime_settings,
    safe_answer_aliases,
    slugify,
    source_card_aliases,
    utc_now,
    write_json_atomic,
)


PROMPT_VERSION = "holdout_en_canonical_v1"
DEFAULT_RANDOM_SEED = 20260627


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/llm_api.env")
    parser.add_argument("--cards-input", default="data/knowledge_cards.json")
    parser.add_argument("--selected-input", default="data/selected_knowledge_card_pairs.json")
    parser.add_argument("--sample-output", default="data/holdout_knowledge_cards.sampled.json")
    parser.add_argument("--output", default="data/holdout_qa.en.json")
    parser.add_argument("--cache-dir", default="data/holdout_qa_cache")
    parser.add_argument("--sample-size", type=int, default=500)
    parser.add_argument("--random-seed", type=int, default=DEFAULT_RANDOM_SEED)
    parser.add_argument("--holdout-id-prefix", default="holdout")
    parser.add_argument("--surface-count", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--api-base", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--refresh-sample", action="store_true")
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--refresh-normalized-cache", action="store_true")
    parser.add_argument("--sample-only", action="store_true")
    parser.add_argument("--generate-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-cards", type=int, default=None)
    return parser.parse_args()


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def valid_card(card: Dict[str, Any]) -> bool:
    required = ["card_id", "relation_type", "fact_statement", "answer", "source_span"]
    return all(normalize_whitespace(card.get(key)) for key in required)


def iter_all_cards(source_data: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    for topic_pair in source_data.get("topic_pairs", []):
        pair_id = topic_pair.get("pair_id")
        topic_type = topic_pair.get("topic_type")
        for role in ("target", "neighbor"):
            topic = topic_pair.get(role) or {}
            for card in topic.get("knowledge_cards", []):
                if not isinstance(card, dict) or not valid_card(card):
                    continue
                yield {
                    "source_pair_id": pair_id,
                    "source_topic_role": role,
                    "topic_name": topic.get("topic_name"),
                    "topic_type": topic.get("topic_type") or topic_type,
                    "source_page": topic.get("source_page"),
                    "source_url": topic.get("source_url"),
                    "card": copy.deepcopy(card),
                }


def selected_card_ids(selected_data: Dict[str, Any]) -> set:
    used = set()
    for topic_pair in selected_data.get("topic_pairs", []):
        for knowledge_pair in topic_pair.get("knowledge_card_pairs", []):
            for role in ("target", "neighbor"):
                card_id = (
                    (knowledge_pair.get(role) or {})
                    .get("card", {})
                    .get("card_id")
                )
                if card_id:
                    used.add(card_id)
    return used


def build_sample_document(args: argparse.Namespace) -> Dict[str, Any]:
    cards_path = Path(args.cards_input)
    selected_path = Path(args.selected_input)
    source_data = read_json(cards_path)
    selected_data = read_json(selected_path)
    used_ids = selected_card_ids(selected_data)

    all_cards = list(iter_all_cards(source_data))
    unique_cards: Dict[str, Dict[str, Any]] = {}
    for item in all_cards:
        card_id = item["card"].get("card_id")
        if card_id and card_id not in unique_cards:
            unique_cards[card_id] = item

    candidates = [
        item
        for card_id, item in unique_cards.items()
        if card_id not in used_ids
    ]
    if len(candidates) < args.sample_size:
        raise SystemExit(
            f"Need {args.sample_size} holdout cards, but only {len(candidates)} candidates are available."
        )

    rng = random.Random(args.random_seed)
    sampled = rng.sample(candidates, args.sample_size)
    sampled.sort(key=lambda item: item["card"]["card_id"])

    holdout_cards = []
    for index, item in enumerate(sampled, start=1):
        holdout = copy.deepcopy(item)
        holdout["holdout_card_id"] = f"{slugify(args.holdout_id_prefix)}__{index:06d}"
        holdout_cards.append(holdout)

    return {
        "step": "holdout_card_sampling",
        "generated_at": utc_now(),
        "source_file": str(cards_path),
        "exclusion_file": str(selected_path),
        "source_step": source_data.get("step"),
        "source_generated_at": source_data.get("generated_at"),
        "sampling_config": {
            "sample_size": args.sample_size,
            "random_seed": args.random_seed,
            "exclude_selected_main_qa_cards": True,
            "sampling_unit": "knowledge_card",
            "sampling_strategy": "global_uniform_without_replacement",
        },
        "summary": {
            "total_card_count": len(unique_cards),
            "excluded_selected_card_count": len(used_ids),
            "candidate_card_count": len(candidates),
            "sampled_card_count": len(holdout_cards),
        },
        "holdout_cards": holdout_cards,
    }


def compact_holdout_card(item: Dict[str, Any]) -> Dict[str, Any]:
    card = item.get("card") or {}
    return {
        "holdout_card_id": item.get("holdout_card_id"),
        "source_card_id": card.get("card_id"),
        "topic_name": item.get("topic_name"),
        "topic_type": item.get("topic_type"),
        "source_page": item.get("source_page"),
        "relation_type": card.get("relation_type"),
        "semantic_slot": card.get("semantic_slot"),
        "fact_statement": card.get("fact_statement"),
        "answer": card.get("answer"),
        "answer_type": card.get("answer_type"),
        "source_span": card.get("source_span"),
        "aliases": card.get("aliases") or [],
    }


def build_batch_prompt(cards: Sequence[Dict[str, Any]], surface_count: int) -> str:
    prompt_cards = [compact_holdout_card(item) for item in cards]
    total_per_card = 1 + surface_count
    surface_instruction = (
        "Generate exactly 1 core factual QA and no surface variants for each card."
        if surface_count == 0
        else f"Generate exactly 1 core factual QA and {surface_count} surface variants for each card."
    )
    return f"""Generate English holdout QA probes for the provided knowledge cards.

{surface_instruction}
Each card should have exactly {total_per_card} QA item(s).

Rules:
1. Every QA must ask about the same single fact as its source card.
2. Design each question backward from the card answer. The question must make the answer the only natural short answer.
3. Keep relation_type unchanged.
4. Keep expected_answer equal to the card answer unless the card answer is not English; if so, use the English equivalent and include the card answer as an alias.
5. Do not leak expected_answer or answer aliases inside the question text.
6. Do not mention target, neighbor, holdout, benchmark, source span, or Wikipedia in the question.
7. Do not ask about dates, people, mechanisms, locations, or causes unless that is the provided relation.
8. Write all questions and expected answers in English only.
9. Do not include mixed-language prompts.

Return JSON only with this schema:
{{
  "holdout_cards": [
    {{
      "holdout_card_id": "holdout__000001",
      "qa_variants": [
        {{
          "language": "en",
          "variant_layer": "core",
          "question": "...",
          "expected_answer": "...",
          "answer_aliases": ["..."],
          "rewrite_note": "direct core question"
        }}
      ]
    }}
  ]
}}

Knowledge cards:
{json.dumps(prompt_cards, ensure_ascii=False, indent=2)}
"""


def cache_key_for_batch(cards: Sequence[Dict[str, Any]], surface_count: int) -> str:
    raw = "|".join(item.get("holdout_card_id", "") for item in cards)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    first = cards[0].get("holdout_card_id", "first")
    last = cards[-1].get("holdout_card_id", "last")
    return f"{slugify(first)}__to__{slugify(last)}__surface{surface_count}__{digest}"


def normalize_variant(
    raw: Dict[str, Any],
    *,
    item: Dict[str, Any],
    sequence: int,
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    card = copy.deepcopy(item.get("card") or {})
    card["topic_name"] = item.get("topic_name")
    card["source_page"] = item.get("source_page")

    language = normalize_whitespace(raw.get("language") or "en").lower()
    variant_layer = normalize_whitespace(raw.get("variant_layer")).lower()
    question = normalize_whitespace(raw.get("question"))
    generated_expected_answer = normalize_whitespace(raw.get("expected_answer"))
    card_answer = normalize_whitespace(card.get("answer"))
    expected_answer = card_answer or generated_expected_answer
    rewrite_note = normalize_whitespace(raw.get("rewrite_note"))

    if language != "en":
        return None, [f"invalid language={language!r}"]
    if variant_layer not in {"core", "surface"}:
        return None, [f"invalid variant_layer={variant_layer!r}"]
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
    holdout_card_id = item.get("holdout_card_id")
    variant = {
        "qa_id": f"{holdout_card_id}__en__{suffix}",
        "holdout_card_id": holdout_card_id,
        "source_card_id": card.get("card_id"),
        "variant_layer": variant_layer,
        "language": language,
        "question": question,
        "expected_answer": expected_answer,
        "answer_aliases": aliases,
        "source_card_aliases": source_card_aliases(card),
        "relation_type": card.get("relation_type"),
        "source_span": card.get("source_span"),
    }
    if rewrite_note:
        variant["rewrite_note"] = rewrite_note
    return variant, warnings


def normalize_card_output(
    item: Dict[str, Any],
    raw_variants: Any,
    surface_count: int,
) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    normalized_variants: List[Dict[str, Any]] = []
    if not isinstance(raw_variants, list):
        raw_variants = []
        warnings.append("qa_variants payload is not a list")

    seen_questions = set()
    core_seen = False
    surface_seen = 0
    for index, raw in enumerate(raw_variants, start=1):
        if not isinstance(raw, dict):
            warnings.append(f"{index}: skipped non-object variant")
            continue
        layer = normalize_whitespace(raw.get("variant_layer")).lower()
        if layer == "core":
            if core_seen:
                warnings.append(f"{index}: duplicate core variant skipped")
                continue
            sequence = 0
        elif layer == "surface":
            if surface_seen >= surface_count:
                warnings.append(f"{index}: extra surface variant skipped")
                continue
            sequence = surface_seen + 1
        else:
            sequence = 0

        variant, variant_warnings = normalize_variant(raw, item=item, sequence=sequence)
        warnings.extend(f"{index}: {warning}" for warning in variant_warnings)
        if variant is None:
            continue
        signature = (variant["language"], normalize_whitespace(variant["question"]).lower())
        if signature in seen_questions:
            warnings.append(f"{index}: duplicate question skipped")
            continue
        seen_questions.add(signature)
        normalized_variants.append(variant)
        if variant["variant_layer"] == "core":
            core_seen = True
        elif variant["variant_layer"] == "surface":
            surface_seen += 1

    if not core_seen:
        warnings.append("missing core variant")
    if surface_seen < surface_count:
        warnings.append(f"expected {surface_count} surface variants, got {surface_seen}")

    card = item.get("card") or {}
    output = {
        "holdout_card_id": item.get("holdout_card_id"),
        "source_card_id": card.get("card_id"),
        "source_pair_id": item.get("source_pair_id"),
        "source_topic_role": item.get("source_topic_role"),
        "topic_name": item.get("topic_name"),
        "topic_type": item.get("topic_type"),
        "source_page": item.get("source_page"),
        "source_url": item.get("source_url"),
        "relation_type": card.get("relation_type"),
        "semantic_slot": card.get("semantic_slot"),
        "fact_statement": card.get("fact_statement"),
        "answer": card.get("answer"),
        "answer_type": card.get("answer_type"),
        "source_span": card.get("source_span"),
        "qa_variants": normalized_variants,
    }
    return output, warnings


def load_normalized_card(cache_dir: Path, item: Dict[str, Any], args: argparse.Namespace) -> Optional[Dict[str, Any]]:
    path = cache_dir / f"{slugify(item['holdout_card_id'])}__en__surface{args.surface_count}.normalized.json"
    if not path.exists() or args.refresh_cache or args.refresh_normalized_cache:
        return None
    cached = read_json(path)
    if cached.get("prompt_version") != PROMPT_VERSION:
        return None
    return cached


def write_normalized_card(cache_dir: Path, item: Dict[str, Any], payload: Dict[str, Any], warnings: List[str], args: argparse.Namespace) -> None:
    path = cache_dir / f"{slugify(item['holdout_card_id'])}__en__surface{args.surface_count}.normalized.json"
    write_json_atomic(
        path,
        {
            "prompt_version": PROMPT_VERSION,
            "holdout_card": payload,
            "warnings": warnings,
            "normalized_at": utc_now(),
        },
    )


def generate_batch(
    session: requests.Session,
    batch: Sequence[Dict[str, Any]],
    args: argparse.Namespace,
    cache_dir: Path,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    batch_key = cache_key_for_batch(batch, args.surface_count)
    raw_path = cache_dir / f"{batch_key}.raw.json"
    raw_payload = None
    if raw_path.exists() and not args.refresh_cache:
        cached_raw = read_json(raw_path)
        if cached_raw.get("prompt_version") == PROMPT_VERSION:
            raw_payload = cached_raw

    if raw_payload is None:
        response_json = call_chat_completion(
            session=session,
            api_base=args.api_base,
            api_keys=args.api_keys,
            model=args.model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_batch_prompt(batch, args.surface_count),
            temperature=args.temperature,
            timeout=args.timeout,
        )
        raw_payload = {
            "prompt_version": PROMPT_VERSION,
            "generated_at": utc_now(),
            "model": args.model,
            "api_base": normalize_api_base(args.api_base),
            "canonical_language": "en",
            "surface_count": args.surface_count,
            "holdout_card_ids": [item.get("holdout_card_id") for item in batch],
            "response": response_json,
        }
        write_json_atomic(raw_path, raw_payload)

    model_output = parse_model_json_response(raw_payload["response"])
    raw_cards = model_output.get("holdout_cards")
    if not isinstance(raw_cards, list):
        raw_cards = []
    by_id = {
        normalize_whitespace(raw.get("holdout_card_id")): raw
        for raw in raw_cards
        if isinstance(raw, dict)
    }

    outputs: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for item in batch:
        holdout_card_id = item.get("holdout_card_id")
        raw = by_id.get(holdout_card_id) or {}
        output, item_warnings = normalize_card_output(
            item,
            raw.get("qa_variants"),
            args.surface_count,
        )
        write_normalized_card(cache_dir, item, output, item_warnings, args)
        warnings.extend(f"{holdout_card_id}: {warning}" for warning in item_warnings)
        outputs.append(output)
    return outputs, warnings


def load_or_generate_cards(sample_doc: Dict[str, Any], args: argparse.Namespace) -> Tuple[List[Dict[str, Any]], List[str]]:
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cards = list(sample_doc.get("holdout_cards", []))
    if args.max_cards is not None:
        cards = cards[: args.max_cards]

    outputs: List[Dict[str, Any]] = []
    warnings: List[str] = []
    missing: List[Dict[str, Any]] = []

    for item in cards:
        cached = load_normalized_card(cache_dir, item, args)
        if cached is None:
            missing.append(item)
        else:
            outputs.append(cached["holdout_card"])
            warnings.extend(f"{item.get('holdout_card_id')}: {warning}" for warning in cached.get("warnings", []))

    if missing:
        session = requests.Session()
        for start in range(0, len(missing), args.batch_size):
            batch = missing[start : start + args.batch_size]
            log(f"Generating holdout QA for cards {start + 1}-{start + len(batch)} of {len(missing)} missing")
            batch_outputs, batch_warnings = generate_batch(session, batch, args, cache_dir)
            outputs.extend(batch_outputs)
            warnings.extend(batch_warnings)

    outputs.sort(key=lambda item: item.get("holdout_card_id", ""))
    return outputs, warnings


def build_output_document(sample_doc: Dict[str, Any], args: argparse.Namespace, holdout_cards: List[Dict[str, Any]], warnings: List[str]) -> Dict[str, Any]:
    core_count = 0
    surface_count = 0
    for item in holdout_cards:
        for variant in item.get("qa_variants", []):
            if variant.get("variant_layer") == "core":
                core_count += 1
            elif variant.get("variant_layer") == "surface":
                surface_count += 1
    return {
        "step": "holdout_qa_generation",
        "generated_at": utc_now(),
        "prompt_version": PROMPT_VERSION,
        "source_file": args.sample_output,
        "source_step": sample_doc.get("step"),
        "source_generated_at": sample_doc.get("generated_at"),
        "model": args.model,
        "api_base": normalize_api_base(args.api_base),
        "qa_config": {
            "language": "en",
            "core_count_per_card": 1,
            "surface_count_per_card": args.surface_count,
        },
        "summary": {
            "holdout_card_count": len(holdout_cards),
            "core_qa_count": core_count,
            "surface_qa_count": surface_count,
            "qa_variant_count": core_count + surface_count,
            "warning_count": len(warnings),
        },
        "warnings": warnings,
        "holdout_cards": holdout_cards,
    }


def main() -> None:
    args = parse_args()
    if args.sample_size <= 0:
        raise SystemExit("--sample-size must be positive.")
    if args.surface_count < 0:
        raise SystemExit("--surface-count must be non-negative.")
    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be positive.")
    if args.sample_only and args.generate_only:
        raise SystemExit("--sample-only and --generate-only cannot be used together.")

    sample_path = Path(args.sample_output)
    if not args.generate_only and (args.refresh_sample or not sample_path.exists()):
        sample_doc = build_sample_document(args)
        if args.dry_run:
            log(json.dumps(sample_doc["summary"], ensure_ascii=False, indent=2))
        else:
            write_json_atomic(sample_path, sample_doc)
            log(f"Wrote {sample_path} with {sample_doc['summary']['sampled_card_count']} sampled cards.")
    else:
        sample_doc = read_json(sample_path)

    if args.sample_only:
        return

    resolve_runtime_settings(args)
    if args.dry_run:
        log(f"Sampled cards: {len(sample_doc.get('holdout_cards', []))}")
        log(f"Expected QA variants: {len(sample_doc.get('holdout_cards', [])) * (1 + args.surface_count)}")
        return
    ensure_api_args(args)

    holdout_cards, warnings = load_or_generate_cards(sample_doc, args)
    output_doc = build_output_document(sample_doc, args, holdout_cards, warnings)
    write_json_atomic(Path(args.output), output_doc)
    log(
        f"Wrote {args.output} with "
        f"{output_doc['summary']['qa_variant_count']} QA variants "
        f"and {output_doc['summary']['warning_count']} warnings."
    )


if __name__ == "__main__":
    main()
