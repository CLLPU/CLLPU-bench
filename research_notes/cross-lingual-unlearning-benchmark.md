# A Benchmark for Cross-Lingual Unlearning in Multilingual Language Models：引言与评价指标设计

## 1. 引言

现有大语言模型 unlearning 研究，已经逐渐从“模型还能不能回答被遗忘问题”这一类单一、表面的测试，转向更完整的多维评测视角。已有综述指出，LLM unlearning 的评估不能只依赖单一 forget score，而应同时关注 unlearning scope、data–model interaction 以及 multifaceted efficacy assessment；与此同时，MUSE 进一步将评估拆解为六类性质，包括文本级记忆、知识级记忆、隐私泄漏、效用保持、可扩展性和持续性。这些研究共同说明：unlearning 本质上不是一个单一目标问题，而是一个需要从多个维度加以刻画的复杂对象。[1][2]

在 multilingual / cross-lingual 场景下，这一问题会进一步复杂化。已有工作表明，许多 unlearning 方法在执行遗忘的训练语言上看似有效，但同一知识在其他语言中仍然可以被访问；并且这种跨语言传播并不总是对称的，还会受到语言相似性等因素影响。[5][7] 这意味着，在多语言模型中，所谓“已经遗忘”并不能简单地理解为“目标语言中答不出来了”，因为模型可能只是失去了某一语言中的访问或表达能力，而目标知识在其他语言、其他表述形式甚至跨语言推理路径中仍然存在。进一步地，最新 cross-lingual unlearning 研究还发现，多语言遗忘并非简单的“删掉或没删掉”，而是可能对应不同层次的内部变化：移除共享跨语言子空间会影响所有语言，而只移除语言特定成分则可能只影响单一语言。[5] 因而，在 cross-lingual setting 下，真正需要回答的问题不再只是“忘了多少”，而是“算法诱导了怎样的多语言遗忘图案”。

基于这一背景，我们构建的 benchmark 不将目标设定为“给所有 unlearning 算法排出一个单一总分”，而是明确区分两个层次的评测目标。

第一层是 **policy-free profiling**。这一层不预设唯一真实场景，也不事先规定哪一种遗忘行为一定更优。它关注的是：在不带入特定任务偏好的情况下，一个 unlearning 算法在 multilingual / cross-lingual 场景中究竟表现出怎样的 **forgetting profile**。更具体地说，我们希望在这一层回答如下问题：该算法的遗忘更偏向全局传播还是局部局限；其跨语言传播是否具有方向性与非对称性；它对目标知识的删除是停留在单一标准问法层面，还是在同一语言内部的表层改写、翻译校正问法、多轮交互、relearning 等条件下仍然稳定。换言之，这一层的目标不是裁定“谁最好”，而是尽可能准确、深刻地描绘不同算法在多语言空间中的遗忘特性，为后续比较与选择提供一个结构化、可解释的画像。也正因为如此，这一层更适合支持 **Pareto-style** 的多维比较，而不是将所有方法压缩到单一分数上。[1][2]

第二层是 **policy-conditioned evaluation**。这一层建立在第一层 profile 之上，关注的是：当具体需求已经明确时，某个算法所呈现出的 forgetting profile 是否符合该场景的目标策略。也就是说，这一层不再只是描述“算法是什么样”，而是进一步评估“这种特性在给定任务下是否合适”。在本文中，我们重点考虑两类具有代表性的多语言 unlearning 场景。第一类是 **common-goals**：某些 topic 在多个语言中都属于共同的遗忘目标，因此理想算法应能使遗忘在相关语言之间有效传播，避免其他语言成为知识逃逸通道。第二类是 **culture-specific**：某些 topic 只在目标语言或特定文化语境中需要遗忘，而在其他语言中应当保留，因此理想算法应具备更强的局部化与边界控制能力，避免不必要的跨语言误伤。由此，第二层的核心不再是抽象的“遗忘强弱”，而是**在具体场景约束下，算法行为是否符合需求**。这也正是本文所说的 Policy fidelity 所对应的含义。

这样的两层结构，旨在有意识地分开两个在既有研究中常被混淆的问题。其一，算法本身在 cross-lingual 场景下呈现出什么样的遗忘特性；其二，在一个具体而明确的应用需求下，这种遗忘特性是否符合目标场景。前者对应的是对算法行为的**描述性刻画**，后者对应的是面向具体部署需求的**条件化选择**。我们认为，只有先在 policy-free 条件下充分刻画算法的 forgetting profile，后续关于“哪种算法更适合某一类场景”的判断才具有坚实基础。[1][2][5]

---

## 2. 评价指标设计：总体思想

本 benchmark 将遗忘目标视为多语言知识对象，而非单一语言表述。后续指标不再重复测量这一前提，而是在该前提下刻画其传播拓扑与边界控制。目标知识的可访问度默认通过各语言内的 core factual QA 与 surface variant QA 估计；code-switching、query / answer language mismatch 与 bridge-language access 等 mixed-language recovery 路径不进入主指标。

本 benchmark 不是由彼此独立的指标组拼接而成，而是由两个相互支撑的观测窗口共同构成：传播拓扑负责刻画目标知识在多语言空间中的遗忘范围、方向性与单语访问鲁棒性，边界控制负责刻画这种删除是否误伤非目标知识与邻近 topic。换言之，core / surface 层面的 recoverability 会影响目标遗忘强度估计；mixed-language recovery 则属于另一类 adversarial access problem，应与主传播矩阵分开处理。

