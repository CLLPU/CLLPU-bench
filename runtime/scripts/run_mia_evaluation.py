#!/usr/bin/env python3
"""Run the paper's four MIA attacks in the unlearned source language."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from cllpu.data.collators import DataCollatorForSupervisedDataset
from cllpu.data.multilingual_qa import MultilingualQADataset
from cllpu.evals.mia import (
    ATTACK_NAMES,
    evaluate_attacks,
    require_mia_dependencies,
)


LANGUAGES = ("ar", "bn", "de", "en", "es", "fr", "ja", "sw", "th", "zh")
CULTURE_COUNTS = {"ar": 33, "bn": 27, **{name: 30 for name in LANGUAGES if name not in {"ar", "bn"}}}


def dtype(name: str):
    return {"float32": torch.float32, "float16": torch.float16, "bfloat16": torch.bfloat16}[name]


def resolve_data_file(root: Path, value: Path) -> Path:
    path = value if value.is_absolute() else root / value
    if not path.is_file():
        raise FileNotFoundError(f"MIA data file not found: {path}")
    return path.resolve()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_reference(value: str) -> str:
    local = Path(value).expanduser()
    return str(local.resolve()) if local.exists() else value


def paper_data_spec(args: argparse.Namespace) -> dict:
    if args.dataset == "common":
        return {
            "member_file": Path(f"multilingual/qa_flat.{args.source_language}.jsonl"),
            "member_role": "target",
            "member_family": None,
            "member_origin": None,
            "member_count": 500,
            "holdout_file": Path(
                f"multilingual/common_holdout/qa_flat.{args.source_language}.jsonl"
            ),
            "holdout_role": "holdout",
            "holdout_family": "holdout",
            "holdout_count": 500,
        }
    return {
        "member_file": Path(
            f"multilingual/train_splits/culture_origin/{args.source_language}_eval_all_languages_core_surface.jsonl"
        ),
        "member_role": "target",
        "member_family": "culture_specific",
        "member_origin": args.source_language,
        "member_count": CULTURE_COUNTS[args.source_language],
        "holdout_file": Path(
            f"multilingual/culture_holdout/qa_flat.{args.source_language}.jsonl"
        ),
        "holdout_role": "culture_holdout",
        "holdout_family": "culture_holdout",
        "holdout_count": 300,
    }


def protocol_payload(
    args: argparse.Namespace,
    spec: dict,
    member_file: Path,
    holdout_file: Path,
    member_count: int,
    holdout_count: int,
) -> dict:
    tokenizer_source = args.tokenizer or args.model
    return {
        "name": "multilingual_source_language_mia_v1",
        "dataset_family": args.dataset,
        "source_language": args.source_language,
        "evaluation_language": args.source_language,
        "member": {
            "file": str(member_file),
            "sha256": file_sha256(member_file),
            "expected_count": member_count,
            "topic_role": spec["member_role"],
            "dataset_family": spec["member_family"],
            "culture_origin": spec["member_origin"],
        },
        "holdout": {
            "file": str(holdout_file),
            "sha256": file_sha256(holdout_file),
            "expected_count": holdout_count,
            "topic_role": spec["holdout_role"],
            "dataset_family": spec["holdout_family"],
        },
        "model": {
            "name_or_path": model_reference(args.model),
            "revision": args.model_revision,
            "tokenizer_name_or_path": model_reference(tokenizer_source),
            "tokenizer_revision": args.tokenizer_revision or args.model_revision,
        },
        "chat_template": {
            "system_prompt": args.system_prompt,
            "date_string": args.date_string,
        },
        "runtime": {
            "torch_dtype": args.torch_dtype,
            "attn_implementation": args.attn_implementation,
            "device_map": args.device_map,
            "batch_size": args.batch_size,
            "min_k_plus_plus_batch_size": args.min_k_plus_plus_batch_size,
        },
        "variant_layer": "core",
        "max_length": args.max_length,
        "k": args.k,
        "attacks": list(ATTACK_NAMES),
    }


def read_report(path: Path) -> dict:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read existing MIA report {path}: {exc}") from exc
    if not isinstance(report, dict):
        raise SystemExit(f"Existing MIA report is not a JSON object: {path}")
    return report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--model", required=True, help="Hugging Face model ID or local checkpoint")
    result.add_argument("--tokenizer", default=None, help="Defaults to --model")
    result.add_argument("--model-revision", default=None)
    result.add_argument("--tokenizer-revision", default=None)
    result.add_argument("--data-root", type=Path, default=Path("runtime/data"))
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument("--dataset", choices=("common", "culture"), required=True)
    result.add_argument("--source-language", choices=LANGUAGES, required=True)
    result.add_argument("--member-file", type=Path, default=None)
    result.add_argument("--holdout-file", type=Path, default=None)
    result.add_argument("--member-expected-count", type=int, default=None)
    result.add_argument("--holdout-expected-count", type=int, default=None)
    result.add_argument("--batch-size", type=int, default=32)
    result.add_argument("--min-k-plus-plus-batch-size", type=int, default=32)
    result.add_argument("--max-length", type=int, default=512)
    result.add_argument("--k", type=float, default=0.4)
    result.add_argument("--torch-dtype", choices=("float32", "float16", "bfloat16"), default="bfloat16")
    result.add_argument("--device-map", default="cuda")
    result.add_argument("--attn-implementation", default="flash_attention_2")
    result.add_argument("--system-prompt", default="You are a helpful assistant.")
    result.add_argument("--date-string", default="10 Apr 2025")
    result.add_argument("--overwrite", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    output_dir = args.output_dir.resolve()
    report_path = output_dir / "MIA_REPORT.json"
    if min(args.batch_size, args.min_k_plus_plus_batch_size, args.max_length) <= 0:
        raise SystemExit("Batch sizes and max length must be positive")
    if not 0 < args.k <= 1:
        raise SystemExit("--k must be in (0, 1]")

    spec = paper_data_spec(args)
    member_value = args.member_file or spec["member_file"]
    holdout_value = args.holdout_file or spec["holdout_file"]
    member_file = resolve_data_file(args.data_root, member_value)
    holdout_file = resolve_data_file(args.data_root, holdout_value)
    member_count = (
        args.member_expected_count
        if args.member_expected_count is not None
        else spec["member_count"]
    )
    holdout_count = (
        args.holdout_expected_count
        if args.holdout_expected_count is not None
        else spec["holdout_count"]
    )
    if min(member_count, holdout_count) <= 0:
        raise SystemExit("Expected member and holdout counts must be positive")
    requested_protocol = protocol_payload(
        args,
        spec,
        member_file,
        holdout_file,
        member_count,
        holdout_count,
    )
    if report_path.exists() and not args.overwrite:
        if read_report(report_path).get("protocol") == requested_protocol:
            print(f"SKIP matching existing report: {report_path}")
            return 0
        raise SystemExit(
            f"Existing MIA report uses a different model, data, or protocol: {report_path}; "
            "choose another --output-dir or pass --overwrite"
        )

    require_mia_dependencies()

    tokenizer_source = args.tokenizer or args.model
    tokenizer = AutoTokenizer.from_pretrained(
        tokenizer_source,
        revision=args.tokenizer_revision or args.model_revision,
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        revision=args.model_revision,
        torch_dtype=dtype(args.torch_dtype),
        device_map=args.device_map,
        attn_implementation=args.attn_implementation,
    )
    model.eval()
    template = {
        "apply_chat_template": True,
        "system_prompt": args.system_prompt,
        "date_string": args.date_string,
    }
    member_dataset = MultilingualQADataset(
        data_files=[str(member_file)],
        tokenizer=tokenizer,
        template_args=template,
        languages=args.source_language,
        topic_roles=spec["member_role"],
        variant_layers="core",
        dataset_families=spec["member_family"],
        culture_origins=spec["member_origin"],
        max_length=args.max_length,
        expected_count=member_count,
    )
    holdout_dataset = MultilingualQADataset(
        data_files=[str(holdout_file)],
        tokenizer=tokenizer,
        template_args=template,
        languages=args.source_language,
        topic_roles=spec["holdout_role"],
        variant_layers="core",
        dataset_families=spec["holdout_family"],
        max_length=args.max_length,
        expected_count=holdout_count,
    )
    collator = DataCollatorForSupervisedDataset(
        tokenizer=tokenizer,
        padding_side="right",
        index="index",
    )
    metrics = evaluate_attacks(
        model=model,
        tokenizer=tokenizer,
        member_dataset=member_dataset,
        holdout_dataset=holdout_dataset,
        collator=collator,
        batch_size=args.batch_size,
        min_k_plus_plus_batch_size=args.min_k_plus_plus_batch_size,
        k=args.k,
    )
    report = {
        "protocol": requested_protocol,
        "metrics": metrics,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"COMPLETE attacks={len(metrics)} output={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
