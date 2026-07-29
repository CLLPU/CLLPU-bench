from cllpu.evals.multilingual import MultilingualEvaluator
from cllpu.evals.multilingual_outputs import build_table_report_payload


def test_table_report_contains_only_single_model_absolute_metrics():
    summary = {
        "overall": {"count": 2, "a_exact_mean": 0.5, "a_rouge_mean": 0.6},
        "by_language": {
            "en": {"count": 2, "a_exact_mean": 0.5, "a_rouge_mean": 0.6},
        },
        "by_topic_role": {"target": {"count": 2}},
        "by_role_language_variant": {
            "en|target|core": {
                "count": 1,
                "A_current_v_exact": 0.4,
                "A_current_v_rouge": 0.5,
            },
            "en|target|surface": {
                "count": 1,
                "A_current_v_exact": 0.6,
                "A_current_v_rouge": 0.7,
            },
        },
        "by_role_language": {
            "en|target": {
                "count": 2,
                "a_exact_mean": 0.4,
                "a_rouge_mean": 0.55,
                "A_current_exact": 0.5,
                "A_current_rouge": 0.6,
            },
        },
    }

    report = build_table_report_payload(summary)

    assert set(report) == {"report_type", "overall", "rows", "column_notes"}
    assert report["report_type"] == "single_model_absolute_metrics"
    assert report["rows"] == [
        {
            "language": "en",
            "topic_role": "target",
            "count": 2,
            "a_exact_mean": 0.4,
            "A_current_exact": {"core": 0.4, "surface": 0.6, "weighted": 0.5},
            "a_rouge_mean": 0.55,
            "A_current_rouge": {"core": 0.5, "surface": 0.7, "weighted": 0.6},
        }
    ]


def test_training_monitor_exposes_core_surface_and_weighted_exact_rouge():
    summary = {
        "by_role_language": {
            "en|target": {
                "language": "en",
                "topic_role": "target",
                "variants": {
                    "core": {"A_current_v_exact": 0.2, "A_current_v_rouge": 0.3},
                    "surface": {"A_current_v_exact": 0.4, "A_current_v_rouge": 0.5},
                },
                "A_current_exact": 0.35,
                "A_current_rouge": 0.45,
            }
        }
    }
    monitor = MultilingualEvaluator._role_monitor_metrics(summary)
    assert monitor == {
        "A_current_exact/target/en/core": 0.2,
        "A_current_exact/target/en/surface": 0.4,
        "A_current_exact/target/en/weighted": 0.35,
        "A_current_rouge/target/en/core": 0.3,
        "A_current_rouge/target/en/surface": 0.5,
        "A_current_rouge/target/en/weighted": 0.45,
    }
