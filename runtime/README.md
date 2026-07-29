# CLLPU Runtime

This directory is the single boundary for active model-training, unlearning,
evaluation, and result-export code. It does not contain or execute the CLLPU
data-construction pipeline.

```text
runtime/
|-- configs/      Hydra model, data, trainer, experiment, and metric configs
|-- data/         reviewed JSONL snapshot consumed by the runtime
|-- evaluation/   compatibility entry points for the earlier evaluator names
|-- scripts/      supported sweep, optional-evaluation, and export commands
|-- src/          installable `cllpu` Python package
`-- tests/        runtime, protocol, packaging, and metric regression tests
```

Run commands from the repository root. This preserves the public defaults:

```text
data root    = runtime/data/
output root  = outputs/
config root  = runtime/configs/
```

Install and verify the runtime from the repository root:

```bash
python -m pip install -r requirements.txt
python -m pip install -e . --no-deps
pytest -q
bash -n runtime/scripts/run_multilingual_unlearn_sweep.sh
bash -n runtime/scripts/run_multilingual_culture_origin_unlearn_sweep.sh
```

Editable installation exposes the `cllpu` Python package and the equivalent
`cllpu-train` and `cllpu-eval` console commands.

The root [`README.md`](../README.md) contains the complete SFT, unlearning,
evaluation, optional-metric, and result-export commands. The frozen runtime
inputs and their protocol summary are under
[`data/multilingual/`](data/multilingual/) and
[`data/README.md`](data/README.md). Construction sources remain in the
top-level stage directories and `code/`.
