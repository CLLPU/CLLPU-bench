"""Run one user-defined experiment sequentially with seeds 1, 2, 3, and 4."""

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

from hydra.core.override_parser.overrides_parser import OverridesParser


SEEDS = (1, 2, 3, 4)
OWNED_KEYS = {
    "trainer.args.seed", "trainer.args.output_dir", "trainer.args.logging_dir",
    "trainer.args.run_name", "paths.output_dir", "task_name", "hydra.run.dir",
}


def build_commands(overrides, output_root, run_name, nproc_per_node=1, config_name="unlearn"):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", run_name):
        raise ValueError("run-name must contain only letters, digits, '.', '_' or '-'")
    if nproc_per_node < 1:
        raise ValueError("nproc-per-node must be positive")
    if not overrides:
        raise ValueError("Supply experiment/model/trainer overrides after --")
    parsed = OverridesParser.create().parse_overrides(overrides)
    for override in parsed:
        key = override.get_key_element().lstrip("+~")
        if override.is_sweep_override():
            raise ValueError("Pass one experiment at a time, without Hydra sweep values")
        if key in OWNED_KEYS or (
            isinstance(override.value(), dict)
            and any(owned.startswith(key + ".") for owned in OWNED_KEYS)
        ):
            raise ValueError(f"The seed launcher owns {key}; remove this override")
    root = Path(output_root).expanduser().resolve()
    prefix = [sys.executable, "-m", "cllpu.train"]
    if nproc_per_node > 1:
        prefix = [sys.executable, "-m", "torch.distributed.run", "--standalone",
                  f"--nproc_per_node={nproc_per_node}", "-m", "cllpu.train"]
    runs = []
    for seed in SEEDS:
        name = f"{run_name}-seed{seed}"
        destination = root / name
        command = [
            *prefix, "--config-name", config_name, *overrides,
            f"trainer.args.seed={seed}",
            f"task_name={name}",
            "++paths.output_dir=" + json.dumps(str(destination)),
            "++trainer.args.output_dir=" + json.dumps(str(destination)),
            "++trainer.args.logging_dir=" + json.dumps(str(destination / "logs")),
            f"++trainer.args.run_name={name}",
            "hydra.run.dir=" + json.dumps(str(destination)),
        ]
        runs.append((destination, command))
    return runs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--nproc-per-node", type=int, default=1)
    parser.add_argument("--config-name", choices=("train", "unlearn"), default="unlearn")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("overrides", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    overrides = args.overrides
    if overrides[:1] == ["--"]:
        overrides = overrides[1:]
    try:
        runs = build_commands(overrides, args.output_root, args.run_name,
                              args.nproc_per_node, args.config_name)
        if not args.dry_run:
            for destination, _ in runs:
                if destination.exists():
                    raise ValueError(f"Output already exists: {destination}; use a new run-name")
    except ValueError as exc:
        parser.error(str(exc))
    for destination, command in runs:
        print(shlex.join(command), flush=True)
        if args.dry_run:
            continue
        # Reserve output atomically; a failed run is retained for inspection.
        destination.mkdir(parents=True, exist_ok=False)
        env = os.environ.copy()
        env.pop("WANDB_RUN_ID", None)
        env.pop("WANDB_RESUME", None)
        env["WANDB_NAME"] = destination.name
        subprocess.run(command, env=env, check=True)


if __name__ == "__main__":
    main()
