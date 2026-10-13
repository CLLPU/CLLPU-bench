import hydra
import json
import logging
import os
from pathlib import Path

from omegaconf import DictConfig, OmegaConf
from omegaconf.errors import OmegaConfBaseException
from transformers import TrainerCallback

from cllpu.config_paths import hydra_config_path
from cllpu.data import get_collators, get_data
from cllpu.evals import get_evaluators
from cllpu.model import get_model
from cllpu.trainer import load_trainer
from cllpu.trainer.utils import seed_everything


class TrainingContextCallback(TrainerCallback):
    """Record effective schedule metadata once Trainer has computed its horizon."""

    def on_train_begin(self, args, state, control, **kwargs):
        if args.should_save:
            output = Path(args.output_dir)
            output.mkdir(parents=True, exist_ok=True)
            (output / "training_context.json").write_text(json.dumps({
                "working_directory": os.getcwd(),
                "world_size": args.world_size,
                "warmup_steps": args.get_warmup_steps(state.max_steps),
            }, indent=2) + "\n", encoding="utf-8")


@hydra.main(
    version_base=None,
    config_path=hydra_config_path(),
    config_name="train.yaml",
)
def main(cfg: DictConfig):
    return run_training(cfg)


def run_training(cfg: DictConfig, callbacks=()):
    """Entry point of the code to train models
    Args:
        cfg (DictConfig): Config to train
    """
    try:
        snapshot = OmegaConf.to_container(cfg, resolve=True, throw_on_missing=True)
    except OmegaConfBaseException:
        # Unused unresolved options must not break an existing training recipe.
        snapshot = None
        logging.getLogger(__name__).warning(
            "Could not freeze all config values; selected seed repetition metadata is unavailable"
        )
    seed_everything(cfg.trainer.args.seed)
    mode = cfg.get("mode", "train")

    model_cfg = cfg.model
    template_args = model_cfg.template_args
    assert model_cfg is not None, "Invalid model yaml passed in train config."
    model, tokenizer = get_model(model_cfg)

    # Load Dataset
    data_cfg = cfg.data
    data = get_data(
        data_cfg, mode=mode, tokenizer=tokenizer, template_args=template_args
    )

    # Load collator
    collator_cfg = cfg.collator
    collator = get_collators(collator_cfg, tokenizer=tokenizer)


    # Get Trainer
    trainer_cfg = cfg.trainer
    assert trainer_cfg is not None, ValueError("Please set trainer")

    # Get Evaluators
    evaluators = None
    eval_cfgs = cfg.get("eval", None)
    if eval_cfgs:
        evaluators = get_evaluators(
            eval_cfgs=eval_cfgs,
            template_args=template_args,
            model=model,
            tokenizer=tokenizer,
        )

    trainer, trainer_args = load_trainer(
        trainer_cfg=trainer_cfg,
        model=model,
        train_dataset=data.get("train", None),
        eval_dataset=data.get("eval", None),
        tokenizer=tokenizer,
        data_collator=collator,
        evaluators=evaluators,
        template_args=template_args,
    )

    for callback in callbacks:
        trainer.add_callback(callback)

    if trainer_args.should_save and snapshot is not None:
        output = Path(trainer_args.output_dir)
        output.mkdir(parents=True, exist_ok=True)
        OmegaConf.save(OmegaConf.create(snapshot), output / "resolved_config.yaml")
    if snapshot is not None:
        trainer.add_callback(TrainingContextCallback())

    if trainer_args.do_train:
        trainer.train()
        trainer.save_state()
        if cfg.get("save_final_model", True):
            trainer.save_model(trainer_args.output_dir)

    if cfg.get("post_train_eval", trainer_args.do_eval):
        trainer.evaluate(metric_key_prefix="eval")
    return trainer


if __name__ == "__main__":
    main()
