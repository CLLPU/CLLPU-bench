import logging
import os
from typing import Any, Dict

import torch
from omegaconf import DictConfig, OmegaConf
from transformers import AutoModelForCausalLM, AutoTokenizer

HF_HOME = os.getenv("HF_HOME", default=None)

logger = logging.getLogger(__name__)

MODEL_REGISTRY: Dict[str, Any] = {}


def _register_model(model_class):
    MODEL_REGISTRY[model_class.__name__] = model_class

def get_dtype(model_args):
    torch_dtype = model_args.get("torch_dtype")
    if model_args.get("attn_implementation", None) == "flash_attention_2":
        # This check handles https://github.com/Dao-AILab/flash-attention/blob/7153673c1a3c7753c38e4c10ef2c98a02be5f778/flash_attn/flash_attn_triton.py#L820
        # If you want to run at other precisions consider running "training or inference using
        # Automatic Mixed-Precision via the `with torch.autocast(device_type='torch_device'):`
        # decorator" or using an attn_implementation compatible with the precision in the model
        # config.
        if torch_dtype not in ("float16", "bfloat16"):
            raise ValueError(
                f"Invalid torch_dtype '{torch_dtype}' for flash_attention_2; "
                "expected float16 or bfloat16."
            )
    if torch_dtype == "float16":
        return torch.float16
    elif torch_dtype == "bfloat16":
        return torch.bfloat16
    return torch.float32


def get_model(model_cfg: DictConfig):
    if model_cfg is None or model_cfg.get("model_args") is None:
        raise ValueError("Model config not found or model_args absent in runtime/configs/model.")
    model_args = dict(OmegaConf.to_container(model_cfg.model_args, resolve=True))
    tokenizer_args = dict(OmegaConf.to_container(model_cfg.tokenizer_args, resolve=True))
    torch_dtype = get_dtype(model_args)
    model_args.pop("torch_dtype", None)
    model_handler = model_cfg.get("model_handler", "AutoModelForCausalLM")
    model_cls = MODEL_REGISTRY[model_handler]
    model_path = model_args.pop("pretrained_model_name_or_path", None)
    model_args.setdefault("cache_dir", HF_HOME)
    try:
        model = model_cls.from_pretrained(
            pretrained_model_name_or_path=model_path,
            torch_dtype=torch_dtype,
            **model_args,
        )
    except Exception as e:
        logger.warning("Model %s requested with %s", model_path, model_cfg.model_args)
        raise RuntimeError(
            f"Error {e} while fetching model using {model_handler}.from_pretrained()."
        ) from e
    tokenizer = get_tokenizer(tokenizer_args)
    return model, tokenizer


def _add_or_replace_eos_token(tokenizer, eos_token: str) -> None:
    is_added = tokenizer.eos_token_id is None
    num_added_tokens = tokenizer.add_special_tokens({"eos_token": eos_token})

    if is_added:
        logger.info("Add eos token: %s", tokenizer.eos_token)
    else:
        logger.info("Replace eos token: %s", tokenizer.eos_token)

    if num_added_tokens > 0:
        logger.info("New tokens have been added, make sure `resize_vocab` is True.")


def get_tokenizer(tokenizer_cfg: DictConfig):
    tokenizer_args = dict(tokenizer_cfg)
    tokenizer_args.setdefault("cache_dir", HF_HOME)
    try:
        tokenizer = AutoTokenizer.from_pretrained(**tokenizer_args)
    except Exception as e:
        error_message = (
            f"{'--' * 40}\n"
            f"Error {e} fetching tokenizer using AutoTokenizer.\n"
            f"Tokenizer requested from path: {tokenizer_args.get('pretrained_model_name_or_path')}\n"
            f"Full tokenizer config: {tokenizer_cfg}\n"
            f"{'--' * 40}"
        )
        raise RuntimeError(error_message)

    if tokenizer.eos_token_id is None:
        logger.info("replacing eos_token with <|endoftext|>")
        _add_or_replace_eos_token(tokenizer, eos_token="<|endoftext|>")

    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
        logger.info("Setting pad_token as eos token: %s", tokenizer.pad_token)

    return tokenizer


# register models
_register_model(AutoModelForCausalLM)
