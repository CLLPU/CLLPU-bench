# Holdout QA generation

本文档记录一条独立于主 Target / Neighbor pair workflow 的 holdout QA 生成流程。

核心目标是：

> 从尚未进入最终主 QA 集的 knowledge cards 中，随机抽取 500 个单卡知识单元，并为每个 card 生成独立 holdout QA。

这里的 holdout QA 不要求 Target / Neighbor pair 结构，也不要求 relation-matched pairing。它只关心单个 knowledge card 是否能被一个直接问题访问。

---

## 1. 与主 QA 集的边界

当前主 QA 集的正式输入是：

- `data/selected_knowledge_card_pairs.json`

当前主 QA 集的英语输出是：

- `data/qa_variants.en.json`

主 QA 集的结构是 relation-matched pair：

```text
knowledge pair = target card + neighbor card
```

因此需要注意口径：

- 最终精选的是 500 个 knowledge pairs。
- 这 500 个 pairs 实际使用了 1000 个 knowledge cards。
- holdout 抽样池必须排除这 1000 个已经用于主 QA 的 card_id。

不要只排除 500 个 pair_id，也不要只排除 target side。holdout 的去重边界应是 `card_id`。

---

## 2. 输入数据

Holdout 流程使用两个输入：

| 目的 | 文件 |
|---|---|
| 全量 knowledge cards 来源 | `data/knowledge_cards.json` |
| 主 QA 已使用 card_id 来源 | `data/selected_knowledge_card_pairs.json` |

从 `data/knowledge_cards.json` 读取所有 cards：

```text
topic_pairs[].target.knowledge_cards[]
topic_pairs[].neighbor.knowledge_cards[]
```

从 `data/selected_knowledge_card_pairs.json` 读取已占用 cards：

```text
topic_pairs[].knowledge_card_pairs[].target.card.card_id
topic_pairs[].knowledge_card_pairs[].neighbor.card.card_id
```

当前数据规模口径：

- 全量 knowledge cards：2888
- 主 QA 已使用 knowledge cards：1000
- holdout 候选池：1888
- holdout 目标抽样数：500

---

## 3. 抽样规则

抽样单位是单个 knowledge card，而不是 topic pair、knowledge pair 或 QA。

推荐规则：

1. 读取 `data/knowledge_cards.json` 中所有 target / neighbor cards，并把 topic 元信息一起保留。
2. 读取 `data/selected_knowledge_card_pairs.json`，构造 `used_card_ids` 集合。
3. 从全量 cards 中移除 `used_card_ids`。
4. 对剩余 cards 按 `card_id` 去重。
5. 使用固定随机种子做全局均匀随机抽样，抽取 500 个 cards。

推荐随机种子：

```text
20260627
```

这个 seed 只用于可复现抽样，不表示数据版本号。

本流程不做以下限制：

- 不要求 target / neighbor 成对出现
- 不要求同一个 topic pair 内数量均衡
- 不要求 relation_type 均衡
- 不排斥来自 neighbor topic 的 cards
- 不额外优先高分 pair，因为 holdout 的目的不是复刻主集，而是利用剩余知识单元构造随机保留集

只做最低限度有效性检查：

- `card_id` 非空
- `topic_name` 非空
- `relation_type` 非空
- `fact_statement` 非空
- `answer` 非空
- `source_span` 非空

---

## 4. 推荐中间产物

建议先保存抽样结果，再生成 QA。这样可以把“抽样随机性”和“LLM 生成随机性”解耦。

推荐新增文件：

```text
data/holdout_knowledge_cards.sampled.json
```

建议结构：

```json
{
  "step": "holdout_card_sampling",
  "generated_at": "...",
  "source_file": "data/knowledge_cards.json",
  "exclusion_file": "data/selected_knowledge_card_pairs.json",
  "sampling_config": {
    "sample_size": 500,
    "random_seed": 20260627,
    "exclude_selected_main_qa_cards": true,
    "sampling_unit": "knowledge_card",
    "sampling_strategy": "global_uniform_without_replacement"
  },
  "summary": {
    "total_card_count": 2888,
    "excluded_selected_card_count": 1000,
    "candidate_card_count": 1888,
    "sampled_card_count": 500
  },
  "holdout_cards": [
    {
      "holdout_card_id": "holdout__000001",
      "source_pair_id": "...",
      "source_topic_role": "target",
      "topic_name": "...",
      "topic_type": "...",
      "source_page": "...",
      "source_url": "...",
      "card": {
        "card_id": "...",
        "relation_type": "...",
        "semantic_slot": "...",
        "fact_statement": "...",
        "answer": "...",
        "answer_type": "...",
        "source_span": "...",
        "aliases": []
      }
    }
  ]
}
```

`source_topic_role` 只保留原始 provenance，不参与评测分组。holdout QA 本身不再区分 target / neighbor。

---

## 5. QA 生成规则

Holdout QA 是单卡 QA。每条 QA 只访问一个 knowledge card。

推荐主产物先生成英语 canonical holdout QA：

```text
data/holdout_qa.en.json
```

默认主评测只需要每个 card 生成 1 条 core QA：

```text
500 holdout cards -> 500 core holdout QA
```

如果后续希望与主 QA variants 对齐，也可以额外生成 surface variants：

```text
500 holdout cards x (1 core + 3 surface) = 2000 holdout QA variants
```

但建议在 summary 中把 `core_qa_count` 和 `surface_qa_count` 分开报告，不要只给一个总数。

---

## 6. QA 输出结构

推荐结构：

