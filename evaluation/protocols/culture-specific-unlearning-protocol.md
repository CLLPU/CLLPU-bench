# Culture-specific Unlearning 实验协议

本文记录当前已实现的 culture-specific unlearning 协议，用于后续论文写作和实验复现。当前正式实现口径为 `culture-origin grouped protocol`：按 `culture_origin` 分组，在该 origin 对应语言上遗忘该文化来源的 target/core QA，并保留同一文化来源的 neighbor/core QA。

## 1. 研究目标

Culture-specific 实验用于检验遗忘边界：当只要求模型遗忘某一文化来源 `c` 的 target knowledge 时，遗忘是否主要发生在该 culture-origin/source-language 边界内，同时尽量保留同一 culture-origin 的 neighbor knowledge，并避免对其他语言或其他范围造成无关误伤。

与 common forgetting 不同，common 部分关注共享知识在跨语言空间中的遗忘传播；culture-specific 部分关注文化来源边界与 off-scope leakage。因此，culture-specific 的成功标准不能直接复用 common 中“跨语言 target transfer 越强越好”的解释。

## 2. 固定训练起点

当前 culture-origin unlearning 从 expanded finetuned-pre checkpoint 出发：

```text
saves/finetune/multilingual_Llama-3.1-8B-Instruct_common_culture_core_b8g4
```

该 checkpoint 由 common core target+neighbor 与 culture-specific core target+neighbor 的合并 SFT split 训练得到：

```text
data/multilingual/train_splits/sft_core_common_plus_culture.jsonl
= 16000 QA
```

这样可以保证模型在 unlearning 前已经学习过 culture-specific 知识。`common_holdout` 与 `culture_holdout` 不进入 SFT、forget 或 retain，只用于 holdout/MIA-style evaluation 或独立诊断。

## 3. Culture-origin 定义与 split

当前 split 来源：

```text
open-unlearning-main/data/multilingual/train_splits/culture_origin/
open-unlearning-main/data/multilingual/train_splits/culture_origin/manifest.json
open-unlearning-main/scripts/prepare_multilingual_culture_origin_splits.py
```

`culture_origin` 的当前规则为：取 `pair_id` 第一个下划线之前的 token，并验证其属于 10 语言 origin 集合：

```text
ar, bn, de, en, es, fr, ja, sw, th, zh
```

当前每个 culture-origin 的 split 计数如下。正式运行时应按此 manifest 或脚本传入的 override 设置 `expected_count`；不能默认假设所有 origin 都是 30/240/2400。

| culture_origin | source_language | forget target/core | retain neighbor/core | source monitor core+surface | full eval all languages core+surface |
| --- | --- | --- | --- | --- | --- |
| ar | ar | 33 | 33 | 264 | 2640 |
| bn | bn | 27 | 27 | 216 | 2160 |
| de | de | 30 | 30 | 240 | 2400 |
| en | en | 30 | 30 | 240 | 2400 |
| es | es | 30 | 30 | 240 | 2400 |
| fr | fr | 30 | 30 | 240 | 2400 |
| ja | ja | 30 | 30 | 240 | 2400 |
| sw | sw | 30 | 30 | 240 | 2400 |
| th | th | 30 | 30 | 240 | 2400 |
| zh | zh | 30 | 30 | 240 | 2400 |

## 4. 训练数据口径

对每个 `culture_origin=c`，当前协议强制 `source_language=c`。脚本会拒绝 `source_language != culture_origin` 的运行。

| split | file pattern | filter | 用途 |
|---|---|---|---|
| forget | `data/multilingual/train_splits/culture_origin/<c>_forget_target_core.jsonl` | `dataset_family=culture_specific, culture_origin=c, language=c, topic_role=target, variant_layer=core` | unlearning forget batch |
| retain | `data/multilingual/train_splits/culture_origin/<c>_retain_neighbor_core.jsonl` | `dataset_family=culture_specific, culture_origin=c, language=c, topic_role=neighbor, variant_layer=core` | retain batch |
| train-time monitor | `data/multilingual/train_splits/culture_origin/<c>_source_monitor_core_surface.jsonl` | `culture_origin=c, language=c, topic_role in {target,neighbor}, variant_layer in {core,surface}` | 训练时同源快速监控 |
| full eval | `data/multilingual/train_splits/culture_origin/<c>_eval_all_languages_core_surface.jsonl` | `culture_origin=c, all languages, topic_role in {target,neighbor}, variant_layer in {core,surface}` | 入选 checkpoint 的 all-language culture-origin eval |