我们认为，cross-lingual unlearning benchmark 的构建不应建立在单一遗忘分数之上，而应建立在多语言知识具有结构性的这一基本事实上。基于这一第一性原理，benchmark 至少应刻画五个方面：其一，遗忘的对象应被理解为跨语言知识对象，而非单一语言表述；其二，遗忘可能作用于不同层次的位置，例如共享概念空间或语言特定通道；其三，遗忘在语言空间中的传播拓扑，包括传播范围、方向性与一致性；其四，这种传播是否能够根据具体任务需求被有效控制；其五，目标知识是否仍能通过各语言内部的表层改写与翻译校正问法被访问。基于这五点，benchmark 的目标不再是以单一分数排序算法，而是系统刻画其在 multilingual / cross-lingual 空间中所诱导的遗忘图案。

### 2.1 设计原则

我们的指标设计不从“构造单一总分”出发，而从两个更本质的问题出发：

1. **一个 unlearning 算法在 cross-lingual setting 下，究竟呈现出什么样的遗忘图案？**
2. **当场景需求明确时，这种遗忘图案是否符合该场景的目标策略？**

因此，评价体系也自然分成两层：

- **第一层：policy-free profile**
  - 面向“描述”
  - 负责完整刻画算法的跨语言遗忘特性
- **第二层：policy-conditioned evaluation**
  - 面向“选择”
  - 在具体任务目标明确时，基于 profile 定义场景化指标

这种设计与现有研究趋势一致：BLUR 指出，如果只依赖传统 benchmark，很多方法会被高估，因为更真实的 forget-retain overlap、combined queries 和 relearning 会显著暴露所谓“已遗忘知识”的残留；Deep Unlearning 则进一步表明，仅仅让目标事实表面上答不出来还不够，还需要测试它是否仍可由保留知识和推理链恢复出来。[3][4] 

### 2.2 Benchmark 默认不输出统一总分

在 **policy-free** 层面，我们默认**不输出单一总分**。原因是：真实用户的场景需求并不唯一，有的任务希望遗忘跨语言传播，有的任务则希望遗忘严格局部化；有的任务更重视深层删除，有的任务更重视效用保持。因此，benchmark 的职责应当首先是完整呈现算法的 forgetting profile，而不是预先替用户规定何为“唯一更优”。这一点与多维评测和场景依赖评估的总体方向是一致的。[1][2][3] 

---

## 3. 第一层：Policy-free Forgetting Profile

这一层的目标是：**不预设具体策略，先尽可能完整地描绘 unlearning 算法的跨语言遗忘特性。**

### 3.1 遗忘的传播范围与方向性（Propagation Scope \& Directionality）

这一组指标用于刻画：**当 unlearning 在源语言 $s$ 上执行后，遗忘如何在多语言空间中传播、衰减或局部化，以及这种传播是否呈现出稳定的方向性与结构性。** 从 benchmark 的第一性原理来看，这一维度对应的是 multilingual unlearning 的 **propagation topology**：即目标知识对象在不同语言之间的遗忘影响如何分布，而不仅仅是“某个目标语言上忘了多少”。这一维度是 cross-lingual benchmark 的核心，因为已有研究表明，多数现有方法难以稳定移除训练语言之外的事实，同时跨语言传播往往具有明显的非对称性，而非简单的均匀迁移。

### 3.1.1 基本思想：从“遗忘强度”到“跨语言传播矩阵”

设共有语言集合 $\mathcal{L}$，其中 $s \in \mathcal{L}$ 表示执行 unlearning 的源语言，$t \in \mathcal{L}$ 表示评测遗忘效果的目标语言。  
对于每个目标知识单元 $g$，我们不把目标语言 $t$ 上的评测查询 $Q_t(g)$ 限定为单一 canonical factual question，而是将其拆成若干访问变体族：

$$
Q_t(g)
=
Q_t^{\text{core}}(g)
\cup
Q_t^{\text{surf}}(g)
$$

其中：

- $Q_t^{\text{core}}(g)$：**core factual QA**，即最直接、最标准的事实问答，用于测量目标知识在目标语言中的基本可访问性；
- $Q_t^{\text{surf}}(g)$：**surface variant QA**，包括 paraphrase、alias substitution、template variation、back-translation 等不改变目标知识语义但改变表面形式的查询；
- 这里默认不把 cross-lingual / mixed-language prompts 放进 $Q_t(g)$。也就是说，语言 $t$ 上的可访问度，使用的是该语言内部的平行单语 probe，而不是 query / answer mismatch、code-switching 或 bridge-language access。

这样定义的原因是：若主任务是衡量“在源语言 $s$ 上做 unlearning 后，知识可访问性如何迁移到目标语言 $t$”，那么评价单位应是语言 $t$ 自身的单语访问能力。否则，语言 $t$ 的分数会混入“模型是否能借助语言混合路径恢复答案”，从而把 transfer 与 escape path 混在一起。

因此，recoverability / escape structure 若需要研究，应该作为额外 stress test 单列，而不并入主可访问度定义。

更具体地说，Source-to-Target Unlearning Transfer Matrix 采用 core factual QA 与 surface variant QA，而排除 mixed-language QA variants，主要基于以下考虑。

首先，矩阵元素 $T_{s \rightarrow t}$ 的目标语义是“在源语言 $s$ 上执行 unlearning 后，目标语言 $t$ 的知识访问能力下降了多少”。因此，目标语言 $t$ 上的 probe 应当尽量只测量 $t$ 语言自身的访问通道。core factual QA 提供最小、稳定、可判分的访问形式；surface variant QA 则检验这种访问能力是否只是对某个模板失效，还是在同一语言内部的改写、别名替换和模板变化下也被削弱。两者合在一起，能够覆盖 clean monolingual access 下的基本可访问性与表层鲁棒性。

