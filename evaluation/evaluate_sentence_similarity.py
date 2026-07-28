#!/usr/bin/env python3
"""Evaluate BGE-M3 cosine similarity accessibility and export numeric matrices."""

from __future__ import annotations

import argparse

from _common import add_common_arguments, aggregate_and_write, read_records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_arguments(parser, "sentence_similarity")
    parser.add_argument(
        "--model",
        default="BAAI/bge-m3",
        help="SentenceTransformers-compatible embedding model.",
    )
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument(
        "--device",
        default=None,
        help="Embedding device, for example cuda or cpu.",
    )
    args = parser.parse_args()

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise SystemExit(
            "sentence-transformers is required: "
            "python -m pip install sentence-transformers"
        ) from exc

    records = read_records(args.input)
    model = SentenceTransformer(args.model, device=args.device)
    predictions = [record["prediction"] for record in records]
    reference_lists = [
        (
            [record["expected_answer"], *record["answer_aliases"]]
            if args.use_aliases
            else [record["expected_answer"]]
        )
        for record in records
    ]
    flat_references = [reference for refs in reference_lists for reference in refs]
    prediction_embeddings = model.encode(
        predictions,
        batch_size=args.batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    reference_embeddings = model.encode(
        flat_references,
        batch_size=args.batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    scores: list[float] = []
    offset = 0
    for prediction_embedding, references in zip(
        prediction_embeddings, reference_lists
    ):
        count = len(references)
        candidates = reference_embeddings[offset : offset + count]
        scores.append(
            max(float(prediction_embedding @ candidate) for candidate in candidates)
        )
        offset += count

    aggregate_and_write(
        records,
        scores,
        "sentence_similarity",
        args.output_dir,
        args.languages,
        args.allow_incomplete,
    )
    print(
        f"Wrote sentence_similarity numeric results for {len(records)} QAs "
        f"to {args.output_dir}"
    )


if __name__ == "__main__":
    main()
