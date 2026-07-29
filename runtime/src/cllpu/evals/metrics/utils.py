"""Generation helpers used by multilingual accessibility evaluation."""

from typing import List

from transformers import PreTrainedTokenizer, StoppingCriteria, StoppingCriteriaList


class MultiTokenEOSCriteria(StoppingCriteria):
    """Stop once every sequence in a batch contains the requested suffix.

    Adapted from lm-evaluation-harness model utilities through OpenUnlearning.
    """

    def __init__(
        self,
        sequence: str,
        tokenizer: PreTrainedTokenizer,
        initial_decoder_input_length: int,
        batch_size: int,
    ) -> None:
        self.initial_decoder_input_length = initial_decoder_input_length
        self.done_tracker = [False] * batch_size
        self.sequence = sequence
        self.sequence_id_len = len(
            tokenizer.encode(sequence, add_special_tokens=False)
        ) + 2
        self.tokenizer = tokenizer

    def __call__(self, input_ids, scores, **kwargs) -> bool:
        generated_ids = input_ids[:, self.initial_decoder_input_length :]
        lookback_ids = generated_ids[:, -self.sequence_id_len :]
        lookback_text = self.tokenizer.batch_decode(lookback_ids)
        for index, done in enumerate(self.done_tracker):
            if not done:
                self.done_tracker[index] = self.sequence in lookback_text[index]
        return all(self.done_tracker)


def stop_sequences_criteria(
    tokenizer: PreTrainedTokenizer,
    stop_sequences: List[str],
    initial_decoder_input_length: int,
    batch_size: int,
) -> StoppingCriteriaList:
    return StoppingCriteriaList(
        [
            MultiTokenEOSCriteria(
                sequence,
                tokenizer,
                initial_decoder_input_length,
                batch_size,
            )
            for sequence in stop_sequences
        ]
    )
