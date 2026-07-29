"""BGE-M3 dense-embedding evaluation for saved benchmark generations."""

from __future__ import annotations

import inspect
import math
import unicodedata
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

import numpy as np


METRIC_NAME = "a_embed_cosine_bge_m3"
DEFAULT_ENCODER = "BAAI/bge-m3"
DEFAULT_ENCODER_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
PROTOCOL_VERSION = "bge_m3_dense_answer_similarity_v2"
VARIANT_WEIGHTS = {"core": 0.25, "surface": 0.75}


def normalize_embedding_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", "" if value is None else str(value))
    return " ".join(normalized.split())


def validate_records(records: Sequence[Mapping[str, Any]], *, input_path: Path) -> None:
    seen = set()
    for index, record in enumerate(records, start=1):
        qa_id = str(record.get("qa_id", "")).strip()
        if not qa_id:
            raise ValueError(f"Missing qa_id in {input_path}:record={index}")
        if qa_id in seen:
            raise ValueError(f"Duplicate qa_id={qa_id!r} in {input_path}:record={index}")
        seen.add(qa_id)
        for field in ("language", "topic_role", "variant_layer"):
            if not str(record.get(field, "")).strip():
                raise ValueError(f"Missing {field!r} for qa_id={qa_id!r}")
        if "cleaned_generation" not in record:
            raise ValueError(f"Missing 'cleaned_generation' for qa_id={qa_id!r}")
        if not normalize_embedding_text(record.get("expected_answer")):
            raise ValueError(f"Empty 'expected_answer' for qa_id={qa_id!r}")


class BGEM3DenseEncoder:
    """Thin, optional-dependency wrapper around FlagEmbedding's BGE-M3 model."""

    def __init__(self, model_name_or_path: str, *, device: str, use_fp16: bool = False):
        try:
            from FlagEmbedding import BGEM3FlagModel
        except ImportError as exc:
            raise RuntimeError(
                "Embedding evaluation requires the optional 'embedding' dependencies. "
                "Install with: pip install -e '.[embedding]'"
            ) from exc

        kwargs: Dict[str, Any] = {"use_fp16": use_fp16}
        if "devices" in inspect.signature(BGEM3FlagModel).parameters:
            kwargs["devices"] = [device]
        self.model = BGEM3FlagModel(model_name_or_path, **kwargs)
        self.tokenizer = getattr(self.model, "tokenizer", None)
        if self.tokenizer is None:
            raise RuntimeError("BGEM3FlagModel did not expose its tokenizer")

    def token_lengths(self, texts: Sequence[str], *, batch_size: int) -> list[int]:
        lengths: list[int] = []
        for start in range(0, len(texts), batch_size):
            encoded = self.tokenizer(
                list(texts[start : start + batch_size]),
                add_special_tokens=True,
                truncation=False,
                padding=False,
            )
            lengths.extend(len(ids) for ids in encoded["input_ids"])
        return lengths

    def encode(self, texts: Sequence[str], *, batch_size: int, max_length: int) -> np.ndarray:
        result = self.model.encode(
            list(texts),
            batch_size=batch_size,
            max_length=max_length,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        if not isinstance(result, Mapping) or "dense_vecs" not in result:
            raise RuntimeError("BGE-M3 encode result did not contain dense_vecs")
        return np.asarray(result["dense_vecs"], dtype=np.float32)


def _unique_texts(records: Sequence[Mapping[str, Any]]) -> list[str]:
    texts: list[str] = []
    seen = set()
    for record in records:
        for field in ("expected_answer", "cleaned_generation"):
            text = normalize_embedding_text(record.get(field))
            if text and text not in seen:
                seen.add(text)
                texts.append(text)
    return texts


def _normalize_vectors(vectors: np.ndarray, expected_count: int) -> np.ndarray:
    if vectors.ndim != 2 or vectors.shape[0] != expected_count:
        raise ValueError(
            f"Expected embedding matrix ({expected_count}, dim), got {vectors.shape}"
        )
    if not np.isfinite(vectors).all():
        raise ValueError("Encoder returned non-finite embeddings")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if np.any(norms <= 0):
        raise ValueError("Encoder returned a zero-norm embedding")
    return np.asarray(vectors / norms, dtype=np.float32)


def score_records(
    records: Sequence[Mapping[str, Any]],
    *,
    encoder: Any,
    batch_size: int,
    tokenization_batch_size: int,
    max_length: int,
) -> Tuple[list[Dict[str, Any]], Dict[str, int]]:
    texts = _unique_texts(records)
    lengths = encoder.token_lengths(texts, batch_size=tokenization_batch_size)
    if len(lengths) != len(texts):
        raise ValueError("Tokenizer length output is not aligned with input texts")
    vectors = _normalize_vectors(
        encoder.encode(texts, batch_size=batch_size, max_length=max_length), len(texts)
    )
    vector_by_text = dict(zip(texts, vectors))
    length_by_text = dict(zip(texts, map(int, lengths)))

    scored: list[Dict[str, Any]] = []
    audit = {
        "record_count": len(records),
        "unique_nonempty_text_count": len(texts),
        "empty_candidate_count": 0,
        "candidate_truncated_count": 0,
        "reference_truncated_count": 0,
    }
    for source in records:
        candidate = normalize_embedding_text(source.get("cleaned_generation"))
        reference = normalize_embedding_text(source.get("expected_answer"))
        reference_tokens = length_by_text[reference]
        reference_truncated = reference_tokens > max_length
        audit["reference_truncated_count"] += int(reference_truncated)
        if candidate:
            candidate_tokens = length_by_text[candidate]
            candidate_truncated = candidate_tokens > max_length
            audit["candidate_truncated_count"] += int(candidate_truncated)
            similarity = float(np.dot(vector_by_text[candidate], vector_by_text[reference]))
            similarity = min(1.0, max(-1.0, similarity))
        else:
            candidate_tokens = 0
            candidate_truncated = False
            similarity = 0.0
            audit["empty_candidate_count"] += 1
        if not math.isfinite(similarity):
            raise ValueError(f"Non-finite similarity for qa_id={source.get('qa_id')!r}")

        updated = dict(source)
        metrics = dict(updated.get("metrics", {}) or {})
        metrics[METRIC_NAME] = similarity
        updated["metrics"] = metrics
        updated["embedding_evaluation"] = {
            "protocol_version": PROTOCOL_VERSION,
            "metric": METRIC_NAME,
            "candidate_field": "cleaned_generation",
            "reference_field": "expected_answer",
            "candidate_token_count_untruncated": candidate_tokens,
            "reference_token_count_untruncated": reference_tokens,
            "candidate_truncated": candidate_truncated,
            "reference_truncated": reference_truncated,
            "empty_candidate": not candidate,
        }
        scored.append(updated)
    return scored, audit


def metric_definition(
    max_length: int,
    *,
    encoder: str = DEFAULT_ENCODER,
    encoder_revision: str | None = DEFAULT_ENCODER_REVISION,
) -> Dict[str, Any]:
    return {
        "name": METRIC_NAME,
        "type": "continuous_cosine_similarity",
        "range": [-1.0, 1.0],
        "encoder": encoder,
        "encoder_revision": encoder_revision,
        "representation": "normalized_dense_embedding_only",
        "candidate_field": "cleaned_generation",
        "reference_field": "expected_answer",
        "normalization": "NFKC_then_unicode_whitespace_collapse",
        "max_length": max_length,
        "empty_candidate_score": 0.0,
        "threshold": None,
        "binary_metric": None,
    }
