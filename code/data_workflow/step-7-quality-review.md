# Step 7: 质检与发布筛选

本文档定义最终质检层。Step 7 不负责生成新数据，而负责判断哪些中间产物可以进入最终 benchmark。

---

## 1. Step 7 的目标

Step 7 的核心任务是：

- 检查 topic、knowledge card、pair、English canonical QA、multilingual QA 五层质量
- 检查英语 canonical QA 与各目标语言扩展 QA 的一致性
- 过滤掉不稳定或耦合错误的样本
- 形成可发布、可追溯的最终保留集

---

## 2. 输入与输出

### 2.1 输入

建议至少联合检查以下文件：

- `data/wiki_page_manifest.json`
- `data/wiki_page_content.json`
- `data/knowledge_cards.json`
- `data/knowledge_card_pairs.json`
- `data/selected_knowledge_card_pairs.json`
- `data/qa_variants.en.json`
- 一个或多个 Step 6 单语言输出文件，例如：
- `data/qa_variants.zh.json`
- `data/qa_variants.fr.json`

对于 culture-specific 数据线，应使用带 `.culture_specific` 后缀的对应文件：

- `data/wiki_page_manifest.culture_specific.json`
- `data/wiki_page_content.culture_specific.json`
- `data/knowledge_cards.culture_specific.json`
- `data/selected_knowledge_card_pairs.culture_specific.json`
- `data/qa_variants.en.culture_specific.json`
- `data/qa_variants.<language>.culture_specific.json`

### 2.2 建议输出

建议把 Step 7 的结果分成两类：

- 质检报告，例如 `data/qa_variants.review_report.md`
- 质检后保留集，例如 `data/qa_variants.reviewed.json`

如果后面需要正式发布 benchmark，再从 reviewed 文件导出最终 release 文件。

---

## 3. 五层检查框架

### 3.1 Topic 层

- Target / Neighbor 是否处于同一抽象层级
- `wiki_title` 是否与 topic 语义一致
- 是否错误落到了子页面、子型号、单部作品或局部条目

### 3.2 Knowledge Card 层

- 每张 card 是否只表达一个核心 relation
- `answer` 是否短且边界清楚
- `source_span` 是否直接支持 `fact_statement`
- `relation_type` 与 `semantic_slot` 是否稳定

### 3.3 Pair 层

- target / neighbor 是否来自同一 `pair_id`
- `relation_type` 是否一致
- `answer_type` 是否兼容
- 证据强度是否接近

### 3.4 English Canonical QA 层

- 英语 `core` 是否稳定、直接、可判分
- 英语 `surface` 是否仍然访问同一个知识单元
- QA 是否 answer-aware，即问题语义焦点是否指向 `expected_answer`
- question 是否泄露了 `expected_answer` 或明确 answer alias
- `answer_aliases` 是否只包含与标准答案等价的可接受答案
- 是否从事实题滑向开放式生成题

当前 Step 5 会保留以下 QA 层 warning，Step 7 应抽样或批量处理：

| Warning | 含义 | 建议处理 |
|---|---|---|
| `question_answer_focus_mismatch` | 生成答案与 card answer 不等价，问题可能没有围绕正确 answer 设计 | 优先回退 Step 5；若 card 本身不适合出题，则回退 Step 3/4 |
| `answer_leakage_in_question` | question 中出现 expected answer 或明确答案别名 | 通常应重跑或剔除该 QA |

另外，Step 5 会在生成阶段过滤掉疑似 topic alias、上下文实体或非等价答案的候选别名，不让它们进入自动判分用的 `answer_aliases`。Step 7 仍应对最终 `answer_aliases` 做残余污染检查；若发现 `unsafe_answer_alias` 类问题，优先回退 Step 5，必要时回查 Step 3 aliases。

### 3.5 Multilingual QA 层

- 每条目标语言 QA 是否有对应 `source_qa_id`
- 每个目标语言文件是否只包含该语言 QA
- 每个目标语言文件中的变体是否仍在访问同一个知识单元
- 是否出现 target / neighbor 串扰
- 是否出现 mixed-language / code-switching
- expected answer 是否与目标语言常见表达对齐

---

## 4. 发现问题时的回退路径

Step 7 的职责不是“就地修 prompt”，而是把问题退回正确的 step：

