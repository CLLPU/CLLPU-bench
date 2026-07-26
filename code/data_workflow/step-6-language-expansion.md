# Step 6: 指定语言直译扩展

本文档定义 Step 6 的职责、数据契约和执行方式。Step 6 负责把 Step 5 生成的英语 canonical QA 扩展成某一个指定目标语言的平行单语 QA；它不重新生成 canonical QA，不重新配对，也不负责最终发布筛选。

这里的关键约束是：

- 一次 Step 6 调用只处理一个目标语言
- 每次调用输出一个该语言独立的 QA 文档
- 如果要扩展到多个语言，就重复调用 Step 6 多次

这样可以避免把多个目标语言耦合到同一个 `multilingual.json` 文件中。

---

## 1. Step 6 的目标

Step 6 的核心任务是：

- 以英语 canonical QA 为唯一上游输入
- 将英语 `core` / `surface` QA 扩展到一个指定目标语言
- 保持每条翻译后的 QA 与其英语 source QA 在 fact、relation、variant layer 上完全对齐
- 把英语 canonical QA 的 `question`、`expected_answer`、`answer_aliases` 保守直译到目标语言
- 只允许最小必要本地化，例如采用目标语言里已经稳定存在的实体名或术语译法
- 在 Python 脚本中自动执行 back-translation 回测：目标语言 QA 再翻回英文，并与 source QA 做一致性检查
- 对回测不一致的条目自动返工，直到通过质量 gate 或达到最大重试次数

Step 6 的目的不是让每种语言重新“发明”一套 QA，而是围绕同一条英语 canonical QA 生成平行单语版本。

这里的回测与返工必须由 `code/step6_expand_qa_translations.py` 自动完成，不依赖 Codex 在生成过程中逐条判断。Codex 可以在完整文件生成后做最后抽查和把关，但不应成为 Step 6 主循环的一部分。

---

## 2. 输入与输出

### 2.1 输入

默认输入：

```text
data/qa_variants.en.json
```

其中每条英语 QA 都已经固定：

- `qa_id`
- `knowledge_pair_id`
- `card_id`
- `topic_role`
- `variant_layer`
- `language = en`
- `question`
- `expected_answer`
- `answer_aliases`

Step 6 也会使用同一 `knowledge_card_pair` 中保留的 card context，但它只用于消歧和选择既有标准译名，不用于扩写答案集合，也不用于把 raw card aliases 混入最终 QA。

### 2.2 输出

每次 Step 6 只输出一个目标语言文件。默认命名建议为：

```text
data/qa_variants.<language>.json
```

例如：

- 中文：`data/qa_variants.zh.json`
- 法语：`data/qa_variants.fr.json`

推荐结构仍然保持：

```text
topic_pairs
  -> knowledge_card_pairs
    -> target_qa_variants
    -> neighbor_qa_variants
```

但这个输出文件中只包含当前目标语言的 QA，不再混入：

- 其他目标语言 QA
- 英语 canonical QA

英语 canonical QA 仍然单独保存在 Step 5 的输出 `data/qa_variants.en.json` 中。Step 6 输出通过 `source_qa_id` 和 `source_file` 回链到英文 source。

每条目标语言 QA 建议新增：

- `source_qa_id`
- `source_language = en`
- `generation_stage = translated_from_canonical_en`
- `translation_status = accepted`
- `backtranslation_status = passed`
- `backtranslation_en`
- `backtranslation_consistency`
- `translation_attempts`

脚本入口：

```bash
python3 code/step6_expand_qa_translations.py \
  --input data/qa_variants.en.json \
  --language zh \
  --output data/qa_variants.zh.json
```

如果要扩展多个语言，则分别调用：

```bash
python3 code/step6_expand_qa_translations.py --language zh --output data/qa_variants.zh.json
python3 code/step6_expand_qa_translations.py --language fr --output data/qa_variants.fr.json
```

### 2.3 Culture-specific 输出

Culture-specific 数据同样使用 Step 6 的单语言调用方式，只是输入、输出和 cache 路径使用 culture-specific 后缀：

```bash
python3 code/step6_expand_qa_translations.py \
  --input data/qa_variants.en.culture_specific.json \
  --language <language> \
  --output data/qa_variants.<language>.culture_specific.json \
  --cache-dir data/step6_qa_translation_cache.culture_specific \
  --failed-output data/qa_variants.<language>.culture_specific.failed_backtranslation.json \
  --workers 16 \
  --max-translation-attempts 4 \
  --timeout 90
```

