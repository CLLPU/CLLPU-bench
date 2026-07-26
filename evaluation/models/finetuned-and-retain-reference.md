# Finetuned 与 Retain Reference 模型口径

本文记录当前两个关键参考模型的训练口径、用途和排除项。

依据来源：

```text
open-unlearning-main/configs/data/finetune_multilingual.yaml
open-unlearning-main/configs/experiment/finetune/multilingual/default.yaml
open-unlearning-main/docs/multilingual.md
open-unlearning-main/docs/multilingual-evaluation-workflow.md
open-unlearning-main/saves/exports/new_export/finetune_retain_common_culture_full_eval_summary.xlsx
```

## 1. Finetuned-pre 模型

finetuned-pre 模型是后续 unlearning 的统一起点。它应显式学过 target 与 neighbor 两类知识，才能在 unlearning 后区分“知识被遗忘”和“模型从未学会”。

| 项 | 内容 |
|---|---|
| run id | `multilingual_Llama-3.1-8B-Instruct_common_culture_core_b8g4` |
| 训练起点 | 原始 `Llama-3.1-8B-Instruct` |
| 训练数据 | common + culture-specific |
| data file | `data/multilingual/train_splits/sft_core_common_plus_culture.jsonl` |
| 语言 | `ar,bn,de,en,es,fr,ja,sw,th,zh` |
| topic roles | `target,neighbor` |
| variant layers | `core` |
| 样本数 | 16000 |
| 训练轮数 | 5 |
| learning rate | `1e-5` |
| weight decay | `0.01` |
| warmup epochs | `1.0` |
| seed | 0 |
| training eval | disabled |

样本数计算：

```text
common core: 10 languages x (500 target + 500 neighbor) = 10000
culture-specific core: 10 languages x (300 target + 300 neighbor) = 6000
total = 16000
```

不包含：

- common surface QA
- culture-specific surface QA
- `common_holdout` QA
- `culture_holdout` QA

当前配置来源：

```text
open-unlearning-main/configs/experiment/finetune/multilingual/default.yaml
open-unlearning-main/configs/data/finetune_multilingual.yaml
```

## 2. Retain Reference 模型

retain reference model 是离线参考模型，用于表示“只学习应保留的 neighbor/core 知识”的参考状态。它不是从 finetuned-pre 继续训练，而是从原始 Instruct 模型出发单独 SFT。

| 项 | 内容 |
|---|---|
| run id | `multilingual_Llama-3.1-8B-Instruct_common_culture_neighbor_core_b8g4_retain` |
| 训练起点 | 原始 `Llama-3.1-8B-Instruct` |
| 训练数据 | common + culture-specific |
| data file | `data/multilingual/train_splits/sft_core_common_plus_culture.jsonl` |
| 语言 | `ar,bn,de,en,es,fr,ja,sw,th,zh` |
| topic roles | `neighbor` |
| variant layers | `core` |
| 样本数 | 8000 |
| 训练轮数 | 5 |
| learning rate | `1e-5` |
| weight decay | `0.01` |
| warmup epochs | `1.0` |
| effective batch size | 32 |
| seed | 0 |

样本数计算：

```text
common neighbor core: 10 languages x 500 = 5000
culture-specific neighbor core: 10 languages x 300 = 3000
total = 8000
```

不包含：

- target QA
- surface QA
- `common_holdout` QA
- `culture_holdout` QA

## 3. 与 Unlearning 训练中 retain batch 的区别

| 对象 | 阶段 | 数据范围 | 含义 |
|---|---|---|---|
| retain reference model | 离线参考模型 | common+culture 的全语言 neighbor/core，共 8000 条 | 只学习应保留知识的参考 checkpoint |
| unlearning retain batch | unlearning 训练 | 单个 source language 的 common neighbor/core，共 500 条 | 约束当前 unlearning loss 的保持集 |

二者都与 neighbor/core 有关，但不是同一个实验对象，不应在结果表中混写。

## 4. 可复现性注意

finetuned-pre 已有明确 Hydra config。retain reference 的训练口径已在文档和结果中固定，但当前未看到独立 retain reference experiment YAML。

因此，在论文或正式实验复现材料中，retain reference 应标记为“口径已记录、结果已导出；独立训练配置/实际命令仍需归档”。在补齐该配置前，不应把 retain reference 描述为已经一键可复现的实验。

后续建议补齐：

```text
open-unlearning-main/configs/experiment/finetune/multilingual/retain_reference.yaml
```

其中应显式设置：

```yaml
data.train.Multilingual_QA.args.topic_roles:
  - neighbor
data.train.Multilingual_QA.args.variant_layers:
  - core
data.train.Multilingual_QA.args.expected_count: 8000
```
