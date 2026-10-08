from collections import Counter
from pathlib import Path
import random
from types import SimpleNamespace
from unittest.mock import Mock

from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf
import pytest
import torch

from cllpu.data import DATASET_REGISTRY, get_data
from cllpu.data.learn_unlearn import (
    LearnUnlearnCombinedQADataset, LearnUnlearnEnglishRetainQADataset, aligned_english,
)
from cllpu.data.utils import preprocess_chat_instance
from cllpu.seed_sweep import build_commands, main as seed_main
from cllpu.trainer import TRAINER_REGISTRY, load_trainer_args
from cllpu.trainer.base import FinetuneTrainer
from cllpu.trainer.unlearn.learn_unlearn import LearnUnlearnCombined


RUNTIME = Path(__file__).resolve().parents[1]
LANGUAGES = "en zh de ar bn es fr ja th sw".split()


@pytest.mark.parametrize("setting", ["common", "culture"])
@pytest.mark.parametrize("language", LANGUAGES)
def test_combined_matches_facts_in_release_data(setting, language):
    root = RUNTIME / "data/multilingual"
    kwargs = dict(tokenizer=None, template_args={}, languages=language, variant_layers="core")
    if setting == "common":
        forget_file = retain_file = root / f"qa_flat.{language}.jsonl"
        english = root / "qa_flat.en.jsonl"
        count = 500
    else:
        root = root / "train_splits/culture_origin"
        forget_file = root / f"{language}_forget_target_core.jsonl"
        retain_file = root / f"{language}_retain_neighbor_core.jsonl"
        english = root / f"{language}_eval_all_languages_core_surface.jsonl"
        kwargs.update(dataset_families="culture_specific", culture_origins=language)
        count = {"ar": 33, "bn": 27}.get(language, 30)
    kwargs.update(expected_count=count, source_language=language, english_data_files=str(english))
    before = random.getstate()
    forget = LearnUnlearnCombinedQADataset(
        data_files=str(forget_file), topic_roles="target", mixture_seed=1, **kwargs
    )
    again = LearnUnlearnCombinedQADataset(
        data_files=str(forget_file), topic_roles="target", mixture_seed=1, **kwargs
    )
    retain = LearnUnlearnEnglishRetainQADataset(
        data_files=str(retain_file), topic_roles="neighbor", **kwargs
    )
    assert random.getstate() == before
    assert len(forget) == len(retain) == count
    assert len({r["source_qa_id"] for r in forget.records}) == count
    assert len({r["source_qa_id"] for r in retain.records}) == count
    assert {r["language"] for r in retain.records} == {"en"}
    expected = {"en": count} if language == "en" else {"en": count // 2, language: count - count // 2}
    assert Counter(r["language"] for r in forget.records) == expected
    assert forget.mixture_manifest == again.mixture_manifest
    assert forget.metadata[0]["qa_id"] == forget.records[0]["qa_id"]
    assert DATASET_REGISTRY["LearnUnlearnCombinedQADataset"] is type(forget)


def test_translation_rejects_missing_duplicate_or_wrong_origin():
    source = {"source_qa_id": "x", "culture_origin": "zh", "language": "zh"}
    english = {**source, "language": "en"}
    assert aligned_english([source], [english]) == [english]
    for pool in ([], [english, english], [{**english, "culture_origin": "fr"}]):
        with pytest.raises(ValueError):
            aligned_english([source], pool)


def test_combined_loss_and_gradient_are_retain_minus_forget():
    class Model(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.weight = torch.nn.Parameter(torch.tensor(0.4))

        def forward(self, input_ids, labels, attention_mask):
            logits = torch.stack([input_ids.float() * self.weight, input_ids.float()], -1)
            return SimpleNamespace(loss=torch.nn.functional.cross_entropy(
                logits.reshape(-1, 2), labels.reshape(-1), ignore_index=-100
            ))

    model = Model()
    trainer = object.__new__(LearnUnlearnCombined)
    trainer.gamma = trainer.alpha = 1.0
    trainer.retain_loss_type = "NLL"
    forget = dict(input_ids=torch.tensor([[1, 2]]), labels=torch.tensor([[-100, 0]]),
                  attention_mask=torch.ones(1, 2))
    retain = dict(input_ids=torch.tensor([[3, 4]]), labels=torch.tensor([[-100, 1]]),
                  attention_mask=torch.ones(1, 2))
    loss = trainer.compute_loss(model, dict(forget=forget, retain=retain))
    expected = model(**retain).loss - model(**forget).loss
    torch.testing.assert_close(loss, expected)
    torch.testing.assert_close(torch.autograd.grad(loss, model.weight)[0],
                               torch.autograd.grad(expected, model.weight)[0])
    assert TRAINER_REGISTRY["LearnUnlearnCombined"] is LearnUnlearnCombined
    with pytest.raises(ValueError):
        LearnUnlearnCombined(alpha=2)


class QwenLikeTokenizer:
    eos_token_id = 151645

    def apply_chat_template(self, chat, *, add_generation_prompt, max_length, **kwargs):
        assert chat[0] == {"role": "system", "content": "You are a helpful assistant."}
        return ([1, 2] if add_generation_prompt else [1, 2, 42, 151645, 198])[:max_length]


@pytest.mark.parametrize("generation", [False, True])
def test_native_qwen_eos_and_legacy_default(generation):
    template = dict(apply_chat_template=True, system_prompt="You are a helpful assistant.")
    qwen = preprocess_chat_instance(QwenLikeTokenizer(), {**template, "append_eos_token": False},
                                    "Q", "A", 32, generation)
    legacy = preprocess_chat_instance(QwenLikeTokenizer(), template, "Q", "A", 32, generation)
    assert qwen["labels"].tolist()[-3:] == [42, 151645, 198]
    assert legacy["labels"].tolist()[-3:] == [151645, 198, 151645]
    assert qwen["input_ids"].tolist() == ([1, 2] if generation else [1, 2, 42, 151645, 198])
    if not generation:
        assert qwen["labels"].tolist()[:2] == [-100, -100]


def test_nested_fsdp_options_are_plain_containers(monkeypatch):
    import cllpu.trainer as module
    monkeypatch.setattr(module, "TrainingArguments", lambda **kwargs: kwargs)
    cfg = OmegaConf.create(dict(fsdp=["full_shard", "auto_wrap"], fsdp_config={
        "transformer_layer_cls_to_wrap": ["Qwen2DecoderLayer"],
        "activation_checkpointing": False,
    }))
    result = load_trainer_args(cfg, [])
    assert isinstance(result["fsdp"], list)
    assert isinstance(result["fsdp_config"], dict)
    assert isinstance(result["fsdp_config"]["transformer_layer_cls_to_wrap"], list)


@pytest.mark.parametrize("should_save", [True, False])
def test_fsdp_save_collects_on_all_ranks_writes_on_main(should_save):
    trainer = object.__new__(FinetuneTrainer)
    trainer.is_fsdp_enabled = True
    trainer.args = SimpleNamespace(should_save=should_save, output_dir="output", push_to_hub=False)
    trainer.model = object()
    trainer.accelerator = SimpleNamespace(
        state=SimpleNamespace(fsdp_plugin=SimpleNamespace(state_dict_type="FULL_STATE_DICT")),
        get_state_dict=Mock(return_value={"weight": 1}),
    )
    trainer._save = Mock()
    trainer.save_model()
    trainer.accelerator.get_state_dict.assert_called_once_with(trainer.model, unwrap=False)
    assert trainer._save.call_count == int(should_save)


def test_seed_commands_preserve_settings_and_compose(tmp_path):
    overrides = ["experiment=unlearn/multilingual/default", "model=Qwen2.5-14B-Instruct",
                 "trainer=DrNPO", "target_model=example/finetuned", "trainer.args.learning_rate=2e-6"]
    runs = build_commands(overrides, tmp_path / "runs with spaces", "trial", 2)
    assert len({path for path, _ in runs}) == 4
    for seed, (path, command) in enumerate(runs, 1):
        assert "torch.distributed.run" in command and "--nproc_per_node=2" in command
        assert command[command.index("cllpu.train") + 1:][:2] == ["--config-name", "unlearn"]
        actual = command[command.index("cllpu.train") + 3:]
        assert actual[:len(overrides)] == overrides
        with initialize_config_dir(config_dir=str(RUNTIME / "configs"), version_base=None):
            cfg = compose(config_name="unlearn", overrides=actual)
        assert cfg.mode == "unlearn"
        assert cfg.trainer.args.seed == seed
        assert cfg.trainer.args.learning_rate == 2e-6
        assert cfg.trainer.args.output_dir == str(path)
        assert cfg.model.model_args.pretrained_model_name_or_path == "example/finetuned"
        assert cfg.model.template_args.append_eos_token is False
        assert "date_string" not in cfg.model.template_args
    assert not tmp_path.joinpath("runs with spaces").exists()


@pytest.mark.parametrize("override", ["trainer.args.seed=9", "++trainer.args.output_dir=x",
    "~task_name", "trainer.args={seed:0}", "trainer.args.learning_rate=1e-5,2e-5"])
def test_seed_launcher_rejects_conflicts(tmp_path, override):
    with pytest.raises(ValueError):
        build_commands([override], tmp_path, "trial")


def test_seed_execution_is_serial_isolated_and_refuses_overwrite(tmp_path, monkeypatch):
    import cllpu.seed_sweep as module
    calls = []
    monkeypatch.setenv("WANDB_RUN_ID", "old")
    monkeypatch.setenv("WANDB_RESUME", "must")
    monkeypatch.setattr(module.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)))
    argv = ["--output-root", str(tmp_path), "--run-name", "trial", "--", "trainer=DrNPO"]
    seed_main(argv)
    assert len(calls) == 4
    for seed, (command, kwargs) in enumerate(calls, 1):
        assert f"trainer.args.seed={seed}" in command
        assert "WANDB_RUN_ID" not in kwargs["env"] and "WANDB_RESUME" not in kwargs["env"]
        assert kwargs["env"]["WANDB_NAME"] == f"trial-seed{seed}"
        assert kwargs["check"] is True
    with pytest.raises(SystemExit):
        seed_main(argv)
    assert len(calls) == 4


