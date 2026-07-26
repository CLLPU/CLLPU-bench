# Multilingual Unlearning Metrics

本文记录当前 multilingual unlearning 实验中用于论文材料的指标口径。记号与 `open-unlearning-main/docs/multilingual-evaluation-workflow.md`、`src/evals/metrics/multilingual.py` 和 `scripts/aggregate_multilingual_transfer.py` 保持一致。

## 1. 记号

| 记号 | 含义 |
|---|---|
| <i>s</i> | source language，即执行 unlearning 的语言。 |
| <i>t</i> | target/evaluation language，即评估访问度变化的语言。 |
| <i>g</i> | knowledge object，当前实现中由 `knowledge_pair_id + topic_role` 标识。 |
| <i>r</i> | topic role，当前主要取 `target` 或 `neighbor`。 |
| <i>v</i> | variant layer，当前主要取 `core` 或 `surface`。 |
| <i>x</i> | metric family，当前取 `exact` 或 `rouge`。 |
| <i>q</i> | 单条 QA 样本。 |
| <i>Q</i><sub><i>t</i></sub><sup><i>v</i></sup>(<i>g</i>,<i>r</i>) | 语言 <i>t</i>、知识对象 <i>g</i>、角色 <i>r</i>、变体层 <i>v</i> 下的 QA 集合。 |
| <i>Q</i><sub><i>t</i></sub><sup><i>v</i></sup>(<i>r</i>) | 语言 <i>t</i>、角色 <i>r</i>、变体层 <i>v</i> 下的全部 QA 集合，用于 role-level `A_current` 汇总。 |
| <i>m</i><sub>pre</sub> | unlearning 前的固定 finetuned-pre 模型。 |
| <i>m</i><sub>post</sub><sup>(<i>s</i>)</sup> | 在 source language <i>s</i> 上完成 unlearning 后的 checkpoint。 |
| <i>epsilon</i> | ratio 分母保护项，当前聚合脚本默认使用 `1e-8`。 |
| <i>tau</i><sub><i>x</i></sub> | metric family <i>x</i> 对应的 pre-threshold；当前 `tau_exact=1e-8`，`tau_rouge=0.1`。 |

当前正式 weighted 口径使用：

$$
w_{\mathrm{core}} = 0.5,\qquad w_{\mathrm{surface}} = 0.5.
$$

若某次聚合显式改变 `variant_weights`，必须在结果记录中另行标明。

pre/post profile 计算前，脚本会先按 `qa_id` 对齐 pre 与 post records，并在严格模式下检查以下字段一致：

```text
language, question, expected_answer, knowledge_pair_id, pair_id,
topic_role, variant_layer, relation_type, source_qa_id
```

因此下文的 $Q$、$G$、$A_{\mathrm{pre}}$ 与 $A_{\mathrm{post}}$ 都是在同一批 aligned QA records 上计算的；若 alignment 不成立，正式 profile 不应被解释为 unlearning 效果。

## 2. Per-QA Accessibility

单条 QA 的可访问度记为 $a(q)$。当前实现保留 exact 与 ROUGE 两个并列口径。

### Exact

$$
a_{\mathrm{exact}}(q)=
\begin{cases}
1, & \text{generation exactly matches the expected answer},\\
0, & \text{otherwise}.
\end{cases}
$$

当前 v1 exact 不使用 answer aliases；使用 OpenUnlearning generation post-processing 后做 strict expected-answer matching。

### ROUGE

$$
a_{\mathrm{rouge}}(q)=\mathrm{ROUGE}\text{-}\mathrm{L}_{F1}
\bigl(\mathrm{generation}(q),\mathrm{expected}(q)\bigr).
$$

ROUGE 使用 `rouge_score` 的 ROUGE-L F1；tokenizer 为 `mixed_unicode_default_latin_v2`，保留 Latin 默认行为，并对 CJK、日文假名、泰文、阿拉伯文、孟加拉文做确定性分词。

### Language-level mean

对语言 $t$ 的 eval QA 集合 $Q_t$，语言级单模型均值为：

$$
a_{\mathrm{exact\_mean}}(t)=\frac{1}{|Q_t|}\sum_{q\in Q_t}a_{\mathrm{exact}}(q),
$$

$$
a_{\mathrm{rouge\_mean}}(t)=\frac{1}{|Q_t|}\sum_{q\in Q_t}a_{\mathrm{rouge}}(q).
$$

`a_exact_mean` 和 `a_rouge_mean` 都是 checkpoint eval 的单模型汇总字段，不需要 pre/post 对齐。

## 3. Single-model A_current

对当前模型 $m$，先在知识对象、角色和变体层上聚合。对任一 $x\in\{\mathrm{exact},\mathrm{rouge}\}$：

