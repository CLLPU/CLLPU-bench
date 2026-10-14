import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf
import pytest
import torch
from transformers import TrainerControl

from cllpu.repeat_selected import SelectedStepCallback, main, prepare


RUNTIME = Path(__file__).resolve().parents[1]


@pytest.fixture
def seed0(tmp_path):
    base = tmp_path / "seed0"
    ck = base / "checkpoint-3"
    ck.mkdir(parents=True)
    config = {
        "mode": "unlearn", "task_name": "original", "save_final_model": True,
        "paths": {"output_dir": str(base)},
        "model": {"model_args": {"pretrained_model_name_or_path": "initial-sft"}},
        "data": {"mixture_seed": 0},
        "eval": {"multilingual": {"output_dir": str(base), "batch_size": 32}},
        "trainer": {"handler": "DrNPO", "method_args": {"beta": 0.1}, "args": {
            "seed": 0, "data_seed": 17, "max_steps": 10, "num_train_epochs": 10,
            "warmup_steps": 2, "learning_rate": 1e-5, "output_dir": str(base),
            "per_device_train_batch_size": 8, "gradient_accumulation_steps": 4,
            "eval_strategy": "epoch", "save_strategy": "epoch",
        }},
    }
    OmegaConf.save(OmegaConf.create(config), base / "resolved_config.yaml")
    (base / "training_context.json").write_text(json.dumps({
        "world_size": 1, "warmup_steps": 2, "working_directory": str(tmp_path),
    }))
    (ck / "trainer_state.json").write_text(json.dumps({
        "global_step": 3, "max_steps": 10, "epoch": 0.75,
    }))
    return base, config


def test_repeat_preserves_science_and_changes_only_seed_and_outputs(seed0, tmp_path):
    base, original = seed0
    jobs = prepare(base, 3, tmp_path / "repeats", "example", [1, 2, 3, 4], 1)
    for seed, (dest, cfg, manifest, _) in enumerate(jobs, 1):
        assert cfg["trainer"]["args"]["seed"] == seed
        unchanged = copy.deepcopy(cfg)
        for key, change in manifest["changes"].items():
            parts = key.split(".")
            obj = unchanged
            for part in parts[:-1]:
                obj = obj[part]
            if change["before"] is None:
                del obj[parts[-1]]
            else:
                obj[parts[-1]] = change["before"]
        assert unchanged == original
        assert cfg["trainer"]["args"]["max_steps"] == 10
        assert cfg["model"] == original["model"]
        assert cfg["trainer"]["args"]["data_seed"] == 17
        assert cfg["data"]["mixture_seed"] == 0
        assert cfg["eval"]["multilingual"]["output_dir"].startswith(str(dest))
        assert manifest["selection"] == {"global_step": 3, "max_steps": 10, "epoch": 0.75}
    assert not (tmp_path / "repeats").exists()


@pytest.mark.parametrize("mutation", ["seed", "interpolation", "best", "wrong_step", "world", "exists"])
def test_invalid_seed0_or_destination_fails(seed0, tmp_path, mutation):
    base, cfg = seed0
    if mutation == "seed":
        cfg["trainer"]["args"]["seed"] = 1
    elif mutation == "interpolation":
        cfg["model"]["model_args"]["pretrained_model_name_or_path"] = "${oc.env:MODEL}"
    elif mutation == "best":
        cfg["trainer"]["args"]["load_best_model_at_end"] = True
    elif mutation == "wrong_step":
        (base / "checkpoint-3/trainer_state.json").write_text(json.dumps({
            "global_step": 4, "max_steps": 10, "epoch": 1,
        }))
    elif mutation == "exists":
        (tmp_path / "example-seed1").mkdir()
    OmegaConf.save(OmegaConf.create(cfg), base / "resolved_config.yaml")
    with pytest.raises(ValueError):
        prepare(base, 3, tmp_path, "example", [1], 2 if mutation == "world" else 1)


