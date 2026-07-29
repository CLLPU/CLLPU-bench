"""Multilingual benchmark accessibility metrics.

This module implements the stage-1 metrics aligned with the outer
multilingual unlearning benchmark:

0. per-QA accessibility a(q): a_exact and a_rouge
1. Q_t^core(g) / Q_t^surf(g) grouping
2. single-model A_current^v(g,t)
3. single-model A_current(g,t)
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

import numpy as np
import torch
from omegaconf import OmegaConf
from rouge_score import rouge_scorer, tokenizers
from torch.utils.data import DataLoader
from tqdm import tqdm

from cllpu.evals.metrics.base import unlearning_metric
from cllpu.evals.metrics.utils import stop_sequences_criteria
from cllpu.evals.multilingual_outputs import (
    build_eval_payload,
    build_generation_record,
    build_summary_payload,
    mean_numeric,
    normalize_answer,
)

logger = logging.getLogger("evaluator")


MetricNames = Tuple[str, str]
DEFAULT_METRIC_NAMES: MetricNames = ("a_exact", "a_rouge")
DEFAULT_VARIANT_WEIGHTS = {"core": 0.25, "surface": 0.75}
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
UNICODE_SCRIPT_RE = re.compile(
    r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff"  # Arabic
    r"\u0980-\u09ff"  # Bengali
    r"\u0e00-\u0e7f"  # Thai
    r"\u3040-\u309f\u30a0-\u30ff\uff66-\uff9f]"  # Japanese kana
)
CHAR_TOKEN_SCRIPTS = ("CJK", "HIRAGANA", "KATAKANA", "THAI")
SPAN_TOKEN_SCRIPTS = ("ARABIC", "BENGALI")


class MixedUnicodeTokenizer(tokenizers.Tokenizer):
    """ROUGE tokenizer for mixed Latin and multilingual benchmark scripts.

    The upstream rouge-score tokenizer works for Latin-script text but drops or
    under-tokenizes several benchmark scripts. This tokenizer preserves default
    English/Latin behavior, keeps existing Chinese behavior by tokenizing CJK
    characters individually, and adds deterministic handling for Japanese kana,
    Thai, Arabic, and Bengali. Identical non-Latin strings must tokenize
    identically and therefore receive ROUGE-L F1 = 1.0.
    """

    def __init__(self, use_stemmer: bool = True):
        self.default_tokenizer = tokenizers.DefaultTokenizer(use_stemmer=use_stemmer)

    def tokenize(self, text: Any) -> List[str]:
        text = str(text or "")
        if not CJK_RE.search(text) and not UNICODE_SCRIPT_RE.search(text):
            return self.default_tokenizer.tokenize(text)

        tokens: List[str] = []
        buffer: List[str] = []
        span_buffer: List[str] = []
        span_script: Optional[str] = None

        def flush_buffer() -> None:
            if not buffer:
                return
            tokens.extend(self.default_tokenizer.tokenize("".join(buffer)))
            buffer.clear()

        def flush_span() -> None:
            nonlocal span_script
            if not span_buffer:
                return
            tokens.append("".join(span_buffer))
            span_buffer.clear()
            span_script = None

        def char_script(char: str) -> Optional[str]:
            name = unicodedata.name(char, "")
            if any(name.startswith(prefix) for prefix in CHAR_TOKEN_SCRIPTS):
                return "char"
            if any(name.startswith(prefix) for prefix in SPAN_TOKEN_SCRIPTS):
                return name.split()[0].lower()
            return None

        for char in text:
            script = char_script(char)
            if script == "char":
                flush_buffer()
                flush_span()
                tokens.append(char)
            elif script is not None:
                flush_buffer()
                if span_script != script:
                    flush_span()
                    span_script = script
                span_buffer.append(char)
            else:
                flush_span()
                buffer.append(char)
        flush_span()
        flush_buffer()
        return tokens


MixedCJKTokenizer = MixedUnicodeTokenizer


def _as_plain_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if OmegaConf.is_config(value):
        return dict(OmegaConf.to_container(value, resolve=True))
    return dict(value)


def _prepare_generation_args(
    tokenizer,
    generation_args: Mapping[str, Any],
    *,
    input_length: int,
    batch_size: int,
) -> Tuple[Dict[str, Any], List[str]]:
    args = _as_plain_dict(generation_args)
    stopwords = args.pop("stopwords", None)
    if stopwords is None:
        stopwords = []
    if not isinstance(stopwords, list):
        raise TypeError("generation_args.stopwords must be a list when provided.")

    if stopwords:
        args["stopping_criteria"] = stop_sequences_criteria(
            tokenizer,
            stopwords,
            input_length,
            batch_size,
        )
    return args, stopwords


def _decode_generated_texts(tokenizer, output_ids: torch.Tensor, prompt_length: int) -> List[str]:
    return tokenizer.batch_decode(
        output_ids[:, prompt_length:],
        skip_special_tokens=True,
        clean_up_tokenization_spaces=True,
    )


def _clean_generations(tokenizer, raw_generations: Sequence[str], stopwords: Sequence[str]) -> List[str]:
    eos_text = tokenizer.decode([tokenizer.eos_token_id]) if tokenizer.eos_token_id is not None else ""
    cut_words = [eos_text] + list(stopwords)
    cleaned = []
    for text in raw_generations:
        clean_text = str(text)
        for word in cut_words:
            if word and word in clean_text:
                clean_text = clean_text.split(word)[0]
        cleaned.append(clean_text.strip())
    return cleaned


def _score_answer(
    scorer: rouge_scorer.RougeScorer,
    generation: Any,
    expected_answer: Any,
) -> Dict[str, float]:
    cleaned_generation = normalize_answer(generation)
    expected = normalize_answer(expected_answer)
    rouge_scores = scorer.score(expected, cleaned_generation)
    return {
        "a_exact": int(cleaned_generation == expected),
        "a_rouge": float(rouge_scores["rougeL"].fmeasure),
    }


def _safe_group_value(record: Mapping[str, Any], key: str) -> str:
    value = record.get(key)
    return "" if value is None else str(value)


def _knowledge_key(record: Mapping[str, Any]) -> Tuple[str, str]:
    return (_safe_group_value(record, "knowledge_pair_id"), _safe_group_value(record, "topic_role"))


def _variant_group_key(record: Mapping[str, Any]) -> Tuple[str, str, str, str]:
    knowledge_pair_id, topic_role = _knowledge_key(record)
    return (
        _safe_group_value(record, "language"),
        knowledge_pair_id,
        topic_role,
        _safe_group_value(record, "variant_layer"),
    )


def _knowledge_language_key(record: Mapping[str, Any]) -> Tuple[str, str, str]:
    knowledge_pair_id, topic_role = _knowledge_key(record)
    return (_safe_group_value(record, "language"), knowledge_pair_id, topic_role)


def _key_to_name(parts: Sequence[str]) -> str:
    return "|".join(parts)


def _mean_metrics(records: Sequence[Mapping[str, Any]], metric_names: Sequence[str]) -> Dict[str, Optional[float]]:
    means: Dict[str, Optional[float]] = {}
    for metric_name in metric_names:
        values = [(record.get("metrics", {}) or {}).get(metric_name) for record in records]
        means[metric_name] = mean_numeric(values)
    return means


def _summarize_variant_access(
    records: Sequence[Mapping[str, Any]], metric_names: Sequence[str]
) -> Dict[str, Dict[str, Any]]:
    groups: MutableMapping[Tuple[str, str, str, str], List[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        groups[_variant_group_key(record)].append(record)

    summary: Dict[str, Dict[str, Any]] = {}
    for key, group_records in sorted(groups.items()):
        language, knowledge_pair_id, topic_role, variant_layer = key
        means = _mean_metrics(group_records, metric_names)
        entry: Dict[str, Any] = {
            "language": language,
            "knowledge_pair_id": knowledge_pair_id,
            "topic_role": topic_role,
            "variant_layer": variant_layer,
            "count": len(group_records),
        }
        for metric_name, value in means.items():
            entry[f"A_current_v_{metric_name.removeprefix('a_')}"] = value
        summary[_key_to_name(key)] = entry
    return summary


def _normalize_weights(
    available_layers: Iterable[str],
    variant_weights: Mapping[str, float],
    *,
    renormalize: bool,
) -> Dict[str, float]:
    weights = {str(layer): float(variant_weights.get(str(layer), 0.0)) for layer in available_layers}
    if not renormalize:
        return weights
    total = sum(weight for weight in weights.values() if weight > 0)
    if total <= 0:
        equal = 1.0 / max(len(weights), 1)
        return {layer: equal for layer in weights}
    return {layer: weight / total for layer, weight in weights.items()}


def _summarize_knowledge_access(
    records: Sequence[Mapping[str, Any]],
    metric_names: Sequence[str],
    *,
    variant_weights: Mapping[str, float],
    renormalize_variant_weights: bool,
) -> Dict[str, Dict[str, Any]]:
    groups: MutableMapping[Tuple[str, str, str], List[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        groups[_knowledge_language_key(record)].append(record)

    summary: Dict[str, Dict[str, Any]] = {}
    for key, group_records in sorted(groups.items()):
        language, knowledge_pair_id, topic_role = key
        by_layer: MutableMapping[str, List[Mapping[str, Any]]] = defaultdict(list)
        for record in group_records:
            by_layer[_safe_group_value(record, "variant_layer")].append(record)

        layer_weights = _normalize_weights(
            by_layer.keys(),
            variant_weights,
            renormalize=renormalize_variant_weights,
        )
        variants: Dict[str, Dict[str, Any]] = {}
        access_values: Dict[str, float] = {}
        for layer, layer_records in sorted(by_layer.items()):
            layer_means = _mean_metrics(layer_records, metric_names)
            variants[layer] = {
                "count": len(layer_records),
                "weight": layer_weights.get(layer, 0.0),
                **{f"A_current_v_{name.removeprefix('a_')}": value for name, value in layer_means.items()},
            }

        for metric_name in metric_names:
            total = 0.0
            has_value = False
            for layer, variant_entry in variants.items():
                value = variant_entry.get(f"A_current_v_{metric_name.removeprefix('a_')}")
                if value is None:
                    continue
                total += layer_weights.get(layer, 0.0) * float(value)
                has_value = True
            access_values[f"A_current_{metric_name.removeprefix('a_')}"] = total if has_value else None

        summary[_key_to_name(key)] = {
            "language": language,
            "knowledge_pair_id": knowledge_pair_id,
            "topic_role": topic_role,
            "count": len(group_records),
            "variant_weights": layer_weights,
            "variants": variants,
            **access_values,
        }
    return summary


def _role_language_variant_key(record: Mapping[str, Any]) -> Tuple[str, str, str]:
    return (
        _safe_group_value(record, "language"),
        _safe_group_value(record, "topic_role"),
        _safe_group_value(record, "variant_layer"),
    )


def _role_language_key(record: Mapping[str, Any]) -> Tuple[str, str]:
    return (_safe_group_value(record, "language"), _safe_group_value(record, "topic_role"))


def _summarize_role_variant_access(
    records: Sequence[Mapping[str, Any]], metric_names: Sequence[str]
) -> Dict[str, Dict[str, Any]]:
    groups: MutableMapping[Tuple[str, str, str], List[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        groups[_role_language_variant_key(record)].append(record)

    summary: Dict[str, Dict[str, Any]] = {}
    for key, group_records in sorted(groups.items()):
        language, topic_role, variant_layer = key
        means = _mean_metrics(group_records, metric_names)
        entry: Dict[str, Any] = {
            "language": language,
            "topic_role": topic_role,
            "variant_layer": variant_layer,
            "count": len(group_records),
        }
        for metric_name, value in means.items():
            entry[f"A_current_v_{metric_name.removeprefix('a_')}"] = value
        summary[_key_to_name(key)] = entry
    return summary


def _summarize_role_language_access(
    records: Sequence[Mapping[str, Any]],
    metric_names: Sequence[str],
    *,
    variant_weights: Mapping[str, float],
    renormalize_variant_weights: bool,
) -> Dict[str, Dict[str, Any]]:
    groups: MutableMapping[Tuple[str, str], List[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        groups[_role_language_key(record)].append(record)

    summary: Dict[str, Dict[str, Any]] = {}
    for key, group_records in sorted(groups.items()):
        language, topic_role = key
        means = _mean_metrics(group_records, metric_names)
        by_layer: MutableMapping[str, List[Mapping[str, Any]]] = defaultdict(list)
        for record in group_records:
            by_layer[_safe_group_value(record, "variant_layer")].append(record)

        layer_weights = _normalize_weights(
            by_layer.keys(),
            variant_weights,
            renormalize=renormalize_variant_weights,
        )
        variants: Dict[str, Dict[str, Any]] = {}
        access_values: Dict[str, float] = {}
        for layer, layer_records in sorted(by_layer.items()):
            layer_means = _mean_metrics(layer_records, metric_names)
            variants[layer] = {
                "count": len(layer_records),
                "weight": layer_weights.get(layer, 0.0),
                **{f"A_current_v_{name.removeprefix('a_')}": value for name, value in layer_means.items()},
            }

        for metric_name in metric_names:
            total = 0.0
            has_value = False
            for layer, variant_entry in variants.items():
                value = variant_entry.get(f"A_current_v_{metric_name.removeprefix('a_')}")
                if value is None:
                    continue
                total += layer_weights.get(layer, 0.0) * float(value)
                has_value = True
            access_values[f"A_current_{metric_name.removeprefix('a_')}"] = total if has_value else None

        summary[_key_to_name(key)] = {
            "language": language,
            "topic_role": topic_role,
            "count": len(group_records),
            "variant_weights": layer_weights,
            "variants": variants,
            **{f"{name}_mean": value for name, value in means.items()},
            **access_values,
        }
    return summary


def build_accessibility_summary(
    records: Sequence[Mapping[str, Any]],
    metric_names: Sequence[str] = DEFAULT_METRIC_NAMES,
    *,
    variant_weights: Optional[Mapping[str, float]] = None,
    renormalize_variant_weights: bool = True,
) -> Dict[str, Any]:
    weights = dict(variant_weights or DEFAULT_VARIANT_WEIGHTS)
    payload = build_summary_payload(
        records,
        metric_names,
        group_keys=(
            "dataset_family",
            "culture_origin",
            "language",
            "topic_role",
            "variant_layer",
            "pair_id",
            "relation_type",
        ),
    )
    payload["by_Q_t_variant_family"] = _summarize_variant_access(records, metric_names)
    payload["by_knowledge_language"] = _summarize_knowledge_access(
        records,
        metric_names,
        variant_weights=weights,
        renormalize_variant_weights=renormalize_variant_weights,
    )
    payload["by_role_language_variant"] = _summarize_role_variant_access(records, metric_names)
    payload["by_role_language"] = _summarize_role_language_access(
        records,
        metric_names,
        variant_weights=weights,
        renormalize_variant_weights=renormalize_variant_weights,
    )
    metric_definitions: Dict[str, Any] = {}
    if "a_exact" in metric_names:
        metric_definitions["a_exact"] = {
            "version": "v1",
            "matching": "strict_expected_answer_only",
            "uses_answer_aliases": False,
            "post_processing": "openunlearning_generation_post_processing_only",
        }
    if "a_rouge" in metric_names:
        metric_definitions["a_rouge"] = {
            "version": "v1",
            "rouge_type": "rougeL_f1",
            "uses_answer_aliases": False,
            "post_processing": "openunlearning_generation_post_processing_only",
            "tokenizer": "mixed_unicode_default_latin_v2",
        }
    metric_definitions.update({
        "A_current_v": {
            "description": "Mean a(q) over Q_t^v(g), grouped by language, knowledge_pair_id, topic_role, and variant_layer.",
        },
        "A_current": {
            "description": "Weighted sum over available variant-family A_current_v values for a fixed language and knowledge object.",
            "variant_weights": weights,
            "renormalize_variant_weights": renormalize_variant_weights,
        },
        "A_current_v_role": {
            "description": "Role-level mean a(q), grouped by language, topic_role, and variant_layer; useful for target/neighbor summary.",
        },
        "A_current_role": {
            "description": "Role-level weighted core/surface accessibility grouped by language and topic_role.",
            "variant_weights": weights,
            "renormalize_variant_weights": renormalize_variant_weights,
        },
    })
    payload["metric_definitions"] = metric_definitions
    return payload


def _run_multilingual_generation(
    model,
    *,
    tokenizer,
    data,
    collator,
    batch_size: int,
    generation_args: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    dataloader = DataLoader(data, batch_size=batch_size, collate_fn=collator)
    scorer = rouge_scorer.RougeScorer(
        ["rougeL"],
        use_stemmer=True,
        tokenizer=MixedUnicodeTokenizer(use_stemmer=True),
    )
    generation_args_for_record = _as_plain_dict(generation_args)
    records: List[Dict[str, Any]] = []

    for batch in tqdm(dataloader, desc="multilingual_accessibility", total=len(dataloader)):
        if "index" not in batch:
            raise ValueError("Multilingual accessibility metric requires a collator that preserves the index field.")
        indices = batch.pop("index").cpu().numpy().tolist()
        batch = {key: value.to(model.device) for key, value in batch.items()}
        input_ids = batch["input_ids"]
        attention_mask = batch["attention_mask"]

        input_texts = tokenizer.batch_decode(
            input_ids,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=True,
        )
        generate_kwargs, stopwords = _prepare_generation_args(
            tokenizer,
            generation_args,
            input_length=input_ids.shape[1],
            batch_size=input_ids.shape[0],
        )
        with torch.no_grad():
            output = model.generate(
                input_ids,
                attention_mask=attention_mask,
                **generate_kwargs,
                pad_token_id=tokenizer.eos_token_id,
            )

        input_sequence_length = input_ids.shape[-1]
        prompt_token_counts = attention_mask.sum(dim=1).detach().cpu().tolist()
        generated_token_ids_batch = output[:, input_sequence_length:].detach().cpu().tolist()
        decode_args = {
            "skip_special_tokens": True,
            "clean_up_tokenization_spaces": True,
        }
        raw_generations = _decode_generated_texts(tokenizer, output, input_sequence_length)
        cleaned_generations = _clean_generations(tokenizer, raw_generations, stopwords)

        for index, input_text, raw_generation, cleaned_generation, generated_token_ids, prompt_token_count in zip(
            indices, input_texts, raw_generations, cleaned_generations, generated_token_ids_batch, prompt_token_counts
        ):
            metadata = dict(data.metadata[index])
            metrics = _score_answer(scorer, cleaned_generation, metadata.get("expected_answer", ""))
            record = build_generation_record(
                metadata,
                prompt=input_text,
                raw_generation=raw_generation,
                cleaned_generation=cleaned_generation,
                input_sequence_length=input_sequence_length,
                prompt_token_count=int(prompt_token_count),
                generated_token_ids=generated_token_ids,
                decode_args=decode_args,
                generation_args=generation_args_for_record,
                metrics=metrics,
            )
            records.append(record)
    return records


@unlearning_metric(name="multilingual_accessibility")
def multilingual_accessibility(model, **kwargs):
    """Compute multilingual stage-1 accessibility metrics.

    The metric uses only expected_answer, not answer_aliases. It compares
    OpenUnlearning-style cleaned generations against expected_answer with a
    strict exact match and ROUGE-L F1.
    """
    tokenizer = kwargs["tokenizer"]
    data = kwargs["data"]
    collator = kwargs["collators"]
    batch_size = int(kwargs["batch_size"])
    generation_args = kwargs["generation_args"]
    variant_weights = _as_plain_dict(kwargs.get("variant_weights", DEFAULT_VARIANT_WEIGHTS))
    renormalize_variant_weights = bool(kwargs.get("renormalize_variant_weights", True))
    metric_names = tuple(kwargs.get("metric_names", DEFAULT_METRIC_NAMES))

    records = _run_multilingual_generation(
        model,
        tokenizer=tokenizer,
        data=data,
        collator=collator,
        batch_size=batch_size,
        generation_args=generation_args,
    )
    eval_payload = build_eval_payload(records, metric_names)
    summary_payload = build_accessibility_summary(
        records,
        metric_names,
        variant_weights=variant_weights,
        renormalize_variant_weights=renormalize_variant_weights,
    )

    overall = summary_payload["overall"]
    agg_value = overall.get("a_rouge_mean")
    if agg_value is None:
        agg_value = overall.get("a_exact_mean")

    return {
        "agg_value": agg_value,
        "records": records,
        "metric_names": list(metric_names),
        "eval_payload": eval_payload,
        "summary_payload": summary_payload,
    }