$$
A_{\mathrm{current},x}^{v}(g,r,t;m)=
\frac{1}{|Q_t^v(g,r)|}
\sum_{q\in Q_t^v(g,r)} a_x(q;m).
$$

知识对象级 weighted 版本为：

$$
A_{\mathrm{current},x}(g,r,t;m)=
\sum_{v\in\{\mathrm{core},\mathrm{surface}\}}
w_v A_{\mathrm{current},x}^{v}(g,r,t;m).
$$

注意这里有两个层级，二者都由代码保存，但用途不同：

| 层级 | 代码字段 | 分组键 | 用途 |
|---|---|---|---|
| knowledge-level | `by_knowledge_language` / profile `by_knowledge` | `language + knowledge_pair_id + topic_role`，并带有 variant 子项 | 计算 `T_x`、`R_nbr,x`、`D_nbr,x` 的 pre/post profile |
| role-level | `by_role_language` | `language + topic_role`，并带有 variant 子项 | 生成结果表中的 `A_current_exact(target,t)`、`A_current_rouge(neighbor,t)` 等单模型汇总 |

当前结果表中的 role-level `A_current_*` 来自 evaluator 的 `by_role_language` 汇总。也就是说，它在同一 `language + topic_role + variant_layer` 下先对 QA 直接求均值，再做 core/surface 加权：

$$
A_{\mathrm{current},x}^{v}(r,t;m)=
\frac{1}{|Q_t^v(r)|}
\sum_{q\in Q_t^v(r)}a_x(q;m),
$$

$$
A_{\mathrm{current},x}(r,t;m)=
\sum_{v}w_v A_{\mathrm{current},x}^{v}(r,t;m).
$$

因此，结果表中的：

$$
A_{\mathrm{current},\mathrm{rouge}}(\mathrm{target},t).\mathrm{weighted}
$$

表示当前 checkpoint 在语言 $t$ 的 target QA 上，按 core/surface 加权后的 ROUGE 可访问度；neighbor 同理。

`A_current` 只描述当前模型本身的可访问度。进入 pre/post 聚合后：

$$
A_{\mathrm{current}}(m_{\mathrm{pre}})\rightarrow A_{\mathrm{pre}},
\qquad
A_{\mathrm{current}}(m_{\mathrm{post}}^{(s)})\rightarrow A_{\mathrm{post}}^{(s)}.
$$

## 4. Target Transfer / Forgetting Strength

Target transfer 衡量 source language $s$ 上 unlearning 后，target role 知识在 evaluation language $t$ 中相对于 pre 的下降比例。对任一 $x\in\{\mathrm{exact},\mathrm{rouge}\}$，weighted 主公式为：

先定义 source $s$ 的 post run 与 pre run 对齐后，在 evaluation language $t$ 上可用于 target profile 的知识集合：

$$
G_{\mathrm{target}}^{(s)}(t)=
\{
g:
\exists q\in Q_t^{\mathrm{core}}(g,\mathrm{target})\cup Q_t^{\mathrm{surface}}(g,\mathrm{target})
\text{ and } q \text{ is aligned in pre and } post^{(s)}
\}.
$$

这里的 $G_{\mathrm{target},x}^{\mathrm{valid}}(s,t)$ 不是一个新的数据集，而是 $G_{\mathrm{target}}^{(s)}(t)$ 在 metric $x$ 下经过 pre-threshold filtering 后留下的有效子集。形式化地：

$$
G_{\mathrm{target},x}^{\mathrm{valid}}(s,t)=
\{
g\in G_{\mathrm{target}}^{(s)}(t):
A_{\mathrm{pre},x}(g,\mathrm{target},t)\ge \tau_x
\}.
$$

直观理解是：只有 pre 模型本来“会”的知识，才适合用相对下降比例衡量遗忘强度；如果 pre 本来几乎不会，则 post 变低并不能说明 unlearning 成功。

$$
T_x(s\rightarrow t)=
\frac{1}{|G_{\mathrm{target},x}^{\mathrm{valid}}(s,t)|}
\sum_{g\in G_{\mathrm{target},x}^{\mathrm{valid}}(s,t)}
\frac{
A_{\mathrm{pre},x}(g,\mathrm{target},t)-A_{\mathrm{post},x}^{(s)}(g,\mathrm{target},t)
}{
\max(A_{\mathrm{pre},x}(g,\mathrm{target},t),\epsilon)
}.
$$

core/surface 分层版本为：

分层有效集合 $G_{\mathrm{target},x}^{v,\mathrm{valid}}(s,t)$ 同理，只是使用对应 variant layer 的 pre 可访问度：

$$
G_{\mathrm{target},x}^{v,\mathrm{valid}}(s,t)=
\{
g\in G_{\mathrm{target}}^{(s)}(t):
A_{\mathrm{pre},x}^{v}(g,\mathrm{target},t)\ge \tau_x
\}.
$$

