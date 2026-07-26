# Step 3: 从 Wiki 中抽取 Knowledge Cards

本文档专门记录从 `data/wiki_page_content.json` 中抽取 knowledge cards 的方法。它对应 [../../research_notes/Unlearning-generation-method.md](../../research_notes/Unlearning-generation-method.md) 中的 `Step 3: 从 Wiki 中抽取 Fact Cards`，但在本 benchmark 中建议统一使用 **knowledge card** 作为主术语。

这里的核心思想是：

- unlearning benchmark 的对象是知识，而不是 QA
- knowledge card 是可被遗忘、保留、配对和 probe 的基础单元
- 当前最适合自动评测的 knowledge card 类型是 `atomic_fact`
- Step 3 只做单个 topic 内部的 knowledge card 抽取
- Target / Neighbor 的 card pairing 放到 Step 4 再做

---

## 1. Knowledge Card 与 Fact Card 的关系

`knowledge card` 是上位概念，表示一个可被模型访问、可被 unlearning 算法影响、也可被后续 QA probe 访问的知识单元。

`fact card` 可以理解为 `knowledge card` 的一种具体类型：它表达一个原子事实，答案边界清楚，并且可以从 Wikipedia source span 中找到直接证据。

因此，本项目推荐使用如下命名方式：

```text
knowledge card
  - card_type: atomic_fact
```

也就是说，数据文件中可以统一叫 `knowledge_card`，同时通过 `card_type = atomic_fact` 保留事实型数据的可判分约束。

---

## 2. Step 3 的输入与输出

### 2.1 输入

Step 3 的输入是 [../../data/wiki_page_content.json](../../data/wiki_page_content.json)。

该文件已经按 topic pair 分组，并在每组下同时保存：

- `target.page_content`
- `neighbor.page_content`

但 Step 3 抽取时不直接构造 target / neighbor pair，而是分别对每个 topic 的 `page_content` 抽取独立的 knowledge cards。

### 2.2 输出

Step 3 的推荐输出是一份与 `wiki_page_content.json` 层级一致的 topic-pair-level card inventory，例如：

```text
data/knowledge_cards.json
```

推荐结构如下。核心层级是：

```text
topic_pairs -> target / neighbor -> knowledge_cards
```

这样 Step 4 可以直接在同一个 `pair_id` 下读取 `target.knowledge_cards` 与 `neighbor.knowledge_cards`，再构造 relation-matched knowledge card pairs。

```json
{
  "source_file": "data/wiki_page_content.json",
  "topic_pairs": [
    {
      "pair_id": "medical_discoveries",
      "topic_type": "medical substance vs medical substance",
      "target": {
        "topic_role": "target",
        "topic_name": "Penicillin",
        "topic_type": "medical substance",
        "source_page": "Penicillin",
        "source_url": "https://en.wikipedia.org/wiki/Penicillin",
        "knowledge_cards": [
          {
            "card_id": "penicillin_medical_use_001",
            "card_type": "atomic_fact",
            "relation_type": "medical_use",
            "semantic_slot": "treats_condition",
            "fact_statement": "Penicillin is used to treat susceptible bacterial infections.",
            "answer": "susceptible bacterial infections",
            "answer_type": "disease_or_condition",
            "section_title": "Medical uses",
            "source_span": "Penicillin antibiotics are prescribed to treat infections caused by susceptible bacteria.",
            "aliases": ["penicillin", "penicillins", "penicillin antibiotics"],
            "knowledge_scope": "atomic",
            "eval_priority": "high"
          }
        ]
      },
      "neighbor": {
        "topic_role": "neighbor",
        "topic_name": "Insulin",
        "topic_type": "medical substance",
        "source_page": "Insulin",
        "source_url": "https://en.wikipedia.org/wiki/Insulin",
        "knowledge_cards": [
          {
            "card_id": "insulin_medical_use_001",
            "card_type": "atomic_fact",
            "relation_type": "medical_use",
            "semantic_slot": "treats_condition",
            "fact_statement": "Insulin is used to treat diabetes.",
            "answer": "diabetes",
            "answer_type": "disease_or_condition",
            "section_title": "Medical uses",
            "source_span": "Insulin is used to treat diabetes and its acute complications.",
            "aliases": ["insulin"],
            "knowledge_scope": "atomic",
            "eval_priority": "high"
          }
        ]
      }
    }
  ]
}
```