## 5. 当前配置与脚本

训练配置：

```text
open-unlearning-main/configs/experiment/unlearn/multilingual/culture_origin.yaml
```

正式 all-language eval 配置：

```text
open-unlearning-main/configs/experiment/eval/multilingual/culture_origin.yaml
```

culture-origin sweep 入口：

```text
open-unlearning-main/scripts/run_multilingual_culture_origin_unlearn_sweep.sh
```

默认输出根目录：

```text
saves/unlearn/<origin>/culture_origin_<origin>_train_eval_grid/
```

注意：`eval/multilingual/culture_origin.yaml` 中 `multilingual_culture_eval_expected_count` 的默认值是 2400；对 `ar` 和 `bn` 做正式 full eval 时，必须按 split manifest 显式覆盖为 2640 和 2160。

## 6. 训练设置

当前配置中的固定训练设置：

| 项 | 当前设置 |
|---|---|
| seed | `0` |
| epochs | `10` |
| per-device train batch size | `4` |
| gradient accumulation steps | `2` |
| effective batch size | `8` |
| optimizer | trainer 配置中的 paged AdamW 系列设置；与具体 method trainer 配置共同生效 |
| learning rate default | `1e-5`，sweep 时由外层脚本覆盖 |
| weight decay | `0.01` |
| warmup | `warmup_epochs=1.0` |
| eval strategy | epoch |
| save strategy | epoch |
| save only model | true |
| final model save | false |
| post train eval | false |

当前 culture-origin sweep 默认方法集合与参数范围继承 `run_multilingual_unlearn_sweep.sh` 的方法循环，并由 culture-origin wrapper 设置：

| 方法 | 当前 sweep 维度 |
|---|---|
| GA | learning rate grid，由底层 sweep 脚本控制 |
| GD | learning rate grid，由底层 sweep 脚本控制 |
| NPO | `beta in {0.1,0.5}` |
| DrNPO | `beta in {0.1,0.5}`, forget-side `beta_dv_forget in {2,5}` |
| SimNPO | `beta in {3.5,4.5}`, `delta=1` |
| DrSimNPO | `beta in {3.5,4.5}`, `delta=1`, forget-side `sigma_forget in {2,5}` |

若论文主实验对 culture-origin sweep 使用了不同 learning-rate、batch 或 method 子集，必须在对应结果文件中另行记录；本文只记录当前已实现入口的默认/约定口径。

## 7. 训练时监控与正式评估

训练时监控只使用当前 origin 的 source-language monitor split，不替代正式 all-language eval。配置中监控指标目前为：

```text
a_rouge
```

监控口径：

```text
A_current_rouge(target,c).core/surface/weighted
A_current_rouge(neighbor,c).core/surface/weighted
```

入选 checkpoint 后，应运行 `eval/multilingual/culture_origin`，对同一 `culture_origin=c` 的 all-language core+surface split 进行正式评估，并与 finetuned-pre 的同范围输出按 `qa_id` 对齐。正式 profile 应至少记录：

```text
T_rouge(c -> t)
R_nbr_rouge(c,t)
D_nbr_rouge(c,t)
```

其中 `t` 覆盖 all-language eval 中的语言集合。`core/surface/weighted` 三个版本都应保留。

## 8. 解释边界

Culture-origin grouped protocol 的结果解释应围绕以下问题展开：

| 指标图案 | 解释 |
|---|---|
| `T_rouge(c -> c)` 高 | source/culture-origin 内 target 遗忘强。 |
| `R_nbr_rouge(c,c)` 高且 `D_nbr_rouge(c,c)` 低 | 同 culture-origin/source-language neighbor 保留较好。 |
| `T_rouge(c -> t), t != c` | 衡量同一 culture-origin 知识在其他语言表达中的遗忘传播；不应直接套用 common 的 globality 偏好。 |
| `D_nbr_rouge(c,t)` | 衡量对同一 culture-origin neighbor knowledge 在不同语言表达上的 collateral damage。 |

如果后续引入 affected-language 或 primary-language 人工标注，应在结果文档中单独区分：`culture_origin` 是当前工程 split 的分组字段，`affected_languages` 是更细的论文分析字段，二者不能混写。
