# Finetuned 与 Retain Reference 评估结果

本文记录 finetuned-pre 与 retain reference 两个模型在 `common` 与 `culture_specific` relation-matched 数据上的 full multilingual evaluation 结果。本文只转写 workbook 中已有的逐语言结果，不额外计算跨语言聚合值或二次聚合表。

## 1. 结果来源

当前结果来自导出的汇总 workbook：

```text
open-unlearning-main/saves/exports/new_export/finetune_retain_common_culture_full_eval_summary.xlsx
```

workbook 包含 6 个 sheet：

```text
exact_all
exact_common
exact_culture
rouge_all
rouge_common
rouge_culture
```

本文转写 `exact_all` 与 `rouge_all`。这两个 sheet 按 `model_type + dataset_family + t language` 给出逐语言行，覆盖 `common` 与 `culture_specific`。表中的 `a_exact_mean` / `a_rouge_mean` 是 workbook 原列名，表示该行评估范围内的 per-QA metric 汇总列；本文不再计算或报告全语言聚合值。

Provenance 状态：

- workbook 记录了 finetuned 与 retain reference 的 formal eval dirs。
- 当前本地检查未发现这些 formal eval dirs 已完整存在于 `open-unlearning-main/saves/eval/` 下。
- 因此本文记录的是 workbook 中可用的汇总结果；若要复算新指标、抽查 raw generation 或做 failure analysis，需要补齐或重新生成对应 `generations.jsonl`、summary 与 `manifest.json`。
- 当前 workbook 不包含 `common_holdout` 或 `culture_holdout` 结果。

## 2. 模型与评估目录

| model_type | run_id | eval_dir |
|---|---|---|
| finetune | `multilingual_Llama-3.1-8B-Instruct_common_culture_core_b8g4` | `saves/eval/multilingual_Llama-3.1-8B-Instruct_common_culture_core_b8g4_common_culture_full_eval` |
| retain | `multilingual_Llama-3.1-8B-Instruct_common_culture_neighbor_core_b8g4_retain` | `saves/eval/multilingual_Llama-3.1-8B-Instruct_common_culture_neighbor_core_b8g4_retain_common_culture_full_eval` |

模型训练口径：

| model_type | 口径 |
|---|---|
| finetune | common + culture-specific, target + neighbor, core QA |
| retain | common + culture-specific, neighbor only, core QA |

## 3. 数据与指标

| dataset_family | 每语言样本数 | 语言数 | roles | variants |
|---|---:|---:|---|---|
| `common` | 4000 | 10 | target, neighbor | core, surface |
| `culture_specific` | 2400 | 10 | target, neighbor | core, surface |

列含义：

| 列 | 含义 |
|---|---|
| `model_type` | `finetune` 或 `retain` |
| `dataset_family` | `common` 或 `culture_specific` |
| `t_language` | 评估目标语言 |
| `count` | 当前行的 QA 数 |
| `a_exact_mean` / `a_rouge_mean` | 当前行全部 QA 的 per-QA metric 均值，来自 workbook 原列 |
| `target_core/surface/weighted` | target role 在 core、surface 与 core/surface weighted 口径下的 accessibility |
| `neighbor_core/surface/weighted` | neighbor role 在 core、surface 与 core/surface weighted 口径下的 accessibility |

方向说明：本文件记录的是 finetuned-pre 与 retain reference 的 full evaluation，不是 post-unlearning checkpoint 的 forgetting score，因此箭头必须按 `model_type` 与 role 解释。对 finetuned-pre，target 与 neighbor accessibility 越高越能说明 pre reference 覆盖对应知识；对 retain reference，期望方向是 target accessibility 低、neighbor accessibility 高。因此 target 列标记为 `finetune ↑ / retain ↓`，neighbor 列标记为 `↑`。`a_exact_mean` 与 `a_rouge_mean` 混合 target 与 neighbor，只作为 diagnostic，不作为单一好坏方向。

结果分析：finetuned-pre 在 common 与 culture-specific 的 target/neighbor 上整体保持较高 accessibility，说明它适合作为后续 pre/post profile 的 pre reference。retain reference 在 neighbor 列保持接近 finetuned-pre 的较高访问度，同时 target 列显著降低，符合“仅用 neighbor core 训练”的设计目的：它不是正式 unlearning 方法结果，而是用于校准 retain/neighbor 可保留性的参考模型。culture-specific 行整体仍呈现同样模式，因此当前 reference 设计可同时支撑 common 与 culture-specific 两条数据线的后续评估。

weighted 使用：

```text
core=0.5, surface=0.5
```

`s language` 在该 workbook 的 finetune/retain full eval 行中为空，因为这些不是 source-language unlearning checkpoint 结果。

## 4. `exact_all`