| 问题类型 | 应回退到 |
|---|---|
| page 选错、topic 粒度不对 | Step 1 或 Step 2 |
| card 不是 atomic fact | Step 3 |
| pair relation 没对齐 | Step 4 |
| 英语 canonical QA 访问错知识单元 | Step 5 |
| 英语 QA 题干泄露答案 | Step 5 |
| answer alias 被 topic alias 污染 | Step 5；若源头 aliases 系统性混乱，则 Step 3 |
| 翻译 / 本地化 QA 偏离 source_qa_id | Step 6 |

---

## 5. 推荐执行方式

当前仓库还没有固定的 Step 7 自动化脚本，因此建议先把质检工作拆成两部分：

1. 规则文档
2. 审核结果文件

等规则稳定后，再补自动化检查脚本。这样不会让规则先被脚本绑死，也方便后续逐步收敛标准。

---

## 6. Culture-specific 当前质检记录

当前 culture-specific 数据已经完成两类 QA 层质检：

| 审核类型 | 文件 | 覆盖范围 | 结论 |
|---|---|---|---|
| 启发式抽样质量检查 | `data/qa_variants.culture_specific.sample300_quality_audit.json`、`data/qa_variants.culture_specific.sample300_quality_flags.tsv` | 每个非英语语言抽样 300 条 | 翻译本身整体可用；主要风险集中在 alias 覆盖，不计入翻译质量失败 |
| 第三方 API 翻译质量审核 | `data/qa_translation_quality_review.sample100.culture_specific.json`、`data/qa_translation_quality_review.sample100.culture_specific.tsv` | 每个非英语语言抽样 100 条，共 900 条 | 900 / 900 overall pass；8 minor；0 major |

第三方 API 审核使用 [../review_step6_translation_quality.py](../review_step6_translation_quality.py) 生成，审核时明确忽略 `answer_aliases`，只评价：

- target-language `question` 是否忠实翻译英语 source question。
- target-language `expected_answer` 是否忠实翻译英语 source expected answer。
- 是否保持同一 fact / relation / entity 边界。
- 目标语言是否自然、可用；专名和缩写可保留拉丁写法。

当前 sample100 审核摘要：

```text
sample_size: 900
pass_count: 900
pass_rate: 1.0
severity_counts: ok=892, minor=8, major=0
issue_type_counts: overliteral=4, unnatural=3, mistranslation=1
avg_scores:
  faithfulness_score: 4.999
  answer_accuracy_score: 4.999
  fluency_score: 4.981
  language_purity_score: 5.0
```

这些 `minor` 不阻断当前 release，但应在后续人工 review 或本地化修订时优先查看。Alias 覆盖问题应作为单独的判分/可接受答案边界问题处理，不应混入翻译质量审核。

## 7. 将 pair 质检结果回流到 Step 4

如果 Step 7 发现某些 Step 4 候选或新增 selected pairs 虽然通过了自动分数，但不符合 topic 核心性或 relation 语义，例如：

- 页面中出现的现实影响项被误当成 fictional artifact。
- 边缘角色被误当成 major character。
- trivia 细节被误当成 mission payload / objective。
- answer 文本过泛，无法形成稳定 core QA。
- relation label 与事实语义不一致。

推荐不要手工编辑最终的 `data/knowledge_card_pairs.json`。更可复现的方式是：

1. 在质检报告中记录问题 pair、card、answer 和原因。
2. 将明确不应进入新增 pairs 的候选写入 `data/quality_review_blocklist.json`。
3. 回到 Step 4，使用 `--quality-blocklist` 重跑 pairing。
4. 再次检查 blocklist violation、topic count、review flags 和 Step 5 dry-run。

这样做的好处是：

- 人工判断有明确记录。
- 最终 pair 文件仍由 Step 4 deterministic matcher 生成。
- 后续扩充时可以复用同一批负面约束。
- 已经作为 seed 固定的旧 pairs 不会被 blocklist 意外删除。

当前建议的回流命令形式：

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

注意：blocklist 是质检结果，不是替代 Step 3 的高质量抽卡。如果某个 topic 在过滤后无法补满，优先回到 Step 3 定向扩充对应 relation family，而不是继续放宽 Step 4 阈值。