相比之下，mixed-language variants 测量的是不同的问题。code-switched prompts、query / answer language mismatch 与 bridge-language access 会同时引入多个额外变量：混合语言的组合方式、提示中哪一部分承载实体或关系、模型是否遵循跨语言作答指令、以及模型是否能通过第三种语言或保留语言重新激活目标知识。此时得到的分数不再只表示“遗忘是否从 $s$ 传播到了 $t$”，而会混入“是否存在一条跨语言恢复路径”。因此，如果把这类 probe 纳入 $A_{\text{post}}^{(s)}(g,t)$，矩阵元素的解释会从 unlearning transfer 变成 transfer 与 adversarial recovery 的混合量，削弱 benchmark 的 construct validity。

这并不意味着 mixed-language recovery 不重要，而是说它不应成为 Source-to-Target Transfer Matrix 的必做组成部分，也不应进入主 benchmark aggregation；否则 benchmark 会从“刻画遗忘传播拓扑”扩张为“同时评估多语言逃逸攻击面”，从而模糊核心研究问题。相关的 mixed-language recovery matrix 更适合作为后续研究方向单独展开。

对每个访问变体族 $v \in \{\text{core}, \text{surf}\}$，先定义族内可访问度：

$$
A_{\text{pre}}^{v}(g,t)
=
\frac{1}{|Q_t^{v}(g)|}
\sum_{q \in Q_t^{v}(g)}
a_{\text{pre}}(g,t,q)
$$

$$
A_{\text{post}}^{(s),v}(g,t)
=
\frac{1}{|Q_t^{v}(g)|}
\sum_{q \in Q_t^{v}(g)}
a_{\text{post}}^{(s)}(g,t,q)
$$

其中 $a_{\text{pre}}(g,t,q)$ 与 $a_{\text{post}}^{(s)}(g,t,q)$ 表示单个查询 $q$ 上的访问成功程度。随后，将两类访问族聚合为模型在 unlearning 前后的总体**知识可访问度**：

$$
A_{\text{pre}}(g,t), \quad A_{\text{post}}^{(s)}(g,t)
$$

具体可写作：

$$
A_{\text{pre}}(g,t)
=
\sum_{v \in \{\text{core},\text{surf}\}}
w_v A_{\text{pre}}^{v}(g,t)
$$

$$
A_{\text{post}}^{(s)}(g,t)
=
\sum_{v \in \{\text{core},\text{surf}\}}
w_v A_{\text{post}}^{(s),v}(g,t)
$$

其中 $w_v \ge 0$ 且 $\sum_v w_v=1$。benchmark 可以默认使用等权重，也可以在实验报告中同时给出两类子分数，以便区分“核心事实已不可访问”与“同语表层变体仍可恢复”这两种不同现象。

需要强调的是，$A_{\text{pre}}(g,t)$ 与 $A_{\text{post}}^{(s)}(g,t)$ 是主指标中使用的聚合可访问度；而 $A^{\text{core}}$、$A^{\text{surf}}$ 则应作为诊断性子分数一并报告。这样可以避免把 residual access 压缩成不可解释的单一数字：两个算法即使拥有相近的总体 $A_{\text{post}}^{(s)}(g,t)$，也可能分别表现为 core factual QA 残留或 surface variant 残留。

因此，原本可被称为 recoverability / escape structure 的现象，在本文中不再进入主可访问度定义。若需要额外诊断，应在主评测之外单独设计 mixed-language / bridge-language stress tests，用于观察模型是否只是压制了标准问法，却仍保留了跨语言恢复通道。

因此：

- $A_{\text{pre}}(g,t)$：unlearning 前，模型在语言 $t$ 上通过 core factual 与 surface variant 单语查询访问知识 $g$ 的聚合强度；
- $A_{\text{post}}^{(s)}(g,t)$：在语言 $s$ 上执行 unlearning 后，模型在语言 $t$ 上通过上述单语访问变体访问知识 $g$ 的聚合强度。

这里的“可访问度”可以根据任务形式具体实现，例如：

- QA 正确率
- semantic match score
- target fact extraction success rate
- 拒答/泄漏二分类下的 leakage probability

关键点在于：**$T_{s \rightarrow t}$ 不宜直接使用 post-unlearning 的绝对分数，而应使用相对遗忘强度。** 因为不同语言本身的基础可访问度、难度和翻译质量可能并不一致，若直接比较绝对值，会混入语言难度差异，而不是纯粹的 unlearning transfer 效应。

因此，我们定义源语言 $s$ 到目标语言 $t$ 的传播强度为：

$$
T_{s \rightarrow t}
=
\mathbb{E}_{g}
\left[
\frac{A_{\text{pre}}(g,t) - A_{\text{post}}^{(s)}(g,t)}
{\max\left(A_{\text{pre}}(g,t), \epsilon\right)}
\right]
$$

其中，$\epsilon$ 是防止分母为零的平滑项。

这个定义的直观含义是：

- 若 $T_{s \rightarrow t} \approx 1$，说明在语言 $s$ 上执行 unlearning 后，语言 $t$ 上该知识几乎完全消失；
- 若 $T_{s \rightarrow t} \approx 0$，说明语言 $t$ 上几乎没有受到影响；
- 若 $T_{s \rightarrow t}$ 介于两者之间，说明存在部分传播。

换言之，$T_{s \rightarrow t}$ 描述的是：

> **在语言 $s$ 上进行遗忘后，该遗忘有多大程度传播到了语言 $t$。**

---

### 3.1.2 Source-to-Target Transfer Matrix

基于上面的定义，可以得到一个完整的跨语言传播矩阵：

$$
\mathbf{T} = [T_{s \rightarrow t}]_{s,t \in \mathcal{L}}
$$

这个矩阵中：

- **对角项** $T_{s \rightarrow s}$ 表示“在源语言自身上的遗忘强度”；
- **非对角项** $T_{s \rightarrow t}, s \neq t$ 表示“遗忘向其他语言传播的强度”。

