# Selected Seed Repetitions

`python -m cllpu.repeat_selected` implements a conditional seed repeat: select
one seed0 configuration/checkpoint per setting/method/source, then train that
configuration with seeds1-4 and compare at the same optimizer step. It does not
estimate the variability of a fresh hyperparameter search for every seed.

## Input Contract

The directory passed to `--seed0-run` must contain:

| File | Required content |
| --- | --- |
| `resolved_config.yaml` | Complete, resolved `cllpu.train` configuration; training seed0; same initial model and data as the original run |
| `training_context.json` | Original absolute `working_directory`, integer `world_size` and effective integer `warmup_steps` |
| `checkpoint-K/trainer_state.json` | Original selected `global_step=K`, full scheduler `max_steps`, and fractional `epoch` |

If the checkpoint state is absent, the run-root `trainer_state.json` is accepted
only if its `global_step` equals K. A final state from a later step cannot stand
in for a missing earlier checkpoint state. The input model weights are taken
from `resolved_config.yaml`, never from `checkpoint-K`.

New training runs save the first two files automatically. For legacy records,
recover them from that run's exact Hydra configuration, original environment,
working directory and effective training arguments. Do not resolve an old
`${oc.env:...}` against an unrelated environment or substitute today's recipe.
Unresolved/missing config values are rejected. Keep copies of the original
records with any manually recovered metadata. No historical experiment tables
or machine-specific configurations are shipped with this interface.

The record does not embed data or model files. Keep the same code, package
versions, data order/content, model/tokenizer files or immutable revisions,
attention implementation, GPU visibility and distributed topology. A matching
horizon is necessary but does not by itself prove the inputs are identical.
Changing hardware or nondeterministic kernels can still change results.

## Preserved and Changed Settings

Preserved: optimizer and method parameters, learning rate and scheduler type,
`num_train_epochs`, `max_steps` (if present), warmup configuration, micro-batch,
gradient accumulation, model/reference initialization, data, template, explicit
`data_seed`, Combined mixture, precision, distributed settings, and evaluation.
An unset `data_seed` continues to follow the Trainer's training seed semantics.
Interpolations are frozen: a seed0 expression that resolved `mixture_seed` to0
stays0, so only the training seed changes.

Changed: `trainer.args.seed`, task/run names and output/log/evaluation paths.
`save_final_model` is disabled because the worker explicitly saves the selected
model after checking the step/epoch. A callback suppresses intermediate weight
saves. These are output-management changes, not optimizer changes. The callback
does not disable or add scheduled evaluations; final standalone evaluation is
still a separate operation. Configured post-training evaluation is retained.

The callback checks that training starts at step0, the computed scheduler
horizon and effective warmup match seed0, and the selected update has the same
fractional epoch. It never sets `max_steps=K` to implement early stopping.
Changed world size, best-model reloading and implicit checkpoint resumption are
not supported. Every seed begins by loading the original configured model.

The launcher is single-node, serial over seeds. With `--nproc-per-node N`, each
seed uses `torch.distributed.run`; N must equal seed0's world size. It does not
automatically convert single-GPU settings to FSDP/ZeRO, or run independent seeds
concurrently. Existing distributed custom-evaluation restrictions still apply.

## Outputs and Failures

Each `RUN_NAME-seedN` directory contains:

- `repeat_config.yaml`: prepared config, hashed in `REPETITION.json`.
- `REPETITION.json`: original evidence hashes, selected step/epoch/horizon,
  original context, and an explicit before/after list of configuration changes.
- `resolved_config.yaml` and `training_context.json`: actual invocation metadata.
- `checkpoint-K/`: selected weights, tokenizer and trainer state.
- `REPEAT_COMPLETE.json`: written only after selected-step checks and saving.

W&B is enabled only if the original configuration enabled it. Inherited
`WANDB_RUN_ID`/`WANDB_RESUME` are cleared and each repeat gets its own run name.
Existing output directories are never overwritten. A failure stops the queue;
retain its evidence for diagnosis and use a new output name when retrying.

`--dry-run` validates the metadata and prints planned differences/commands. It
does not load weights, verify GPU capacity, or certify successful training.

## Evaluation and Reporting

Use the existing evaluation commands with the matching model-family config and
each `checkpoint-K`. Keep source-language MIA, ten-language Belebele, generation
and saved-generation scoring protocols consistent with seed0. Model-dependent
metrics need weights, so run them before deleting the selected model.

Aggregate each seed using the same language/QA weighting. Report the mean and
sample standard deviation over the independent per-seed macro scores, not over
individual QA rows or pooled language runs. State explicitly whether the summary
uses seeds1-4 only or includes seed0 (five seeds). This launcher does not silently
include seed0 or perform statistical aggregation.
