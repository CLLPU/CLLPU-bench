import torch
import torch.nn.functional as F

from cllpu.trainer.unlearn.grad_diff import GradDiff
from cllpu.trainer.utils import compute_batch_nll


class SimNPO(GradDiff):
    def __init__(self, delta=0.0, beta=1.0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.delta = delta
        self.beta = beta

    def compute_loss(self, model, inputs, return_outputs=False):
        forget_inputs = inputs["forget"]

        forget_labels = forget_inputs["labels"]
        loss_mask = forget_labels != -100
        forget_loss, forget_outputs = compute_batch_nll(model, forget_inputs)
        forget_loss = forget_loss / loss_mask.sum(-1) - self.delta
        forget_loss = -F.logsigmoid(self.beta * forget_loss).mean() * 2 / self.beta

        retain_inputs = inputs["retain"]
        retain_inputs = {
            "input_ids": retain_inputs["input_ids"],
            "attention_mask": retain_inputs["attention_mask"],
            "labels": retain_inputs["labels"],
        }
        retain_loss = self.compute_retain_loss(model=model, retain_inputs=retain_inputs)

        loss = self.gamma * forget_loss + self.alpha * retain_loss
        return (loss, forget_outputs) if return_outputs else loss


class DrSimNPO(SimNPO):
    def __init__(
        self,
        sigma_forget=1.0,
        sigma_retain=1.0,
        forget_dro=True,
        retain_dro=False,
        log_ori_loss=True,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.sigma_forget = sigma_forget
        self.sigma_retain = sigma_retain
        self.forget_dro = forget_dro
        self.retain_dro = retain_dro
        self.log_ori_loss = log_ori_loss

    @staticmethod
    def _dv_aggregate(loss, sigma):
        if sigma <= 0:
            raise ValueError(f"DV sigma must be positive, got {sigma}")
        return -sigma * torch.logsumexp(-loss / sigma, dim=0) + sigma * torch.log(
            torch.tensor(loss.numel(), device=loss.device, dtype=loss.dtype)
        )

    def compute_loss(self, model, inputs, return_outputs=False):
        forget_inputs = inputs["forget"]

        forget_labels = forget_inputs["labels"]
        loss_mask = forget_labels != -100
        forget_loss, forget_outputs = compute_batch_nll(model, forget_inputs)
        forget_loss = forget_loss / loss_mask.sum(-1) - self.delta
        forget_loss = -F.logsigmoid(self.beta * forget_loss) * 2 / self.beta
        if self.log_ori_loss:
            self.log({"forget_loss_ori": forget_loss.detach().mean().item()})
        if self.forget_dro:
            forget_loss = self._dv_aggregate(forget_loss, self.sigma_forget)
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
                raise NotImplementedError("DrSimNPO retain_dro currently supports only NLL retain loss.")
            retain_loss, _ = compute_batch_nll(model, retain_inputs)
            if self.log_ori_loss:
                self.log({"retain_loss_ori": retain_loss.detach().mean().item()})
            retain_loss = self._dv_aggregate(retain_loss, self.sigma_retain)
        else:
            retain_loss = self.compute_retain_loss(model=model, retain_inputs=retain_inputs)

        loss = self.gamma * forget_loss + self.alpha * retain_loss
        return (loss, forget_outputs) if return_outputs else loss
