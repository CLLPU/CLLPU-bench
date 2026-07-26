# Step Houldout: Holdout QA 数据构建

本文档总结 holdout 数据的构建过程。这里保留用户侧命名 `step houldout`，实际含义是 `holdout QA construction`。

Step Houldout 是一条独立于主 Target / Neighbor pair 训练评测集的旁路流程。它复用 Step 5 和 Step 6 的生成与转译规则，但不修改 Step 5 / Step 6 原脚本，也不覆盖主数据产物。

---

## 1. 目标

Step Houldout 的目标是：

- 从没有进入主 QA 集的剩余 knowledge cards 中随机抽取 500 个单卡知识单元
- 为每个 knowledge card 生成 1 条英语 canonical core QA
- 按 Step 6 的转译和 back-translation 规则，把这 500 条英语 QA 扩展到所有目标语言
- 形成一套与主 training / eval QA 风格一致、但样本来源不重叠的 holdout QA

这条流程不要求：

- target / neighbor 成对
- relation-matched pair
- neighbor topic
- topic pair 内数量均衡

抽样单位是单个 `knowledge_card`，不是 `knowledge_card_pair`。

---

## 2. 与主数据集的边界

主数据集的正式 high-quality selection 是 500 个 knowledge card pairs：

```text
data/selected_knowledge_card_pairs.json
```

每个 pair 含：

```text
target card + neighbor card
```

因此主数据实际占用了 1000 个 knowledge cards。Step Houldout 的候选池必须排除这 1000 个 `card_id`，而不是只排除 500 个 `knowledge_pair_id`。

边界规则：

- 主数据的 Step 5 输出仍是 `data/qa_variants.en.json`
- 主数据的 Step 6 输出仍是 `data/qa_variants.<language>.json`
- holdout 输出统一使用 `data/holdout_*`
- holdout 生成脚本只 import / reuse Step 5 和 Step 6 的逻辑，不回写 Step 5 / Step 6 脚本

---

## 3. 输入数据

Step Houldout 使用两个上游输入：

| 目的 | 文件 |
|---|---|
| 全量 knowledge cards | [../../data/knowledge_cards.json](../../data/knowledge_cards.json) |
| 主 QA 已占用 cards | [../../data/selected_knowledge_card_pairs.json](../../data/selected_knowledge_card_pairs.json) |

从 `data/knowledge_cards.json` 读取：

```text
topic_pairs[].target.knowledge_cards[]
topic_pairs[].neighbor.knowledge_cards[]
```

从 `data/selected_knowledge_card_pairs.json` 读取并排除：

```text
topic_pairs[].knowledge_card_pairs[].target.card.card_id
topic_pairs[].knowledge_card_pairs[].neighbor.card.card_id
```

当前实际规模：

| 层级 | 数量 |
|---|---:|
| 全量 knowledge cards | 2888 |
| 主 QA 已占用 cards | 1000 |
| holdout 候选池 | 1888 |
| holdout 抽样 cards | 500 |

---

## 4. 抽样规则

抽样配置：

| 字段 | 值 |
|---|---|
| `sample_size` | 500 |
| `random_seed` | 20260627 |
| `sampling_unit` | `knowledge_card` |
| `sampling_strategy` | `global_uniform_without_replacement` |
| `exclude_selected_main_qa_cards` | true |

抽样过程：

1. 读取全量 target / neighbor knowledge cards，并保留 topic provenance。
2. 读取主 QA 已占用的 target / neighbor card IDs。
3. 从全量 cards 中移除已占用 card IDs。
4. 按 `card_id` 去重。
5. 使用固定随机种子全局均匀随机抽样 500 个 cards。
6. 为抽中的 cards 分配稳定 `holdout_card_id`，格式为 `holdout__000001`。

抽样输出：

```text
data/holdout_knowledge_cards.sampled.json
```

---

## 5. 英语 Holdout QA 生成

英语 QA 生成脚本：

```text
code/step_holdout_generate_qa.py
```

该脚本复用 Step 5 的关键逻辑：

- `SYSTEM_PROMPT`
- runtime settings 解析
- LLM API 调用与 key rotation
- JSON response parsing
- `answer_aliases` 安全过滤
- answer leakage checker
- atomic write

但它不修改：

```text
code/step5_generate_qa_variants.py
```

执行入口：

```bash
python3 code/step_holdout_generate_qa.py
```

默认输出：

```text
data/holdout_qa.en.json
data/holdout_qa_cache/
```

当前配置：

| 配置 | 值 |
|---|---:|
| 每个 card core QA | 1 |
| 每个 card surface QA | 0 |
| holdout cards | 500 |
| English QA variants | 500 |

英语 QA 曾出现 10 条 `answer_leakage_in_question` warning，已人工改写 question 并用 Step 5 的 leakage checker 复核。当前英文 warning 为 0。

