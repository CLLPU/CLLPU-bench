import logging
from typing import Callable, Any
from cllpu.data import get_collators, get_datasets

logger = logging.getLogger("metrics")


class UnlearningMetric:
    def __init__(
        self,
        name: str,
        metric_fn: Callable[..., Any],
    ):
        self.name = name
        self._metric_fn = metric_fn
        self.data = None
        self.collators = None

    def get_datasets(self, dataset_cfgs=None, **kwargs):
        """Load the datasets from config"""
        if self.data:
            return self.data
        data = get_datasets(
            tokenizer=kwargs.get("tokenizer", None),
            template_args=kwargs.get("template_args", None),
            dataset_cfgs=dataset_cfgs,
        )
        return data

    def get_collators(self, collator_cfgs=None, **kwargs):
        """Load the collators from config"""
        if self.collators:
            return self.collators
        collators = get_collators(
            tokenizer=kwargs.get("tokenizer", None), collator_cfgs=collator_cfgs
        )
        return collators

    def evaluate_metric(self, model, metric_name, **kwargs):
        logger.info(f"Evaluating {metric_name}")
        results = self._metric_fn(model, **kwargs)
        return results

    def prepare_kwargs_evaluate_metric(self, **kwargs):
        """Load the configured dataset and collator for the metric."""
        # Load datasets
        dataset_cfgs = kwargs.pop("datasets", None)
        if dataset_cfgs is not None:
            data = self.get_datasets(dataset_cfgs=dataset_cfgs, **kwargs)
            kwargs.update({"data": data})

        # Load collators
        collator_cfgs = kwargs.pop("collators", None)
        if collator_cfgs is not None:
            collators = self.get_collators(collator_cfgs=collator_cfgs, **kwargs)
            kwargs.update({"collators": collators})

        return kwargs

    def evaluate(self, model, metric_name, cache, **kwargs):
        """Evaluate one configured metric and update the evaluator cache."""
        if metric_name in cache:
            logger.info(f"Skipping {metric_name}, already evaluated.")

        metric_kwargs = self.prepare_kwargs_evaluate_metric(**kwargs)
        results = self.evaluate_metric(model, metric_name, **metric_kwargs)
        cache.update({metric_name: results})
        return results

    def __call__(self, model, **kwargs):
        return self.evaluate(model, **kwargs)

    def __repr__(self) -> str:
        """Represents class object as string

        Returns:
            str: string representation of the class object
        """
        return f"{type(self).__name__} {self.name}"


# decorator that wraps simple user-defined metric python functions into callable UnlearningMetric objects
class unlearning_metric:

    def __init__(self, name: str):
        self.name = name

    def __call__(self, metric_fn: Callable[..., Any]) -> UnlearningMetric:
        name = self.name or metric_fn.__name__
        return UnlearningMetric(name=name, metric_fn=metric_fn)
