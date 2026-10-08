"""Fixed-size English/source forget mixture from Lu & Koehn (2025), Sec. 4.4."""

from collections import Counter
import hashlib
import json
import random

from cllpu.data.multilingual_qa import MultilingualQADataset


def translation_key(record):
    key = record.get("source_qa_id")
    if not isinstance(key, str) or not key:
        raise ValueError(f"Missing translation identity for {record.get('qa_id')}")
    return key


def aligned_english(source_records, english_records):
    """Select only translations of the same facts, including culture origin."""
    english = {}
    for record in english_records:
        if record['language'] != 'en':
            raise ValueError('English translation pool contains a non-English record')
        key = translation_key(record)
        if key in english:
            raise ValueError(f'Duplicate English translation: {key}')
        english[key] = record
    keys = [translation_key(record) for record in source_records]
    if len(keys) != len(set(keys)):
        raise ValueError('Source translation identities are not unique')
    translated = []
    for record, key in zip(source_records, keys):
        if key not in english:
            raise ValueError(f'Missing English translation: {key}')
        other = english[key]
        for field in ('knowledge_pair_id', 'pair_id', 'topic_role', 'variant_layer',
                      'dataset_family', 'culture_origin'):
            if record.get(field) != other.get(field):
                raise ValueError(f'Translation mismatch for {key}: {field}')
        translated.append(other)
    return translated


class LearnUnlearnCombinedQADataset(MultilingualQADataset):
    """Replace half the source records by English translations, once per run.

    The remaining half stays in the source language. Each fact occurs exactly
    once; the dataset length and the benchmark's scheduler horizon are preserved.
    """

    def __init__(self, english_data_files, source_language, mixture_seed=0, **kwargs):
        if not isinstance(mixture_seed, int) or isinstance(mixture_seed, bool) or mixture_seed < 0:
            raise ValueError('mixture_seed must be a nonnegative integer')
        if kwargs.get('predict_with_generate', False):
            raise ValueError('The combined dataset is for training, not evaluation')
        configured = self._as_set(kwargs.get('languages'))
        if configured is not None and configured != {source_language}:
            raise ValueError('languages must select only source_language')
        kwargs['languages'] = source_language
        super().__init__(**kwargs)
        if not self.records:
            raise ValueError('The source forget dataset is empty')
        source = self.records
        if any(r['topic_role'] != 'target' or r['variant_layer'] != 'core' for r in source):
            raise ValueError('Combined unlearning expects target/core training records')
        english_kwargs = dict(kwargs)
        english_kwargs.update(data_files=english_data_files, languages='en', expected_count=None)
        pool = MultilingualQADataset(**english_kwargs)
        english = aligned_english(source, pool.records)
        indices = sorted(range(len(source)), key=lambda i: translation_key(source[i]))
        n_english = len(source) if source_language == 'en' else len(source) // 2
        selected = set(random.Random(mixture_seed).sample(indices, n_english))
        self.records = [english[i] if i in selected else record for i, record in enumerate(source)]
        self.metadata = [self._metadata(record, i) for i, record in enumerate(self.records)]
        assignments = [
            {'source_qa_id': translation_key(old), 'original_qa_id': old['qa_id'],
             'training_qa_id': new['qa_id'], 'language': new['language']}
            for old, new in zip(source, self.records)
        ]
        payload = json.dumps(assignments, sort_keys=True, ensure_ascii=False).encode('utf-8')
        self.mixture_manifest = {
            'method': 'learn_unlearn_combined', 'source_language': source_language,
            'mixture_seed': mixture_seed, 'record_count': len(self),
            'language_counts': dict(Counter(r['language'] for r in self.records)),
            'english_only_degenerate_case': source_language == 'en',
            'odd_count_policy': 'floor(N/2) English; remaining source; no duplication',
            'assignment_sha256': hashlib.sha256(payload).hexdigest(),
            'assignments': assignments,
        }


class LearnUnlearnEnglishRetainQADataset(MultilingualQADataset):
    """English translations of exactly the benchmark's source retain facts."""

    def __init__(self, english_data_files, source_language, **kwargs):
        configured = self._as_set(kwargs.get('languages'))
        if configured is not None and configured != {source_language}:
            raise ValueError('languages must select only source_language')
        kwargs['languages'] = source_language
        super().__init__(**kwargs)
        if not self.records or any(r['topic_role'] != 'neighbor' or r['variant_layer'] != 'core'
                                   for r in self.records):
            raise ValueError('Retain data must be nonempty neighbor/core records')
        english_kwargs = dict(kwargs)
        english_kwargs.update(data_files=english_data_files, languages='en', expected_count=None)
        pool = MultilingualQADataset(**english_kwargs)
        self.records = aligned_english(self.records, pool.records)
        self.metadata = [self._metadata(record, i) for i, record in enumerate(self.records)]
