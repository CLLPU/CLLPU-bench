import os
from pathlib import Path

from hydra import compose, initialize_config_dir

from cllpu.config_paths import hydra_config_path


CONFIG_DIR = Path(__file__).resolve().parents[1] / "configs"


def test_hydra_entrypoint_uses_absolute_config_path():
    path = hydra_config_path()
    assert os.path.isabs(path)
    assert Path(path).resolve() == CONFIG_DIR.resolve()


def compose_config(config_name: str, overrides: list[str]):
    with initialize_config_dir(version_base=None, config_dir=str(CONFIG_DIR)):
        return compose(config_name=config_name, overrides=overrides)


def test_finetune_config_uses_official_meta_model():
    cfg = compose_config(
        "train.yaml",
        ["experiment=finetune/multilingual/default", "task_name=test"],
    )
    assert cfg.model.model_args.pretrained_model_name_or_path == (
        "meta-llama/Meta-Llama-3.1-8B-Instruct"
    )
    assert cfg.model.model_args.revision == "0e9e39f249a16976918f6564b8830bc894c89659"
    assert cfg.model.model_args.attn_implementation == "flash_attention_2"
    assert cfg.data.train.Multilingual_QA.args.expected_count == 16000
    assert cfg.save_final_model is True


def test_finetune_public_save_override_composes():
    cfg = compose_config(
        "train.yaml",
        [
            "experiment=finetune/multilingual/default",
            "task_name=test",
            "save_final_model=false",
        ],
    )
    assert cfg.save_final_model is False


def test_retain_reference_config_matches_target_sft_except_data_role():
    target = compose_config(
        "train.yaml",
        ["experiment=finetune/multilingual/default", "task_name=target"],
    )
    retain = compose_config(
        "train.yaml",
        ["experiment=finetune/multilingual/retain_reference", "task_name=retain"],
    )
    target_data = target.data.train.Multilingual_QA.args
    retain_data = retain.data.train.Multilingual_QA.args
    assert retain.model == target.model
    for name in (
        "per_device_train_batch_size",
        "gradient_accumulation_steps",
        "learning_rate",
        "weight_decay",
        "warmup_epochs",
        "num_train_epochs",
        "optim",
        "seed",
        "do_eval",
        "eval_on_start",
        "eval_strategy",
    ):
        assert retain.trainer.args[name] == target.trainer.args[name]
    assert retain_data.data_files == target_data.data_files
    assert list(retain_data.languages) == list(target_data.languages)
    assert list(retain_data.variant_layers) == ["core"]
    assert list(retain_data.topic_roles) == ["neighbor"]
    assert retain_data.expected_count == 8000


def test_common_unlearning_config_composes_for_each_method():
    method_defaults = {
        "SimNPO": ("delta", 1),
        "DrNPO": ("beta_dv_forget", 2),
        "DrSimNPO": ("sigma_forget", 2),
    }
    for trainer in ("GradAscent", "GradDiff", "NPO", "SimNPO", "DrNPO", "DrSimNPO"):
        cfg = compose_config(
            "unlearn.yaml",
            [
                "experiment=unlearn/multilingual/default",
                f"trainer={trainer}",
                "model=Llama-3.1-8B-Instruct",
                "target_model=example/target-model",
                "multilingual_source_language=ja",
                "task_name=test",
            ],
        )
        assert cfg.trainer.handler == trainer
        assert "per_device_eval_batch_size" not in cfg.trainer.args
        assert cfg.model.model_args.pretrained_model_name_or_path == "example/target-model"
        assert cfg.model.tokenizer_args.pretrained_model_name_or_path == "example/target-model"
        assert cfg.data.forget.Multilingual_QA.args.languages == "ja"
        assert cfg.data.forget.Multilingual_QA.args.data_files == [
            "runtime/data/multilingual/qa_flat.ja.jsonl"
        ]
        assert cfg.data.forget.Multilingual_QA.args.topic_roles == "target"
        assert cfg.data.forget.Multilingual_QA.args.variant_layers == "core"
        assert cfg.data.forget.Multilingual_QA.args.expected_count == 500
        assert cfg.data.retain.Multilingual_QA.args.data_files == [
            "runtime/data/multilingual/qa_flat.ja.jsonl"
        ]
        assert cfg.data.retain.Multilingual_QA.args.languages == "ja"
        assert cfg.data.retain.Multilingual_QA.args.topic_roles == "neighbor"
        assert cfg.data.retain.Multilingual_QA.args.variant_layers == "core"
        assert cfg.data.retain.Multilingual_QA.args.expected_count == 500
        eval_dataset = cfg.eval.multilingual.metrics.accessibility.datasets.Multilingual_QA.args
        assert eval_dataset.expected_count == 4000
        assert eval_dataset.data_files == [
            "runtime/data/multilingual/qa_flat.ja.jsonl"
        ]
        assert eval_dataset.languages == "ja"
        assert list(eval_dataset.topic_roles) == ["target", "neighbor"]
        assert list(eval_dataset.variant_layers) == ["core", "surface"]
        if trainer in method_defaults:
            parameter, expected = method_defaults[trainer]
            assert cfg.trainer.method_args[parameter] == expected
        assert dict(cfg.eval.multilingual.metrics.accessibility.variant_weights) == {
            "core": 0.25,
            "surface": 0.75,
        }
        assert cfg.post_train_eval is False


