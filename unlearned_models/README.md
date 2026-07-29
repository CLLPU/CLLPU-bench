# Target, Retain-Reference, and Unlearned Models

## Model Lineage

```text
meta-llama/Meta-Llama-3.1-8B-Instruct
|-- SFT on Common+Culture target/neighbor core QAs -> Target model
|   `-- source-specific Common or Culture unlearning -> Unlearned model
`-- independent SFT on Common+Culture neighbor core QAs -> Retain-reference
```

The Target model is a benchmark-specific knowledge-injected model, not the
untouched Hugging Face base checkpoint. Model weights are not committed to this
repository. Commands accept either a Hugging Face model ID or a local checkpoint
path, and write artifacts to a caller-selected output directory.

## Model Preparation

Both models are initialized independently from
`meta-llama/Meta-Llama-3.1-8B-Instruct`.

| Model | Training records | Protocol | Configuration |
| --- | ---: | --- | --- |
| Target | 16,000 Common+Culture target/neighbor core records | 5 epochs, batch size 8, gradient accumulation 4 | [`default.yaml`](../runtime/configs/experiment/finetune/multilingual/default.yaml) |
| Retain-reference | 8,000 Common+Culture neighbor/core records | 5 epochs, batch size 8, gradient accumulation 4 | [`retain_reference.yaml`](../runtime/configs/experiment/finetune/multilingual/retain_reference.yaml) |

The Retain-reference model is used only as the Common-setting reference. It is
not used as a Culture-setting reference. Culture methods may still train with
the same-origin neighbor/core retain split defined by their objective; that
training split is not the independently trained Retain-reference model.

## Source-Specific Unlearning

Every unlearning run starts from the same Target model and operates on one
source language. The runtime provides six methods:

```text
GradAscent, GradDiff, NPO, SimNPO, DrNPO, DrSimNPO
```

`DrNPO` and `DrSimNPO` are the runtime names for the BalDRO-DV variants. The
executable experiment configurations are:

- Common: [`default.yaml`](../runtime/configs/experiment/unlearn/multilingual/default.yaml)
- Culture origin: [`culture_origin.yaml`](../runtime/configs/experiment/unlearn/multilingual/culture_origin.yaml)

During training, each saved epoch is screened only with Exact Match and
ROUGE-L from the source language. Cross-language behavior does not participate
in checkpoint screening. After checkpoint selection, multilingual evaluation
is run separately against the selected checkpoint.

## Evaluation Entry Points

The complete training, screening, and post-selection evaluation commands are
documented in the [root evaluation workflow](../README.md#evaluation).
Standalone evaluation configurations are under
[`runtime/configs/experiment/eval/multilingual/`](../runtime/configs/experiment/eval/multilingual/),
and compatibility wrappers are under
[`runtime/evaluation/`](../runtime/evaluation/).
