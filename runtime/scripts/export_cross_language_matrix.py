#!/usr/bin/env python3
"""Export strict source-by-evaluation-language absolute metric tables."""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Mapping, Sequence


LANGUAGES = ("ar", "bn", "de", "en", "es", "fr", "ja", "sw", "th", "zh")
METHODS = ("ga", "gd", "npo", "simnpo", "drnpo", "drsimnpo")
EXPECTED_VARIANT_WEIGHTS = {"core": 0.25, "surface": 0.75}


@dataclass(frozen=True)
class SummaryInput:
    checkpoint_id: str
    source_language: str
    summary_path: Path


def comma_list(value: str, *, allowed: Sequence[str], option: str) -> tuple[str, ...]:
    items = tuple(item.strip().lower() for item in value.split(",") if item.strip())
    if not items:
        raise argparse.ArgumentTypeError(f"{option} cannot be empty")
    if len(set(items)) != len(items):
        raise argparse.ArgumentTypeError(f"{option} contains duplicate values: {value}")
    invalid = sorted(set(items).difference(allowed))
    if invalid:
        raise argparse.ArgumentTypeError(f"Invalid {option}: {','.join(invalid)}")
    return items


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Missing evaluation summary: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in evaluation summary {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Evaluation summary must be a JSON object: {path}")
    return payload


def resolve_inputs(
    *,
    input_root: Path | None,
    input_index: Path | None,
    path_template: str,
    method: str,
    source_languages: Sequence[str] | None,
) -> tuple[SummaryInput, ...]:
    requested = set(source_languages) if source_languages is not None else None
    resolved: list[SummaryInput] = []
    checkpoint_ids: set[str] = set()
    if input_index is not None:
        index_path = input_index.resolve()
        with index_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"method", "source_language", "summary_path"}
            missing = required.difference(reader.fieldnames or ())
            if missing:
                raise ValueError(f"Input index is missing columns: {sorted(missing)}")
            for line_number, row in enumerate(reader, start=2):
                source = str(row["source_language"]).strip().lower()
                if source not in LANGUAGES:
                    raise ValueError(
                        f"Invalid source language at {index_path}:{line_number}: {source!r}"
                    )
                if requested is not None and source not in requested:
                    raise ValueError(
                        f"Unexpected source language at {index_path}:{line_number}: {source!r}"
                    )
                row_method = str(row["method"]).strip().lower()
                if row_method != method:
                    raise ValueError(
                        f"Input index method mismatch at {index_path}:{line_number}: "
                        f"expected {method!r}, got {row_method!r}"
                    )
                raw_path = str(row["summary_path"]).strip()
                if not raw_path:
                    raise ValueError(f"Empty summary_path at {index_path}:{line_number}")
                value = Path(raw_path).expanduser()
                summary_path = (
                    value.resolve()
                    if value.is_absolute()
                    else (index_path.parent / value).resolve()
                )
                checkpoint_id = str(row.get("checkpoint_id") or source).strip()
                if not checkpoint_id:
                    raise ValueError(f"Empty checkpoint_id at {index_path}:{line_number}")
                if checkpoint_id in checkpoint_ids:
                    raise ValueError(
                        f"Duplicate checkpoint_id at {index_path}:{line_number}: "
                        f"{checkpoint_id!r}; assign a unique checkpoint_id to every row"
                    )
                checkpoint_ids.add(checkpoint_id)
                resolved.append(
                    SummaryInput(
                        checkpoint_id=checkpoint_id,
                        source_language=source,
                        summary_path=summary_path,
                    )
                )
    else:
        if input_root is None:
            raise ValueError("Either --input-root or --input-index is required")
        if "{method}" not in path_template:
            raise ValueError("--path-template must contain the {method} placeholder")
        selected_sources = tuple(source_languages or LANGUAGES)
        root = input_root.resolve()
        for source in selected_sources:
            try:
                relative = path_template.format(method=method, source_language=source)
            except (KeyError, ValueError) as exc:
                raise ValueError(f"Invalid --path-template: {path_template!r}") from exc
            path = Path(relative)
            if path.is_absolute():
                raise ValueError("--path-template must render a path relative to --input-root")
            resolved.append(
                SummaryInput(
                    checkpoint_id=source,
                    source_language=source,
                    summary_path=(root / path).resolve(),
                )
            )

    if not resolved:
        raise ValueError("Input mapping contains no checkpoint summaries")
    if requested is not None:
        present_sources = {item.source_language for item in resolved}
        missing_sources = sorted(requested.difference(present_sources))
        if missing_sources:
            raise ValueError(f"Input mapping is missing source languages: {missing_sources}")
    by_path: dict[Path, list[str]] = {}
    for item in resolved:
        by_path.setdefault(item.summary_path, []).append(item.checkpoint_id)
    duplicates = {str(path): sources for path, sources in by_path.items() if len(sources) > 1}
    if duplicates:
        raise ValueError(f"Multiple source checkpoints reference the same summary: {duplicates}")
    return tuple(resolved)


