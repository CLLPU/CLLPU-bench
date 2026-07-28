# Benchmark Data

This directory contains released benchmark data and construction intermediates. The public lifecycle is documented in the three top-level stage guides:

- [`stage_1_topic_pairs/`](../stage_1_topic_pairs/)
- [`stage_2_knowledge_to_qa/`](../stage_2_knowledge_to_qa/)
- [`stage_3_multilingual_translation/`](../stage_3_multilingual_translation/)

## Filename conventions

| Pattern | Meaning |
|---|---|
| no family suffix | common-goal track |
| `.culture_specific` | language-conditioned track; legacy filename retained for compatibility |
| `.en` or `.<lang>` | QA realization language |
| `.failed_backtranslation` | verification failures, not release-ready QA |
| `.sampled` | sampled holdout knowledge units |
| `*_cache/` | resumable LLM-construction cache, not the canonical release |
| `archive/` | superseded research or construction material |

## Canonical release families

| Family | Common-goal | Language-conditioned |
|---|---|---|
| topic manifest | `wiki_page_manifest.json` | `wiki_page_manifest.culture_specific.json` |
| page content | `wiki_page_content.json` | `wiki_page_content.culture_specific.json` |
| knowledge units | `knowledge_cards.json` | `knowledge_cards.culture_specific.json` |
| selected matches | `selected_knowledge_card_pairs.json` | `selected_knowledge_card_pairs.culture_specific.json` |
| matched multilingual QA | `qa_variants.<lang>.json` | `qa_variants.<lang>.culture_specific.json` |
| sampled holdout units | `holdout_knowledge_cards.sampled.json` | `holdout_knowledge_cards.culture_specific.sampled.json` |
| holdout multilingual QA | `holdout_qa.<lang>.json` | `holdout_qa.<lang>.culture_specific.json` |

Use the canonical files above for benchmark experiments. Backup, cache, repair, review, and failure artifacts are retained for provenance but should not be mixed into training or headline evaluation.

## Role mapping

Existing JSON uses `target` and `neighbor`. In the paper and evaluation protocol:

```text
target   = forget
neighbor = retain
```

Holdout units are disjoint non-members for membership-inference evaluation. They must not be used during knowledge injection or unlearning.

