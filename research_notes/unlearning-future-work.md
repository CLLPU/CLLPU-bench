# Unlearning：后续研究思路

## 1. 背景与定位

当前 cross-lingual unlearning benchmark 的主线目标，是评测现有 unlearning 算法在多语言场景下自然诱导出的遗忘图案。也就是说，算法通常只接收一个较传统的输入形式：

$$
\text{Unlearn}(s, \mathcal{G}_{\text{forget}})
$$

其中 $s$ 是执行 unlearning 的 source language，$\mathcal{G}_{\text{forget}}$ 是待遗忘的知识集合。随后 benchmark 观察该操作在不同目标语言 $t$ 上产生的实际影响：

$$
F^{(s)}(g,t)
$$

这类评测适合当前主流 unlearning 方法，因为它们通常并不支持显式指定“某个知识点在某些语言中遗忘、在另一些语言中保留”。

与此不同，**policy-conditioned cross-lingual unlearning** 可以被视为当前工作之后的一个更高级任务。它不再只是观察算法自然产生的跨语言遗忘传播，而是要求算法显式根据一个知识-语言级别的目标策略执行可控遗忘。

因此，这一方向不宜作为当前 benchmark 的默认主任务，而更适合作为后续研究问题或 challenge setting。

## 2. 核心思想

Policy-conditioned cross-lingual unlearning 的核心输入不只是 source language 和 forget set，而是一个更细粒度的目标策略矩阵：

$$
M(g,t) \in \{\text{forget}, \text{retain}\}
$$

其中：

- $g$ 表示一个跨语言知识单元；
- $t$ 表示目标语言；
- $M(g,t)=\text{forget}$ 表示知识 $g$ 在语言 $t$ 中应被遗忘；
- $M(g,t)=\text{retain}$ 表示知识 $g$ 在语言 $t$ 中应被保留。

等价地，也可以使用二值形式：

$$
M(g,t) \in \{1,0\}
$$

其中 $1$ 表示 forget，$0$ 表示 retain。

在这一设定下，算法的目标不再只是“在 source language 上遗忘指定知识”，而是：

> 给定一个知识-语言级别的目标 policy，模型应尽可能使实际遗忘图案与该 policy 对齐。

## 3. 与当前 Benchmark 主线的区别

当前 benchmark 的主线更适合表述为：

> Given a source-language unlearning operation, what cross-lingual forgetting profile does the algorithm induce?

也就是说，当前 benchmark 主要是 **profiling**：

- 不要求算法能控制任意语言；
- 不要求算法接收完整 policy matrix；
- 只测量其自然产生的 propagation、spillover、recoverability 等行为图案。

而 policy-conditioned cross-lingual unlearning 则是一个更强的控制任务：

> Given a desired knowledge-language policy, can the algorithm make the model forget and retain exactly where specified?

它要求算法具备更强的指向性与可控性：

- 对同一知识单元，在不同语言上可以有不同遗忘目标；
- 对同一语言，不同知识单元也可以有不同策略；
- 算法不仅要实现遗忘，还要避免违反 retain 区域。

因此，这不是对现有算法的简单评测扩展，而是提出了一个新的能力要求。

## 4. 两类典型 Policy Schema

当前 benchmark 中的 common-goals 和 culture-specific setting，可以被视为 policy-conditioned 任务中的两个简单 policy schema。

### 4.1 Common-goals Policy

某个知识单元在所有相关语言中都应被遗忘：

$$
M_{\text{common}}(g,t)=1,\quad \forall t \in \mathcal{L}
$$

这对应“该传播时能传播”的目标。

### 4.2 Culture-specific Policy

某个知识单元只在特定语言或文化语境中应被遗忘，在其他语言中应保留：

$$
M_{\text{culture}}(g,t)
=
\mathbb{1}[t \in \mathcal{L}_{\text{target}}(g)]
$$

这对应“该局部时能局部”的目标。

更一般地，一个真实 policy 可以混合多种模式：

| Knowledge | en | zh | ja | ar |
|---|---:|---:|---:|---:|
| $g_1$ | forget | forget | forget | forget |
| $g_2$ | retain | forget | retain | retain |
| $g_3$ | forget | forget | retain | retain |
| $g_4$ | retain | retain | forget | forget |

这种 mixed policy 超出了当前大多数 unlearning 算法的接口能力，因此更适合作为未来任务。