$$
T_x^v(s\rightarrow t)=
\frac{1}{|G_{\mathrm{target},x}^{v,\mathrm{valid}}(s,t)|}
\sum_{g\in G_{\mathrm{target},x}^{v,\mathrm{valid}}(s,t)}
\frac{
A_{\mathrm{pre},x}^{v}(g,\mathrm{target},t)-A_{\mathrm{post},x}^{(s),v}(g,\mathrm{target},t)
}{
\max(A_{\mathrm{pre},x}^{v}(g,\mathrm{target},t),\epsilon)
}.
$$

解释：$T$ 越高，表示相对遗忘越强；$T<0$ 表示 post 可访问度高于 pre。

当前 ratio 指标使用 pre-threshold filtering：

| metric family | pre threshold |
|---|---:|
| exact | `1e-8` |
| ROUGE | `0.1` |

使用该 filtering 的原因如下：

- Ratio 指标的分母是 pre 可访问度。如果 $A_{\mathrm{pre}}$ 很小，$(A_{\mathrm{pre}}-A_{\mathrm{post}})/A_{\mathrm{pre}}$ 或 $A_{\mathrm{post}}/A_{\mathrm{pre}}$ 会非常不稳定，容易由极小分母放大成没有解释意义的数值。
- 对 exact 来说，$A_{\mathrm{pre},\mathrm{exact}}$ 来自 strict match 均值，实际只需要排除 pre exact 为 0 的知识；因此阈值设为 `1e-8`，等价于“pre exact 必须大于 0”，同时避免浮点比较中的零分母问题。
- 对 ROUGE 来说，低于 `0.1` 的 ROUGE-L F1 通常表示 pre 生成与标准答案只有很弱文本重叠。此时即使 post 继续下降，也不应被解释为可靠的“遗忘”；若 post 上升，也不应被一个很小的 pre 分母放大为异常大的 retention ratio。因此当前工程口径将 $A_{\mathrm{pre},\mathrm{rouge}}<0.1$ 的知识排除在 ratio 均值之外。

低于阈值的知识对象不进入 $T/R_{\mathrm{nbr}}/D_{\mathrm{nbr}}$ 的 ratio 均值；脚本同时记录 `*_valid_count` 与 `*_excluded_low_pre_count`。这些 count 很重要：它们说明该 source-target 单元中有多少知识真正参与了 ratio 计算，以及有多少知识因为 pre 不足而只适合作为诊断样本。被过滤样本的绝对变化仍保存在：

$$
\Delta_{\mathrm{target},x}=
A_{\mathrm{pre},x}-A_{\mathrm{post},x}^{(s)}
$$

中，作为诊断信息。

实现细节需要明确区分：weighted $T_x(s\rightarrow t)$ 的 filtering 使用 knowledge-level weighted $A_{\mathrm{pre},x}(g,\mathrm{target},t)$；variant $T_x^v(s\rightarrow t)$ 的 filtering 使用对应 variant 的 $A_{\mathrm{pre},x}^{v}(g,\mathrm{target},t)$。结果表中的 `T_*_valid_count` / `T_*_excluded_low_pre_count` 是 weighted ratio 的 count；variant-level count 保存在 profile summary 中，不在当前 common 长表中单独展开。

## 5. Neighbor Retention and Damage

Neighbor retention 衡量 unlearning 后 neighbor role 的保留比例。对任一 $x\in\{\mathrm{exact},\mathrm{rouge}\}$，weighted 主公式为：

先定义 source $s$ 的 post run 与 pre run 对齐后，在 evaluation language $t$ 上可用于 neighbor profile 的知识集合：

$$
G_{\mathrm{neighbor}}^{(s)}(t)=
\{
g:
\exists q\in Q_t^{\mathrm{core}}(g,\mathrm{neighbor})\cup Q_t^{\mathrm{surface}}(g,\mathrm{neighbor})
\text{ and } q \text{ is aligned in pre and } post^{(s)}
\}.
$$

Neighbor 侧的有效集合与 target 侧同理：

$$
G_{\mathrm{neighbor},x}^{\mathrm{valid}}(s,t)=
\{
g\in G_{\mathrm{neighbor}}^{(s)}(t):
A_{\mathrm{pre},x}(g,\mathrm{neighbor},t)\ge \tau_x
\}.
$$

也就是说，$R_{\mathrm{nbr}}$ 与 $D_{\mathrm{nbr}}$ 只在 pre 模型原本可访问的 neighbor knowledge 上解释“保留率”和“误伤”。如果 pre 对某个 neighbor knowledge 本来就不可访问，则它不能用于判断 retain 是否成功，但其绝对变化仍保留在 Delta 诊断字段中。