本批 culture-specific 扩展覆盖除英语外的 9 个语言：

```text
ar, bn, de, es, fr, ja, sw, th, zh
```

Step 6 脚本不是固定 6 个语言的批处理器；它每次只接收一个 `--language`，因此只要语言代码能被脚本识别，就可以用同一套输入重复执行。Culture-specific 的目标产物为：

```text
data/qa_variants.ar.culture_specific.json
data/qa_variants.bn.culture_specific.json
data/qa_variants.de.culture_specific.json
data/qa_variants.es.culture_specific.json
data/qa_variants.fr.culture_specific.json
data/qa_variants.ja.culture_specific.json
data/qa_variants.sw.culture_specific.json
data/qa_variants.th.culture_specific.json
data/qa_variants.zh.culture_specific.json
```

当前 culture-specific Step 6 输出概况：

| Language | Output | QA variants | Accepted | Failed BT | Warnings |
|---|---|---:|---:|---:|---:|
| `ar` | `data/qa_variants.ar.culture_specific.json` | 2400 | 2400 | 0 | 1451 |
| `bn` | `data/qa_variants.bn.culture_specific.json` | 2400 | 2400 | 0 | 1731 |
| `de` | `data/qa_variants.de.culture_specific.json` | 2400 | 2400 | 0 | 215 |
| `es` | `data/qa_variants.es.culture_specific.json` | 2400 | 2400 | 0 | 127 |
| `fr` | `data/qa_variants.fr.culture_specific.json` | 2400 | 2400 | 0 | 118 |
| `ja` | `data/qa_variants.ja.culture_specific.json` | 2400 | 2400 | 0 | 1288 |
| `sw` | `data/qa_variants.sw.culture_specific.json` | 2400 | 2400 | 0 | 112 |
| `th` | `data/qa_variants.th.culture_specific.json` | 2400 | 2400 | 0 | 1455 |
| `zh` | `data/qa_variants.zh.culture_specific.json` | 2400 | 2400 | 0 | 463 |

这里的 `Warnings` 是 Step 6 输出内的启发式提示，主要用于提示 alias/script/本地化风险；它不等同于 back-translation failure。当前所有 9 个语言的 `failed_backtranslation_count` 均为 `0`。

---

## 3. Direct Translation First

Step 6 不是开放式重写，而是以英语 canonical QA 为边界的保守翻译流程：

```text
English canonical QA
  -> direct translation into target language
  -> minimal localization only when needed for established names/terms
  -> back-translation to English
  -> consistency check against English source QA
  -> automatic repair if inconsistent
```

这意味着：

- `question` 的实质语义必须直接对应英语 source question，不重写提问目标，不新增限定
- `expected_answer` 必须直接对应英语 source `expected_answer`，只允许使用目标语言里的标准对等表达
- `answer_aliases` 只能来自英语 source QA 的 `answer_aliases` 的直译或稳定对等表达
- 如果英语 source QA 没有 `answer_aliases`，目标语言默认也必须输出空 `answer_aliases`
- 不应把 `knowledge card` 原始 `aliases` 直接并入目标语言 QA，因为这些 alias 不一定都属于英语 canonical QA 的可接受答案边界
- 不应为了“更自然”而改写成另一个问法、另一个答案集合或另一个判分标准
- 目标语言 QA 翻回英文后，必须仍然询问同一个 fact，并期待同一个 answer
- 回译文本不要求和原英文逐字相同，但语义、关系、实体、限定条件必须一致

可以把 Step 6 理解为：

```text
translate the English QA faithfully
not invent a better local QA
```

例如：

```text
English source QA:
Q: What mechanism does penicillin use to kill bacteria?
A: inhibiting the completion of the synthesis of peptidoglycans

Localized Chinese QA:
Q: 青霉素通过什么机制来杀死细菌？
A: 抑制肽聚糖合成的完成
```

---

## 4. Back-translation 回测与自动返工

Step 6 必须把回测做成脚本内的自动质量 gate，而不是人工 checklist。每条英语 source QA 的处理流程建议为：

```text
source English QA
  -> generate target-language QA
  -> translate target-language question / expected_answer back to English
  -> compare back-translated English with source English
  -> if consistent: accept
  -> if inconsistent: repair target-language QA and rerun back-test
```

### 4.1 一致性检查标准

Back-translation 通过条件不是“英文完全相同”，而是语义一致。至少需要检查：

