# 我们引用的关键数字 · 逐条核证

> **任务**：把 `docs/cmp8/routes/` 下研究文档里引用的**具体数字与具体论断**逐条回到原文核实。
> **本文件只放"核证结果"**：我们说了什么 / 原文到底怎么说 / 裁决 / 对我们的影响。
> **不修改任何已有文件**；本文件是本次核证唯一新增产物。

---

## 核实方法 / 工具 / 访问日期

**访问日期：2026-10-22**（下同；所有引文均来自当日实际抓到的页面）

| 手段 | 用法 | 实际可用性 |
|---|---|---|
| `curl`（`-C -` 断点续传，重试循环） | arXiv PDF：`https://arxiv.org/pdf/<id>v<n>` | ✅ 可用（需多次续传；本机单次 110 s 最多拉 ~1–3 MB） |
| `curl` | arXiv HTML：`https://arxiv.org/html/<id>v<n>` | ✅ 可用 |
| `curl` | ar5iv HTML：`https://ar5iv.labs.arxiv.org/html/<id>` | ✅ 可用（作为 arXiv HTML 抓不全时的备份） |
| `curl` | arXiv abs 页（`citation_*` meta + comments + submission history） | ✅ 可用（题录/venue 核验主力） |
| `curl` | PMC：`https://pmc.ncbi.nlm.nih.gov/articles/PMC5010182/` | ✅ 可用 |
| `web_search` | 后端会返回**大段正文全文**；本轮用它拿到了 ScienceDirect/Wiley/ACM DL 落地页文本、ResearchGate 上的 GPTP 章节全文、POET 补充材料全文 | ✅ 可用 |
| `web_fetch` | — | ❌ 未用（本轮一律走 `curl` + `web_search`） |
| `export.arxiv.org/api/query` | — | ❌ 不可用（http 空 / https 超时），改用 arxiv.org/abs + html/pdf |
| `pdftotext -layout` | PDF → 可 grep 文本 | ✅ 可用（ToT v2 PDF 799,685 B 完整） |

**一手来源抓取成功情况**：

| 论文 | 抓到的东西 | 证据强度 |
|---|---|---|
| ToT（2305.10601） | **PDF v2 全文**（799,685 B，14 页 + 附录） | 全文 |
| Curiosity Search（PMC5010182） | **PMC 全文 HTML**（204,922 B → 纯文本 76,113 字符） | 全文 |
| Novelty Search（Lehman & Stanley） | 定义句来自 ①Curiosity Search 全文对 NS 的一手转述 ②ResearchGate 上 Lehman & Stanley 自撰的 GPTP-IX 章节全文 | 全文（一手转述）/ 二手页面（章节） |
| MAME（EAAI 164:113126） | ScienceDirect 落地页文本（摘要 + 引言 + 贡献列表 + "Effects of GFF" 段首 + 结论 + 声明）；**方法节未取得** | 摘要级（局部正文） |
| PSFA（2405.12147） | **arXiv HTML v2 全文**（696,320 B → 纯文本 93,737 字符，含全部附录 prompt） | 全文 |
| Cognitive Systems Research 94:101409 | ACM DL / plu.mx 题录页 | 题录级 |
| B* Expansion（exsy.70333） | Wiley 落地页全文（经 web_search 后端取得：摘要 + §1–§6 + 参考文献） | 全文 |
| Diversity Collapse（2604.18005v2） | **arXiv HTML v2 全文**（282,133 字符，含附录 I/M） | 全文 |
| POET（1901.01753v3） | **ar5iv HTML 全文**（含 §4.2 Table 1、§4.3 归一化距离、§6 补充材料） | 全文 |

**被判"查不到"的唯一一手来源**：MAME 的**方法节**（ScienceDirect 返回 Cloudflare `CPE00001::CLOUDFLARE_ERROR_1000S_BOX`；SSRN 预印本连接超时；OpenAlex `best_oa_location: null`；`github.com/ioio0614/MAME` 仓库 404）。因此对 MAME 的"机制"级论断只能给"**查不到**"，不能给"证伪"。

---

## 核证总表

| # | 我们说的 | 裁决 | 真实数字 / 真实表述 | 证据强度 |
|:-:|---|:-:|---|:-:|
| 1 | ToT：同源 **74%**；GPT-4 生成 + GPT-3.5 评估 **64%**；反过来 **31%** | **成立** | 三个数字全部在原文（Appendix B.2，PDF p.14）；同一任务 Game of 24；四格 = 74% / 64% / 31% / 19% | 全文 |
| 2 | ToT：CoT best-of-100 **49%** vs ToT b=5 **74%** | **成立** | 原文措辞："best of 100 CoT samples achieve a success rate of **49%**, but still much worse than exploring more nodes in ToT (b > 1)"（PDF p.6）；Table 2 / Table 7 同数 | 全文 |
| 3 | Curiosity Search："某条信息是不是独立维度 = **拿掉它之后结论是否改变**"（leave-one-out） | **部分成立（归因不成立）** | Curiosity Search **没有**"独立维度"这个定义，也**没有** leave-one-out 措辞；只有"拿掉门"这一次实证反事实。Novelty Search 完全没有这个概念。**这个判据是我们自造的**（我们自己的 spec 已承认） | 全文 |
| 4 | MAME（EAAI 2026, 164, 113126）：把"自报置信度"换成"反馈实际引用的**依据 ID**"，形成 **agent×依据 影响矩阵** | **部分成立：书目全对，机制查不到且与可读正文相悖** | 书目 100% 正确。MAME 可读正文只说 **"a dynamic confidence matrix and an answer credibility score to quantify inter-agent influence"**、**"the credibility of the pair of agents"** ⇒ 矩阵是 **agent×agent**，且**保留**自报置信度；全文无"evidence ID / 依据 ID" | 摘要级（方法节未取得） |
| 5 | PSFA（Wray/Kirk/Laird, arXiv 2405.12147 + Cognitive Systems Research 94:101409）：在 **GOMS 先验格子里填**；"Test Cases 节点是全部节点里最不成功的"；"生成 novel problem spaces"列为**开放问题**；出现 "**strong attractor effect**" | **部分成立（3/4 成立，1 措辞过头）+ 标题/版本归并问题** | ①GOMS 只被提**一次**且是"为什么选 CTA"的依据，**没有"先验格子"** ✗ ②Test Cases ✔ ③novel problem spaces ✔ ④原文是 `("strong attractor" effect)`（引号只包 strong attractor）。另：**arXiv 版与 CSR 版是两份标题不同的论文** | 全文（arXiv）/ 题录（CSR） |
| 6 | B* Expansion（Expert Systems 2026, 43(8), e70333）：假设动作集固定完备，改为 **B\* = B ∪ A\*** 迭代构造新动作 | **成立** | 标题/作者/期刊/卷期/年份/DOI 全对；论断是原文摘要原句 | 全文 |
| 7 | Diversity Collapse（ACL 2026 Findings, §4.2 + 附录 I/M）：拓扑效应结构性跨模型稳定；Interdisciplinary Vendi 最低 **4.65**、Horizontal 最高 **8.08**、质量只差 **0.62**；机制名 "**Authority-Induced Collapse**" 与 "**Sycophancy Trap**"；"partitioning the social graph creates '**local pockets of divergence**' that prevent the premature '**rush to agreement**'" | **成立**（五项全中，仅段落定位需微调） | 4.65 / 8.08 / 0.62 全部原文；三个机制名全部原文；引号内英文逐字一致 | 全文 |
| 8 | POET（1901.01753）："开放性"是在**人手工编码的 5 维基因空间**里开放的（**归一化 L2 距离 = 1**） | **部分成立（"5 维"数字要改）** | "归一化 L2 距离 = 1" ✔（β=√5）。"5 维基因" ✗：原文是 **5 种障碍类型 / 9 个基因参数**；β=√5 只对应 §4.3 那个"只开 gap/roughness/stump ⇒ 5 个基因值"的**缩减编码** | 全文 |