$$
R_{\mathrm{nbr},x}(s,t)=
\frac{1}{|G_{\mathrm{neighbor},x}^{\mathrm{valid}}(s,t)|}
\sum_{g\in G_{\mathrm{neighbor},x}^{\mathrm{valid}}(s,t)}
\frac{
A_{\mathrm{post},x}^{(s)}(g,\mathrm{neighbor},t)
}{
\max(A_{\mathrm{pre},x}(g,\mathrm{neighbor},t),\epsilon)
}.
$$

core/surface 分层版本为：

$$
G_{\mathrm{neighbor},x}^{v,\mathrm{valid}}(s,t)=
\{
g\in G_{\mathrm{neighbor}}^{(s)}(t):
A_{\mathrm{pre},x}^{v}(g,\mathrm{neighbor},t)\ge \tau_x
\}.
$$

$$
R_{\mathrm{nbr},x}^{v}(s,t)=
\frac{1}{|G_{\mathrm{neighbor},x}^{v,\mathrm{valid}}(s,t)|}
\sum_{g\in G_{\mathrm{neighbor},x}^{v,\mathrm{valid}}(s,t)}
\frac{
A_{\mathrm{post},x}^{(s),v}(g,\mathrm{neighbor},t)
}{
\max(A_{\mathrm{pre},x}^{v}(g,\mathrm{neighbor},t),\epsilon)
}.
$$

Neighbor damage 定义为：

$$
D_{\mathrm{nbr},x}(s,t)=1-R_{\mathrm{nbr},x}(s,t),
$$

$$
D_{\mathrm{nbr},x}^{v}(s,t)=1-R_{\mathrm{nbr},x}^{v}(s,t).
$$

解释：$R_{\mathrm{nbr}}$ 越接近或高于 $1$，neighbor 保留越好；$D_{\mathrm{nbr}}$ 越高，neighbor 误伤越大。若 $D_{\mathrm{nbr}}<0$，表示 post 的相对可访问度高于 pre。低-pre 样本不进入 ratio 均值；绝对变化保存在：

$$
\Delta_{\mathrm{nbr\_damage},x}=
A_{\mathrm{pre},x}-A_{\mathrm{post},x}^{(s)}
$$

中。

与 target transfer 一样，weighted $R_{\mathrm{nbr},x}$ / $D_{\mathrm{nbr},x}$ 使用 weighted $A_{\mathrm{pre},x}$ 过滤；variant 指标使用对应 $A_{\mathrm{pre},x}^{v}$ 过滤。当前 common 长表中的 `R_nbr_*_valid_count` / `R_nbr_*_excluded_low_pre_count` 是 weighted neighbor ratio 的 count。

## 6. 三个主要矩阵系列

当前 common 主结果使用 selected-checkpoint method-level matrix。每个 method 的每一行 $s$ 来自该 method 在 source language $s$ 上最终保留的 checkpoint；因此它不是“同一超参数、同一 epoch 横跨所有 source language”的严格 full-transfer profile。

对每个 metric $x\in\{\mathrm{exact},\mathrm{rouge}\}$ 和 variant $v\in\{\mathrm{core},\mathrm{surface},\mathrm{weighted}\}$，三个主要矩阵系列为：

| 矩阵系列 | 单元格 | 含义 | 论文使用建议 |
|---|---|---|---|
| Target transfer matrix `T_x^v` | `T_x^v(s -> t)` | source `s` unlearning 后 target 知识在 target language `t` 上的相对遗忘强度。 | 展示语言内与跨语言遗忘传播图案。 |
| Neighbor retention matrix `R_nbr,x^v` | `R_nbr,x^v(s,t)` | source `s` unlearning 后 neighbor 知识在 language `t` 上相对 pre 的保留比例。 | 展示 retain/neighbor 是否被保持。 |
| Neighbor damage matrix `D_nbr,x^v` | `D_nbr,x^v(s,t)` | `1 - R_nbr,x^v(s,t)`。 | 展示 neighbor collateral damage。 |

当前 `evaluation/results/common/` 同时记录 exact 与 ROUGE 两个系列；若正文只展示 ROUGE，exact 仍可作为 appendix 或 robustness material。

## 7. 当前 common 结果源

当前 common selected-checkpoint 结果源为：

```text
open-unlearning-main/saves/exports/common_selected_checkpoint_matrices/
  manifest.json
  common_selected_checkpoint_profile_metrics.csv
  <method>/selected_checkpoints.csv
  <method>/matrices/{T,R_nbr,D_nbr}_{exact,rouge}_{core,surface,weighted}.csv
```

`manifest.json` 的 `profile_type` 为 `common_selected_checkpoint_method_level_matrix`。本目录下结果文档中的数值表为展示用 6 位小数；完整精度以源 CSV/matrix artifact 为准。
