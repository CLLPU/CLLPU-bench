# Step 4.5: 从 Pair Pool 中选出高质量 Knowledge Card Pairs

本文档定义 Step 4.5 的职责、数据契约和执行方式。Step 4.5 不重新配对、不新增知识，也不生成 QA；它只负责从 Step 4 已经构造好的高召回 `knowledge_card_pairs.json` 中，确定性选出后续正式使用的固定规模高质量 pair。Common-goals 默认规模是 `500`，culture-specific 数据默认规模是 `300`。

---

## 1. Step 4.5 的目标

Step 4.5 的核心任务是同时满足三个目标：

- 最终总量固定为 `500`
- 优先保留更高 `quality_score` 的 pair
- 每个 `topic pair` 尽量保留 `10` 个；如果个别 topic pair 不足 10 个，则把缺口均匀分配给其他 topic pair

整体流程变为：

```text
Wiki page content
  -> Step 3: knowledge cards
  -> Step 4: relation-matched high-recall pair pool
  -> Step 4.5: fixed-size high-quality pair selection
  -> Step 5: QA variants
```

Step 4 的定位因此更清晰：

- Step 4 负责“尽可能找到足够好的 pair pool”
- Step 4.5 负责“从 pool 中收敛到发布用的固定规模子集”

---

## 2. 输入与输出

### 2.1 输入

默认输入：

```text
data/knowledge_card_pairs.json
```

这个文件是 Step 4 的高召回输出，当前共有 `958` 个 pair。

### 2.2 输出

默认输出：

```text
data/selected_knowledge_card_pairs.json
```

输出保持与 Step 4 兼容的 `topic_pairs -> knowledge_card_pairs` 结构。它的正式用途是作为 Step 5 的唯一输入，直接生成新的英语 canonical QA。

推荐顶层字段包括：

- `step`
- `source_file`
- `selection_config`
- `summary`
- `topic_pairs`

---

## 3. 选择规则

### 3.1 基本约束

- 总数必须恰好为 `500`
- 不跨 `pair_id` 重组 pair，只在 Step 4 已有 pair 中做筛选
- 选中的每条记录保留原始 `knowledge_pair_id`，不重命名

### 3.2 优先级

排序优先级按以下顺序确定：

1. `quality_score` 更高优先
2. `quality_label` 更高优先
3. `review_flags` 更少优先
4. 仍然并列时按 `relation_type` 和 `knowledge_pair_id` 做确定性 tie-break

### 3.3 配额策略

默认目标是：

```text
50 个 topic pair x 每个 10 个 = 500
```

脚本分两阶段：

1. 先给每个 `topic pair` 选最多 `10` 个最高分 pair
2. 如果某个 `topic pair` 不足 `10` 个，则把剩余名额分给其他还有冗余 pair 的 topic pair

### 3.4 缺口补齐策略

缺口补齐不是把所有剩余名额一次性给某一个 topic pair，而是采用：

```text
round-robin overflow fill
```

具体做法：

- 每一轮，每个仍有剩余 pair 的 topic pair 最多只拿到 `1` 个额外名额
- 这一轮的候选按“各 topic 的下一个未入选高分 pair”排序
- 选出当轮需要的前若干个 topic pair

这样可以同时满足：

- 额外名额仍然由高分 pair 主导
- 不会把所有缺口都集中补给同一个 topic pair

当前数据下，只有 `mixed_reality_headsets_2025` 少于 10 个，只有 `8` 个，因此会额外从其他 topic pair 中均匀补 `2` 个名额。

---

## 4. 脚本入口

```bash
python3 code/step4_5_select_high_quality_pairs.py \
  --input data/knowledge_card_pairs.json \
  --output data/selected_knowledge_card_pairs.json \
  --target-total 500 \
  --target-pairs-per-topic 10
```

如需只检查某几个 `pair_id`，可以加：

```bash
python3 code/step4_5_select_high_quality_pairs.py \
  --pair-id mixed_reality_headsets_2025 \
  --pair-id asian_bus_crashes_2025 \
  --target-total 18
```