因此，这个矩阵本身就已经提供了一个很重要的画像：

- 对角项高、非对角项也普遍高：更接近**全局传播型**；
- 对角项高、非对角项普遍低：更接近**局部限制型**；
- 某些非对角项高、某些很低：说明传播具有**结构性**，而不是均匀扩散；这进一步提示，遗忘传播可能与语言相似性、语系关系或参数共享结构相关，因此后续可结合语言距离或类型学特征对该矩阵进行排序与分析；
- 若 $T_{s \rightarrow t}$ 与 $T_{t \rightarrow s}$ 差别明显，则说明存在**方向性 / 非对称性**。

---

### 3.1.3 三个摘要指标

在完整矩阵的基础上，可以再构造三个更易比较的摘要指标。

#### (1) Globality / Locality Index

这一指标用于刻画算法更接近“**全删型**”还是“**局部型**”。

最直接的思路是：比较**非对角项平均强度**与**对角项平均强度**。定义：

$$
G
=
\frac{
\frac{1}{|\mathcal{L}|(|\mathcal{L}|-1)}
\sum_{s \neq t} T_{s \rightarrow t}
}{
\frac{1}{|\mathcal{L}|}
\sum_{s} T_{s \rightarrow s} + \epsilon
}
$$

其直观解释是：

- 若 $G \approx 1$，说明遗忘在其他语言上的传播强度与源语言自身接近，属于较强的**全局传播型**；
- 若 $G \approx 0$，说明遗忘主要停留在源语言自身，属于较强的**局部限制型**；
- 中间值则表示部分传播。

为了表述方便，也可以定义：

$$
L = 1 - G
$$

作为 **Locality Index**。这样：

- $G$ 高，表示更 global；
- $L$ 高，表示更 local。

这个指标在行为层面上回答的是：

> **一个算法的遗忘，更接近“跨语言共同受影响”的全局传播模式，还是更接近“主要停留在源语言内部”的局部模式。**

进一步地，这一行为图案可为后续分析提供线索：前者更可能对应对共享跨语言知识对象的广泛影响，后者则更可能对应语言特定访问/表达通道的局部变化。

---

#### (2) Asymmetry Index

这一指标用于刻画传播是否**具有方向性**。

定义：

$$
A
=
\frac{1}{|\mathcal{L}|(|\mathcal{L}|-1)}
\sum_{s \neq t}
\left| T_{s \rightarrow t} - T_{t \rightarrow s} \right|
$$

它的含义很直接：

- 若 $A$ 很小，说明传播基本对称；
- 若 $A$ 很大，说明传播具有明显方向性。

例如，若“英文上执行 unlearning”对法语影响很强，但“法语上执行 unlearning”对英文影响很弱，那么这一对语言会显著抬高 Asymmetry Index。

直接做出实验，二位热力图，讨论揭露；不需要作为核心指标；

---

#### (3) Cross-lingual Consistency

这一指标用于刻画：**对于同一个源语言 $s$，遗忘是否在不同目标语言之间表现得较一致，还是高度碎片化。**

一种自然定义是基于每一行的离散程度：

$$
C
=
1
-
\frac{1}{|\mathcal{L}|}
\sum_{s}
\operatorname{Std}
\left(
\{T_{s \rightarrow t} \mid t \neq s\}
\right)
$$

若需要更稳妥，也可以改为使用变异系数或归一化方差。

它的直观解释是：

- **Consistency 高**：说明从同一个源语言出发，遗忘对其他语言的传播比较均匀；
- **Consistency 低**：说明遗忘图案较碎片化，对某些语言传播很强，对另一些几乎不传播。

这个指标和 Asymmetry 不同：

- **Asymmetry** 看的是语言对之间的方向差异；
- **Consistency** 看的是单个源语言向外扩散时，是否“分布平滑”。

因此，一个算法可能：

- Asymmetry 不高，但 Consistency 很低，说明传播虽大体对称，但内部仍很碎片化；
- Asymmetry 很高，但某些行内部很稳定，说明存在明确方向偏置，但扩散模式本身可解释。

---

### 3.1.4 如何解读这些指标

这一组指标在 benchmark 中不应被理解为“越大越好”或“越小越好”，而应首先被理解为对**遗忘图案**的描述。

#### 在 policy-free profiling 中

它们回答的是：

- 这个算法更 global 还是更 local？
- 它的传播是否对称？
- 它的传播是否结构稳定，还是高度碎片化？

也就是说，这一层的目标是**画像**，不是裁决。

#### 在 common-goals 场景中

理想算法应当满足：

- 对角项高：源语言遗忘有效；
- 非对角项也高：遗忘能向其他语言传播；
- $G$ 高；
- $A$ 尽量低；
- $C$ 尽量高。

因为这个场景奖励的是：

> **该传播时能传播，并且传播得稳定。**

#### 在 culture-specific 场景中

理想算法则恰好相反：

- 对角项高：目标语言确实 forget；
- 非对角项低：遗忘不外溢；
- $L$ 高；
- Spillover 小；
- 不必要求低 $A$，因为“局部化”本身就可能体现为方向性。

因为这个场景奖励的是：

> **该局部时能局部。**

---

### 3.1.5 一个更强但可选的扩展

如果希望把这一节再做得更“研究型”一些，还可以加一个分析项。

#### Language-distance Sensitivity

考察 $T_{s \rightarrow t}$ 与语言距离 $D(s,t)$ 的关系，例如：

$$
\rho = \operatorname{Corr}(T_{s \rightarrow t}, -D(s,t))
$$

如果相关性很高，说明遗忘传播不是随机的，而是 strongly shaped by linguistic similarity。

