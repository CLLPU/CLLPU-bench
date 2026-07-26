# Step 2: 收集 Wiki 原文

本文档记录如何从 Step 1 的 topic-pair manifest 出发，抓取 Wikipedia 纯文本正文，并生成后续 Step 3 可直接消费的页面内容文件。

当前 Step 2 同时支持两条数据线：

- `common-goals`
- `culture-specific`

两条数据线使用同一个脚本 [../step2_collect_wiki_pages.py](../step2_collect_wiki_pages.py)，但必须使用不同的输入输出文件。运行 culture-specific 时不要使用默认输出路径，否则会覆盖 common-goals 的已有结果。

---

## 1. Step 2 的目标

Step 2 的核心任务不是“随便抓一些百科文本”，而是：

- 按 Step 1 manifest 固定每个 topic 对应的 canonical Wikipedia 页面。
- 确保 target / neighbor 保留在同一个 `pair_id` 下。
- 把页面原文保存为后续 Step 3 可直接使用的结构化输入。
- 保留 `pair_id -> target / neighbor -> page_content` 的层级结构，避免后续重新分组。

Step 2 不重新设计 topic pair；如果页面选择或 topic 粒度有问题，应回到 Step 1 修改 manifest。

---

## 2. 输入与输出文件

| 数据线 | Step 2 输入 manifest | Step 2 输出 content | 质检摘要 | 当前规模 | 当前状态 |
|---|---|---|---|---:|---|
| common-goals | [../../data/wiki_page_manifest.json](../../data/wiki_page_manifest.json) | [../../data/wiki_page_content.json](../../data/wiki_page_content.json) | [../../data/wiki_page_content_word_counts.json](../../data/wiki_page_content_word_counts.json) | 50 pairs / 100 pages | 符合 post-cutoff 约束 |
| culture-specific | [../../data/wiki_page_manifest.culture_specific.json](../../data/wiki_page_manifest.culture_specific.json) | [../../data/wiki_page_content.culture_specific.json](../../data/wiki_page_content.culture_specific.json) | [../../data/wiki_page_content.culture_specific_word_counts.json](../../data/wiki_page_content.culture_specific_word_counts.json) | 30 pairs / 60 pages | 已基于 `v4_post_cutoff_culture_specific_rule_checked` manifest 重跑完成 |

命名约定：

- common-goals 使用默认文件名：`data/wiki_page_content.json`
- culture-specific 使用后缀文件名：`data/wiki_page_content.culture_specific.json`

后续新增数据线时，应继续使用显式后缀，例如 `data/wiki_page_content.<dataset_family>.json`。

注意：culture-specific 也必须满足 `2024-07-23` 之后出现、发生、发布、立法、生效或显著进入公共语境的 topic 时间边界。当前 culture-specific Step 1 manifest 和 Step 2 content 均已更新到 `v4_post_cutoff_culture_specific_rule_checked` 对应版本；若后续替换任一 topic，必须同步重跑对应 content 与 word-count 摘要。

---

## 3. 输入 manifest 契约

Step 2 的输入是 Step 1 的 manifest。每个 manifest 至少需要：

- 顶层 `topic_pairs` 列表。
- 每个 pair 有 `pair_id` 和 `topic_type`。
- 每个 pair 有 `target` 与 `neighbor`。
- `target.role` 必须是 `target`。
- `neighbor.role` 必须是 `neighbor`。
- `target` 与 `neighbor` 都必须有 `topic_zh`、`topic_en`、`wiki_title`、`wiki_url`。

最小输入单元示例：

```json
{
  "pair_id": "medical_discoveries",
  "topic_type": "medical substance vs medical substance",
  "target": {
    "role": "target",
    "topic_zh": "青霉素",
    "topic_en": "Penicillin",
    "wiki_title": "Penicillin",
    "wiki_url": "https://en.wikipedia.org/wiki/Penicillin"
  },
  "neighbor": {
    "role": "neighbor",
    "topic_zh": "胰岛素",
    "topic_en": "Insulin",
    "wiki_title": "Insulin",
    "wiki_url": "https://en.wikipedia.org/wiki/Insulin"
  }
}
```

Culture-specific manifest 可以额外包含 `primary_language`、`affected_languages`、`sensitivity_type`、`qa_guardrail` 等字段。Step 2 当前不会强依赖这些字段，但应在 manifest 中保留，方便后续审查和标签继承。

---

## 4. 输出 content 契约

Step 2 的输出是 topic-pair-level 的页面内容文件，而不是扁平页面列表。

推荐层级：

```text
topic_pairs -> target / neighbor -> page_content
```

输出结构示例：

