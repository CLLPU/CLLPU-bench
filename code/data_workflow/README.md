# Benchmark Data Construction Workflow

本文档是当前 benchmark 数据构造流程的总入口。

这里的 workflow 只负责：

- topic pair 到 QA variants 的数据构造
- 中间产物的输入输出契约
- 各 step 的复跑与局部回改边界

它不负责 evaluation metric 设计、评分规则聚合、judge protocol 或最终报告体系。

换句话说，这里讨论的是 `benchmark data construction`，不是整个 benchmark lifecycle。

本文档只回答四件事：

- 每个 step 的目标是什么
- 每个 step 消费哪些输入
- 每个 step 依赖哪些说明文档和脚本
- 如果后期要回改某一层，应该从哪里切入

方法论总述见 [../../research_notes/Unlearning-generation-method.md](../../research_notes/Unlearning-generation-method.md)。

---

## 1. 设计原则

这个 data construction workflow 的目标，是把当前数据构造流程整理成“可执行代码”一样的结构，而不是只保留在长篇说明里。

因此每一步都遵循同一条解耦原则：

```text
同一数据线内，上一步的输出 = 下一步的正式输入
```

只要输入契约不变，就可以单独回改某一步，而不需要从 Step 1 全部重来。

---

## 2. 工作流总表