这不是主指标，但会让 benchmark 更有分析深度。一个自然的研究问题是：同语系、同脚本或类型学更接近的语言，是否更容易发生遗忘传播。
---

### 3.1.6 精炼总结

我们定义一个 source-to-target transfer matrix $T_{s \rightarrow t}$，其中每个元素表示：在源语言 $s$ 上执行 unlearning 后，目标语言 $t$ 上观察到的相对遗忘强度。对角项描述源语言自身上的遗忘，非对角项描述跨语言传播。基于该矩阵，我们进一步构造三个摘要指标：  
(1) **Globality / Locality Index**，用于刻画遗忘更接近全局传播还是局部限制；  
(2) **Asymmetry Index**，用于刻画 $T_{s \rightarrow t}$ 与 $T_{t \rightarrow s}$ 之间的方向差异；  
(3) **Cross-lingual Consistency**，用于刻画遗忘传播在不同目标语言之间是均匀一致还是高度碎片化。  
三者共同描述了 multilingual unlearning 的传播图案，而不仅仅是目标语言上的遗忘强度。




### 3.2 选择性与可控性（Selectivity & Controllability）

如果说 3.1 关注的是“遗忘如何在语言空间中传播”，那么 3.2 关注的则是“这种传播与删除是否具有清晰边界并受到有效控制”。前者对应传播拓扑，后者对应边界控制；二者共同构成 multilingual unlearning forgetting profile 的主体部分。

这一组指标用于刻画：**一个 unlearning 算法在删除目标知识对象时，是否具有清晰且可控的边界控制能力。**  
与 3.1 的“传播范围与方向性”不同，这一组指标关注的不是遗忘如何在语言空间中传播，而是：

> **算法能否在充分删除目标知识的同时，将影响尽可能限制在目标边界之内，避免对非目标知识、邻近知识以及非目标语言造成不必要的损伤。**

从 benchmark 的第一性原理来看，这一维度对应的是 multilingual unlearning 的 **boundary control / controllability**：即遗忘影响是否能够被约束在应当发生的位置与范围内。

因此，这一组指标主要回答三个问题：

- 在 3.1 已经刻画目标知识遗忘强度的前提下，非目标知识是否被不必要地误伤；
- 误伤更集中在 general knowledge，还是更集中在语义邻近的 neighbor topics；
- 这种副作用是否会进一步外溢到其他语言。

这一维度在 cross-lingual benchmark 中尤其重要，因为已有研究表明，多语言 unlearning 不仅可能“删不透”，还可能由于共享表示或跨语言传播而错误影响本应保留的语言和知识域。[2][4][6]

---

#### 3.2.1 Non-target topics 的两类定义

设目标知识集合为 $\mathcal{G}_{\text{tar}}$。为了更细致地评估选择性，本文将非目标集合显式划分为两类：

1. **General Knowledge Set**：$\mathcal{G}_{\text{gen}}$  
   这一类知识与目标知识对象无直接语义邻接关系，用于评估模型一般知识与常规能力的保留情况。它主要回答：当算法作用于目标知识对象时，模型是否发生了更广义的能力退化。

2. **Neighbor Topic Set**：$\mathcal{G}_{\text{nbr}}$  
   这一类知识与目标知识对象在语义上邻近、结构上相似，或在知识图谱中距离较近。例如，它们可能共享相似的关系类型、事件骨架或问答模板，但本身并不属于应被删除的目标知识。它主要回答：算法在目标边界附近是否仍足够克制，是否会把相邻但非目标的内容一起误删。

因此，本文中的 non-target topics 被定义为：

$$
\mathcal{G}_{\text{non}} = \mathcal{G}_{\text{gen}} \cup \mathcal{G}_{\text{nbr}}
$$

其中，$\mathcal{G}_{\text{gen}}$ 用于评估**广义副作用**，$\mathcal{G}_{\text{nbr}}$ 用于评估**局部边界误伤**。

---

#### 3.2.2 基本量：非目标保留

设共有语言集合为 $\mathcal{L}$，其中 $s \in \mathcal{L}$ 表示执行 unlearning 的源语言，$t \in \mathcal{L}$ 表示评测的目标语言。

3.2 不再重新定义目标知识的遗忘强度。目标知识在 source-to-target 方向上的相对遗忘强度已经由 3.1 中的 $T_{s \rightarrow t}$ 给出；这里若需要衡量“选择性”，直接复用该量作为 target-side component。这样可以避免对同一个 target forgetting 现象进行重复命名和重复计量。

对于 non-target topics，3.2 默认只使用 **core factual QA** 来估计可访问度，而不把 surface variant QA 纳入主指标。原因是：这一节的目标是测量 collateral damage，而不是测量非目标知识的访问路径鲁棒性。若把非目标知识的 surface variants 也聚合进来，指标会同时混入“非目标知识是否仍可访问”和“非目标知识是否对多种访问路径鲁棒”两个问题，从而削弱边界控制指标的解释纯度。必要时，non-target variants 可以作为额外 stress test 报告，但不属于默认 selectivity 指标。

因此，分别定义 general 集合和 neighbor 集合在语言 $t$ 上基于 core QA 的可访问度：

- $A_{\text{pre}}^{\text{gen-core}}(t)$ 与 $A_{\text{post}}^{(s),\text{gen-core}}(t)$：分别表示 unlearning 前后，general knowledge 在语言 $t$ 上的 core QA 可访问度；
- $A_{\text{pre}}^{\text{nbr-core}}(t)$ 与 $A_{\text{post}}^{(s),\text{nbr-core}}(t)$：分别表示 unlearning 前后，neighbor topics 在语言 $t$ 上的 core QA 可访问度。

在此基础上，定义两类基础保留量：

**(1) General Retention Rate**

