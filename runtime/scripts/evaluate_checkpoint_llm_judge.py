#!/usr/bin/env python3
"""Evaluate saved generations with the resumable five-level semantic judge."""

from run_semantic_evaluation import main


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
