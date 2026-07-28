# Stage 2 - Topic to Knowledge to English QA

## Goal

Transform each Stage 1 topic pair into explicit, relation-aligned forget-retain probes and canonical English QA families.

This stage contains four operations that were previously described as repository Steps 3, 4, 4.5, and 5:

```text
Wikipedia pages
  -> atomic knowledge units
  -> schema-aware relation matching
  -> reviewed one-to-one forget-retain pairs
  -> English core + surface QA families
```

## Knowledge-unit schema

Each atomic unit records at least:

- relation type;
- semantic slot;
- answer and answer type;
- factual statement;
- directly supporting source span.

Target and neighbor units are eligible for matching only when their normalized relation type, semantic slot, answer type, and evidence are compatible. Selected units are one-to-one: a unit is not reused in another matched pair.

The target unit becomes the **forget unit**; the neighbor unit becomes the **retain unit**.

## Executable pipeline

Run from the repository root:

```powershell
python code/step3_extract_knowledge_cards.py --help
python code/step4_construct_relation_matched_pairs.py --help
python code/step4_5_select_high_quality_pairs.py --help
python code/step5_generate_qa_variants.py --help
```

The default common-goal path is:

```text
data/wiki_page_content.json
  -> data/knowledge_cards.json
  -> data/knowledge_card_pairs.json
  -> data/selected_knowledge_card_pairs.json
  -> data/qa_variants.en.json
```

The language-conditioned path uses the corresponding `.culture_specific` filenames and produces:

```text
data/wiki_page_content.culture_specific.json
  -> data/knowledge_cards.culture_specific.json
  -> data/knowledge_card_pairs.culture_specific.strict.json
  -> data/selected_knowledge_card_pairs.culture_specific.json
  -> data/qa_variants.en.culture_specific.json
```

Use explicit `--input`, `--output`, and cache arguments when running the second track; check each script's `--help`.

## QA contract

Each selected forget or retain unit produces:

- one **core QA** that directly queries the fact;
- three **surface variants** that ask for the same information with different wording.

Across all four realizations, relation type, semantic slot, expected answer, answer boundary, and evidence must remain invariant. Surface variants are evaluation probes; only core QAs are used for knowledge injection and unlearning.

| Track | Matched unit pairs | English QAs |
|---|---:|---:|
| Common-goal | 500 | 4,000 |
| Language-conditioned | 300 | 2,400 |

The English QA files are the main input to [Stage 3](../stage_3_multilingual_translation/).

## Holdout construction

Unmatched valid units are sampled separately and must be disjoint from the matched pool:

```powershell
python code/step_holdout_generate_qa.py --help
```

Each holdout unit produces one core QA and no surface variants. Current sizes are 500 common-goal units and 300 language-conditioned units. These QAs are non-members for membership-inference evaluation and must not enter SFT or unlearning training.

## Exit criteria

Stage 2 is complete when:

- all selected units have traceable evidence;
- forget-retain matches satisfy the shared relation schema;
- no selected unit is reused;
- every English QA family has one core and three equivalent surface probes;
- holdout units are knowledge-unit-disjoint from matched units;
- automated and human review flags are resolved or documented.

Fine-grained legacy documentation remains under [`code/data_workflow/`](../code/data_workflow/).

