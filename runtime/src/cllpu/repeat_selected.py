"""Repeat a seed0 selection from the same initial model and scheduler horizon."""

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

from omegaconf import OmegaConf
from transformers import TrainerCallback


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def positive_int(value, name):
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def validate_frozen(value):
    if isinstance(value, dict):
        for item in value.values():
            validate_frozen(item)
    elif isinstance(value, list):
        for item in value:
            validate_frozen(item)
    elif isinstance(value, str) and ("${" in value or value == "???"):
        raise ValueError("Use a fully resolved seed0 config, without interpolations or missing values")


class SelectedStepCallback(TrainerCallback):
    """Keep the original LR schedule, but stop and save at the selected update."""

    def __init__(self, selection, context):
        self.step = selection["global_step"]
        self.horizon = selection["max_steps"]
        self.epoch = selection["epoch"]
        self.context = context

    def on_train_begin(self, args, state, control, **kwargs):
        if state.global_step != 0 or state.max_steps != self.horizon:
            raise ValueError("Training start/scheduler horizon differs from seed0")
        if args.world_size != self.context["world_size"]:
            raise ValueError("World size differs from seed0")
        if args.get_warmup_steps(state.max_steps) != self.context["warmup_steps"]:
            raise ValueError("Effective warmup steps differ from seed0")

    def on_step_end(self, args, state, control, **kwargs):
        control.should_save = False
        if state.global_step >= self.step:
            self.verify(state)
            control.should_training_stop = True
        return control

    def on_epoch_end(self, args, state, control, **kwargs):
        control.should_save = False
        return control

    def on_train_end(self, args, state, control, **kwargs):
        self.verify(state)

    def verify(self, state):
        if (state.global_step != self.step or state.max_steps != self.horizon
                or not math.isclose(state.epoch, self.epoch, rel_tol=0, abs_tol=1e-9)):
            raise ValueError("Training did not reach seed0's exact selected step/epoch")


def prepare(seed0_run, selected_step, output_root, run_name, seeds, nproc_per_node):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", run_name):
        raise ValueError("run-name must contain only letters, digits, '.', '_' or '-'")
    positive_int(selected_step, "selected-step")
    positive_int(nproc_per_node, "nproc-per-node")
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("Provide distinct, nonzero seeds")
    for seed in seeds:
        positive_int(seed, "seed")
        if seed >= 2**32:
            raise ValueError("seed must be smaller than 2**32")
    base = Path(seed0_run).expanduser().resolve()
    config_path = base / "resolved_config.yaml"
    context_path = base / "training_context.json"
    state_path = base / f"checkpoint-{selected_step}" / "trainer_state.json"
    if not state_path.is_file():
        state_path = base / "trainer_state.json"
    source = OmegaConf.to_container(OmegaConf.load(config_path), resolve=False)
    validate_frozen(source)
    context = json.loads(context_path.read_text())
    state = json.loads(state_path.read_text())
    for field in ("global_step", "max_steps"):
        positive_int(state[field], field)
    if state["global_step"] != selected_step or selected_step > state["max_steps"]:
        raise ValueError("The recorded trainer state does not match the selected step")
    if (type(state.get("epoch")) not in (int, float)
            or not math.isfinite(state["epoch"]) or state["epoch"] <= 0):
        raise ValueError("The selected trainer state must record a positive finite epoch")
    args = source["trainer"]["args"]
    if args.get("seed") != 0 or not args.get("do_train", True):
        raise ValueError("The input must describe a seed0 training run")
    if args.get("load_best_model_at_end", False):
        raise ValueError("load_best_model_at_end would replace the fixed selected weights")
    if args.get("push_to_hub", False):
        raise ValueError("Use a seed0 config with push_to_hub=false")
    if args.get("save_on_each_node", False):
        raise ValueError("This launcher supports one node with one saving rank")
    if "defaults" in source or "hydra" in source:
        raise ValueError("Use resolved_config.yaml, not a Hydra composition recipe")
    if positive_int(context["world_size"], "seed0 world_size") != nproc_per_node:
        raise ValueError("nproc-per-node must match seed0's recorded world size")
    if type(context["warmup_steps"]) is not int or context["warmup_steps"] < 0:
        raise ValueError("Missing/invalid effective seed0 warmup steps")
    cwd = Path(context["working_directory"])
    if not cwd.is_absolute() or not cwd.is_dir():
        raise ValueError("The seed0 working directory must still exist")
    root = Path(output_root).expanduser().resolve()
    evidence = {str(p): digest(p) for p in (config_path, context_path, state_path)}
    jobs = []
    for seed in seeds:
        name = f"{run_name}-seed{seed}"
        dest = root / name
        if dest.exists():
            raise ValueError(f"Output already exists: {dest}; use a new run-name")
        cfg = copy.deepcopy(source)
        changed = {}

        def change(keys, value):
            obj = cfg
            for k in keys[:-1]:
                obj = obj.setdefault(k, {})
            old = obj.get(keys[-1])
            if old != value:
                changed[".".join(keys)] = {"before": old, "after": value}
            obj[keys[-1]] = value

        change(["trainer", "args", "seed"], seed)
        change(["task_name"], name)
        change(["paths", "output_dir"], str(dest))
        for field, value in (("output_dir", str(dest)), ("logging_dir", str(dest / "logs")),
                             ("run_name", name)):
            change(["trainer", "args", field], value)
        # The selected model is saved explicitly after verifying its state.
        change(["save_final_model"], False)
        for name, evaluator in (cfg.get("eval") or {}).items():
            if isinstance(evaluator, dict) and "output_dir" in evaluator:
                change(["eval", name, "output_dir"], str(dest / "eval" / name))
        manifest = {
            "seed": seed, "seed0_run": str(base), "source_sha256": evidence,
            "selection": {k: state[k] for k in ("global_step", "max_steps", "epoch")},
            "context": context, "changes": changed,
        }
        prefix = [sys.executable, "-m", "cllpu.repeat_selected"]
        if nproc_per_node > 1:
            prefix = [sys.executable, "-m", "torch.distributed.run", "--standalone",
                      f"--nproc_per_node={nproc_per_node}", "-m", "cllpu.repeat_selected"]
        jobs.append((dest, cfg, manifest, [*prefix, "--worker", str(dest)]))
    return jobs


