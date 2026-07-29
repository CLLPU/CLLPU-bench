"""Tokenization helpers for benchmark QA records."""

from typing import Any, Dict, List, Union

import torch


IGNORE_INDEX = -100


def preprocess_chat_instance(
    tokenizer,
    template_config: Dict[str, Any],
    prompt_msgs: Union[List[str], str],
    response_msgs: Union[List[str], str],
    max_length: int,
    predict_with_generate: bool = False,
) -> Dict[str, torch.Tensor]:
    """Tokenize a chat and apply loss only to the final assistant response."""
    if isinstance(prompt_msgs, str):
        if not isinstance(response_msgs, str):
            raise TypeError("response_msgs must be a string when prompt_msgs is a string")
        prompt_msgs, response_msgs = [prompt_msgs], [response_msgs]
    if len(prompt_msgs) != len(response_msgs):
        raise ValueError("prompt_msgs and response_msgs must have equal lengths")

    if template_config["apply_chat_template"]:
        chat = []
        system_prompt = template_config.get("system_prompt")
        if system_prompt:
            chat.append({"role": "system", "content": system_prompt})
        for prompt, response in zip(prompt_msgs, response_msgs):
            chat.extend(
                [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": response},
                ]
            )
        date_string = template_config.get("date_string")
        template_kwargs = {"date_string": date_string} if date_string is not None else {}
        chat_ids = tokenizer.apply_chat_template(
            chat,
            tokenize=True,
            add_generation_prompt=False,
            truncation=True,
            max_length=max_length,
            **template_kwargs,
        )
        prompt_ids = tokenizer.apply_chat_template(
            chat[:-1],
            tokenize=True,
            add_generation_prompt=True,
            truncation=True,
            max_length=max_length,
            **template_kwargs,
        )
    else:
        wrapped_prompt = template_config.get("system_prompt_with_special_tokens", "")
        for prompt, response in zip(prompt_msgs[:-1], response_msgs[:-1]):
            wrapped_prompt += (
                template_config["user_start_tag"]
                + prompt
                + template_config["user_end_tag"]
                + template_config["asst_start_tag"]
                + response
                + template_config["asst_end_tag"]
            )
        wrapped_prompt += (
            template_config["user_start_tag"]
            + prompt_msgs[-1]
            + template_config["user_end_tag"]
            + template_config["asst_start_tag"]
        )
        chat_ids = tokenizer(
            wrapped_prompt + response_msgs[-1],
            add_special_tokens=True,
            max_length=max_length,
            truncation=True,
        )["input_ids"]
        prompt_ids = tokenizer(
            wrapped_prompt,
            add_special_tokens=True,
            max_length=max_length,
            truncation=True,
        )["input_ids"]

    if not chat_ids or chat_ids[-1] != tokenizer.eos_token_id:
        if len(chat_ids) >= max_length:
            chat_ids = [*chat_ids[: max_length - 1], tokenizer.eos_token_id]
        else:
            chat_ids = [*chat_ids, tokenizer.eos_token_id]

    if predict_with_generate:
        input_ids = prompt_ids
        labels = chat_ids
    else:
        input_ids = chat_ids
        labels = [IGNORE_INDEX] * len(prompt_ids) + chat_ids[len(prompt_ids) :]
        if not any(label != IGNORE_INDEX for label in labels):
            raise ValueError(
                "Training example has no supervised response tokens after tokenization; "
                "increase max_length or shorten the prompt"
            )

    return {
        "input_ids": torch.tensor(input_ids, dtype=torch.long),
        "labels": torch.tensor(labels, dtype=torch.long),
        "attention_mask": torch.ones(len(input_ids), dtype=torch.long),
    }
