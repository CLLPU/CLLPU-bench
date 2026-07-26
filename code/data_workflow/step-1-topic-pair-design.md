# Step 1: Topic Pair Design

本文档记录 Step 1 的 topic-pair 设计与输出契约。当前数据构造分为两条并行数据线：

- `common-goals`：所有语言共同需要 unlearning 的 post-release / post-cutoff topics。
- `culture-specific`：只在特定语言或文化语境中需要 unlearning 的本地风险边界 topics。

两条数据线共享同一种 manifest 结构，后续 Step 2 使用同一个脚本抓取 Wikipedia 页面。但两者必须使用不同文件名，避免 culture-specific 回改覆盖 common-goals 的已有数据。

---

## 1. Step 1 的目标

Step 1 的核心任务是固定每个 `pair_id` 下的 target / neighbor topic，并为二者绑定 English Wikipedia canonical page。

每个 pair 都必须满足：

- `target` 与 `neighbor` 处在相近抽象层级。
- 两侧都有明确的 `wiki_title` 和 `wiki_url`。
- 两侧 topic 都满足当前数据线的时间边界；目前 common-goals 和 culture-specific 都要求 topic 出现、发生、发布、立法、生效或显著进入公共语境的时间晚于 `2024-07-23`。
- 两侧能支持后续 Step 3 抽取 relation-matched factual knowledge cards。
- `target` 是需要 unlearning / refusal stress-test 的 topic。
- `neighbor` 是相邻但不应被误删的 control topic。

Step 1 不下载 Wikipedia 正文；它只产出 Step 2 可消费的 manifest。

---

## 2. 当前 Step 1 输出文件

| 数据线 | 设计说明 | Step 1 manifest 输出 | 当前规模 | 当前状态 | Step 2 对应输出 |
|---|---|---|---:|---|---|
| common-goals | [topic-pair-summary.md](topic-pair-summary.md) | [../../data/wiki_page_manifest.json](../../data/wiki_page_manifest.json) | 50 pairs / 100 pages | 符合 post-cutoff 约束 | [../../data/wiki_page_content.json](../../data/wiki_page_content.json) |
| culture-specific | [culture-specific-topic-pair-summary.md](culture-specific-topic-pair-summary.md) | [../../data/wiki_page_manifest.culture_specific.json](../../data/wiki_page_manifest.culture_specific.json) | 30 pairs / 60 pages | `v4` 已按 post-cutoff 与 culture-specific 风险边界复核；Step 2 content 已重跑完成 | [../../data/wiki_page_content.culture_specific.json](../../data/wiki_page_content.culture_specific.json) |

文件命名约定：

- common-goals 使用默认文件名：`data/wiki_page_manifest.json`
- culture-specific 使用后缀文件名：`data/wiki_page_manifest.culture_specific.json`

后续新增数据线时，应继续使用显式后缀，例如 `data/wiki_page_manifest.<dataset_family>.json`。

---

## 3. Manifest 结构契约

Step 2 脚本要求每个 manifest 至少包含：

```json
{
  "step": "step_1_topic_pair_design",
  "source_language": "en",
  "source_site": "English Wikipedia",
  "topic_pairs": [
    {
      "pair_id": "example_pair",
      "topic_type": "topic class vs topic class",
      "target": {
        "role": "target",
        "topic_zh": "中文标题",
        "topic_en": "English topic",
        "wiki_title": "English Wikipedia title",
        "wiki_url": "https://en.wikipedia.org/wiki/English_Wikipedia_title"
      },
      "neighbor": {
        "role": "neighbor",
        "topic_zh": "中文标题",
        "topic_en": "English neighbor topic",
        "wiki_title": "English Wikipedia title",
        "wiki_url": "https://en.wikipedia.org/wiki/English_Wikipedia_title"
      }
    }
  ]
}
```

可选但建议保留的字段：

- `design_version`
- `dataset_family`
- `topic_category`
- `candidate_relation_families`
- `title_match`
- `abstraction_level_check`
- `selection_note`

Culture-specific manifest 还应保留：

- `primary_language`
- `affected_languages`
- `locale_scope`
- `sensitivity_type`
- `neighbor_context`
- `qa_guardrail`

Step 2 当前只强校验 `pair_id`、`topic_type`、`target`、`neighbor`、`wiki_title`、`wiki_url` 等抓取必需字段；额外字段用于后续人工审查和 Step 3 之后的标签继承。

---

## 4. Common-goals 设计规则

Common-goals 数据用于构造跨语言共同遗忘目标。本版 common-goals 不再使用旧版 6 组经典 topic，因为它们高度可能出现在 Llama 2 / Llama 3.1 系列模型的 pretraining 语料中。

当前 common-goals 采用 50 组 post-release topic pairs。基准时间边界是 Meta Llama 3.1 发布时间：

```text
2024-07-23
```

选择规则：

