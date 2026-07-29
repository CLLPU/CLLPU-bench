import torch
import torch.nn.functional as F

from cllpu.trainer.unlearn.grad_diff import GradDiff
from cllpu.trainer.utils import compute_batch_nll, compute_dpo_loss


class NPO(GradDiff):
    def __init__(self, beta=1.0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.beta = beta
        if self.ref_model is None:
            self.ref_model = self._prepare_ref_model(self.model)

    def compute_loss(self, model, inputs, return_outputs=False):
        forget_inputs = inputs["forget"]

        forget_loss, forget_outputs = compute_dpo_loss(
            model=model,
            ref_model=self.ref_model,
            win_inputs=None,
            lose_inputs=forget_inputs,
            beta=self.beta,
        )

        retain_inputs = inputs["retain"]
        retain_inputs = {
            "input_ids": retain_inputs["input_ids"],
            "attention_mask": retain_inputs["attention_mask"],
            "labels": retain_inputs["labels"],
        }
        retain_loss = self.compute_retain_loss(model=model, retain_inputs=retain_inputs)

        loss = self.gamma * forget_loss + self.alpha * retain_loss
        return (loss, forget_outputs) if return_outputs else loss


class DrNPO(NPO):
    def __init__(
        self,
        beta_dv_forget=1.0,
        beta_dv_retain=1.0,
        forget_dro=True,
        retain_dro=False,
        log_ori_loss=True,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.beta_dv_forget = beta_dv_forget
        self.beta_dv_retain = beta_dv_retain
        self.forget_dro = forget_dro
        self.retain_dro = retain_dro
        self.log_ori_loss = log_ori_loss

    @staticmethod
    def _dv_aggregate(loss, beta):
        if beta <= 0:
            raise ValueError(f"DV beta must be positive, got {beta}")
        return -beta * torch.logsumexp(-loss / beta, dim=0) + beta * torch.log(
            torch.tensor(loss.numel(), device=loss.device, dtype=loss.dtype)
        )

    def _compute_per_sample_dpo_loss(
        self, model, ref_model, win_inputs=None, lose_inputs=None, beta=1.0
    ):
        if win_inputs is None and lose_inputs is None:
            raise ValueError("Both win_inputs and lose_inputs can't be None")

        win_log_ratio, lose_log_ratio = 0.0, 0.0
        win_outputs, lose_outputs = None, None

        if win_inputs is not None:
            win_loss, win_outputs = compute_batch_nll(model, win_inputs)
            with torch.no_grad():
                win_ref_loss, _ = compute_batch_nll(ref_model, win_inputs)
            win_log_ratio = -(win_loss - win_ref_loss)

        if lose_inputs is not None:
            lose_loss, lose_outputs = compute_batch_nll(model, lose_inputs)
            with torch.no_grad():
                lose_ref_loss, _ = compute_batch_nll(ref_model, lose_inputs)
            lose_log_ratio = -(lose_loss - lose_ref_loss)

        loss = -2 / beta * F.logsigmoid(beta * (win_log_ratio - lose_log_ratio))
        return loss, (win_outputs, lose_outputs)

    def compute_loss(self, model, inputs, return_outputs=False):
        forget_inputs = inputs["forget"]

        forget_loss, forget_outputs = self._compute_per_sample_dpo_loss(
            model=model,
            ref_model=self.ref_model,
            win_inputs=None,
            lose_inputs=forget_inputs,
            beta=self.beta,
        )
        if self.log_ori_loss:
            self.log({"forget_loss_ori": forget_loss.detach().mean().item()})
        if self.forget_dro:
            forget_loss = self._dv_aggregate(forget_loss, self.beta_dv_forget)
        else:
            forget_loss = forget_loss.mean()

        retain_inputs = inputs["retain"]
        retain_inputs = {
            "input_ids": retain_inputs["input_ids"],
            "attention_mask": retain_inputs["attention_mask"],
            "labels": retain_inputs["labels"],
        }
        if self.retain_dro:
            if self.retain_loss_type != "NLL":
                raise NotImplementedError("DrNPO retain_dro currently supports only NLL retain loss.")
            retain_loss, _ = compute_batch_nll(model, retain_inputs)
            if self.log_ori_loss:
                self.log({"retain_loss_ori": retain_loss.detach().mean().item()})
            retain_loss = self._dv_aggregate(retain_loss, self.beta_dv_retain)
        else:
            retain_loss = self.compute_retain_loss(model=model, retain_inputs=retain_inputs)

        loss = self.gamma * forget_loss + self.alpha * retain_loss
        return (loss, forget_outputs) if return_outputs else loss
