# Common Selected-checkpoint Results

本文档组记录当前 common forgetting 最终 selected-checkpoint 结果。当前结果是 method-level selected-checkpoint aggregation：每个 method 的每一行 source language 使用该 method 在该 source language 上最终保留的一个 checkpoint。

## Source artifacts

```text
open-unlearning-main/saves/exports/common_selected_checkpoint_matrices/manifest.json
open-unlearning-main/saves/exports/common_selected_checkpoint_matrices/common_selected_checkpoint_profile_metrics.csv
open-unlearning-main/saves/exports/common_selected_checkpoint_matrices/<method>/selected_checkpoints.csv
open-unlearning-main/saves/exports/common_selected_checkpoint_matrices/<method>/matrices/*.csv
```

`manifest.json` 记录的解释为：

```text
Each source-language row uses that source language and method's selected/kept checkpoint; this is method-level selected-checkpoint aggregation, not a strict same-hyperparameter full-transfer profile.
```

Validation summary：

| item | value |
|---|---:|
| `expected_cells` | 600 |
| `indexed_cells` | 600 |
| `missing_count` | 0 |
| `duplicate_count` | 0 |
| `checkpoint_mismatch_count` | 0 |
| `method_source_checkpoint_groups` | 60 |

## Metric Direction

本文档组中的箭头表示在当前 benchmark 目标下的阅读方向：

| metric family | direction | interpretation |
|---|---|---|
| `T_exact` / `T_rouge` | ↑ | target role 的相对遗忘强度；越高表示 target knowledge 相对 pre 下降越多。 |
| `R_nbr_exact` / `R_nbr_rouge` | ↑ | neighbor role 的相对保留率；越高表示 retain/neighbor knowledge 越接近或高于 pre。 |
| `D_nbr_exact` / `D_nbr_rouge` | ↓ | neighbor collateral damage；定义为 `1 - R_nbr`，越低表示 neighbor 误伤越小。 |
| `A_current_* target` | ↓ | unlearning checkpoint 对 target role 的当前访问度；越低通常表示 target forgetting 更强。 |
| `A_current_* neighbor` | ↑ | unlearning checkpoint 对 neighbor role 的当前访问度；越高通常表示 neighbor retention 更好。 |
| `*_valid_count` / `*_excluded_low_pre_count` | coverage | 不是效果指标；用于说明 pre-threshold filtering 后纳入或排除的知识对象数量。 |

`a_exact_mean` 与 `a_rouge_mean` 是整行 eval QA 的单模型总体访问度，混合 target 与 neighbor；它们用于诊断 checkpoint 的整体可访问性，不单独作为 forgetting-retention trade-off 的好坏排序依据。

## Result Analysis

当前 common selected-checkpoint 结果服务于外层 multilingual unlearning benchmark 的核心问题：模型能否在某个 source language 上遗忘 target knowledge，同时尽量保留 neighbor knowledge，并观察这种影响是否跨语言传播。基于 `common_selected_checkpoint_profile_metrics.csv` 的 method-level selected-checkpoint aggregation，当前结果呈现清晰 trade-off：`ga` 的 weighted ROUGE target transfer 较弱，但 neighbor retention 最高，说明它更像温和更新而非强遗忘；`npo`、`simnpo`、`drnpo`、`drsimnpo` 的 target transfer 明显更强，但伴随更高 neighbor damage；其中 `drnpo` 的 target forgetting 最强，同时 neighbor damage 也最大。`gd` 位于两者之间，既有明显遗忘，也存在较大 neighbor 保留损失。

矩阵结果应按 source-target 单元解释。对角线反映 source language 内的遗忘/保留，非对角线反映跨语言传播。由于当前结果是 selected-checkpoint method-level aggregation，每个 source-language row 使用该 source language 最终保留的 checkpoint，因此适合比较最终规则下的 language/method 行为，但不应解释为严格 same-hyperparameter full-transfer profile。

## Files

- [Selected checkpoints and provenance](selected-checkpoints.md)
- [Single-model exact and ROUGE table](single-model-exact-rouge.md)
- [Profile exact and ROUGE table](profile-exact-rouge.md)
- [Exact and ROUGE matrix appendix](matrices-exact-rouge.md)

表格数值统一显示 6 位小数；完整精度以 source artifacts 中 CSV 为准。本文档组不记录跨方法均值或额外统计显著性结论。
