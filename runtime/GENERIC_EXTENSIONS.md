# Generic Extensions

These additions extend the existing `cllpu` runtime. They include reusable
method/model definitions and a seed launcher, not historical hyperparameters,
per-run experiment configurations, selected checkpoints, results, or weights.
Use the repository's existing installation instructions; run commands from the
repository root after installing `cllpu` (for example, `pip install -e . --no-deps`
in an environment where the declared dependencies are already installed).

## Seeds 1, 2, 3, 4

Pass the Hydra overrides for **one** experiment after `--`:

```bash
python -m cllpu.seed_sweep \
  --output-root /path/to/results --run-name my-experiment --dry-run -- \
  experiment=unlearn/multilingual/default \
  trainer=DrNPO target_model=/path/to/finetuned-model \
  multilingual_source_language=zh
```

Remove `--dry-run` to execute sequential seeds **1, 2, 3, 4**. This example
inherits the chosen repository experiment's defaults; it does not select or
reconstruct historical best hyperparameters. Append your own training, method,
and evaluation overrides. The installed equivalent is `cllpu-seed-sweep`.

The launcher changes `trainer.args.seed` and isolates output, log, Hydra, and
W&B run names. It rejects existing output directories and stops on the first
failure. It clears inherited W&B run ID/resume settings to avoid merging runs;
W&B reporting is enabled only when the supplied configuration enables it.
Explicit `data_seed`, deterministic settings, data order, method parameters,
and Combined mixture settings remain as supplied. Different seeds do not
guarantee identical or deterministic GPU results.

The default configuration entry point is `unlearn`. For ordinary training use
`--config-name train` and a training experiment. Optional
`--nproc-per-node N` uses `torch.distributed.run`; the user must supply a valid
distributed configuration. It does not automatically set FSDP, GPU selection,
offload, effective batch size, or concurrent independent runs. Choose visible
GPUs through `CUDA_VISIBLE_DEVICES`. Existing single-process custom evaluation
limitations still apply to distributed training.

## Combined

`LearnUnlearnCombined` adapts Lu & Koehn (2025), Sections 4.1 and 4.4, to this
benchmark's answer-only QA/full-parameter setting. It uses
`CE(English retain) - CE(combined forget)` with unit coefficients. It is not a
claim of reproducing the authors' article/LoRA training pipeline verbatim.
Reference: <https://aclanthology.org/2025.emnlp-main.516/>.

The forget dataset replaces half of the source-language target/core facts
with their English translations once per run. Every fact appears exactly
once. Odd counts use `floor(N/2)` English records; the rest remain in the source
language. English-source runs use the original English facts without
duplication. The retain dataset uses English translations of the same neighbor
facts. Translation identities and culture origins are checked; missing or
ambiguous translations fail instead of silently changing the training data.

Append these structural overrides to an existing Common or Culture experiment:

```bash
trainer=LearnUnlearnCombined
data.forget.Multilingual_QA.handler=LearnUnlearnCombinedQADataset
data.retain.Multilingual_QA.handler=LearnUnlearnEnglishRetainQADataset
'+data.forget.Multilingual_QA.args.source_language=${multilingual_source_language}'
'+data.retain.Multilingual_QA.args.source_language=${multilingual_source_language}'
"+data.forget.Multilingual_QA.args.english_data_files=$ENGLISH_POOL"
"+data.retain.Multilingual_QA.args.english_data_files=$ENGLISH_POOL"
```

This block lists arguments, not a standalone shell script. Set `ENGLISH_POOL`
to the appropriate existing data file before incorporating the arguments into
`python -m cllpu.train --config-name unlearn ...` or the seed launcher:

| Setting | English translation pool under the existing data root |
| --- | --- |
| Common | `multilingual/qa_flat.en.jsonl` |
| Culture | `multilingual/train_splits/culture_origin/<origin>_eval_all_languages_core_surface.jsonl` |

The pool is filtered to English core training facts, without surface questions
or evaluation scores entering the objective. Keep Culture's source/origin and
expected counts consistent with the existing Culture recipe (Arabic 33,
Bengali 27, other origins 30). The source monitor counts are twice the training
count times four QA variants. Evaluation continues to use the original source
language, not the mixed training language distribution.

The mixture uses local RNG with `mixture_seed=0` by default and does not mutate
global RNG state. To vary the mixture with each training seed, explicitly add
`'+data.forget.Multilingual_QA.args.mixture_seed=${trainer.args.seed}'`.
Dataset instances expose `mixture_manifest` for optional inspection.
The existing shell grid-sweep wrappers retain their original method lists;
use direct Hydra overrides or the new seed launcher for Combined.

## Qwen2.5-14B-Instruct

Select `model=Qwen2.5-14B-Instruct`. For unlearning, `target_model` must be the
desired fine-tuned Qwen checkpoint, as with the existing Llama workflow.
For SFT/retain-reference SFT, the model definition defaults to the public
`Qwen/Qwen2.5-14B-Instruct` model/tokenizer. Pin both model and tokenizer
revisions yourself when an immutable upstream revision is required.

The adapter uses the tokenizer's native chat template, explicitly supplies
`You are a helpful assistant.`, preserves native PAD/EOS tokens, and sets
`append_eos_token=false`. The native `<|im_end|>` and following newline are
retained without appending another EOS. The preprocessing default remains
unchanged for Llama. Existing truncation and answer-only masking still apply;
a truncated response is not guaranteed to retain its end marker.

No learning rate, epoch count, batch size, selected checkpoint, local model
path, or GPU topology is fixed by these additions. BF16/FlashAttention model
defaults require a compatible installation and hardware. Existing generation
and scoring configurations remain in force; this does not replace the ROUGE
tokenizer or bundle evaluation model weights.

Nested FSDP options are converted to plain Python containers before creating
`TrainingArguments`. Full-state FSDP saves collect the state on every rank and
write on the saving rank with the repository's pinned Transformers/Accelerate
versions. Configure Qwen wrapping using `Qwen2DecoderLayer` when using class-
based auto-wrap. No particular hardware capacity or full-size distributed run
is certified by the unit tests.

## Validation

Run `python -m pytest -q runtime/tests` with the development dependencies.
Added tests cover Common/Culture translation alignment across all ten
languages, the loss and gradient, EOS/label masking, Hydra composition,
seed execution isolation/failure behavior, and FSDP save dispatch.
