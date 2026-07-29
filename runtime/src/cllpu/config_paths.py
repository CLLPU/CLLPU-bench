"""Locate the canonical Hydra configuration tree in source and wheel installs."""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path


DIST_NAME = "cllpu"
INSTALLED_CONFIG_PATH = Path("share/cllpu/configs")


def get_config_dir() -> Path:
    override = os.environ.get("CROSS_LINGUAL_CONFIG_DIR")
    if override:
        path = Path(override).expanduser().resolve()
    else:
        module_path = Path(__file__).resolve()
        source_path = module_path.parents[2] / "configs"
        if module_path.parents[1].name == "src" and (source_path / "train.yaml").is_file():
            path = source_path
        else:
            try:
                path = Path(distribution(DIST_NAME).locate_file(INSTALLED_CONFIG_PATH)).resolve()
            except PackageNotFoundError as exc:
                raise RuntimeError(
                    "Cannot locate benchmark configs; set CROSS_LINGUAL_CONFIG_DIR"
                ) from exc
    if not (path / "train.yaml").is_file() or not (path / "eval.yaml").is_file():
        raise RuntimeError(f"Invalid benchmark config directory: {path}")
    return path


def hydra_config_path() -> str:
    """Return an absolute path accepted by Hydra in source and wheel installs."""
    return str(get_config_dir())
