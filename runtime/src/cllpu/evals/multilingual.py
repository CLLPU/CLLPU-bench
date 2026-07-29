from cllpu.evals.base import Evaluator
from cllpu.evals.multilingual_outputs import save_multilingual_eval_outputs


class MultilingualEvaluator(Evaluator):
    def __init__(self, eval_cfg, **kwargs):
        super().__init__("MULTILINGUAL", eval_cfg, **kwargs)

    def get_logs_file_path(self, output_dir, suffix="EVAL"):
        """Keep the base Evaluator cache separate from public outputs.

        The multilingual evaluator writes user-facing per-QA metrics to
        ``MULTILINGUAL_EVAL.json``. The base Evaluator also uses an ``EVAL``
        file as its cache, so sharing the same path breaks ``overwrite=false``
        cache reuse. Store the base cache under explicit CACHE names instead.
        """
        cache_suffix = "CACHE" if suffix == "EVAL" else f"CACHE_{suffix}"
        return super().get_logs_file_path(output_dir, suffix=cache_suffix)

    def summarize(self, logs):
        accessibility = logs.get("accessibility") or {}
        summary_payload = accessibility.get("summary_payload") or {}
        monitor = self._role_monitor_metrics(summary_payload)
        if bool(getattr(self.eval_cfg, "monitor_summary_only", False)):
            return monitor

        summary = super().summarize(logs)
        summary.update(monitor)
        return summary


    @staticmethod
    def _role_monitor_metrics(summary_payload):
        """Expose per-language target/neighbor accessibility as trainer log scalars."""
        by_role_language = summary_payload.get("by_role_language", {}) or {}
        monitor = {}
        for key, entry in sorted(by_role_language.items()):
            language = entry.get("language")
            topic_role = entry.get("topic_role")
            if topic_role not in {"target", "neighbor"}:
                continue
            if not language:
                continue

            variants = entry.get("variants", {}) or {}
            for metric_suffix in ("exact", "rouge"):
                for variant_layer in ("core", "surface"):
                    variant_entry = variants.get(variant_layer, {}) or {}
                    value = variant_entry.get(f"A_current_v_{metric_suffix}")
                    if value is not None:
                        monitor[f"A_current_{metric_suffix}/{topic_role}/{language}/{variant_layer}"] = value

                weighted_value = entry.get(f"A_current_{metric_suffix}")
                if weighted_value is not None:
                    monitor[f"A_current_{metric_suffix}/{topic_role}/{language}/weighted"] = weighted_value
        return monitor

    def evaluate(self, model, output_dir=None, overwrite=None, **kwargs):
        summary = super().evaluate(model, output_dir=output_dir, overwrite=overwrite, **kwargs)
        output_dir = output_dir if output_dir else self.eval_cfg.output_dir
        logs_file_path = self.get_logs_file_path(output_dir)
        logs = self.load_logs_from_file(logs_file_path)
        accessibility = logs.get("accessibility")
        if accessibility:
            records = accessibility.get("records", [])
            save_multilingual_eval_outputs(
                output_dir,
                records,
                metric_names=accessibility.get("metric_names", ("a_exact", "a_rouge")),
                eval_payload=accessibility.get("eval_payload"),
                summary_payload=accessibility.get("summary_payload"),
            )
        return summary