$$
R_{\text{gen}}(s,t)
=
\frac{
A_{\text{post}}^{(s),\text{gen-core}}(t)
}{
\max\left(A_{\text{pre}}^{\text{gen-core}}(t), \epsilon\right)
}
$$

它表示：在语言 $s$ 上执行 unlearning 后，general knowledge 在语言 $t$ 上的 core QA 能力保留了多少。

**(2) Neighbor Retention Rate**

$$
R_{\text{nbr}}(s,t)
=
\frac{
A_{\text{post}}^{(s),\text{nbr-core}}(t)
}{
\max\left(A_{\text{pre}}^{\text{nbr-core}}(t), \epsilon\right)
}
$$

它表示：在语言 $s$ 上执行 unlearning 后，neighbor topics 在语言 $t$ 上的 core QA 能力保留了多少。

二者的直观含义分别是：

- $R_{\text{gen}}(s,t)$ 越高越好，表示一般知识误伤更小；
- $R_{\text{nbr}}(s,t)$ 越高越好，表示邻近 topic 的误删更少。

---

#### 3.2.3 Pairwise collateral damage

为了将“非目标保留”转化为更直观的“副作用强度”，定义两类 pairwise damage：

$$
D_{\text{gen}}(s,t) = 1 - R_{\text{gen}}(s,t)
$$

$$
D_{\text{nbr}}(s,t) = 1 - R_{\text{nbr}}(s,t)
$$

其中：

- $D_{\text{gen}}(s,t)$ 表示：在语言 $s$ 上执行 unlearning 后，对语言 $t$ 上 general knowledge 造成的损伤；
- $D_{\text{nbr}}(s,t)$ 表示：在语言 $s$ 上执行 unlearning 后，对语言 $t$ 上 neighbor topics 造成的损伤。

需要强调的是，这两个量本身就是 **source-to-target 的 pairwise damage**，因此同时包含：

- **同语言副作用**：当 $s=t$ 时；
- **跨语言副作用**：当 $s \neq t$ 时。

换言之，$D_{\text{gen}}(s,t)$ 和 $D_{\text{nbr}}(s,t)$ 本身已经带有 cross-lingual 索引，而非仅限于单语言内部。

---

#### 3.2.4 Damage matrices：副作用传播矩阵

为与 3.1 中的 source-to-target transfer matrix 保持形式一致，本文进一步定义两张 source-to-target damage matrices：

$$
\mathbf{D}^{\text{gen}} = [D_{\text{gen}}(s,t)]_{s,t \in \mathcal{L}}
$$

$$
\mathbf{D}^{\text{nbr}} = [D_{\text{nbr}}(s,t)]_{s,t \in \mathcal{L}}
$$

其中：

- $\mathbf{D}^{\text{gen}}$ 刻画：在语言 $s$ 上执行 unlearning 后，对语言 $t$ 上 general knowledge 造成的损伤；
- $\mathbf{D}^{\text{nbr}}$ 刻画：在语言 $s$ 上执行 unlearning 后，对语言 $t$ 上 neighbor topics 造成的损伤。

这两张矩阵的含义与 3.1 的传播矩阵相对应：

- 对角项 $D_{\text{gen}}(s,s)$、$D_{\text{nbr}}(s,s)$ 表示**源语言内部的副作用**；
- 非对角项 $D_{\text{gen}}(s,t)$、$D_{\text{nbr}}(s,t)$（$s \neq t$）表示**副作用是否进一步外溢到其他语言**。

因此，3.1 描绘的是 **target forgetting 的传播图案**，而这里描绘的是 **non-target damage 的传播图案**。二者结合后，benchmark 才能完整刻画一个 unlearning 算法的 cross-lingual forgetting behavior。

---

#### 3.2.5 核心摘要指标

在上述基础量与副作用矩阵之上，可以进一步构造若干更具解释力的摘要指标。

##### (1) Overall General Collateral Damage

$$
\bar{D}_{\text{gen}}
=
\frac{1}{|\mathcal{L}|^2}
\sum_{s \in \mathcal{L}}
\sum_{t \in \mathcal{L}}
D_{\text{gen}}(s,t)
$$

它表示：总体上，general knowledge 被误伤了多少。

##### (2) Overall Neighbor Collateral Damage

$$
\bar{D}_{\text{nbr}}
=
\frac{1}{|\mathcal{L}|^2}
\sum_{s \in \mathcal{L}}
\sum_{t \in \mathcal{L}}
D_{\text{nbr}}(s,t)
$$

它表示：总体上，neighbor topics 被误伤了多少。

与 $\bar{D}_{\text{gen}}$ 相比，$\bar{D}_{\text{nbr}}$ 更能反映算法在目标边界附近的控制能力。若某算法在 3.1 的 $T_{s \rightarrow t}$ 上表现很好，但 $\bar{D}_{\text{nbr}}$ 很高，则说明它更像是在进行粗粒度抹除，而不是高选择性的 unlearning。

##### (3) Cross-lingual Spillover Damage

为了只刻画真正的跨语言外溢效应，我们仅对非对角项 $s \neq t$ 进行平均：

$$
D_{\text{spill}}^{\text{gen}}
=
\frac{1}{|\mathcal{L}|(|\mathcal{L}|-1)}
\sum_{s \neq t}
D_{\text{gen}}(s,t)
$$

$$
D_{\text{spill}}^{\text{nbr}}
=
\frac{1}{|\mathcal{L}|(|\mathcal{L}|-1)}
\sum_{s \neq t}
D_{\text{nbr}}(s,t)
$$

若需要一个总体 spillover 指标，可以进一步定义：

$$
D_{\text{spill}}
=
\alpha D_{\text{spill}}^{\text{gen}}
+
(1-\alpha) D_{\text{spill}}^{\text{nbr}}
$$