### ★ 三条最要紧的发现（先点名）

1. **#4 MAME —— 机制张冠李戴。** 我们写"把自报置信度**换成**反馈实际引用的**依据 ID**，形成 **agent×依据** 影响矩阵"。MAME 论文可读正文说的是：保留置信度分，建 **agent×agent** 的 *dynamic confidence matrix* + *answer credibility score*。**"依据 ID" 与 "agent×依据" 在 MAME 里查不到**。这类"换成依据 ID"的实验设计出现在**另一族论文**（多智能体"证据 vs 置信"文献），不是 MAME。
2. **#3 Curiosity Search —— 归因过头。** 我们的 `DEEP-18-11-Curiosity-POET-spec.md:183` 自己已经写明"**【论文没写】**：LOO 判据本身两篇论文都没有；上面是借'拿掉门'的机制**自造**的"。但 `COLLAPSE-REMEDY-2026-10-22.md` 与 `REFERENCE-AND-CORRECTIONS-2026-10-22.md` 仍把它**写成"Curiosity Search："**（带引号、像是论文原话）。⇒ **同一批数字，两处文档口径不一致**。
3. **#8 POET —— "5 维基因" 是把"5 种障碍类型"当成了"5 维基因向量"。** 完整编码是 9 个基因参数。⇒ 我们自己 `LIT/11_1901.01753.md:20` 里那句"环境的编码 = 一个 5 维基因向量（每维是 (min,max) 区间 + 一个随机种子）" **两处都错**（维数错、粗糙度不是区间、种子是每环境一个不是每维一个）。

---

## 逐条详情

### #1 ToT：74% / 64% / 31%

- **我们文档原话**（`docs/cmp8/routes/HANDOVER-GROUP2-DESIGN-LAYER1.md:75`）：
  > `| B-2c | **跨判官交叉实验** | ToT（同源 74% / 换评估器 64% / 31%） | 换判官看读数怎么动 ⇒ 我们已有的 \`measure_answer(judge_model=...)\` 已经支持 |`

- **真实出处**：
  Shunyu Yao, Dian Yu, Jeffrey Zhao, Izhak Shafran, Thomas L. Griffiths, Yuan Cao, Karthik Narasimhan. *Tree of Thoughts: Deliberate Problem Solving with Large Language Models.* **NeurIPS 2023**（arXiv:2305.10601v2, 2023-12-03）。PDF：`https://arxiv.org/pdf/2305.10601v2`（本次实抓 799,685 B）。

- **原文摘录**（**PDF p.14，Appendix B.2 "Extension to new LMs (GPT-3.5)"**）：
  > `On Game of 24 (we changed 1-shot proposal prompt to 3-shot to make it work), GPT-3.5+ToT's 19% is far worse than GPT-4+ToT's 74%. To further understand the importance of generation vs. evaluation, we ran GPT-4 generation + GPT-3.5 evaluation (64%) and GPT-3.5 generation + GPT-4 evaluation (31%). This suggests the game's bottleneck is thought generation, and different generation/evaluation language models might attain decent results while reducing costs.`

  同一附录的 **Table 5（PDF p.13）**：
  > ```
  >             GPT-4     GPT-3.5
  >     IO     7.3%      6%
  >     CoT    4.0%      3%
  >     ToT    74%       19%
  > Table 5: Game of 24 with GPT-4 vs GPT-3.5.
  > ```

- **裁决**：**成立**。三个数字都在原文，分别对应：
  | 数字 | 设定 | 任务 | 位置 |
  |---|---|---|---|
  | **74%** | GPT-4 生成 + GPT-4 评估（"同源"） | Game of 24（100 题，index 901–1000） | Table 5 + 正文 + Table 2 + Table 7 |
  | **64%** | GPT-4 生成 + **GPT-3.5 评估** | 同上 | Appendix B.2 正文（**无表格**） |
  | **31%** | **GPT-3.5 生成** + GPT-4 评估 | 同上 | Appendix B.2 正文（**无表格**） |
  （第四格 GPT-3.5 生成 + GPT-3.5 评估 = 19%，在 Table 5 里。）

- **方向**：**没有反**。原文结论与我们读法一致——"the game's bottleneck is thought **generation**"。64%（换评估器掉 10pp）远好于 31%（换生成器掉 43pp）。⇒ 我们的 "换判官" 论证方向正确。

- **对我们的影响**：
  1. ⚠️ **引用时必须带限定条件**：GPT-3.5 生成时论文把 1-shot proposal prompt 改成 3-shot（`we changed 1-shot proposal prompt to 3-shot to make it work`）⇒ **2×2 不是受控 A/B**（生成格同时变了模型和 shot 数）。我们 B-2c 的"换判官"实验如果照抄这个设定，**同样不可受控归因**。
  2. ⚠️ **64% / 31% 只出现在正文一句话里**，无表、无重复数、无置信区间，n=100 一次性成功率。我们的 `measure_answer(judge_model=...)` 若要跟 64%/31% 对标，**必须自己报告 n 与 CI**，否则我们的对照和论文的对照不同量纲。
  3. **方向可迁移**：ToT 证明的是"生成侧比评估侧更关键"；对我们的多智能体系统，这支持"**先改生成多样性，别只改判官**"的优先级排序。

---

### #2 ToT：CoT best-of-100 49% vs ToT b=5 74%

- **我们文档原话**（`docs/cmp8/routes/HANDOVER-GROUP2-DESIGN-LAYER1.md:77`）：
  > `| B-2e | **同预算 best-of-k** | ToT（CoT best-of-100 **49%** vs ToT b=5 **74%**） | ★ **轴要换成 $**（论文用节点数，节点轴在成本上不等价）|`

- **真实出处**：同上（arXiv:2305.10601v2，NeurIPS 2023）。

- **原文摘录**（**PDF p.6，§4.1 Game of 24 "Results"**）：
  > `In contrast, ToT with a breadth of b = 1 already achieves a success rate of 45%, while b = 5 achieves 74%. We also consider an oracle setup for IO/CoT, by calculating the success rate using best of k samples (1 ≤ k ≤ 100). To compare IO/CoT (best of k) with ToT, we consider calculating the tree nodes visited per task in ToT across b = 1···5, and map the 5 success rates in Figure 3(a), treating IO/CoT (best of k) as visiting k nodes in a bandit. Not surprisingly, CoT scales better than IO, and best of 100 CoT samples achieve a success rate of 49%, but still much worse than exploring more nodes in ToT (b > 1).`

  **Table 2（Game of 24 Results，PDF p.6）**：
  > ```
  >   IO prompt 7.3%      CoT (best of 100) 49%
  >   CoT prompt 4.0%     IO (best of 100) 33%
  >   ToT (ours) (b=1) 45%
  >   ToT (ours) (b=5) 74%
  > ```

  **Table 7（Cost analysis on Game of 24，PDF p.14）**：
  > ```
  >             Game of 24   Generate/Prompt tokens   Cost per case   Success
  >   CoT (best of 100)     6.7k / 2.2k              $0.47           49%
  >   ToT                   5.5k / 1.4k              $0.74           74%
  > ```