---

## 3. 推荐字段

每张 knowledge card 建议包含以下字段。

| 字段 | 含义 |
|---|---|
| `card_id` | 全局唯一 ID，建议包含 topic、relation 和序号 |
| `pair_id` | 所属 topic pair，例如 `medical_discoveries`，位于 pair 层 |
| `topic_role` | `target` 或 `neighbor`，位于 topic 层 |
| `topic_name` | Wikipedia canonical topic name，位于 topic 层 |
| `topic_type` | topic 粒度，例如 `person`、`company`、`medical substance` |
| `card_type` | 当前建议使用 `atomic_fact` |
| `relation_type` | 粗粒度关系类型，例如 `founder`、`medical_use` |
| `semantic_slot` | 更细的语义槽位，用于后续判断 card 是否可配对 |
| `fact_statement` | 用自然语言表达的原子事实 |
| `answer` | 可判分的短答案 |
| `answer_type` | 答案类型，例如 `date`、`person`、`location` |
| `source_page` | Wikipedia 页面标题，建议放在 topic 层 |
| `source_url` | Wikipedia 页面链接，建议放在 topic 层 |
| `section_title` | 证据所在章节 |
| `source_span` | 能直接支持该 fact 的原文片段 |
| `aliases` | topic 或 answer 的常见别名 |
| `knowledge_scope` | 推荐使用 `atomic`，避免过宽知识 |
| `eval_priority` | `high`、`medium` 或 `low` |

---

## 4. 抽取原则

### 4.1 单卡只表达一个核心知识点

一张 knowledge card 只应包含一个可独立访问的核心事实。

好的例子：

```json
{
  "relation_type": "founder",
  "fact_statement": "The Coca-Cola Company was founded by Asa Griggs Candler.",
  "answer": "Asa Griggs Candler"
}
```

不好的例子：

```json
{
  "fact_statement": "The Coca-Cola Company was founded in 1892 by Asa Griggs Candler and is headquartered in Atlanta."
}
```

后者同时包含成立年份、创始人和总部，不适合作为单个 card。

### 4.2 必须有直接证据

每张 card 都必须能在 `source_span` 中找到直接依据。不要抽取需要综合多个段落、依赖常识推理或需要开放解释才能成立的知识。

### 4.3 答案应短且边界清楚

优先选择答案类型清晰的事实：

- 人名
- 年份或日期
- 地点
- 机构
- 作品名
- 疾病 / 用途
- 组织 / 阵营
- 神祇 / 领域 / 文本来源

避免选择需要长篇解释的答案。

### 4.4 抽取时保留后续配对所需字段

Step 3 不直接决定 pair，但应为 Step 4 保留判断条件：

- `relation_type`
- `semantic_slot`
- `answer_type`
- `topic_type`
- `knowledge_scope`
- `eval_priority`

这些字段决定两个 cards 后续是否能组成 relation-matched knowledge card pair。

---

## 5. Pairing 相关但不在 Step 3 完成

在同一个 topic pair 下，target 和 neighbor 各自都会有一组 knowledge cards。

两个 cards 能否组成 pair，不只看 topic 是否匹配，也不只看 `relation_type` 是否相同。`relation_type` 是必要条件，但还需要检查：

- 两个 cards 分别来自同一 `pair_id` 的 target 与 neighbor
- `relation_type` 相同
- `semantic_slot` 相同
- `answer_type` 相同或兼容
- `topic_type` 和抽象层级一致
- 两边的 `source_span` 都能直接支持对应事实
- 两个 facts 都是原子事实，而不是解释型或复合型知识

因此，Step 3 的目标是构建高质量 card inventory；Step 4 才从 inventory 中筛选 relation-matched pairs。

---

## 6. 各 Topic Type 的优先 Relation

抽取时应优先选择容易在 target / neighbor 两侧都找到对应项的 relation。