def test_seed_failure_stops_remaining_runs(tmp_path, monkeypatch):
    import cllpu.seed_sweep as module
    runner = Mock(side_effect=module.subprocess.CalledProcessError(1, "training"))
    monkeypatch.setattr(module.subprocess, "run", runner)
    with pytest.raises(module.subprocess.CalledProcessError):
        seed_main(["--output-root", str(tmp_path), "--run-name", "trial", "--", "trainer=DrNPO"])
    assert runner.call_count == 1
    assert not (tmp_path / "trial-seed2").exists()


@pytest.mark.parametrize("setting,language,count", [("default", "zh", 500), ("culture_origin", "ar", 33)])
def test_combined_hydra_loads_forget_retain_wrapper(setting, language, count):
    root = RUNTIME / "data/multilingual"
    pool = root / "qa_flat.en.jsonl"
    overrides = [
        f"experiment=unlearn/multilingual/{setting}", "trainer=LearnUnlearnCombined",
        "target_model=example/target", "task_name=test",
        f"multilingual_source_language={language}", f"paths.data_dir={RUNTIME / 'data'}",
        "data.forget.Multilingual_QA.handler=LearnUnlearnCombinedQADataset",
        "data.retain.Multilingual_QA.handler=LearnUnlearnEnglishRetainQADataset",
    ]
    if setting == "culture_origin":
        pool = root / f"train_splits/culture_origin/{language}_eval_all_languages_core_surface.jsonl"
        overrides += [f"multilingual_culture_origin={language}",
                      f"multilingual_culture_forget_expected_count={count}",
                      f"multilingual_culture_retain_expected_count={count}"]
    for split in ("forget", "retain"):
        overrides += [f"+data.{split}.Multilingual_QA.args.english_data_files={pool}",
                      f"+data.{split}.Multilingual_QA.args.source_language={language}"]
    with initialize_config_dir(config_dir=str(RUNTIME / "configs"), version_base=None):
        cfg = compose(config_name="unlearn", overrides=overrides)
    data = get_data(cfg.data, mode=cfg.mode, tokenizer=None, template_args=cfg.model.template_args)
    assert len(data["train"]) == count
    assert cfg.trainer.handler == "LearnUnlearnCombined"
    assert cfg.trainer.method_args == {"alpha": 1.0, "gamma": 1.0, "retain_loss_type": "NLL"}


@pytest.mark.parametrize("model", ["Llama-3.1-8B-Instruct", "Qwen2.5-14B-Instruct"])
@pytest.mark.parametrize("experiment,count", [("default", 16000), ("retain_reference", 8000)])
def test_finetune_recipes_load_training_data(model, experiment, count):
    with initialize_config_dir(config_dir=str(RUNTIME / "configs"), version_base=None):
        cfg = compose(config_name="train", overrides=[
            f"experiment=finetune/multilingual/{experiment}", f"model={model}",
            f"paths.data_dir={RUNTIME / 'data'}", "task_name=check",
        ])
    assert cfg.mode == "finetune"
    data = get_data(cfg.data, mode=cfg.mode, tokenizer=None, template_args=cfg.model.template_args)
    assert len(data["train"]) == count
