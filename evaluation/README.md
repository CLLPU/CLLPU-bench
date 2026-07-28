# Evaluation

This directory supports exactly four knowledge-accessibility metrics:

1. **EM** - normalized Exact Match
2. **RL** - multilingual ROUGE-L F1
3. **SS** - BGE-M3 sentence similarity
4. **LLM-as-a-Judge** - binary factual correctness from an OpenAI-compatible judge

The scripts export every numeric value required to build the paper heatmaps and the final Source/Cross summaries. They **do not draw heatmaps or generate any figure files**.

## Scripts

| Metric | Entry point | Extra requirement |
|---|---|---|
| EM | [`evaluate_em.py`](evaluate_em.py) | none beyond base requirements |
| RL | [`evaluate_rouge_l.py`](evaluate_rouge_l.py) | none beyond base requirements |
| SS | [`evaluate_sentence_similarity.py`](evaluate_sentence_similarity.py) | `sentence-transformers`, BGE-M3 weights |
| LLM-as-a-Judge | [`evaluate_llm_judge.py`](evaluate_llm_judge.py) | OpenAI-compatible API and judge model |

`_common.py` is shared implementation code, not a fifth evaluation entry point.

## Input

Each script accepts JSONL or JSON generation records. JSON may be a list or contain a `records`/`generations` list.

Required logical fields:

| Canonical field | Accepted aliases | Meaning |
|---|---|---|
| `setting` | `scenario`, `dataset_family` | `common_goal` or `language_conditioned`; defaults to `unspecified` |
| `method` | `model_type`, `checkpoint_method` | method/checkpoint family |
| `source_language` | `source_lang`, `s_language` | unlearning language `s` |
| `evaluation_language` | `target_language`, `language`, `t_language` | query language `t` |
| `role` | `topic_role` | `forget`/`target` or `retain`/`neighbor` |
| `knowledge_id` | `knowledge_pair_id`, `card_id` | knowledge unit used for unit-level aggregation |
| `variant_layer` | `variant`, `qa_variant` | `core` or `surface` |
| `prediction` | `generation`, `generated_answer`, `response` | model answer |
| `expected_answer` | `reference`, `answer` | gold answer |

Recommended fields:

```json
{
  "qa_id": "pair_001__target__en__core",
  "setting": "common_goal",
  "method": "npo",
  "source_language": "en",
  "evaluation_language": "zh",
  "role": "forget",
  "knowledge_id": "pair_001__target",
  "variant_layer": "core",
  "question": "……",
  "prediction": "……",
  "expected_answer": "……",
  "answer_aliases": []
}
```

`question` is required in practice for LLM-as-a-Judge. The paper-compatible default scores only `expected_answer`. Pass `--use-aliases` to allow `answer_aliases` as alternative correct references.

## Run

```powershell
python evaluation/evaluate_em.py generations.jsonl
python evaluation/evaluate_rouge_l.py generations.jsonl
python evaluation/evaluate_sentence_similarity.py generations.jsonl
python evaluation/evaluate_llm_judge.py generations.jsonl `
  --model YOUR_JUDGE_MODEL
```

The default language order is:

```text
ar, bn, de, en, es, fr, ja, sw, th, zh
```

By default, each `setting + method + role` must contain a complete source-language × evaluation-language matrix. Use `--allow-incomplete` only for smoke tests or partial diagnostics.

## Outputs

Each metric writes to `evaluation/outputs/<metric>/` by default:

| File | Contents |
|---|---|
| `per_qa.jsonl` | score for every generation |
| `per_knowledge.csv` | mean over the core QA and its surface variants for each knowledge unit |
| `heatmap_values.csv` | all numeric source × evaluation-language cells in long format |
| `heatmap_matrices.json` | the same cells as ordered 10 × 10 numeric matrices |
| `overall.csv` | final Source, Cross, and all-cell Overall values |
| `overall.json` | JSON form of the final values |

No PNG, SVG, PDF, Matplotlib, or Seaborn output is produced.

## Aggregation

For metric `m`, role `z`, source language `s`, and evaluation language `t`:

1. score every QA;
2. average the core QA and three surface variants belonging to the same knowledge unit;
3. average the knowledge-unit values to obtain the heatmap cell `A_z^m(s,t)`;
4. macro-average diagonal cells for **Source**;
5. average off-diagonal languages within each source, then macro-average sources for **Cross**;
6. average all available cells for the diagnostic **Overall** value.

Thus `heatmap_values.csv` contains every value that would be printed inside a heatmap, while `overall.csv` contains the final values used in the paper-level comparison.

Expected directions:

| Setting | Forget Source | Forget Cross | Retain Source | Retain Cross |
|---|---:|---:|---:|---:|
| Common-goal | low | low | high | high |
| Language-conditioned | low | high | high | high |

## Metric details

### EM

Both prediction and reference are Unicode NFKC-normalized, case-folded, stripped of punctuation/symbols, and whitespace-normalized. Score is `1` for equality and `0` otherwise.

### RL

ROUGE-L uses longest-common-subsequence F1. The deterministic tokenizer uses word tokens where languages delimit words and character tokens for CJK, Japanese kana, and Thai.

### SS

The default embedding model is `BAAI/bge-m3`. Embeddings are L2-normalized and the score is cosine similarity. Override with `--model` only when the replacement is documented in the result manifest.

### LLM-as-a-Judge

The judge receives the question, candidate answer, expected answer, and aliases, and returns binary correctness. Configure:

```powershell
$env:OPENAI_BASE_URL = "https://api.openai.com/v1"
$env:OPENAI_API_KEY = "..."
$env:CLLPU_JUDGE_MODEL = "..."
```

Responses are cached in JSONL so interrupted or repeated evaluation does not rescore completed examples.

Historical experiment notes under `models/`, `protocols/`, and `results/` are provenance records. They are not additional supported metrics or executable evaluation entry points.
