# Holdout 评估状态

本文记录 `common_holdout` 与 `culture_holdout` 的当前数据状态和评估结果缺口。

依据来源：

```text
open-unlearning-main/data/multilingual/manifest.json
open-unlearning-main/data/multilingual/README.md
open-unlearning-main/docs/multilingual.md
open-unlearning-main/saves/exports/new_export/finetune_retain_common_culture_full_eval_summary.xlsx
```

## 1. 当前数据

| 数据族 | 来源 | 每语言样本数 | 总样本数 | all-language split |
|---|---|---:|---:|---|
| `common_holdout` | `../data/holdout_qa.<language>.json` | 500 | 5000 | `data/multilingual/train_splits/eval_common_holdout_all.jsonl` |
| `culture_holdout` | `../data/holdout_qa.<language>.culture_specific.json` | 300 | 3000 | `data/multilingual/train_splits/eval_culture_holdout_all.jsonl` |

两类 holdout 都是 singleton held-out cards，不是 target/neighbor relation-matched knowledge pairs。`knowledge_pair_id` 有意为空，因此不适合进入当前 common transfer/profile 的 per-knowledge 聚合。

## 2. 使用边界

`common_holdout` 和 `culture_holdout` 不进入：

- finetuned-pre SFT
- retain reference SFT
- common forgetting 的 forget split
- common forgetting 的 retain split
- 当前 common forgetting 默认 full eval

它们只用于 holdout / MIA / membership-inference 类评估，或后续明确设计的 holdout QA accessibility 检查。

## 3. 当前结果状态

截至当前记录，已有结果 workbook：

```text
open-unlearning-main/saves/exports/new_export/finetune_retain_common_culture_full_eval_summary.xlsx
```

只覆盖 finetuned-pre 与 retain reference 在 `common` 和 `culture_specific` relation-matched 数据上的 exact/ROUGE 汇总，不包含：

- `common_holdout`
- `culture_holdout`

因此当前不能报告 finetuned-pre、retain reference 或 unlearning checkpoint 在 holdout 数据上的正式指标。

论文写作时，若需要讨论 holdout，只能基于本节数据状态说明“已构造评估 split、尚未记录模型结果”。不能把 relation-matched `common` / `culture_specific` 结果外推为 holdout 结果。

## 4. 后续记录要求

执行 holdout 评估后，应至少记录：

| 项 | 要求 |
|---|---|
| model | run id、checkpoint path、base type |
| data | `eval_common_holdout_all.jsonl` 或 `eval_culture_holdout_all.jsonl` |
| metric | QA accessibility、MIA 指标或二者 |
| output | `generations.jsonl`、summary/report、manifest 的保存目录 |
| aggregation | QA-level、card-level 或 MIA-specific 聚合方式 |
| exclusion | 明确说明 holdout 未参与 SFT/unlearning 训练 |

若使用 QA accessibility 指标，应避免把 holdout 结果解释为 target/neighbor transfer/profile，因为 holdout 数据没有 relation-matched `knowledge_pair_id` 结构。