---

## 5. 输出检查

至少检查：

- `summary.selected_pair_count == 500`
- `summary.topic_pair_count == 50`
- `summary.topic_pairs_below_target_pairs_per_topic_count` 是否合理
- 每个 `topic_pairs[*].stats.selected_pair_count` 是否符合预期
- `overflow_rounds` 是否只在必要时启用

当前默认运行下，预期是：

- 绝大多数 topic pair 选中 `10` 个
- `mixed_reality_headsets_2025` 选中 `8` 个
- 其余缺口通过 overflow fill 补足到总量 `500`

---

## 6. 与 Step 5 的衔接

从现在开始，正式生成 QA 时，推荐把 Step 5 的输入切换为：

```text
data/selected_knowledge_card_pairs.json
```

换句话说，Step 5 的正式输入不再是 Step 4 的高召回 pool，而是 Step 4.5 已经固定好的 500-pair 子集。

---

## 7. Culture-Specific 数据

Culture-specific 数据沿用同一个 Step 4.5 脚本，但使用独立输入输出，并把总量固定为 `300`：

```text
30 topic pairs * 10 pairs = 300 knowledge card pairs
```

为了优先满足“高质量”要求，正式选择使用 Step 4 的 strict pool 作为输入：

```text
data/knowledge_card_pairs.culture_specific.strict.json
```

注意：Step 4 中的 `data/knowledge_card_pairs.culture_specific.json` 是 fixed-15 / coverage-oriented 备选 pool，当前不是正式 Step 5 输入。正式路径优先使用 strict pool，经 Step 4.5 筛出 `300` 个 high-quality pairs 后，再进入 Step 5。

该 strict pool 会排除默认不建议进入主评测的 review flags，例如：

```text
semantic_slot_weak_match
same_answer_text_across_target_neighbor
```

正式 Step 4.5 输出为：

```text
data/selected_knowledge_card_pairs.culture_specific.json
```

运行命令：

```bash
python3 code/step4_5_select_high_quality_pairs.py \
  --input data/knowledge_card_pairs.culture_specific.strict.json \
  --output data/selected_knowledge_card_pairs.culture_specific.json \
  --target-total 300 \
  --target-pairs-per-topic 10
```

当前输出概况：

```text
source_selected_pair_count: 440
selected_pair_count: 300
target_selected_pair_count: 300
selected_quality_label_counts: high=300
selected_review_flag_counts: {}
overflow_pair_count: 5
overflow_round_count: 1
topic_pairs_below_target_pairs_per_topic_count: 1
quality_score_min: 103.0
quality_score_max: 103.0
```

严格过滤后，有一个 topic pair 无法达到每组 10 对：

```text
bn_anti_hindu_violence_national_citizen_party: 5 / 10
```

这个缺口由其他 topic pair 的 next-best high-quality pairs 通过 round-robin overflow fill 补齐，因此最终总数仍是 `300`。这一路的取舍是：

- 优点：选中的 300 对全部是 `quality_label=high`，且没有 selected review flag。
- 代价：topic 间不再严格保持每组 10 对，`bn_anti_hindu_violence_national_citizen_party` 在 strict 过滤后覆盖不足。

如果下游任务更重视每个 topic pair 都固定保留 10 对，可以改用固定覆盖版本：

```bash
python3 code/step4_5_select_high_quality_pairs.py \
  --input data/knowledge_card_pairs.culture_specific.json \
  --output data/selected_knowledge_card_pairs.culture_specific.balanced.json \
  --target-total 300 \
  --target-pairs-per-topic 10
```

固定覆盖版本会得到每组正好 10 对，但当前会保留 `5` 个 `semantic_slot_weak_match` pair，其中：

```text
bn_anti_hindu_violence_national_citizen_party: 5
```

因此，除非后续实验明确要求所有 topic pair 完全均衡，否则 culture-specific 的正式 Step 5 输入应使用：

```text
data/selected_knowledge_card_pairs.culture_specific.json
```