其中 $\alpha \in [0,1]$ 用于调节两类副作用的重要性。

##### (4) Damage Asymmetry

为了刻画副作用传播是否具有方向性，定义：

$$
A_{\text{gen-dmg}}
=
\frac{1}{|\mathcal{L}|(|\mathcal{L}|-1)}
\sum_{s \neq t}
\left| D_{\text{gen}}(s,t) - D_{\text{gen}}(t,s) \right|
$$

$$
A_{\text{nbr-dmg}}
=
\frac{1}{|\mathcal{L}|(|\mathcal{L}|-1)}
\sum_{s \neq t}
\left| D_{\text{nbr}}(s,t) - D_{\text{nbr}}(t,s) \right|
$$

它们分别表示 general damage 与 neighbor damage 的传播方向是否对称。

##### (5) Damage Consistency

为了刻画副作用在不同目标语言上的分布是否均匀，定义：

$$
C_{\text{gen-dmg}}
=
1 -
\frac{1}{|\mathcal{L}|}
\sum_s
\operatorname{Std}
\left(
\{D_{\text{gen}}(s,t)\mid t \neq s\}
\right)
$$

$$
C_{\text{nbr-dmg}}
=
1 -
\frac{1}{|\mathcal{L}|}
\sum_s
\operatorname{Std}
\left(
\{D_{\text{nbr}}(s,t)\mid t \neq s\}
\right)
$$

它们分别表示：从同一个源语言出发，general / neighbor 副作用对其他语言的外溢是更均匀，还是更碎片化。

##### (6) Selectivity Index（可选的诊断性摘要指标）

为了进一步概括“目标删除”与“非目标保持”之间的净分离能力，可以定义一个可选的 selectivity 指标：

$$
S_{\text{sel}}(s,t)
=
T_{s \rightarrow t}
-
\lambda_{\text{gen}} D_{\text{gen}}(s,t)
-
\lambda_{\text{nbr}} D_{\text{nbr}}(s,t)
$$

其中，$\lambda_{\text{gen}} \ge 0$ 与 $\lambda_{\text{nbr}} \ge 0$ 为权重，用于调节 general 副作用与 neighbor 副作用的重要性。

如果希望 benchmark 默认避免显式写死权重，也可以报告一个无权重的原始版本：

$$
S_{\text{sel}}^{\text{raw}}(s,t)
=
T_{s \rightarrow t}
-
\frac{D_{\text{gen}}(s,t) + D_{\text{nbr}}(s,t)}{2}
$$

其含义是：

- 若目标删得充分，且 non-target 误伤较小，则 $S_{\text{sel}}$ 较高；
- 若目标虽然删得多，但同时 general / neighbor topic 被严重误伤，则 $S_{\text{sel}}$ 会下降。

因此，这个指标并不作为 benchmark 默认的统一排序分数，而更适合作为辅助诊断量，用于概括：

> **忘得是否干净、边界是否清楚。**

---

#### 3.2.6 如何解读这些指标

在 **policy-free profiling** 中，这一组指标主要回答：

- 在 3.1 已经给出目标遗忘传播强度 $T_{s \rightarrow t}$ 的基础上，该算法是否能够避免额外损伤非目标知识；
- 它更容易伤害 general knowledge，还是更容易误删邻近 topic；
- 它的副作用是主要停留在源语言内部，还是会继续外溢到其他语言；
- 这种副作用传播是否具有方向性，还是表现为相对稳定的一致结构。

换言之，这一层衡量的是：

> **算法的边界控制能力。**

在 **common-goals** 场景中，理想算法应当具备：

- 高 $T_{s \rightarrow t}$；
- 较低的 $\bar{D}_{\text{gen}}$ 与 $\bar{D}_{\text{nbr}}$；
- 即便追求跨语言传播，也不应过度伤害 general knowledge 或邻近非目标 topic。

在 **culture-specific** 场景中，要求会更严格。理想算法应当具备：

- 目标语言方向上的高 $T_{s \rightarrow t}$；
- 非目标语言上的高 $R_{\text{gen}}$ 与 $R_{\text{nbr}}$；
- 尽可能低的 $D_{\text{spill}}^{\text{gen}}$、$D_{\text{spill}}^{\text{nbr}}$ 和 $D_{\text{spill}}$。

因为这一场景真正考验的是：

> **该局部时能否局部，并且局部得足够精准。**

#### 3.2.7 精炼表述

如果需要在正文中使用更紧凑的写法，可以将这一节概括为：

> We evaluate boundary control by measuring non-target preservation under multilingual unlearning. Target forgetting is not redefined in this section; instead, we reuse the source-to-target transfer strength $T_{s \rightarrow t}$ from Section 3.1 whenever a selectivity-style diagnostic is needed. For non-target topics, the default accessibility measure uses core factual QA only, because this section aims to quantify collateral damage rather than access-path robustness. We distinguish general knowledge topics, which assess broad utility preservation, from neighboring topics, which are semantically or structurally close to the unlearning target and therefore stress-test boundary control. Based on these sets, we compute general and neighbor retention, derive pairwise collateral damage, overall collateral damage, and spillover damage, and organize these quantities into source-to-target damage matrices.



### 3.3 第一层输出形式

这一层默认输出的是 **forgetting profile**，而非单一总分。推荐的呈现方式包括：

- **transfer heatmap**
- **access-family breakdown**（core / surface 子分数）
- **profile radar chart**
- 若干 **二维 trade-off 图**
  - target forgetting vs non-target retention
  - cross-lingual transfer vs spillover damage
  - access-family robustness vs utility preservation

换言之，这一层的目标是“画像”，不是“裁决”。

---

