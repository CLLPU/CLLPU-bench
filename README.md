# CLLPU Benchmark

Repository for **CLLPU: Cross-Lingual and Language-Bound Protocol for LLM Unlearning**.

CLLPU asks whether an unlearning method respects the intended propagation boundary:

- **Common-goal forgetting:** knowledge forgotten in source language `s` should also be inaccessible in every evaluation language `t`.
- **Language-conditioned forgetting:** knowledge should be inaccessible when `t = s`, but remain accessible when `t != s`.

The repository follows the paper's lifecycle:

```text
Stage 1                Stage 2                  Stage 3
topic pairs       ->   knowledge units    ->   multilingual QA
                         + English QA
                              |
                              v
Original / Retrain -> Unlearned models -> Evaluation
```

## Start here

| Order | Directory | Purpose | Main output |
|---:|---|---|---|
| 1 | [`stage_1_topic_pairs/`](stage_1_topic_pairs/) | Construct target-neighbor topic pairs under the two forgetting goals | `data/wiki_page_manifest*.json` |
| 2 | [`stage_2_knowledge_to_qa/`](stage_2_knowledge_to_qa/) | Extract atomic knowledge units, relation-match forget-retain units, and generate canonical English QA families | `data/qa_variants.en*.json` |
| 3 | [`stage_3_multilingual_translation/`](stage_3_multilingual_translation/) | Translate English QAs with dual anchors, back-translate, and review | `data/qa_variants.<lang>*.json` |
| 4 | [`unlearned_models/`](unlearned_models/) | Build Original/Retrain references and source-specific unlearned checkpoints | model checkpoints and run manifests |
| 5 | [`evaluation/`](evaluation/) | Measure knowledge accessibility, membership inference, and multilingual utility | matrices, tables, and figures |

The stage directories are the public navigation layer. Existing executable scripts remain in [`code/`](code/) and released artifacts remain in [`data/`](data/) so current paths and cached runs are not broken.

## Benchmark at a glance

CLLPU contains two matched data tracks:

| Paper setting | Legacy filename label | Topic pairs | Matched forget-retain unit pairs | QA per matched pair per language |
|---|---|---:|---:|---:|
| Common-goal | default / `common` | 50 | 500 | 8: 2 roles x (1 core + 3 surface) |
| Language-conditioned | `.culture_specific` | 30 | 300 | 8: 2 roles x (1 core + 3 surface) |

The ten languages are:

```text
ar, bn, de, en, es, fr, ja, sw, th, zh
```

This yields 64,000 matched QA instances:

```text
(500 + 300) matched pairs x 2 roles x 4 QA realizations x 10 languages
```

The release also contains 800 disjoint holdout core QAs per language across the two tracks, adding 8,000 instances and bringing the complete benchmark to **72,000 QA instances**.

Terminology:

| Paper term | Repository field or legacy term |
|---|---|
| forget unit / forget set | `target` |
| retain unit / retain set | `neighbor` |
| language-conditioned | `culture_specific` in existing filenames |
| source scope | matrix diagonal, `t = s` |
| cross scope | matrix off-diagonal, `t != s` |

## Data construction

The committed release is already built. Re-run only the stage that you need to change.

Create an environment and install the repository dependencies first:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### Stage 1 - Goal-guided topic pairs

Stage 1 is a curated design step followed by Wikipedia collection:

```powershell
python code/step2_collect_wiki_pages.py --help
```

See [`stage_1_topic_pairs/README.md`](stage_1_topic_pairs/README.md) for the two manifests, acceptance rules, and outputs.

### Stage 2 - Knowledge units to English QA

```powershell
python code/step3_extract_knowledge_cards.py --help
python code/step4_construct_relation_matched_pairs.py --help
python code/step4_5_select_high_quality_pairs.py --help
python code/step5_generate_qa_variants.py --help
python code/step_holdout_generate_qa.py --help
```

See [`stage_2_knowledge_to_qa/README.md`](stage_2_knowledge_to_qa/README.md) for exact input-output contracts.

### Stage 3 - Parallel multilingual translation

Run one target language at a time:

```powershell
python code/step6_expand_qa_translations.py --language zh
python code/step_holdout_expand_qa_translations.py --language zh
python code/review_step6_translation_quality.py --help
```

See [`stage_3_multilingual_translation/README.md`](stage_3_multilingual_translation/README.md) for the dual-anchor and verification protocol.

LLM-assisted construction scripts read API settings from `config/llm_api.env` by default. Do not commit credentials. Use `--help` before a production run; most scripts support explicit inputs, outputs, caches, and partial reruns.

## Models and unlearning

The paper evaluates `Meta-Llama-3.1-8B-Instruct` with:

- **Original:** full-parameter SFT on all forget and retain core QAs in all ten languages.
- **Retrain:** common-goal reference trained from the same base model on retain core QAs only.
- **Unlearned models:** one checkpoint per method, setting, and source language, initialized from Original.
- **Methods:** GA, GD, NPO, SimNPO, BalDRO-NPO, and BalDRO-SimNPO.

The model runtime used for the experiments is referenced as `open-unlearning-main` in existing experiment records but is not currently vendored in this repository. Therefore the released data and result visualizations are present, while end-to-end model training is not yet standalone. See [`unlearned_models/README.md`](unlearned_models/README.md) for the checkpoint identity and required manifest.

## Evaluation

For every source-specific model `M_u^(s)`, evaluate all ten query languages `t`.

Primary knowledge-accessibility measures:

- Exact Match (EM)
- ROUGE-L (RL)
- BGE-M3 sentence similarity (SS)
- LLM-as-a-Judge

Each matched knowledge unit is scored by averaging its core QA and three surface variants. Results are then aggregated over units into a source-language x evaluation-language matrix. Diagonal cells are Source results; off-diagonal cells are Cross results.

Expected directions:

| Setting | Forget Source | Forget Cross | Retain Source | Retain Cross |
|---|---:|---:|---:|---:|
| Common-goal | low | low | high | high |
| Language-conditioned | low | high | high | high |

The evaluation scripts export all matrix-cell values and final Source/Cross/Overall values as CSV and JSON. They do not render heatmaps. Full input and output contracts are under [`evaluation/`](evaluation/).

## Repository map

```text
.
|-- stage_1_topic_pairs/             paper Stage 1 guide
|-- stage_2_knowledge_to_qa/         paper Stage 2 guide
|-- stage_3_multilingual_translation/ paper Stage 3 guide
|-- unlearned_models/                model and checkpoint protocol
|-- evaluation/                      metrics, results, plots
|-- code/                            executable construction scripts
|-- data/                            released and intermediate benchmark data
|-- research_notes/                  design history and research notes
`-- tmp/                             local intermediate files
```

For data provenance and file families, see [`data/README.md`](data/README.md). Detailed legacy construction notes remain in [`code/data_workflow/`](code/data_workflow/).