def run_worker(directory):
    from cllpu.train import run_training

    directory = Path(directory).resolve()
    manifest = json.loads((directory / "REPETITION.json").read_text())
    config_path = directory / "repeat_config.yaml"
    if digest(config_path) != manifest["config_sha256"]:
        raise ValueError("Prepared repeat configuration changed")
    for path, expected in manifest["source_sha256"].items():
        if digest(path) != expected:
            raise ValueError(f"Seed0 evidence changed: {path}")
    os.chdir(manifest["context"]["working_directory"])
    callback = SelectedStepCallback(manifest["selection"], manifest["context"])
    trainer = run_training(OmegaConf.load(config_path), callbacks=[callback])
    callback.verify(trainer.state)
    checkpoint = directory / f"checkpoint-{callback.step}"
    trainer.save_model(str(checkpoint))
    if trainer.args.should_save:
        trainer.tokenizer.save_pretrained(checkpoint)
        trainer.state.save_to_json(str(checkpoint / "trainer_state.json"))
    trainer.accelerator.wait_for_everyone()
    if trainer.args.should_save:
        (directory / "REPEAT_COMPLETE.json").write_text(json.dumps({
            "status": "passed", "seed": manifest["seed"],
            "selected_step": trainer.state.global_step, "epoch": trainer.state.epoch,
            "scheduler_horizon": trainer.state.max_steps, "checkpoint": str(checkpoint),
            "config_sha256": manifest["config_sha256"],
        }, indent=2) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed0-run", type=Path)
    parser.add_argument("--selected-step", type=int)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--run-name")
    parser.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3, 4])
    parser.add_argument("--nproc-per-node", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        run_worker(args.worker)
        return
    if any(v is None for v in (args.seed0_run, args.selected_step, args.output_root, args.run_name)):
        parser.error("--seed0-run, --selected-step, --output-root and --run-name are required")
    try:
        jobs = prepare(args.seed0_run, args.selected_step, args.output_root, args.run_name,
                       args.seeds, args.nproc_per_node)
    except (ValueError, KeyError, OSError) as exc:
        parser.error(str(exc))
    for dest, cfg, manifest, command in jobs:
        print(json.dumps(manifest, indent=2), flush=True)
        print(shlex.join(command), flush=True)
        if args.dry_run:
            continue
        dest.mkdir(parents=True, exist_ok=False)
        config_path = dest / "repeat_config.yaml"
        OmegaConf.save(OmegaConf.create(cfg), config_path)
        manifest["config_sha256"] = digest(config_path)
        (dest / "REPETITION.json").write_text(json.dumps(manifest, indent=2) + "\n")
        env = os.environ.copy()
        env.pop("WANDB_RUN_ID", None)
        env.pop("WANDB_RESUME", None)
        env["WANDB_NAME"] = dest.name
        subprocess.run(command, env=env, cwd=manifest["context"]["working_directory"], check=True)


if __name__ == "__main__":
    main()
