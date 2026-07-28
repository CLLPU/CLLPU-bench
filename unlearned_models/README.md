# Original, Retrain, and Unlearned Models

## Model lineage

```text
Meta-Llama-3.1-8B-Instruct
|-- SFT on all forget + retain core QAs in 10 languages -> Original
|   `-- unlearn separately for each source language s -> M_u^(s)
`-- SFT on retain core QAs only -> Retrain (common-goal reference only)
```

The paper's **Original** model is a benchmark-specific knowledge-injected model, not the untouched Hugging Face checkpoint.

## Reference models

| Model | Initialization | Training data | Purpose |
|---|---|---|---|
| Original | base Instruct model | forget + retain core QAs, all ten languages | common starting point for all unlearning runs |
| Retrain | same base Instruct model | retain core QAs only | common-goal oracle-like reference without target training |

Retrain is omitted from the language-conditioned setting because a clean retraining oracle is not well-defined: retaining the target in non-source languages can transfer it back to the source language, while removing it globally violates the preservation objective.

## Source-specific unlearning

For every setting, method, and source language `s`:

1. initialize from Original;
2. train on forget core QAs in `s`;
3. when required by the method, use retain core QAs in the same `s`;
4. select a checkpoint using low source-language target accessibility and high source-language neighbor accessibility;
5. evaluate the selected checkpoint in every language `t`.

Methods:

```text
GA, GD, NPO, SimNPO, BalDRO-NPO, BalDRO-SimNPO
```

Expected full matrix:

```text
2 settings x 6 methods x 10 source languages = 120 selected unlearned checkpoints
```

## Required checkpoint identity

Every exported checkpoint or adapter should be accompanied by a machine-readable manifest containing:

```text
setting
method
source_language
base_model
original_model_run_id
dataset_release/version
forget_split
retain_split
hyperparameters
epoch/checkpoint
selection_metrics
artifact_path or public model ID
```

Recommended layout:

```text
unlearned_models/
|-- manifests/
|   |-- original.json
|   |-- retrain.json
|   `-- <setting>/<method>/<source_language>.json
`-- README.md
```

Do not commit large model weights to Git. Publish weights in a model registry or external artifact store and commit only manifests, checksums, and stable IDs/URLs.

## Current repository status

The construction data, evaluation records, matrices, and plots are present. Existing experiment notes refer to an `open-unlearning-main` runtime containing Hydra configs, training code, saved checkpoints, and exported evaluation artifacts. That runtime is not currently included in this repository, so model training is not yet reproducible from this checkout alone.

There is also a protocol item to reconcile before claiming paper-level reproduction: current experiment notes describe one combined `common + culture_specific` knowledge-injection split, whereas the paper presents the two settings as separate evaluation objectives. The released runtime/configuration should make explicit whether Original is shared across settings or built per setting and should record that choice in every model manifest.

Current model documentation:

- [`evaluation/models/finetuned-and-retain-reference.md`](../evaluation/models/finetuned-and-retain-reference.md)
- [`evaluation/protocols/current-experiment-flow.md`](../evaluation/protocols/current-experiment-flow.md)
- [`evaluation/protocols/common-unlearning-sweep-screening.md`](../evaluation/protocols/common-unlearning-sweep-screening.md)
- [`evaluation/protocols/culture-specific-unlearning-protocol.md`](../evaluation/protocols/culture-specific-unlearning-protocol.md)
- [`evaluation/results/common/selected-checkpoints.md`](../evaluation/results/common/selected-checkpoints.md)

The next reproducibility milestone is to vendor or release the runtime configs and populate manifests for Original, Retrain, and all selected source-specific checkpoints.
