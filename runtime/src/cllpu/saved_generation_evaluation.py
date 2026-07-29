"""Score Exact Match or ROUGE-L from completed benchmark generations."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from rouge_score import rouge_scorer

from cllpu.evals.metrics.multilingual import (
    DEFAULT_VARIANT_WEIGHTS,
    MixedUnicodeTokenizer,
    _score_answer,
    build_accessibility_summary,
)
from cllpu.evals.multilingual_outputs import (
    build_eval_payload,
    save_multilingual_eval_outputs,
    write_json_atomic,
)


METRIC_NAMES = {"em": "a_exact", "rouge": "a_rouge"}
REQUIRED_FIELDS = (
    "qa_id",
    "language",
    "knowledge_pair_id",
    "topic_role",
    "variant_layer",
    "expected_answer",
    "cleaned_generation",
)


def resolve_input(value: Path) -> Path:
    path = value / "generations.jsonl" if value.is_dir() else value
    if not path.is_file():
        raise FileNotFoundError(f"Missing generations JSONL: {path}")
    return path.resolve()


def read_and_validate_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_qa_ids: set[str] = set()
    form_counts: dict[tuple[str, str, str], dict[str, int]] = {}

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path}:{line_number}: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"Record in {path}:{line_number} must be an object")
            missing = [field for field in REQUIRED_FIELDS if field not in record]
            if missing:
                raise ValueError(f"Missing fields in {path}:{line_number}: {missing}")

            qa_id = str(record["qa_id"])
            if not qa_id:
                raise ValueError(f"Empty qa_id in {path}:{line_number}")
            if qa_id in seen_qa_ids:
                raise ValueError(f"Duplicate qa_id in {path}: {qa_id}")
            seen_qa_ids.add(qa_id)

            role = str(record["topic_role"])
            variant = str(record["variant_layer"])
            if role not in {"target", "neighbor"}:
                raise ValueError(f"Invalid topic_role for qa_id={qa_id!r}: {role!r}")
            if variant not in {"core", "surface"}:
                raise ValueError(f"Invalid variant_layer for qa_id={qa_id!r}: {variant!r}")
            key = (str(record["language"]), str(record["knowledge_pair_id"]), role)
            counts = form_counts.setdefault(key, {"core": 0, "surface": 0})
            counts[variant] += 1
            records.append(record)

    if not records:
        raise ValueError(f"No generation records found in {path}")
    invalid = [key for key, counts in form_counts.items() if counts != {"core": 1, "surface": 3}]
    if invalid:
        raise ValueError(
            "Saved generations must contain one core and three surface forms for every "
            f"language/knowledge/role group; invalid groups include {invalid[:5]}"
        )
    return records


def score_records(records: Sequence[Mapping[str, Any]], metric_name: str) -> list[dict[str, Any]]:
    scorer = rouge_scorer.RougeScorer(
        ["rougeL"],
        use_stemmer=True,
        tokenizer=MixedUnicodeTokenizer(use_stemmer=True),
    )
    scored: list[dict[str, Any]] = []
    for source in records:
        values = _score_answer(
            scorer,
            source["cleaned_generation"],
            source["expected_answer"],
        )
        record = dict(source)
        metrics = dict(record.get("metrics", {}) or {})
        metrics[metric_name] = values[metric_name]
        record["metrics"] = metrics
        scored.append(record)
    return scored


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parser_for(metric: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            f"Compute {metric.upper()} from an existing benchmark generations.jsonl; "
            "this command never loads the evaluated model or generates responses."
        )
    )
    parser.add_argument("input", type=Path, help="Evaluation directory or generations.jsonl")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(metric: str) -> int:
    args = parser_for(metric).parse_args()
    metric_name = METRIC_NAMES[metric]
    try:
        input_path = resolve_input(args.input)
        records = read_and_validate_records(input_path)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    output_dir = args.output_dir.resolve()
    if output_dir == input_path.parent:
        raise SystemExit("--output-dir must differ from the source evaluation directory")
    if output_dir.exists() and any(output_dir.iterdir()) and not args.overwrite:
        raise SystemExit(f"Output directory is not empty: {output_dir}")

    scored = score_records(records, metric_name)
    summary = build_accessibility_summary(
        scored,
        (metric_name,),
        variant_weights=DEFAULT_VARIANT_WEIGHTS,
        renormalize_variant_weights=True,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    save_multilingual_eval_outputs(
        output_dir,
        scored,
        metric_names=(metric_name,),
        eval_payload=build_eval_payload(scored, (metric_name,)),
        summary_payload=summary,
    )
    write_json_atomic(
        output_dir / "SAVED_GENERATION_EVALUATION_PROTOCOL.json",
        {
            "protocol_version": "saved_generation_absolute_evaluation_v1",
            "input": str(input_path),
            "input_sha256": file_sha256(input_path),
            "record_count": len(scored),
            "metric": metric_name,
            "candidate_field": "cleaned_generation",
            "reference_field": "expected_answer",
            "variant_weights": DEFAULT_VARIANT_WEIGHTS,
            "runs_model_generation": False,
        },
    )
    print(f"Wrote {metric_name} evaluation for {len(scored)} records to {output_dir}")
    return 0