| Step | 目标 | 主要任务 | 输入数据 | 依赖文档 | 脚本 / 执行入口 | 输出数据 |
|---|---|---|---|---|---|---|
| Step 1 | 固定 Target / Neighbor topic pair | 定义 topic 粒度、Wikipedia canonical page、风险边界 | 无固定机器输入；基于研究设计手动整理 | [step-1-topic-pair-design.md](step-1-topic-pair-design.md)、[topic-pair-summary.md](topic-pair-summary.md)、[culture-specific-topic-pair-summary.md](culture-specific-topic-pair-summary.md) | 暂无固定脚本 | common-goals: [../../data/wiki_page_manifest.json](../../data/wiki_page_manifest.json)；culture-specific: [../../data/wiki_page_manifest.culture_specific.json](../../data/wiki_page_manifest.culture_specific.json) |
| Step 2 | 收集 Wiki 原文 | 从 manifest 抓取页面文本并保留 pair 结构 | common-goals: [../../data/wiki_page_manifest.json](../../data/wiki_page_manifest.json)；culture-specific: [../../data/wiki_page_manifest.culture_specific.json](../../data/wiki_page_manifest.culture_specific.json) | [step-2-wiki-page-collection.md](step-2-wiki-page-collection.md) | [../step2_collect_wiki_pages.py](../step2_collect_wiki_pages.py) | common-goals: [../../data/wiki_page_content.json](../../data/wiki_page_content.json)；culture-specific: [../../data/wiki_page_content.culture_specific.json](../../data/wiki_page_content.culture_specific.json) |
| Step 3 | 抽取 knowledge cards | 为 target / neighbor 分别抽取 atomic facts | common-goals: [../../data/wiki_page_content.json](../../data/wiki_page_content.json)；culture-specific: [../../data/wiki_page_content.culture_specific.json](../../data/wiki_page_content.culture_specific.json) | [step-3-knowledge-card-extraction.md](step-3-knowledge-card-extraction.md)、[../../research_notes/Unlearning-generation-method.md](../../research_notes/Unlearning-generation-method.md) | [../step3_extract_knowledge_cards.py](../step3_extract_knowledge_cards.py) | common-goals: [../../data/knowledge_cards.json](../../data/knowledge_cards.json)；culture-specific: [../../data/knowledge_cards.culture_specific.json](../../data/knowledge_cards.culture_specific.json) |
| Step 4 | 构造 relation-matched pairs | 在同一 pair_id 内做 target / neighbor knowledge card pairing，先得到高召回 pair pool | common-goals: [../../data/knowledge_cards.json](../../data/knowledge_cards.json)；culture-specific: [../../data/knowledge_cards.culture_specific.json](../../data/knowledge_cards.culture_specific.json) | [step-4-relation-matched-card-pairing.md](step-4-relation-matched-card-pairing.md) | [../step4_construct_relation_matched_pairs.py](../step4_construct_relation_matched_pairs.py) | common-goals: [../../data/knowledge_card_pairs.json](../../data/knowledge_card_pairs.json)；culture-specific strict pool: [../../data/knowledge_card_pairs.culture_specific.strict.json](../../data/knowledge_card_pairs.culture_specific.strict.json) |
| Step 4.5 | 选出高质量固定规模 pair | 从 Step 4 的高召回 pair pool 中，优先按 quality score 选择固定规模子集；common-goals 默认 500，culture-specific 正式口径 300 | common-goals: [../../data/knowledge_card_pairs.json](../../data/knowledge_card_pairs.json)；culture-specific: [../../data/knowledge_card_pairs.culture_specific.strict.json](../../data/knowledge_card_pairs.culture_specific.strict.json) | [step-4.5-high-quality-pair-selection.md](step-4.5-high-quality-pair-selection.md) | [../step4_5_select_high_quality_pairs.py](../step4_5_select_high_quality_pairs.py) | common-goals: [../../data/selected_knowledge_card_pairs.json](../../data/selected_knowledge_card_pairs.json)；culture-specific: [../../data/selected_knowledge_card_pairs.culture_specific.json](../../data/selected_knowledge_card_pairs.culture_specific.json) |
| Step 5 | 生成英语 canonical QA variants | 把选中的 paired knowledge 变成 English core / surface probes，而不是新造知识 | common-goals: [../../data/selected_knowledge_card_pairs.json](../../data/selected_knowledge_card_pairs.json)；culture-specific: [../../data/selected_knowledge_card_pairs.culture_specific.json](../../data/selected_knowledge_card_pairs.culture_specific.json) | [step-5-qa-variant-generation.md](step-5-qa-variant-generation.md)、[../../research_notes/Unlearning-generation-method.md](../../research_notes/Unlearning-generation-method.md) | [../step5_generate_qa_variants.py](../step5_generate_qa_variants.py) | common-goals: [../../data/qa_variants.en.json](../../data/qa_variants.en.json)；culture-specific: [../../data/qa_variants.en.culture_specific.json](../../data/qa_variants.en.culture_specific.json) |
| Step 6 | 扩展指定语言 QA | 以英语 canonical QA 为 source，做 translation + localization，并在脚本内自动 back-translation 回测与返工；一次只处理一个目标语言 | common-goals: [../../data/qa_variants.en.json](../../data/qa_variants.en.json)；culture-specific: [../../data/qa_variants.en.culture_specific.json](../../data/qa_variants.en.culture_specific.json) | [step-6-language-expansion.md](step-6-language-expansion.md)、[../../research_notes/Unlearning-generation-method.md](../../research_notes/Unlearning-generation-method.md) | [../step6_expand_qa_translations.py](../step6_expand_qa_translations.py) | common-goals: `data/qa_variants.<language>.json`；culture-specific: `data/qa_variants.<language>.culture_specific.json` |
| Step 7 | 质检与发布筛选 | 检查 topic / card / pair / canonical QA / target-language QA 五层质量 | `data/qa_variants.en.json`、`data/qa_variants.<language>.json` 与上游中间文件 | [step-7-quality-review.md](step-7-quality-review.md)、[../../research_notes/Unlearning-generation-method.md](../../research_notes/Unlearning-generation-method.md) | 暂无固定脚本 | 建议新增 `data/qa_variants.reviewed.json` 或最终发布文件 |
| Step Houldout | 构造 holdout QA | 从未进入主 QA 的剩余 knowledge cards 中随机抽取单卡知识单元，复用 Step 5 / Step 6 规则生成英语与多语言 holdout QA；common-goals 默认 500，culture-specific 当前 300 | [../../data/knowledge_cards.json](../../data/knowledge_cards.json)、[../../data/selected_knowledge_card_pairs.json](../../data/selected_knowledge_card_pairs.json)；culture-specific 使用 `.culture_specific` 输入 | [step-houldout.md](step-houldout.md)、[../../research_notes/holdout-qa-generation.md](../../research_notes/holdout-qa-generation.md) | [../step_holdout_generate_qa.py](../step_holdout_generate_qa.py)、[../step_holdout_expand_qa_translations.py](../step_holdout_expand_qa_translations.py) | common-goals: `data/holdout_knowledge_cards.sampled.json`、`data/holdout_qa.<language>.json`；culture-specific: `data/holdout_knowledge_cards.culture_specific.sampled.json`、`data/holdout_qa.<language>.culture_specific.json` |

---

## 3. Step 1/2 双轨文件地图

当前 common-goals 和 culture-specific 在 Step 1/2 使用同一套 schema 和脚本，但使用不同文件名。

