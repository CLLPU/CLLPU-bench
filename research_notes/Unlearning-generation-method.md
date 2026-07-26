# Unlearning knowledge-QA construction method

本文档记录了在构造cross unlearning 语料过程中的整体方法，以及基于 knowledge-first 思路的数据构造流程。

这里的核心更新是：

- 先定义知识单元，再生成 QA
- 先做 Target / Neighbor 的关系配对，再生成问题
- QA 不是被遗忘对象本身，而是用于观测知识是否仍可访问的 probe

---

## 1. Topic Pair 设计

Topic pair 的构造过程、筛选原则和数据线边界单独记录在 [../code/data_workflow/step-1-topic-pair-design.md](../code/data_workflow/step-1-topic-pair-design.md)。

历史 pilot 版本中曾是 ~~当前 6 组 Target / Neighbor 结果~~。该口径已过期；当前 active 数据构造以 [../code/data_workflow/README.md](../code/data_workflow/README.md) 为准：common-goals 为 50 组 topic pairs，culture-specific 为 30 组 topic pairs。

其中，[../code/data_workflow/topic-pair-summary.md](../code/data_workflow/topic-pair-summary.md) 汇总了当前使用的 topic pair 总表，并额外整理了每组 target topic / neighbor topic 对应的 Wikipedia 条目与链接，便于后续 fact card 抽取与来源对齐。

本文档只保留后续从 topic pair 到 fact card、relation-matched fact pair、QA variants 的通用数据构造流程。

---

## 2. 数据单位：先 Knowledge，再 QA

新的构造方式不再把 QA 对视为数据集的原子单位，而是把 knowledge unit / fact card 视为原子单位。

原因是：

- unlearning 的对象本质上是知识，而不是某一个具体问法
- 同一个知识可以被不同语言、不同模板、不同 paraphrase 访问
- 如果一开始只存 QA，就很难区分模型到底是忘了知识，还是只对某一种表述失效
- 在 cross-lingual setting 下，我们需要一个语言无关的 canonical knowledge object，来承接后续的多语言 probing

因此，新的构造流程是：

> Wiki page -> fact cards -> relation-matched Target / Neighbor fact pairs -> QA variants

这里：

- Wiki page 是原始内容来源
- fact card 是知识单元
- relation-matched Target / Neighbor fact pair 是评测中的核心配对单元
- QA variants 是用于访问该知识单元的 probe

---

## 3. Fact Card 设计

### 3.1 什么是 Fact Card

每一个 fact card 对应一个可以被单独访问、单独遗忘、单独评测的知识单元。

一个理想的 fact card 应满足：

- 单一关系明确：尽量只表达一个核心 relation
- 答案可判定：答案尽量短、边界清晰、便于自动或半自动判分
- 可溯源：能够在对应 Wiki 词条中找到直接证据
- 可跨语言复用：同一个 fact card 可以派生多语言 QA

### 3.2 推荐字段

每个 fact card 建议至少包含以下字段：

```json
{
  "fact_id": "starwars_release_date",
  "topic_group": "Global Pop Culture & Franchises",
  "topic_name": "Star Wars: Episode IV - A New Hope",
  "topic_type": "film",
  "relation_type": "release_date",
  "fact_statement": "Star Wars: Episode IV - A New Hope was released on May 25, 1977.",
  "answer": "May 25, 1977",
  "answer_type": "date",
  "source_page": "Star Wars",
  "source_span": "...",
  "aliases": [
    "Star Wars",
    "Star Wars: Episode IV",
    "A New Hope"
  ]
}
```

### 3.3 Fact Card 的粒度要求

建议优先保留以下类型的 fact：

具体的类型，可以让 LLM 比对 topic 的 Wikipedia 内容来决定。

- 上映 / 发生 / 出生 / 成立时间
- 导演 / 作者 / 创始人 / 发现者
- 地点 / 总部 / 出生地 / 发生地
- 主要反派 / 主角 / 关键实体
- 原因 / 用途 / 作用 / 核心机制
- 奖项 / 代表作 / 标志性事件

不建议把以下内容作为主评测单元：

- 需要长篇生成才能完整回答的问题
- 同时包含多个核心事实的复合问答
- 事实边界模糊、答案难以标准化的问题
- 明显依赖开放式解释或价值判断的问题

---

## 4. Target / Neighbor 配对方式

### 4.1 配对单位不再是“topic 相近的 QA”，而是“relation 对齐的 fact”

新的方法中，Target / Neighbor 的核心配对单位不是 QA，而是：

> relation-matched Target / Neighbor fact pair

也就是说，Target 和 Neighbor 不仅 topic 接近，而且必须问的是同一种 relation type。

例如：

- 好的配对：
  - Target: 《星球大战》的上映时间是什么？
  - Neighbor: 《星际迷航》的上映时间是什么？
  - relation_type: `release_date`

- 不好的配对：
  - Target: 《星球大战》中绝地武士角色有哪些？
  - Neighbor: 《星际迷航》中进取号的建设地点是哪里？