- 是否询问同一个实体 / topic
- 是否保持同一个 `relation_type`
- 是否访问同一张 `card_id` 对应的 fact
- 回译后的 expected answer 是否等价于 source `expected_answer` 或其 `answer_aliases`
- 目标语言 `answer_aliases` 是否仍然只是 source `expected_answer` / `answer_aliases` 的等价表达，而不是 topic 名、事件名、模型名、作品名或其他上下文实体
- 是否没有新增 source QA 中不存在的限定条件、解释或暗示
- 是否没有把 target / neighbor 混淆
- 是否没有把 `core` / `surface` 的 variant intent 改掉

例如，下面这种回译可以视为通过：

```text
Source EN:
Q: What mechanism does penicillin use to kill bacteria?
A: inhibiting the completion of the synthesis of peptidoglycans

Back-translated EN:
Q: By what mechanism does penicillin kill bacteria?
A: by inhibiting completion of peptidoglycan synthesis
```

下面这种应视为失败并返工：

```text
Source EN:
Q: What mechanism does penicillin use to kill bacteria?
A: inhibiting the completion of the synthesis of peptidoglycans

Back-translated EN:
Q: What disease is penicillin used to treat?
A: bacterial infections
```

### 4.2 自动返工策略

脚本应对每条 QA 维护 attempt loop：

```text
for each source_qa:
  for attempt in 1..max_translation_attempts:
    generate or repair target-language QA
    back-translate target-language QA to English
    run consistency check
    if passed:
      accept this QA
      break
  if still failed:
    mark as failed and exclude from accepted output, or write to a repair queue
```

推荐默认值：

```text
max_translation_attempts = 3
```

自动返工的目标应是修复目标语言 QA 本身，而不是不断向目标语言 QA 重新注入上游 `knowledge card` 的原始 alias。Step 6 的正式输出应以英语 canonical QA 的 `question`、`expected_answer`、`answer_aliases` 为语义边界，只允许做保守直译和最小必要本地化，不应扩大答案集合。

返工时不应重新生成英语 canonical QA，也不应修改 upstream card / pair。返工 prompt 只允许修改当前目标语言的 `question`、`expected_answer`、`answer_aliases` 和 `translation_note`。

### 4.3 自动化边界

整个回测过程必须在 Python 代码中完成：

- Python 脚本负责调用翻译、最小必要本地化、回译、一致性判断和返工
- Python 脚本负责读写 cache、attempt history、失败队列和最终输出
- 不需要 Codex 在每条数据生成后人工介入
- 即使 Codex 当前没有额度，Step 6 也可以继续通过脚本配置的 API / 本地模型 / 缓存机制运行
- Codex 的角色只是在生成结束后做最终抽查、读 summary、看失败样例并提出改进建议

建议把未通过回测的条目写入单独文件，避免它们混入正式目标语言 QA：

```text
data/qa_variants.<language>.failed_backtranslation.json
```

---

## 5. 对齐原则

每条扩展后的目标语言 QA 必须满足：

- 与 `source_qa_id` 对齐
- `topic_role` 不变
- `variant_layer` 不变
- `relation_type` 不变
- 访问的仍是同一个 fact card
- 不引入原 source QA 或 source card 中不存在的新信息

换句话说，Step 6 改变的是语言，不是知识对象。

---

## 6. 推荐字段

目标语言 QA 建议至少保留：

| 字段 | 作用 |
|---|---|
| `qa_id` | 目标语言 QA 唯一标识 |
| `source_qa_id` | 回链到英语 canonical QA |
| `source_language` | 默认 `en` |
| `generation_stage` | `translated_from_canonical_en` |
| `translation_status` | `accepted` / `failed_backtranslation` / `needs_repair` |
| `backtranslation_status` | `passed` / `failed` / `skipped` |
| `backtranslation_en` | 目标语言 QA 回译成英文后的 question / expected_answer |
| `backtranslation_consistency` | 回测一致性判断结果、理由和失败类型 |
| `translation_attempts` | 当前 QA 自动翻译 / 返工尝试次数 |
| `knowledge_pair_id` | 回链到 Step 4 的 pair |
| `card_id` | 回链到具体 card |
| `topic_role` | `target` 或 `neighbor` |
| `variant_layer` | `core` 或 `surface` |
| `language` | 当前目标语言 |
| `question` | 目标语言问句 |
| `expected_answer` | 目标语言标准答案 |
| `answer_aliases` | 目标语言可接受别名 |
| `relation_type` | relation 对齐信息 |
| `source_span` | 用于 review 的证据 |
| `translation_note` | 可选；用于人工 review 的简短说明 |