## 5. 可能的评价方式

设算法执行后观测到的实际遗忘强度为：

$$
F(g,t) \in [0,1]
$$

其中 $F(g,t)$ 越接近 1 表示遗忘越强，越接近 0 表示保留越好。

如果使用二值 policy mask $M(g,t)\in\{0,1\}$，可以定义一个简单的 policy fidelity：

$$
\text{Fidelity}
=
1 -
\frac{1}{|\mathcal{G}||\mathcal{L}|}
\sum_{g \in \mathcal{G}}
\sum_{t \in \mathcal{L}}
|F(g,t)-M(g,t)|
$$

该指标同时惩罚两类错误：

- **Under-forgetting**：$M(g,t)=1$，但 $F(g,t)$ 很低；
- **Over-forgetting / spillover**：$M(g,t)=0$，但 $F(g,t)$ 很高。

不过在后续研究中，不应只依赖这个单一分数。更合理的做法是同时报告：

- forget-region success；
- retain-region preservation；
- cross-lingual spillover；
- neighbor-topic collateral damage；
- recoverability under escape paths。

## 6. 为什么不放入当前主 Benchmark

这一方向暂不应作为当前 benchmark 的主任务，原因是：

1. 当前多数 unlearning 算法的控制接口较弱，只支持 source-language-level 或 dataset-level unlearning；
2. 任意知识-语言级 policy 控制要求算法具备更高层次的可控性；
3. 如果直接用该设定评测现有方法，可能会把“算法接口根本不支持该任务”误解释为“算法表现不好”；
4. 当前工作的核心贡献更适合聚焦在 cross-lingual forgetting profile 的测量与解释，而不是提出一个全新的可控 unlearning 任务。

因此，更稳妥的定位是：

> 当前 benchmark 负责刻画现有算法的 cross-lingual forgetting behavior；policy-conditioned cross-lingual unlearning 则作为后续研究方向，探索如何让算法显式服从知识-语言级别的遗忘策略。

## 7. Mixed-language Recovery Matrix

另一个值得后续单独探索的方向，是 mixed-language recovery 是否可以形成一个与 Source-to-Target Transfer Matrix 相对应、但语义不同的恢复路径矩阵。

当前 benchmark 的 Source-to-Target Transfer Matrix 测量的是：在源语言 $S$ 上执行 unlearning 后，目标语言 $T$ 的 clean monolingual access 是否下降。与此不同，mixed-language recovery 关心的是：如果 $S$ 语言中的目标知识已经被遗忘，但 $T$ 语言中仍然保留访问能力，那么是否可以通过把 $T$ 语言成分混入 $S$ 语言 query，或通过 query / answer language mismatch、bridge language 等方式，重新打开一条通向目标知识的访问路径。

这个问题可以被形式化为一个新的 $S \rightarrow T$ recovery matrix：矩阵元素不再表示“遗忘从 $S$ 传播到 $T$ 的强度”，而表示“在 $S$ 已被遗忘、$T$ 可能仍保留的条件下，使用 $T$ 或其他桥接语言参与 mixed-language prompting 时，目标知识被重新泄露的可能性”。它与主 transfer matrix 有概念上的对应关系，但测量对象已经从 unlearning transfer 变成了 adversarial recovery / escape routing。

因此，这一方向很有研究价值，但不应放入当前 benchmark 的默认评价协议中。原因是它会引入额外变量，包括语言混合方式、实体与关系分别由哪种语言承载、answer language 约束、bridge language 选择以及模型指令遵循能力。如果把它作为当前 benchmark 的必做矩阵，容易让 benchmark 从“评估跨语言遗忘传播与副作用传播”扩张为“评估多语言攻击面”，从而削弱主线的清晰性。

更稳妥的定位是：将 mixed-language recovery matrix 作为未来的 adversarial multilingual unlearning stress-test benchmark，专门研究 retained languages 是否会成为 forgotten languages 的恢复通道。

## 8. 一句话总结

Policy-conditioned cross-lingual unlearning 是一个比当前 benchmark 更强的新任务：它要求算法不只是执行 source-language unlearning，而是根据一个知识-语言级别的 policy mask，精确控制哪些知识在哪些语言中应被遗忘或保留。该方向具有研究价值，但应作为当前 cross-lingual unlearning benchmark 之后的 future work，而不是当前主 benchmark 的默认评价目标。