- **裁决**：**成立**。原文措辞已逐字附上（见上）。注意原文的比较轴是 **"tree nodes visited"（节点数）**，不是美元——我们 B-2e 说的"轴要换成 $"**是对的**，而且论文自己给了美元数字（$0.47 vs $0.74）可以直接换算。

- **对我们的影响**：
  1. 引用 49% / 74% 时**建议同时带 $0.47 / $0.74**（Table 7），因为我们的论证轴是成本；这样我们的"同预算"对照与论文"同节点"对照的差异就摆平了。
  2. ⚠️ 论文另给 IO (best of 100) = 33%、ToT b=1 = 45%——若我们做 best-of-k 曲线，这四个点都是现成锚点（7.3% / 4.0% / 33% / 49% / 74%）。
  3. ⚠️ 我们旧笔记 `DEEP-04-ToT-quotes.md` §7 记录：官方发布日志重算 ToT b=5 = **69.0%**（any-of-5），与论文 74% 差 5pp。⇒ **我们引 74% 时应注明"论文正文/Table 2/Table 7 的数"，并知道发布产物复现不出 74%**（这一点旧笔记已查证，非本轮新增）。

---

### #3 Curiosity Search / Novelty Search：leave-one-out 判"独立维度"

- **我们文档原话**：
  - `docs/cmp8/routes/COLLAPSE-REMEDY-2026-10-22.md:100`：
    > `| 4 | **依据包 leave-one-out** | Curiosity Search："某条信息是不是独立维度 = **拿掉它之后结论是否改变**" | 信息级独立维度判定（n 条 = n 次消融，比组件级消融更便宜）|`
  - `docs/cmp8/routes/REFERENCE-AND-CORRECTIONS-2026-10-22.md:38`：
    > `| A1-18 | **leave-one-out 判独立维度** | Curiosity Search | "某条信息是不是独立维度 = **拿掉它之后结论是否改变**" ⇒ n 条 = n 次消融 | 对照臂④ |`
  - `docs/cmp8/routes/LIT/DEEP-18-11-Curiosity-POET-spec.md:183`（**我们自己的 spec，已经写了实话**）：
    > `**【论文没写】**：LOO 判据本身两篇论文都没有；上面是借"拿掉门"的机制**自造**的（`【我们】`）。`

- **真实出处**：
  - **Curiosity Search**：Stanton C, Clune J (2016). *Curiosity Search: Producing Generalists by Encouraging Individuals to Continually Explore and Acquire Skills throughout Their Lifetime.* **PLoS ONE 11(9): e0162235**. DOI 10.1371/journal.pone.0162235. PMCID **PMC5010182**.（本次抓 `https://pmc.ncbi.nlm.nih.gov/articles/PMC5010182/` 全文）
  - **Novelty Search**：Lehman J, Stanley KO (2011). *Abandoning Objectives: Evolution Through the Search for Novelty Alone.* **Evolutionary Computation 19(2): 189–223**. DOI 10.1162/EVCO_a_00025.（原文期刊页未抓到；定义句以 ①Curiosity Search 全文对 NS 的一手转述 ②Lehman & Stanley 自撰 GPTP-IX 章节（ResearchGate 全文转载）为准）

- **原文摘录（Curiosity Search，PMC5010182 全文）**：
  - **"拿掉门"那一节**（§Results and Discussion → 小节 **"Do Doors Represent Distinct Skills?"**）：
    > `To ascertain whether this phenomenon occurs, we test CS and NST in each maze with and without doors. **If the doors are merely obstacles requiring no skill to open, removing them should have little to no effect on our results**: CS should still slightly, but significantly, outperform NST and overall exploration percentages should remain similar. However, we found that both CS and NST agents explore **nearly twice as much** of their environment when the doors are removed (Fig 8, p < 0.0001 except for the Cross Maze, in which there is no significant change). Furthermore, the exploration gap between Curiosity Search and Novelty Search **disappears almost entirely**; in aggregate there is no difference (p ≥ 0.05) after the doors are removed.`

    **Fig 8 图注**：
    > `Fig 8. Removing doors increases exploration and causes the difference between Curiosity Search and Novelty Search to disappear. ... If the doors were merely obstacles requiring no skill to open, we would expect little or no change in either algorithm's ability to explore the domain after doors are removed. However, exploration greatly increases when doors are removed and the difference between treatments disappears almost entirely, suggesting that the doors in these experiments are **an abstraction of distinct skills**, which CS seems better able to acquire.`

  - 论文里"independently"一词的**唯一**出现处（§Methods → Problem Domain，**说的是接线，不是维度**）：
    > `Each robot has a separate door-opening neuron for each type of door ... Because each of these neurons must be **independently wired**, each type of door can be thought of as representing a functionally different skill.`

  - **论文对 NS 的定义**（§Introduction）：
    > `Novelty Search helps avoid deception by instead encouraging individuals to be behaviorally different from previously produced individuals [19]. Agents are compared by their **behavioral distance** from the rest of the population and also from an archive, which contains a history of prior individuals to prevent backtracking. The distance function can take different forms; for example, in a maze environment, one possible metric is the distance between the final locations of each agent, thereby rewarding individuals for ending up as far away from each other as possible.`

    以及 §Introduction：
    > `Like Novelty Search, Curiosity Search operates without a traditional fitness goal [19] ... **Unlike Novelty Search, this novelty is measured not against the population, but against the individual's own accomplishments.**`

  - **Novelty Search 的新颖度公式**（Lehman & Stanley, *Novelty Search and the Problem with Objectives*, GPTP-IX 章节，ResearchGate 全文）：
    > `A simple measure of sparseness at a point is the **average distance to the k-nearest neighbors** of that point, where k is a fixed parameter that is determined experimentally. ... The sparsity ρ at point x is given by ρ(x) = (1/k) Σᵢ dist(x, μᵢ)`

- **裁决**：**部分成立 —— 归因不成立**。
  - ❌ **Curiosity Search 没有定义"独立维度"这个概念**，没有 "leave-one-out" 这个词，没有"某条信息是不是独立维度 = 拿掉它之后结论是否改变"这句话。
  - ✅ **但"拿掉一个东西看效应是否消失"的反事实范式确实在原文**（"Do Doors Represent Distinct Skills?" 一节），而且原文的零假设写法与我们的 LOO 零假设几乎同构："If the doors were merely obstacles requiring no skill to open, **removing them should have little to no effect on our results**"。
  - ⚠️ **方向要小心**：原文去掉门之后，**探索量几乎翻倍**（p<0.0001），**而且 CS 与 NS 的差距"几乎完全消失"**（p ≥ 0.05）。也就是说"结论改变"在原文里指的是**比较关系被抹平**（CS 不再优于 NS），不是我们语境里"该条依据是否承重"。
  - ⚠️ **对象不同**：原文讨论的是 **skill（门的种类）**，不是"某条信息/依据"。
  - ❌ **Novelty Search 完全没有这个概念**：NS 的新颖度 = 行为空间里到 k 近邻的**平均距离**，与"拿掉某维度后结论是否改变"无关。
  - 📌 **我们自己的 spec 已经写明这是自造的**（`DEEP-18-11-Curiosity-POET-spec.md:183`）。所以**问题不在"判据错"，而在"两处文档把自造判据写成了带引号的论文原话"**。

