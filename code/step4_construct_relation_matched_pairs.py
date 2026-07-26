#!/usr/bin/env python3
"""Construct relation-matched target/neighbor knowledge-card pairs."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


ANSWER_TYPE_GROUPS = {
    "person": {"person", "people", "human", "artist", "creator", "scientist"},
    "date": {"date", "year", "time", "mission_date"},
    "location": {"location", "place", "country", "city", "region", "site"},
    "organization": {
        "organization",
        "organisation",
        "company",
        "agency",
        "institution",
        "fictional_organization",
    },
    "work": {"work", "book", "film", "painting", "artwork", "television_series"},
    "medical_condition": {
        "disease",
        "condition",
        "disease_or_condition",
        "disease_or_medical_condition",
        "medical_condition",
        "disease_condition",
        "physiological_target_state",
        "clinical_purpose",
        "clinical_subject",
        "target_condition",
    },
    "biological_role": {
        "biological_role",
        "mechanism",
        "mechanism_or_role",
        "physiological_role",
        "process",
        "production_method",
        "medical_mechanism",
    },
    "drug_or_chemical": {
        "chemical",
        "compound",
        "chemical_structure",
        "structural_description",
        "drug",
        "drug_class",
        "drug_form",
        "formulation",
        "named_formulation",
        "analogue",
        "derivative",
        "route",
        "delivery_device",
    },
    "concept": {
        "concept",
        "term",
        "fictional_concept",
        "mythological_concept",
        "cosmology_term",
    },
    "object": {
        "object",
        "artifact",
        "artefact",
        "fictional_object",
        "vehicle",
        "spacecraft",
        "payload",
        "component",
    },
}

DEFAULT_EXCLUDED_REVIEW_FLAGS = [
    "semantic_slot_weak_match",
    "same_answer_text_across_target_neighbor",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default="data/knowledge_cards.json",
        help="Step 3 knowledge-card inventory JSON.",
    )
    parser.add_argument(
        "--output",
        default="data/knowledge_card_pairs.json",
        help="Output relation-matched card-pair JSON.",
    )
    parser.add_argument(
        "--target-pairs-per-topic",
        type=int,
        default=20,
        help="Maximum number of relation-matched pairs to keep for each topic pair.",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=70.0,
        help="Minimum pair quality score to keep.",
    )
    parser.add_argument(
        "--allow-card-reuse",
        action="store_true",
        help="Allow one card to appear in multiple final pairs.",
    )
    parser.add_argument(
        "--strict-answer-type",
        action="store_true",
        help="Require exact normalized answer_type equality.",
    )
    parser.add_argument(
        "--require-direct-answer-span",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "For newly selected pairs, require both answers to appear directly "
            "inside their source_span. Seed pairs are preserved as-is."
        ),
    )
    parser.add_argument(
        "--max-answer-words",
        type=int,
        default=6,
        help=(
            "Optional maximum answer word count for newly selected pairs. "
            "Use 0 to disable. Seed pairs are preserved as-is."
        ),
    )
    parser.add_argument(
        "--exclude-review-flag",
        action="append",
        default=None,
        help=(
            "Review flag to exclude from newly selected pairs. Can be passed "
            "multiple times. By default excludes semantic_slot_weak_match and "
            "same_answer_text_across_target_neighbor."
        ),
    )
    parser.add_argument(
        "--allow-default-review-flags",
        action="store_true",
        help=(
            "Do not apply the default review-flag exclusions. Any explicit "
            "--exclude-review-flag values still apply."
        ),
    )
    parser.add_argument(
        "--seed-pairs",
        default="",
        help=(
            "Optional existing Step 4 output whose selected pairs should be "
            "preserved before filling the remaining slots."
        ),
    )
    parser.add_argument(
        "--quality-blocklist",
        default="",
        help=(
            "Optional JSON review file listing card IDs, answer texts, or pair "
            "card combinations to exclude from newly selected pairs. Seed pairs "
            "are preserved as-is."
        ),
    )
    parser.add_argument(
        "--pair-id",
        action="append",
        dest="pair_ids",
        help="Optional pair_id to process. Can be passed multiple times.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def slugify(value: Any) -> str:
    normalized = normalize_text(value).lower()
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")


def token_set(value: Any) -> Set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", normalize_text(value).lower()) if token}


def answer_type_family(answer_type: str) -> Optional[str]:
    normalized = slugify(answer_type)
    for family, aliases in ANSWER_TYPE_GROUPS.items():
        if normalized in aliases:
            return family
        if any(alias in normalized for alias in aliases):
            return family
    return None


def answer_type_compatible(left: str, right: str, strict: bool) -> Tuple[bool, str]:
    left_norm = slugify(left)
    right_norm = slugify(right)
    if left_norm == right_norm:
        return True, "exact"
    if strict:
        return False, "mismatch"
    left_family = answer_type_family(left_norm)
    right_family = answer_type_family(right_norm)
    if left_family and left_family == right_family:
        return True, f"family:{left_family}"
    return False, "mismatch"


def answer_in_source_span(card: Dict[str, Any]) -> bool:
    answer = normalize_text(card.get("answer")).lower()
    source_span = normalize_text(card.get("source_span")).lower()
    return bool(answer and answer in source_span)


def semantic_slot_core(value: str) -> str:
    slot = normalize_text(value)
    if "->" in slot:
        slot = slot.rsplit("->", 1)[-1]
    return slot.strip()


def semantic_slot_similarity(left: str, right: str) -> float:
    left_tokens = token_set(semantic_slot_core(left))
    right_tokens = token_set(semantic_slot_core(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def priority_points(card: Dict[str, Any]) -> float:
    priority = normalize_text(card.get("eval_priority")).lower()
    if priority == "high":
        return 5.0
    if priority == "medium":
        return 2.5
    return 0.0


def score_pair(
    target_card: Dict[str, Any],
    neighbor_card: Dict[str, Any],
    answer_type_match: str,
) -> Tuple[float, List[str]]:
    flags: List[str] = []
    score = 55.0

    if answer_type_match == "exact":
        score += 18.0
    elif answer_type_match.startswith("family:"):
        score += 10.0
        flags.append("answer_type_family_match")

    slot_similarity = semantic_slot_similarity(
        target_card.get("semantic_slot", ""),
        neighbor_card.get("semantic_slot", ""),
    )
    if slot_similarity >= 0.99:
        score += 10.0
    elif slot_similarity >= 0.35:
        score += 5.0
        flags.append("semantic_slot_partial_match")
    else:
        flags.append("semantic_slot_weak_match")

    target_answer_direct = answer_in_source_span(target_card)
    neighbor_answer_direct = answer_in_source_span(neighbor_card)
    if target_answer_direct and neighbor_answer_direct:
        score += 10.0
    else:
        score -= 8.0
        flags.append("answer_not_directly_in_source_span")

    score += priority_points(target_card)
    score += priority_points(neighbor_card)

    if normalize_text(target_card.get("answer")).lower() == normalize_text(neighbor_card.get("answer")).lower():
        score -= 4.0
        flags.append("same_answer_text_across_target_neighbor")

    return round(score, 2), flags


def answer_length_penalty(card: Dict[str, Any]) -> int:
    return len(normalize_text(card.get("answer")).split())


def card_identity(card: Dict[str, Any]) -> Tuple[str, str, str]:
    return (
        slugify(card.get("relation_type")),
        slugify(card.get("answer_type")),
        normalize_text(card.get("answer")).lower(),
    )


def fact_identity(card: Dict[str, Any]) -> str:
    return normalize_text(card.get("fact_statement")).lower()


def load_quality_blocklist(path: str) -> Dict[str, Set[Tuple[str, ...]]]:
    # Step 7 review can feed known-bad candidates back into deterministic Step 4
    # without hand-editing the final selected pair file.
    empty: Dict[str, Set[Tuple[str, ...]]] = {
        "card_ids": set(),
        "answers": set(),
        "pair_card_ids": set(),
        "relations": set(),
    }
    if not path:
        return empty

    data = read_json(Path(path))
    for item in data.get("blocked_cards", []):
        pair_id = normalize_text(item.get("pair_id"))
        role = normalize_text(item.get("role"))
        card_id = normalize_text(item.get("card_id"))
        if pair_id and role and card_id:
            empty["card_ids"].add((pair_id, role, card_id))
    for item in data.get("blocked_answers", []):
        pair_id = normalize_text(item.get("pair_id"))
        role = normalize_text(item.get("role"))
        answer = normalize_text(item.get("answer")).lower()
        if pair_id and role and answer:
            empty["answers"].add((pair_id, role, answer))
    for item in data.get("blocked_pair_card_combinations", []):
        pair_id = normalize_text(item.get("pair_id"))
        target_card_id = normalize_text(item.get("target_card_id"))
        neighbor_card_id = normalize_text(item.get("neighbor_card_id"))
        if pair_id and target_card_id and neighbor_card_id:
            empty["pair_card_ids"].add((pair_id, target_card_id, neighbor_card_id))
    for item in data.get("blocked_relations", []):
        pair_id = normalize_text(item.get("pair_id"))
        relation_type = slugify(item.get("relation_type"))
        if pair_id and relation_type:
            empty["relations"].add((pair_id, relation_type))
    return empty


def resolve_excluded_review_flags(args: argparse.Namespace) -> List[str]:
    explicit_flags = [normalize_text(flag) for flag in args.exclude_review_flag or []]
    explicit_flags = [flag for flag in explicit_flags if flag]
    if args.allow_default_review_flags:
        flags = explicit_flags
    else:
        flags = DEFAULT_EXCLUDED_REVIEW_FLAGS + explicit_flags
    return list(dict.fromkeys(flags))


def candidate_blocked(
    pair_id: str,
    candidate: Dict[str, Any],
    blocklist: Dict[str, Set[Tuple[str, ...]]],
) -> bool:
    relation_type = slugify(candidate.get("relation_type"))
    target_card = candidate["target_card"]
    neighbor_card = candidate["neighbor_card"]
    target_id = normalize_text(target_card.get("card_id"))
    neighbor_id = normalize_text(neighbor_card.get("card_id"))
    target_answer = normalize_text(target_card.get("answer")).lower()
    neighbor_answer = normalize_text(neighbor_card.get("answer")).lower()
    return any(
        (
            (pair_id, relation_type) in blocklist["relations"],
            (pair_id, "target", target_id) in blocklist["card_ids"],
            (pair_id, "neighbor", neighbor_id) in blocklist["card_ids"],
            (pair_id, "target", target_answer) in blocklist["answers"],
            (pair_id, "neighbor", neighbor_answer) in blocklist["answers"],
            (pair_id, target_id, neighbor_id) in blocklist["pair_card_ids"],
        )
    )


def quality_label(score: float, flags: List[str]) -> str:
    if score >= 90 and not any(flag.endswith("weak_match") for flag in flags):
        return "high"
    if score >= 78:
        return "medium"
    return "review"


def compact_card(card: Dict[str, Any]) -> Dict[str, Any]:
    keep_fields = [
        "card_id",
        "card_type",
        "relation_type",
        "semantic_slot",
        "fact_statement",
        "answer",
        "answer_type",
        "section_title",
        "source_span",
        "aliases",
        "knowledge_scope",
        "eval_priority",
    ]
    return {field: card.get(field) for field in keep_fields}


def build_candidate_pairs(
    pair: Dict[str, Any],
    strict_answer_type: bool,
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    target_cards = pair["target"].get("knowledge_cards", [])
    neighbor_cards = pair["neighbor"].get("knowledge_cards", [])

    neighbor_by_relation: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for card in neighbor_cards:
        neighbor_by_relation[slugify(card.get("relation_type"))].append(card)

    for target_card in target_cards:
        relation_type = slugify(target_card.get("relation_type"))
        for neighbor_card in neighbor_by_relation.get(relation_type, []):
            compatible, answer_type_match = answer_type_compatible(
                target_card.get("answer_type", ""),
                neighbor_card.get("answer_type", ""),
                strict=strict_answer_type,
            )
            if not compatible:
                continue
            score, flags = score_pair(target_card, neighbor_card, answer_type_match)
            candidates.append(
                {
                    "relation_type": relation_type,
                    "semantic_slot_similarity": round(
                        semantic_slot_similarity(
                            target_card.get("semantic_slot", ""),
                            neighbor_card.get("semantic_slot", ""),
                        ),
                        3,
                    ),
                    "answer_type_match": answer_type_match,
                    "score": score,
                    "quality_label": quality_label(score, flags),
                    "review_flags": flags,
                    "target_card": target_card,
                    "neighbor_card": neighbor_card,
                }
            )
    return candidates


def select_pairs(
    pair_id: str,
    candidates: Iterable[Dict[str, Any]],
    max_pairs: int,
    min_score: float,
    allow_card_reuse: bool,
    quality_blocklist: Optional[Dict[str, Set[Tuple[str, ...]]]] = None,
    require_direct_answer_span: bool = False,
    max_answer_words: int = 0,
    used_target_ids: Optional[Set[str]] = None,
    used_neighbor_ids: Optional[Set[str]] = None,
    used_target_identities: Optional[Set[Tuple[str, str, str]]] = None,
    used_neighbor_identities: Optional[Set[Tuple[str, str, str]]] = None,
    used_target_facts: Optional[Set[str]] = None,
    used_neighbor_facts: Optional[Set[str]] = None,
    excluded_review_flags: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    if max_pairs <= 0:
        return selected

    used_target_ids = set(used_target_ids or set())
    used_neighbor_ids = set(used_neighbor_ids or set())
    used_target_identities = set(used_target_identities or set())
    used_neighbor_identities = set(used_neighbor_identities or set())
    used_target_facts = set(used_target_facts or set())
    used_neighbor_facts = set(used_neighbor_facts or set())
    excluded_review_flags = set(excluded_review_flags or set())

    sorted_candidates = sorted(
        candidates,
        key=lambda item: (
            "answer_not_directly_in_source_span" not in item["review_flags"],
            item["score"],
            item["semantic_slot_similarity"],
            -max(
                answer_length_penalty(item["target_card"]),
                answer_length_penalty(item["neighbor_card"]),
            ),
            item["relation_type"],
        ),
        reverse=True,
    )

    for candidate in sorted_candidates:
        if len(selected) >= max_pairs:
            break
        if quality_blocklist and candidate_blocked(pair_id, candidate, quality_blocklist):
            continue
        if candidate["score"] < min_score:
            continue
        if excluded_review_flags and excluded_review_flags.intersection(candidate["review_flags"]):
            continue
        if require_direct_answer_span and "answer_not_directly_in_source_span" in candidate["review_flags"]:
            continue
        if max_answer_words > 0 and max(
            answer_length_penalty(candidate["target_card"]),
            answer_length_penalty(candidate["neighbor_card"]),
        ) > max_answer_words:
            continue

        target_id = candidate["target_card"]["card_id"]
        neighbor_id = candidate["neighbor_card"]["card_id"]
        if not allow_card_reuse and (target_id in used_target_ids or neighbor_id in used_neighbor_ids):
            continue
        target_identity = card_identity(candidate["target_card"])
        neighbor_identity = card_identity(candidate["neighbor_card"])
        if not allow_card_reuse and (
            target_identity in used_target_identities
            or neighbor_identity in used_neighbor_identities
        ):
            continue
        target_fact = fact_identity(candidate["target_card"])
        neighbor_fact = fact_identity(candidate["neighbor_card"])
        if not allow_card_reuse and (
            target_fact in used_target_facts
            or neighbor_fact in used_neighbor_facts
        ):
            continue

        selected.append(candidate)
        used_target_ids.add(target_id)
        used_neighbor_ids.add(neighbor_id)
        used_target_identities.add(target_identity)
        used_neighbor_identities.add(neighbor_identity)
        used_target_facts.add(target_fact)
        used_neighbor_facts.add(neighbor_fact)

    return selected


def pair_record(pair: Dict[str, Any], candidate: Dict[str, Any], index: int) -> Dict[str, Any]:
    relation_type = candidate["relation_type"]
    knowledge_pair_id = f"{pair['pair_id']}__{relation_type}__{index:03d}"
    target_card = compact_card(candidate["target_card"])
    neighbor_card = compact_card(candidate["neighbor_card"])
    return {
        "knowledge_pair_id": knowledge_pair_id,
        "pair_id": pair["pair_id"],
        "topic_type": pair["topic_type"],
        "relation_type": relation_type,
        "semantic_slot_similarity": candidate["semantic_slot_similarity"],
        "answer_type_match": candidate["answer_type_match"],
        "answer_type_pair": {
            "target": target_card.get("answer_type"),
            "neighbor": neighbor_card.get("answer_type"),
        },
        "quality_score": candidate["score"],
        "quality_label": candidate["quality_label"],
        "review_flags": candidate["review_flags"],
        "target": {
            "topic_name": pair["target"].get("topic_name"),
            "topic_type": pair["target"].get("topic_type"),
            "source_page": pair["target"].get("source_page"),
            "source_url": pair["target"].get("source_url"),
            "card": target_card,
        },
        "neighbor": {
            "topic_name": pair["neighbor"].get("topic_name"),
            "topic_type": pair["neighbor"].get("topic_type"),
            "source_page": pair["neighbor"].get("source_page"),
            "source_url": pair["neighbor"].get("source_url"),
            "card": neighbor_card,
        },
    }


def seed_records_for_pair(seed_data: Optional[Dict[str, Any]], pair_id: str) -> List[Dict[str, Any]]:
    # Seed pairs are preserved as released data; new selection only fills the
    # remaining slots while avoiding seed card/fact reuse.
    if not seed_data:
        return []
    for pair in seed_data.get("topic_pairs", []):
        if pair.get("pair_id") == pair_id:
            return list(pair.get("knowledge_card_pairs", []))
    return []


def used_cards_from_records(records: Iterable[Dict[str, Any]]) -> Tuple[
    Set[str],
    Set[str],
    Set[Tuple[str, str, str]],
    Set[Tuple[str, str, str]],
    Set[str],
    Set[str],
]:
    target_ids: Set[str] = set()
    neighbor_ids: Set[str] = set()
    target_identities: Set[Tuple[str, str, str]] = set()
    neighbor_identities: Set[Tuple[str, str, str]] = set()
    target_facts: Set[str] = set()
    neighbor_facts: Set[str] = set()

    for record in records:
        target_card = record.get("target", {}).get("card", {})
        neighbor_card = record.get("neighbor", {}).get("card", {})
        target_id = normalize_text(target_card.get("card_id"))
        neighbor_id = normalize_text(neighbor_card.get("card_id"))
        if target_id:
            target_ids.add(target_id)
        if neighbor_id:
            neighbor_ids.add(neighbor_id)
        if target_card:
            target_identities.add(card_identity(target_card))
            target_facts.add(fact_identity(target_card))
        if neighbor_card:
            neighbor_identities.add(card_identity(neighbor_card))
            neighbor_facts.add(fact_identity(neighbor_card))

    return target_ids, neighbor_ids, target_identities, neighbor_identities, target_facts, neighbor_facts


def process_topic_pair(pair: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    candidates = build_candidate_pairs(pair, args.strict_answer_type)
    seed_records = seed_records_for_pair(args.seed_pairs_data, pair["pair_id"])
    if len(seed_records) > args.target_pairs_per_topic:
        raise SystemExit(
            f"Seed pair count for {pair['pair_id']} ({len(seed_records)}) exceeds "
            f"--target-pairs-per-topic ({args.target_pairs_per_topic})."
        )
    (
        used_target_ids,
        used_neighbor_ids,
        used_target_identities,
        used_neighbor_identities,
        used_target_facts,
        used_neighbor_facts,
    ) = used_cards_from_records(seed_records)
    selected = select_pairs(
        pair_id=pair["pair_id"],
        candidates=candidates,
        max_pairs=args.target_pairs_per_topic - len(seed_records),
        min_score=args.min_score,
        allow_card_reuse=args.allow_card_reuse,
        quality_blocklist=args.quality_blocklist_data,
        require_direct_answer_span=args.require_direct_answer_span,
        max_answer_words=args.max_answer_words,
        used_target_ids=used_target_ids,
        used_neighbor_ids=used_neighbor_ids,
        used_target_identities=used_target_identities,
        used_neighbor_identities=used_neighbor_identities,
        used_target_facts=used_target_facts,
        used_neighbor_facts=used_neighbor_facts,
        excluded_review_flags=set(args.excluded_review_flags),
    )
    added_records = [
        pair_record(pair, candidate, index)
        for index, candidate in enumerate(selected, start=len(seed_records) + 1)
    ]
    selected_records = seed_records + added_records

    target_relation_counts = Counter(
        slugify(card.get("relation_type")) for card in pair["target"].get("knowledge_cards", [])
    )
    neighbor_relation_counts = Counter(
        slugify(card.get("relation_type")) for card in pair["neighbor"].get("knowledge_cards", [])
    )
    selected_relation_counts = Counter(record["relation_type"] for record in selected_records)
    candidate_review_flag_counts = Counter(
        flag for candidate in candidates for flag in candidate.get("review_flags", [])
    )
    selected_review_flag_counts = Counter(
        flag for record in selected_records for flag in record.get("review_flags", [])
    )

    return {
        "pair_id": pair["pair_id"],
        "topic_type": pair["topic_type"],
        "target_topic": pair["target"].get("topic_name"),
        "neighbor_topic": pair["neighbor"].get("topic_name"),
        "stats": {
            "target_card_count": len(pair["target"].get("knowledge_cards", [])),
            "neighbor_card_count": len(pair["neighbor"].get("knowledge_cards", [])),
            "candidate_pair_count": len(candidates),
            "selected_pair_count": len(selected_records),
            "seed_pair_count": len(seed_records),
            "added_pair_count": len(added_records),
            "target_relation_counts": dict(target_relation_counts),
            "neighbor_relation_counts": dict(neighbor_relation_counts),
            "selected_relation_counts": dict(selected_relation_counts),
            "candidate_review_flag_counts": dict(candidate_review_flag_counts),
            "selected_review_flag_counts": dict(selected_review_flag_counts),
        },
        "knowledge_card_pairs": selected_records,
    }


def filter_topic_pairs(topic_pairs: Iterable[Dict[str, Any]], pair_ids: Optional[List[str]]) -> List[Dict[str, Any]]:
    selected = list(topic_pairs)
    if pair_ids:
        allowed = set(pair_ids)
        selected = [pair for pair in selected if pair.get("pair_id") in allowed]
    return selected


def build_output(source_file: str, input_data: Dict[str, Any], processed_pairs: List[Dict[str, Any]], args: argparse.Namespace) -> Dict[str, Any]:
    total_selected = sum(pair["stats"]["selected_pair_count"] for pair in processed_pairs)
    total_candidates = sum(pair["stats"]["candidate_pair_count"] for pair in processed_pairs)
    selected_review_flag_counts: Counter[str] = Counter()
    candidate_review_flag_counts: Counter[str] = Counter()
    shortfall_topic_pairs = []
    for pair in processed_pairs:
        selected_review_flag_counts.update(pair["stats"].get("selected_review_flag_counts", {}))
        candidate_review_flag_counts.update(pair["stats"].get("candidate_review_flag_counts", {}))
        if pair["stats"]["selected_pair_count"] < args.target_pairs_per_topic:
            shortfall_topic_pairs.append(
                {
                    "pair_id": pair["pair_id"],
                    "selected_pair_count": pair["stats"]["selected_pair_count"],
                    "target_pairs_per_topic": args.target_pairs_per_topic,
                }
            )
    return {
        "step": "Step 4 relation-matched knowledge card pairing",
        "generated_at": utc_now(),
        "source_file": source_file,
        "source_step3_prompt_version": input_data.get("prompt_version"),
        "pairing_config": {
            "target_pairs_per_topic": args.target_pairs_per_topic,
            "min_score": args.min_score,
            "allow_card_reuse": args.allow_card_reuse,
            "strict_answer_type": args.strict_answer_type,
            "require_direct_answer_span": args.require_direct_answer_span,
            "max_answer_words": args.max_answer_words,
            "excluded_review_flags": args.excluded_review_flags,
            "seed_pair_count": sum(pair["stats"].get("seed_pair_count", 0) for pair in processed_pairs),
            "quality_blocklist": args.quality_blocklist,
        },
        "summary": {
            "topic_pair_count": len(processed_pairs),
            "candidate_pair_count": total_candidates,
            "selected_pair_count": total_selected,
            "candidate_review_flag_counts": dict(candidate_review_flag_counts),
            "selected_review_flag_counts": dict(selected_review_flag_counts),
            "shortfall_topic_pair_count": len(shortfall_topic_pairs),
            "shortfall_topic_pairs": shortfall_topic_pairs,
        },
        "topic_pairs": processed_pairs,
    }


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    input_data = read_json(input_path)
    args.seed_pairs_data = read_json(Path(args.seed_pairs)) if args.seed_pairs else None
    args.quality_blocklist_data = load_quality_blocklist(args.quality_blocklist)
    args.excluded_review_flags = resolve_excluded_review_flags(args)
    topic_pairs = filter_topic_pairs(input_data.get("topic_pairs", []), args.pair_ids)
    if not topic_pairs:
        raise SystemExit("No topic pairs selected.")

    processed_pairs = [process_topic_pair(pair, args) for pair in topic_pairs]
    output_data = build_output(str(input_path), input_data, processed_pairs, args)
    write_json_atomic(output_path, output_data)

    print(f"Wrote {output_path}")
    print(f"Selected {output_data['summary']['selected_pair_count']} pairs from {output_data['summary']['candidate_pair_count']} candidates")


if __name__ == "__main__":
    main()