| 数据线 | Step 1 设计说明 | Step 1 输出 manifest | Step 2 输出 content | Step 2 质检摘要 | 当前状态 |
|---|---|---|---|---|---|
| common-goals | [topic-pair-summary.md](topic-pair-summary.md) | [../../data/wiki_page_manifest.json](../../data/wiki_page_manifest.json) | [../../data/wiki_page_content.json](../../data/wiki_page_content.json) | [../../data/wiki_page_content_word_counts.json](../../data/wiki_page_content_word_counts.json) | 符合 post-cutoff 约束 |
| culture-specific | [culture-specific-topic-pair-summary.md](culture-specific-topic-pair-summary.md) | [../../data/wiki_page_manifest.culture_specific.json](../../data/wiki_page_manifest.culture_specific.json) | [../../data/wiki_page_content.culture_specific.json](../../data/wiki_page_content.culture_specific.json) | [../../data/wiki_page_content.culture_specific_word_counts.json](../../data/wiki_page_content.culture_specific_word_counts.json) | `v4` Step 1 已按 post-cutoff 与 culture-specific 风险边界复核；Step 2 已基于当前 manifest 重跑完成 |

约定：

- common-goals 保留默认文件名，兼容既有下游脚本。
- culture-specific 使用 `.culture_specific` 后缀，避免覆盖 common-goals。
- culture-specific 也必须满足 `2024-07-23` 之后出现、发生、发布、立法、生效或显著进入公共语境的 post-cutoff 约束；当前 Step 1 manifest 与 Step 2 content 均已更新为 `v4_post_cutoff_culture_specific_rule_checked` 对应版本。
- 后续新增数据线时，应继续使用 `.<dataset_family>` 后缀。

### 3.1 Common-goals 当前数据快照

当前 common-goals 数据已经从 Step 1 跑通到 Step 6：

| 层级 | 文件 | 当前规模 / 结果 |
|---|---|---|
| Step 1 topic manifest | [../../data/wiki_page_manifest.json](../../data/wiki_page_manifest.json) | 50 topic pairs / 100 pages |
| Step 2 wiki content | [../../data/wiki_page_content.json](../../data/wiki_page_content.json) | 50 topic pairs / 100 pages；word-count min=701, max=11663, total=285032 |
| Step 3 knowledge cards | [../../data/knowledge_cards.json](../../data/knowledge_cards.json) | 2888 cards；target=1457, neighbor=1431 |
| Step 4 high-recall pair pool | [../../data/knowledge_card_pairs.json](../../data/knowledge_card_pairs.json) | 958 selected pairs from 5432 candidates；selected_review_flag_counts=`semantic_slot_partial_match: 39` |
| Step 4.5 selected pairs | [../../data/selected_knowledge_card_pairs.json](../../data/selected_knowledge_card_pairs.json) | 500 selected high-quality pairs；selected_review_flag_counts=`semantic_slot_partial_match: 21` |
| Step 5 English QA | [../../data/qa_variants.en.json](../../data/qa_variants.en.json) | 4000 English canonical QA；warning_count=9 |
| Step 6 multilingual QA | `data/qa_variants.<language>.json` | 9 non-English languages (`ar,bn,de,es,fr,ja,sw,th,zh`)；each 4000 accepted QA；failed_backtranslation_count=0 |
| Step Houldout English QA | [../../data/holdout_qa.en.json](../../data/holdout_qa.en.json) | 500 sampled unused cards -> 500 English core holdout QA；warning_count=0 |
| Step Houldout multilingual QA | `data/holdout_qa.<language>.json` | 9 non-English languages (`ar,bn,de,es,fr,ja,sw,th,zh`)；each 500 accepted QA；failed_backtranslation_count=0 |

### 3.2 Culture-specific 当前数据快照

当前 culture-specific 数据已经从 Step 1 跑通到 Step 6，并完成抽样翻译质量审核：

