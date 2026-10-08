"""Paper objective: CE(retain) - CE(forget), with a combined-language forget set."""

from cllpu.trainer.unlearn.grad_diff import GradDiff


class LearnUnlearnCombined(GradDiff):
    """Lu & Koehn (2025), Secs. 4.1 and 4.4, adapted to benchmark QA.

    Reuse the benchmark's tested answer-only CE and gradient accumulation.
    The data handler, not an extra loss term, implements the language mixture.
    """

    def __init__(self, alpha=1.0, gamma=1.0, retain_loss_type='NLL', **kwargs):
        if alpha != 1.0 or gamma != 1.0 or retain_loss_type != 'NLL':
            raise ValueError('The paper objective requires alpha=gamma=1 and retain_loss_type=NLL')
        super().__init__(alpha=alpha, gamma=gamma, retain_loss_type=retain_loss_type, **kwargs)