def test_culture_origin_config_composes():
    cfg = compose_config(
        "unlearn.yaml",
        [
            "experiment=unlearn/multilingual/culture_origin",
            "target_model=example/target-model",
            "multilingual_culture_origin=bn",
            "multilingual_culture_forget_expected_count=27",
            "multilingual_culture_retain_expected_count=27",
            "multilingual_culture_monitor_expected_count=216",
            "task_name=test",
        ],
    )
    assert "per_device_eval_batch_size" not in cfg.trainer.args
    assert cfg.data.forget.Multilingual_QA.args.culture_origins == "bn"
    assert cfg.data.forget.Multilingual_QA.args.data_files == [
        "runtime/data/multilingual/train_splits/culture_origin/bn_forget_target_core.jsonl"
    ]
    assert cfg.data.forget.Multilingual_QA.args.languages == "bn"
    assert cfg.data.forget.Multilingual_QA.args.topic_roles == "target"
    assert cfg.data.forget.Multilingual_QA.args.variant_layers == "core"
    assert cfg.data.forget.Multilingual_QA.args.expected_count == 27
    assert cfg.data.retain.Multilingual_QA.args.data_files == [
        "runtime/data/multilingual/train_splits/culture_origin/bn_retain_neighbor_core.jsonl"
    ]
    assert cfg.data.retain.Multilingual_QA.args.languages == "bn"
    assert cfg.data.retain.Multilingual_QA.args.topic_roles == "neighbor"
    assert cfg.data.retain.Multilingual_QA.args.variant_layers == "core"
    assert cfg.data.retain.Multilingual_QA.args.expected_count == 27
    eval_dataset = cfg.eval.multilingual.metrics.accessibility.datasets.Multilingual_QA.args
    assert eval_dataset.expected_count == 216
    assert eval_dataset.languages == "bn"
    assert eval_dataset.data_files == [
        "runtime/data/multilingual/train_splits/culture_origin/bn_source_monitor_core_surface.jsonl"
    ]
    assert eval_dataset.dataset_families == "culture_specific"
    assert eval_dataset.culture_origins == "bn"
    assert list(eval_dataset.topic_roles) == ["target", "neighbor"]
    assert list(eval_dataset.variant_layers) == ["core", "surface"]
    assert cfg.post_train_eval is False


def test_full_eval_config_composes():
    cfg = compose_config(
        "eval.yaml",
        [
            "experiment=eval/multilingual/default",
            "target_model=example/target-model",
            "task_name=test",
        ],
    )
    assert cfg.eval.multilingual.handler == "MultilingualEvaluator"
    dataset = cfg.eval.multilingual.metrics.accessibility.datasets.Multilingual_QA.args
    assert dataset.expected_count == 64000
    assert dataset.data_files == [
        "runtime/data/multilingual/train_splits/eval_common_plus_culture_all.jsonl"
    ]
    assert cfg.eval.multilingual.overwrite is True


def test_common_eval_config_composes():
    cfg = compose_config(
        "eval.yaml",
        [
            "experiment=eval/multilingual/common",
            "target_model=example/target-model",
            "task_name=test",
        ],
    )
    dataset = cfg.eval.multilingual.metrics.accessibility.datasets.Multilingual_QA.args
    assert dataset.expected_count == 40000
    assert len(dataset.data_files) == 10


def test_culture_origin_full_eval_remains_separate_from_training_screening():
    cfg = compose_config(
        "eval.yaml",
        [
            "experiment=eval/multilingual/culture_origin",
            "target_model=example/target-model",
            "multilingual_culture_origin=bn",
            "multilingual_culture_eval_expected_count=2160",
            "task_name=test",
        ],
    )
    dataset = cfg.eval.multilingual.metrics.accessibility.datasets.Multilingual_QA.args
    assert dataset.data_files == [
        "runtime/data/multilingual/train_splits/culture_origin/"
        "bn_eval_all_languages_core_surface.jsonl"
    ]
    assert dataset.languages is None
    assert dataset.culture_origins == "bn"
    assert dataset.expected_count == 2160
