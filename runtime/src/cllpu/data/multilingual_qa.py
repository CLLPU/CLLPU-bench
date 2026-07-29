"""Dataset handler for flattened multilingual benchmark QA JSONL records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from torch.utils.data import Dataset

from cllpu.data.utils import preprocess_chat_instance


class MultilingualQADataset(Dataset):
    """Load benchmark-distributed flattened multilingual QA records.

    The dataset keeps non-tensor metadata in ``self.metadata``. Batches can carry
    the numeric ``index`` field, and evaluators can recover metadata with
    ``dataset.metadata[index]``.
    """

    def __init__(
        self,
        data_files: Sequence[str] | str,
        template_args,
        tokenizer,
        languages: Optional[Sequence[str] | str] = None,
        topic_roles: Optional[Sequence[str] | str] = None,
        variant_layers: Optional[Sequence[str] | str] = None,
        pair_ids: Optional[Sequence[str] | str] = None,
        relation_types: Optional[Sequence[str] | str] = None,
        dataset_families: Optional[Sequence[str] | str] = None,
        culture_origins: Optional[Sequence[str] | str] = None,
        question_key: str = "question",
        answer_key: str = "expected_answer",
        max_length: int = 512,
        predict_with_generate: bool = False,
        expected_count: Optional[int] = None,
        required_metadata_fields: Optional[Sequence[str] | str] = None,
    ):
        self.tokenizer = tokenizer
        self.template_args = template_args
        self.question_key = question_key
        self.answer_key = answer_key
        self.max_length = max_length
        self.predict_with_generate = predict_with_generate
        self.data_files = self._as_list(data_files)
        self.required_metadata_fields = self._as_list(required_metadata_fields or [])

        filters = {
            "language": self._as_set(languages),
            "topic_role": self._as_set(topic_roles),
            "variant_layer": self._as_set(variant_layers),
            "pair_id": self._as_set(pair_ids),
            "relation_type": self._as_set(relation_types),
            "dataset_family": self._as_set(dataset_families),
            "culture_origin": self._as_set(culture_origins),
        }
        self.records = self._load_records(
            self.data_files,
            filters,
            self.required_metadata_fields,
        )
        if expected_count is not None and len(self.records) != expected_count:
            raise ValueError(
                f"Expected {expected_count} multilingual QA records after filtering, "
                f"but loaded {len(self.records)} from {self.data_files}."
            )
        self.metadata = [self._metadata(record, index) for index, record in enumerate(self.records)]

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        record = self.records[idx]
        tokenized_data = preprocess_chat_instance(
            self.tokenizer,
            self.template_args,
            record[self.question_key],
            record[self.answer_key],
            self.max_length,
            self.predict_with_generate,
        )
        return {
            "input_ids": tokenized_data["input_ids"],
            "labels": tokenized_data["labels"],
            "attention_mask": tokenized_data["attention_mask"],
            "index": idx,
        }

    @staticmethod
    def _as_list(value: Sequence[str] | str) -> List[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return [str(item) for item in value]

    @staticmethod
    def _as_set(value: Optional[Sequence[str] | str]) -> Optional[set[str]]:
        if value is None:
            return None
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",") if item.strip()]
        else:
            items = [str(item).strip() for item in value if str(item).strip()]
        return set(items) if items else None

    @staticmethod
    def _read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON in {path}:{line_number}: {exc}") from exc
                if not isinstance(record, dict):
                    raise ValueError(f"Record in {path}:{line_number} must be a JSON object.")
                yield record

    def _load_records(
        self,
        data_files: Sequence[str],
        filters: Dict[str, Optional[set[str]]],
        required_metadata_fields: Sequence[str],
    ) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        seen_qa_ids = set()
        for data_file in data_files:
            path = Path(data_file)
            if not path.exists():
                raise FileNotFoundError(f"Multilingual QA data file not found: {path}")
            for record in self._read_jsonl(path):
                self._validate_record(record, path, required_metadata_fields)
                if not self._passes_filters(record, filters):
                    continue
                qa_id = record["qa_id"]
                if qa_id in seen_qa_ids:
                    raise ValueError(f"Duplicate qa_id after filtering: {qa_id}")
                seen_qa_ids.add(qa_id)
                records.append(record)
        return records

    @staticmethod
    def _validate_record(
        record: Dict[str, Any],
        path: Path,
        required_metadata_fields: Sequence[str],
    ) -> None:
        required = [
            "qa_id",
            "question",
            "expected_answer",
            "source_span",
            "language",
            "topic_role",
            "variant_layer",
        ]
        required.extend(required_metadata_fields)
        missing = [key for key in required if not str(record.get(key, "")).strip()]
        if missing:
            raise ValueError(f"Missing required fields {missing} in {path}")
        aliases = record.get("answer_aliases", [])
        if aliases is None:
            record["answer_aliases"] = []
        elif not isinstance(aliases, list):
            record["answer_aliases"] = [str(aliases)]

    @staticmethod
    def _passes_filters(record: Dict[str, Any], filters: Dict[str, Optional[set[str]]]) -> bool:
        for key, allowed in filters.items():
            if allowed is not None and str(record.get(key, "")) not in allowed:
                return False
        return True

    @staticmethod
    def _metadata(record: Dict[str, Any], index: int) -> Dict[str, Any]:
        metadata_keys = [
            "qa_id",
            "knowledge_pair_id",
            "pair_id",
            "source_file",
            "topic_role",
            "language",
            "variant_layer",
            "question",
            "expected_answer",
            "answer_aliases",
            "relation_type",
            "target_topic",
            "neighbor_topic",
            "source_span",
            "source_qa_id",
            "dataset_family",
            "split_role",
            "culture_origin",
        ]
        metadata = {key: record.get(key) for key in metadata_keys if key in record}
        metadata["index"] = index
        return metadata
