import json

import pytest

from cllpu.data.multilingual_qa import MultilingualQADataset


def record(qa_id: str, language: str = "en", role: str = "target") -> dict:
    return {
        "qa_id": qa_id,
        "question": "Question?",
        "expected_answer": "Answer.",
        "source_span": "Evidence supporting the answer.",
        "answer_aliases": [],
        "language": language,
        "topic_role": role,
        "variant_layer": "core",
    }


def write_jsonl(path, records):
    path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records),
        encoding="utf-8",
    )


def test_dataset_filters_and_expected_count(tmp_path):
    path = tmp_path / "qa.jsonl"
    write_jsonl(path, [record("en-target"), record("fr-target", "fr")])
    dataset = MultilingualQADataset(
        data_files=[str(path)],
        tokenizer=object(),
        template_args={},
        languages="fr",
        expected_count=1,
    )
    assert len(dataset) == 1
    assert dataset.metadata[0]["qa_id"] == "fr-target"


def test_dataset_rejects_duplicate_qa_ids(tmp_path):
    path = tmp_path / "qa.jsonl"
    write_jsonl(path, [record("duplicate"), record("duplicate")])
    with pytest.raises(ValueError, match="Duplicate qa_id"):
        MultilingualQADataset(
            data_files=[str(path)],
            tokenizer=object(),
            template_args={},
        )


def test_dataset_rejects_missing_required_fields(tmp_path):
    path = tmp_path / "qa.jsonl"
    item = record("missing-answer")
    item["expected_answer"] = ""
    write_jsonl(path, [item])
    with pytest.raises(ValueError, match="expected_answer"):
        MultilingualQADataset(
            data_files=[str(path)],
            tokenizer=object(),
            template_args={},
        )


def test_dataset_rejects_missing_source_span(tmp_path):
    path = tmp_path / "qa.jsonl"
    item = record("missing-source-span")
    item["source_span"] = ""
    write_jsonl(path, [item])
    with pytest.raises(ValueError, match="source_span"):
        MultilingualQADataset(
            data_files=[str(path)],
            tokenizer=object(),
            template_args={},
        )


def test_dataset_checks_configured_metadata_fields(tmp_path):
    path = tmp_path / "qa.jsonl"
    write_jsonl(path, [record("missing-pair")])
    with pytest.raises(ValueError, match="knowledge_pair_id"):
        MultilingualQADataset(
            data_files=[str(path)],
            tokenizer=object(),
            template_args={},
            required_metadata_fields=["knowledge_pair_id", "pair_id", "relation_type"],
        )
