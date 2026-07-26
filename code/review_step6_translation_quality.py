#!/usr/bin/env python3
"""Sample Step-6 QA translations and review translation quality with an LLM judge."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Iterable, List, Sequence

import requests

import step6_expand_qa_translations as step6


PROMPT_VERSION = "step6_translation_quality_review_v1"
DEFAULT_LANGUAGES = ["ar", "bn", "de", "es", "fr", "ja", "sw", "th", "zh"]

SYSTEM_PROMPT = """You are a multilingual QA translation quality reviewer.

Return JSON only. Evaluate translation quality only.
Ignore answer_aliases entirely: do not penalize missing aliases, extra aliases, or alias coverage.
Compare the English source question/expected_answer with the target-language question/expected_answer.
Proper names, acronyms, product names, official names, and titles may remain in Latin script when natural.
Do not judge whether the underlying fact is true; judge whether the target-language QA faithfully preserves the English QA.
Use the provided backtranslation only as weak context. Prefer direct judgment of the target text when you know the language.
"""

USER_PROMPT_TEMPLATE = """Review these {language_name} QA translations.

For each item, return exactly one review object with:
- id: same item id.
- overall_pass: true if the translated question and expected_answer are faithful enough for benchmark use.
- severity: "ok", "minor", or "major".
- issue_type: one of "none", "question_drift", "answer_drift", "mistranslation", "wrong_language", "unnatural", "overliteral", "ambiguous", "proper_name_drift", "formatting", "other".
- faithfulness_score: integer 1-5 for source-to-target meaning preservation.
- answer_accuracy_score: integer 1-5 for expected_answer translation accuracy.
- fluency_score: integer 1-5 for naturalness in the target language.
- language_purity_score: integer 1-5 for using the requested target language; allow Latin-script names/acronyms.
- comment: concise English explanation. For ok reviews, keep this short.

Severity guidance:
- ok: faithful and usable.
- minor: faithful enough but awkward, over-literal, or mildly ambiguous.
- major: wrong answer, changed relation, changed constraints, wrong language, or materially misleading question.

Return this exact top-level shape:
{{"reviews":[{{"id":"...","overall_pass":true,"severity":"ok","issue_type":"none","faithfulness_score":5,"answer_accuracy_score":5,"fluency_score":5,"language_purity_score":5,"comment":"..."}}]}}

