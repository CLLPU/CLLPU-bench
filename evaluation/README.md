# Evaluation

本目录记录 multilingual unlearning benchmark 的具体实验流程、模型口径、评估范围、指标定义、结果表和待补齐状态。

当前记录覆盖 10 种语言：

```text
ar, bn, de, en, es, fr, ja, sw, th, zh
```

## 当前数据范围

数据范围依据：

```text
open-unlearning-main/data/multilingual/manifest.json
open-unlearning-main/data/multilingual/README.md
open-unlearning-main/docs/multilingual.md
open-unlearning-main/data/multilingual/train_splits/culture_origin/manifest.json
```

| 数据族 | 每语言样本数 | 总样本数 | 当前用途 |
|---|---:|---:|---|
| `common` | 4000 | 40000 | 当前 common forgetting 主协议的训练、默认 full eval 与 transfer/profile 聚合 |
| `culture_specific` | 2400 | 24000 | common+culture SFT、retain reference，以及 culture-origin grouped unlearning/eval |
| `common_holdout` | 500 | 5000 | MIA / membership-inference 类评估保留集，不进入 SFT 或 unlearning 训练 |
| `culture_holdout` | 300 | 3000 | culture-specific holdout / MIA 类评估保留集，不进入 SFT 或 unlearning 训练 |

Derived split：

| 文件 | 样本数 | 用途 |
|---|---:|---|
| `train_splits/sft_core_culture_only.jsonl` | 6000 | culture-specific target+neighbor core SFT 子集 |
| `train_splits/sft_core_common_plus_culture.jsonl` | 16000 | 当前 finetuned-pre 与 retain reference 的训练入口 |
| `train_splits/eval_common_plus_culture_all.jsonl` | 64000 | common + culture-specific 关系匹配数据的合并评估入口 |
| `train_splits/eval_culture_all.jsonl` | 24000 | culture-specific 关系匹配数据评估入口 |
| `train_splits/eval_common_holdout_all.jsonl` | 5000 | common holdout 评估入口 |
| `train_splits/eval_culture_holdout_all.jsonl` | 3000 | culture-specific holdout 评估入口 |
| `train_splits/culture_origin/<origin>_*` | 见 `culture_origin/manifest.json` | culture-origin grouped unlearning/eval |

## 当前文档

- [Multilingual Unlearning 指标定义](metrics/multilingual-unlearning-metrics.md)
- [当前实验流程](protocols/current-experiment-flow.md)
- [Common Unlearning 扫参与初筛方案](protocols/common-unlearning-sweep-screening.md)
- [Culture-specific Unlearning 实验协议](protocols/culture-specific-unlearning-protocol.md)
- [Finetuned 与 Retain Reference 模型口径](models/finetuned-and-retain-reference.md)
- [Finetuned 与 Retain Reference 评估结果](results/finetune-retain-common-culture-eval.md)
- [Holdout 评估状态](results/holdout-evaluation-status.md)
- [Common Selected-checkpoint Results](results/common/README.md)

## 记录约定

- 写入本目录的结果必须标明来源 artifact、数据范围、模型 run id、指标口径和是否有原始评估产物。
- `common_holdout` 与 `culture_holdout` 只记录为 holdout/MIA 评估数据；除非后续协议明确改变，否则不得写入 finetune、forget 或 retain 训练数据。
- Common selected-checkpoint 结果使用 `common_selected_checkpoint_method_level_matrix` 口径：每个 method 的每个 source-language row 来自该语言最终保留的 checkpoint，不等同于严格 same-hyperparameter full-transfer profile。
- 论文写作若需要跨语言均值、显著性、置信区间或新指标，应从原始 workbook、CSV、JSONL 或 eval artifact 重新计算，并记录计算脚本与公式；本目录不把未记录来源的二次推导写成事实。