def validate_dataset(summary: Mapping[str, Any], *, dataset: str, source: str, path: Path) -> None:
    families = set((summary.get("by_dataset_family", {}) or {}).keys())
    valid_families = {"", "common"} if dataset == "common" else {"culture_specific"}
    if not families or not families.issubset(valid_families):
        raise ValueError(
            f"{path}: expected only dataset_family values {sorted(valid_families)}, "
            f"got {sorted(families)}"
        )
    if dataset == "culture":
        origins = set((summary.get("by_culture_origin", {}) or {}).keys())
        if origins != {source}:
            raise ValueError(
                f"{path}: expected only culture_origin={source!r}, got {sorted(origins)}"
            )


def validate_weights(summary: Mapping[str, Any], *, path: Path) -> None:
    definition = (summary.get("metric_definitions", {}) or {}).get("A_current_role", {}) or {}
    weights = definition.get("variant_weights", {}) or {}
    if set(weights) != set(EXPECTED_VARIANT_WEIGHTS) or any(
        not math.isclose(float(weights[name]), expected, rel_tol=0.0, abs_tol=1e-12)
        for name, expected in EXPECTED_VARIANT_WEIGHTS.items()
    ):
        raise ValueError(
            f"{path}: expected variant weights {EXPECTED_VARIANT_WEIGHTS}, got {weights}"
        )