---

## 7. 推荐数量

设：

- Step 5 已经有英语 QA 总数 `Q_en`
- 当前这一次 Step 6 只处理一个目标语言

则本次正式输出文件中应新增：

```text
目标语言 accepted QA 总数 = Q_en
```

如果存在少量条目达到最大返工次数后仍无法通过 back-translation gate，它们不应静默混入正式输出。脚本应在 summary 中明确记录：

```text
accepted_qa_count
failed_backtranslation_count
repair_attempt_count
```

正式目标是 `accepted_qa_count = Q_en`。如果达不到，优先复跑 failed queue，而不是降低一致性标准。

如果后续要扩展到 `L_target` 个目标语言，则通过独立运行 `L_target` 次 Step 6，最终得到：

```text
所有目标语言文件中的新增 QA 总数 = Q_en x L_target
```

例如：

- Step 5 若基于 `500` 个 selected knowledge-card pairs，并使用默认 `surface-count=3`，则会得到 `4000` 条英语 QA
- Step 6 分别运行 `zh` 和 `fr`

则：

```text
data/qa_variants.zh.json 中约有 4000 条 QA
data/qa_variants.fr.json 中约有 4000 条 QA
两个目标语言文件合计新增 QA = 8000
```

---

## 8. LLM 生成约束

LLM prompt 应强调：

- 输入是英语 canonical QA，不是裸 fact card
- 当前调用只处理一个 `target_language`
- 每条翻译结果必须带 `source_qa_id`
- `variant_layer` 必须保持不变
- 目标语言必须是自然单语
- 不生成 mixed-language、code-switching、query/answer language mismatch
- 不新增事实、限定或解释
- `question` 要尽量直译英语 source question，只做最小必要语序调整
- `expected_answer` 要尽量直译英语 source expected answer，只使用目标语言里的稳定对等术语
- `answer_aliases` 只能来自英语 source `answer_aliases` 的直译或稳定对等表达；如果英语 source 没有 alias，就输出空列表
- 不得引入 raw card aliases、topic 名、页面名、作品名、模型名等额外答案别名
- 每条目标语言 QA 后续会被回译成英文并做一致性检查
- 如果收到回测失败原因，只修复目标语言 QA，不改 source QA

推荐 prompt 结构：

```text
给定一个 knowledge card pair，以及其英语 canonical QA probes。
请把这些英语 QA 扩展为某一个指定目标语言的平行单语 QA。

要求：
1. 每条输出都必须对应一个 source_qa_id；
2. 所有输出都必须属于同一个 target_language；
3. variant_layer 保持不变；
4. relation type 保持不变；
5. question 必须忠实对应英语 source question，只做最小必要调整；
6. expected answer 必须忠实对应英语 source expected_answer；
7. answer_aliases 只能翻译英语 source answer_aliases；如果 source 为空就输出空列表；
8. 不要生成 mixed-language；
9. 生成结果将被自动 back-translate 到英文并检查语义一致性；
10. 输出 JSON。
```

---

## 9. 执行方式

### 9.1 预览工作量

```bash
python3 code/step6_expand_qa_translations.py --dry-run --language zh
```

### 9.2 生成小样本

```bash
python3 code/step6_expand_qa_translations.py \
  --max-knowledge-pairs 2 \
  --language zh \
  --output /private/tmp/qa_variants.zh.sample.json
```

### 9.3 生成完整文件

```bash
python3 code/step6_expand_qa_translations.py \
  --input data/qa_variants.en.json \
  --language zh \
  --output data/qa_variants.zh.json
```

### 9.4 启用回测与自动返工

建议 Step 6 默认启用 back-translation gate；如果脚本提供开关，也应把启用回测作为正式生产文件的默认路径：

```bash
python3 code/step6_expand_qa_translations.py \
  --input data/qa_variants.en.json \
  --language zh \
  --output data/qa_variants.zh.json \
  --enable-backtranslation \
  --max-translation-attempts 3 \
  --workers 4 \
  --failed-output data/qa_variants.zh.failed_backtranslation.json
```

正式数据构造不建议使用 `--skip-backtranslation`。这个选项如果存在，只应用于调试 API、估算成本或定位 prompt 问题。

`--workers` 可以用于并发调用大模型 API。建议并发粒度保持在 knowledge-pair 层：每个 worker 内部仍然按单条 source QA 执行“翻译 -> 回译 -> 一致性检查 -> 必要时返工”，不同 knowledge pair 之间并行，最后再按原始顺序统一汇总输出。这样既能提升吞吐，也能避免多个线程同时写同一个 cache 文件。

