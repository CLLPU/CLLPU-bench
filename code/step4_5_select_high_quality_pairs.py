#!/usr/bin/env python3
"""Select a fixed-size high-quality subset from Step-4 knowledge-card pairs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Iterable, List, Tuple


QUALITY_LABEL_RANK = {
    "high": 2,
    "medium": 1,
    "review": 0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default="data/knowledge_card_pairs.json",
        help="Input Step-4 knowledge-card pair JSON.",
    )
    parser.add_argument(
        "--output",
        default="data/selected_knowledge_card_pairs.json",
        help="Output Step-4.5 selected knowledge-card pair JSON.",
    )
    parser.add_argument(
        "--target-total",
        type=int,
        default=500,
        help="Total number of knowledge-card pairs to keep.",
    )
    parser.add_argument(
        "--target-pairs-per-topic",
        type=int,
        default=10,
        help="Soft per-topic target before overflow fill.",
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


def filter_topic_pairs(
    topic_pairs: Iterable[Dict[str, Any]],
    pair_ids: List[str] | None,
) -> List[Dict[str, Any]]:
    selected = list(topic_pairs)
    if pair_ids:
        allowed = set(pair_ids)
        selected = [pair for pair in selected if pair.get("pair_id") in allowed]
    return selected


def pair_sort_key(record: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        -float(record.get("quality_score", 0.0)),
        -QUALITY_LABEL_RANK.get(str(record.get("quality_label", "")).lower(), -1),
        len(record.get("review_flags", [])),
        str(record.get("relation_type", "")),
        str(record.get("knowledge_pair_id", "")),
    )


def average(values: List[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def prepare_topic_pair(topic_pair: Dict[str, Any], base_quota: int) -> Dict[str, Any]:
    available_pairs = sorted(
        list(topic_pair.get("knowledge_card_pairs", [])),
        key=pair_sort_key,
    )
    base_selected = min(len(available_pairs), base_quota)
    selected_pairs = available_pairs[:base_selected]
    remaining_pairs = available_pairs[base_selected:]
    return {
        "pair": topic_pair,
        "available_pairs": available_pairs,
        "selected_pairs": selected_pairs,
        "remaining_pairs": remaining_pairs,
        "base_selected_count": base_selected,
        "overflow_selected_count": 0,
    }


def select_pairs(
    topic_pairs: List[Dict[str, Any]],
    target_total: int,
    target_pairs_per_topic: int,
) -> Tuple[List[Dict[str, Any]], int, List[Dict[str, Any]]]:
    if target_total <= 0:
        raise SystemExit("--target-total must be positive.")
    if target_pairs_per_topic <= 0:
        raise SystemExit("--target-pairs-per-topic must be positive.")
    if not topic_pairs:
        raise SystemExit("No topic pairs selected.")

    available_total = sum(len(pair.get("knowledge_card_pairs", [])) for pair in topic_pairs)
    if available_total < target_total:
        raise SystemExit(
            f"Only {available_total} knowledge-card pairs available, which is less than "
            f"--target-total={target_total}."
        )

    topic_pair_count = len(topic_pairs)
    base_quota = min(target_pairs_per_topic, target_total // topic_pair_count)
    prepared = [prepare_topic_pair(topic_pair, base_quota) for topic_pair in topic_pairs]

    selected_total = sum(len(item["selected_pairs"]) for item in prepared)
    remaining = target_total - selected_total
    overflow_rounds: List[Dict[str, Any]] = []
    round_index = 0

    while remaining > 0:
        round_index += 1
        round_candidates = []
        for item in prepared:
            if not item["remaining_pairs"]:
                continue
            next_pair = item["remaining_pairs"][0]
            round_candidates.append(
                (
                    -float(next_pair.get("quality_score", 0.0)),
                    len(item["selected_pairs"]),
                    len(next_pair.get("review_flags", [])),
                    str(item["pair"].get("pair_id", "")),
                    str(next_pair.get("knowledge_pair_id", "")),
                    item,
                    next_pair,
                )
            )

        if not round_candidates:
            raise SystemExit(
                f"Unable to reach --target-total={target_total}; ran out of overflow candidates "
                f"after selecting {target_total - remaining} pairs."
            )

        round_candidates.sort()
        allocation_count = min(remaining, len(round_candidates))
        allocations = []
        for candidate in round_candidates[:allocation_count]:
            item = candidate[5]
            next_pair = candidate[6]
            item["selected_pairs"].append(next_pair)
            item["remaining_pairs"] = item["remaining_pairs"][1:]
            item["overflow_selected_count"] += 1
            remaining -= 1
            allocations.append(
                {
                    "pair_id": item["pair"].get("pair_id"),
                    "knowledge_pair_id": next_pair.get("knowledge_pair_id"),
                    "quality_score": next_pair.get("quality_score"),
                }
            )
        overflow_rounds.append(
            {
                "round": round_index,
                "allocation_count": len(allocations),
                "allocations": allocations,
            }
        )

    return prepared, base_quota, overflow_rounds


def build_topic_pair_output(item: Dict[str, Any], target_pairs_per_topic: int) -> Dict[str, Any]:
    source_pair = item["pair"]
    selected_pairs = item["selected_pairs"]
    selected_scores = [float(record.get("quality_score", 0.0)) for record in selected_pairs]
    remaining_scores = [
        float(record.get("quality_score", 0.0))
        for record in item["remaining_pairs"]
    ]
    source_stats = dict(source_pair.get("stats", {}))

    return {
        "pair_id": source_pair.get("pair_id"),
        "topic_type": source_pair.get("topic_type"),
        "target_topic": source_pair.get("target_topic"),
        "neighbor_topic": source_pair.get("neighbor_topic"),
        "stats": {
            "source_selected_pair_count": len(item["available_pairs"]),
            "selected_pair_count": len(selected_pairs),
            "base_quota_selected_count": item["base_selected_count"],
            "overflow_selected_count": item["overflow_selected_count"],
            "unselected_pair_count": len(item["remaining_pairs"]),
            "selected_quality_score_min": min(selected_scores) if selected_scores else None,
            "selected_quality_score_max": max(selected_scores) if selected_scores else None,
            "selected_quality_score_avg": average(selected_scores),
            "highest_unselected_quality_score": max(remaining_scores) if remaining_scores else None,
            "target_pairs_per_topic": target_pairs_per_topic,
            "source_stats": source_stats,
        },
        "knowledge_card_pairs": selected_pairs,
    }


def build_output(
    source_file: str,
    source_data: Dict[str, Any],
    prepared: List[Dict[str, Any]],
    base_quota: int,
    overflow_rounds: List[Dict[str, Any]],
    target_total: int,
    target_pairs_per_topic: int,
) -> Dict[str, Any]:
    output_topic_pairs = [
        build_topic_pair_output(item, target_pairs_per_topic)
        for item in prepared
    ]

    selected_pairs = [
        pair
        for topic_pair in output_topic_pairs
        for pair in topic_pair["knowledge_card_pairs"]
    ]
    selected_review_flag_counts: Counter[str] = Counter()
    selected_quality_label_counts: Counter[str] = Counter()
    for pair in selected_pairs:
        selected_review_flag_counts.update(pair.get("review_flags", []))
        selected_quality_label_counts.update([pair.get("quality_label", "unknown")])

    topic_pairs_below_target = []
    for topic_pair in output_topic_pairs:
        selected_count = topic_pair["stats"]["selected_pair_count"]
        available_count = topic_pair["stats"]["source_selected_pair_count"]
        if selected_count < target_pairs_per_topic:
            topic_pairs_below_target.append(
                {
                    "pair_id": topic_pair["pair_id"],
                    "available_pair_count": available_count,
                    "selected_pair_count": selected_count,
                    "shortfall_vs_target_pairs_per_topic": target_pairs_per_topic - selected_count,
                }
            )

    return {
        "step": "Step 4.5 high-quality knowledge card pair selection",
        "generated_at": utc_now(),
        "source_file": source_file,
        "source_step": source_data.get("step"),
        "source_generated_at": source_data.get("generated_at"),
        "selection_config": {
            "target_selected_pair_count": target_total,
            "target_pairs_per_topic": target_pairs_per_topic,
            "base_quota_per_topic": base_quota,
            "selection_strategy": (
                "Per-topic top-k by quality_score, then round-robin overflow fill "
                "using each topic pair's next-best remaining candidate."
            ),
        },
        "summary": {
            "topic_pair_count": len(output_topic_pairs),
            "source_selected_pair_count": sum(
                topic_pair["stats"]["source_selected_pair_count"]
                for topic_pair in output_topic_pairs
            ),
            "selected_pair_count": len(selected_pairs),
            "target_selected_pair_count": target_total,
            "overflow_pair_count": sum(
                topic_pair["stats"]["overflow_selected_count"]
                for topic_pair in output_topic_pairs
            ),
            "overflow_round_count": len(overflow_rounds),
            "selected_quality_label_counts": dict(selected_quality_label_counts),
            "selected_review_flag_counts": dict(selected_review_flag_counts),
            "topic_pairs_below_target_pairs_per_topic_count": len(topic_pairs_below_target),
            "topic_pairs_below_target_pairs_per_topic": topic_pairs_below_target,
            "overflow_rounds": overflow_rounds,
        },
        "topic_pairs": output_topic_pairs,
    }


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    source_data = read_json(input_path)
    topic_pairs = filter_topic_pairs(source_data.get("topic_pairs", []), args.pair_ids)
    prepared, base_quota, overflow_rounds = select_pairs(
        topic_pairs=topic_pairs,
        target_total=args.target_total,
        target_pairs_per_topic=args.target_pairs_per_topic,
    )
    output_data = build_output(
        source_file=str(input_path),
        source_data=source_data,
        prepared=prepared,
        base_quota=base_quota,
        overflow_rounds=overflow_rounds,
        target_total=args.target_total,
        target_pairs_per_topic=args.target_pairs_per_topic,
    )
    write_json_atomic(output_path, output_data)

    print(f"Wrote {output_path}")
    print(
        "Selected "
        f"{output_data['summary']['selected_pair_count']} pairs "
        f"from {output_data['summary']['source_selected_pair_count']} source pairs"
    )


if __name__ == "__main__":
    main()