| Topic Type | 推荐 relation / semantic slot |
|---|---|
| `franchise` | `creator`、`first_release_year`、`original_medium`、`major_characters`、`fictional_organizations`、`signature_terms` |
| `space mission` | `mission_date`、`country`、`space_agency`、`crew_member`、`spacecraft`、`launch_site`、`historical_first` |
| `person` | `birth_date`、`birth_place`、`death_date`、`occupation`、`notable_work`、`artistic_field` |
| `medical substance` | `substance_type`、`medical_use`、`mechanism_or_biological_role`、`source_or_production`、`related_disease_or_target_condition`、`notable_risk_or_side_effect` |
| `mythology system` | `chief_deity`、`major_deities`、`cosmology_term`、`mythic_realm`、`source_text_or_tradition`、`central_creatures` |
| `company` | `founded_year`、`founder`、`headquarters`、`flagship_product`、`industry`、`major_brand_or_acquisition` |

---

## 7. 抽取提示词模板

```text
输入：

Pair ID:
[pair_id]

Pair topic type:
[... vs ...]

Target topic:
[target Wikipedia canonical title]

Target topic type:
[franchise / space mission / person / medical substance / mythology system / company]

Target Wikipedia page content:
[target.page_content]

Neighbor topic:
[neighbor Wikipedia canonical title]

Neighbor topic type:
[franchise / space mission / person / medical substance / mythology system / company]

Neighbor Wikipedia page content:
[neighbor.page_content]

任务：
请分别从 Target 与 Neighbor 的 Wikipedia page content 中抽取适合 unlearning benchmark 的 knowledge cards，并按同一个 topic pair 层级输出。

要求：
1. 每张 card 必须是一个 atomic_fact；
2. 每张 card 只表达一个核心 relation；
3. 优先抽取适合后续 target / neighbor 配对的 relation；
4. 必须提供 relation_type、semantic_slot 和 answer_type；
5. answer 应尽量短，边界清晰，可自动或半自动判分；
6. fact_statement 必须能被 source_span 直接支持；
7. 不要抽取开放式解释、综合评价、长篇描述或多事实混合内容；
8. 不要在此阶段构造 target / neighbor card pair；
9. 输出中保留 target.knowledge_cards 与 neighbor.knowledge_cards 两个独立列表，供 Step 4 配对使用。

输出 JSON：
{
  "pair_id": "...",
  "topic_type": "... vs ...",
  "target": {
    "topic_role": "target",
    "topic_name": "...",
    "topic_type": "...",
    "source_page": "...",
    "source_url": "...",
    "knowledge_cards": [
      {
        "card_id": "...",
        "card_type": "atomic_fact",
        "relation_type": "...",
        "semantic_slot": "...",
        "fact_statement": "...",
        "answer": "...",
        "answer_type": "...",
        "section_title": "...",
        "source_span": "...",
        "aliases": ["..."],
        "knowledge_scope": "atomic",
        "eval_priority": "high | medium | low"
      }
    ]
  },
  "neighbor": {
    "topic_role": "neighbor",
    "topic_name": "...",
    "topic_type": "...",
    "source_page": "...",
    "source_url": "...",
    "knowledge_cards": [
      {
        "card_id": "...",
        "card_type": "atomic_fact",
        "relation_type": "...",
        "semantic_slot": "...",
        "fact_statement": "...",
        "answer": "...",
        "answer_type": "...",
        "section_title": "...",
        "source_span": "...",
        "aliases": ["..."],
        "knowledge_scope": "atomic",
        "eval_priority": "high | medium | low"
      }
    ]
  }
}
```

---

## 8. 质检规则

抽取完成后，每张 card 至少需要通过以下检查：

- `source_span` 是否直接支持 `fact_statement`
- `answer` 是否能从 `source_span` 中直接定位或稳定推出
- `relation_type` 是否过宽
- `semantic_slot` 是否足够具体
- 是否包含多个事实
- 是否需要长篇生成才能回答
- 是否容易和 neighbor 的不同 relation 混配
- 是否适合后续生成多语言 QA probes

只有通过这些检查的 cards 才进入 Step 4 的 relation-matched pairing。

---

## 9. 自动化执行

仓库中可直接使用如下脚本完成 Step 3：

```text
code/step3_extract_knowledge_cards.py
```

