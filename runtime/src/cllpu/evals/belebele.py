"""Stable helpers for the benchmark's ten-language Belebele evaluation."""

from __future__ import annotations

from numbers import Real
from typing import Any, Dict, Mapping, Sequence


DATASET_REVISION = "7899cdfa4e1e0d733fd77c848e2c273cb1d32be2"
LANGUAGE_CONFIGS = {
    "ar": "arb_Arab",
    "bn": "ben_Beng",
    "de": "deu_Latn",
    "en": "eng_Latn",
    "es": "spa_Latn",
    "fr": "fra_Latn",
    "ja": "jpn_Jpan",
    "sw": "swh_Latn",
    "th": "tha_Thai",
    "zh": "zho_Hans",
}
TASK_NAMES = tuple(f"belebele_{value}" for value in LANGUAGE_CONFIGS.values())


def extract_loglikelihood(response: Any) -> float:
    value = response
    while isinstance(value, (list, tuple)) and len(value) == 1:
        value = value[0]
    if isinstance(value, (list, tuple)) and value and isinstance(value[0], Real):
        return float(value[0])
    if isinstance(value, Real):
        return float(value)
    raise ValueError(f"Cannot extract log-likelihood from response: {response!r}")


def normalize_samples(task_name: str, samples: Sequence[Mapping[str, Any]]) -> list[Dict[str, Any]]:
    """Convert lm-eval sample logs into stable per-item multiple-choice records."""
    normalized = []
    required = {
        "link",
        "question_number",
        "correct_answer_num",
        "dialect",
        "mc_answer1",
        "mc_answer2",
        "mc_answer3",
        "mc_answer4",
    }
    labels = ["A", "B", "C", "D"]
    for sample in samples:
        doc = sample.get("doc", {}) or {}
        missing = sorted(required.difference(doc))
        if missing:
            raise ValueError(f"{task_name} sample is missing fields: {missing}")
        scores = [extract_loglikelihood(item) for item in sample["filtered_resps"]]
        if len(scores) != 4:
            raise ValueError(f"{task_name} sample has {len(scores)} choices; expected 4")
        prediction = max(range(4), key=scores.__getitem__)
        normalized_scores = [score / len(label) for score, label in zip(scores, labels)]
        normalized_prediction = max(range(4), key=normalized_scores.__getitem__)
        gold = int(doc["correct_answer_num"]) - 1
        if gold not in range(4):
            raise ValueError(f"Invalid correct_answer_num={doc['correct_answer_num']!r}")
        correct = int(prediction == gold)
        correct_normalized = int(normalized_prediction == gold)
        if "acc" in sample and float(sample["acc"]) != correct:
            raise ValueError("Derived prediction disagrees with lm-eval acc")
        if "acc_norm" in sample and float(sample["acc_norm"]) != correct_normalized:
            raise ValueError("Derived prediction disagrees with lm-eval acc_norm")
        link = str(doc["link"])
        question_number = int(doc["question_number"])
        normalized.append(
            {
                "task": task_name,
                "language": doc["dialect"],
                "item_id": f"{link}::question_{question_number}",
                "link": link,
                "question_number": question_number,
                "doc_id": int(sample["doc_id"]),
                "gold_option": labels[gold],
                "predicted_option": labels[prediction],
                "predicted_option_normalized": labels[normalized_prediction],
                "correct": correct,
                "correct_normalized": correct_normalized,
                "option_loglikelihoods": dict(zip(labels, scores)),
                "option_loglikelihoods_normalized": dict(zip(labels, normalized_scores)),
                "doc_hash": sample.get("doc_hash"),
                "prompt_hash": sample.get("prompt_hash"),
                "target_hash": sample.get("target_hash"),
            }
        )
    return normalized


def task_summary(results: Mapping[str, Any], task_name: str) -> Dict[str, float]:
    metrics = (results.get("results", {}) or {}).get(task_name, {}) or {}
    output = {}
    for key, value in metrics.items():
        name = key.split(",", 1)[0]
        if name in {"acc", "acc_norm"} and isinstance(value, Real):
            output[f"{task_name}/{name}"] = float(value)
    missing = {f"{task_name}/acc", f"{task_name}/acc_norm"}.difference(output)
    if missing:
        raise ValueError(f"lm-eval omitted required Belebele metrics: {sorted(missing)}")
    return output


def add_macro_average(summary: Mapping[str, Any]) -> Dict[str, Any]:
    output = dict(summary)
    for metric in ("acc", "acc_norm"):
        keys = [f"{task}/{metric}" for task in TASK_NAMES]
        if all(isinstance(output.get(key), Real) for key in keys):
            output[f"belebele_10lang_macro/{metric}"] = sum(output[key] for key in keys) / len(keys)
    return output
