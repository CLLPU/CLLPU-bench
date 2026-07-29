from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from cllpu.saved_generation_evaluation import (
    main,
    parser_for,
    read_and_validate_records,
    resolve_input,
    score_records,
)


def generation(index: int, variant: str, candidate: str = "Answer") -> dict:
    return {
        "qa_id": f"qa-{index}",
        "language": "en",
        "knowledge_pair_id": "knowledge-1",
        "topic_role": "target",
        "variant_layer": variant,
        "expected_answer": "Answer",
        "cleaned_generation": candidate,
        "metrics": {"a_exact": -1, "a_rouge": -1.0},
    }


def write_generations(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def complete_records() -> list[dict]:
    return [
        generation(0, "core", " Answer "),
        generation(1, "surface", "answer"),
        generation(2, "surface", "Answer."),
        generation(3, "surface", "Answer"),
    ]


def test_saved_em_exactly_matches_openunlearning_strip_only_behavior(tmp_path):
    path = tmp_path / "evaluation/generations.jsonl"
    write_generations(path, complete_records())

    records = read_and_validate_records(resolve_input(path.parent))
    scored = score_records(records, "a_exact")

    assert [record["metrics"]["a_exact"] for record in scored] == [1, 0, 0, 1]
    assert all(record["metrics"]["a_rouge"] == -1.0 for record in scored)


def test_saved_rouge_replaces_only_rouge_metric(tmp_path):
    path = tmp_path / "generations.jsonl"
    write_generations(path, complete_records())

    scored = score_records(read_and_validate_records(path), "a_rouge")

    assert all(record["metrics"]["a_exact"] == -1 for record in scored)
    assert scored[0]["metrics"]["a_rouge"] == pytest.approx(1.0)
    assert scored[3]["metrics"]["a_rouge"] == pytest.approx(1.0)


def test_saved_generation_evaluator_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="Missing generations JSONL"):
        resolve_input(tmp_path / "missing")


def test_saved_generation_evaluator_rejects_incomplete_four_form_group(tmp_path):
    path = tmp_path / "generations.jsonl"
    write_generations(path, complete_records()[:3])

    with pytest.raises(ValueError, match="one core and three surface forms"):
        read_and_validate_records(path)


def test_saved_metric_cli_has_no_model_generation_arguments(tmp_path):
    parser = parser_for("em")
    args = parser.parse_args(
        [str(tmp_path / "generations.jsonl"), "--output-dir", str(tmp_path / "result")]
    )
    option_names = {option for action in parser._actions for option in action.option_strings}

    assert args.input == tmp_path / "generations.jsonl"
    assert "--checkpoint" not in option_names
    assert "--tokenizer" not in option_names
    assert "--gpu" not in option_names
    assert "--dataset" not in option_names


def test_saved_em_main_writes_equal_four_form_aggregate(tmp_path, monkeypatch):
    input_path = tmp_path / "source/generations.jsonl"
    output_dir = tmp_path / "result"
    write_generations(input_path, complete_records())
    monkeypatch.setattr(
        sys,
        "argv",
        ["evaluate_checkpoint_em.py", str(input_path), "--output-dir", str(output_dir)],
    )

    assert main("em") == 0
    summary = json.loads((output_dir / "MULTILINGUAL_SUMMARY.json").read_text())
    protocol = json.loads(
        (output_dir / "SAVED_GENERATION_EVALUATION_PROTOCOL.json").read_text()
    )

    assert summary["by_role_language"]["en|target"]["A_current_exact"] == pytest.approx(0.5)
    assert protocol["variant_weights"] == {"core": 0.25, "surface": 0.75}
    assert protocol["runs_model_generation"] is False
