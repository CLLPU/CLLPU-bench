#!/usr/bin/env python3
"""Score saved generations with a resumable OpenAI-compatible semantic judge."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import signal
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Mapping, TextIO

from cllpu.evals.metrics.multilingual import build_accessibility_summary
from cllpu.config_paths import get_config_dir
from cllpu.evals.multilingual_outputs import (
    build_eval_payload,
    save_multilingual_eval_outputs,
)
from cllpu.evals.semantic_api import (
    API_MODES,
    OpenAISemanticClient,
    SemanticAPIError,
    SemanticHTTPError,
    build_evaluation_input,
    retry_delay_seconds,
    sha256_json,
    sleep_before_retry,
)


CONFIG_DIR = get_config_dir()
DEFAULT_PROMPT = CONFIG_DIR / "semantic_judge/system_prompt_v1.txt"
DEFAULT_SCHEMA = CONFIG_DIR / "semantic_judge/schema_v1.json"
METRIC_NAME = "a_semantic"
PROTOCOL_VERSION = "reference_semantic_v2"
DEFAULT_JUDGE_MODEL = "gpt-5.6-luna"
DEFAULT_API_MODE = "chat-completions"
DEFAULT_CLEANER_VERSION = "openunlearning_cleaned_generation_v1"
RESULTS_FILE = "SEMANTIC_RESULTS.jsonl"
FAILURES_FILE = "SEMANTIC_FAILURES.jsonl"
PROGRESS_FILE = "SEMANTIC_PROGRESS.json"
PROTOCOL_FILE = "SEMANTIC_PROTOCOL.json"
VARIANT_WEIGHTS = {"core": 0.25, "surface": 0.75}
DETERMINISTIC_MATCH_RULE = {
    "enabled": True,
    "version": "nfkc_unicode_whitespace_v1",
    "unicode_normalization": "NFKC",
    "whitespace_normalization": "strip_and_collapse_all_unicode_whitespace",
    "case_folding": False,
    "punctuation_normalization": False,
    "score_on_match": 1,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        json.dump(dict(payload), tmp, ensure_ascii=False, indent=2, sort_keys=True)
        tmp.write("\n")
        tmp.flush()
        os.fsync(tmp.fileno())
        temporary = Path(tmp.name)
    temporary.replace(path)


def append_jsonl_fsync(handle: TextIO, payload: Mapping[str, Any]) -> None:
    handle.write(json.dumps(dict(payload), ensure_ascii=False, sort_keys=True) + "\n")
    handle.flush()
    os.fsync(handle.fileno())


def repair_and_read_jsonl(path: Path) -> list[Dict[str, Any]]:
    """Read an append-only journal and truncate only a malformed final line."""
    if not path.exists():
        return []
    records: list[Dict[str, Any]] = []
    with path.open("rb+") as handle:
        size = path.stat().st_size
        while True:
            start = handle.tell()
            raw = handle.readline()
            if not raw:
                break
            if not raw.strip():
                continue
            try:
                item = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                if handle.tell() == size:
                    handle.truncate(start)
                    handle.flush()
                    os.fsync(handle.fileno())
                    print(f"Recovered truncated final journal line in {path}")
                    break
                raise ValueError(f"Corrupt JSONL record in {path} at byte {start}: {exc}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"Journal record in {path} at byte {start} must be an object")
            records.append(item)
    return records


def resolve_input(value: Path) -> Path:
    path = value / "generations.jsonl" if value.is_dir() else value
    if not path.is_file():
        raise FileNotFoundError(f"Missing generations JSONL: {path}")
    return path.resolve()


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        item = json.load(handle)
    if not isinstance(item, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return item


def parse_record(line: str, path: Path, line_number: int) -> Dict[str, Any]:
    try:
        record = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}:{line_number}: {exc}") from exc
    if not isinstance(record, dict):
        raise ValueError(f"Record in {path}:{line_number} must be an object")
    return record


def validate_record(
    record: Mapping[str, Any], path: Path, line_number: int, candidate_field: str
) -> str:
    required = ("qa_id", "question", "expected_answer", "source_span")
    missing = [field for field in required if not str(record.get(field, "")).strip()]
    if missing:
        raise ValueError(f"Missing required fields {missing} in {path}:{line_number}")
    if candidate_field not in record:
        raise ValueError(f"Missing candidate field {candidate_field!r} in {path}:{line_number}")
    return str(record["qa_id"])


def input_record_hash(record: Mapping[str, Any], candidate_field: str) -> str:
    return sha256_json(
        {
            "qa_id": record.get("qa_id"),
            "question": record.get("question"),
            "expected_answer": record.get("expected_answer"),
            "source_span": record.get("source_span"),
            "candidate_field": candidate_field,
            "candidate_response": record.get(candidate_field),
        }
    )


def preflight(path: Path, candidate_field: str) -> int:
    seen = set()
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            qa_id = validate_record(
                parse_record(line, path, line_number), path, line_number, candidate_field
            )
            if qa_id in seen:
                raise ValueError(f"Duplicate qa_id={qa_id!r} in {path}:{line_number}")
            seen.add(qa_id)
            count += 1
    if not count:
        raise ValueError(f"No records found in {path}")
    return count


def normalized_exact(expected: Any, candidate: Any) -> bool:
    def normalize(value: Any) -> str:
        return " ".join(unicodedata.normalize("NFKC", str(value or "")).split())

    expected_text = normalize(expected)
    return bool(expected_text) and expected_text == normalize(candidate)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def protocol_payload(
    args: argparse.Namespace, input_path: Path, input_count: int
) -> Dict[str, Any]:
    prompt = args.prompt_file.read_text(encoding="utf-8")
    schema = read_json(args.schema_file)
    identity = {
        "protocol_version": PROTOCOL_VERSION,
        "input": {
            "sha256": file_sha256(input_path),
            "record_count": input_count,
            "candidate_field": args.candidate_field,
            "cleaner_version": args.cleaner_version,
        },
        "judge": {
            "provider": "openai_compatible",
            "model": args.model,
            "api_mode": args.api_mode,
            "base_url": args.base_url.rstrip("/"),
            "temperature": None if args.omit_temperature else args.temperature,
            "reasoning_effort": args.reasoning_effort,
            "max_output_tokens": args.max_output_tokens,
            "request_timeout_seconds": args.request_timeout_seconds,
            "api_parameters_hash": sha256_json(
                {
                    "api_mode": args.api_mode,
                    "base_url": args.base_url.rstrip("/"),
                    "model": args.model,
                    "temperature": None if args.omit_temperature else args.temperature,
                    "reasoning_effort": args.reasoning_effort,
                    "max_output_tokens": args.max_output_tokens,
                    "request_timeout_seconds": args.request_timeout_seconds,
                }
            ),
        },
        "prompt": {"sha256": hashlib.sha256(prompt.encode()).hexdigest()},
        "schema": {"sha256": sha256_json(schema)},
        "metric": {
            "name": METRIC_NAME,
            "allowed_scores": [0, 0.25, 0.5, 0.75, 1],
            "uses_answer_aliases": False,
            "source_role": "grounding_and_disambiguation_only",
            "expected_answer_role": "sole_reference_target",
            "deterministic_normalized_exact": DETERMINISTIC_MATCH_RULE,
        },
        "execution": {
            "retry_policy": {
                "max_attempts": args.max_attempts,
                "base_seconds": args.retry_base_seconds,
                "max_seconds": args.retry_max_seconds,
                "retryable_http_statuses": [408, 409, 425, 429, "5xx"],
            },
            "stop_on_error": not args.continue_on_error,
            "journal_fsync_per_success": True,
        },
    }
    return {
        "created_at": utc_now(),
        "protocol_hash": sha256_json(identity),
        "input_path": str(input_path),
        "prompt_path": str(args.prompt_file),
        "schema_path": str(args.schema_file),
        **identity,
    }


def load_successes(output_dir: Path, protocol_hash: str, candidate_field: str) -> Dict[str, dict]:
    successes = {}
    for record in repair_and_read_jsonl(output_dir / RESULTS_FILE):
        qa_id = str(record.get("qa_id", ""))
        semantic = record.get("semantic_evaluation", {}) or {}
        if not qa_id or semantic.get("protocol_hash") != protocol_hash:
            raise ValueError(f"Invalid saved semantic result for qa_id={qa_id!r}")
        if semantic.get("input_record_hash") != input_record_hash(record, candidate_field):
            raise ValueError(f"Input hash mismatch for saved qa_id={qa_id!r}")
        if qa_id in successes:
            raise ValueError(f"Duplicate successful qa_id={qa_id!r}")
        successes[qa_id] = record
    return successes


def call_with_retries(client: OpenAISemanticClient, user_input: str, args: argparse.Namespace):
    for attempt in range(1, args.max_attempts + 1):
        try:
            return client.evaluate(user_input), attempt
        except SemanticAPIError as exc:
            retryable = not isinstance(exc, SemanticHTTPError) or exc.retryable
            if not retryable or attempt == args.max_attempts:
                raise
            retry_after = exc.retry_after if isinstance(exc, SemanticHTTPError) else None
            sleep_before_retry(
                retry_delay_seconds(
                    attempt,
                    base_seconds=args.retry_base_seconds,
                    max_seconds=args.retry_max_seconds,
                    retry_after=retry_after,
                )
            )
    raise AssertionError("unreachable")


def result_record(
    source: Mapping[str, Any],
    *,
    line_number: int,
    record_hash: str,
    protocol_hash: str,
    score: float,
    path: str,
    api_result: Any = None,
    attempts: int = 0,
) -> Dict[str, Any]:
    record = dict(source)
    metrics = dict(record.get("metrics", {}) or {})
    metrics[METRIC_NAME] = score
    record["metrics"] = metrics
    record["semantic_evaluation"] = {
        "completed_at": utc_now(),
        "protocol_hash": protocol_hash,
        "input_line": line_number,
        "input_record_hash": record_hash,
        "evaluation_path": path,
        "api_attempts": attempts,
        "request_hash": getattr(api_result, "request_hash", None),
        "response_id": getattr(api_result, "response_id", None),
        "response_model": getattr(api_result, "response_model", None),
        "raw_api_response": dict(getattr(api_result, "raw_response", {}) or {}),
    }
    return record


def progress(status: str, input_count: int, success_count: int, resume_line=None, qa_id=None):
    return {
        "updated_at": utc_now(),
        "status": status,
        "input_record_count": input_count,
        "success_count": success_count,
        "remaining_count": input_count - success_count,
        "resume_input_line": resume_line,
        "resume_qa_id": qa_id,
    }


def write_complete_outputs(
    output_dir: Path, successes: Mapping[str, dict], protocol: Mapping[str, Any]
):
    records = sorted(successes.values(), key=lambda item: item["semantic_evaluation"]["input_line"])
    existing = [
        name
        for name in ("a_exact", "a_rouge")
        if any(name in (record.get("metrics") or {}) for record in records)
    ]
    metric_names = (*existing, METRIC_NAME)
    summary = build_accessibility_summary(
        records, metric_names, variant_weights=VARIANT_WEIGHTS, renormalize_variant_weights=True
    )
    summary["metric_definitions"][METRIC_NAME] = dict(protocol["metric"])
    save_multilingual_eval_outputs(
        output_dir,
        records,
        metric_names=metric_names,
        eval_payload=build_eval_payload(records, metric_names),
        summary_payload=summary,
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("input", type=Path, help="Evaluation directory or generations.jsonl")
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument(
        "--model",
        default=DEFAULT_JUDGE_MODEL,
        help=f"Judge model ID (default: {DEFAULT_JUDGE_MODEL})",
    )
    result.add_argument("--api-mode", choices=API_MODES, default=DEFAULT_API_MODE)
    result.add_argument("--base-url", default="https://api.openai.com/v1")
    result.add_argument("--api-key-env", default="OPENAI_API_KEY")
    result.add_argument("--allow-unauthenticated", action="store_true")
    result.add_argument("--prompt-file", type=Path, default=DEFAULT_PROMPT)
    result.add_argument("--schema-file", type=Path, default=DEFAULT_SCHEMA)
    result.add_argument("--candidate-field", default="cleaned_generation")
    result.add_argument("--cleaner-version", default=DEFAULT_CLEANER_VERSION)
    result.add_argument("--temperature", type=float, default=0.0)
    result.add_argument("--omit-temperature", action="store_true")
    result.add_argument("--reasoning-effort", default=None)
    result.add_argument("--max-output-tokens", type=int, default=1024)
    result.add_argument("--request-timeout-seconds", type=float, default=120.0)
    result.add_argument("--max-attempts", type=int, default=5)
    result.add_argument("--retry-base-seconds", type=float, default=2.0)
    result.add_argument("--retry-max-seconds", type=float, default=60.0)
    result.add_argument("--continue-on-error", action="store_true")
    result.add_argument("--max-new-records", type=int, default=None)
    result.add_argument("--validate-only", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    args.prompt_file = Path(args.prompt_file).resolve()
    args.schema_file = Path(args.schema_file).resolve()
    input_path = resolve_input(args.input)
    output_dir = args.output_dir.resolve()
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", args.api_key_env) is None:
        raise SystemExit("--api-key-env must be an environment variable name")
    if min(args.max_attempts, args.max_output_tokens) <= 0:
        raise SystemExit("Attempt and output-token limits must be positive")
    for path in (args.prompt_file, args.schema_file):
        if not path.is_file():
            raise SystemExit(f"Missing protocol file: {path}")

    input_count = preflight(input_path, args.candidate_field)
    requested_protocol = protocol_payload(args, input_path, input_count)
    if args.validate_only:
        print(
            json.dumps(
                {
                    "valid": True,
                    "record_count": input_count,
                    "protocol_hash": requested_protocol["protocol_hash"],
                },
                indent=2,
            )
        )
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    lock = (output_dir / ".semantic_eval.lock").open("w", encoding="utf-8")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise SystemExit(f"Another semantic evaluation is using {output_dir}") from exc

    protocol_path = output_dir / PROTOCOL_FILE
    if protocol_path.exists():
        protocol = read_json(protocol_path)
        if protocol.get("protocol_hash") != requested_protocol["protocol_hash"]:
            raise SystemExit(f"Existing output uses a different protocol: {output_dir}")
    else:
        protocol = requested_protocol
        write_json_atomic(protocol_path, protocol)
    successes = load_successes(output_dir, protocol["protocol_hash"], args.candidate_field)
    repair_and_read_jsonl(output_dir / FAILURES_FILE)

    api_key = os.environ.get(args.api_key_env, "")
    client = OpenAISemanticClient(
        api_key=api_key,
        model=args.model,
        system_prompt=args.prompt_file.read_text(encoding="utf-8"),
        schema=read_json(args.schema_file),
        api_mode=args.api_mode,
        base_url=args.base_url,
        timeout_seconds=args.request_timeout_seconds,
        temperature=None if args.omit_temperature else args.temperature,
        reasoning_effort=args.reasoning_effort,
        max_output_tokens=args.max_output_tokens,
    )

    result_handle = (output_dir / RESULTS_FILE).open("a", encoding="utf-8")
    failure_handle = (output_dir / FAILURES_FILE).open("a", encoding="utf-8")
    new_successes = 0

    def stop_handler(signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt(f"received signal {signum}")

    old_sigterm = signal.signal(signal.SIGTERM, stop_handler)
    try:
        with input_path.open("r", encoding="utf-8") as source:
            for line_number, line in enumerate(source, start=1):
                if not line.strip():
                    continue
                record = parse_record(line, input_path, line_number)
                qa_id = validate_record(record, input_path, line_number, args.candidate_field)
                record_hash = input_record_hash(record, args.candidate_field)
                if qa_id in successes:
                    if successes[qa_id]["semantic_evaluation"]["input_record_hash"] != record_hash:
                        raise ValueError(f"Input changed for completed qa_id={qa_id}")
                    continue
                try:
                    if normalized_exact(record["expected_answer"], record[args.candidate_field]):
                        completed = result_record(
                            record,
                            line_number=line_number,
                            record_hash=record_hash,
                            protocol_hash=protocol["protocol_hash"],
                            score=1.0,
                            path="deterministic_normalized_exact",
                        )
                    else:
                        if not api_key and not args.allow_unauthenticated:
                            raise SemanticAPIError(
                                f"Environment variable {args.api_key_env} is unset; "
                                "set it or use --allow-unauthenticated for a "
                                "compatible local endpoint"
                            )
                        api_result, attempts = call_with_retries(
                            client,
                            build_evaluation_input(
                                question=record["question"],
                                expected_answer=record["expected_answer"],
                                source_evidence=record["source_span"],
                                candidate_response=record[args.candidate_field],
                            ),
                            args,
                        )
                        completed = result_record(
                            record,
                            line_number=line_number,
                            record_hash=record_hash,
                            protocol_hash=protocol["protocol_hash"],
                            score=api_result.score,
                            path="api_judge",
                            api_result=api_result,
                            attempts=attempts,
                        )
                except SemanticAPIError as exc:
                    append_jsonl_fsync(
                        failure_handle,
                        {
                            "failed_at": utc_now(),
                            "input_line": line_number,
                            "qa_id": qa_id,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    )
                    write_json_atomic(
                        output_dir / PROGRESS_FILE,
                        progress("failed", input_count, len(successes), line_number, qa_id),
                    )
                    if not args.continue_on_error:
                        return 1
                    continue
                append_jsonl_fsync(result_handle, completed)
                successes[qa_id] = completed
                new_successes += 1
                write_json_atomic(
                    output_dir / PROGRESS_FILE,
                    progress("running", input_count, len(successes), line_number + 1),
                )
                if args.max_new_records and new_successes >= args.max_new_records:
                    write_json_atomic(
                        output_dir / PROGRESS_FILE,
                        progress("paused", input_count, len(successes), line_number + 1),
                    )
                    print(f"PAUSED completed={len(successes)}/{input_count} output={output_dir}")
                    return 0
    except KeyboardInterrupt:
        write_json_atomic(
            output_dir / PROGRESS_FILE,
            progress("interrupted", input_count, len(successes)),
        )
        return 130
    finally:
        signal.signal(signal.SIGTERM, old_sigterm)
        result_handle.close()
        failure_handle.close()
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()

    if len(successes) == input_count:
        write_complete_outputs(output_dir, successes, protocol)
        write_json_atomic(
            output_dir / PROGRESS_FILE,
            progress("complete", input_count, len(successes)),
        )
        print(f"COMPLETE scored={len(successes)}/{input_count} output={output_dir}")
        return 0
    write_json_atomic(
        output_dir / PROGRESS_FILE,
        progress("complete_with_failures", input_count, len(successes)),
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
