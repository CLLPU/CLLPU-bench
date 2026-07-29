#!/usr/bin/env python3
"""Evaluate saved generations with the pinned BGE-M3 embedding protocol."""

from run_embedding_evaluation import main


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
