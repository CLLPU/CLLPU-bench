#!/usr/bin/env python3
"""Add BGE-M3 dense cosine scores to saved multilingual generations."""

from __future__ import annotations

import argparse
import hashlib
import json
from importlib.metadata import version
from pathlib import Path

from huggingface_hub import snapshot_download

from cllpu.evals.embedding import (
    BGEM3DenseEncoder,
    DEFAULT_ENCODER,
    DEFAULT_ENCODER_REVISION,
    METRIC_NAME,
    PROTOCOL_VERSION,
    VARIANT_WEIGHTS,
    metric_definition,
    score_records,
    validate_records,
)
from cllpu.evals.metrics.multilingual import build_accessibility_summary
from cllpu.evals.multilingual_outputs import (
    build_eval_payload,
    save_multilingual_eval_outputs,
    write_json_atomic,
)


def read_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path}:{line_number}: {exc}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"Record in {path}:{line_number} must be an object")
            records.append(item)
    if not records:
        raise ValueError(f"No records found in {path}")
    return records


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_input(value: Path) -> Path:
    path = value / "generations.jsonl" if value.is_dir() else value
    if not path.is_file():
        raise FileNotFoundError(f"Missing generations JSONL: {path}")
    return path.resolve()


def resolve_encoder(value: str, revision: str | None, cache_dir: Path | None) -> str:
    local = Path(value).expanduser()
    if local.exists():
        if not local.is_dir():
            raise ValueError(f"Encoder path is not a directory: {local}")
        return str(local.resolve())
    return snapshot_download(repo_id=value, revision=revision, cache_dir=cache_dir)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("input", type=Path, help="Evaluation directory or generations.jsonl")
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument("--encoder", default=DEFAULT_ENCODER, help="Hub ID or local directory")
    result.add_argument("--encoder-revision", default=DEFAULT_ENCODER_REVISION)
    result.add_argument("--cache-dir", type=Path, default=None)
    result.add_argument("--device", default="cuda:0")
    result.add_argument("--batch-size", type=int, default=32)
    result.add_argument("--tokenization-batch-size", type=int, default=256)
    result.add_argument("--max-length", type=int, default=512)
    result.add_argument("--use-fp16", action="store_true")
    result.add_argument("--overwrite", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    input_path = resolve_input(args.input)
    output_dir = args.output_dir.resolve()
    if output_dir == input_path.parent:
        raise SystemExit("--output-dir must differ from the source evaluation directory")
    if output_dir.exists() and any(output_dir.iterdir()) and not args.overwrite:
        raise SystemExit(f"Output directory is not empty: {output_dir}")
    if min(args.batch_size, args.tokenization_batch_size, args.max_length) <= 0:
        raise SystemExit("Batch sizes and max length must be positive")

    records = read_jsonl(input_path)
    validate_records(records, input_path=input_path)
    encoder_source = resolve_encoder(args.encoder, args.encoder_revision, args.cache_dir)
    encoder = BGEM3DenseEncoder(
        encoder_source,
        device=args.device,
        use_fp16=args.use_fp16,
    )
    scored, audit = score_records(
        records,
        encoder=encoder,
        batch_size=args.batch_size,
        tokenization_batch_size=args.tokenization_batch_size,
        max_length=args.max_length,
    )
    # Report only the embedding metric here so this optional pass cannot
    # silently rewrite Exact/ROUGE aggregate outputs from the source run.
    metric_names = (METRIC_NAME,)
    summary = build_accessibility_summary(
        scored,
        metric_names,
        variant_weights=VARIANT_WEIGHTS,
        renormalize_variant_weights=True,
    )
    definition = metric_definition(
        args.max_length,
        encoder=args.encoder,
        encoder_revision=args.encoder_revision,
    )
    summary["metric_definitions"][METRIC_NAME] = definition
    output_dir.mkdir(parents=True, exist_ok=True)
    save_multilingual_eval_outputs(
        output_dir,
        scored,
        metric_names=metric_names,
        eval_payload=build_eval_payload(scored, metric_names),
        summary_payload=summary,
    )
    write_json_atomic(
        output_dir / "EMBEDDING_PROTOCOL.json",
        {
            "protocol_version": PROTOCOL_VERSION,
            "input": str(input_path),
            "input_sha256": file_sha256(input_path),
            "encoder": args.encoder,
            "encoder_revision": args.encoder_revision,
            "resolved_encoder": encoder_source,
            "software_versions": {
                "FlagEmbedding": version("FlagEmbedding"),
                "huggingface_hub": version("huggingface-hub"),
                "numpy": version("numpy"),
                "torch": version("torch"),
                "transformers": version("transformers"),
            },
            "device": args.device,
            "use_fp16": args.use_fp16,
            "batch_size": args.batch_size,
            "tokenization_batch_size": args.tokenization_batch_size,
            "max_length": args.max_length,
            "metric_definition": definition,
            "variant_weights": VARIANT_WEIGHTS,
            "audit": audit,
        },
    )
    print(f"COMPLETE records={len(scored)} metric={METRIC_NAME} output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
