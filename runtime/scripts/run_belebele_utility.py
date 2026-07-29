#!/usr/bin/env python3
"""Run the fixed ten-language Belebele utility protocol for one model."""

from __future__ import annotations

import argparse
import hashlib
import json
from importlib.metadata import version
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from transformers import AutoTokenizer

from cllpu.evals.belebele import (
    DATASET_REVISION,
    TASK_NAMES,
    add_macro_average,
    normalize_samples,
    task_summary,
)


def optional_imports():
    try:
        from lm_eval import simple_evaluate
        from lm_eval.models.huggingface import HFLM
        from lm_eval.tasks import TaskManager
        from lm_eval.utils import handle_non_serializable
    except ImportError as exc:
        raise RuntimeError(
            "Belebele evaluation requires: pip install -e '.[belebele]'"
        ) from exc
    return simple_evaluate, HFLM, TaskManager, handle_non_serializable


def write_json(path: Path, value: Any, *, default=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        json.dump(value, tmp, ensure_ascii=False, indent=2, sort_keys=True, default=default)
        tmp.write("\n")
        temporary = Path(tmp.name)
    temporary.replace(path)


def write_jsonl(path: Path, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        for record in records:
            tmp.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        temporary = Path(tmp.name)
    temporary.replace(path)


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_reference(value: str) -> str:
    local = Path(value).expanduser()
    return str(local.resolve()) if local.exists() else value


def local_data_identity(data_root: Path | None) -> dict | None:
    if data_root is None:
        return None
    root = data_root.resolve()
    files = {}
    for task_name in TASK_NAMES:
        language = task_name.removeprefix("belebele_")
        path = root / "belebele" / DATASET_REVISION / f"{language}.jsonl"
        if not path.is_file():
            raise FileNotFoundError(f"Missing local Belebele file: {path}")
        files[task_name] = {"path": str(path), "sha256": file_sha256(path)}
    return {"root": str(root), "files": files}


def task_config(task_name: str, data_root: Path | None) -> Any:
    if data_root is None:
        return {"task": task_name, "dataset_kwargs": {"revision": DATASET_REVISION}}
    language = task_name.removeprefix("belebele_")
    path = data_root / "belebele" / DATASET_REVISION / f"{language}.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"Missing local Belebele file: {path}")
    return {
        "task": task_name,
        "dataset_path": "json",
        "dataset_name": None,
        "dataset_kwargs": {"data_files": {"test": str(path.resolve())}},
    }


def protocol(args: argparse.Namespace, tokenizer_source: str) -> dict:
    result = {
        "name": "belebele_10lang_utility_v1",
        "model": model_reference(args.model),
        "model_revision": args.model_revision,
        "tokenizer": model_reference(tokenizer_source),
        "tokenizer_revision": args.tokenizer_revision or args.model_revision,
        "dataset": "facebook/belebele",
        "dataset_revision": DATASET_REVISION,
        "local_data": local_data_identity(args.data_root),
        "tasks": list(TASK_NAMES),
        "expected_samples_per_task": 900,
        "metrics": ["acc", "acc_norm"],
        "continuations": ["A", "B", "C", "D"],
        "num_fewshot": 0,
        "log_samples": True,
        "apply_chat_template": True,
        "system_instruction": None,
        "fewshot_as_multiturn": False,
        "bootstrap_iters": 0,
        "batch_size": args.batch_size,
        "dtype": args.dtype,
        "device": args.device,
        "attn_implementation": args.attn_implementation,
        "trust_remote_code": False,
        "limit": args.limit,
        "seeds": {"python": 0, "numpy": 1234, "torch": 1234, "fewshot": 1234},
        "software_versions": {
            "lm_eval": version("lm-eval"),
            "datasets": version("datasets"),
            "transformers": version("transformers"),
        },
    }
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--model", required=True, help="Hugging Face model ID or local checkpoint")
    result.add_argument("--tokenizer", default=None, help="Defaults to --model")
    result.add_argument("--model-revision", default=None)
    result.add_argument("--tokenizer-revision", default=None)
    result.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Optional root containing belebele/<revision>/*.jsonl; Hub data is used if omitted",
    )
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument("--device", default="cuda")
    result.add_argument("--dtype", default="bfloat16")
    result.add_argument("--batch-size", type=int, default=16)
    result.add_argument("--attn-implementation", default="flash_attention_2")
    result.add_argument("--limit", type=float, default=None, help="Smoke tests only; omit for paper runs")
    result.add_argument("--overwrite", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    simple_evaluate, HFLM, TaskManager, json_default = optional_imports()
    output_dir = args.output_dir.resolve()
    protocol_path = output_dir / "BELEBELE_PROTOCOL.json"
    summary_path = output_dir / "BELEBELE_SUMMARY.json"
    metadata_path = output_dir / "BELEBELE_TASK_METADATA.json"
    tokenizer_source = args.tokenizer or args.model
    requested_protocol = protocol(args, tokenizer_source)

    if output_dir.exists() and args.overwrite:
        for path in (
            protocol_path,
            summary_path,
            metadata_path,
        ):
            if path.exists():
                path.unlink()
    existing_protocol = read_json(protocol_path)
    if existing_protocol and existing_protocol != requested_protocol:
        raise SystemExit(f"Existing output uses a different model or protocol: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    if not existing_protocol:
        write_json(protocol_path, requested_protocol)

    summary = read_json(summary_path)
    metadata = read_json(metadata_path)
    pending = [task for task in TASK_NAMES if f"{task}/acc" not in summary]
    if not pending:
        print(f"SKIP complete Belebele evaluation: {output_dir}")
        return 0

    tokenizer = AutoTokenizer.from_pretrained(
        tokenizer_source,
        revision=args.tokenizer_revision or args.model_revision,
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model_args = dict(
        pretrained=args.model,
        revision=args.model_revision or "main",
        tokenizer=tokenizer,
        device=args.device,
        dtype=args.dtype,
        batch_size=args.batch_size,
        trust_remote_code=False,
        attn_implementation=args.attn_implementation,
    )
    model = HFLM(**model_args)
    task_manager = TaskManager()

    for task_name in pending:
        task = task_config(task_name, args.data_root)
        results = simple_evaluate(
            model=model,
            tasks=[task],
            task_manager=task_manager,
            num_fewshot=0,
            batch_size=args.batch_size,
            limit=args.limit,
            bootstrap_iters=0,
            log_samples=True,
            system_instruction=None,
            apply_chat_template=True,
            fewshot_as_multiturn=False,
            random_seed=0,
            numpy_random_seed=1234,
            torch_random_seed=1234,
            fewshot_random_seed=1234,
        )
        if not results or task_name not in (results.get("samples") or {}):
            raise RuntimeError(f"lm-eval returned no sample logs for {task_name}")
        samples = results["samples"][task_name]
        normalized = normalize_samples(task_name, samples)
        if args.limit is None and len(normalized) != 900:
            raise ValueError(f"{task_name} produced {len(normalized)} samples; expected 900")
        write_jsonl(output_dir / "BELEBELE_ITEMS" / f"{task_name}.jsonl", normalized)
        write_json(
            output_dir / "BELEBELE_RAW" / f"{task_name}.json",
            samples,
            default=json_default,
        )
        summary.update(task_summary(results, task_name))
        summary = add_macro_average(summary)
        metadata[task_name] = {key: value for key, value in results.items() if key != "samples"}
        write_json(summary_path, summary, default=json_default)
        write_json(metadata_path, metadata, default=json_default)

    print(
        f"COMPLETE tasks={len(TASK_NAMES)} lm_eval={version('lm-eval')} output={output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