```json
{
  "step": "step_2_collect_wiki_pages",
  "source_language": "en",
  "source_site": "English Wikipedia",
  "based_on_manifest": "data/wiki_page_manifest.json",
  "topic_pairs": [
    {
      "pair_id": "medical_discoveries",
      "topic_type": "medical substance vs medical substance",
      "target": {
        "role": "target",
        "topic_zh": "青霉素",
        "topic_en": "Penicillin",
        "wiki_title": "Penicillin",
        "wiki_url": "https://en.wikipedia.org/wiki/Penicillin",
        "page_id": 23312,
        "page_content": "Penicillins are a group of beta-lactam antibiotics ...",
        "word_count": 5200
      },
      "neighbor": {
        "role": "neighbor",
        "topic_zh": "胰岛素",
        "topic_en": "Insulin",
        "wiki_title": "Insulin",
        "wiki_url": "https://en.wikipedia.org/wiki/Insulin",
        "page_id": 17147,
        "page_content": "Insulin is a peptide hormone produced by beta cells ...",
        "word_count": 4800
      }
    }
  ]
}
```

关键字段：

- `based_on_manifest`：记录本次抓取使用的 manifest 路径。
- `wiki_title`：Wikipedia API 实际解析后的 canonical title。
- `page_id`：Wikipedia page id。
- `page_content`：Step 3 的正文输入。
- `word_count`：用于发现页面过短或异常抓取。

---

## 5. 页面选择原则

Step 2 必须严格执行 Step 1 已经确定的页面选择。

### 5.1 必须使用 manifest 中的 wiki title

默认以 manifest 中的 `wiki_title` 作为抓取入口。不要在 Step 2 阶段临时把：

- franchise 改成某一部作品
- company 改成某个单独产品
- mythology system 改成某个神祇页面
- local risk topic 改成 broader page 的 section

否则会破坏后续 target / neighbor 的抽象层级一致性。

### 5.2 Target / Neighbor 必须保持 pair 结构

Step 2 在实际抓取前，应检查：

- `target` 与 `neighbor` 是否都存在。
- 两者是否都有 `wiki_title`。
- 两者的 topic 类型是否仍然匹配当前 pair 的粒度。
- 输出中是否仍在同一个 `pair_id` 下并列保存。

### 5.3 允许 Wikipedia redirect，但不允许改变语义层级

Wikipedia API 可能会把请求标题重定向到 canonical title。这是允许的。

但若 redirect 结果明显落到错误层级，例如从公司页跳到某个产品页，或从独立 topic 跳到 broader page 的不相关主题，应视为异常并人工复核 Step 1 manifest。

---

## 6. 抓取策略

### 6.1 使用 Wikipedia API，而不是页面 HTML

Step 2 使用 Wikipedia API 获取纯文本 extract。

接口：

```text
https://en.wikipedia.org/w/api.php
```

参数：

- `action=query`
- `prop=extracts`
- `explaintext=1`
- `redirects=1`
- `format=json`
- `titles=<wiki_title>`

这样得到的是适合 Step 3 抽取的纯文本正文，噪声比直接抓 HTML 更低。

### 6.2 保留页面级元信息

输出中必须保留：

- `wiki_title`
- `wiki_url`
- `page_id`
- `page_content`
- `word_count`

其中 `wiki_title` 是 Wikipedia API 解析后的实际标题；如果它与 manifest 中请求标题不同，应判断是否只是正常 canonical redirect。

---

## 7. 运行命令

### 7.1 Common-goals

common-goals 使用默认输入输出：

```bash
python3 code/step2_collect_wiki_pages.py
```

等价于：

```bash
python3 code/step2_collect_wiki_pages.py \
  --input data/wiki_page_manifest.json \
  --output data/wiki_page_content.json
```

### 7.2 Culture-specific

culture-specific 必须显式指定输入输出。当前 [../../data/wiki_page_manifest.culture_specific.json](../../data/wiki_page_manifest.culture_specific.json) 已经按 post-cutoff 与 culture-specific 风险边界更新为 v4；[../../data/wiki_page_content.culture_specific.json](../../data/wiki_page_content.culture_specific.json) 已使用该 manifest 重新抓取完成。后续如果 Step 1 有变化，应使用同一命令刷新 content：

```bash
python3 code/step2_collect_wiki_pages.py \
  --input data/wiki_page_manifest.culture_specific.json \
  --output data/wiki_page_content.culture_specific.json \
  --sleep-seconds 0.1 \
  --max-retries 3 \
  --timeout 30
```

### 7.3 只处理部分 pair

两条数据线都可以用 `--pair-id` 限定局部抓取：

```bash
python3 code/step2_collect_wiki_pages.py \
  --input data/wiki_page_manifest.culture_specific.json \
  --output /private/tmp/wiki_page_content_subset.json \
  --pair-id zh_shenzhen_stabbing_wuxi_stabbing
```

局部测试建议输出到 `/private/tmp`，确认无误后再写回正式 content 文件。

### 7.4 控制抓取节奏

```bash
python3 code/step2_collect_wiki_pages.py \
  --input data/wiki_page_manifest.json \
  --output data/wiki_page_content.json \
  --sleep-seconds 0.2 \
  --max-retries 3 \
  --timeout 30
```

