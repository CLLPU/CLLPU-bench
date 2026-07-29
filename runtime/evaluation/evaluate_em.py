#!/usr/bin/env python3
"""Compatibility entry point for strict saved-generation Exact Match."""

from cllpu.saved_generation_evaluation import main


if __name__ == "__main__":
    raise SystemExit(main("em"))
