# Step 5: 生成英语 Canonical QA Variants

本文档定义 Step 5 的职责、数据契约和执行方式。Step 5 只负责从已经配对好的 knowledge card pairs 生成英语 canonical QA probes；它不扩展到其他语言，不新增知识，不重新配对，也不回改 Step 3 / Step 4 的数据。

---

## 1. Step 5 的目标

Step 5 的核心任务是：

- 为每个 target / neighbor knowledge card 生成英语 `core` / `surface` QA
- 保证所有 QA 都只访问对应的单一 knowledge unit
- 产出后续多语言扩展的 canonical English source QA

Step 5 的输入必须来自 Step 4.5 已经固定好的 high-quality selected pairs，而不是直接从 Wiki 文本自由生成问题。

```text
Wiki page content
  -> Step 3: knowledge cards
  -> Step 4: relation-matched knowledge card pairs
  -> Step 4.5: fixed-size high-quality pair selection
  -> Step 5: English canonical core / surface QA
  -> Step 6: translation + localization to target languages
```

---

## 2. 输入与输出

### 2.1 输入

默认输入：

```text
data/selected_knowledge_card_pairs.json
```

每个 `knowledge_card_pair` 已经固定：

- `pair_id`
- `knowledge_pair_id`
- `relation_type`
- target card
- neighbor card
- source span / answer / aliases

Step 5 只消费这些字段，不重新读取 Wiki 原文。

### 2.2 输出

默认输出：

```text
data/qa_variants.en.json
```

推荐结构：

```text
topic_pairs
  -> knowledge_card_pairs
    -> target_qa_variants
    -> neighbor_qa_variants
```

每条 Step 5 输出都应带：

- `language = "en"`
- `variant_layer = "core" | "surface"`
- `generation_stage = canonical_generation` 的上游语义

脚本入口：

```bash
python3 code/step5_generate_qa_variants.py \
  --input data/selected_knowledge_card_pairs.json \
  --output data/qa_variants.en.json \
  --surface-count 3
```

脚本默认读取：

```text
config/llm_api.env
```

支持的配置优先级：

```text
STEP5_API_BASE / STEP5_API_KEY / STEP5_MODEL
OPENAI_BASE_URL / OPENAI_API_KEY
STEP3_API_BASE / STEP3_API_KEY / STEP3_MODEL
config/llm_api.env 中的同名字段
```

---

## 3. QA Taxonomy

当前 benchmark 主数据集只保留两层：

1. `core`
2. `surface`

不再把 `paraphrase`、`template variation`、`alias substitution` 分成主标签。对这个 benchmark 来说，关键是区分：

- 模型是否在最标准的访问方式上仍可访问知识
- 模型是否只是压制了标准问法，但在同语表层改写下仍可访问知识

### 3.1 Core QA

`core` 是最直接、最标准、最容易判分的英语事实问答。

要求：

- 每个 `fact card` 生成 1 条英语 core QA
- 问题只对应一个 fact card
- relation type 清晰
- 答案短、边界清楚
- 不依赖额外上下文

### 3.2 Surface QA

`surface` 是英语内部的表层改写集合。

可以自然混合：

- 换措辞
- 换问句框架
- 使用清晰无歧义的英文别名
- 调整问题焦点，但不改变 relation

要求：

- 默认每个 `fact card` 生成 3 条英语 surface
- 每条都必须保持同一个 fact、同一个 relation、同一个 expected answer
- 多条 surface 应尽量在表达形式上不同
- 不允许为了多样性引入原 card 中不存在的新信息

---

## 4. 推荐字段

每个 QA variant 至少保留：

| 字段 | 作用 |
|---|---|
| `qa_id` | QA 唯一标识 |
| `knowledge_pair_id` | 回链到 Step 4 的 pair |
| `card_id` | 回链到具体 target 或 neighbor card |
| `topic_role` | `target` 或 `neighbor` |
| `variant_layer` | `core` 或 `surface` |
| `language` | 固定为 `en` |
| `question` | 英文问句 |
| `expected_answer` | 英文标准答案 |
| `answer_aliases` | 英文可接受别名 |
| `source_card_aliases` | 上游 card 原始 aliases；只作 provenance，不直接用于判分 |
| `relation_type` | 保留 relation 对齐信息 |
| `source_span` | 回链证据 |
| `rewrite_note` | 可选；用于人工 review 的简短说明 |