def numeric(value: Any, *, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise ValueError(f"Missing numeric value for {label}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Non-finite numeric value for {label}: {value!r}")
    return result


def validate_weighted_entry(
    entry: Mapping[str, Any], *, metric_suffix: str, label: str
) -> float:
    weights = entry.get("variant_weights", {}) or {}
    if set(weights) != set(EXPECTED_VARIANT_WEIGHTS) or any(
        not math.isclose(float(weights[name]), expected, rel_tol=0.0, abs_tol=1e-12)
        for name, expected in EXPECTED_VARIANT_WEIGHTS.items()
    ):
        raise ValueError(f"{label}: invalid entry variant weights: {weights}")
    variants = entry.get("variants", {}) or {}
    if set(variants) != {"core", "surface"}:
        raise ValueError(f"{label}: expected core and surface variants")
    core_count = int((variants["core"] or {}).get("count", -1))
    surface_count = int((variants["surface"] or {}).get("count", -1))
    if core_count <= 0 or surface_count != 3 * core_count:
        raise ValueError(
            f"{label}: expected positive core count and surface_count=3*core_count, "
            f"got core={core_count}, surface={surface_count}"
        )
    variant_field = f"A_current_v_{metric_suffix}"
    core = numeric((variants["core"] or {}).get(variant_field), label=f"{label}:core")
    surface = numeric(
        (variants["surface"] or {}).get(variant_field), label=f"{label}:surface"
    )
    weighted = numeric(entry.get(f"A_current_{metric_suffix}"), label=f"{label}:weighted")
    expected = 0.25 * core + 0.75 * surface
    if not math.isclose(weighted, expected, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError(
            f"{label}: stored weighted score {weighted} does not equal "
            f"0.25*core + 0.75*surface = {expected}"
        )
    return weighted


def extract_rows(
    inputs: Sequence[SummaryInput],
    *,
    dataset: str,
    experiment: str,
    method: str,
    language_scope: str,
    metric: str,
    topic_role: str,
    variant: str,
) -> list[dict[str, Any]]:
    if not metric.startswith("a_"):
        raise ValueError("--metric must be an accessibility metric name beginning with 'a_'")
    suffix = metric.removeprefix("a_")
    rows: list[dict[str, Any]] = []
    expected_rows = 0
    for item in inputs:
        source = item.source_language
        path = item.summary_path
        summary = read_json(path)
        validate_dataset(summary, dataset=dataset, source=source, path=path)
        validate_weights(summary, path=path)
        role_entries = summary.get("by_role_language", {}) or {}
        available_languages = {
            str(entry.get("language"))
            for entry in role_entries.values()
            if isinstance(entry, Mapping) and entry.get("topic_role") == topic_role
        }
        evaluation_languages = (source,) if language_scope == "source" else LANGUAGES
        missing_languages = set(evaluation_languages).difference(available_languages)
        if missing_languages:
            raise ValueError(
                f"{path}: missing {topic_role} aggregates for languages "
                f"{sorted(missing_languages)}; available={sorted(available_languages)}"
            )
        expected_rows += len(evaluation_languages)
        for evaluation_language in evaluation_languages:
            if variant == "weighted":
                key = f"{evaluation_language}|{topic_role}"
                entry = role_entries.get(key)
                field = f"A_current_{suffix}"
            else:
                key = f"{evaluation_language}|{topic_role}|{variant}"
                entry = (summary.get("by_role_language_variant", {}) or {}).get(key)
                field = f"A_current_v_{suffix}"
            if not isinstance(entry, Mapping):
                raise ValueError(f"{path}: missing aggregate {key!r}")
            if variant == "weighted":
                score = validate_weighted_entry(
                    entry, metric_suffix=suffix, label=f"{path}:{key}"
                )
            else:
                score = numeric(entry.get(field), label=f"{path}:{key}:{field}")
            rows.append(
                {
                    "experiment": experiment,
                    "dataset": dataset,
                    "method": method,
                    "checkpoint_id": item.checkpoint_id,
                    "source_language": source,
                    "evaluation_language": evaluation_language,
                    "topic_role": topic_role,
                    "metric": metric,
                    "variant": variant,
                    "score": score,
                    "summary_path": str(path),
                }
            )
    if len(rows) != expected_rows:
        raise AssertionError(f"Produced {len(rows)} rows, expected {expected_rows}")
    return rows


def write_csv_atomic(
    path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as tmp:
        writer = csv.DictWriter(tmp, fieldnames=list(fieldnames))
        writer.writeheader()
        writer.writerows(rows)
        temporary = Path(tmp.name)
    temporary.replace(path)


def write_matrices(
    directory: Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    method: str,
    inputs: Sequence[SummaryInput],
) -> None:
    index = {
        (
            str(row["method"]),
            str(row["checkpoint_id"]),
            str(row["evaluation_language"]),
        ): row["score"]
        for row in rows
    }
    fields = ("checkpoint_id", "source_language", *LANGUAGES)
    matrix_rows = [
        {
            "checkpoint_id": item.checkpoint_id,
            "source_language": item.source_language,
            **{
                target: index.get((method, item.checkpoint_id, target), "")
                for target in LANGUAGES
            },
        }
        for item in inputs
    ]
    write_csv_atomic(directory / f"{method}.csv", matrix_rows, fields)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    source = result.add_mutually_exclusive_group(required=True)
    source.add_argument("--input-root", type=Path)
    source.add_argument(
        "--input-index",
        type=Path,
        help=(
            "CSV with method, source_language, and summary_path; optional "
            "checkpoint_id column"
        ),
    )
    result.add_argument(
        "--path-template",
        default="{source_language}/{method}/MULTILINGUAL_SUMMARY.json",
        help="Relative layout below --input-root",
    )
    result.add_argument("--output", required=True, type=Path)
    result.add_argument("--matrix-output-dir", type=Path, default=None)
    result.add_argument("--experiment", required=True)
    result.add_argument("--dataset", choices=("common", "culture"), required=True)
    result.add_argument("--method", choices=METHODS, required=True)
    result.add_argument("--metric", default="a_rouge")
    result.add_argument("--topic-role", choices=("target", "neighbor"), default="target")
    result.add_argument("--variant", choices=("weighted", "core", "surface"), default="weighted")
    result.add_argument(
        "--source-languages",
        default=None,
        help="Comma-separated checkpoint source languages; input-index rows are used if omitted",
    )
    result.add_argument(
        "--language-scope",
        choices=("source", "all", "source+cross"),
        default="all",
        help="Export only each source diagonal or every source+cross evaluation language",
    )
    result.add_argument("--overwrite", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    requested_sources = (
        comma_list(args.source_languages, allowed=LANGUAGES, option="source languages")
        if args.source_languages is not None
        else None
    )
    inputs = resolve_inputs(
        input_root=args.input_root,
        input_index=args.input_index,
        path_template=args.path_template,
        method=args.method,
        source_languages=requested_sources,
    )
    rows = extract_rows(
        inputs,
        dataset=args.dataset,
        experiment=args.experiment,
        method=args.method,
        language_scope="source" if args.language_scope == "source" else "all",
        metric=args.metric,
        topic_role=args.topic_role,
        variant=args.variant,
    )
    fields = (
        "experiment",
        "dataset",
        "method",
        "checkpoint_id",
        "source_language",
        "evaluation_language",
        "topic_role",
        "metric",
        "variant",
        "score",
        "summary_path",
    )
    output = args.output.resolve()
    matrix_dir = args.matrix_output_dir.resolve() if args.matrix_output_dir is not None else None
    output_targets = [output]
    if matrix_dir is not None:
        output_targets.append(matrix_dir / f"{args.method}.csv")
    existing = [path for path in output_targets if path.exists()]
    if existing and not args.overwrite:
        raise SystemExit(f"Refusing to overwrite existing outputs: {existing}")
    write_csv_atomic(output, rows, fields)
    if matrix_dir is not None:
        write_matrices(
            matrix_dir,
            rows,
            method=args.method,
            inputs=inputs,
        )
    print(f"COMPLETE rows={len(rows)} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
