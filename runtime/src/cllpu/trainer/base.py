# Modified from https://github.com/huggingface/transformers/blob/v4.45.1/src/transformers/trainer.py
from typing import Dict, List, Optional, Union

import os
import logging
from transformers import Trainer
from torch.utils.data import Dataset
from transformers.trainer_utils import PREFIX_CHECKPOINT_DIR
from typing import Any

logger = logging.getLogger(__name__)


class FinetuneTrainer(Trainer):
    def __init__(self, evaluators=None, template_args=None, *args, **kwargs):
        self.evaluators = evaluators
        self.template_args = template_args
        super().__init__(*args, **kwargs)

    def save_model(self, output_dir=None, _internal_call=False):
        # Transformers 4.45.1 gates FSDP saving on a newer Accelerate version.
        # Collect the full state on all ranks with the pinned Accelerate 0.34.2.
        if not self.is_fsdp_enabled or "FULL_STATE_DICT" not in str(
            self.accelerator.state.fsdp_plugin.state_dict_type
        ):
            return super().save_model(output_dir, _internal_call=_internal_call)
        state_dict = self.accelerator.get_state_dict(self.model, unwrap=False)
        if self.args.should_save:
            self._save(output_dir or self.args.output_dir, state_dict=state_dict)
        if self.args.push_to_hub and not _internal_call:
            self.push_to_hub(commit_message="Model save")

    def evaluate(
        self,
        eval_dataset: Optional[Union[Dataset, Dict[str, Dataset]]] = None,
        ignore_keys: Optional[List[str]] = None,

        metric_key_prefix: str = "eval",

        trial: Dict[str, Any] = None,
    ) -> Dict[str, float]:
        # Run a custom evaluator and save results
        if self.evaluators:
            if self.accelerator.is_local_main_process:

                eval_metrics = {}
                if self.accelerator.num_processes == 1:
                    run_dir = self._get_output_dir(trial=trial)
                    checkpoint_folder = (
                        f"{PREFIX_CHECKPOINT_DIR}-{self.state.global_step}"
                    )
                    output_dir = os.path.join(run_dir, checkpoint_folder, "evals")
                    os.makedirs(output_dir, exist_ok=True)
                    eval_metrics = {}
                    for _, evaluator in self.evaluators.items():
                        eval_args = {
                            "output_dir": output_dir,
                            "template_args": self.template_args,
                            "model": self.model,
                            "tokenizer": self.tokenizer,
                        }
                        eval_metrics.update(evaluator.evaluate(**eval_args))
                    self.log(eval_metrics)
                else:
                    logger.warning(
                        "Custom evaluator can be run with this Trainer only when a single accelerator process is running."
                    )
                return eval_metrics

        if eval_dataset is None:
            return {}
        # Run the default HF Trainer evaluate method when eval dataset is provided
        return super().evaluate(eval_dataset, ignore_keys, metric_key_prefix)
