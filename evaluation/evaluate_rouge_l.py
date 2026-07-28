#!/usr/bin/env python3
"""Evaluate multilingual ROUGE-L F1 accessibility and export numeric matrices."""

from __future__ import annotations

import argparse

from _common import add_common_arguments, best_reference_score, rouge_l_f1, run_local_metric


def score(record: dict, use_aliases: bool = False) -> float:
    return best_reference_score(record, rouge_l_f1, use_aliases)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_arguments(parser, "rouge_l")
    args = parser.parse_args()
    run_local_metric(args, "rouge_l", lambda record: score(record, args.use_aliases))


if __name__ == "__main__":
    main()
