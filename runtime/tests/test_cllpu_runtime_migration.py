from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


RUNTIME_ROOT = Path(__file__).resolve().parents[1]
ROOT = RUNTIME_ROOT.parent


def _write_four_form_generations(path: Path) -> None:
    candidates = (" Answer ", "answer", "Answer.", "Answer")
    variants = ("core", "surface", "surface", "surface")
    records = []
    for index, (candidate, variant) in enumerate(zip(candidates, variants)):
        records.append(
            {
                "qa_id": f"qa-{index}",
                "language": "en",
                "knowledge_pair_id": "knowledge-1",
                "topic_role": "target",
                "variant_layer": variant,
                "expected_answer": "Answer",
                "cleaned_generation": candidate,
            }
        )
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def test_legacy_cllpu_metric_stack_is_absent():
    assert not (RUNTIME_ROOT / "evaluation/_common.py").exists()


@pytest.mark.parametrize(
    ("entrypoint", "canonical_script"),
    (
        ("evaluate_sentence_similarity.py", "run_embedding_evaluation"),
        ("evaluate_llm_judge.py", "run_semantic_evaluation"),
    ),
)
def test_optional_compatibility_entrypoints_delegate_to_canonical_scripts(
    entrypoint: str, canonical_script: str
):
    source = (RUNTIME_ROOT / "evaluation" / entrypoint).read_text(encoding="utf-8")
    assert f"from {canonical_script} import main" in source


def test_em_compatibility_entrypoint_preserves_strict_cross_runtime_behavior(tmp_path):
    input_path = tmp_path / "generations.jsonl"
    output_dir = tmp_path / "em"
    _write_four_form_generations(input_path)

    subprocess.run(
        [
            sys.executable,
            "runtime/evaluation/evaluate_em.py",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                filter(None, (str(RUNTIME_ROOT / "src"), os.environ.get("PYTHONPATH")))
            ),
        },
        check=True,
        capture_output=True,
        text=True,
    )

    scored = [
        json.loads(line)
        for line in (output_dir / "generations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [record["metrics"]["a_exact"] for record in scored] == [1, 0, 0, 1]


def test_retain_reference_is_documented_as_common_only():
    retain_config = (
        RUNTIME_ROOT / "configs/experiment/finetune/multilingual/retain_reference.yaml"
    ).read_text(encoding="utf-8")
    culture_config = (
        RUNTIME_ROOT / "configs/experiment/unlearn/multilingual/culture_origin.yaml"
    ).read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "all 8,000 Common+Culture neighbor/core records" in retain_config
    assert "Common setting only" in retain_config
    assert "not used as a Culture-setting reference" in retain_config
    assert "not the independently trained Retain-reference model" in culture_config
    assert "used only as the Common-setting reference" in readme
