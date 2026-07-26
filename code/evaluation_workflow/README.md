# Benchmark Evaluation Workflow

本文档是 benchmark 评测设计主线的入口。

这条 workflow 与 [../data_workflow/README.md](../data_workflow/README.md) 明确分离：

- `code/data_workflow/` 负责 benchmark data construction
- `code/evaluation_workflow/` 负责 benchmark evaluation design

这样做的目的，是避免“怎么造数据”和“怎么评估数据”继续耦在同一条流水线里。

---

## 1. 这条 Workflow 负责什么

evaluation workflow 预计负责以下内容：

- evaluation target 的定义
- forget / retain / neighbor behavior 的指标设计
- 基于平行单语 QA 的 cross-lingual transfer 评测维度
- 与主评测分离的 recovery / escape stress test 设计
- answer matching 与 judge protocol
- metric aggregation 与 summary reporting
- error taxonomy 与 failure analysis

它不负责：

- topic pair 设计
- Wikipedia 页面收集
- knowledge card 抽取
- relation-matched pairing
- QA variant 生成

这些内容属于 data construction workflow。

---

## 2. 预期输入

这条 workflow 的上游输入，原则上应来自已经冻结或至少相对稳定的数据构造产物，例如：

- `data/knowledge_card_pairs.json`
- `data/qa_variants.en.json`
- 一个或多个 Step 6 单语言 QA 文件，例如 `data/qa_variants.zh.json`、`data/qa_variants.fr.json`
- 最终筛选后的 benchmark release 文件

如果后续增加模型输出记录或判分缓存，也建议作为 evaluation 侧独立产物维护。

---

## 3. 预期子步骤

后续可以逐步拆成若干子文档，例如：

1. `step-1-evaluation-targets.md`
2. `step-2-metric-definition.md`
3. `step-3-judge-protocol.md`
4. `step-4-aggregation-and-reporting.md`
5. `step-5-error-analysis.md`

当前先保留空骨架，等 metric 设计真正展开时再逐步落细。

---

## 4. 与 Data Construction 的边界

推荐遵守下面这条分工：

- data construction workflow 产出“评什么”
- evaluation workflow 定义“怎么评”

如果发现某个 QA 根本不适合评测，应优先回退到 data construction workflow 修改数据，而不是在 evaluation 层硬补规则。

---

## 5. 当前状态

当前仓库里，evaluation workflow 还是骨架阶段。

正式开展 metric 设计时，建议从这里继续扩展，而不要把评测逻辑重新写回 `code/data_workflow/README.md`。
