#!/usr/bin/env python3
"""Compatibility entry point for the resumable five-level semantic judge."""

from pathlib import Path
import sys


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from run_semantic_evaluation import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
