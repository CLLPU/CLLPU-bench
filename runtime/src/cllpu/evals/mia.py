"""Membership-inference attacks used by the multilingual benchmark."""

from __future__ import annotations

import zlib
from typing import Any, Dict, Mapping, Sequence

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader
from tqdm import tqdm

from cllpu.data.utils import IGNORE_INDEX


ATTACK_NAMES = ("mia_loss", "mia_zlib", "mia_min_k", "mia_min_k_plus_plus")


def require_mia_dependencies() -> None:
    try:
        import sklearn  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "MIA evaluation requires the optional dependencies: pip install -e '.[mia]'"
        ) from exc


def _to_device(batch: Mapping[str, torch.Tensor], model) -> Dict[str, torch.Tensor]:
    return {key: value.to(model.device) for key, value in batch.items()}


def average_losses(model, batch: Mapping[str, torch.Tensor]) -> list[float]:
    batch = _to_device(batch, model)
    with torch.no_grad():
        logits = model(**batch).logits[..., :-1, :].contiguous()
    labels = batch["labels"][..., 1:].contiguous()
    losses = nn.CrossEntropyLoss(ignore_index=IGNORE_INDEX, reduction="none")(
        logits.transpose(-1, -2), labels
    ).sum(dim=-1)
    counts = labels.ne(IGNORE_INDEX).sum(dim=-1).clamp_min(1)
    return (losses / counts).detach().cpu().tolist()


def token_log_probabilities(
    model,
    batch: Mapping[str, torch.Tensor],
    *,
    include_vocab: bool = False,
) -> list[Any]:
    batch = _to_device(batch, model)
    with torch.no_grad():
        log_probs = torch.nn.functional.log_softmax(model(**batch).logits, dim=-1)[:, :-1]
    next_tokens = batch["input_ids"][:, 1:].unsqueeze(-1)
    target = torch.gather(log_probs, dim=2, index=next_tokens).squeeze(-1)
    results = []
    for row in range(batch["input_ids"].shape[0]):
        label_positions = batch["labels"][row].ne(IGNORE_INDEX).nonzero(as_tuple=True)[0][:-1]
        if not len(label_positions):
            empty = torch.empty(0, device=model.device)
            results.append((empty, torch.empty(0, log_probs.shape[-1], device=model.device)) if include_vocab else empty)
            continue
        start, end = int(label_positions[0]), int(label_positions[-1])
        selected_target = target[row, start - 1 : end]
        if include_vocab:
            results.append((selected_target, log_probs[row, start - 1 : end]))
        else:
            results.append(selected_target)
    return results


def _min_k_score(values: torch.Tensor, k: float) -> float:
    if not len(values):
        return 0.0
    array = values.detach().float().cpu().numpy()
    count = max(1, int(len(array) * k))
    return float(-np.mean(np.sort(array)[:count]))


def _min_k_plus_plus_score(target: torch.Tensor, vocab: torch.Tensor, k: float) -> float:
    if not len(target):
        return 0.0
    probabilities = torch.exp(vocab)
    mean = (probabilities * vocab).sum(dim=-1)
    variance = (probabilities * vocab.square()).sum(dim=-1) - mean.square()
    normalized = (target - mean) / torch.sqrt(variance.clamp_min(1e-6))
    return _min_k_score(normalized, k)


def _target_texts(tokenizer, batch: Mapping[str, torch.Tensor]) -> list[str]:
    texts = []
    for labels in batch["labels"]:
        tokens = labels[labels.ne(IGNORE_INDEX)].detach().cpu().tolist()
        texts.append(tokenizer.decode(tokens, skip_special_tokens=True))
    return texts


def score_dataset(
    attack_name: str,
    *,
    model,
    tokenizer,
    dataset,
    collator,
    batch_size: int,
    k: float,
) -> Dict[str, float]:
    if attack_name not in ATTACK_NAMES:
        raise ValueError(f"Unsupported MIA attack: {attack_name}")
    scores: Dict[str, float] = {}
    dataloader = DataLoader(dataset, batch_size=batch_size, collate_fn=collator)
    for batch in tqdm(dataloader, desc=attack_name, total=len(dataloader)):
        indices = batch.pop("index").tolist()
        if attack_name in {"mia_loss", "mia_zlib"}:
            losses = average_losses(model, batch)
            if attack_name == "mia_loss":
                values = losses
            else:
                texts = _target_texts(tokenizer, batch)
                values = [
                    loss / max(len(zlib.compress(text.encode("utf-8"))), 1)
                    for loss, text in zip(losses, texts)
                ]
        elif attack_name == "mia_min_k":
            values = [_min_k_score(item, k) for item in token_log_probabilities(model, batch)]
        else:
            values = [
                _min_k_plus_plus_score(target, vocab, k)
                for target, vocab in token_log_probabilities(model, batch, include_vocab=True)
            ]
        for index, value in zip(indices, values):
            qa_id = str(dataset.metadata[int(index)]["qa_id"])
            scores[qa_id] = float(value)
    if len(scores) != len(dataset):
        raise ValueError(f"MIA score count mismatch: scores={len(scores)}, data={len(dataset)}")
    return scores


def roc_auc(member_scores: Sequence[float], holdout_scores: Sequence[float]) -> float:
    require_mia_dependencies()
    from sklearn.metrics import roc_auc_score
    labels = np.asarray([0] * len(member_scores) + [1] * len(holdout_scores))
    scores = np.asarray([*member_scores, *holdout_scores], dtype=np.float64)
    return float(roc_auc_score(labels, scores))


def evaluate_attacks(
    *,
    model,
    tokenizer,
    member_dataset,
    holdout_dataset,
    collator,
    batch_size: int = 32,
    min_k_plus_plus_batch_size: int = 32,
    k: float = 0.4,
) -> Dict[str, Any]:
    output: Dict[str, Any] = {}
    for attack_name in ATTACK_NAMES:
        attack_batch_size = (
            min_k_plus_plus_batch_size if attack_name == "mia_min_k_plus_plus" else batch_size
        )
        member = score_dataset(
            attack_name,
            model=model,
            tokenizer=tokenizer,
            dataset=member_dataset,
            collator=collator,
            batch_size=attack_batch_size,
            k=k,
        )
        holdout = score_dataset(
            attack_name,
            model=model,
            tokenizer=tokenizer,
            dataset=holdout_dataset,
            collator=collator,
            batch_size=attack_batch_size,
            k=k,
        )
        output[attack_name] = {
            "auc": roc_auc(list(member.values()), list(holdout.values())),
            "member_count": len(member),
            "holdout_count": len(holdout),
            "member_score_mean": float(np.mean(list(member.values()))),
            "holdout_score_mean": float(np.mean(list(holdout.values()))),
            "member_scores_by_qa_id": member,
            "holdout_scores_by_qa_id": holdout,
        }
    return output