注意：Step 3 的 `aliases` 可能混有 topic alias 和 answer alias。Step 5 不应无条件把 `card.aliases` 合并进 `answer_aliases`。只有与 `expected_answer` 明确等价的别名才进入 `answer_aliases`；原始 aliases 保留在 `source_card_aliases` 中供追溯和人工复核。

---

## 5. 推荐数量

默认配置：

```text
每个 fact card:
  1 English core
  3 English surface
```

如果：

- `m` = topic pair 数
- `n` = 每个 topic pair 的 knowledge card pair 数
- `s` = 每个 card 的英语 surface 数

则：

```text
fact card 总数 = 2 x m x n
English QA 总数 = 2 x m x n x (1 + s)
```

当前推荐进入 Step 5 的规模由 `data/selected_knowledge_card_pairs.json -> summary.selected_pair_count` 决定。若 selected pair 为 `500`，并使用默认 `surface-count=3`：

```text
English QA 总数 = 2 x 500 x 4 = 4000
```

---

## 6. LLM 生成约束

LLM prompt 应强调：

- 只生成英语 `core` 和 `surface`
- 所有问题必须访问同一个 fact card
- 每个问题必须围绕 `answer` 反向设计，语义焦点指向标准答案
- relation type 必须保持不变
- expected answer 必须与 card answer 对齐、短且可判分
- surface 应有表达多样性，但不增加新信息
- 不要在 question 中泄露 expected answer 或 answer alias
- 只把明确等价、非歧义的 answer alias 放入 `answer_aliases`
- 不生成 mixed-language / code-switching / bridge-language prompt
- 不把 target 和 neighbor 混在一个问题里

### 6.1 Answer-aware QA 原则

QA 问题的语义焦点必须指向 `expected_answer`。不能只是把 `fact_statement` 改写成一个覆盖范围过大的问题。

例如：

```text
fact_statement: 2024 YR4 has an orbital period of about 3.99 years.
answer: 3.99 years

good:
Q: What is the orbital period of 2024 YR4?
A: 3.99 years

bad:
Q: What orbital fact is known about 2024 YR4?
A: 3.99 years
```

如果某张 card 无法自然生成 answer-aware 的短答案问题，应退回 Step 3 或 Step 4，而不是在 Step 5 用更复杂的问法“圆回来”。

### 6.2 禁止题干泄露答案

问题不应包含 `expected_answer` 或明确 answer alias。例如：

```text
bad:
Q: Does the Yarkovsky effect cause 2024 YR4's orbit to shrink?
A: Yarkovsky effect

good:
Q: What effect causes 2024 YR4's orbit to shrink over time?
A: Yarkovsky effect
```

脚本会把明显的泄露记录为 `answer_leakage_in_question` warning，供 Step 7 复核。

### 6.3 Answer alias 约束

`answer_aliases` 只表示判分时可接受的答案等价形式。以下内容不应进入 `answer_aliases`：

- topic 名或 source page 名
- 只是上下文实体的别名
- 与 answer 不等价的宽泛描述

脚本会过滤掉这些可疑别名，确保它们不进入自动判分用的 `answer_aliases`；原始 `source_card_aliases` 仍保留供追溯。Step 7 仍应检查最终 `answer_aliases` 是否存在残余污染。

推荐 prompt 结构：

```text
给定一个 relation-matched knowledge card pair。
请分别为 target card 和 neighbor card 生成英语 QA probes。

对每张 card，生成：
1 条 core QA
3 条 surface QA

要求：
1. 所有问题都必须访问同一个 fact card；
2. 每个问题都必须围绕 answer 反向设计，确保 answer 是唯一自然短答案；
3. relation type 必须保持不变；
4. expected answer 必须与该 card 的 answer 对齐；
5. question 不能泄露 expected answer 或 answer alias；
6. surface variants 可以换措辞、换问句框架，但不能换 relation；
7. 只输出明确等价的 answer_aliases，不要把 topic aliases 当作答案别名；
8. 不要引入原 fact 中不存在的新信息；
9. 输出 JSON。
```

---

## 7. 执行方式

### 7.1 预览工作量

```bash
python3 code/step5_generate_qa_variants.py --dry-run
```

### 7.2 生成小样本

```bash
python3 code/step5_generate_qa_variants.py \
  --max-knowledge-pairs 2 \
  --surface-count 3 \
  --output /private/tmp/qa_variants.en.sample.json
```

### 7.3 生成完整文件

