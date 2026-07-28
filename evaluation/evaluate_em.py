#!/usr/bin/env python3
"""Evaluate normalized exact-match accessibility and export numeric matrices."""

from __future__ import annotations

import argparse

from _common import (
    add_common_arguments,
    best_reference_score,
    normalize_answer,
    run_local_metric,
)


def score(record: dict, use_aliases: bool = False) -> float:
    return best_reference_score(
        record,
        lambda prediction, reference: float(
            normalize_answer(prediction) == normalize_answer(reference)
        ),
        use_aliases,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_arguments(parser, "em")
    args = parser.parse_args()
    run_local_metric(args, "em", lambda record: score(record, args.use_aliases))


if __name__ == "__main__":
    main()