Items:
{items_json}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/llm_api.env")
    parser.add_argument("--input-template", default="data/qa_variants.{lang}.culture_specific.json")
    parser.add_argument("--english-input", default="data/qa_variants.en.culture_specific.json")
    parser.add_argument("--languages", default=",".join(DEFAULT_LANGUAGES))
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260701)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--cache-dir", default="data/step6_translation_quality_review_cache.culture_specific")
    parser.add_argument("--output", default="data/qa_translation_quality_review.sample100.culture_specific.json")
    parser.add_argument("--tsv-output", default="data/qa_translation_quality_review.sample100.culture_specific.tsv")
    parser.add_argument("--api-base", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def write_tsv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "language",
        "id",
        "qa_id",
        "source_qa_id",
        "pair_id",
        "knowledge_pair_id",
        "holdout_card_id",
        "source_card_id",
        "topic_role",
        "variant_layer",
        "relation_type",
        "overall_pass",
        "severity",
        "issue_type",
        "faithfulness_score",
        "answer_accuracy_score",
        "fluency_score",
        "language_purity_score",
        "comment",
        "source_question",
        "source_expected_answer",
        "target_question",
        "target_expected_answer",
        "backtranslation_question",
        "backtranslation_expected_answer",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def iter_qa_items(doc: Dict[str, Any], language: str) -> Iterable[Dict[str, Any]]:
    if "holdout_cards" in doc:
        for card in doc.get("holdout_cards", []):
            for qa in card.get("qa_variants", []):
                yield {
                    "language": language,
                    "pair_id": card.get("source_pair_id", ""),
                    "topic_type": card.get("topic_type", ""),
                    "target_topic": "",
                    "neighbor_topic": "",
                    "knowledge_pair_id": qa.get("knowledge_pair_id", card.get("holdout_card_id", "")),
                    "holdout_card_id": card.get("holdout_card_id", qa.get("holdout_card_id", "")),
                    "source_card_id": card.get("source_card_id", qa.get("source_card_id", "")),
                    "relation_type": qa.get("relation_type", card.get("relation_type", "")),
                    "topic_role": qa.get("topic_role", card.get("source_topic_role", "")),
                    "variant_layer": qa.get("variant_layer", ""),
                    "topic_name": card.get("topic_name", ""),
                    "qa": qa,
                }
        return

    for topic_pair in doc.get("topic_pairs", []):
        pair_id = topic_pair.get("pair_id", "")
        for knowledge_pair in topic_pair.get("knowledge_card_pairs", []):
            for field_name, topic_role in [
                ("target_qa_variants", "target"),
                ("neighbor_qa_variants", "neighbor"),
            ]:
                card_meta = knowledge_pair.get(topic_role, {})
                for qa in knowledge_pair.get(field_name, []):
                    yield {
                        "language": language,
                        "pair_id": pair_id,
                        "topic_type": topic_pair.get("topic_type", ""),
                        "target_topic": topic_pair.get("target_topic", ""),
                        "neighbor_topic": topic_pair.get("neighbor_topic", ""),
                        "knowledge_pair_id": knowledge_pair.get("knowledge_pair_id", qa.get("knowledge_pair_id", "")),
                        "holdout_card_id": "",
                        "source_card_id": "",
                        "relation_type": qa.get("relation_type", knowledge_pair.get("relation_type", "")),
                        "topic_role": qa.get("topic_role", topic_role),
                        "variant_layer": qa.get("variant_layer", ""),
                        "topic_name": card_meta.get("topic_name", ""),
                        "qa": qa,
                    }


def english_index(doc: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for item in iter_qa_items(doc, "en"):
        qa = item["qa"]
        qa_id = qa.get("qa_id")
        if qa_id:
            index[qa_id] = item
    return index


def sample_language_items(
    doc: Dict[str, Any],
    english_by_id: Dict[str, Dict[str, Any]],
    language: str,
    sample_size: int,
    seed: int,
) -> List[Dict[str, Any]]:
    rng = random.Random(f"{seed}:{language}")
    by_pair: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    missing_source = 0
    for item in iter_qa_items(doc, language):
        qa = item["qa"]
        source_qa_id = qa.get("source_qa_id", "")
        source_item = english_by_id.get(source_qa_id)
        if not source_item:
            missing_source += 1
            continue
        item = dict(item)
        item["source_item"] = source_item
        by_pair[item["pair_id"]].append(item)

    if missing_source:
        log(f"[{language}] skipped {missing_source} items without English source_qa_id match.")

    if not by_pair:
        raise SystemExit(f"No reviewable items found for {language}.")

    selected: List[Dict[str, Any]] = []
    pair_ids = sorted(by_pair)
    base_quota = sample_size // len(pair_ids)
    for pair_id in pair_ids:
        candidates = by_pair[pair_id][:]
        rng.shuffle(candidates)
        selected.extend(candidates[:base_quota])
        by_pair[pair_id] = candidates[base_quota:]

    remaining = [item for pair_id in pair_ids for item in by_pair[pair_id]]
    rng.shuffle(remaining)
    selected.extend(remaining[: max(0, sample_size - len(selected))])
    selected = selected[:sample_size]
    rng.shuffle(selected)

    if len(selected) != sample_size:
        raise SystemExit(f"Only sampled {len(selected)} items for {language}; expected {sample_size}.")

    return selected


def review_item_payload(item: Dict[str, Any], language_name: str, ordinal: int) -> Dict[str, Any]:
    qa = item["qa"]
    source_qa = item["source_item"]["qa"]
    backtranslation = qa.get("backtranslation_en") or {}
    review_id = f"{item['language']}:{ordinal:03d}:{qa.get('qa_id', '')}"
    return {
        "id": review_id,
        "language": language_name,
        "metadata": {
            "qa_id": qa.get("qa_id", ""),
            "source_qa_id": qa.get("source_qa_id", ""),
            "pair_id": item.get("pair_id", ""),
            "knowledge_pair_id": item.get("knowledge_pair_id", ""),
            "holdout_card_id": item.get("holdout_card_id", ""),
            "source_card_id": item.get("source_card_id", ""),
            "topic_role": item.get("topic_role", ""),
            "variant_layer": item.get("variant_layer", ""),
            "relation_type": item.get("relation_type", ""),
        },
        "source": {
            "language": "English",
            "question": source_qa.get("question", ""),
            "expected_answer": source_qa.get("expected_answer", ""),
        },
        "target": {
            "language": language_name,
            "question": qa.get("question", ""),
            "expected_answer": qa.get("expected_answer", ""),
        },
        "backtranslation_en": {
            "question": backtranslation.get("question", ""),
            "expected_answer": backtranslation.get("expected_answer", ""),
        },
    }


def coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "pass", "passed", "ok"}
    return bool(value)


def normalize_reviews(model_output: Dict[str, Any]) -> List[Dict[str, Any]]:
    reviews = model_output.get("reviews")
    if isinstance(reviews, dict):
        reviews = list(reviews.values())
    if not isinstance(reviews, list):
        raise ValueError("Model output does not contain a reviews list.")

    normalized: List[Dict[str, Any]] = []
    for raw in reviews:
        if not isinstance(raw, dict):
            continue
        severity = str(raw.get("severity", "")).strip().lower() or "ok"
        if severity not in {"ok", "minor", "major"}:
            severity = "major" if not coerce_bool(raw.get("overall_pass")) else "minor"
        issue_type = str(raw.get("issue_type", "")).strip().lower() or "none"
        normalized.append(
            {
                "id": str(raw.get("id", "")).strip(),
                "overall_pass": coerce_bool(raw.get("overall_pass")),
                "severity": severity,
                "issue_type": issue_type,
                "faithfulness_score": coerce_int(raw.get("faithfulness_score")),
                "answer_accuracy_score": coerce_int(raw.get("answer_accuracy_score")),
                "fluency_score": coerce_int(raw.get("fluency_score")),
                "language_purity_score": coerce_int(raw.get("language_purity_score")),
                "comment": str(raw.get("comment", "")).strip(),
            }
        )
    return normalized


def review_batch(
    session: requests.Session,
    args: argparse.Namespace,
    language: str,
    language_name: str,
    batch_index: int,
    payload_items: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    cache_dir = Path(args.cache_dir)
    cache_path = cache_dir / f"{language}__batch_{batch_index:03d}.json"
    expected_ids = {item["id"] for item in payload_items}
    if cache_path.exists() and not args.refresh_cache:
        cached = read_json(cache_path)
        cached_ids = set(cached.get("item_ids", []))
        if cached_ids and cached_ids != expected_ids:
            log(f"[{language}] ignoring stale cache for batch {batch_index:03d}; item ids changed.")
        else:
            return cached["reviews"]

    prompt = USER_PROMPT_TEMPLATE.format(
        language_name=language_name,
        items_json=json.dumps(payload_items, ensure_ascii=False, indent=2),
    )
    last_error: Exception | None = None

    for attempt in range(1, 4):
        try:
            model_output = step6.call_json_model(session, args, SYSTEM_PROMPT, prompt)
            reviews = normalize_reviews(model_output)
            found_ids = {review["id"] for review in reviews}
            missing = sorted(expected_ids - found_ids)
            extra = sorted(found_ids - expected_ids)
            if missing or extra:
                raise ValueError(f"Review id mismatch. missing={missing[:3]} extra={extra[:3]}")
            write_json_atomic(
                cache_path,
                {
                    "prompt_version": PROMPT_VERSION,
                    "generated_at": utc_now(),
                    "language": language,
                    "language_name": language_name,
                    "batch_index": batch_index,
                    "item_ids": sorted(expected_ids),
                    "reviews": reviews,
                },
            )
            return reviews
        except Exception as exc:  # noqa: BLE001 - retry model formatting failures too.
            last_error = exc
            log(f"[{language}] batch {batch_index:03d} review attempt {attempt}/3 failed: {exc}")
    assert last_error is not None
    raise last_error


def enriched_rows(language: str, payloads: Sequence[Dict[str, Any]], reviews: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    review_by_id = {review["id"]: review for review in reviews}
    rows: List[Dict[str, Any]] = []
    for payload in payloads:
        review = review_by_id[payload["id"]]
        metadata = payload["metadata"]
        row = {
            "language": language,
            "id": payload["id"],
            "qa_id": metadata.get("qa_id", ""),
            "source_qa_id": metadata.get("source_qa_id", ""),
            "pair_id": metadata.get("pair_id", ""),
            "knowledge_pair_id": metadata.get("knowledge_pair_id", ""),
            "holdout_card_id": metadata.get("holdout_card_id", ""),
            "source_card_id": metadata.get("source_card_id", ""),
            "topic_role": metadata.get("topic_role", ""),
            "variant_layer": metadata.get("variant_layer", ""),
            "relation_type": metadata.get("relation_type", ""),
            "source_question": payload["source"].get("question", ""),
            "source_expected_answer": payload["source"].get("expected_answer", ""),
            "target_question": payload["target"].get("question", ""),
            "target_expected_answer": payload["target"].get("expected_answer", ""),
            "backtranslation_question": payload["backtranslation_en"].get("question", ""),
            "backtranslation_expected_answer": payload["backtranslation_en"].get("expected_answer", ""),
        }
        row.update(review)
        rows.append(row)
    return rows


def average(rows: Sequence[Dict[str, Any]], field: str) -> float:
    values = [coerce_int(row.get(field)) for row in rows if coerce_int(row.get(field)) > 0]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 3)


def summarize_rows(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    severity_counts = Counter(str(row.get("severity", "")) for row in rows)
    issue_counts = Counter(str(row.get("issue_type", "")) for row in rows)
    pass_count = sum(1 for row in rows if coerce_bool(row.get("overall_pass")))
    return {
        "sample_size": len(rows),
        "pass_count": pass_count,
        "pass_rate": round(pass_count / len(rows), 4) if rows else 0.0,
        "severity_counts": dict(sorted(severity_counts.items())),
        "issue_type_counts": dict(issue_counts.most_common()),
        "avg_scores": {
            "faithfulness_score": average(rows, "faithfulness_score"),
            "answer_accuracy_score": average(rows, "answer_accuracy_score"),
            "fluency_score": average(rows, "fluency_score"),
            "language_purity_score": average(rows, "language_purity_score"),
        },
    }


def main() -> None:
    args = parse_args()
    languages = [part.strip() for part in args.languages.replace(" ", ",").split(",") if part.strip()]
    step6.resolve_runtime_settings(args)
    if not args.dry_run:
        step6.ensure_api_args(args)
    args.api_key_scheduler = step6.RoundRobinKeyScheduler()

    english_doc = read_json(Path(args.english_input))
    english_by_id = english_index(english_doc)

    all_rows: List[Dict[str, Any]] = []
    by_language_summary: Dict[str, Any] = {}
    session = requests.Session()

    for language in languages:
        language_name = step6.LANGUAGE_NAMES.get(language, language)
        input_path = Path(args.input_template.format(lang=language))
        doc = read_json(input_path)
        sampled = sample_language_items(doc, english_by_id, language, args.sample_size, args.seed)
        payloads = [review_item_payload(item, language_name, ordinal + 1) for ordinal, item in enumerate(sampled)]
        log(f"[{language}] sampled {len(payloads)} items from {input_path}.")

        if args.dry_run:
            rows = enriched_rows(
                language,
                payloads,
                [
                    {
                        "id": payload["id"],
                        "overall_pass": True,
                        "severity": "ok",
                        "issue_type": "none",
                        "faithfulness_score": 5,
                        "answer_accuracy_score": 5,
                        "fluency_score": 5,
                        "language_purity_score": 5,
                        "comment": "dry run",
                    }
                    for payload in payloads
                ],
            )
        else:
            rows = []
            for batch_index, start in enumerate(range(0, len(payloads), args.batch_size), start=1):
                batch = payloads[start : start + args.batch_size]
                log(f"[{language}] reviewing batch {batch_index:03d} ({len(batch)} items).")
                reviews = review_batch(session, args, language, language_name, batch_index, batch)
                rows.extend(enriched_rows(language, batch, reviews))

        all_rows.extend(rows)
        by_language_summary[language] = summarize_rows(rows)
        log(f"[{language}] pass_rate={by_language_summary[language]['pass_rate']:.2%}")

    payload = {
        "step": "step6_translation_quality_review",
        "prompt_version": PROMPT_VERSION,
        "generated_at": utc_now(),
        "judge_model": args.model,
        "api_base": step6.normalize_api_base(args.api_base) if args.api_base else "",
        "config": {
            "english_input": args.english_input,
            "input_template": args.input_template,
            "languages": languages,
            "sample_size_per_language": args.sample_size,
            "seed": args.seed,
            "batch_size": args.batch_size,
            "aliases_ignored": True,
        },
        "summary": {
            "overall": summarize_rows(all_rows),
            "by_language": by_language_summary,
        },
        "reviews": all_rows,
    }

    write_json_atomic(Path(args.output), payload)
    write_tsv(Path(args.tsv_output), all_rows)
    log(f"Wrote {args.output}")
    log(f"Wrote {args.tsv_output}")


if __name__ == "__main__":
    main()
