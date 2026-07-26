# Common Unlearning 扫参与初筛方案

本文记录当前 common forgetting 部分的六方法扫参范围、每个 source language 的训练数据口径、训练时初筛评估方案和 Pareto checkpoint 初筛规则。本文记录的是当前固定实验计划与执行口径。

## 1. 依据来源

```text
open-unlearning-main/scripts/run_multilingual_unlearn_sweep.sh
open-unlearning-main/scripts/select_pareto_checkpoints.py
open-unlearning-main/configs/experiment/unlearn/multilingual/default.yaml
open-unlearning-main/configs/trainer/GradAscent.yaml
open-unlearning-main/configs/trainer/GradDiff.yaml
open-unlearning-main/configs/trainer/NPO.yaml
open-unlearning-main/configs/trainer/SimNPO.yaml
open-unlearning-main/configs/trainer/DrNPO.yaml
open-unlearning-main/configs/trainer/DrSimNPO.yaml
```

当前 source languages：

```text
ar, bn, de, en, es, fr, ja, sw, th, zh
```

每个 source language 使用相同的 six-method grid。本文中的 “每语言” 指单个 source language `s` 上的一套 common forgetting sweep。

## 2. Common unlearning 数据口径

当前 common forgetting 只使用 common relation-matched QA，不混入 `culture_specific`、`common_holdout` 或 `culture_holdout`。

对每个 source language `s`：

| split | data file | filter | expected_count |
|---|---|---|---:|
| forget | `data/multilingual/qa_flat.<s>.jsonl` | `language=s, topic_role=target, variant_layer=core` | 500 |
| retain | `data/multilingual/qa_flat.<s>.jsonl` | `language=s, topic_role=neighbor, variant_layer=core` | 500 |
| training-time screening eval | `data/multilingual/qa_flat.<s>.jsonl` | `language=s, topic_role in {target,neighbor}, variant_layer in {core,surface}` | 4000 |

训练起点模型：

```text
saves/finetune/multilingual_Llama-3.1-8B-Instruct_common_culture_core_b8g4
```

该起点是 common+culture SFT 后的 finetuned-pre checkpoint，但当前 unlearning sweep 的 forget/retain 数据只取 common。

## 3. 全局训练设置

| 项 | 当前设置 |
|---|---|
| epochs | 10 |
| effective batch size | 32 |
| per-device train batch size | 8 |
| gradient accumulation steps | 4 |
| optimizer | `paged_adamw_32bit` |
| weight decay | `0.01` |
| warmup | 1 epoch linear warmup，配置字段为 `warmup_epochs=1.0` |
| learning rate | `{1e-5, 3e-5, 5e-5}` |
| retain loss weight `lambda` | `{1}`，在脚本参数中对应 `alpha=1.0` |
| save strategy | epoch |
| training eval strategy | epoch |
| final model save | false |
| epoch checkpoint | model-only checkpoint，保留 eval outputs |

## 4. 六方法扫参范围

| 方法 | trainer | 扫参维度 | 每语言 run 数 |
|---|---|---|---:|
| GA | `GradAscent` | `learning_rate in {1e-5,3e-5,5e-5}` | 3 |
| GD | `GradDiff` | `learning_rate in {1e-5,3e-5,5e-5}`, `alpha=1`, `gamma=1` | 3 |
| NPO | `NPO` | `learning_rate in {1e-5,3e-5,5e-5}`, `beta in {0.1,0.5}`, `alpha=1`, `gamma=1` | 6 |
| SimNPO | `SimNPO` | `learning_rate in {1e-5,3e-5,5e-5}`, `beta in {3.5,4.5}`, `delta=1`, `gamma in {0.125,0.25}`, `alpha=1` | 12 |
| BalDRO + NPO | `DrNPO` | NPO grid plus forget-side DV strength `beta_dv_forget in {2,5}` | 12 |
| BalDRO + SimNPO | `DrSimNPO` | SimNPO grid plus forget-side DV strength `sigma_forget in {2,5}` | 24 |

每个 source language 总 run 数：

```text
GA 3 + GD 3 + NPO 6 + SimNPO 12 + DrNPO 12 + DrSimNPO 24 = 60
```

10 个 source languages 全部完成时，总训练 run 数为：

```text
60 runs/language x 10 languages = 600 runs
```

## 5. 方法参数映射

| 文档名称 | 代码字段 | 说明 |
|---|---|---|
| retain loss weight `lambda` | `trainer.method_args.alpha` | 当前固定为 `1.0`；GA 不使用该字段 |
| GD/NPO forget loss weight | `trainer.method_args.gamma` | GD、NPO、DrNPO 当前固定为 `1.0` |
| NPO beta | `trainer.method_args.beta` | NPO、DrNPO 使用 `{0.1,0.5}` |
| SimNPO beta | `trainer.method_args.beta` | SimNPO、DrSimNPO 使用 `{3.5,4.5}` |
| SimNPO delta | `trainer.method_args.delta` | 当前固定为 `1` |
| SimNPO gamma | `trainer.method_args.gamma` | SimNPO、DrSimNPO 使用 `{0.125,0.25}` |
| BalDRO + NPO forget DV | `trainer.method_args.beta_dv_forget` | DrNPO 使用 `{2,5}` |
| BalDRO + SimNPO forget DV | `trainer.method_args.sigma_forget` | DrSimNPO 使用 `{2,5}` |
| retain-side DRO | `trainer.method_args.retain_dro` | 当前保持 `false` |
| forget-side DRO | `trainer.method_args.forget_dro` | DrNPO、DrSimNPO 当前为 `true` |