后者虽然 topic 相近，但 relation type 不同，无法用于稳定测量 boundary Neighbor。

### 4.2 配对原则

每一个 Target / Neighbor fact pair 应满足：

- topic 领域接近
- topic 粒度一致
- relation type 一致
- 答案类型尽量一致
- 证据强度相近

这里特别强调 topic 粒度一致。例如：

- franchise 应该对 franchise
- 电影应当对电影
- 公司应当对公司
- 事故应当对事故

不能出现：

- Target 是公司词条
- Neighbor 实际却是某个产品或子型号词条

否则后续的 retain / neighbor 分析会被 topic 粒度差异污染。

### 4.3 Pair 数据结构

一个 relation-matched pair 可以表示为：

```json
{
  "pair_id": "starwars_startrek_release_date",
  "topic_group": "Global Pop Culture & Franchises",
  "relation_type": "release_date",
  "target_fact_id": "starwars_release_date",
  "neighbor_fact_id": "startrek_release_date",
  "answer_type": "date"
}
```

---

## 5. QA Variants 设计

### 5.1 QA 的角色

在新的构造框架中，QA 不再是被遗忘对象本身，而是：

> 用于访问某个 fact card 的 probe

因此，同一个 fact card 应该对应多种 QA variants，而不是只生成一个标准问法。

这里需要额外固定一条边界：

> 如果主任务是测“从目标语言遗忘到其他语言的迁移”，那么 QA variant 的默认设计必须避免把“语言 B 的直接访问能力”和“语言 A+B 混合路径的恢复能力”混在一起。

因此，默认 QA variant 集合只保留单语 probe。跨语言迁移通过“同一 fact 在不同语言上的平行单语 QA”来测，而不是通过 mixed-language 或 bridge-language prompt 来测。

### 5.2 QA Variant 的分层

建议把 QA variants 分为两层：

1. Core factual QA
   - 用于主评测
   - 目标是稳定、简洁、可判分

2. Surface variants
   - paraphrase
   - alias substitution
   - template variation
   - translation / back-translation
   - 用于测试同一语言内部表层改写后的可访问性

这里的 `translation / back-translation` 指的是：

- 先为某个目标语言单独写出自然问法
- 或把已有人类写好的问法翻译后再人工校正
- 但最终产物仍应是单语问题和单语答案预期

默认不纳入 QA variant 构造集的类型包括：

- 不同语言提问但要求另一种语言作答
- query / answer language mismatch
- code-switched prompts
- bridge-language access
- 任何以“恢复与逃逸路径”而非“目标语言到其他语言的迁移”作为主要测量对象的 probe

如果后续确实要研究 recovery / escape path，上述类型应单列为额外 stress test，而不是并入主 QA variants。

### 5.3 Core QA 的要求

主评测中的 Core QA 应满足：

- 问题只对应一个 fact card
- 问题的 relation type 清晰
- 答案尽量短
- 问题不依赖额外上下文
- 不把多个事实绑在一个问题里

例如：

- 好的 Core QA：
  - Q: 《星球大战》最初上映于哪一年？
  - A: 1977 年

- 较弱的 Core QA：
  - Q: 《星球大战》的主要剧情、主要人物和历史影响分别是什么？
  - A: ...

后者更像生成题，不适合作为主 forget probe。

---

## 6. 数据集规模定义

在新的构造方式下，数据集规模不应只按 QA 数量定义，而应按三个层次描述：

1. Topic pair 数量
   - 记为 \(m\)

2. 每个 topic pair 下的 relation-matched fact pair 数量
   - 记为 \(n\)

3. 每个 fact card 对应的 QA variants 数量
   - 记为 \(q\)

那么：

- fact card 总数为：

\[
2 \times m \times n
\]

- 若每个 fact card 派生 \(q\) 个 QA variants，则 QA 总数为：

\[
2 \times m \times n \times q
\]

因此，新的 benchmark 更推荐优先报告：

- topic pair 数
- fact pair 数
- QA variant 数

而不是只报告最终的 QA 总量。

---

## 7. 执行工作流与解耦边界

从这里开始，文档的重点不再是“研究上为什么这样设计”，而是“工程上如何把每一步拆开、低成本复跑”。

这部分已经单独沉淀为 benchmark data construction workflow 文档：

- 总入口：[../code/data_workflow/README.md](../code/data_workflow/README.md)
- Step 1: [../code/data_workflow/step-1-topic-pair-design.md](../code/data_workflow/step-1-topic-pair-design.md)
- Step 2: [../code/data_workflow/step-2-wiki-page-collection.md](../code/data_workflow/step-2-wiki-page-collection.md)
- Step 3: [../code/data_workflow/step-3-knowledge-card-extraction.md](../code/data_workflow/step-3-knowledge-card-extraction.md)
- Step 4: [../code/data_workflow/step-4-relation-matched-card-pairing.md](../code/data_workflow/step-4-relation-matched-card-pairing.md)
- Step 5: [../code/data_workflow/step-5-qa-variant-generation.md](../code/data_workflow/step-5-qa-variant-generation.md)
- Step 6: [../code/data_workflow/step-6-language-expansion.md](../code/data_workflow/step-6-language-expansion.md)
- Step 7: [../code/data_workflow/step-7-quality-review.md](../code/data_workflow/step-7-quality-review.md)