@pytest.mark.parametrize("seeds", [[], [0], [-1], [1, 1], [2**32]])
def test_bad_seeds_rejected(seed0, tmp_path, seeds):
    with pytest.raises(ValueError):
        prepare(seed0[0], 3, tmp_path, "repeat", seeds, 1)


def test_root_state_fallback_requires_exact_selected_step(seed0, tmp_path):
    base, _ = seed0
    state = base / "checkpoint-3/trainer_state.json"
    state.rename(base / "trainer_state.json")
    assert prepare(base, 3, tmp_path, "repeat", [1], 1)
    with pytest.raises(ValueError, match="selected step"):
        prepare(base, 2, tmp_path, "repeat", [1], 1)


def test_callback_preserves_evaluation_and_rejects_horizon_or_epoch_mismatch():
    cb = SelectedStepCallback({"global_step": 3, "max_steps": 10, "epoch": 0.75},
                              {"world_size": 1, "warmup_steps": 2})
    args = SimpleNamespace(world_size=1, warmup_steps=2)
    state = SimpleNamespace(global_step=0, max_steps=10, epoch=0)
    control = TrainerControl(should_evaluate=True, should_save=True)
    cb.on_train_begin(args, state, control)
    state.global_step, state.epoch = 2, 0.5
    cb.on_step_end(args, state, control)
    assert control.should_evaluate and not control.should_save and not control.should_training_stop
    state.global_step, state.epoch = 3, 0.75
    cb.on_step_end(args, state, control)
    assert control.should_training_stop and control.should_evaluate
    cb.on_train_end(args, state, control)
    state.epoch = 0.8
    with pytest.raises(ValueError, match="exact selected"):
        cb.on_step_end(args, state, control)
    state.global_step, state.max_steps = 0, 3
    with pytest.raises(ValueError, match="scheduler horizon"):
        cb.on_train_begin(args, state, control)


def test_cli_dry_run_and_failure_isolation(seed0, tmp_path, monkeypatch):
    import cllpu.repeat_selected as module
    import subprocess

    calls = Mock(side_effect=subprocess.CalledProcessError(1, "train"))
    monkeypatch.setattr(module.subprocess, "run", calls)
    monkeypatch.setenv("WANDB_RUN_ID", "seed0")
    monkeypatch.setenv("WANDB_RESUME", "must")
    argv = ["--seed0-run", str(seed0[0]), "--selected-step", "3",
            "--output-root", str(tmp_path / "out"), "--run-name", "example"]
    main(argv + ["--dry-run"])
    assert not (tmp_path / "out").exists() and not calls.called
    with pytest.raises(subprocess.CalledProcessError):
        main(argv)
    assert calls.call_count == 1
    env = calls.call_args.kwargs["env"]
    assert "WANDB_RUN_ID" not in env and "WANDB_RESUME" not in env
    assert env["WANDB_NAME"] == "example-seed1"
    assert not (tmp_path / "out/example-seed2").exists()


@pytest.mark.parametrize("model", ["Llama-3.1-8B-Instruct", "Qwen2.5-14B-Instruct"])
@pytest.mark.parametrize("recipe,entry", [
    ("unlearn/multilingual/default", "unlearn"),
    ("eval/multilingual/common", "eval"),
    ("eval/multilingual/culture_origin", "eval"),
])
def test_documented_model_switch_routes_weights_and_template(model, recipe, entry):
    with initialize_config_dir(config_dir=str(RUNTIME / "configs"), version_base=None):
        cfg = compose(config_name=entry, overrides=[
            f"experiment={recipe}", f"model={model}", "target_model=example/selected",
            "task_name=model-switch",
        ])
    assert cfg.model.model_args.pretrained_model_name_or_path == "example/selected"
    assert cfg.model.tokenizer_args.pretrained_model_name_or_path == "example/selected"
    assert cfg.model.model_args.revision is None
    if model.startswith("Qwen"):
        assert cfg.model.template_args.append_eos_token is False
        assert cfg.model.template_args.asst_end_tag == "<|im_end|>\n"


