# 当前实验流程

本文记录当前 multilingual unlearning benchmark 的 finetune、retain reference、pre evaluation、holdout 状态与后续 unlearning 评估流程。

依据来源：

```text
open-unlearning-main/data/multilingual/manifest.json
open-unlearning-main/configs/data/finetune_multilingual.yaml
open-unlearning-main/configs/experiment/finetune/multilingual/default.yaml
open-unlearning-main/configs/eval/multilingual.yaml
open-unlearning-main/configs/experiment/unlearn/multilingual/default.yaml
open-unlearning-main/docs/multilingual.md
open-unlearning-main/docs/multilingual-evaluation-workflow.md
```

## 1. 数据范围

当前 runtime 数据包含四类 dataset family：

| 数据族 | 来源 | 结构 | 当前用途 |
|---|---|---|---|
| `common` | `../data/qa_variants.<language>.json` | relation-matched target/neighbor，core/surface | 当前 common forgetting 主协议的训练与默认 full eval |
| `culture_specific` | `../data/qa_variants.<language>.culture_specific.json` | relation-matched target/neighbor，core/surface | 已纳入 common+culture SFT 与 retain reference；当前 culture-origin grouped unlearning 协议已单独记录 |
| `common_holdout` | `../data/holdout_qa.<language>.json` | singleton held-out cards，非 target/neighbor pair | MIA / membership-inference 类评估，不进入训练 |
| `culture_holdout` | `../data/holdout_qa.<language>.culture_specific.json` | singleton culture-specific held-out cards，非 target/neighbor pair | culture-specific holdout / MIA 类评估，不进入训练 |

语言范围固定为：

```text
ar, bn, de, en, es, fr, ja, sw, th, zh
```

样本数：

| 数据族 | 每语言样本数 | 总样本数 |
|---|---:|---:|
| `common` | 4000 | 40000 |
| `culture_specific` | 2400 | 24000 |
| `common_holdout` | 500 | 5000 |
| `culture_holdout` | 300 | 3000 |

## 2. Runtime split

OpenUnlearning 侧 runtime 数据位置：

```text
open-unlearning-main/data/multilingual/
```

关键 split：

| 文件 | 样本数 | 用途 |
|---|---:|---|
| `qa_flat.<lang>.jsonl` | 4000/language | common full eval、common unlearning forget/retain 与训练时 monitoring |
| `culture_specific/qa_flat.<lang>.jsonl` | 2400/language | culture-specific relation-matched eval |
| `common_holdout/qa_flat.<lang>.jsonl` | 500/language | common holdout / MIA eval |
| `culture_holdout/qa_flat.<lang>.jsonl` | 300/language | culture-specific holdout / MIA eval |
| `train_splits/sft_core_culture_only.jsonl` | 6000 | culture-specific target+neighbor core SFT 子集 |
| `train_splits/sft_core_common_plus_culture.jsonl` | 16000 | finetuned-pre SFT 与 retain reference 训练入口 |
| `train_splits/eval_common_plus_culture_all.jsonl` | 64000 | common + culture-specific relation-matched 合并 eval |
| `train_splits/eval_culture_all.jsonl` | 24000 | culture-specific relation-matched eval |
| `train_splits/eval_common_holdout_all.jsonl` | 5000 | common holdout eval |
| `train_splits/eval_culture_holdout_all.jsonl` | 3000 | culture-specific holdout eval |
| `train_splits/culture_origin/<origin>_*` | 见 `train_splits/culture_origin/manifest.json` | culture-origin grouped unlearning/eval |

`common_holdout` 与 `culture_holdout` 的 `knowledge_pair_id` 有意为空，因为它们不是 target/neighbor relation-matched knowledge pairs。它们不参与当前 common transfer/profile 的 per-knowledge 聚合。

## 3. Finetuned-pre

finetuned-pre 是后续 unlearning 的统一起点模型。当前口径是从原始 Instruct 模型出发，使用 common + culture-specific 的 target/neighbor core QA 做 SFT。该口径有明确 Hydra 配置支持。

| 项 | 设置 |
|---|---|
| run id | `multilingual_Llama-3.1-8B-Instruct_common_culture_core_b8g4` |
| base model | `model/Meta-Llama-3.1-8B-Instruct` |
| data file | `data/multilingual/train_splits/sft_core_common_plus_culture.jsonl` |
| languages | `ar,bn,de,en,es,fr,ja,sw,th,zh` |
| topic roles | `target,neighbor` |
| variant layers | `core` |
| expected count | 16000 |
| seed | 0 |
| epochs | 5 |
| learning rate | `1e-5` |
| weight decay | `0.01` |
| warmup epochs | `1.0` |
| training eval | disabled: `do_eval=false`, `eval_strategy=no` |

样本数计算：

```text
common core: 10 languages x (500 target + 500 neighbor) = 10000
culture-specific core: 10 languages x (300 target + 300 neighbor) = 6000
total = 16000
```

最小训练命令：

```bash
cd open-unlearning-main
python src/train.py --config-name=train.yaml \
  experiment=finetune/multilingual/default \
  task_name=multilingual_Llama-3.1-8B-Instruct_common_culture_core_b8g4
```

## 4. Retain Reference

retain reference model 是离线参考模型，不是 unlearning 训练中的 source-language retain batch。它从原始 Instruct 模型出发，只学习 expanded benchmark 中应保留的 neighbor/core 知识。当前仓库文档和结果 workbook 已固定该口径；但尚未看到独立 retain reference Hydra experiment YAML，因此长期复现时需要补齐或归档实际运行命令。

