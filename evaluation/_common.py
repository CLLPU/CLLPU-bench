"""Shared input, normalization, and aggregation for CLLPU evaluation scripts."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any, Callable, Iterable


LANGUAGES = ["ar", "bn", "de", "en", "es", "fr", "ja", "sw", "th", "zh"]
ROLES = ("forget", "retain")

FIELD_ALIASES = {
    "setting": ("setting", "scenario", "dataset_family"),
    "method": ("method", "model_type", "checkpoint_method"),
    "source_language": ("source_language", "source_lang", "s_language"),
    "evaluation_language": (
        "evaluation_language",
        "target_language",
        "language",
        "t_language",
    ),
    "role": ("role", "topic_role"),
    "knowledge_id": ("knowledge_id", "knowledge_pair_id", "card_id"),
    "variant_layer": ("variant_layer", "variant", "qa_variant"),
    "qa_id": ("qa_id", "id"),
    "prediction": ("prediction", "generation", "generated_answer", "response"),
    "expected_answer": ("expected_answer", "reference", "answer"),
    "answer_aliases": ("answer_aliases", "aliases"),
    "question": ("question", "prompt"),
}


def add_common_arguments(parser: argparse.ArgumentParser, metric: str) -> None:
    parser.add_argument("input", type=Path, help="Generation records in JSONL or JSON.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation/outputs") / metric,
        help="Directory for numeric outputs. No figures are generated.",
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        default=LANGUAGES,
        help="Ordered language list used in matrix JSON output.",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Allow missing source/evaluation-language cells.",
    )
    parser.add_argument(
        "--use-aliases",
        action="store_true",
        help="Also score answer_aliases; the paper-compatible default uses expected_answer only.",
    )


def _first(record: dict[str, Any], canonical: str, default: Any = None) -> Any:
    for key in FIELD_ALIASES[canonical]:
        if key in record and record[key] is not None:
            return record[key]
    return default


def _normalize_role(value: Any) -> str:
    role = str(value or "").strip().lower()
    mapping = {
        "target": "forget",
        "forget": "forget",
        "f": "forget",
        "neighbor": "retain",
        "retain": "retain",
        "r": "retain",
    }
    if role not in mapping:
        raise ValueError(f"Unsupported role {value!r}; expected target/forget or neighbor/retain")
    return mapping[role]


def _normalize_variant(value: Any) -> str:
    variant = str(value or "").strip().lower()
    if variant.startswith("core"):
        return "core"
    if variant.startswith("surface"):
        return "surface"
    raise ValueError(f"Unsupported variant_layer {value!r}; expected core or surface")


def canonicalize_record(record: dict[str, Any], line_number: int) -> dict[str, Any]:
    required = (
        "method",
        "source_language",
        "evaluation_language",
        "role",
        "knowledge_id",
        "variant_layer",
        "prediction",
        "expected_answer",
    )
    values = {key: _first(record, key) for key in required}
    missing = [key for key, value in values.items() if value is None or value == ""]
    if missing:
        raise ValueError(f"Record {line_number}: missing fields {missing}")

    aliases = _first(record, "answer_aliases", [])
    if aliases is None:
        aliases = []
    if isinstance(aliases, str):
        aliases = [aliases]
    if not isinstance(aliases, list):
        raise ValueError(f"Record {line_number}: answer_aliases must be a list or string")

    return {
        **record,
        "setting": str(_first(record, "setting", "unspecified")),
        "method": str(values["method"]),
        "source_language": str(values["source_language"]).lower(),
        "evaluation_language": str(values["evaluation_language"]).lower(),
        "role": _normalize_role(values["role"]),
        "knowledge_id": str(values["knowledge_id"]),
        "variant_layer": _normalize_variant(values["variant_layer"]),
        "qa_id": str(_first(record, "qa_id", f"record-{line_number}")),
        "prediction": str(values["prediction"]),
        "expected_answer": str(values["expected_answer"]),
        "answer_aliases": [str(item) for item in aliases if str(item).strip()],
        "question": str(_first(record, "question", "")),
    }


def read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".jsonl":
        records = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if line.strip():
                    records.append(canonicalize_record(json.loads(line), line_number))
        return records

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        raw_records = payload
    elif isinstance(payload, dict):
        raw_records = payload.get("records") or payload.get("generations")
        if not isinstance(raw_records, list):
            raise ValueError("JSON input must be a list or contain records/generations list")
    else:
        raise ValueError("JSON input must contain generation records")
    return [canonicalize_record(record, i) for i, record in enumerate(raw_records, 1)]


def normalize_answer(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    chars: list[str] = []
    for char in text:
        category = unicodedata.category(char)
        if category.startswith(("P", "S")):
            chars.append(" ")
        else:
            chars.append(char)
    return re.sub(r"\s+", " ", "".join(chars)).strip()


def tokenize_mixed_unicode(text: str) -> list[str]:
    """Deterministic tokenizer suitable for short multilingual answers."""
    text = unicodedata.normalize("NFKC", text).casefold()
    tokens: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            tokens.append("".join(current))
            current.clear()

    for char in text:
        codepoint = ord(char)
        is_char_token_script = (
            0x0E00 <= codepoint <= 0x0E7F  # Thai
            or 0x3040 <= codepoint <= 0x30FF  # Hiragana/Katakana
            or 0x3400 <= codepoint <= 0x9FFF  # CJK
            or 0xAC00 <= codepoint <= 0xD7AF  # Hangul
        )
        category = unicodedata.category(char)
        if is_char_token_script and not category.startswith(("P", "S", "Z")):
            flush()
            tokens.append(char)
        elif category[0] in {"L", "N", "M"}:
            current.append(char)
        else:
            flush()
    flush()
    return tokens


def rouge_l_f1(prediction: str, reference: str) -> float:
    predicted = tokenize_mixed_unicode(prediction)
    expected = tokenize_mixed_unicode(reference)
    if not predicted or not expected:
        return 1.0 if predicted == expected else 0.0
    previous = [0] * (len(expected) + 1)
    for predicted_token in predicted:
        current = [0]
        for index, expected_token in enumerate(expected, 1):
            if predicted_token == expected_token:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(current[-1], previous[index]))
        previous = current
    lcs = previous[-1]
    precision = lcs / len(predicted)
    recall = lcs / len(expected)
    return 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)


def best_reference_score(
    record: dict[str, Any],
    scorer: Callable[[str, str], float],
    use_aliases: bool = False,
) -> float:
    references = [record["expected_answer"]]
    if use_aliases:
        references.extend(record["answer_aliases"])
    return max(scorer(record["prediction"], reference) for reference in references)


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _mean(values: Iterable[float]) -> float | None:
    materialized = list(values)
    return fmean(materialized) if materialized else None


def aggregate_and_write(
    records: list[dict[str, Any]],
    scores: list[float],
    metric: str,
    output_dir: Path,
    languages: list[str],
    allow_incomplete: bool,
) -> None:
    if len(records) != len(scores):
        raise ValueError("Record/score count mismatch")
    if not records:
        raise ValueError("No generation records found")
    if any(not math.isfinite(score) for score in scores):
        raise ValueError("Metric produced a non-finite score")

    output_dir.mkdir(parents=True, exist_ok=True)
    per_qa_rows: list[dict[str, Any]] = []
    knowledge_groups: dict[tuple[str, ...], list[float]] = defaultdict(list)
    qa_counts: dict[tuple[str, ...], int] = defaultdict(int)

    for record, score in zip(records, scores):
        row = {
            "setting": record["setting"],
            "metric": metric,
            "method": record["method"],
            "source_language": record["source_language"],
            "evaluation_language": record["evaluation_language"],
            "role": record["role"],
            "knowledge_id": record["knowledge_id"],
            "variant_layer": record["variant_layer"],
            "qa_id": record["qa_id"],
            "score": score,
        }
        per_qa_rows.append(row)
        key = (
            record["setting"],
            record["method"],
            record["source_language"],
            record["evaluation_language"],
            record["role"],
            record["knowledge_id"],
        )
        knowledge_groups[key].append(score)
        qa_counts[key] += 1

    with (output_dir / "per_qa.jsonl").open("w", encoding="utf-8") as handle:
        for row in per_qa_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    per_knowledge_rows: list[dict[str, Any]] = []
    cell_groups: dict[tuple[str, ...], list[float]] = defaultdict(list)
    cell_qa_counts: dict[tuple[str, ...], int] = defaultdict(int)
    for key, values in sorted(knowledge_groups.items()):
        setting, method, source, evaluation, role, knowledge_id = key
        value = fmean(values)
        per_knowledge_rows.append(
            {
                "setting": setting,
                "metric": metric,
                "method": method,
                "source_language": source,
                "evaluation_language": evaluation,
                "role": role,
                "knowledge_id": knowledge_id,
                "qa_count": qa_counts[key],
                "value": value,
            }
        )
        cell_key = (setting, method, source, evaluation, role)
        cell_groups[cell_key].append(value)
        cell_qa_counts[cell_key] += qa_counts[key]

    _write_csv(
        output_dir / "per_knowledge.csv",
        per_knowledge_rows,
        [
            "setting",
            "metric",
            "method",
            "source_language",
            "evaluation_language",
            "role",
            "knowledge_id",
            "qa_count",
            "value",
        ],
    )

    heatmap_rows: list[dict[str, Any]] = []
    for key, values in sorted(cell_groups.items()):
        setting, method, source, evaluation, role = key
        heatmap_rows.append(
            {
                "setting": setting,
                "metric": metric,
                "method": method,
                "role": role,
                "source_language": source,
                "evaluation_language": evaluation,
                "value": fmean(values),
                "knowledge_count": len(values),
                "qa_count": cell_qa_counts[key],
            }
        )
    _write_csv(
        output_dir / "heatmap_values.csv",
        heatmap_rows,
        [
            "setting",
            "metric",
            "method",
            "role",
            "source_language",
            "evaluation_language",
            "value",
            "knowledge_count",
            "qa_count",
        ],
    )

    dimensions = sorted(
        {(row["setting"], row["method"], row["role"]) for row in heatmap_rows}
    )
    matrix_payload: dict[str, Any] = {
        "metric": metric,
        "languages": languages,
        "matrices": [],
    }
    overall_rows: list[dict[str, Any]] = []

    for setting, method, role in dimensions:
        lookup = {
            (row["source_language"], row["evaluation_language"]): row["value"]
            for row in heatmap_rows
            if row["setting"] == setting
            and row["method"] == method
            and row["role"] == role
        }
        observed_languages = {
            language for pair in lookup for language in pair
        }
        unsupported = sorted(observed_languages.difference(languages))
        if unsupported:
            raise ValueError(
                f"{setting}/{method}/{role} contains languages not listed in "
                f"--languages: {unsupported}"
            )
        active_languages = languages
        missing = [
            (source, evaluation)
            for source in active_languages
            for evaluation in active_languages
            if (source, evaluation) not in lookup
        ]
        if missing and not allow_incomplete:
            preview = ", ".join(f"{s}->{t}" for s, t in missing[:8])
            raise ValueError(
                f"Incomplete {setting}/{method}/{role} matrix: {len(missing)} "
                f"missing cells ({preview}). Use --allow-incomplete for partial runs."
            )

        matrix_payload["matrices"].append(
            {
                "setting": setting,
                "method": method,
                "role": role,
                "values": [
                    [lookup.get((source, evaluation)) for evaluation in languages]
                    for source in languages
                ],
            }
        )
        source_values = [
            lookup[(language, language)]
            for language in languages
            if (language, language) in lookup
        ]
        per_source_cross = []
        for source in languages:
            values = [
                lookup[(source, evaluation)]
                for evaluation in languages
                if evaluation != source and (source, evaluation) in lookup
            ]
            if values:
                per_source_cross.append(fmean(values))
        all_values = list(lookup.values())
        overall_rows.append(
            {
                "setting": setting,
                "metric": metric,
                "method": method,
                "role": role,
                "source": _mean(source_values),
                "cross": _mean(per_source_cross),
                "overall": _mean(all_values),
                "cell_count": len(all_values),
            }
        )

    (output_dir / "heatmap_matrices.json").write_text(
        json.dumps(matrix_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_csv(
        output_dir / "overall.csv",
        overall_rows,
        [
            "setting",
            "metric",
            "method",
            "role",
            "source",
            "cross",
            "overall",
            "cell_count",
        ],
    )
    (output_dir / "overall.json").write_text(
        json.dumps(
            {"metric": metric, "results": overall_rows},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def run_local_metric(
    args: argparse.Namespace,
    metric: str,
    scorer: Callable[[dict[str, Any]], float],
) -> None:
    records = read_records(args.input)
    scores = [float(scorer(record)) for record in records]
    aggregate_and_write(
        records,
        scores,
        metric,
        args.output_dir,
        args.languages,
        args.allow_incomplete,
    )
    print(f"Wrote {metric} numeric results for {len(records)} QAs to {args.output_dir}")