def test_selected_stop_matches_full_horizon_parameters(tmp_path):
    """An early stop must match a full run at K, not a schedule shortened to K."""
    from transformers import Trainer, TrainerCallback, TrainingArguments

    class Model(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.weight = torch.nn.Parameter(torch.tensor([0.2, 0.7]))

        def forward(self, input_ids, labels):
            pred = input_ids.float() @ self.weight
            return {"loss": ((pred - labels) ** 2).mean(), "logits": pred}

    class Capture(TrainerCallback):
        def on_step_end(self, args, state, control, model=None, lr_scheduler=None, **kwargs):
            if state.global_step == 3:
                self.weight = model.weight.detach().clone()
                self.lr = lr_scheduler.get_last_lr()

    data = [{"input_ids": torch.tensor([i % 3, i % 2]), "labels": float(i % 4)} for i in range(8)]
    outcomes = []
    for name, horizon, stop in [("full", 4, False), ("repeat", 4, True), ("wrong", 3, False)]:
        args = TrainingArguments(output_dir=str(tmp_path / name), max_steps=horizon,
                                 per_device_train_batch_size=2, learning_rate=0.1,
                                 warmup_steps=1, report_to=[], save_strategy="no",
                                 use_cpu=True, disable_tqdm=True, seed=1)
        capture = Capture()
        callbacks = [capture]
        if stop:
            callbacks.append(SelectedStepCallback({"global_step": 3, "max_steps": 4, "epoch": 0.75},
                                                  {"world_size": 1, "warmup_steps": 1}))
        trainer = Trainer(model=Model(), args=args, train_dataset=data, callbacks=callbacks)
        trainer.train()
        outcomes.append(capture)
    torch.testing.assert_close(outcomes[0].weight, outcomes[1].weight, rtol=0, atol=0)
    assert outcomes[0].lr == outcomes[1].lr
    assert not torch.equal(outcomes[0].weight, outcomes[2].weight)


@pytest.mark.parametrize("method", ["finetune", "DrNPO"])
def test_real_qwen_entrypoint_selected_seeds(tmp_path, monkeypatch, method):
    """Load/save real tiny Qwen weights through the serial repetition CLI."""
    import os
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace
    from transformers import AutoModelForCausalLM, PreTrainedTokenizerFast, Qwen2Config, Qwen2ForCausalLM
    from cllpu.train import run_training

    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "")
    monkeypatch.setenv("TOKENIZERS_PARALLELISM", "false")
    monkeypatch.setenv("OMP_NUM_THREADS", "2")
    monkeypatch.setenv("PYTHONPATH", str(RUNTIME / "src") + os.pathsep + os.environ.get("PYTHONPATH", ""))
    monkeypatch.chdir(tmp_path)
    words = ["<pad>", "<unk>", "<eos>", "<system>", "<user>", "<assistant>", "Q", "A"]
    backend = Tokenizer(WordLevel(dict(zip(words, range(len(words)))), unk_token="<unk>"))
    backend.pre_tokenizer = Whitespace()
    tok = PreTrainedTokenizerFast(tokenizer_object=backend, pad_token="<pad>", unk_token="<unk>",
                                 eos_token="<eos>", additional_special_tokens=words[3:6])
    tok.chat_template = (
        "{% for m in messages %}{{ '<' + m['role'] + '> ' + m['content'] }}"
        "{% if m['role'] == 'assistant' %}{{ eos_token }}{% endif %}{{ '\n' }}{% endfor %}"
        "{% if add_generation_prompt %}{{ '<assistant> ' }}{% endif %}"
    )
    model_dir = tmp_path / "initial"
    tok.save_pretrained(model_dir)
    model = Qwen2ForCausalLM(Qwen2Config(vocab_size=len(tok), hidden_size=16, intermediate_size=32,
        num_hidden_layers=1, num_attention_heads=2, num_key_value_heads=2,
        pad_token_id=0, eos_token_id=2, max_position_embeddings=512))
    model.save_pretrained(model_dir)
    with (RUNTIME / "data/multilingual/qa_flat.en.jsonl").open() as f:
        core = [r for line in f if (r := json.loads(line))["variant_layer"] == "core"]
    rows = [r for role in ("target", "neighbor")
            for r in [x for x in core if x["topic_role"] == role][:4]]
    datafile = tmp_path / "qa.jsonl"
    datafile.write_text("".join(json.dumps(r) + "\n" for r in rows))
    base = tmp_path / "seed0"
    # Quoted forward-slash paths also work on Windows and in Unicode workspaces.
    model_path = json.dumps(model_dir.as_posix(), ensure_ascii=False)
    data_path = json.dumps(datafile.as_posix(), ensure_ascii=False)
    output_path = json.dumps(base.as_posix(), ensure_ascii=False)
    if method == "finetune":
        recipe = ["experiment=finetune/multilingual/default",
                  f"model.model_args.pretrained_model_name_or_path={model_path}",
                  f"model.tokenizer_args.pretrained_model_name_or_path={model_path}",
                  f"data.train.Multilingual_QA.args.data_files=[{data_path}]",
                  "data.train.Multilingual_QA.args.expected_count=8"]
    else:
        recipe = ["experiment=unlearn/multilingual/default", f"trainer={method}",
                  f"target_model={model_path}", "multilingual_source_language=en"]
        for split in ("forget", "retain"):
            recipe += [f"data.{split}.Multilingual_QA.args.data_files=[{data_path}]",
                       f"data.{split}.Multilingual_QA.args.expected_count=4"]
    with initialize_config_dir(config_dir=str(RUNTIME / "configs"), version_base=None):
        cfg = compose(config_name="train" if method == "finetune" else "unlearn", overrides=[
            *recipe, "model=Qwen2.5-14B-Instruct",
            "model.model_args.attn_implementation=eager", "model.model_args.torch_dtype=float32",
            "task_name=seed0", "trainer.args.eval_strategy=no", "trainer.args.do_eval=false",
            "trainer.args.eval_on_start=false",
            f"paths.output_dir={output_path}", "trainer.args.bf16=false", "trainer.args.bf16_full_eval=false",
            "trainer.args.optim=adamw_torch", "trainer.args.report_to=[]",
            "trainer.args.per_device_train_batch_size=2", "trainer.args.gradient_accumulation_steps=1",
            "trainer.args.warmup_epochs=0", "+trainer.args.warmup_steps=1",
            "+trainer.args.max_steps=4", "trainer.args.save_strategy=steps",
            "+trainer.args.save_steps=2", "+trainer.args.use_cpu=true", "save_final_model=false",
            "++post_train_eval=false",
        ])
    cfg.eval = None
    run_training(cfg)
    main(["--seed0-run", str(base), "--selected-step", "2", "--output-root", str(tmp_path / "out"),
          "--run-name", "tiny", "--seeds", "1", "2", "3", "4"])
    for seed in (1, 2, 3, 4):
        dest = tmp_path / f"out/tiny-seed{seed}"
        receipt = json.loads((dest / "REPEAT_COMPLETE.json").read_text())
        assert receipt["selected_step"] == 2 and receipt["scheduler_horizon"] == 4
        assert receipt["seed"] == seed
        assert [x.name for x in dest.glob("checkpoint-*")] == ["checkpoint-2"]
        saved = AutoModelForCausalLM.from_pretrained(dest / "checkpoint-2", local_files_only=True)
        assert all(torch.isfinite(p).all() for p in saved.parameters())
        assert any(not torch.equal(v, model.state_dict()[k]) for k, v in saved.state_dict().items())