- **对我们的影响**：
  1. 🔴 **必须改口径**：所有把 leave-one-out 判据归给 Curiosity Search 的地方（`COLLAPSE-REMEDY-2026-10-22.md:100`、`REFERENCE-AND-CORRECTIONS-2026-10-22.md:38`、`HANDOVER-GROUP2-DESIGN-LAYER1.md:74`）应改成
     **"判据形态借自 Curiosity Search 的『Do Doors Represent Distinct Skills?』（PMC5010182）反事实实验；『某条信息=独立维度』的表述是本项目自造（spec §3 已标注）"**。
  2. ✅ **判据本身仍然可用**，而且比原文更强：原文只做到"skill 级"（门是/不是一种独立技能），我们要做到"**信息条目级**"（第 k 条依据是否承重）——这是原文没有的扩展，引用时**必须自己承担**，不能挂在论文名下。
  3. ⚠️ **不要引用"Curiosity Search 证明了 leave-one-out"**——评审只要翻到原文就会发现没有这句，直接影响我们"承重判定"这条最关键的方法论的可信度。

---

### #4 MAME（Engineering Applications of AI 2026, 164, 113126）

- **我们文档原话**（`docs/cmp8/routes/HANDOVER-GROUP2-DESIGN-LAYER1.md:74`）：
  > `| B-2b | **锚外维度的读数实现** | Curiosity Search（leave-one-out）+ **MAME（agent×依据 影响矩阵）** | ★ **本组最重要的交付**：\`VD_anchor_out\`（锚外新增维度数）…… |`
  - 另见 `docs/cmp8/routes/LIT/DEEP-09-12-quotes.md:17` 与 `DEEP-09-12-SelfDiscover-MAME-spec.md:17`（书目部分）。

- **真实出处（书目全部核对通过）**：
  Liangji Zhang, Jianbo Yuan, Yougming He, Miao Yu, Kun Zhu, Zhenni Yu.
  ***Diversity-driven reasoning: Mitigating logical errors in LLMs through social-attribute guided multi-agent collaboration.***
  **Engineering Applications of Artificial Intelligence**, Vol. 164, Issue PB, Art. 113126. DOI **10.1016/j.engappai.2025.113126**. PII **S0952197625031574**.
  ACM DL 记录：*Volume 164, Issue PB*，*Published: 04 June 2026*；OpenAlex `publication_year: 2025`（online 2025）。
  论文自称 MAME = **Multi-Attribute Hybrid Expert**；含 **GFF**（Group Feedback Framework）+ **MAP**（Multi-Attribute Prompting）。

- **原文摘录（ScienceDirect 落地页可见正文）**：
  - **Abstract**：
    > `First, we introduce a Group Feedback Framework (GFF) that integrates group decision-making theory into multi-agent collaboration. By simulating human consensus formation and error correction mechanisms, we **define a dynamic confidence matrix and an answer credibility score to quantify inter-agent influence**. These metrics dynamically guide agents in adjusting their reasoning paths based on collective feedback.`
  - **Introduction**：
    > `Specifically, multiple agents first give an initial answer to a given question, second, each agent in the framework refines its answer to the suggestions of the other agents and **gives the credibility of the pair of agents** and the feasible confidence of the answer, and finally each agents refines its answer based on the feedback. ... and the final answer with the highest confidence level is taken as the answer to the given question.`
  - **Contribution bullet**：
    > `Inspired by group decision theory, we propose GFF to improve the reasoning ability of agents. The agent in the framework have a **confidence score for other agents and reasoning answers**, and through multiple rounds of dialogues and continuous feedback, each agent in the framework can continuously adjust and optimize their reasoning paths.`
  - **Abstract（数字）**：
    > `MAME achieves enhancements of up to 24.05 % in mathematical reasoning, 39.1 % in logical reasoning, and 4.94 % in commonsense reasoning compared to baseline models.`

- **裁决**：**部分成立 —— 书目 100% 正确；机制论断"查不到"，且与可读正文相悖**。
  | 我们的说法 | MAME 原文 |
  |---|---|
  | 把"自报置信度"**换成**"依据 ID" | ❌ 查不到；相反，论文**用**置信度分（`confidence score`、`feasible confidence of the answer`） |
  | **agent×依据** 影响矩阵 | ❌ 查不到；论文的是 **agent×agent** 的 `dynamic confidence matrix`（"credibility of the pair of agents"）+ 一个 `answer credibility score`（对**答案**的可信度，不是对依据） |
  - **证据强度说明**：MAME **方法节**未取得（ScienceDirect Cloudflare 拦截、SSRN 超时、OpenAlex 无 OA、官方仓 404）⇒ 我们**不能证伪**"依据 ID"，只能说**在可得的一手/准一手正文里查不到**，且可读正文明确指向 agent×agent + 自报置信度。
  - 🔎 **疑似来源串线**："用证据替代自报置信度"的设计出现在**另一族论文**里（例如把 agent 消息拆成 *evidence-only / conclusion-only* 条件、区分 *evidence-driven belief update* 与 *source-driven social influence* 的多智能体社会认知文献）。本轮**未能定位到我们当初引的那一篇一手文献**，故只作提示，不作裁决。

- **对我们的影响**：
  1. 🔴 **`VD_anchor_out` 的方法学背书要换**。当前 `HANDOVER-GROUP2-DESIGN-LAYER1.md` 把 MAME 当成"agent×依据 影响矩阵"的出处；MAME 撑不住这个说法（它撑的是 agent×agent）。⇒ 报告里要么**删掉 MAME 的背书**，要么**改成"MAME 提供 agent×agent 的 pairwise 可信度/置信矩阵范式"**，并把"依据 ID"标成**我们自己的设计**。
  2. ⚠️ 我们旧笔记 `LIT/24_sciencedirect_pick.md` 已经写明"**方法节未读到**（ScienceDirect 页文本跳过方法节）"——本轮复核**同样没读到**。⇒ 这条不是新问题，是**旧问题没解决**，而下游文档已经把它当成已核实。
  3. ⚠️ 我们的旧笔记还有一个未解项："weight vector modulation 改权重还是改 prompt"仍未查清 ⇒ 引用 MAME 时**不要**把它当作"多属性 ⇒ 多样性"的机制证据。

---

### #5 PSFA（Wray / Kirk / Laird）

- **我们文档原话**（`docs/cmp8/routes/HANDOVER-GROUP2-DESIGN-LAYER1.md:84-88`）：
  > `⇒ ⇒ 而**最新读到的一篇（PSFA, Wray/Kirk/Laird, arXiv 2405.12147 + Cognitive Systems Research 94:101409）**`
  > `**正是在 GOMS 先验格子里填**（它自己承认"Test Cases 节点是全部节点里最不成功的"、`
  > `并把"生成 novel problem spaces"列为**开放问题**、还写了 *"strong attractor effect"*）`
  > `⇒ ⇒ **我们的"锚外发现"是与它有量纲差异的位置** ⇒ 这条要写进你的报告。`