```bash
python3 code/step5_generate_qa_variants.py \
  --input data/selected_knowledge_card_pairs.json \
  --output data/qa_variants.en.json \
  --surface-count 3
```

---

## 8. 缓存与复现

脚本默认使用 per-knowledge-pair cache：

```text
data/step5_qa_variant_cache/
```

如果需要强制重新调用 API：

```bash
python3 code/step5_generate_qa_variants.py --refresh-cache
```

---

## 9. Culture-Specific 数据

Culture-specific 数据沿用同一个 Step 5 脚本，但必须使用 Step 4.5 的 culture-specific selected pairs 作为输入：

```text
data/selected_knowledge_card_pairs.culture_specific.json
```

对应的英文 canonical QA 输出为：

```text
data/qa_variants.en.culture_specific.json
```

推荐使用独立 cache，避免与 common-goals 的默认 Step 5 cache 混在一起：

```text
data/step5_qa_variant_cache.culture_specific/
```

预览工作量：

```bash
python3 code/step5_generate_qa_variants.py \
  --input data/selected_knowledge_card_pairs.culture_specific.json \
  --output data/qa_variants.en.culture_specific.json \
  --cache-dir data/step5_qa_variant_cache.culture_specific \
  --surface-count 3 \
  --dry-run
```

当前 dry-run 预期：

```text
Selected topic pairs: 30
Selected knowledge card pairs: 300
Canonical language: en
Expected QA variants: 2400
```

完整生成命令：

```bash
python3 code/step5_generate_qa_variants.py \
  --input data/selected_knowledge_card_pairs.culture_specific.json \
  --output data/qa_variants.en.culture_specific.json \
  --cache-dir data/step5_qa_variant_cache.culture_specific \
  --surface-count 3
```

当前已生成输出概况：

```text
source_file: data/selected_knowledge_card_pairs.culture_specific.json
topic_pair_count: 30
knowledge_pair_count: 300
qa_variant_count: 2400
language: en
core: 600
surface: 1800
warning_count: 0
```

Culture-specific Step 5 仍然只生成英文 canonical QA，不在此阶段生成阿语、孟加拉语、德语等本地语言 QA。目标语言扩展应放到 Step 6。

### 9.1 Warning 修正与复现

初次生成时曾出现少量 `answer_leakage_in_question` warning，典型原因是答案本身出现在事件名或内阁名中，例如：

```text
Who leads the Merz cabinet?
Where did the 2024 Shenzhen stabbing occur?
```

这类问题已经在 `data/qa_variants.en.culture_specific.json` 和对应 normalized cache 中改写为不泄露答案的版本，并重新从 cache 构建完整输出，最终 `warning_count = 0`。

如果后续重新生成 culture-specific Step 5：

- 默认直接复用 `data/step5_qa_variant_cache.culture_specific/`，可以保留已修正的问题。
- 若使用 `--refresh-cache` 强制重调 API，应重新检查 `summary.warning_count` 和 `warnings`。
- 若只想用 cache 重建输出，不要加 `--refresh-cache`。

推荐检查命令：

```bash
jq '.summary' data/qa_variants.en.culture_specific.json
jq '.warnings' data/qa_variants.en.culture_specific.json
```

---

## 10. 质量检查

Step 5 生成后至少检查：

- 每个 card 是否有 1 条英语 core
- 每个 card 是否有指定数量英语 surface
- `variant_layer` 是否只有 `core` / `surface`
- surface 是否仍然问同一个 relation
- question 是否 answer-aware，而不是宽泛覆盖 fact statement
- question 是否包含 `answer_leakage_in_question`
- question 是否自然、独立、可判分
- expected answer 是否短且与 card answer 对齐
- `answer_aliases` 是否仍有 topic alias、上下文实体或非等价答案污染

如果发现某张 card 本身不适合出题，应回到 Step 3 或 Step 4 处理，而不是在 Step 5 用 prompt 把问题“圆回来”。

---

## 11. 边界

Step 5 可以做：

- 根据已配对 card 生成英语 QA
- 保留生成 warnings 供 Step 7 review
- 为 Step 6 提供 canonical English source QA

Step 5 不应做：

- 新增 relation
- 新增事实
- 重读 Wiki 原文抽取证据
- 重做 target / neighbor pairing
- 直接扩展到多语言
- 生成 recovery / escape path stress test

这样 Step 5 才能保持低耦合、低回滚成本，也能让 Step 6 的语言扩展建立在统一的 canonical English QA 上。
