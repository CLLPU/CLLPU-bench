# Frozen Runtime Data

This directory contains the reviewed JSONL snapshot consumed by the CLLPU
training, unlearning, and evaluation code. These files are derived benchmark
inputs; no runtime command rebuilds or modifies the top-level construction
sources.

```text
runtime/data/multilingual/
  qa_flat.{ar,bn,de,en,es,fr,ja,sw,th,zh}.jsonl
  common_holdout/qa_flat.<language>.jsonl
  culture_holdout/qa_flat.<language>.jsonl
  train_splits/
    sft_core_common_plus_culture.jsonl
    eval_common_plus_culture_all.jsonl
    culture_origin/
      <origin>_forget_target_core.jsonl
      <origin>_retain_neighbor_core.jsonl
      <origin>_source_monitor_core_surface.jsonl
      <origin>_eval_all_languages_core_surface.jsonl
```

The runtime defaults to `runtime/data` when commands are launched from the
repository root. An identical snapshot stored elsewhere can be selected
without editing Hydra files:

```bash
export CROSS_LINGUAL_DATA_DIR=/path/to/data-root
```

The selected root must contain the `multilingual/` directory shown above. The
snapshot contains 40,000 Common evaluation records, 24,000 Culture-origin
evaluation records, a 16,000-record Common+Culture target-model SFT split, and
the source-language unlearning/screening splits. MIA uses 500 Common holdout
core records or 300 Culture holdout core records in the source language only.

Belebele is downloaded separately at its pinned revision and is not stored in
this directory. Training-time screening remains source-language-only. Common,
Culture-origin, and unified 64,000-record evaluation remain separate
post-selection workflows. Every weighted result is
`0.25 * core_mean + 0.75 * surface_mean`, equivalent to equal weight for one
core and each of three surface forms.