- **真实出处（⚠️ 两份标题不同的论文，不能并成一篇）**：
  | 我们写的 | 真实标题 | 出处 | 年/卷期 |
  |---|---|---|---|
  | `arXiv 2405.12147` | ***Eliciting Problem Specifications via Large Language Models*** | Robert E. Wray, James R. Kirk, John E. Laird；arXiv v2（2024-06-12）；被 **ACS 2024**（Advances in Cognitive Systems, Palermo）接收 | 2024 |
  | `Cognitive Systems Research 94:101409` | ***Eliciting problem specifications for LLM-Modulo cognitive systems*** | 同三位作者；DOI **10.1016/j.cogsys.2025.101409**；PII S1389041725000890；ACM DL 记 *Volume 94, Issue C*，*Published: 12 June 2026*；plu.mx 记 *Publication Year 2025* | 2025（online）/ 2026（卷期） |
  ⇒ **"PSFA" 这个标签在我们文档里把两篇不同标题的论文合并引用了。** 下面四条论断**全部出自 arXiv 版**（本次实抓 `https://arxiv.org/html/2405.12147v2` 全文，696,320 B）。

- **原文摘录（arXiv:2405.12147v2）**：
  - **② Test Cases 自陈**（**§6 Feasibility Evaluation**，小节 "Test Cases/Test States"）：
    > `Test Cases/Test States: This step was **the least successful of all the nodes we included in the CTA Agent**. It produced test cases, but they were (generally) neither obvious examples of unit tests (e.g., representing the goal state to test goal recognition) nor alternative problem sets. Neither this step nor the problem characterization (which asked for examples of undesired states or configurations) identified problematic test cases (e.g., a problem with two pails of the same size). Again, in the long term, we can likely improve the generation of test cases, but the initial results from this node were limited at best.`
  - **③ novel problem spaces 列为开放问题**（**§4 Design of the Cognitive Task Analyst**，末尾的 "open/unresolved questions" 清单，第一条）：
    > （引导句）`... we identify a few **open/unresolved questions** for a future, refined implementation that motivate our goals of this initial feasibility implementation.`
    > （第一条）`• Generation for novel problems. An assessment of overall feasibility of the approach must attempt to evaluate the ability of the CTA Agent to formulate problem spaces for problems not in its training set. Variations include problems that are wholly novel and also problems that share some features with familiar problems but that are novel in whole. In particular, this last class of problem requires that the LLM generate good, novel analysis while mitigating the general tendency of LLMs to reproduce or "parrot" similar problems and solutions that appeared in its training set.`
  - **④ "strong attractor"**（**§5 Feasibility Implementation and Evaluation Plan**，"Variations of water jugs" 段）：
    > `Further, known problems might bias the LLM's response to responding appropriately to slight variations in a problem statement **("strong attractor" effect)**.`
    ⚠️ 原文引号只包住 `strong attractor`，**不含** `effect`。我们写的 `"strong attractor effect"` 多了引号范围。
  - **① GOMS**（**§2 Background: Problem Spaces and Cognitive Task Analysis**，**全文仅此一次**提到 GOMS）：
    > `We choose CTA because the design of an early and influential form of CTA, **GOMS (John & Kieras, 1996)**, focused analysis somewhat directly on the formulation of problem spaces compatible with Newell's definition. **GOMS guides the analyst in identifying Goals, Operators, Methods, and Selection knowledge** (roughly, path constraints) for a task. Below, we take advantage of this connection by defining a "Cognitive task analyst" role for the LLM agent. By creating this role context for the LLM, the intent is to bias generation toward concepts consistent with this conception of problem spaces (and their requirements).`
    - ⚠️ 全文检索：`GOMS` 出现 **1 次**；`grid` / `cell`（"格子"）**不出现**；"prior" 只在 "prior formulation"（"refine the prior formulation"）语境出现，与 GOMS 无关。
    - 论文真正的结构是 **Figure 3 的节点图**（§4）：`the agent chooses among four high-level directions in which to continue its analysis: 1) defining the characteristics of the problem, 2) defining characteristics of problem solving, 3) formulating the problem space, and 4) assessing the quality of the solution thus far.` —— **不是 GOMS 的四格**（GOMS 是 Goals/Operators/Methods/Selection）。

- **裁决**：**部分成立（3/4 成立；GOMS 一条措辞过头）+ 题录归并问题**。
  | 子项 | 裁决 | 说明 |
  |---|---|---|
  | 在 **GOMS 先验格子里填** | ✗ **部分成立（措辞过头）** | GOMS 是"为什么选 CTA"的**方法论依据**（且全文只提一次）；论文里**没有任何"先验格子"**，实际结构是 Figure 3 的四向节点图 + 若干子节点（`nodes and subnodes in the figure`） |
  | Test Cases 节点"最不成功" | ✅ **成立（逐字）** | 见上，§6 |
  | "生成 novel problem spaces" 是**开放问题** | ✅ **成立（逐字）** | §4 的 open/unresolved questions 清单第一条 |
  | 出现 "strong attractor effect" | ✅ **成立（引号位置要改）** | 原文是 `("strong attractor" effect)` |
  | `arXiv 2405.12147 + Cognitive Systems Research 94:101409` | ⚠️ **归并了** | 两份**标题不同**的论文（"…via Large Language Models" / "…for LLM-Modulo cognitive systems"）；卷 94 / 文章号 101409 / DOI / 作者全对 |

- **对我们的影响**：
  1. ⚠️ **"量纲差异"的论证仍可成立，但措辞要改**：把"在 GOMS 先验格子里填"改成 **"在 Newell(1980) 问题空间 + GOMS 四要素（Goals/Operators/Methods/Selection）启发的节点-子节点架构里逐格填写（Figure 3）"** —— 这样才是原文能支撑的说法，而且**更有力**（因为论文自己承认节点粒度粗、Test Cases 节点最失败）。
  2. ✅ **两条硬证据可以照旧用**：Test Cases 自陈（"least successful of all the nodes"）与 "Generation for novel problems" 作为 open question，都是我们"锚外发现"这条线的最好对照材料。
  3. ⚠️ **引用要写全两个标题**，否则评审一查就发现"CSR 94:101409 的标题里没有 'Large Language Models'"。

---

### #6 B* Expansion（Expert Systems 2026, 43(8), e70333）

- **我们文档原话**（`docs/cmp8/routes/COLLAPSE-REMEDY-2026-10-22.md:64`）：
  > `**出处**：**B\* Expansion**（*Thinking Is Not Enough: The B\* Expansion Technique*, Expert Systems 2026, 43(8), e70333）`
  - 机制主张见 `docs/cmp8/routes/LIT/REFERENCE-AND-CORRECTIONS-2026-10-22.md:27`：
    > `| A1-7 | **动作空间展开 \`B* = B ∪ A*\`** | B\* Expansion, Expert Systems 2026 43(8) e70333 | 正式命题：**"action space completeness is insufficient"** ⇒ 离散、非措辞、可复算 | 动作③动作空间可演化 |`

- **真实出处（全部核对通过）**：
  Sebastián Andrés Mayorquín Posadas, Julio Vega.
  ***Thinking Is Not Enough: The B\* Expansion Technique for Enhancing Autonomous LLM Agents.***
  **Expert Systems** (Wiley), **2026, Vol. 43, Issue 8, Art. e70333**. DOI **10.1111/exsy.70333**.
  Handle/Handle-Proxy 记录日期 2026-06-18；官方仓 `github.com/SamthinkGit/Bstar-Expansion`。

