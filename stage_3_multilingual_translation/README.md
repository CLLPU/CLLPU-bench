# Stage 3 - Parallel Multilingual QA Translation

## Goal

Create parallel QAs in ten languages without changing the underlying fact, question intent, expected-answer boundary, or core/surface identity.

Languages:

```text
ar, bn, de, en, es, fr, ja, sw, th, zh
```

## Dual-anchor translation

Each translation is conditioned on two anchors:

1. **Knowledge-unit anchor:** fixes the fact, relation type, semantic slot, and answer boundary.
2. **English-QA anchor:** fixes the question intent and whether the item is a core QA or surface variant.

Only the linguistic realization may change.

## Run

The English files already represent `en`. Generate one non-English language per run:

```powershell
python code/step6_expand_qa_translations.py --language zh
python code/step_holdout_expand_qa_translations.py --language zh
```

For the language-conditioned track, pass the `.culture_specific` English input and output paths explicitly. Use `--help` for the complete cache and retry controls.

Outputs:

```text
data/qa_variants.<lang>.json
data/qa_variants.<lang>.culture_specific.json
data/holdout_qa.<lang>.json
data/holdout_qa.<lang>.culture_specific.json
```

## Verification

The paper uses three verification layers:

1. Blind back-translation to English and comparison with the original.
2. Independent model review against both anchors.
3. Repeated human audits of accepted samples.

Failed back-translations are written to separate `*.failed_backtranslation.json` artifacts for diagnosis and retry. Translation-review scripts and committed audit outputs are available in `code/` and `data/`.

```powershell
python code/review_step6_translation_quality.py --help
```

## Released scale

| Data family | Per language | Across 10 languages |
|---|---:|---:|
| Common matched QA | 4,000 | 40,000 |
| Language-conditioned matched QA | 2,400 | 24,000 |
| Common holdout core QA | 500 | 5,000 |
| Language-conditioned holdout core QA | 300 | 3,000 |
| **Total** | **7,200** | **72,000** |

## Exit criteria

Stage 3 is complete when every translated item preserves both anchors, IDs remain aligned with English, expected answers and aliases are language-appropriate, failed verification items are resolved, and the released language files have equal cardinality within each data family.

The verified multilingual QAs feed both [model construction and unlearning](../unlearned_models/) and the [released runtime evaluation workflow](../README.md#evaluation).