| model_type | dataset_family | t_language | count | a_exact_mean (diagnostic) | target_core (finetune ↑ / retain ↓) | target_surface (finetune ↑ / retain ↓) | target_weighted (finetune ↑ / retain ↓) | neighbor_core (↑) | neighbor_surface (↑) | neighbor_weighted (↑) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| finetune | common | ar | 4000 | 0.6535 | 0.874 | 0.574 | 0.724 | 0.886 | 0.582 | 0.734 |
| finetune | common | bn | 4000 | 0.60625 | 0.878 | 0.494 | 0.686 | 0.888 | 0.534 | 0.711 |
| finetune | common | de | 4000 | 0.74875 | 0.912 | 0.69 | 0.801 | 0.912 | 0.698667 | 0.805333 |
| finetune | common | en | 4000 | 0.78825 | 0.91 | 0.747333 | 0.828667 | 0.902 | 0.750667 | 0.826333 |
| finetune | common | es | 4000 | 0.737 | 0.904 | 0.670667 | 0.787333 | 0.902 | 0.692667 | 0.797333 |
| finetune | common | fr | 4000 | 0.75525 | 0.908 | 0.712667 | 0.810333 | 0.9 | 0.698667 | 0.799333 |
| finetune | common | ja | 4000 | 0.73725 | 0.902 | 0.694 | 0.798 | 0.89 | 0.674667 | 0.782333 |
| finetune | common | sw | 4000 | 0.6405 | 0.904 | 0.56 | 0.732 | 0.898 | 0.547333 | 0.722667 |
| finetune | common | th | 4000 | 0.6695 | 0.894 | 0.600667 | 0.747333 | 0.896 | 0.588 | 0.742 |
| finetune | common | zh | 4000 | 0.7145 | 0.908 | 0.650667 | 0.779333 | 0.906 | 0.65 | 0.778 |
| finetune | culture_specific | ar | 2400 | 0.7075 | 0.933333 | 0.647778 | 0.790556 | 0.933333 | 0.616667 | 0.775 |
| finetune | culture_specific | bn | 2400 | 0.680417 | 0.93 | 0.601111 | 0.765556 | 0.923333 | 0.595556 | 0.759444 |
| finetune | culture_specific | de | 2400 | 0.80125 | 0.96 | 0.751111 | 0.855556 | 0.943333 | 0.751111 | 0.847222 |
| finetune | culture_specific | en | 2400 | 0.829583 | 0.946667 | 0.812222 | 0.879444 | 0.926667 | 0.775556 | 0.851111 |
| finetune | culture_specific | es | 2400 | 0.798333 | 0.95 | 0.758889 | 0.854444 | 0.923333 | 0.745556 | 0.834444 |
| finetune | culture_specific | fr | 2400 | 0.8 | 0.953333 | 0.75 | 0.851667 | 0.93 | 0.755556 | 0.842778 |
| finetune | culture_specific | ja | 2400 | 0.770833 | 0.933333 | 0.721111 | 0.827222 | 0.923333 | 0.715556 | 0.819444 |
| finetune | culture_specific | sw | 2400 | 0.72125 | 0.943333 | 0.643333 | 0.793333 | 0.923333 | 0.657778 | 0.790556 |
| finetune | culture_specific | th | 2400 | 0.687083 | 0.95 | 0.617778 | 0.783889 | 0.92 | 0.591111 | 0.755556 |
| finetune | culture_specific | zh | 2400 | 0.741667 | 0.95 | 0.677778 | 0.813889 | 0.916667 | 0.677778 | 0.797222 |
| retain | common | ar | 4000 | 0.37 | 0.074 | 0.066667 | 0.070333 | 0.892 | 0.598 | 0.745 |
| retain | common | bn | 4000 | 0.35125 | 0.064 | 0.06 | 0.062 | 0.912 | 0.551333 | 0.731667 |
| retain | common | de | 4000 | 0.41975 | 0.086 | 0.078667 | 0.082333 | 0.916 | 0.706667 | 0.811333 |
| retain | common | en | 4000 | 0.4435 | 0.1 | 0.091333 | 0.095667 | 0.904 | 0.756667 | 0.830333 |
| retain | common | es | 4000 | 0.41725 | 0.084 | 0.082 | 0.083 | 0.898 | 0.703333 | 0.800667 |
| retain | common | fr | 4000 | 0.418 | 0.092 | 0.078 | 0.085 | 0.9 | 0.706 | 0.803 |
| retain | common | ja | 4000 | 0.39925 | 0.088 | 0.072667 | 0.080333 | 0.888 | 0.666667 | 0.777333 |
| retain | common | sw | 4000 | 0.35225 | 0.086 | 0.063333 | 0.074667 | 0.9 | 0.547333 | 0.723667 |
| retain | common | th | 4000 | 0.36525 | 0.07 | 0.059333 | 0.064667 | 0.886 | 0.596 | 0.741 |
| retain | common | zh | 4000 | 0.3925 | 0.086 | 0.073333 | 0.079667 | 0.892 | 0.647333 | 0.769667 |
| retain | culture_specific | ar | 2400 | 0.4025 | 0.093333 | 0.093333 | 0.093333 | 0.933333 | 0.637778 | 0.785556 |
| retain | culture_specific | bn | 2400 | 0.395833 | 0.11 | 0.112222 | 0.111111 | 0.923333 | 0.598889 | 0.761111 |
| retain | culture_specific | de | 2400 | 0.495833 | 0.183333 | 0.173333 | 0.178333 | 0.943333 | 0.773333 | 0.858333 |
| retain | culture_specific | en | 2400 | 0.517083 | 0.213333 | 0.207778 | 0.210556 | 0.923333 | 0.792222 | 0.857778 |
| retain | culture_specific | es | 2400 | 0.484167 | 0.183333 | 0.167778 | 0.175556 | 0.926667 | 0.753333 | 0.84 |
| retain | culture_specific | fr | 2400 | 0.476667 | 0.163333 | 0.161111 | 0.162222 | 0.93 | 0.745556 | 0.837778 |
| retain | culture_specific | ja | 2400 | 0.4575 | 0.143333 | 0.153333 | 0.148333 | 0.923333 | 0.711111 | 0.817222 |
| retain | culture_specific | sw | 2400 | 0.435833 | 0.146667 | 0.145556 | 0.146111 | 0.936667 | 0.655556 | 0.796111 |
| retain | culture_specific | th | 2400 | 0.387917 | 0.106667 | 0.093333 | 0.1 | 0.933333 | 0.594444 | 0.763889 |
| retain | culture_specific | zh | 2400 | 0.430833 | 0.136667 | 0.122222 | 0.129444 | 0.913333 | 0.676667 | 0.795 |