DrNPO 和 DrSimNPO 当前只扫 forget-side DV。由于 `retain_dro=false`，`beta_dv_retain` / `sigma_retain` 不参与当前 retain loss 的 DRO 聚合，不作为本轮 sweep 维度记录。

## 6. 训练时初筛评估

训练时初筛不是完整多语言 full eval。它只评估当前 source language `s` 的 common QA：

| 项 | 设置 |
|---|---|
| data | `data/multilingual/qa_flat.<s>.jsonl` |
| expected_count | 4000 |
| roles | `target,neighbor` |
| variants | `core,surface` |
| metrics | `a_exact,a_rouge` |
| eval batch size | 32 |
| variant weights | `core=0.5, surface=0.5` |
| monitor summary | `monitor_summary_only=true` |

训练中每个 epoch 结束时进行一次 screening eval，并保存同 step 的 checkpoint。评估输出写入 checkpoint 的 `evals/` 目录，关键文件包括：

```text
saves/unlearn/<run_id>/checkpoint-<step>/evals/
  generations.jsonl
  MULTILINGUAL_EVAL.json
  MULTILINGUAL_SUMMARY.json
  MULTILINGUAL_REPORT.json
  manifest.json
```

训练时初筛重点读取当前 source language 下：

```text
A_current_exact/target/<s>/weighted
A_current_exact/neighbor/<s>/weighted
A_current_rouge/target/<s>/weighted
A_current_rouge/neighbor/<s>/weighted
```

其中 target weighted 越低表示 source-language target QA 越不可访问；neighbor weighted 越高表示 source-language neighbor QA 保留越好。

## 7. Pareto checkpoint 初筛规则

当前初筛脚本：

```text
open-unlearning-main/scripts/select_pareto_checkpoints.py
```

当前 selection mode 为 `balanced`，筛选指标为：

```text
metric = A_current_rouge
variant = weighted
```

有效候选条件：

```text
A_current_rouge(target,s).weighted <= 0.5
A_current_rouge(neighbor,s).weighted >= 0.5
```

在有效候选集合上，脚本执行全局 Pareto frontier 筛选：

```text
minimize A_current_rouge(target,s).weighted
maximize A_current_rouge(neighbor,s).weighted
```

balanced mode 最多保留 3 个代表 checkpoint：

| 代表点 | 选择倾向 |
|---|---|
| `best_forget` | target weighted ROUGE 最低 |
| `best_retain` | neighbor weighted ROUGE 最高 |
| `best_balanced` | `neighbor_score - target_score` 最大 |

筛选范围应是同一个 method + source language 的全部 sweep checkpoints，而不是单个 run 内部。例如 NPO + `s=en` 应在该方法该语言的所有 learning-rate/beta checkpoint 中做 global top-3。

如果没有 checkpoint 满足 balanced 有效候选条件，脚本会输出 `weak_candidate=true` 的弱候选。当前脚本在该情况下只保留 1 个弱候选；选择规则是在该 language + method 的全部已评分 checkpoints 中最大化：

```text
neighbor_score - target_score
```

其中：

```text
target_score = A_current_rouge(target,s).weighted
neighbor_score = A_current_rouge(neighbor,s).weighted
```

若 `neighbor_score - target_score` 相同，脚本进一步偏向 `target_score` 更低、`neighbor_score` 更高的 checkpoint。该弱候选表示“没有达到 balanced 有效候选阈值时，按当前规则能找到的相对最好折中点”。

每个 language + method 经过 balanced Pareto 规则最多保留 3 个候选 checkpoints。后续需要对这 3 个候选进行人工比较，最终只保留 1 个作为该 language + method 的 best checkpoint。这里的 best checkpoint 指“在当前筛选规则和人工比较流程下选出的最佳 checkpoint”，不声明为整个扫参空间、所有可能超参数或所有评价指标下的绝对最优 checkpoint。

若某个 language + method 没有 balanced 有效候选，则不再进入 top-3 人工比较流程；当前记录口径下直接取该唯一 `weak_candidate=true` checkpoint 作为该 language + method 的 rule-based best checkpoint。该 checkpoint 仍需在结果表中显式标注 `weak_candidate=true`，以区别于满足 balanced 有效候选阈值后再经人工比较选出的 best checkpoint。

## 8. 保存与清理边界

当前 checkpoint selection 只写 JSON report，不删除任何 checkpoint。

若开启：

```text
--delete-non-kept-weights --yes
```

只删除非保留 checkpoint 目录中的模型权重文件，保留 eval outputs、Hydra config、manifest 和 summary。这样后续仍可基于已有 `generations.jsonl` 与 report 复算筛选表，但不能再用被清理权重的 checkpoint 重新生成答案。

不建议在正式实验归档前使用：

```text
--delete-non-frontier --yes
```

该模式会删除整个非保留 checkpoint 目录，包括评估输出。

## 9. 后续 full eval 与论文记录

训练时初筛只用于快速筛选 source-language checkpoint。进入论文主表或最终实验比较前，保留 checkpoint 还需要单独运行当前 common forgetting 协议的 full eval：

```text
common 10 languages x target/neighbor x core/surface = 40000 QA
```

然后与 finetuned-pre 的 common full eval 按 `qa_id` 对齐，计算 source-row 或 full-transfer profile。训练时初筛指标不能直接替代正式 transfer/profile 结果。
