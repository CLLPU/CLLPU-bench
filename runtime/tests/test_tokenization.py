import pytest

from cllpu.data.utils import IGNORE_INDEX, preprocess_chat_instance


class FakeChatTokenizer:
    eos_token_id = 3

    def apply_chat_template(self, chat, *, tokenize, add_generation_prompt, **kwargs):
        assert tokenize is True
        assert kwargs["truncation"] is True
        assert kwargs["max_length"] == 32
        assert kwargs["date_string"] == "10 Apr 2025"
        if add_generation_prompt:
            assert chat[-1]["role"] == "user"
            return [10, 11]
        assert chat[-1]["role"] == "assistant"
        return [10, 11, self.eos_token_id]


class FakeTruncatingTokenizer:
    eos_token_id = 3

    def apply_chat_template(
        self, chat, *, tokenize, add_generation_prompt, truncation, max_length, **kwargs
    ):
        assert tokenize is True
        assert truncation is True
        tokens = list(range(10, 10 + max_length + 5))
        return tokens[:max_length]


TEMPLATE = {
    "apply_chat_template": True,
    "system_prompt": "You are a helpful assistant.",
    "date_string": "10 Apr 2025",
}


def test_training_chat_has_one_final_eos_and_masks_prompt():
    item = preprocess_chat_instance(
        FakeChatTokenizer(), TEMPLATE, "Question?", "Answer.", max_length=32
    )
    assert item["input_ids"].tolist() == [10, 11, 3]
    assert item["input_ids"].tolist().count(3) == 1
    assert item["labels"].tolist() == [IGNORE_INDEX, IGNORE_INDEX, 3]
    assert item["attention_mask"].tolist() == [1, 1, 1]


def test_generation_input_ends_at_assistant_prompt():
    item = preprocess_chat_instance(
        FakeChatTokenizer(),
        TEMPLATE,
        "Question?",
        "Answer.",
        max_length=32,
        predict_with_generate=True,
    )
    assert item["input_ids"].tolist() == [10, 11]
    assert item["labels"].tolist() == [10, 11, 3]
    assert item["attention_mask"].tolist() == [1, 1]


def test_chat_template_output_respects_max_length_including_eos():
    item = preprocess_chat_instance(
        FakeTruncatingTokenizer(),
        TEMPLATE,
        "Question?",
        "Answer.",
        max_length=8,
        predict_with_generate=True,
    )
    assert len(item["input_ids"]) == 8


def test_training_fails_when_truncation_removes_all_response_tokens():
    with pytest.raises(ValueError, match="no supervised response tokens"):
        preprocess_chat_instance(
            FakeTruncatingTokenizer(), TEMPLATE, "Question?", "Answer.", max_length=8
        )