| 项 | 设置 |
|---|---|
| run id | `multilingual_Llama-3.1-8B-Instruct_common_culture_neighbor_core_b8g4_retain` |
| base model | `model/Meta-Llama-3.1-8B-Instruct` |
| data file | `data/multilingual/train_splits/sft_core_common_plus_culture.jsonl` |
| languages | `ar,bn,de,en,es,fr,ja,sw,th,zh` |
| topic roles | `neighbor` |
| variant layers | `core` |
| expected count | 8000 |
| seed | 0 |
| epochs | 5 |
| learning rate | `1e-5` |
| weight decay | `0.01` |
| warmup epochs | `1.0` |
| effective batch size | 32 |

样本数计算：

```text
common neighbor core: 10 languages x 500 = 5000
culture-specific neighbor core: 10 languages x 300 = 3000
total = 8000
```

该模型不包含 target QA、surface QA、`common_holdout` QA 或 `culture_holdout` QA。

## 5. 当前 full evaluation

当前已有结果记录覆盖 finetuned-pre 与 retain reference 在以下 relation-matched 数据上的 full multilingual evaluation：

| 数据族 | 每语言样本数 | 总样本数 | roles | variants |
|---|---:|---:|---|---|
| `common` | 4000 | 40000 | target, neighbor | core, surface |
| `culture_specific` | 2400 | 24000 | target, neighbor | core, surface |

指标：

| 指标 | 含义 |
|---|---|
| `a_exact` | cleaned generation 与 `expected_answer` 的 strict exact match |
| `a_rouge` | ROUGE-L F1 |
| `A_current(target,t)` | 语言 `t` 的 target accessibility，按 core/surface 加权 |
| `A_current(neighbor,t)` | 语言 `t` 的 neighbor accessibility，按 core/surface 加权 |

默认变体权重：

```text
core=0.5, surface=0.5
```

当前 workbook 结果没有覆盖 `common_holdout` 或 `culture_holdout`，也不包含 unlearning checkpoint 的 post eval 或 transfer/profile 结果。

## 6. 当前 common forgetting unlearning

当前第一阶段仍是 common forgetting 协议。unlearning 训练、训练时初筛和默认 full eval 均使用 common relation-matched QA，不混入 `culture_specific`、`common_holdout` 或 `culture_holdout`。

对每个 source language `s`：

| split | 数据 | 过滤 | 数量 |
|---|---|---|---:|
| forget | `data/multilingual/qa_flat.<s>.jsonl` | `topic_role=target, variant_layer=core` | 500 |
| retain | `data/multilingual/qa_flat.<s>.jsonl` | `topic_role=neighbor, variant_layer=core` | 500 |
| training-time eval | `data/multilingual/qa_flat.<s>.jsonl` | target/neighbor, core/surface | 4000 |

训练中 retain batch 的含义是 source-language common neighbor/core 保持集约束；它不等同于 retain reference model。

完整 pre/post transfer profile 需要：

1. 对 finetuned-pre 跑一次 common full eval，作为 `A_pre`。
2. 对每个 unlearn checkpoint 跑同一 common full eval，作为 `A_post^(s)`。
3. 用 `scripts/aggregate_multilingual_transfer.py` 按 `qa_id` 严格对齐，计算 `T_{s->t}`、`R_nbr(s,t)` 与 `D_nbr(s,t)`。

这里的 full eval 指当前 common forgetting 协议的 common 40000 条 relation-matched QA，不包括 `culture_specific`、`common_holdout` 或 `culture_holdout`。

## 7. 当前 culture-origin grouped unlearning

Culture-specific forgetting/eval 当前作为独立协议记录，不混入上述 common forgetting 主流程。正式入口见：

```text
evaluation/protocols/culture-specific-unlearning-protocol.md
open-unlearning-main/configs/experiment/unlearn/multilingual/culture_origin.yaml
open-unlearning-main/configs/experiment/eval/multilingual/culture_origin.yaml
open-unlearning-main/scripts/run_multilingual_culture_origin_unlearn_sweep.sh
```

该协议按 `culture_origin` 分组，并强制 `source_language == culture_origin`。训练时 forget 使用 `<origin>_forget_target_core.jsonl`，retain 使用 `<origin>_retain_neighbor_core.jsonl`，训练时 monitor 使用 `<origin>_source_monitor_core_surface.jsonl`，正式 all-language eval 使用 `<origin>_eval_all_languages_core_surface.jsonl`。

当前 split 计数以 `data/multilingual/train_splits/culture_origin/manifest.json` 为准：`ar` 为 33/33/264/2640，`bn` 为 27/27/216/2160，其余 8 个 origin 为 30/30/240/2400。这里的四个数依次对应 forget target/core、retain neighbor/core、source monitor core+surface、full eval all languages core+surface。

## 8. Holdout 状态

`common_holdout` 和 `culture_holdout` 已经有 runtime JSONL 与 all-language eval split，但当前没有 finetuned-pre 或 retain reference 在这两类 holdout 上的结果表。

后续若执行 holdout/MIA 评估，应单独记录：

- 使用的数据入口：`eval_common_holdout_all.jsonl` 或 `eval_culture_holdout_all.jsonl`
- 评估模型 run id 与 checkpoint
- 是否使用 QA accessibility、membership-inference 指标或二者同时使用
- 原始输出目录与可复算 artifact