- **原文摘录**：
  - **Abstract（首两句）**：
    > `Most autonomous agents built on large language models (LLMs) focus on improving internal reasoning **while assuming a fixed and complete set of primitive actions**. In this work, we challenge this assumption and introduce the B* expansion technique, an action-centric method that enables agents to **iteratively construct new actions beyond an initial basis B**, forming an expanded action space **B* = B ∪ A***.`
  - **§3.3（action basis 的"完备"定义）**：
    > `We now introduce a finite subset [B], called the action basis, which serves as a generative core for the entire space [A]. The set [B] is assumed to be complete, in the following formal sense: An action basis is complete if and only if every action can be expressed as a finite composition of actions in [B]: (6) where [∘] is a composition function mapping finite sequences over [B] to actions in [A].`
  - **§3.3（并集的正式定义 + 完备 vs 最优）**：
    > `As stated, completeness ensures solvability but it does not imply optimality. ... Finally, we define the expanded action space as the union of the action basis and a growing approximator: (9)`
  - **Abstract（命题句，与我们的 A1-7 一致）**：
    > `Our results show that expanding the action space leads to improved exploration and performance, demonstrating that **action space completeness is insufficient** and that optimizing the action set itself can significantly enhance agent effectiveness, even surpassing state-of-the-art reasoning-based approaches.`

- **裁决**：**成立**。标题 / 作者 / 期刊 / 卷期 / 年份 / 文章号 / DOI 全部正确；"假设固定完备 → 改为 B* = B ∪ A* 迭代构造新动作"是原文摘要原句。

- **对我们的影响**：
  1. ✅ **可以直接引用**，无修订需求。它是我们唯一一条"标题/卷期/DOI/命题全部零误差"的论文级引用。
  2. ⚠️ 引用时建议补一句限定：论文的实证只在 **Conway's Game of Life（200×200 网格、300 代）** 一个环境里做，模型是 `gpt-4o-mini` 与 `o4-mini`；"甚至超过 SOTA 推理型方法"这一句只在这个环境里成立。

---

### #7 Diversity Collapse（ACL 2026 Findings）

- **我们文档原话**（`docs/cmp8/routes/HANDOVER-GROUP2-DESIGN-LAYER1.md:71`）：
  > `| B-2a | **去权威化对照臂** | Diversity Collapse (ACL 2026 Findings, §4.2 + 附录 I/M) | 判官从"权威裁定"改成**逐条对照表**（vote 式集合比较）；**把"专家 persona"与"权威结构"拆成两个变量**（2×2）⇒ 写好 2×2 的臂定义与读数表 |`
  - 数字与机制名的具体主张见 `docs/cmp8/routes/LIT/DEEP-16-19-quotes.md`（§A.2/A.4/A.5）与 `DEEP-16-19-DiversityCollapse-ADHD-spec.md`。

- **真实出处（全部核对通过）**：
  Nuo Chen, Yicheng Tong, Yuzhe Yang, Yufei He, Xueyi Zhang, Qingyun Zou, Qian Wang, Bingsheng He.
  ***Diversity Collapse in Multi-Agent LLM Systems: Structural Coupling and Collective Failure in Open-Ended Idea Generation.***
  arXiv:**2604.18005v2**（v1 2026-04-20，v2 2026-04-21）。
  arXiv `comments` 字段逐字：**`56 pages, 15 figures; Accepted at ACL 2026 Findings`** ⇒ "ACL 2026 Findings" ✔。
  代码：`github.com/Xtra-Computing/MAS_Diversity`（论文自述）。

- **原文摘录**：
  - **① Fig. 3 caption（Vendi 4.65 / 8.08 + "Sycophancy Trap"）**：
    > `Figure 3: Diversity Metrics across Cognitive Structures. Horizontal collaboration (Junior-driven) consistently maximizes diversity (**Vendi: 8.08**), identifying the "Unbound Junior" effect. Surprisingly, Interdisciplinary collaboration exhibits the **lowest diversity (Vendi: 4.65)**, suggesting that distinct expert roles induce a **"Sycophancy Trap"** where agents converge on safe, high-level generalities.`
  - **② §4.3（"Authority-Induced Collapse" 定义句 + 质量 vs 多样性）**：
    > `**Authority-Induced Collapse is a form of directed coupling that accelerates convergence.** The Vertical structure which mixes authority levels, offers a compromise, mitigating the chaos of juniors with the structure of seniors.`
    > `While Interdisciplinary attains the highest Overall Quality (**8.50 vs. Horizontal's 7.88, a +0.6 gap on a 10-point scale**, Figure 6), this gain does not offset the much larger diversity drop between the same two conditions (**Vendi 4.65 vs. 8.08**, Figure 3).`
  - **③ 附录（0.62 的出处）**：
    > `Quality differences are modest. The Overall Quality range across all five structures is **7.88–8.50 (a 0.62-point spread on a 10-point scale, or 6%)**. By contrast, the Vendi Score range is **4.65–8.08 (a 74% relative difference)**. Quality variation is an order of magnitude smaller than diversity variation.`
  - **④ §5.2（引号内英文逐字 + 拓扑结构性 + 附录指引）**：
    > `This suggests that **partitioning the social graph creates "local pockets of divergence" that prevent the premature "rush to agreement"** observed in the Standard mode. A 2×2 Persona × Topology factorial (**Appendix I**) and a cross-model replication on GPT-5.1 (**Appendix M**) further show that **this topology ranking is structural rather than model-specific**.`
  - **⑤ §4.2（"strong attractor"）**：
    > `Gravitational Collapse (Leader-Led/Naive): The Leader-Led structure (Red) closely mirrors the Naive baseline (Grey), exhibiting high Kurtosis. This suggests that the presence of senior authority acts as a **strong attractor**. Junior agents likely succumb to sycophancy, aligning their vectors with the leader rather than offering orthogonal critiques.`
  - **⑥ §4.1（质量差异的总体表述）**：
    > `Junior-dominated horizontal collaboration achieves the highest diversity, interdisciplinary expert teams the lowest, with only modest quality differences (**Overall Quality 7.88–8.50**). The ranking is robust across embedding backbones (Appendix F) and heterogeneous-model ensembles (Appendix J) ...`
  - **附录标题（确认附录 I / M 存在）**：
    > `Appendix I  2×2 Factorial Ablation: Topology × Persona on DeepSeek-V3`
    > `Appendix M  GPT-5.1 Cross-Topology and Cross-Model Analysis`
    > （附录 M 内）`Finding 4: Cross-model validation with GPT-5.1.`

- **裁决**：**成立**（五项全中）。唯一需要微调的是**位置标注**：
  | 我们写的 | 原文实际位置 |
  |---|---|
  | "§4.2" | §4.2 = *Distributional Dynamics*，**"strong attractor"** 那句在这 ✔ |
  | — | **"Authority-Induced Collapse is a form of directed coupling…"** 在 **§4.3**（*Topological Segregation: Two Semantic Regimes*），不在 §4.2 |
  | — | **"Sycophancy Trap"** 在 **Figure 3 图注**，不在 §4.2 正文 |
  | — | **"local pockets of divergence" / "rush to agreement" / "topology ranking is structural rather than model-specific"** 在 **§5.2**（*Topology: The Impact of Communication Structure*） |
  | "附录 I/M" | ✔ 附录 I = 2×2 Persona×Topology 析因；附录 M = GPT-5.1 跨模型复现 |

