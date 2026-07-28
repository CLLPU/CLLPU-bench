# Stage 1 - Goal-Guided Topic Pair Construction

## Goal

Construct target-neighbor topic pairs that place comparable knowledge on opposite sides of the intended forgetting boundary.

A valid pair should:

- belong to the same semantic domain;
- have comparable abstraction level and temporal context;
- support similar relation types and answer types;
- refer to distinct entities or events with non-overlapping factual answers;
- avoid parent-child pairs, aliases, variants of the same event, and superficial matches.

## Two tracks

| Setting | Target behavior | Neighbor behavior | Current manifest |
|---|---|---|---|
| Common-goal | target should be forgotten in all languages | preserved in all languages | [`data/wiki_page_manifest.json`](../data/wiki_page_manifest.json) |
| Language-conditioned | target should be forgotten only in its assigned source language | preserved in all languages, including source | [`data/wiki_page_manifest.culture_specific.json`](../data/wiki_page_manifest.culture_specific.json) |

The `.culture_specific` suffix is a legacy repository name for the paper's language-conditioned track.

All selected events postdate the July 23, 2024 release of Llama-3.1-8B-Instruct. The target model is then taught these facts during the later knowledge-injection step, reducing ambiguity between successful forgetting and facts never learned.

## Workflow

1. Curate target topics under the intended forgetting goal.
2. Select one semantically comparable neighbor for each target.
3. Record canonical Wikipedia pages and source-language assignments.
4. Human-review the intended boundary and factual non-overlap.
5. Fetch and normalize both Wikipedia pages.

The design step is curated; page collection is executable:

```powershell
python code/step2_collect_wiki_pages.py --help
```

## Inputs and outputs

| Track | Manifest | Collected page content | Size |
|---|---|---|---:|
| Common-goal | `data/wiki_page_manifest.json` | `data/wiki_page_content.json` | 50 pairs / 100 pages |
| Language-conditioned | `data/wiki_page_manifest.culture_specific.json` | `data/wiki_page_content.culture_specific.json` | 30 pairs / 60 pages |

Word-count audit files are stored beside the content files:

```text
data/wiki_page_content_word_counts.json
data/wiki_page_content.culture_specific_word_counts.json
```

## Exit criteria

Stage 1 is complete when every pair has two accessible canonical pages, a stable `pair_id`, a clearly documented target/neighbor role, comparable factual schemas, distinct answers, and a reviewed forgetting boundary.

The collected page content is the input to [Stage 2](../stage_2_knowledge_to_qa/).