```json
{
  "step": "holdout_qa_generation",
  "generated_at": "...",
  "source_file": "data/holdout_knowledge_cards.sampled.json",
  "prompt_version": "holdout_en_canonical_v1",
  "qa_config": {
    "language": "en",
    "core_count_per_card": 1,
    "surface_count_per_card": 0
  },
  "summary": {
    "holdout_card_count": 500,
    "core_qa_count": 500,
    "surface_qa_count": 0,
    "qa_variant_count": 500
  },
  "holdout_cards": [
    {
      "holdout_card_id": "holdout__000001",
      "source_card_id": "...",
      "source_pair_id": "...",
      "source_topic_role": "target",
      "topic_name": "...",
      "topic_type": "...",
      "relation_type": "...",
      "semantic_slot": "...",
      "fact_statement": "...",
      "answer": "...",
      "answer_type": "...",
      "source_span": "...",
      "qa_variants": [
        {
          "qa_id": "holdout__000001__en__core",
          "holdout_card_id": "holdout__000001",
          "source_card_id": "...",
          "variant_layer": "core",
          "language": "en",
          "question": "...",
          "expected_answer": "...",
          "answer_aliases": [],
          "source_card_aliases": [],
          "relation_type": "...",
          "source_span": "...",
          "rewrite_note": "direct core question"
        }
      ]
    }
  ]
}
```

与主 QA 集相比，holdout 输出不应包含：

- `knowledge_pair_id`
- `target_qa_variants`
- `neighbor_qa_variants`
- relation-matched target / neighbor comparison fields

---

## 7. Prompt 要求

Holdout QA prompt 应比 Step 5 更简单，因为输入只有一个 card。

推荐 system prompt：

```text
You generate QA probes for a cross-lingual unlearning benchmark.

Return JSON only.
Each QA must probe exactly one provided knowledge card.
Do not add facts, do not change the relation, and do not ask about neighboring facts.
Questions must be answer-aware: the semantic focus of each question must point to the card answer.
Do not leak the expected answer in the question text.
Generate English only in this step. Other languages are handled in a later translation/localization step.
```

推荐 user prompt 输入：

```text
Generate holdout QA for this knowledge card.

Topic:
- topic_name: ...
- topic_type: ...

Knowledge card:
- card_id: ...
- relation_type: ...
- semantic_slot: ...
- fact_statement: ...
- answer: ...
- answer_type: ...
- source_span: ...
- aliases: [...]

Requirements:
1. Generate exactly 1 core factual QA.
2. The question must be answerable from the provided card alone.
3. The expected_answer must remain equal to the card answer unless an English equivalent is required.
4. Do not include the expected answer or its aliases in the question text.
5. Do not mention target, neighbor, holdout, benchmark, source span, or Wikipedia in the question.

Return JSON:
{
  "qa_variants": [
    {
      "variant_layer": "core",
      "question": "...",
      "expected_answer": "...",
      "answer_aliases": [],
      "rewrite_note": "direct core question"
    }
  ]
}
```

If surface variants are enabled, change requirement 1 to:

```text
Generate exactly 1 core factual QA and 3 surface variants.
```

---

## 8. 质量检查

生成后至少检查以下项目：

1. 数量检查
   - sampled cards 必须等于 500
   - core QA 必须等于 500
   - 如果开启 surface variants，总 QA 数必须符合配置

2. 泄漏检查
   - question 不能直接包含 `expected_answer`
   - question 不能直接包含高风险 alias

3. 单卡一致性检查
   - QA 的 `relation_type` 必须等于 source card 的 `relation_type`
   - QA 的 `expected_answer` 必须等价于 source card 的 `answer`
   - QA 不能引入 source card 外的新事实

4. 主集隔离检查
   - holdout 的 `source_card_id` 不得出现在 `data/selected_knowledge_card_pairs.json`
   - holdout 的 `qa_id` 不得与主 QA 集 `qa_id` 冲突

5. Provenance 检查
   - 每条 QA 都必须保留 `source_span`
   - 每条 QA 都必须可追溯回 `source_card_id`

---

## 9. 多语言扩展

Holdout 的多语言扩展应在英语 canonical QA 生成之后进行，和主 QA 集一样保持单语平行 probe。

推荐输出：

```text
data/holdout_qa.zh.json
data/holdout_qa.fr.json
data/holdout_qa.es.json
...
```

多语言 holdout QA 不应重新抽样。所有语言都必须共享同一批 500 个 `holdout_card_id`。

多语言版本需要保留：

- `source_qa_id`
- `source_card_id`
- `holdout_card_id`
- `relation_type`
- `expected_answer`
- `source_span`

这样后续可以比较同一 holdout knowledge card 在不同语言上的可访问性。

---

## 10. 推荐执行顺序

建议把 holdout 流程拆成两个可复跑步骤：

```text
Holdout Step A: sample cards
data/knowledge_cards.json
+ data/selected_knowledge_card_pairs.json
-> data/holdout_knowledge_cards.sampled.json

Holdout Step B: generate English QA
data/holdout_knowledge_cards.sampled.json
-> data/holdout_qa.en.json
```

如果后续需要多语言：

```text
Holdout Step C: expand languages
data/holdout_qa.en.json
-> data/holdout_qa.<language>.json
```

---

## 11. 一句话总结

主 QA 集测试 relation-matched Target / Neighbor 边界；holdout QA 集测试剩余知识单元的随机单卡可访问性。

因此 holdout 的关键不是 pair 质量，而是：

- 排除主 QA 已用 cards
- 全局随机抽样
- 单卡生成 QA
- 保持可复现和可追溯
