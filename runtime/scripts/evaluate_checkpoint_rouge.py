#!/usr/bin/env python3
"""Evaluate saved generations with multilingual ROUGE-L."""

from cllpu.saved_generation_evaluation import main


if __name__ == "__main__":
    raise SystemExit(main("rouge"))