这里仅保留三条方法层的不变量：

- Topic pair 必须先固定，再进入内容抽取。
- knowledge card pair 必须先固定，再生成 QA probes。
- 每一步都应显式声明输入数据、依赖文档和输出数据，保证局部修改时不必从头重做。

evaluation metric 的设计不放在这条 workflow 中，后续应单独在 [../code/evaluation_workflow/README.md](../code/evaluation_workflow/README.md) 维护。

---

## 8. 质检规则

建议至少加入以下检查项：

### 8.1 Topic 层检查

- Target / Neighbor 是否属于同一抽象层级
- Wiki 词条是否与 topic 名一致
- 是否误用了子页面或子产品页面

### 8.2 Fact 层检查

- fact 是否只表达一个核心 relation
- answer 是否可标准化
- source span 是否能支持该 fact
- relation_type 标注是否稳定

### 8.3 Pair 层检查

- Target / Neighbor 的 relation_type 是否一致
- answer_type 是否一致或足够接近
- 两个 fact 的证据密度是否相近

### 8.4 QA 层检查

- QA 是否只对应一个 fact card
- QA 是否出现 target / neighbor 串扰
- QA 是否脱离 source span
- QA 是否变成开放式生成问题
- QA variants 是否真的仍在访问同一个 fact

---

## 9. 提示词模板

新的提示词也应拆成三个阶段，而不是一步直接生成 QA。

### 9.1 阶段一：抽取 Fact Cards

```text
输入：

话题名称：
[topic name]

话题类型：
[film / person / company / disaster / mythology / ...]

Wiki 原文：
[对应词条内容]

任务：
请基于给定 Wiki 原文，抽取一组适合作为 unlearning benchmark 基础单元的 fact cards。

要求：
1. 每个 fact card 只表达一个核心 relation；
2. relation_type 必须明确，例如 release_date、founder、cause、headquarters、main_antagonist；
3. answer 必须尽量短且边界清晰；
4. fact_statement 必须能在原文中找到直接依据；
5. 避免抽取需要长篇解释才能回答的问题；
6. 避免抽取多个事实混在一起的复合事实；
7. 输出时给出 source_span 作为证据。

输出格式：
[
  {
    "fact_id": "...",
    "topic_name": "...",
    "relation_type": "...",
    "fact_statement": "...",
    "answer": "...",
    "answer_type": "...",
    "source_span": "..."
  }
]
```

### 9.2 阶段二：构造 Relation-Matched Pair

```text
输入：

Target fact cards：
[Target 的 fact card 列表]

Neighbor fact cards：
[Neighbor 的 fact card 列表]

任务：
请从 Target 和 Neighbor 的 fact cards 中，构造 relation-matched pairs。

要求：
1. 每一对 pair 的 relation_type 必须一致；
2. answer_type 应尽量一致；
3. 两个 fact 必须分别来自 Target 与 Neighbor；
4. 不要配对 topic 接近但 relation 不同的事实；
5. 若某个 fact 在另一侧没有足够匹配的 relation，则舍弃该 fact。

输出格式：
[
  {
    "pair_id": "...",
    "relation_type": "...",
    "target_fact_id": "...",
    "neighbor_fact_id": "...",
    "answer_type": "..."
  }
]
```

### 9.3 阶段三：为 Fact Card 生成 QA Variants

```text
输入：

fact card：
{
  "fact_id": "...",
  "topic_name": "...",
  "relation_type": "...",
  "fact_statement": "...",
  "answer": "..."
}

任务：
请围绕该 fact card 生成 QA variants。

要求：
1. 所有问题都必须访问同一个 fact；
2. 先生成 1 条 core factual QA；
3. 再生成若干 paraphrase / alias / template variation；
4. Step 5 只生成英语 canonical QA；若扩展到多语言，应在后续独立步骤中把英语 canonical QA 翻译并本地化成各语言的平行单语版本，并保证只是语言变化，而不是换了 relation；
5. 不要引入原 fact 中不存在的新信息。

输出格式：
{
  "core_qa": [
    {"Q": "...", "A": "..."}
  ],
  "surface_variants": [
    {"Q": "...", "A": "..."}
  ]
}
```

---

## 10. 一句话总结

新的构造逻辑是：

> 先把 Wiki 页面拆成可独立评测的知识单元，再在 Target / Neighbor 之间做 relation 对齐，最后把 QA 作为访问这些知识单元的 probe 来生成。

因此，本数据集不再是“直接从话题生成一批相似 QA”，而是一个：

- knowledge-centered
- relation-aligned
- source-grounded
- cross-lingual comparable

的 unlearning benchmark 数据构造流程。