| 层级 | 文件 | 当前规模 / 结果 |
|---|---|---|
| Step 1 topic manifest | [../../data/wiki_page_manifest.culture_specific.json](../../data/wiki_page_manifest.culture_specific.json) | 30 topic pairs / 60 pages；`design_version = v4_post_cutoff_culture_specific_rule_checked` |
| Step 2 wiki content | [../../data/wiki_page_content.culture_specific.json](../../data/wiki_page_content.culture_specific.json) | 30 topic pairs / 60 pages；word-count min=516, max=11676, total=227826 |
| Step 3 knowledge cards | [../../data/knowledge_cards.culture_specific.json](../../data/knowledge_cards.culture_specific.json) | 1761 cards；target=874, neighbor=887；warning_count=52 |
| Step 4 strict pair pool | [../../data/knowledge_card_pairs.culture_specific.strict.json](../../data/knowledge_card_pairs.culture_specific.strict.json) | 440 high-quality selected pairs from 3583 candidates |
| Step 4.5 selected pairs | [../../data/selected_knowledge_card_pairs.culture_specific.json](../../data/selected_knowledge_card_pairs.culture_specific.json) | 300 selected high-quality pairs；selected_review_flag_counts={} |
| Step 5 English QA | [../../data/qa_variants.en.culture_specific.json](../../data/qa_variants.en.culture_specific.json) | 2400 English canonical QA；warning_count=0 |
| Step 6 multilingual QA | `data/qa_variants.<language>.culture_specific.json` | 9 non-English languages (`ar,bn,de,es,fr,ja,sw,th,zh`)；each 2400 accepted QA；failed_backtranslation_count=0 |
| Step 6 translation review | [../../data/qa_translation_quality_review.sample100.culture_specific.json](../../data/qa_translation_quality_review.sample100.culture_specific.json) | 900 sampled reviews；900 pass；8 minor；0 major |
| Step Houldout English QA | [../../data/holdout_qa.en.culture_specific.json](../../data/holdout_qa.en.culture_specific.json) | 300 sampled unused cards -> 300 English core holdout QA；warning_count=0 |
| Step Houldout multilingual QA | `data/holdout_qa.<language>.culture_specific.json` | 9 non-English languages (`ar,bn,de,es,fr,ja,sw,th,zh`)；each 300 accepted QA；failed_backtranslation_count=0 |

---

## 4. 修改入口

如果后期需要回顾或修改数据，建议按问题所在层级回改，不要直接从头重跑：

| 你要改什么 | 从哪一步开始 |
|---|---|
| topic 选错、粒度不一致、Wikipedia 页面不对 | Step 1 |
| 抓错页面、页面 extract 不完整、page 对齐不正确 | Step 2 |
| 抽出来的 knowledge card 不原子、relation_type 不稳、source_span 不好 | Step 3 |
| target / neighbor 没有对齐、pair 质量差、answer_type 不兼容 | Step 4 |
| 500-pair 子集分配不均、topic 间数量不平衡、同 topic 选得不够优 | Step 4.5 |
| 英语 canonical QA 问法跑偏、surface 不稳定、同一卡被问歪了 | Step 5 |
| 目标语言翻译不自然、expected answer 本地化不好、`source_qa_id` 对齐错误、back-translation 回测未通过 | Step 6 |
| 最终保留集质量不稳、某类错误需要批量过滤 | Step 7 |
| holdout 抽样、holdout 英语 QA 或 holdout 多语言 QA 需要回改 | Step Houldout |

---

## 5. 当前子文档

- [step-1-topic-pair-design.md](step-1-topic-pair-design.md)
- [topic-pair-summary.md](topic-pair-summary.md)
- [culture-specific-topic-pair-summary.md](culture-specific-topic-pair-summary.md)
- [step-2-wiki-page-collection.md](step-2-wiki-page-collection.md)
- [step-3-knowledge-card-extraction.md](step-3-knowledge-card-extraction.md)
- [step-4-relation-matched-card-pairing.md](step-4-relation-matched-card-pairing.md)
- [step-4.5-high-quality-pair-selection.md](step-4.5-high-quality-pair-selection.md)
- [step-5-qa-variant-generation.md](step-5-qa-variant-generation.md)
- [step-6-language-expansion.md](step-6-language-expansion.md)
- [step-7-quality-review.md](step-7-quality-review.md)
- [step-houldout.md](step-houldout.md)

---

## 6. 推荐使用方式

后续协作时，建议把这些文档当作“执行代码”来维护：

- 研究动机、设计原则和 prompt 哲学写在 `research_notes/`
- 具体 step 的输入输出契约、脚本、复跑方式写在 `code/data_workflow/`
- evaluation metric、aggregation、judge rubric 与 report schema 写在 `code/evaluation_workflow/`
- 中间产物全部留在 `data/`

这样修改某个局部时，只需要改对应 step 的文档、脚本和输出文件，不需要重新解释整个项目。