## 5. `rouge_all`

| model_type | dataset_family | t_language | count | a_rouge_mean (diagnostic) | target_core (finetune ↑ / retain ↓) | target_surface (finetune ↑ / retain ↓) | target_weighted (finetune ↑ / retain ↓) | neighbor_core (↑) | neighbor_surface (↑) | neighbor_weighted (↑) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| finetune | common | ar | 4000 | 0.706237 | 0.888229 | 0.645045 | 0.766637 | 0.892859 | 0.644557 | 0.768708 |
| finetune | common | bn | 4000 | 0.66058 | 0.898143 | 0.572703 | 0.735423 | 0.889 | 0.593129 | 0.741064 |
| finetune | common | de | 4000 | 0.794876 | 0.916114 | 0.755063 | 0.835589 | 0.9158 | 0.753968 | 0.834884 |
| finetune | common | en | 4000 | 0.823741 | 0.914114 | 0.798451 | 0.856283 | 0.9028 | 0.792552 | 0.847676 |
| finetune | common | es | 4000 | 0.793583 | 0.910781 | 0.747394 | 0.829087 | 0.9048 | 0.763634 | 0.834217 |
| finetune | common | fr | 4000 | 0.807929 | 0.911848 | 0.777728 | 0.844788 | 0.905133 | 0.771089 | 0.838111 |
| finetune | common | ja | 4000 | 0.819504 | 0.92648 | 0.799442 | 0.862961 | 0.91243 | 0.772933 | 0.842681 |
| finetune | common | sw | 4000 | 0.699486 | 0.916695 | 0.636216 | 0.776456 | 0.908214 | 0.620776 | 0.764495 |
| finetune | common | th | 4000 | 0.785094 | 0.925495 | 0.750073 | 0.837784 | 0.924803 | 0.726746 | 0.825775 |
| finetune | common | zh | 4000 | 0.790862 | 0.921535 | 0.752402 | 0.836969 | 0.916672 | 0.743828 | 0.83025 |
| finetune | culture_specific | ar | 2400 | 0.74769 | 0.941667 | 0.693953 | 0.81781 | 0.940222 | 0.67259 | 0.806406 |
| finetune | culture_specific | bn | 2400 | 0.72684 | 0.940889 | 0.660412 | 0.80065 | 0.935111 | 0.652494 | 0.793803 |
| finetune | culture_specific | de | 2400 | 0.826466 | 0.96 | 0.786309 | 0.873154 | 0.944444 | 0.782785 | 0.863615 |
| finetune | culture_specific | en | 2400 | 0.857033 | 0.948333 | 0.846921 | 0.897627 | 0.936778 | 0.81013 | 0.873454 |
| finetune | culture_specific | es | 2400 | 0.834403 | 0.951667 | 0.80251 | 0.877088 | 0.936601 | 0.793143 | 0.864872 |
| finetune | culture_specific | fr | 2400 | 0.834224 | 0.954667 | 0.794842 | 0.874754 | 0.937508 | 0.79903 | 0.868269 |
| finetune | culture_specific | ja | 2400 | 0.843485 | 0.945861 | 0.806379 | 0.87612 | 0.951536 | 0.81045 | 0.880993 |
| finetune | culture_specific | sw | 2400 | 0.762673 | 0.949167 | 0.694666 | 0.821916 | 0.935127 | 0.71103 | 0.823078 |
| finetune | culture_specific | th | 2400 | 0.818955 | 0.966271 | 0.784161 | 0.875216 | 0.950181 | 0.760901 | 0.855541 |
| finetune | culture_specific | zh | 2400 | 0.805468 | 0.955349 | 0.756645 | 0.855997 | 0.934715 | 0.761248 | 0.847982 |
| retain | common | ar | 4000 | 0.439697 | 0.172161 | 0.163272 | 0.167717 | 0.896143 | 0.65315 | 0.774647 |
| retain | common | bn | 4000 | 0.414699 | 0.149595 | 0.139488 | 0.144541 | 0.915 | 0.611511 | 0.763256 |
| retain | common | de | 4000 | 0.4875 | 0.182379 | 0.172739 | 0.177559 | 0.9168 | 0.760867 | 0.838834 |
| retain | common | en | 4000 | 0.512174 | 0.205363 | 0.197773 | 0.201568 | 0.906838 | 0.797291 | 0.852065 |
| retain | common | es | 4000 | 0.509461 | 0.213334 | 0.211822 | 0.212578 | 0.903943 | 0.774315 | 0.839129 |
| retain | common | fr | 4000 | 0.507697 | 0.205269 | 0.20422 | 0.204745 | 0.904255 | 0.779797 | 0.842026 |
| retain | common | ja | 4000 | 0.536651 | 0.285732 | 0.262681 | 0.274206 | 0.911266 | 0.769389 | 0.840328 |
| retain | common | sw | 4000 | 0.433428 | 0.189039 | 0.16474 | 0.176889 | 0.911878 | 0.624097 | 0.767987 |
| retain | common | th | 4000 | 0.539181 | 0.312135 | 0.299673 | 0.305904 | 0.91339 | 0.729634 | 0.821512 |
| retain | common | zh | 4000 | 0.512955 | 0.255349 | 0.238906 | 0.247127 | 0.90291 | 0.742888 | 0.822899 |
| retain | culture_specific | ar | 2400 | 0.446121 | 0.138638 | 0.13956 | 0.139099 | 0.935 | 0.692217 | 0.813609 |
| retain | culture_specific | bn | 2400 | 0.440682 | 0.153452 | 0.15216 | 0.152806 | 0.929444 | 0.662026 | 0.795735 |
| retain | culture_specific | de | 2400 | 0.532246 | 0.237127 | 0.225209 | 0.231168 | 0.945556 | 0.799886 | 0.872721 |
| retain | culture_specific | en | 2400 | 0.56159 | 0.283979 | 0.26857 | 0.276274 | 0.929333 | 0.824566 | 0.87695 |
| retain | culture_specific | es | 2400 | 0.543019 | 0.275566 | 0.247817 | 0.261692 | 0.933238 | 0.797298 | 0.865268 |
| retain | culture_specific | fr | 2400 | 0.532845 | 0.234824 | 0.236965 | 0.235894 | 0.93473 | 0.794103 | 0.864416 |
| retain | culture_specific | ja | 2400 | 0.577333 | 0.313572 | 0.314261 | 0.313917 | 0.945474 | 0.805612 | 0.875543 |
| retain | culture_specific | sw | 2400 | 0.488853 | 0.209766 | 0.211478 | 0.210622 | 0.939683 | 0.708981 | 0.824332 |
| retain | culture_specific | th | 2400 | 0.580095 | 0.371087 | 0.344644 | 0.357865 | 0.960725 | 0.758339 | 0.859532 |
| retain | culture_specific | zh | 2400 | 0.524173 | 0.245675 | 0.243301 | 0.244488 | 0.935295 | 0.760838 | 0.848066 |

## 6. 结果边界

本结果文档不覆盖：

- `common_holdout` 的 holdout/MIA 评估结果。
- `culture_holdout` 的 holdout/MIA 评估结果。
- unlearning checkpoint 的 post eval、source-row profile 或 full-transfer profile。

这些结果应在执行后另建结果文档或追加到对应结果记录中。若需要论文级统计结论，应从本页逐语言表或原 workbook 出发，在论文分析脚本中显式计算并记录计算方法。
