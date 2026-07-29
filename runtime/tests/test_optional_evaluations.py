from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from argparse import Namespace
from pathlib import Path

import numpy as np
import pytest

from cllpu.evals.belebele import TASK_NAMES, add_macro_average, normalize_samples
from cllpu.evals.embedding import (
    DEFAULT_ENCODER_REVISION,
    METRIC_NAME,
    metric_definition,
    normalize_embedding_text,
    score_records,
)
from cllpu.evals.mia import ATTACK_NAMES, roc_auc
from cllpu.evals.metrics.multilingual import build_accessibility_summary
from cllpu.evals.semantic_api import (
    OpenAISemanticClient,
    SemanticAPIResult,
    build_evaluation_input,
    parse_semantic_score,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeEncoder:
    def token_lengths(self, texts, *, batch_size):
        assert batch_size > 0
        return [600 if text == "long" else 2 for text in texts]

    def encode(self, texts, *, batch_size, max_length):
        assert batch_size > 0 and max_length > 0
        vectors = {"same": [2.0, 0.0], "other": [0.0, 3.0], "long": [1.0, 1.0]}
        return np.asarray([vectors[text] for text in texts], dtype=np.float32)


def generation(qa_id: str, candidate: str, reference: str, variant="core"):
    return {
        "qa_id": qa_id,
        "language": "en",
        "topic_role": "target",
        "variant_layer": variant,
        "cleaned_generation": candidate,
        "expected_answer": reference,
        "metrics": {"a_exact": 0, "a_rouge": 0.0},
    }


def test_embedding_scoring_matches_paper_definition():
    assert normalize_embedding_text("  Ａ\u00a0B  ") == "A B"
    records = [
        generation("same", "same", "same"),
        generation("different", "other", "same", "surface"),
        generation("empty", "", "long"),
    ]
    scored, audit = score_records(
        records,
        encoder=FakeEncoder(),
        batch_size=2,
        tokenization_batch_size=8,
        max_length=512,
    )
    assert scored[0]["metrics"][METRIC_NAME] == pytest.approx(1.0)
    assert scored[1]["metrics"][METRIC_NAME] == pytest.approx(0.0)
    assert scored[2]["metrics"][METRIC_NAME] == pytest.approx(0.0)
    assert audit["empty_candidate_count"] == 1
    assert audit["reference_truncated_count"] == 1


def test_semantic_prompt_and_schema_are_exact_paper_assets():
    prompt = ROOT / "configs/semantic_judge/system_prompt_v1.txt"
    schema = ROOT / "configs/semantic_judge/schema_v1.json"
    assert hashlib.sha256(prompt.read_bytes()).hexdigest() == (
        "2852831c13832495d77a0fd7e8d3cd823366fde15af0391c6cbc4e1b6a7fc933"
    )
    assert hashlib.sha256(schema.read_bytes()).hexdigest() == (
        "d361045cd39fd5c3cf1c98b4e84a079b7f6a31d5bc6388678503f06f042a6f22"
    )


def test_semantic_client_builds_structured_responses_request():
    schema = {
        "type": "object",
        "properties": {"semantic_score": {"type": "number"}},
        "required": ["semantic_score"],
        "additionalProperties": False,
    }
    client = OpenAISemanticClient(
        model="judge-model",
        system_prompt="prompt",
        schema=schema,
        api_mode="responses",
    )
    payload = client.request_payload(
        build_evaluation_input(
            question="q", expected_answer="a", source_evidence="s", candidate_response="c"
        )
    )
    assert payload["text"]["format"]["type"] == "json_schema"
    assert payload["text"]["format"]["strict"] is True
    assert (
        parse_semantic_score(
            {"output_text": '{"semantic_score": 0.75}'}, api_mode="responses"
        )
        == 0.75
    )


def test_semantic_client_default_builds_paper_chat_request():
    client = OpenAISemanticClient(
        model="gpt-5.6-luna",
        system_prompt="prompt",
        schema={
            "type": "object",
            "properties": {"semantic_score": {"enum": [0, 0.25, 0.5, 0.75, 1]}},
            "required": ["semantic_score"],
            "additionalProperties": False,
        },
    )
    payload = client.request_payload("input")

    assert payload["model"] == "gpt-5.6-luna"
    assert payload["messages"] == [
        {"role": "system", "content": "prompt"},
        {"role": "user", "content": "input"},
    ]
    assert payload["max_completion_tokens"] == 1024
    assert payload["temperature"] == 0.0
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert "reasoning_effort" not in payload


def test_semantic_runner_defaults_and_protocol_match_paper(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "semantic_runner_defaults_test", ROOT / "scripts/run_semantic_evaluation.py"
    )
    runner = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(runner)
    input_path = tmp_path / "generations.jsonl"
    item = generation("qa", "candidate", "answer")
    item.update({"question": "question", "source_span": "evidence"})
    input_path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    args = runner.parser().parse_args(
        [str(input_path), "--output-dir", str(tmp_path / "semantic")]
    )
    args.prompt_file = Path(args.prompt_file).resolve()
    args.schema_file = Path(args.schema_file).resolve()
    protocol = runner.protocol_payload(args, input_path, 1)

    assert runner.VARIANT_WEIGHTS == {"core": 0.25, "surface": 0.75}
    assert protocol["judge"] == {
        "provider": "openai_compatible",
        "model": "gpt-5.6-luna",
        "api_mode": "chat-completions",
        "base_url": "https://api.openai.com/v1",
        "temperature": 0.0,
        "reasoning_effort": None,
        "max_output_tokens": 1024,
        "request_timeout_seconds": 120.0,
        "api_parameters_hash": protocol["judge"]["api_parameters_hash"],
    }
    assert protocol["input"]["cleaner_version"] == "openunlearning_cleaned_generation_v1"
    assert protocol["execution"]["retry_policy"]["max_attempts"] == 5


def test_semantic_runner_resumes_without_repeating_successes(tmp_path, monkeypatch):
    requests = []

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def evaluate(self, user_input):
            requests.append(user_input)
            score = 0.25 if len(requests) == 1 else 0.75
            return SemanticAPIResult(
                score=score,
                response_id=f"response-{len(requests)}",
                response_model="mock-judge",
                request_hash=f"request-{len(requests)}",
                raw_response={"output_text": json.dumps({"semantic_score": score})},
            )

    input_path = tmp_path / "generations.jsonl"
    records = []
    for index in range(2):
        item = generation(f"qa-{index}", f"candidate-{index}", f"answer-{index}")
        item.update({"question": f"question-{index}", "source_span": f"evidence-{index}"})
        records.append(item)
    input_path.write_text(
        "".join(json.dumps(item) + "\n" for item in records), encoding="utf-8"
    )
    output_dir = tmp_path / "semantic"
    spec = importlib.util.spec_from_file_location(
        "semantic_runner_test", ROOT / "scripts/run_semantic_evaluation.py"
    )
    runner = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(runner)
    monkeypatch.setattr(runner, "OpenAISemanticClient", FakeClient)
    monkeypatch.setenv("TEST_OPENAI_API_KEY", "test-only")
    command = [
        "run_semantic_evaluation.py",
        str(input_path),
        "--output-dir",
        str(output_dir),
        "--model",
        "mock-judge",
        "--base-url",
        "http://mock.invalid/v1",
        "--api-key-env",
        "TEST_OPENAI_API_KEY",
        "--max-attempts",
        "1",
    ]
    monkeypatch.setattr(sys, "argv", [*command, "--max-new-records", "1"])
    assert runner.main() == 0
    monkeypatch.setattr(sys, "argv", command)
    assert runner.main() == 0

    assert len(requests) == 2
    results = [
        json.loads(line)
        for line in (output_dir / "SEMANTIC_RESULTS.jsonl").read_text().splitlines()
    ]
    assert [item["qa_id"] for item in results] == ["qa-0", "qa-1"]
    assert [item["metrics"]["a_semantic"] for item in results] == [0.25, 0.75]
    progress = json.loads((output_dir / "SEMANTIC_PROGRESS.json").read_text())
    assert progress["status"] == "complete"


def test_mia_attack_set_and_auc_direction():
    assert ATTACK_NAMES == ("mia_loss", "mia_zlib", "mia_min_k", "mia_min_k_plus_plus")
    pytest.importorskip("sklearn")
    assert roc_auc([0.1, 0.2], [0.8, 0.9]) == pytest.approx(1.0)


def test_mia_protocol_identity_covers_model_data_template_and_runtime(tmp_path):
    member = tmp_path / "member.jsonl"
    holdout = tmp_path / "holdout.jsonl"
    member.write_text('{"qa_id":"member"}\n', encoding="utf-8")
    holdout.write_text('{"qa_id":"holdout"}\n', encoding="utf-8")
    spec = importlib.util.spec_from_file_location(
        "mia_runner_test", ROOT / "scripts/run_mia_evaluation.py"
    )
    runner = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(runner)
    args = Namespace(
        model="example/model",
        tokenizer="example/tokenizer",
        model_revision="model-sha",
        tokenizer_revision="tokenizer-sha",
        dataset="common",
        source_language="en",
        system_prompt="system",
        date_string="10 Apr 2025",
        torch_dtype="bfloat16",
        attn_implementation="flash_attention_2",
        device_map="cuda",
        batch_size=32,
        min_k_plus_plus_batch_size=16,
        max_length=512,
        k=0.4,
    )
    data_spec = {
        "member_role": "target",
        "member_family": None,
        "member_origin": None,
        "holdout_role": "holdout",
        "holdout_family": "holdout",
    }
    protocol = runner.protocol_payload(args, data_spec, member, holdout, 1, 1)
    assert protocol["evaluation_language"] == "en"
    assert protocol["model"]["revision"] == "model-sha"
    assert protocol["chat_template"] == {
        "system_prompt": "system",
        "date_string": "10 Apr 2025",
    }
    assert protocol["runtime"] == {
        "torch_dtype": "bfloat16",
        "attn_implementation": "flash_attention_2",
        "device_map": "cuda",
        "batch_size": 32,
        "min_k_plus_plus_batch_size": 16,
    }
    assert protocol["member"]["sha256"] == hashlib.sha256(member.read_bytes()).hexdigest()


def test_mia_cli_has_no_cross_language_dimension():
    spec = importlib.util.spec_from_file_location(
        "mia_source_only_test", ROOT / "scripts/run_mia_evaluation.py"
    )
    runner = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(runner)
    args = runner.parser().parse_args(
        [
            "--model",
            "example/model",
            "--output-dir",
            "output",
            "--dataset",
            "common",
            "--source-language",
            "ja",
        ]
    )
    assert args.source_language == "ja"
    assert not hasattr(args, "eval_language")


def test_mia_data_spec_uses_source_language_for_members_and_holdouts():
    spec = importlib.util.spec_from_file_location(
        "mia_data_spec_test", ROOT / "scripts/run_mia_evaluation.py"
    )
    runner = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(runner)

    common = runner.paper_data_spec(Namespace(dataset="common", source_language="ja"))
    assert common["member_file"] == Path("multilingual/qa_flat.ja.jsonl")
    assert common["holdout_file"] == Path(
        "multilingual/common_holdout/qa_flat.ja.jsonl"
    )
    assert (common["member_count"], common["holdout_count"]) == (500, 500)

    culture = runner.paper_data_spec(Namespace(dataset="culture", source_language="bn"))
    assert culture["member_file"] == Path(
        "multilingual/train_splits/culture_origin/"
        "bn_eval_all_languages_core_surface.jsonl"
    )
    assert culture["holdout_file"] == Path(
        "multilingual/culture_holdout/qa_flat.bn.jsonl"
    )
    assert (culture["member_count"], culture["holdout_count"]) == (27, 300)


def test_embedding_only_summary_does_not_claim_exact_or_rouge():
    record = generation("qa", "same", "same")
    record["metrics"] = {"a_embedding": 1.0}
    summary = build_accessibility_summary(
        [record], ("a_embedding",), variant_weights={"core": 0.25, "surface": 0.75}
    )
    assert "a_exact" not in summary["metric_definitions"]
    assert "a_rouge" not in summary["metric_definitions"]


def test_default_weighted_accessibility_gives_four_forms_equal_weight():
    records = []
    forms = (("core", 1.0), ("surface", 0.0), ("surface", 0.0), ("surface", 0.0))
    for index, (layer, score) in enumerate(forms):
        item = generation(f"qa-{index}", "candidate", "reference", variant=layer)
        item["knowledge_pair_id"] = "knowledge-1"
        item["metrics"] = {"a_exact": score, "a_rouge": score}
        records.append(item)
    summary = build_accessibility_summary(records, ("a_exact", "a_rouge"))
    knowledge = summary["by_knowledge_language"]["en|knowledge-1|target"]
    role = summary["by_role_language"]["en|target"]
    assert knowledge["variant_weights"] == {"core": 0.25, "surface": 0.75}
    assert knowledge["variants"]["surface"]["count"] == 3
    assert knowledge["A_current_exact"] == pytest.approx(0.25)
    assert knowledge["A_current_rouge"] == pytest.approx(0.25)
    assert role["A_current_exact"] == pytest.approx(0.25)
    assert role["A_current_rouge"] == pytest.approx(0.25)


def test_embedding_definition_records_selected_encoder():
    definition = metric_definition(
        384, encoder="example/bge-m3-checkpoint", encoder_revision="encoder-sha"
    )
    assert definition["encoder"] == "example/bge-m3-checkpoint"
    assert definition["encoder_revision"] == "encoder-sha"


def test_embedding_default_revision_matches_paper_snapshot():
    assert DEFAULT_ENCODER_REVISION == "5617a9f61b028005a4858fdac845db406aefb181"


def test_belebele_resume_identity_covers_inference_protocol():
    spec = importlib.util.spec_from_file_location(
        "belebele_runner_test", ROOT / "scripts/run_belebele_utility.py"
    )
    runner = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(runner)
    args = Namespace(
        model="example/model",
        model_revision="model-sha",
        tokenizer_revision="tokenizer-sha",
        data_root=None,
        batch_size=16,
        dtype="bfloat16",
        device="cuda",
        attn_implementation="flash_attention_2",
        limit=None,
    )
    identity = runner.protocol(args, "example/tokenizer")
    assert identity["dataset"] == "facebook/belebele"
    assert identity["dataset_revision"] == "7899cdfa4e1e0d733fd77c848e2c273cb1d32be2"
    assert identity["expected_samples_per_task"] == 900
    assert identity["metrics"] == ["acc", "acc_norm"]
    assert identity["continuations"] == ["A", "B", "C", "D"]
    assert identity["batch_size"] == 16
    assert identity["num_fewshot"] == 0
    assert identity["log_samples"] is True
    assert identity["apply_chat_template"] is True
    assert identity["system_instruction"] is None
    assert identity["fewshot_as_multiturn"] is False
    assert identity["bootstrap_iters"] == 0
    assert identity["dtype"] == "bfloat16"
    assert identity["attn_implementation"] == "flash_attention_2"
    assert identity["software_versions"]["lm_eval"] == "0.4.8"


def test_belebele_normalization_and_macro():
    task = "belebele_eng_Latn"
    sample = {
        "doc_id": 2,
        "doc": {
            "link": "example",
            "question_number": 3,
            "correct_answer_num": "2",
            "dialect": "eng_Latn",
            "mc_answer1": "one",
            "mc_answer2": "two",
            "mc_answer3": "three",
            "mc_answer4": "four",
        },
        "filtered_resps": [[-3.0], [-1.0], [-2.0], [-4.0]],
        "acc": 1,
        "acc_norm": 1,
    }
    normalized = normalize_samples(task, [sample])
    assert normalized[0]["item_id"] == "example::question_3"
    assert normalized[0]["predicted_option"] == "B"

    summary = {}
    for name in TASK_NAMES:
        summary[f"{name}/acc"] = 0.5
        summary[f"{name}/acc_norm"] = 0.5
    summary = add_macro_average(summary)
    assert summary["belebele_10lang_macro/acc"] == pytest.approx(0.5)
    assert summary["belebele_10lang_macro/acc_norm"] == pytest.approx(0.5)
