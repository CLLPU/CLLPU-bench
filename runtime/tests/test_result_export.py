from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_exporter():
    spec = importlib.util.spec_from_file_location(
        "cross_language_export_test", ROOT / "scripts/export_cross_language_matrix.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def summary_payload(score_offset: float = 0.0) -> dict:
    by_role_language = {}
    by_role_language_variant = {}
    languages = ("ar", "bn", "de", "en", "es", "fr", "ja", "sw", "th", "zh")
    for index, language in enumerate(languages):
        score = score_offset + index / 100
        by_role_language[f"{language}|target"] = {
            "A_current_rouge": score,
            "language": language,
            "topic_role": "target",
            "variant_weights": {"core": 0.25, "surface": 0.75},
            "variants": {
                "core": {"count": 10, "A_current_v_rouge": score},
                "surface": {"count": 30, "A_current_v_rouge": score},
            },
        }
        for variant in ("core", "surface"):
            by_role_language_variant[f"{language}|target|{variant}"] = {
                "A_current_v_rouge": score
            }
    return {
        "by_dataset_family": {"common": {"count": 40000}},
        "by_role_language": by_role_language,
        "by_role_language_variant": by_role_language_variant,
        "metric_definitions": {
            "A_current_role": {
                "variant_weights": {"core": 0.25, "surface": 0.75},
                "renormalize_variant_weights": True,
            }
        },
    }


def test_exporter_builds_one_method_complete_ten_by_ten_matrix(tmp_path):
    exporter = load_exporter()
    inputs = {}
    method = "simnpo"
    for source in exporter.LANGUAGES:
        path = tmp_path / source / method / "MULTILINGUAL_SUMMARY.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary_payload()), encoding="utf-8")
        inputs[source] = exporter.SummaryInput(source, source, path)

    rows = exporter.extract_rows(
        tuple(inputs.values()),
        dataset="common",
        experiment="paper_common",
        method=method,
        language_scope="all",
        metric="a_rouge",
        topic_role="target",
        variant="weighted",
    )
    output = tmp_path / "all_methods.csv"
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
    exporter.write_csv_atomic(output, rows, fields)
    exporter.write_matrices(
        tmp_path / "matrices",
        rows,
        method=method,
        inputs=tuple(inputs.values()),
    )

    assert len(rows) == 100
    assert rows[0]["method"] == method
    assert rows[0]["source_language"] == "ar"
    assert rows[0]["evaluation_language"] == "ar"
    assert rows[-1]["source_language"] == "zh"
    with output.open("r", encoding="utf-8", newline="") as handle:
        exported = list(csv.DictReader(handle))
    assert len(exported) == 100
    assert tuple(exported[0]) == fields
    assert len(output.read_text(encoding="utf-8").splitlines()) == 101
    assert len(list((tmp_path / "matrices").glob("*.csv"))) == 1
    assert len((tmp_path / "matrices" / f"{method}.csv").read_text().splitlines()) == 11


def test_exporter_accepts_one_checkpoint_for_all_or_source_only(tmp_path):
    exporter = load_exporter()
    path = tmp_path / "en" / "ga" / "MULTILINGUAL_SUMMARY.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(summary_payload()), encoding="utf-8")
    inputs = (exporter.SummaryInput("en-checkpoint-150", "en", path),)

    all_rows = exporter.extract_rows(
        inputs,
        dataset="common",
        experiment="one_checkpoint",
        method="ga",
        language_scope="all",
        metric="a_rouge",
        topic_role="target",
        variant="weighted",
    )
    source_rows = exporter.extract_rows(
        inputs,
        dataset="common",
        experiment="one_checkpoint",
        method="ga",
        language_scope="source",
        metric="a_rouge",
        topic_role="target",
        variant="weighted",
    )
    exporter.write_matrices(
        tmp_path / "partial_matrix",
        all_rows,
        method="ga",
        inputs=inputs,
    )

    assert len(all_rows) == 10
    assert len(source_rows) == 1
    assert source_rows[0]["evaluation_language"] == "en"
    matrix_lines = (tmp_path / "partial_matrix" / "ga.csv").read_text().splitlines()
    assert len(matrix_lines) == 2


def test_exporter_rejects_non_paper_variant_weights(tmp_path):
    exporter = load_exporter()
    payload = summary_payload()
    payload["metric_definitions"]["A_current_role"]["variant_weights"] = {
        "core": 0.5,
        "surface": 0.5,
    }
    path = tmp_path / "summary.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="expected variant weights"):
        exporter.extract_rows(
            (exporter.SummaryInput("en", "en", path),),
            dataset="common",
            experiment="paper_common",
            method="ga",
            language_scope="source",
            metric="a_rouge",
            topic_role="target",
            variant="weighted",
        )


def test_exporter_accepts_legacy_common_family_but_rejects_unified_full(tmp_path):
    exporter = load_exporter()
    payload = summary_payload()
    payload["by_dataset_family"] = {"": {"count": 40000}}
    path = tmp_path / "legacy_common.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    exporter.validate_dataset(payload, dataset="common", source="en", path=path)

    payload["by_dataset_family"]["culture_specific"] = {"count": 24000}
    with pytest.raises(ValueError, match="expected only dataset_family"):
        exporter.validate_dataset(payload, dataset="common", source="en", path=path)


def test_input_index_accepts_multiple_checkpoints_for_one_source(tmp_path):
    exporter = load_exporter()
    first = tmp_path / "checkpoint-10.json"
    second = tmp_path / "checkpoint-20.json"
    first.write_text(json.dumps(summary_payload()), encoding="utf-8")
    second.write_text(json.dumps(summary_payload(0.1)), encoding="utf-8")
    index = tmp_path / "index.csv"
    index.write_text(
        "checkpoint_id,source_language,summary_path,method\n"
        "en-cp10,en,checkpoint-10.json,simnpo\n"
        "en-cp20,en,checkpoint-20.json,simnpo\n",
        encoding="utf-8",
    )

    inputs = exporter.resolve_inputs(
        input_root=None,
        input_index=index,
        path_template="unused",
        method="simnpo",
        source_languages=None,
    )
    rows = exporter.extract_rows(
        inputs,
        dataset="common",
        experiment="two_checkpoints",
        method="simnpo",
        language_scope="all",
        metric="a_rouge",
        topic_role="target",
        variant="weighted",
    )
    exporter.write_matrices(tmp_path / "matrices", rows, method="simnpo", inputs=inputs)

    assert len(inputs) == 2
    assert len(rows) == 20
    assert {row["checkpoint_id"] for row in rows} == {"en-cp10", "en-cp20"}
    matrix = list(
        csv.DictReader((tmp_path / "matrices/simnpo.csv").open(encoding="utf-8"))
    )
    assert [row["checkpoint_id"] for row in matrix] == ["en-cp10", "en-cp20"]
    assert [row["source_language"] for row in matrix] == ["en", "en"]


def test_input_index_rejects_empty_summary_path(tmp_path):
    exporter = load_exporter()
    index = tmp_path / "index.csv"
    index.write_text("method,source_language,summary_path\nga,en,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Empty summary_path"):
        exporter.resolve_inputs(
            input_root=None,
            input_index=index,
            path_template="unused",
            method="ga",
            source_languages=None,
        )


def test_inputs_require_an_explicit_single_method_boundary(tmp_path):
    exporter = load_exporter()
    index = tmp_path / "index.csv"
    index.write_text(
        "method,source_language,summary_path\nnpo,en,summary.json\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="method mismatch"):
        exporter.resolve_inputs(
            input_root=None,
            input_index=index,
            path_template="unused",
            method="simnpo",
            source_languages=None,
        )
    with pytest.raises(ValueError, match=r"must contain the \{method\} placeholder"):
        exporter.resolve_inputs(
            input_root=tmp_path,
            input_index=None,
            path_template="{source_language}/summary.json",
            method="simnpo",
            source_languages=("en",),
        )