- **对我们的影响**：
  1. ✅ **B-2a 的立论完全站得住**：论文自己就做了"persona 结构 × 拓扑"的 2×2 拆解（附录 I），并明确说"**the combination of expertise and hierarchy, not expertise alone, drives the collapse**"（§4.1）与 "Authority-induced collapse is structural, not prompt-driven"（附录 K 段）。⇒ 我们把"专家 persona"与"权威结构"拆成两个变量，**与论文方法一致**，可以直接点名引用。
  2. ⚠️ **引用 0.62 时要注明它是附录的"range spread"**（5 个认知结构的 Overall Quality 全域 7.88–8.50，跨度 0.62），而**正文**写的是 Interdisciplinary vs Horizontal 的 "+0.6 gap"。我们若说"Interdisciplinary 与 Horizontal 只差 0.62"，严格讲正文给的是 8.50 vs 7.88（= 0.62，一致），可放心用。
  3. ⚠️ **"拓扑效应结构性跨模型稳定"有边界**：论文的跨模型复现用的是 **GPT-5.1**（且附录 M 显示 GPT-5.1 在某些干预下**反而**降低多样性，见 §6 "Alignment-Topology Mismatch"）。⇒ 我们写"跨模型稳定"时最好加限定"**在论文测过的拓扑排序上**"，不要泛化成"任何模型上都稳定"。
  4. ✅ **可直接引用的逐字英文**（我们文档里的引号内英文与原文**逐字一致**，无需改）：`"local pockets of divergence"`、`"rush to agreement"`、`"Sycophancy Trap"`、`"Authority-Induced Collapse"`。

---

### #8 POET（arXiv 1901.01753）

- **我们文档原话**：
  - `docs/cmp8/routes/LIT/11_1901.01753.md:20`：
    > `• **环境的编码 = 一个 5 维基因向量**（每维是"从哪个区间均匀采样"的 (min,max) 区间 + 一个随机种子）：\`stump height\` / \`gap width\` / \`step height\` / \`step number\` / \`surface roughness\`。**实际环境 = 从这些分布采样出的具体地形，种子存在环境里 ⇒ 可精确复现。**`
  - `docs/cmp8/routes/LIT/11_1901.01753.md:135`：
    > `→ **要改什么**：POET 的距离是在**人手写的 5 维基因空间**里算的（归一化到全平↔最大环境的 L2 距离 = 1）。`
  - `docs/cmp8/routes/LIT/11_1901.01753.md:153-155`：
    > `- 环境空间 = **人手设计的 5 维基因**（stump / gap / step height / step number / roughness），**每维的初值、变异步长、上限全是人定的（Table 1）**。`
    > `- "开放"发生在**这 5 维盒子内部**（论文自陈："This space is limited by the maximal ranges of those distributions… can eventually 'max out' the difficulty"）。`
    > `- 覆盖度量也在**同一个 5 维空间**里算。`

- **真实出处**：Rui Wang, Joel Lehman, Jeff Clune, Kenneth O. Stanley.
  ***Paired Open-Ended Trailblazer (POET): Endlessly Generating Increasingly Complex and Diverse Learning Environments and Their Solutions.***
  arXiv:1901.01753v3 [cs.NE], 2019-02-21；**GECCO 2019**。（本次实抓 ar5iv HTML 全文 `https://ar5iv.labs.arxiv.org/html/1901.01753`）

- **原文摘录**：
  - **§4.2 Environment Encoding and Mutation（"五种障碍类型"）**：
    > `To enable such a progression, we adopt a simple encoding to represent the search space of possible environments. As enumerated in Table 1, there are **five types of obstacles** that can be distributed throughout the environment: (1) stump height, (2) gap width, (3) step height, (4) step number (i.e. number of stairs), and (5) surface roughness. **Three of these obstacles, e.g. stump height, are encoded as a pair of parameters (or genes) that form an interval** from which the actual value for each instance of that type of obstacle in a given environment is uniformly sampled.`
    > （同节）`Because the parameters of an environment define a distribution, the actual environment sampled from that distribution is the result of a random seed. **This seed value is stored with each environment** so that environments can be be reproduced precisely, ensuring repeatability.`
  - **Table 1（§4.2）逐行（本次从 ar5iv 抽取）**：
    > ```
    > Obstacle Type | Initial Value | Mutation Step | Max Value
    > Stump Height  | (0.0, 0.4)   | 0.2           | (5.0, 5.0)
    > Gap Width     | (0.0, 0.8)   | 0.4           | (10.0, 10.0)
    > Step Height   | (0.0, 0.4)   | 0.2           | (5.0, 5.0)
    > Step Number   | 1            | 1             | 9
    > Roughness     | uniform (0, 0.6)              | 10.0
    > ```
    ⇒ **基因参数总数 = 2+2+2+2+1 = 9**（"5" 是**障碍类型数**，不是基因维数）。
  - **§4.3（归一化 L2 距离 = 1）**：
    > `To more precisely quantify these results, we define the **normalized distance** between any two environments, E_A and E_B as`
    > `(1/β)·‖(e(E_A) − e(E_B)) / e(E_Max)‖₂ , where e(E) is the genetic encoding vector of E, and E_Max is a hypothetical environment (for normalization purpose) with all genetic encoding values are maxed out. (The maximum values are **roughness = 8, Gap_lower = Gap_upper = 8, Stump_lower = Stump_upper = 3**.)`
    > `The constant **β = √5** is simply for normalization so that the distance is **normalized to 1 when E_A = E_Max and E_B is a purely flat environment** (roughness zero) without any obstacles, which therefore contains an all-zero genetic encoding vector.`
    > （同节）`For these experiments, the environments have **three obstacle types enabled: gaps, roughness, and stumps**.`
  - **§6 Supplemental Information（新颖度用 L2 + k=5）**：
    > `Note that in this work the **distance between genetic encodings of environments is calculated with an L2-norm and the number of nearest neighbors k in the calculation of novelty is 5**.`
    > （同节）`... the encoding of an environment is in effect a genetic representation, which means that in POET in effect novelty is a genetic diversity measure. That way, **POET does not in principle require a behavior characterization (BC) to be devised for environments**, though doing so is also not precluded.`
  - **§5（"开放性"的边界）**：
    > `The present problem space is a 2-D course of obstacles that can be generated within distributions defined by the genome describing the environment. **This space is limited by the maximal** ...`

- **裁决**：**部分成立 —— "归一化 L2 距离 = 1" ✔；"5 维基因空间" ✗（数字要改）**。
  | 我们的说法 | 原文 | 裁决 |
  |---|---|---|
  | "人手工编码" | Table 1 的初值/变异步长/上限全由人手定 | ✅ 成立 |
  | "开放性是在这个编码盒子里开放的" | §5 "This space is limited by the maximal ranges of those distributions…" | ✅ 成立 |
  | "归一化 L2 距离 = 1" | `(1/β)‖(e(EA)−e(EB))/e(EMax)‖₂`，β=√5，使"最大环境↔全平环境"距离 = 1 | ✅ 成立（逐字） |
  | **"5 维基因空间"** | 原文是 **5 种障碍类型 / 9 个基因参数**（Table 1）；β=√5 对应的是 §4.3 那个**只开 gap/roughness/stump ⇒ 5 个基因值**的缩减编码 | ❌ **数字有误** |
  | "每维是 (min,max) 区间 + 一个随机种子" | roughness 是**单个标量** `uniform(0,0.6)`，不是区间；种子是**每个环境一个**（存 environment 对象里），不是每维一个 | ❌ **表述有误** |