---

## 6. 多语言扩展

多语言扩展脚本：

```text
code/step_holdout_expand_qa_translations.py
```

该脚本复用 Step 6 的规则：

- direct translation
- minimal localization
- back-translation
- consistency check
- automatic retry
- failed backtranslation queue
- target-language alias safety filtering

但它不修改：

```text
code/step6_expand_qa_translations.py
```

执行入口：

```bash
python3 code/step_holdout_expand_qa_translations.py --workers 12
```

也可以只恢复部分语言：

```bash
python3 code/step_holdout_expand_qa_translations.py \
  --languages ar,bn,sw \
  --workers 12
```

默认目标语言：

```text
zh, fr, es, de, ja, th, ar, bn, sw
```

默认输出：

```text
data/holdout_qa.<language>.json
data/holdout_qa.<language>.failed_backtranslation.json
data/holdout_qa_translation_cache/<language>/
```

---

## 7. 输出文件

### 7.1 主要数据文件

| 文件 | 作用 |
|---|---|
| [../../data/holdout_knowledge_cards.sampled.json](../../data/holdout_knowledge_cards.sampled.json) | 500 个 holdout knowledge cards 的固定抽样结果 |
| [../../data/holdout_qa.en.json](../../data/holdout_qa.en.json) | 500 条英语 canonical holdout QA |
| `data/holdout_qa.<language>.json` | 每个目标语言的 500 条 translated holdout QA |
| `data/holdout_qa.<language>.failed_backtranslation.json` | 每个目标语言的 failed backtranslation 队列 |
| [../../data/holdout_qa_warnings.tsv](../../data/holdout_qa_warnings.tsv) | 当前 warning 明细 |

### 7.2 缓存文件

| 路径 | 作用 |
|---|---|
| `data/holdout_qa_cache/` | 英语 holdout QA 生成缓存 |
| `data/holdout_qa_translation_cache/` | 多语言转译、回译和 normalized 输出缓存 |

缓存文件已随数据一起保留，便于复现、恢复和审计。

---

## 8. 当前结果快照

最终输出统计：

| Language | Cards | QA variants | Failed backtranslation | Warnings |
|---|---:|---:|---:|---:|
| `en` | 500 | 500 | 0 | 0 |
| `zh` | 500 | 500 | 0 | 82 |
| `fr` | 500 | 500 | 0 | 26 |
| `es` | 500 | 500 | 0 | 24 |
| `de` | 500 | 500 | 0 | 33 |
| `ja` | 500 | 500 | 0 | 93 |
| `th` | 500 | 500 | 0 | 97 |
| `ar` | 500 | 500 | 0 | 113 |
| `bn` | 500 | 500 | 0 | 204 |
| `sw` | 500 | 500 | 0 | 16 |

校验结果：

- 每个语言都有 500 个 holdout cards
- 每个语言都有 500 条 QA variants
- 每个语言都有 500 个唯一 `source_card_id`
- 每个语言都有 500 个唯一 `qa_id`
- 所有目标语言 `failed_backtranslation_count = 0`
- 英语 `answer_leakage_in_question = 0`

当前剩余 warning 主要是 alias 质量提示：

| Warning type | 数量 | 说明 |
|---|---:|---|
| `unsafe_answer_alias_non_equivalent` | 687 | 目标语言中某个 generated / translated alias 被判定与标准答案不等价，因此被跳过 |
| `source_qa_no_answer_aliases` | 1 | 英文源 QA 没有 answer aliases，因此丢弃目标语言生成的 aliases |

这些 warning 不等同于生成失败，也不影响 `failed_backtranslation_count`。

---

## 9. 质量修复记录

英语初版中有 10 条 question 包含答案词或答案 alias。修复方式：

1. 手动重写这 10 条 English core question。
2. 保持 `expected_answer`、`source_card_id`、`relation_type` 不变。
3. 使用 Step 5 原始 `answer_leakage_warnings` 函数重新检查。
4. 清理这 10 条对应的 target-language translation cache。
5. 复用 Step 6 规则重译 9 个目标语言。
6. 重新生成 `data/holdout_qa_warnings.tsv`。

修复后的 10 条英文 question 全部通过 leakage checker。

---

## 10. 复跑边界

如果只想重新抽样：

```bash
python3 code/step_holdout_generate_qa.py --refresh-sample
```

注意：重新抽样会改变 holdout 集合，不应在已发布数据后随意执行。

如果只想重新生成英文 QA：

```bash
python3 code/step_holdout_generate_qa.py --refresh-cache
```

如果只想重新翻译某些语言：

```bash
python3 code/step_holdout_expand_qa_translations.py \
  --languages zh,fr \
  --workers 12
```

如果只想重译少量 card，应先移除对应语言缓存中的：