- 新发布产品尽量落在 2025 年中到 2026 年中。
- 政治文化事件必须是 2025 年以后发生的事件。
- Target / Neighbor 必须处在相似抽象层级，例如 comet vs comet、earthquake vs earthquake、smartphone vs smartphone。
- 每组都要能抽取一批 relation-matched facts，例如 date、location、discoverer、manufacturer、winner、fatalities、release_date。
- 对于 broader Wikipedia page 上的 section topic，例如 Claude Sonnet 4.5、DeepSeek V3.1、Qwen3-Max、Apple Vision Pro M5 variant，Step 3 抽卡时必须限定到指定 release section，避免抽到旧版本事实。

当前 topic 类型分布：

- 新发现天体：6 pairs
- 新命名古生物：6 pairs
- 突发公共卫生事件：2 pairs
- 自然灾害：11 pairs
- 停电事故：1 pair
- 大型交通事故：5 pairs
- 政治文化事件：10 pairs
- 新发布产品：9 pairs

完整 common-goals 表格见 [topic-pair-summary.md](topic-pair-summary.md)，机器输入见 [../../data/wiki_page_manifest.json](../../data/wiki_page_manifest.json)。

---

## 5. Culture-specific 设计规则

Culture-specific 数据用于测试模型能否学会本地风险边界：在某些语言或文化语境中需要规避的内容，应被 unlearning / refusal stress-test；相邻但公开可讨论的内容不能被一起误伤。

从当前版本开始，culture-specific 与 common-goals 共用同一个 hard cutoff：

```text
2024-07-23
```

也就是说，culture-specific 的 target 和 neighbor 都必须是 2024-07-23 之后出现、发生、发布、立法、生效或显著进入公共语境的 topic。长期存在的历史、宗教、法律、社会制度或文化争议 topic，即使具有 culture-specific 风险，也不能作为正式 release 数据。

当前 culture-specific 采用 10 种语言各 3 组，共 30 组 topic pairs：

```text
en, ar, bn, de, es, fr, ja, sw, th, zh
```

选择规则：

- topic 时间边界必须晚于 `2024-07-23`；优先选择 2025 年以后形成的事件、法律变化、监管行动、社会争议、平台争议、公共安全事件或文化舆论事件。
- `target topic` 必须在对应 `affected_languages` 中具有某种法律、宗教、民俗、社会舆论或企业合规风险。
- `neighbor topic` 必须与 target 处在相邻文化、法律、社会或知识语境中，但在该语言下通常可以公开讨论。
- 不优先使用“目标国家 topic X vs 其他国家 topic X”，避免 benchmark 退化成国家名识别。
- 每个 target / neighbor topic 都必须有独立、稳定的 English Wikipedia canonical page；不能用 broader page 的 section 作为独立 topic。
- 中文 `zh` 部分采用低政治风险原则，不纳入国家领导人、主权争议、近现代政治运动、民族地区、人权指控、政党合法性、审查制度本身等 topic。
- 后续 QA 只抽取中性百科事实，不生成倡议、动员、规避执法、仇恨论述、操作细节、露骨内容或美化表达。

当前 [culture-specific-topic-pair-summary.md](culture-specific-topic-pair-summary.md) 和 [../../data/wiki_page_manifest.culture_specific.json](../../data/wiki_page_manifest.culture_specific.json) 已更新为 `v4_post_cutoff_culture_specific_rule_checked`，包含 30 组 post-cutoff topic pairs。对应 Step 2 输出 [../../data/wiki_page_content.culture_specific.json](../../data/wiki_page_content.culture_specific.json) 与 [../../data/wiki_page_content.culture_specific_word_counts.json](../../data/wiki_page_content.culture_specific_word_counts.json) 已基于该 manifest 重跑完成，可作为 culture-specific Step 3 的正式输入。

---

## 6. 回改规则

如果发现 topic 选错、粒度不一致、Wikipedia 页面不对，应回到对应数据线的 Step 1 文件修改：

- common-goals：先改 [topic-pair-summary.md](topic-pair-summary.md)，再同步 [../../data/wiki_page_manifest.json](../../data/wiki_page_manifest.json)。
- culture-specific：先改 [culture-specific-topic-pair-summary.md](culture-specific-topic-pair-summary.md)，再同步 [../../data/wiki_page_manifest.culture_specific.json](../../data/wiki_page_manifest.culture_specific.json)。

如果 Step 2 或 Step 3 发现页面文本太短、重定向异常、事实密度不足，优先替换同类 topic，而不是放宽粒度。

不要在回改 culture-specific 时覆盖 common-goals 的默认文件；反之亦然。

---

## 7. 下一步

对应数据线的 Step 1 manifest 是 Step 2 的正式输入：

```text
Step 1 topic-pair manifest
-> Step 2 wiki page collection
```

Step 2 的具体文件关系和运行命令见 [step-2-wiki-page-collection.md](step-2-wiki-page-collection.md)。
