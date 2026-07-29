"""Utilities for saving multilingual evaluation raw generations and summaries."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

def normalize_answer(text: Any) -> str:
    """Keep OP-style post-processed text without custom answer normalization.

    The multilingual v1 metrics intentionally avoid lowercasing, punctuation
    stripping, article removal, prefix removal, and alias matching. Generation
    post-processing such as special-token cleanup, tokenization-space cleanup,
    stopword truncation, and strip should happen before this helper receives
    ``raw_generation``; this function only applies a final ``strip`` for schema
    compatibility with the existing ``normalized_generation`` field.
    """
    return str(text or "").strip()


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2, sort_keys=True)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def write_jsonl_atomic(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        for record in records:
            json.dump(dict(record), tmp, ensure_ascii=False, sort_keys=True)
            tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def build_generation_record(
    metadata: Mapping[str, Any],
    *,
    prompt: str = "",
    messages: Optional[Sequence[Mapping[str, str]]] = None,
    raw_generation: str,
    cleaned_generation: Optional[str] = None,
    input_sequence_length: Optional[int] = None,
    prompt_token_count: Optional[int] = None,
    generated_token_ids: Optional[Sequence[int]] = None,
    decode_args: Optional[Mapping[str, Any]] = None,
    generation_args: Optional[Mapping[str, Any]] = None,
    metrics: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a raw generation record that can be reused for future metrics."""
    normalized_generation = normalize_answer(
        cleaned_generation if cleaned_generation is not None else raw_generation
    )
    record = dict(metadata)
    record.update(
        {
            "prompt": prompt,
            "messages": [dict(message) for message in messages] if messages else [],
            "input_sequence_length": input_sequence_length,
            "prompt_token_count": prompt_token_count,
            "generated_token_ids": list(generated_token_ids or []),
            "decode_args": dict(decode_args or {}),
            "raw_generation": raw_generation,
            "cleaned_generation": normalized_generation,
            "normalized_generation": normalized_generation,
            "generation_args": dict(generation_args or {}),
            "metrics": dict(metrics or {}),
        }
    )
    return record


def metric_values_by_qa_id(records: Iterable[Mapping[str, Any]], metric_name: str) -> Dict[str, Any]:
    values = {}
    for record in records:
        metrics = record.get("metrics", {}) or {}
        if metric_name in metrics:
            values[str(record["qa_id"])] = metrics[metric_name]
    return values


def mean_numeric(values: Iterable[Any]) -> Optional[float]:
    numeric = [float(value) for value in values if value is not None]
    if not numeric:
        return None
    return sum(numeric) / len(numeric)


def build_eval_payload(records: Sequence[Mapping[str, Any]], metric_names: Sequence[str]) -> Dict[str, Any]:
    metrics = {}
    for metric_name in metric_names:
        values = metric_values_by_qa_id(records, metric_name)
        metrics[metric_name] = {
            "value_by_qa_id": values,
            "agg_value": mean_numeric(values.values()),
        }
    return {"metrics": metrics}


def summarize_by(records: Sequence[Mapping[str, Any]], group_key: str, metric_names: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        groups[str(record.get(group_key, ""))].append(record)

    summary = {}
    for group_value, group_records in sorted(groups.items()):
        entry: Dict[str, Any] = {"count": len(group_records)}
        for metric_name in metric_names:
            values = [((record.get("metrics", {}) or {}).get(metric_name)) for record in group_records]
            entry[f"{metric_name}_mean"] = mean_numeric(values)
        summary[group_value] = entry
    return summary


def build_summary_payload(
    records: Sequence[Mapping[str, Any]],
    metric_names: Sequence[str],
    group_keys: Sequence[str] = ("language", "topic_role", "variant_layer", "pair_id", "relation_type"),
) -> Dict[str, Any]:
    payload = {"overall": {"count": len(records)}}
    for metric_name in metric_names:
        values = [((record.get("metrics", {}) or {}).get(metric_name)) for record in records]
        payload["overall"][f"{metric_name}_mean"] = mean_numeric(values)
    for group_key in group_keys:
        payload[f"by_{group_key}"] = summarize_by(records, group_key, metric_names)
    return payload


def _role_report_entry(
    summary_payload: Mapping[str, Any],
    language: str,
    topic_role: str,
    metric_names: Sequence[str],
) -> Dict[str, Any]:
    by_variant = summary_payload.get("by_role_language_variant", {}) or {}
    weighted = (summary_payload.get("by_role_language", {}) or {}).get(f"{language}|{topic_role}", {}) or {}

    entry: Dict[str, Any] = {
        "language": language,
        "topic_role": topic_role,
        "count": weighted.get("count"),
    }
    for metric_name in metric_names:
        if not metric_name.startswith("a_"):
            raise ValueError(f"Accessibility metric must start with 'a_': {metric_name}")
        metric_suffix = metric_name.removeprefix("a_")
        entry[f"{metric_name}_mean"] = weighted.get(f"{metric_name}_mean")
        values: Dict[str, Any] = {}
        for variant_layer in ("core", "surface"):
            variant_entry = by_variant.get(f"{language}|{topic_role}|{variant_layer}", {}) or {}
            values[variant_layer] = variant_entry.get(f"A_current_v_{metric_suffix}")
        values["weighted"] = weighted.get(f"A_current_{metric_suffix}")
        entry[f"A_current_{metric_suffix}"] = values
    return entry


def build_table_report_payload(
    summary_payload: Mapping[str, Any],
    metric_names: Sequence[str] = ("a_exact", "a_rouge"),
) -> Dict[str, Any]:
    """Build a compact absolute-metric report for one evaluated model."""
    languages = sorted((summary_payload.get("by_language", {}) or {}).keys())
    roles = [role for role in ("target", "neighbor") if role in (summary_payload.get("by_topic_role", {}) or {})]
    rows = [
        _role_report_entry(summary_payload, language, role, metric_names)
        for language in languages
        for role in roles
    ]
    column_notes: Dict[str, str] = {}
    for metric_name in metric_names:
        metric_suffix = metric_name.removeprefix("a_")
        column_notes[f"{metric_name}_mean"] = (
            f"Mean {metric_name} over all QA records for this row's language and topic role. "
            "The report-level overall field keeps the global mean."
        )
        column_notes[f"A_current_{metric_suffix}"] = (
            f"Single-model accessibility {metric_name}, split by core/surface and weighted "
            "over available variants."
        )
    return {
        "report_type": "single_model_absolute_metrics",
        "overall": dict(summary_payload.get("overall", {}) or {}),
        "rows": rows,
        "column_notes": column_notes,
    }


def save_multilingual_eval_outputs(
    output_dir: str | Path,
    records: Sequence[Mapping[str, Any]],
    *,
    metric_names: Sequence[str] = ("a_exact", "a_rouge"),
    eval_payload: Optional[Mapping[str, Any]] = None,
    summary_payload: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Path]:
    """Save raw generations, per-QA metrics, and aggregate summaries."""
    output_path = Path(output_dir)
    paths = {
        "generations": output_path / "generations.jsonl",
        "eval": output_path / "MULTILINGUAL_EVAL.json",
        "summary": output_path / "MULTILINGUAL_SUMMARY.json",
        "report": output_path / "MULTILINGUAL_REPORT.json",
    }
    write_jsonl_atomic(paths["generations"], records)
    write_json_atomic(paths["eval"], dict(eval_payload or build_eval_payload(records, metric_names)))
    summary = dict(summary_payload or build_summary_payload(records, metric_names))
    write_json_atomic(paths["summary"], summary)
    write_json_atomic(paths["report"], build_table_report_payload(summary, metric_names))
    return paths