```text
data/holdout_qa_translation_cache/<language>/holdout_000XXX__<language>.attempts.json
data/holdout_qa_translation_cache/<language>/holdout_000XXX__<language>.normalized.json
```

然后重新运行对应语言。未清理缓存的 cards 会直接复用已有 normalized output。

---

## 11. 与主 Workflow 的关系

Step Houldout 是主 workflow 的旁路，而不是 Step 7 之后的线性步骤。

推荐理解为：

```text
Step 3 knowledge cards
  -> Step 4 / Step 4.5 / Step 5 / Step 6: main paired QA
  -> Step Houldout: remaining-card holdout QA
```

它依赖 Step 3 的全量 cards，也依赖 Step 4.5 的 selected pairs 来排除主数据已使用 cards。它复用 Step 5 / Step 6 的代码规则来保持 QA 风格一致，但输出命名空间独立。

---

## 12. Culture-specific Holdout

culture-specific 数据线使用同一套 holdout 规则，但使用 `.culture_specific` 后缀，避免覆盖 common-goals 产物。

### 12.1 当前产物

| 文件 | 作用 | 当前规模 / 结果 |
|---|---|---|
| [../../data/holdout_knowledge_cards.culture_specific.sampled.json](../../data/holdout_knowledge_cards.culture_specific.sampled.json) | culture-specific holdout card 抽样 | 300 sampled cards |
| [../../data/holdout_qa.en.culture_specific.json](../../data/holdout_qa.en.culture_specific.json) | culture-specific English canonical holdout QA | 300 core QA；warning_count=0 |
| `data/holdout_qa.<language>.culture_specific.json` | culture-specific target-language holdout QA | 9 个非英语语言各 300 条；failed_backtranslation_count=0 |

当前抽样口径：

| 层级 | 数量 |
|---|---:|
| 全量 culture-specific knowledge cards | 1761 |
| Step 4.5 selected pairs 已占用 cards | 600 |
| holdout 候选池 | 1161 |
| holdout 抽样 cards | 300 |

抽样使用 `random_seed = 20260627`，`holdout_card_id` 使用 `culture_holdout__000001` 形式，避免与 common-goals holdout ID 碰撞。

已验证：

- 300 个 sampled `source_card_id` 唯一
- sampled cards 与 `data/selected_knowledge_card_pairs.culture_specific.json` 中已占用的 600 个 `card_id` 无交集
- English canonical QA 为 300 条 core QA
- 空 question / answer 数为 0
- English warning_count 为 0
- 9 个非英语语言 `ar,bn,de,es,fr,ja,sw,th,zh` 均为 300 条 accepted QA
- 9 个非英语语言 `failed_backtranslation_count = 0`

### 12.2 多语言扩展结果

| Language | QA variants | Failed backtranslations | Warnings |
|---|---:|---:|---:|
| `ar` | 300 | 0 | 96 |
| `bn` | 300 | 0 | 116 |
| `de` | 300 | 0 | 31 |
| `es` | 300 | 0 | 25 |
| `fr` | 300 | 0 | 19 |
| `ja` | 300 | 0 | 79 |
| `sw` | 300 | 0 | 18 |
| `th` | 300 | 0 | 93 |
| `zh` | 300 | 0 | 50 |

`bn` 初次扩展时 `culture_holdout__000141` 因 source English aliases 与 Bengali transliterated aliases 的等价判定冲突，产生 1 条 failed backtranslation。修复方式是在 Step 6 alias equivalence 中加入 Unicode-aware fallback，使 Bengali / Arabic / Thai 等非 Latin / CJK 脚本的别名子串关系可被识别；随后仅清理该 card 的 `bn` cache 并重跑 `bn`，最终 `bn` 也达到 300 条 accepted QA、0 failed backtranslations。

### 12.3 复跑命令

抽样并生成英语 canonical holdout QA：

```bash
python3 code/step_holdout_generate_qa.py \
  --cards-input data/knowledge_cards.culture_specific.json \
  --selected-input data/selected_knowledge_card_pairs.culture_specific.json \
  --sample-output data/holdout_knowledge_cards.culture_specific.sampled.json \
  --output data/holdout_qa.en.culture_specific.json \
  --cache-dir data/holdout_qa_cache.culture_specific \
  --sample-size 300 \
  --holdout-id-prefix culture_holdout \
  --surface-count 0 \
  --batch-size 10
```

API 可用后，可继续做 9 个非英语语言扩展：

```bash
python3 code/step_holdout_expand_qa_translations.py \
  --input data/holdout_qa.en.culture_specific.json \
  --output-template 'data/holdout_qa.{language}.culture_specific.json' \
  --failed-output-template 'data/holdout_qa.{language}.culture_specific.failed_backtranslation.json' \
  --cache-dir data/holdout_qa_translation_cache.culture_specific \
  --workers 12
```