---

## 8. 质量检查

在生成正式 content 文件前后，至少做以下检查。

### 8.1 输入检查

- `topic_pairs` 是否存在且为列表。
- 每个条目是否都有 `pair_id`。
- 每个条目是否都有 `target` 和 `neighbor`。
- `target.wiki_title` 与 `neighbor.wiki_title` 是否非空。
- `target.role` 是否为 `target`。
- `neighbor.role` 是否为 `neighbor`。

### 8.2 抓取检查

- API 是否成功返回 JSON。
- 返回页面是否含有 `extract`。
- `extract` 是否非空。
- `pageid` 是否存在。
- 实际返回标题是否与预期语义一致。

### 8.3 输出检查

- 每个 `pair_id` 下是否同时存在 `target` 和 `neighbor`。
- `target.page_content` 与 `neighbor.page_content` 是否都非空。
- 输出 JSON 是否可被正常解析。
- 输出是否仍然保留原始 pair 层级。
- `based_on_manifest` 是否指向对应数据线的 manifest。

### 8.4 当前已生成结果

当前文件状态：

- common-goals：[../../data/wiki_page_content.json](../../data/wiki_page_content.json)
  - 50 pairs / 100 pages
  - word-count 摘要：[../../data/wiki_page_content_word_counts.json](../../data/wiki_page_content_word_counts.json)
- culture-specific：[../../data/wiki_page_content.culture_specific.json](../../data/wiki_page_content.culture_specific.json)
  - 30 pairs / 60 pages
  - word-count 摘要：[../../data/wiki_page_content.culture_specific_word_counts.json](../../data/wiki_page_content.culture_specific_word_counts.json)
  - based_on_manifest: [../../data/wiki_page_manifest.culture_specific.json](../../data/wiki_page_manifest.culture_specific.json)
  - total_word_count: 227826
  - min_word_count: 516
  - max_word_count: 11676
  - 当前文件已基于 `v4_post_cutoff_culture_specific_rule_checked` manifest 重跑完成，可作为 culture-specific Step 3 的正式输入。

---

## 9. 当 Step 1 变化时如何复用

后续如果 Step 1 的 topic pair 有改变，Step 2 不需要重写方法，只需要：

1. 修改对应数据线的设计文档。
2. 同步对应数据线的 manifest。
3. 确认新的 `wiki_title` 和 `wiki_url` 已经对齐。
4. 用对应输入输出路径重新运行 [../step2_collect_wiki_pages.py](../step2_collect_wiki_pages.py)。
5. 更新对应数据线的 word-count 质检摘要。

对应关系：

| 数据线 | 修改设计 | 更新 manifest | 重跑 content |
|---|---|---|---|
| common-goals | [topic-pair-summary.md](topic-pair-summary.md) | [../../data/wiki_page_manifest.json](../../data/wiki_page_manifest.json) | [../../data/wiki_page_content.json](../../data/wiki_page_content.json) |
| culture-specific | [culture-specific-topic-pair-summary.md](culture-specific-topic-pair-summary.md) | [../../data/wiki_page_manifest.culture_specific.json](../../data/wiki_page_manifest.culture_specific.json) | [../../data/wiki_page_content.culture_specific.json](../../data/wiki_page_content.culture_specific.json) |

---

## 10. 常见失败场景

### 10.1 页面抓取失败

可能原因：

- 网络不可用。
- Wikipedia API 暂时不可达。
- 请求过快被限制。
- `wiki_title` 填写错误。

处理方式：

- 先重试。
- 降低抓取频率。
- 检查 `wiki_title`。
- 人工确认该页面在英文 Wikipedia 中是否存在。

### 10.2 页面内容不符合 topic 粒度

可能原因：

- Step 1 的 manifest 选错了页面。
- redirect 落到了不合适的页面。
- culture-specific topic 被误写成 section-only topic。

处理方式：

- 回到对应数据线的 Step 1 设计文档修正 topic。
- 同步对应 manifest 中的 `wiki_title` 和 `wiki_url`。
- 重新运行 Step 2。

### 10.3 输出结构不便于 Step 3

若输出被写成扁平列表，Step 3 和 Step 4 会多做一次 regroup。推荐始终坚持：

```text
topic_pairs -> target / neighbor -> page_content
```

不要改成：

```text
pages -> [ ... ]
```

---

## 11. 下一步

Step 2 content 文件是 Step 3 的正式输入：

```text
Step 1 manifest
-> Step 2 wiki page content
-> Step 3 knowledge card extraction
```

当前 common-goals 的 Step 3 输入是 [../../data/wiki_page_content.json](../../data/wiki_page_content.json)。culture-specific 的 Step 3 输入是 [../../data/wiki_page_content.culture_specific.json](../../data/wiki_page_content.culture_specific.json)，并继续使用独立输出命名，避免覆盖 common-goals 的 `knowledge_cards.json`。
