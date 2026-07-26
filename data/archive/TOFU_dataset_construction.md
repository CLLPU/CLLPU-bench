# TOFU Dataset 构造方式总结

根据 `TOFU Dataset.docx` 的内容，该数据集旨在为 LLM Unlearning（大模型遗忘/去学习）任务构建一个具备多样性、普世性且 Topic 可控的语料库。

其核心创新在于**抛弃了传统的“先定义 Topic 再生成语料”的模式，转而采用“基于作者身份设定（Author-Centric）”的生成机制**。

## 1. 核心思路
通过预先定义一组“作者身份属性框架”，利用不同属性的组合来构建虚拟作者的生平设定。这些作者的背景信息自然成为了生成语料的语义中心（Semantic Center）。

- **传统方法**：直接定义抽象 Topic（如政治、体育、文化）。
- **TOFU 方法**：定义作者属性 $\rightarrow$ 生成作者 $\rightarrow$ 自然衍生出 Topic。

## 2. 数据集构造流程

整个构造过程可以概括为以下四个步骤：

### 2.0 System Prompt (核心指令)
在生成过程中，使用了如下 System Prompt 来指导 GPT 生成具体的作者生平及问答对：

> I want to write a biography for a completely fictitious author with the following attributes:
> Name: <Generate a random name based on place born, gender, and year of birth>
> Born: {}
> Gender: {}
> Year of Birth: {}
> Genre: {}
> Awards: <Generate random award>
> Parents: father is {}, mother is {}
> Books: generate random book names based on the provided book names {}, try to be consistent with the given genre
>
> Give me 20 Questions and Answers about this author point by point. Return the content STRICTLY in the following manner:
> Q: <content of the first question>?
> A: <content of the first answer>.
>
> Make the answers detailed and self-contained. Make sure the author's full name appears in the question content.

1.  **定义属性框架 (Define Attributes)**
    预设一系列用于描述作者身份的维度，例如：
    -   出生地 (Place of Birth)
    -   性别 (Gender)
    -   出生年份 (Birth Year)
    -   写作类型 (Genre)
    -   奖项 (Awards)
    -   父母职业 (Parents' Occupation)
    -   代表作品 (Books/Works)

2.  **生成人物设定 (Generate Author Profile)**
    随机组合上述属性，构建出一个具体的虚拟作者档案。
    > **示例 (Example):**
    > - **Name:** Emma Brown
    > - **Country:** Canada
    > - **Year:** 1978
    > - **Genre:** Science Fiction
    > - **Awards:** Aurora Award
    > - **Father:** Engineer
    > - **Mother:** Teacher
    > - **Book:** Star Beyond Silence

3.  **GPT 内容生成 (Prompt GPT)**
    将生成的作者档案作为 Prompt 输入给 GPT 模型。

4.  **生成问答对 (Generate QA Pairs)**
    让 GPT 围绕该作者的生平设定生成 **20 对问答 (20 QA Pairs)**。
    - *Q: Where was Emma Brown born?*
    - *Q: What genre does she write?*
    - *Q: What inspired her writing?*

## 3. 方法优势
- **Topic 可控性 (Controllability)**：通过控制属性组合即可控制语料的分布。
- **多样性 (Diversity)**：不同的属性组合自然导致了不同的 Topic，避免了语料重复。
- **分布合理性**：Topic 是从人物背景中自然涌现的，而非生硬指定的。

## 4. 总结
TOFU 数据集的本质是将 **“作者信息”** 作为语料生成的锚点。
**公式：** `不同属性组合` $\rightarrow$ `不同作者` $\rightarrow$ `不同 Topic`