### 9.5 生成多个语言

```bash
python3 code/step6_expand_qa_translations.py --language zh --output data/qa_variants.zh.json
python3 code/step6_expand_qa_translations.py --language fr --output data/qa_variants.fr.json
python3 code/step6_expand_qa_translations.py --language es --output data/qa_variants.es.json
```

---

## 10. 缓存与复现

脚本默认使用 per-knowledge-pair、per-language cache：

```text
data/step6_qa_translation_cache/
```

推荐缓存文件命名形如：

```text
<knowledge_pair_id>__zh.raw.json
<knowledge_pair_id>__zh.normalized.json
<knowledge_pair_id>__zh.backtranslation.json
<knowledge_pair_id>__zh.consistency.json
<knowledge_pair_id>__zh.attempts.json
```

如果需要强制重新调用 API：

```bash
python3 code/step6_expand_qa_translations.py --language zh --refresh-cache
```

回测 cache 应保留每次 attempt 的关键信息：

- target-language question / expected_answer
- back-translated English question / expected_answer
- consistency verdict
- failure reason
- repair instruction
- accepted / failed 状态

这样 Step 6 可以在中断后继续运行，也可以在不消耗 Codex 额度的情况下由 Python 脚本独立完成复跑。

---

## 11. 质量检查

Step 6 生成后至少检查：

- 每条目标语言 QA 是否有对应的 `source_qa_id`
- 每个英语 source QA 是否都恰好生成了一条当前目标语言翻译
- `variant_layer` 是否与英语 source QA 保持一致
- `topic_role` 是否保持一致
- target / neighbor 是否被混问
- 目标语言问句是否自然
- expected answer 是否与目标语言常见表达对齐
- 是否出现 mixed-language / code-switching
- 输出文件中是否只包含当前目标语言
- 每条 accepted QA 是否都通过 back-translation consistency gate
- `failed_backtranslation_count` 是否为 0；如果不为 0，是否已写入 failed queue
- 回译失败原因是否集中在某一类 relation、实体名或 answer type 上

如果发现问题，优先判断问题属于：

- 英语 canonical QA 本身有偏差：回退到 Step 5
- 翻译 / 直译边界执行得不够严格：在 Step 6 的自动返工队列中修正并复跑
- 回译一致性检查过严或过松：调整 Step 6 的 consistency judge prompt / rule，但不要直接放宽正式输出标准

### 11.1 Culture-specific 翻译质量抽样审核

在不考虑 `answer_aliases` 覆盖问题的前提下，当前 culture-specific Step 6 另做了一轮第三方 API 翻译质量审核：

```text
review script: code/review_step6_translation_quality.py
review json: data/qa_translation_quality_review.sample100.culture_specific.json
review tsv: data/qa_translation_quality_review.sample100.culture_specific.tsv
sample: 100 QA per non-English language, 900 QA total
result: 900 / 900 overall pass, 8 minor, 0 major
```

该审核只比较英语 source `question` / `expected_answer` 与目标语言 `question` / `expected_answer` 的翻译等价性、流畅度和目标语言使用情况；明确忽略 `answer_aliases`，不把 alias 缺失或覆盖不足作为翻译质量失败。

---

## 12. 边界

Step 6 可以做：

- 以英语 canonical QA 为 source 扩展到一个目标语言
- 保留 `source_qa_id`，建立跨语言 lineage
- 自动执行目标语言 QA 的 back-translation 回测
- 自动返工未通过回测的目标语言 QA
- 输出 accepted 文件、失败队列和 summary
- 为 Step 7 提供独立的单语言 QA 文件
- 依据英语 canonical QA 的 Q/A/answer_aliases 做保守直译

Step 6 不应做：

- 一次生成多个目标语言并耦合到同一输出文件
- 重新生成英语 canonical QA
- 重新决定 `core` / `surface`
- 重做 target / neighbor pairing
- 生成 mixed-language recovery probes
- 直接承担最终发布筛选职责
- 让 Codex 在生成主循环中逐条判断翻译是否通过
- 为了补齐数量而接受未通过回测的 QA
- 让目标语言 `answer_aliases` 脱离英语 canonical QA 的答案边界自行扩张

这样 Step 6 才能成为“稳定英语 source QA -> 单一目标语言平行单语 QA”的独立扩展层，并且可以按语言反复复跑。
