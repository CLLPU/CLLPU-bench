# Step 4: 构造 Relation-Matched Knowledge Card Pairs

本文档记录如何从 Step 3 的 knowledge card inventory 中构造 Target / Neighbor 的 relation-matched knowledge card pairs。

Step 4 的目标不是继续抽取新知识，也不是生成 QA，而是在同一个 topic pair 内，把 Target 与 Neighbor 中 relation 对齐、答案类型兼容、证据质量足够接近的 cards 组成可用于后续评测的数据单元。

---

## 1. Step 4 的定位

整体流程是：

```text
Wiki page content
  -> Step 3: knowledge cards
  -> Step 4: relation-matched knowledge card pairs
  -> Step 4.5: fixed-size pair selection
  -> Step 5: QA variants
```

Step 4 的核心输出是一组 `knowledge_card_pair`。

每个 pair 表示：

```text
Target topic 的一个 atomic fact
Neighbor topic 的一个 atomic fact
两者共享同一种 relation_type，并且 answer_type / semantic_slot 尽量兼容
```

这样后续做 unlearning evaluation 时，可以稳定比较：

- Target 是否被忘掉
- Neighbor 是否被保留
- Forget / retain 边界是否只影响同 relation 下的目标知识

---

## 2. 输入与输出

### 2.1 输入

默认输入：

```text
data/knowledge_cards.json
```

该文件由 Step 3 生成，核心结构是：

```text
topic_pairs -> target.knowledge_cards
topic_pairs -> neighbor.knowledge_cards
```

Step 4 只在同一个 `pair_id` 内做配对，不跨 topic pair 混配。

### 2.2 输出

默认输出：

```text
data/knowledge_card_pairs.json
```

这里的 `knowledge_card_pairs.json` 现在被视为高召回 pair pool，而不是最终固定发布集。正式进入 Step 5 前，建议先经过 Step 4.5，把 pool 收敛成 `data/selected_knowledge_card_pairs.json`。

推荐结构：

```json
{
  "step": "Step 4 relation-matched knowledge card pairing",
  "source_file": "data/knowledge_cards.json",
  "pairing_config": {
    "target_pairs_per_topic": 20,
    "min_score": 70.0,
    "allow_card_reuse": false,
    "strict_answer_type": false,
    "require_direct_answer_span": true,
    "max_answer_words": 6,
    "excluded_review_flags": [
      "semantic_slot_weak_match",
      "same_answer_text_across_target_neighbor"
    ]
  },
  "summary": {
    "topic_pair_count": 50,
    "candidate_pair_count": 1234,
    "selected_pair_count": 958,
    "selected_review_flag_counts": {
      "semantic_slot_partial_match": 39
    },
    "shortfall_topic_pair_count": 8
  },
  "topic_pairs": [
    {
      "pair_id": "medical_discoveries",
      "topic_type": "medical substance vs medical substance",
      "target_topic": "Penicillin",
      "neighbor_topic": "Insulin",
      "stats": {
        "target_card_count": 30,
        "neighbor_card_count": 23,
        "candidate_pair_count": 96,
        "selected_pair_count": 20
      },
      "knowledge_card_pairs": [
        {
          "knowledge_pair_id": "medical_discoveries__mechanism_or_biological_role__001",
          "relation_type": "mechanism_or_biological_role",
          "quality_score": 92.0,
          "quality_label": "high",
          "target": {
            "topic_name": "Penicillin",
            "card": {
              "card_id": "...",
              "fact_statement": "...",
              "answer": "...",
              "source_span": "..."
            }
          },
          "neighbor": {
            "topic_name": "Insulin",
            "card": {
              "card_id": "...",
              "fact_statement": "...",
              "answer": "...",
              "source_span": "..."
            }
          }
        }
      ]
    }
  ]
}
```

---

## 3. 配对原则

### 3.1 必要条件

一对 cards 必须满足：

- 来自同一个 `pair_id`
- 一个来自 `target.knowledge_cards`
- 一个来自 `neighbor.knowledge_cards`
- `relation_type` 完全一致
- `card_type` 是 `atomic_fact`
- `knowledge_scope` 是 `atomic`
- `answer_type` 完全一致或属于兼容类型族

### 3.2 推荐条件

高质量 pair 还应满足：

- `semantic_slot` 完全一致或高度相近
- 两边的 `answer` 都能在各自 `source_span` 中直接定位
- 两边的 `eval_priority` 都是 `high` 或至少不是 `low`
- 两边的事实粒度相近，都是短答案事实
- 两边都不是解释型、评价型或多事实混合型 knowledge

### 3.3 不推荐的 pair

以下情况应降权或剔除：

