# Evaluation Compatibility Entrypoints

The canonical CLLPU evaluation implementation lives in
`runtime/src/cllpu/` and `runtime/scripts/`. The four files
in this directory preserve the earlier evaluator names but delegate to that
implementation; they are not a second metric stack.

All four commands require a completed benchmark `generations.jsonl`. They
score existing generations and never load a checkpoint or generate responses:

```bash
python runtime/evaluation/evaluate_em.py generations.jsonl --output-dir outputs/eval/em
python runtime/evaluation/evaluate_rouge_l.py generations.jsonl --output-dir outputs/eval/rouge
python runtime/evaluation/evaluate_sentence_similarity.py generations.jsonl \
  --output-dir outputs/eval/embedding
python runtime/evaluation/evaluate_llm_judge.py generations.jsonl \
  --output-dir outputs/eval/semantic
```

The authoritative definitions are:

- Exact Match: OpenUnlearning-aligned strict equality after generation cleanup;
  it does not case-fold, remove punctuation, or score aliases.
- ROUGE-L: `rouge-score` with the benchmark's deterministic multilingual
  tokenizer.
- Embedding: dense cosine similarity from `BAAI/bge-m3` at the pinned revision
  recorded in the output protocol.
- Semantic judge: the fixed five-level score `0, 0.25, 0.5, 0.75, 1`, with a
  versioned prompt/schema and protocol-checked resume behavior.

Every aggregation uses `0.25 * core_mean + 0.75 * surface_mean` and validates
the expected one-core plus three-surface structure. This is equivalent to
giving the core form and each of the three surface forms weight `0.25`.

MIA and Belebele are checkpoint-based evaluations and therefore have separate
entry points:

```text
runtime/scripts/run_mia_evaluation.py
runtime/scripts/run_belebele_utility.py
```

The root [`README.md`](../../README.md) documents the supported generation,
optional-evaluation, and export commands. These compatibility entry points do
not define a separate protocol.