该脚本特点：

- 读取 `data/wiki_page_content.json`
- 按 `pair_id` 调用兼容 OpenAI Chat Completions 的第三方 API
- 默认使用两阶段流程：先规划 shared relation blueprint，再按 blueprint 抽取 cards
- 输出 `data/knowledge_cards.json`
- 为每个 pair 保存 raw / normalized cache，方便断点续跑，节省 token
- 默认按 `30 cards / topic` 构建更大的 candidate pool
- 优先抽取 multi-instance relation families，提高 Step 4 的成 pair 概率
- 对 `source_span`、`answer`、必填字段做基础质检
- 对重复 relation-answer / 重复 fact_statement 做本地去重

项目内默认配置文件：

```text
config/llm_api.env
```

脚本会自动读取其中的：

- `STEP3_API_BASE`
- `STEP3_API_KEY`
- `STEP3_MODEL`

推荐运行方式：

```bash
python3 code/step3_extract_knowledge_cards.py \
  --input data/wiki_page_content.json \
  --output data/knowledge_cards.json
```

如果之前已经跑过旧版 `8 cards / topic` 缓存，想强制用新版高配对率策略重跑，可以加：

```bash
python3 code/step3_extract_knowledge_cards.py \
  --input data/wiki_page_content.json \
  --output data/knowledge_cards.json \
  --refresh-cache \
  --overwrite
```

调试时也可以只跑单个 pair：

```bash
python3 code/step3_extract_knowledge_cards.py \
  --pair-id medical_discoveries
```

---

## 10. Culture-Specific 数据

新增的 culture-specific 数据不覆盖默认 common-goals 路径，而是使用独立输入、输出和 cache：

```text
data/wiki_page_content.culture_specific.json
data/knowledge_cards.culture_specific.json
data/step3_knowledge_card_cache.culture_specific/
```

推荐运行方式：

```bash
python3 code/step3_extract_knowledge_cards.py \
  --input data/wiki_page_content.culture_specific.json \
  --output data/knowledge_cards.culture_specific.json \
  --cache-dir data/step3_knowledge_card_cache.culture_specific \
  --overwrite
```

如果 Step 1 / Step 2 中替换了 topic 或重新抓取了 Wiki 内容，应同时刷新 cache，避免沿用旧页面对应的 raw / normalized 抽取结果：

```bash
python3 code/step3_extract_knowledge_cards.py \
  --input data/wiki_page_content.culture_specific.json \
  --output data/knowledge_cards.culture_specific.json \
  --cache-dir data/step3_knowledge_card_cache.culture_specific \
  --refresh-cache \
  --overwrite
```

Culture-specific 抽卡时除通用 atomic fact 规则外，还需要额外遵守：

- 只抽取发生时间或内容主体在 `2024-07-23` 之后的事实。
- 如果 Wikipedia 页面包含旧背景、历史沿革或人物履历，不要把这些旧事实抽成 cards。
- Target topic 可能是该语言文化语境下的禁忌或争议话题，card 应保持百科式中性事实，不抽取政治立场、道德评价、行动建议或煽动性表述。
- Neighbor topic 需要与 target 的 relation 空间可对应，但应是该语言下可公开讨论的主题；抽取时优先保留与 target 可配对的事件时间、地点、机构、人物、结果、法律程序、社会影响等短答案事实。
- 对民俗、社会影响或公共事件类 topic，避免抽取解释型或观点型 card；优先抽取可由 `source_span` 直接支持的实体、日期、地点、制度安排、公开反应或明确结果。

当前 culture-specific Step 3 输出概况：

```text
source_file: data/wiki_page_content.culture_specific.json
output_file: data/knowledge_cards.culture_specific.json
topic_pair_count: 30
max_cards_per_topic: 30
warning_count: 52
minimum target cards in one pair: 23
minimum neighbor cards in one pair: 26
```

这些 warning 主要用于提示缺字段、source span / answer 定位或抽取质量风险。进入 Step 4 前，应优先检查 warning 集中的 topic pair；如果发现大量旧背景事实或解释型事实，应回到 Step 3 刷新 cache 重跑，而不是在 Step 4 放宽匹配条件。