- 只有 `relation_type` 一致，但 `semantic_slot` 明显不同
- `answer_type` 不兼容，例如 `person` 对 `location`
- `source_span` 找不到或证据不直接
- Target 与 Neighbor 的答案是同一个字符串，且容易让后续 retain 判断失真
- 一个 card 被重复配给多个 card，除非明确开启 `allow_card_reuse`

主评测默认会直接排除：

- `semantic_slot_weak_match`
- `same_answer_text_across_target_neighbor`

原因是这两类 pair 会削弱 boundary control：前者虽然 relation 大类一致，但 target / neighbor 实际问的语义槽不同；后者会让 forget 与 retain 的标准答案重叠，导致 neighbor preservation 的解释变钝。`semantic_slot_partial_match` 默认保留，但会在 summary 中显式统计，供 Step 7 抽样复核。

---

## 4. Answer Type 兼容规则

默认不要求 `answer_type` 字符串完全一致，因为 Step 3 中可能出现细粒度写法差异。

例如以下可以视为兼容：

```text
person ~ people ~ artist ~ scientist
date ~ year
location ~ place ~ country ~ city ~ site
organization ~ company ~ agency ~ institution
disease_or_medical_condition ~ disease_or_condition ~ medical_condition
fictional_object ~ vehicle ~ spacecraft ~ payload
concept ~ term ~ fictional_concept ~ cosmology_term
```

若希望更保守，可以运行时开启：

```bash
--strict-answer-type
```

这会要求 normalized `answer_type` 完全一致。

---

## 5. 配对算法

默认脚本采用确定性规则，不调用 LLM。

算法流程：

1. 对每个 `pair_id` 单独处理
2. 按 `relation_type` 将 neighbor cards 分桶
3. 对每张 target card，只和同 relation bucket 下的 neighbor cards 组成候选
4. 检查 `answer_type` 是否兼容
5. 为每个候选 pair 计算质量分
6. 按质量分排序
7. 贪心选择 pair，默认每张 card 最多使用一次
8. 每个 topic pair 最多保留 `target_pairs_per_topic` 个 pair

这样做的好处是：

- 可复现
- 不依赖 API
- topic 数量变化后仍然可以批量运行
- 后续可以在候选结果上叠加人工或 LLM review

---

## 6. Scoring 规则

默认分数主要由以下部分组成：

| 项 | 作用 |
|---|---|
| `relation_type` 一致 | 必要条件，不一致则不进入候选 |
| `answer_type` exact match | 强加分 |
| `answer_type` family match | 中等加分 |
| `semantic_slot` 相似度 | 完全一致或 token overlap 越高越好 |
| answer 是否在 source_span 中 | 两边都能定位则加分，否则降权 |
| `eval_priority` | `high` 优先 |
| Target / Neighbor answer 完全相同 | 轻微降权，并加 review flag |

输出中每个 pair 会包含：

- `quality_score`
- `quality_label`
- `review_flags`
- `answer_type_match`
- `semantic_slot_similarity`

输出 summary 还会汇总：

- `candidate_review_flag_counts`
- `selected_review_flag_counts`
- `shortfall_topic_pairs`

推荐解释：

```text
quality_label = high
  可以优先进入 Step 5

quality_label = medium
  通常可用，但建议抽样检查

quality_label = review
  不建议直接进入主评测，适合作为备选池
```

---

## 7. 数量策略

当前 Step 3 已经把每个 topic 扩到约 30 张 cards。

Step 4 默认目标是：

```text
每个 topic pair 保留 20 个 relation-matched knowledge card pairs
```

对应脚本参数：

```bash
--target-pairs-per-topic 20
```

如果后续 topic pair 数量变多，可以保持这个参数不变，让总数据规模线性增长。

如果某些 topic pair 的高质量 pair 不足 20，不建议强行补满。应保留真实数量，并在 summary 中记录。

---

## 8. 可执行脚本

脚本路径：

```text
code/step4_construct_relation_matched_pairs.py
```

默认运行：

```bash
python3 code/step4_construct_relation_matched_pairs.py \
  --input data/knowledge_cards.json \
  --output data/knowledge_card_pairs.json
```

当前默认等价于主评测的严格筛选：

```bash
python3 code/step4_construct_relation_matched_pairs.py \
  --input data/knowledge_cards.json \
  --output data/knowledge_card_pairs.json \
  --target-pairs-per-topic 20 \
  --min-score 70 \
  --require-direct-answer-span \
  --max-answer-words 6 \
  --exclude-review-flag semantic_slot_weak_match \
  --exclude-review-flag same_answer_text_across_target_neighbor
```

如果临时做探索分析，可以用 `--allow-default-review-flags` 取消默认 review-flag 排除；主评测不建议这样做。

只跑单个 topic pair：

```bash
python3 code/step4_construct_relation_matched_pairs.py \
  --pair-id medical_discoveries
```

更严格的版本：

```bash
python3 code/step4_construct_relation_matched_pairs.py \
  --strict-answer-type \
  --min-score 78 \
  --target-pairs-per-topic 20
```