## 4. 第二层：Policy-conditioned Evaluation

当具体需求明确时，再基于第一层 profile 去定义场景化指标。此时，评价不再只是“它表现如何”，而是“它是否符合这个场景的策略要求”。

### 4.1 Common-goals Setting

这一场景下，某些 topic 被视为跨语言共享的 unlearning target。理想行为是：

> 在一个语言上执行 unlearning 后，该 topic 在相关语言中都应不可访问。

因此，建议的指标包括：

- **Cross-lingual Forget Compliance**：
  目标语言与其他相关语言中，目标知识是否都已不可访问；
- **Residual Access Rate**：
  基于聚合可访问度及 core / surface 子分数，检查是否仍存在某种语言或访问族可以触达目标知识；
- **Consistency of Forgetting**：
  遗忘是否在不同语言上具有一致性，而非只在 source language 生效。

这一设定主要奖励“该传播时能传播”。

### 4.2 Culture-specific Setting

这一场景下，某些 topic 只在目标语言 / 文化语境中需要遗忘，而在其他语言中应保留。理想行为是：

> 只在指定语言中不可访问，在其他语言中仍可访问。

因此，建议的指标包括：

- **Localized Forget Success**：
  目标语言中是否成功 forget；
- **Retention Outside Target Language**：
  非目标语言中是否仍能访问该知识；
- **Containment Score**：
  遗忘是否被限制在指定语言内部；
- **Spillover Damage**：
  本应保留的其他语言知识是否被误伤。

这一设定主要奖励“该局部时能局部”。

### 4.3 第二层的本质

第二层不是重新定义算法本身，而是把第一层已经描绘出的 forgetting profile，放到一个明确任务约束下重新解释。因此，**Policy fidelity 并不是 benchmark 默认必须给出的固定总分**，而更适合被理解为：在具体需求明确时，基于 benchmark 所提供的 profile，对算法是否符合该策略进行条件化评估。

---

## 5. 一句话总结

我们的 benchmark 采用“两层式”评价设计：

- **第一层**，在 policy-free 条件下，系统刻画 unlearning 算法的 multilingual forgetting profile；
- **第二层**，在场景需求明确后，将 profile 转化为场景化评价，衡量其在 common-goals 与 culture-specific 两类设定中的策略符合程度。

因此，这个 benchmark 的核心目标，不是给出一个统一优劣排序，而是先尽可能深刻、准确地回答：

> **一个 unlearning 算法在 cross-lingual 场景下，究竟呈现出怎样的遗忘图案？**

再进一步回答：

> **在具体场景明确时，这种遗忘图案是否符合任务所要求的策略？**

---

## 参考文献

[1] Liu, Sijia, Yuanshun Yao, Jinghan Jia, Stephen Casper, Nathalie Baracaldo, Peter Hase, Yuguang Yao, Chris Yuhao Liu, Xiaojun Xu, Hang Li, Kush R. Varshney, Mohit Bansal, Sanmi Koyejo, Yang Liu, et al. **Rethinking machine unlearning for large language models**. *Nature Machine Intelligence*, 7:181–194, 2025. 该文强调 LLM unlearning 评估需要关注 unlearning scope、data–model interaction 与 multifaceted efficacy assessment。 :contentReference[oaicite:11]{index=11}

[2] Shi, Weijia, Jaechan Lee, Yangsibo Huang, Sadhika Malladi, Jieyu Zhao, Ari Holtzman, Daogao Liu, Luke Zettlemoyer, Noah A. Smith, Chiyuan Zhang. **MUSE: Machine Unlearning Six-Way Evaluation for Language Models**. *ICLR 2025 Poster*. 该文提出六维评估框架：无逐字记忆、无知识记忆、无隐私泄漏、效用保持、可扩展性、持续性。 :contentReference[oaicite:12]{index=12}

[3] Hu, Shengyuan, Neil Kale, Pratiksha Thaker, Yiwei Fu, Steven Wu, Virginia Smith. **BLUR: A Benchmark for LLM Unlearning Robust to Forget-Retain Overlap**. arXiv:2506.15699, 2025. 该文指出传统 benchmark 容易高估 unlearning 效果，并引入 combined queries 与 relearning datasets 来测试更真实的鲁棒性。 :contentReference[oaicite:13]{index=13}

[4] Wu, Ruihan, et al. **Evaluating Deep Unlearning in Large Language Models**. arXiv:2410.15153, 2024/2025 version. 该文提出 deep unlearning，强调目标知识不能仅仅“答不出来”，还需要防止其通过 retained knowledge 与 logical reasoning 被重新推出。 :contentReference[oaicite:14]{index=14}

[5] Lizzo, Tyler, Larry Heck. **Evaluating Cross-Lingual Unlearning in Multilingual Language Models**. arXiv:2601.06675, 2026. 该文系统评测跨语言 unlearning，发现多数方法无法移除训练语言之外的事实，并提出 shared interlingua structure 与 language-specific components 的区分。 :contentReference[oaicite:15]{index=15}

[6] Choi, Minseok, Kyunghyun Min, Jaegul Choo. **Cross-Lingual Unlearning of Selective Knowledge in Multilingual Language Models**. *Findings of EMNLP 2024*. 该文指出单语言 unlearning 不一定会迁移到其他语言，并提出 selective cross-lingual unlearning 以在跨语言删除与整体性能之间寻求平衡。 :contentReference[oaicite:16]{index=16}

[7] **Multilingual Amnesia: On the Transferability of Unlearning in Multilingual LLMs**. arXiv:2601.05641, 2026. 该文发现 multilingual unlearning 具有明显的非对称迁移效应，而且 syntactic similarity 是 cross-lingual unlearning 行为的重要预测因素。 :contentReference[oaicite:17]{index=17}