- **对我们的影响**：
  1. 🔴 **`LIT/11_1901.01753.md` 的"5 维"要改成"5 种障碍类型 / 9 个基因参数"**（并注明 §4.3 的归一化距离用的是只开 3 种障碍的 5 值缩减编码，β=√5）。我们**自己**的核心论断（"它的'开放'是在一个人手写的 5 维盒子'里开放的"）**不依赖维数是 5 还是 9**——只要写"**一个由 5 种障碍类型 / 9 个基因参数手工定义的盒子**"，论断更强、更准确（因为 9 维比 5 维更"盒子"）。
  2. ✅ **核心洞察（度量与被测共享同一坐标 ⇒ 自证的高覆盖）完全成立**：POET 的新颖度、覆盖度、距离全都在同一个手工基因编码里算（§6 明确说 "POET does not in principle require a behavior characterization"）⇒ 我们引用这条时**可以直接说"POET 的多样性就是基因空间里的距离"**，有原文支撑。
  3. ⚠️ **不要把"归一化到 1"说成"距离范围是 0–1"**：归一化的定义是"**最大环境 ↔ 全平环境** 这一对恰好 = 1"，不是所有点对的取值范围上界。

---

## 查不到的

### A. MAME（#4）的**方法节** —— 唯一的一手来源缺口

- **试过什么**：
  1. `curl https://www.sciencedirect.com/science/article/pii/S0952197625031574` → **Cloudflare 拦截**，返回错误页（`::CLOUDFLARE_ERROR_1000S_BOX::`, Reference `a4e954b34c5a49e1`），全文 0 命中 "credibility"。
  2. `curl` ACM DL 落地页 `https://acm-stag.literatumonline.com/doi/10.1016/j.engappai.2025.113126` → 只回 5,915 B 的壳页面（Cloudflare/JS 挑战）。
  3. `curl` SSRN 预印本 `https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5167458` → `upstream connect error … connection timeout`。
  4. `curl` OpenAlex API `works/doi:10.1016/j.engappai.2025.113126` → `best_oa_location: null`，无任何 `pdf_url`（closed）。
  5. `web_search` 命中 ScienceDirect 页 → **拿到的是摘要 + 引言 + 贡献列表 + "Effects of GFF" 段首 + Conclusion + CRediT + 参考文献**，**方法节（公式、置信矩阵定义）被跳过**。与我们旧笔记 `LIT/24_sciencedirect_pick.md` 的记录**完全一致**。
  6. 官方仓 `github.com/ioio0614/MAME` → 404（旧笔记已记，本次未复现成功）。
- **结论**：**MAME 的方法节查不到**。因此 #4 的"依据 ID / agent×依据"只能判"**在可得的一手正文中查不到，且可读正文明确写的是 agent×agent 置信矩阵 + 自报置信度**"，**不能判"证伪"**。
- **对下游的具体建议**：在拿到 MAME 方法节之前，**不要把 MAME 当作 "agent×依据 影响矩阵" 的出处**（见 #4 的"对我们的影响"）。

### B. Novelty Search（Lehman & Stanley 2011, *Evolutionary Computation* 19(2):189–223）**原刊 PDF**

- **试过什么**：`web_search` 命中的可用全文是 Lehman & Stanley 自撰的 GPTP-IX 章节 **"Novelty Search and the Problem with Objectives"**（ResearchGate 上的作者上传全文），其中复述了与 GPEM 2011 相同的新颖度定义与公式；**期刊版 PDF（mitpressjournals `10.1162/EVCO_a_00025`）本轮未抓到**。
- **结论**：Novelty Search 的定义句我用的是**双重来源**——①Curiosity Search（PMC5010182，全文）里对 NS 的一手转述；②GPTP-IX 章节全文。二者一致（新颖度 = 到 k 近邻的平均距离；比较对象 = 当前种群 + archive）。**证据强度标为"全文（经 CS 一手转述）/ 二手页面（章节）"，不标"原刊 PDF"。**
- **对 #3 裁决的影响**：无 —— 因为 #3 的核心结论是"**两篇论文都没有 leave-one-out 定义**"，这个结论只需要**读遍全文并确认不存在**，而我们把两篇的全文（CS 全文 + NS 的完整定义章节）都读过了。

### C. 我们**没有**去核、也不属于本任务范围的东西

- ToT **Fig 3(a) 的矢量数据**（b=2/3/4 的中间成功率）、官方仓库发布日志与论文 74% 的 5pp 差异：属 `DEEP-04-ToT-quotes.md` 已记录的旧结论，本轮不重复。
- MAME 的 `weight vector modulation` 到底是改权重还是改 prompt：仍未解（`LIT/24_sciencedirect_pick.md` 已标"未读到方法节"）。
- Diversity Collapse 的附录 G.4 / 表 5 / 表 25 等次级读数：不属于本轮 5 条子项。

---

## 修订清单（按优先级）

| 优先级 | 文件 : 行 | 现状 | 应改为 |
|:-:|---|---|---|
| 🔴 高 | `COLLAPSE-REMEDY-2026-10-22.md:100` | `Curiosity Search："某条信息是不是独立维度 = 拿掉它之后结论是否改变"` | `判据形态借自 Curiosity Search（PMC5010182, "Do Doors Represent Distinct Skills?"）的反事实实验；"某条信息=独立维度"是**本项目自造**（spec §3 已标注）` |
| 🔴 高 | `REFERENCE-AND-CORRECTIONS-2026-10-22.md:38` | 同上（带引号像论文原话） | 同上，并删掉引号式转述 |
| 🔴 高 | `HANDOVER-GROUP2-DESIGN-LAYER1.md:74` | `MAME（agent×依据 影响矩阵）` | `MAME（agent×agent 动态置信矩阵 + 答案可信度；"依据 ID"为我们的设计，未见原文）` |
| 🟠 中 | `HANDOVER-GROUP2-DESIGN-LAYER1.md:86` | `正是在 GOMS 先验格子里填` | `在 Newell(1980) 问题空间 + GOMS 四要素启发的 Figure 3 节点架构里逐格填写（GOMS 全文仅被提及一次）` |
| 🟠 中 | `HANDOVER-GROUP2-DESIGN-LAYER1.md:84` | `arXiv 2405.12147 + Cognitive Systems Research 94:101409` | 写全两个标题：`Eliciting Problem Specifications via Large Language Models`(arXiv:2405.12147) / `Eliciting problem specifications for LLM-Modulo cognitive systems`(CSR 94:101409, DOI 10.1016/j.cogsys.2025.101409) |
| 🟠 中 | `LIT/11_1901.01753.md:20, 135, 153-155` | `5 维基因向量` | `5 种障碍类型 / 9 个基因参数（Table 1）；§4.3 归一化距离用的是只开 3 种障碍的 5 值缩减编码，β=√5` |
| 🟡 低 | `HANDOVER-GROUP2-DESIGN-LAYER1.md:71` | `§4.2 + 附录 I/M` | `§4.2（strong attractor）/ §4.3（Authority-Induced Collapse 定义）/ Fig.3 图注（Sycophancy Trap）/ §5.2（local pockets of divergence）+ 附录 I/M` |
| 🟡 低 | `HANDOVER-GROUP2-DESIGN-LAYER1.md:75, 77` | `ToT（同源 74% / 换评估器 64% / 31%）` | 数字不变，但建议加限定："均为 Game of 24、n=100、64%/31% 仅见于 Appendix B.2 正文一句；GPT-3.5 生成时 proposal prompt 由 1-shot 改 3-shot" |

---

*核证人：引用核证员（general）。本文件由本次核证新建；仓库内其它文件一律未改动。*