探索更多候选：

```bash
python3 code/step4_construct_relation_matched_pairs.py \
  --target-pairs-per-topic 30 \
  --min-score 65
```

默认不复用 card。如果想允许一张 card 进入多个 pair，可以开启：

```bash
--allow-card-reuse
```

主评测默认不建议开启 card reuse，因为它会让后续 QA variants 之间产生重复知识依赖。

---

## 9. 质检建议

Step 4 完成后建议检查：

- 每个 `pair_id` 是否有接近 20 个 selected pairs
- 每个 pair 的 `relation_type` 分布是否过度集中
- `quality_label=review` 的比例是否过高
- `review_flags` 是否集中在某个 topic 或 relation
- `summary.selected_review_flag_counts` 是否只剩下可接受的部分匹配项
- `summary.shortfall_topic_pairs` 是否由质量过滤造成，而不是 topic/page 选错

推荐先用默认脚本生成一版，再查看 summary。

如果某个 topic pair 结果偏少，优先回到 Step 3 增加该 topic pair 中对应 relation family 的抽卡数量，而不是在 Step 4 放宽到低质量匹配。

---

## 10. 固定旧 pairs 后扩充新 pairs

如果数据集已经有一版稳定的 `knowledge_card_pairs.json`，后续只想扩充新增 pairs，而不想重排或替换旧 pairs，可以使用 seed 模式。

seed 模式的含义是：

- 先读取旧版 Step 4 输出。
- 对每个 `pair_id` 保留旧版已选中的 pairs。
- 新选择只填补 `--target-pairs-per-topic` 与 seed 数量之间的差额。
- 新增 pairs 会避开 seed 中已经用过的 card id、relation-answer identity 和 fact statement。

典型用法：

```bash
python3 code/step4_construct_relation_matched_pairs.py \
  --input data/knowledge_cards.json \
  --output data/knowledge_card_pairs.json \
  --target-pairs-per-topic 35 \
  --min-score 70 \
  --seed-pairs data/original_knowledge_card_pairs.json
```

为了让新增 pairs 更适合后续 core QA，扩充时建议同时开启：

```bash
--require-direct-answer-span
--max-answer-words 6
```

其中：

- `--require-direct-answer-span` 要求新增 pair 两侧 answer 都能在各自 `source_span` 中直接定位。
- `--max-answer-words` 限制新增 pair 的 answer 长度；seed pairs 不受影响。

### 10.1 质检 blocklist

Step 4 的自动分数只能检查 relation、answer type、semantic slot、source span 等结构信号，不能完全判断 topic 核心性。人工 Step 7 质检发现的坏候选，可以写入 blocklist，再回流到 Step 4 重跑。

当前 blocklist 文件示例：

```text
data/quality_review_blocklist.json
```

支持的过滤粒度包括：

- `blocked_cards`：按 `pair_id`、`role`、`card_id` 排除某张 card。
- `blocked_answers`：按 `pair_id`、`role`、`answer` 排除某个答案文本。
- `blocked_pair_card_combinations`：排除某个 target card 与 neighbor card 的具体组合。
- `blocked_relations`：排除某个 `pair_id` 下的整个 relation。

运行示例：

```bash
python3 code/step4_construct_relation_matched_pairs.py \
  --input data/knowledge_cards.json \
  --output data/knowledge_card_pairs.json \
  --target-pairs-per-topic 35 \
  --min-score 70 \
  --seed-pairs data/original_knowledge_card_pairs.json \
  --require-direct-answer-span \
  --max-answer-words 6 \
  --quality-blocklist data/quality_review_blocklist.json
```

blocklist 只影响新增选择，不会删除或改写 seed pairs。这样可以保持已发布数据稳定，同时让后续扩充具备可复现的人工质检回流路径。

---

## 11. 后续可增强方向

当前脚本是 deterministic matcher，适合作为可复跑 baseline。

后续可以加两个增强层：

1. LLM review

输入候选 pair，让模型判断：

- 两边是否真的是同一种 semantic_slot
- 是否都可以生成同结构 QA
- 是否存在 topic 粒度不一致

2. relation quota balancing

避免某个 relation family 占满 20 个 pairs。

例如：

```text
major_characters 最多 5 对
signature_terms 最多 4 对
creator / founded_year 等 singleton relation 最多 1 对
```

这会让最终 benchmark 覆盖更均衡，但也可能降低每个 topic pair 的总 pair 数。

---

## 12. 推荐默认方案

当前阶段建议先采用：

```bash
python3 code/step4_construct_relation_matched_pairs.py \
  --input data/knowledge_cards.json \
  --output data/knowledge_card_pairs.json
```

然后检查：

```text
data/knowledge_card_pairs.json -> summary
data/knowledge_card_pairs.json -> topic_pairs[*].stats
data/knowledge_card_pairs.json -> knowledge_card_pairs[*].review_flags
```

如果大多数 topic pair 能达到目标覆盖、`review` 比例可控，就说明 Step 4 的高召回 pool 已经可用。下一步应进入 Step 4.5 做固定规模筛选，再把选中的 500 个 pair 送入 Step 5 生成 QA variants。

---

## 13. Culture-Specific 数据

新增的 culture-specific 数据使用独立 Step 3 输出：

```text
data/knowledge_cards.culture_specific.json
```

对应 Step 4 输出为：

```text
data/knowledge_card_pairs.culture_specific.json
```

Culture-specific 的 Step 4 目标是先构造一个足够大的 relation-matched pair pool，而不是直接决定正式 Step 5 输入。当前有两种可复跑输出：

- strict pool：质量优先，输出到 `data/knowledge_card_pairs.culture_specific.strict.json`，供正式 Step 4.5 选择。
- fixed-15 pool：覆盖优先，输出到 `data/knowledge_card_pairs.culture_specific.json`，作为需要每个 topic pair 固定 15 对时的备选。

如果采用 fixed-15 pool，则每个 topic pair 构造 `15` 个 relation-matched knowledge card pairs。该数量不同于 common-goals 默认的 `20`，因为 culture-specific 共有 `30` 个 topic pairs，对应总量为：

```text
30 topic pairs * 15 pairs = 450 knowledge card pairs
```

### 13.1 严格质量优先版本

如果优先保证严格匹配质量，可以先运行：

```bash
python3 code/step4_construct_relation_matched_pairs.py \
  --input data/knowledge_cards.culture_specific.json \
  --output data/knowledge_card_pairs.culture_specific.strict.json \
  --target-pairs-per-topic 15 \
  --min-score 70 \
  --require-direct-answer-span \
  --max-answer-words 6
```

这一路仍沿用主评测默认的 review-flag 排除逻辑，会排除：

```text
semantic_slot_weak_match
same_answer_text_across_target_neighbor
```

Step 4 matcher 会先规范化 `semantic_slot`：如果槽位写成 `topic title -> slot name`，只用右侧的 `slot name` 计算相似度。这样可以避免 culture-specific 抽卡中带 topic 前缀的槽位被误判成 `semantic_slot_weak_match`。

在当前 culture-specific cards 上，严格版本可选出 `440 / 450` 对；短缺集中在：

```text
bn_anti_hindu_violence_national_citizen_party: 5 / 15
```

如果不强制每组正好 15 对，严格版本更适合作为质量优先的候选池。使用独立 `.strict.json` 文件可以避免覆盖固定 15 对版本。

### 13.2 固定 15 对版本

如果下游 Step 5 需要每个 topic pair 固定 `15` 对，当前采用以下运行方式：

```bash
python3 code/step4_construct_relation_matched_pairs.py \
  --input data/knowledge_cards.culture_specific.json \
  --output data/knowledge_card_pairs.culture_specific.json \
  --target-pairs-per-topic 15 \
  --min-score 65 \
  --require-direct-answer-span \
  --max-answer-words 6 \
  --allow-default-review-flags
```

该版本的当前输出概况：

```text
topic_pair_count: 30
candidate_pair_count: 3583
selected_pair_count: 450
shortfall_topic_pair_count: 0
quality_label=high: 440
quality_label=medium: 10
selected_review_flag semantic_slot_weak_match: 10
```

`semantic_slot_weak_match` 集中在一个 topic pair：

```text
bn_anti_hindu_violence_national_citizen_party: 10
```

这 10 对可以进入 fixed-15 备选版本，但在进入 Step 5 / Step 7 前应优先人工复核。复核重点是：

- target 与 neighbor 是否确实在比较同一类事实，而不只是 `relation_type` 大类相同。
- 两边 answer 是否都能从各自 `source_span` 中直接定位。
- fact 的发生时间或内容主体是否仍在 `2024-07-23` 之后。
- 是否出现了旧背景事实、政治立场、价值判断或解释型描述。

`--allow-default-review-flags` 是 culture-specific fixed-15 备选版本的补齐策略，不应替代 common-goals 主评测的默认严格配置，也不应替代 culture-specific 当前正式 Step 5 输入。当前 culture-specific 正式路径是：

```text
data/knowledge_card_pairs.culture_specific.strict.json
-> Step 4.5
-> data/selected_knowledge_card_pairs.culture_specific.json
-> Step 5
```

因此，正式 Step 5 使用的是 Step 4.5 strict-selected 的 `300` 个 pairs，而不是 fixed-15 pool 的 `450` 个 pairs。如果后续重新抽取 cards 后 strict pool 也能达到每组 15 对，可以再评估是否把 strict pool 的上限提高；在此之前，`450` 版本只作为覆盖优先的备选口径。
