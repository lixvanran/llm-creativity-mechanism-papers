# LLM Agent 创造力机制 · 科研过程数据包

**这不是论文集。** 这是一份**过程数据**包：读数、出处链、判据定义、审计轨迹、待取证任务、以及阴性结果。
叙述性的结论文档在 `papers/`，它们是**过程记录**，其中包含**未经外部同行评议**的结论陈述。

MIT License ｜ 数据快照 2026-10-25 ｜ 面向第三方复算、审计与再利用

---

## 为什么以数据形态发布

这项工作的实际产物不是几篇成稿，而是**一批带出处链的读数**和**一批被判为「不可分辨」的负结果**。
后者在成稿里只能占一行，在数据形态下才是可检索、可统计、可复用的对象。

所以本仓的定位从「成果展示」改成「**过程数据仓库**」：

| | 原来的做法 | 现在 |
|---|---|---|
| 仓里放什么 | 只放成果（正文），过程日志与跑批输出留在私有仓 | **过程数据本身就是产物** |
| 读数能不能被程序读 | 散在散文里，只能人读 | `data/*.jsonl`，逐行带 `file:line` 出处 |
| 阴性结果 | 埋在正文某段 | 单独立表 `data/negative_results.jsonl`（475 行） |
| 待取证任务 | 散在各篇的表格里 | 单独立表 `data/open_tasks.jsonl`（45 条） |
| 判据 | 脚本在 `tools/`，靠人记得跑 | 脚本在 `tools/`，`run_finalize.sh` 一条命令跑完 |
| 判据能不能信 | —— | 每个判据**配负向测试**（篡改一下必须能红） |

---

## 数据地图

| 路径 | 是什么 | 怎么用 |
|---|---|---|
| `data/` | **机器可读的过程数据**（6 个数据集，2,329 行） | 直接 `json.loads` 每行；索引见 [DATASETS.md](DATASETS.md) |
| `tools/` | 判据、抽取器、复算脚本、打包器 | 全部离线可跑；多数不耗 token、不需要 key |
| `papers/` | **叙述层**：五篇结论文档 + 详稿 + 审稿/改稿留痕 | 当过程记录读，**不要当投稿件引用** |
| `support/` | 总纲、缺口清单、待填审计、回源对照表 | 判定「哪些结论现在能下」的依据表 |
| `来源与底稿/` | 一手材料（各组原始产出与底稿） | 出处链的终点；2 组的历史产出 128 个文件在这 |
| `baseline/` | 改写前正文快照 | 「读数是新增还是沿用」的比对基准 |
| `证据与底稿` 相关脚本 | 复算（第四组 McNemar 三项、② 篇净增益双边重算） | 第三方可独立复算 |
| `四篇正文合订本_2026-10-25.md` | 五篇合订本（单文件） | 只想读结论的人从这里进 |

---

## 怎么取这份数据

```bash
git clone https://github.com/lixvanran/llm-creativity-mechanism-papers.git
```

`data/readings.jsonl` 约 1.1 MB，**超过 GitHub contents API 的 1 MB 内联上限**：
只想取单个小文件用 `contents` API；取大文件用 `GET /git/blobs/<blob sha>`
（带 `Accept: application/vnd.github.raw`）或直接 clone。
受限网络下 `raw.githubusercontent.com` 可能不可达 —— 走 API 或 clone。

---

## 三种用法

### 1) 跑判据（验证这份数据自洽）

```bash
# 全量收口：重建 docx → 跑全部判据 → 跑负向测试 → 打包 → 交付态复跑
bash tools/run_finalize.sh

# 只跑数据包的校验器（逐条回源 + 负向测试）
python3 tools/check_data_package.py --negative
```

### 2) 复算读数

```python
import json
rd = [json.loads(l) for l in open('data/readings.jsonl', encoding='utf-8')]
# 每条带 sources: [{file, line, class}, ...] -> 第三方可自己去那一行核
hit = [r for r in rd if r['token'] == '0.886']
```

### 3) 查某个读数从哪来

```python
neg = [json.loads(l) for l in open('data/negative_results.jsonl', encoding='utf-8')]
undet = [r for r in neg if '不可分辨' in r['markers'] and r['numbers']]
# 每条：paper / file / line / section / markers / numbers / text
```

---

## 数据集索引

见 **[DATASETS.md](DATASETS.md)**（由 `tools/build_data_package.py` 自动生成，勿手改）。

| 数据集 | 行数 | 是什么 |
|---|--:|---|
| `readings` | 1678 | 读数全集：token × 篇，含出处与出处等级 |
| `negative_results` | 475 | 阴性/未定结果行（不可分辨、未测、未检出…） |
| `open_tasks` | 45 | 待取证任务（要补什么 / 去哪找 / 判据 / 回填后影响 / 成本） |
| `audit_verdicts` | 108 | 审稿逐条判定 |
| `audit_objects` | 23 | 每次判定的**被审对象身份**（sha）—— 判定只对它审的那一版有效 |
| `pointer_migrations` | 1 | 指针迁移 25 条（原样保留） |

**出处等级**：`一手材料`（在 `来源与底稿/` 里）> `审稿留痕` > `复算底稿` > `改稿规格` > `前作基线`。
规则细节见 [PROVENANCE.md](PROVENANCE.md)。

---

## 叙述层：五篇结论文档（= 过程记录，不是投稿件）

| 代号 | 题 | 一句话 claim | 状态 |
|:-:|---|---|---|
| **C** | *Six Ways to Look Done Without Being Verified* | 「看起来完成」与「被独立验证过」之间有系统性落差；给出可执行防伪规程 + 外部只读审计协议 | 成稿（position paper，无主实验） |
| **A** | *Selection Is Not Creation* | 在有外部可核验依据的域上，工作流类创造力方法不产生增量 | 结论为**窄表述** |
| **D** | *A State Machine Is Not Yet a Prompt* | 当前形态的状态机**未被证明**优于等强度提示词 —— 边界结论 | 整合稿 |
| **L1** | *Premature Convergence Is a Structural-Dimensional Collapse* | 「闭合」是相对于参照系的可证伪命题；三层分离协议 | 判决**混合**（表述层成立 / 解码层否定 / 注意力归因不支持） |
| **L3** | 层3 自修改 | 自迭代/学习路线的机制与边界 | 成稿 |
| ~~B~~ | *Genre Drift and Object Drift Are One Mechanism* | 多 Agent 工作流把用户问题「降格」成待分析对象 | 只有缺口清单与预注册骨架 |

**为什么切成五件而不是一件**：合并的诱惑来自「材料都在手上」，不是来自「科学上该合」。
切分标准是「一件 = 一个可独立检验的 claim」，且须同时满足 独立判据 / 独立数据 / 独立论点。

**①篇有两件**：`papers/01_L1_PrematureConvergence_交差稿.md`（主稿，五章结构）
与 `papers/01_L1_注意力层归因_详稿_2026-10-25.md`（详稿，含数字台账、机制假说 H1–H7、引用要求）。

---

## 三条必须一起讲的限定

> 这三条不是某一篇的内部问题，而是跨篇共享、且会改变读者对结论强度判断的事实。
> 主动说，比被逐条追问强得多。

**1 · 型号池静默下架，历史 dual 臂读数的分母是 4，不是 5**
`MODELS` 池第 5 位 `MiniMax-M2.1` 已 404，5 分支臂的第 5 支返空，被 `if o` 过滤，5 支静默变 4 支，表上看不出来。
晚间独立复核还查出 `MiniMax-M2`（第 6 支）同为死型号，任何声称用满 6 支的场合，读数都要先核支数是否真为 6。
历史对照值 `+0.0483` 因此作废（它算在 4 支口径下），对照域必须重跑。

**2 · 层1 的归因天花板：注意力机制归因不成立，不是「没做」**
全仓没有任何注意力权重 / logits / hidden state / 内部激活数据；托管 API 静默忽略 `logprobs`，
NLL / perplexity / typicality / PMI 全族作废；无 GPU。唯一允许的写法：
**「与注意力机制相容，但本文未检验该假设」**。这是能力边界，不是未尝试。

**3 · 「不可分辨」≠「无效应」**
凡报「不可分辨」，必须同时报检出力地板；门槛锚在本批自己的噪声地板，不许拿文献阈值当判决线；
方向一致只能作辅助条件且须先过 H0 标定。H0 的唯一合法来源 = 同臂、同题、不同 rep
（rep 差异是纯噪声，天然零分布）。`θ₀` 以题内 rep σ 为单位（如 θ₀ = 1.33 σ），
引用时必须写成「≥ θ₀ 个题内 rep σ」，否则会被误读成绝对阈值。

---

## 证据四档（对外一律按这四档说）

| 档位 | 含义 |
|:-:|---|
| `【已核】` **已跑批读数** | 有出处、已回源、预注册在先 |
| `【已核】` **事后重算** | 口径修正后的重算，修正的必要性不依赖结果方向 |
| `【方向】` **探索性 / 事后校准** | 无事前预注册，只作方向性证据 |
| `【待完成】` **待填** | 判据已定版，等跑批 |

**回源对照表**（`support/08_回源对照表.md`）给出每个头条数字到源文件行号的对照，84 / 84 定位命中。

**待填审计**（`support/07_待填审计_判据定版状态.md`）把全部真实待办逐条分级：24 条
（`【已核】` 判据已定版 10 条、`【方向】` 形式待补 5 条、未成文或当前条件下不可判定 9 条）。
判据定版状态是可核验的表，不是口头承诺。

---

## 复现与核验

```bash
# 1) 重建全部 DOCX（构建参数固化 -> 外部可逐字节重建）
cd tools && bash build_docx.sh ../papers

# 2) 核验 DOCX 无单元格丢失
python3 tools/check_docx.py papers

# 3) 完整性校验（每个受管文件一行 sha256）
sha256sum -c SHA256SUMS.txt

# 4) 数据包校验（逐条回源 + 负向测试）
python3 tools/check_data_package.py --negative
```

**为什么把 pandoc 参数写死随包交付**：pandoc 默认 `smart` 扩展会把 `"` → `“”`、`...` → `…`，
同一份 md 在不同机器、不同 pandoc 版本下可能产出不同的 docx，外部就复核不了我们交付的 docx。
关闭 `smart`，md 与 docx 逐字一致，「单元格零丢失」才是个真判据。

**打包规则**：交付包的内容集合由 `git ls-files` 定义 -> **先 commit，再打包，再自检**。
顺序反了会出现「包里少文件、而自检照样全绿」。

---

## 本仓的诚实边界

| 项 | 状态 |
|---|---|
| 24 条待办中 9 条判据未成文或不可判定 | 已分级公开（`support/07_`） |
| C 篇是 position paper | 没有主实验。交付形态是规程 + 六个真实失效案例 + 一套可执行审计协议，不是已被验证能提升准确率的结论 |
| A 篇结论为窄表述 | 不是「架构没用」，而是「架构的杠杆是【交互结构 × 任务结构】的交互，且二者必须分开测」 |
| L1 判决是混合的 | 表述层成立 / 解码层否定 / 注意力归因不支持，必须拆开写 |
| D 篇是边界结论 | 「当前形态的状态机未被证明优于等强度提示词」不等于「状态驱动这条路无效」 |
| B 篇没有正文 | 3 项必补实验未做，只有缺口清单与预注册骨架 |
| **②篇批 2 的逐条判决客观不可达** | 三处查证留痕：仓内 `runs/` 无、两个 drive 包无、GitHub `cmp8-handover` 的 `runs/` 被 gitignore。判决维持「不可分辨」 |
| **①篇 α 的 `0.886` / `0.944` 第三方不可独立复算** | 取数脚本与机读数据未随稿归档 |
| **层3 部分读数不能由包内完全复现** | 底稿 `workflow.py:1088` 缺陷，已披露，不改口径 |
| **v3.1 审稿 PASS 的效力边界** | 绑的是当时的包 sha 与当时的五篇 sha。措辞与结构重写后，**只在读数与判决层覆盖，逐字层不适用** |

**本仓是过程数据快照，不是终稿。** 终稿的剩余工作及其阻塞，逐条列在合订本与 `data/open_tasks.jsonl` 里。

---

## 引用

BibTeX 见 `papers.bib`（作者与发表信息为占位）。

```bibtex
@misc{lixvanran2026papers,
  title  = {LLM Creativity Mechanism: research process data package},
  author = {lixvanran},
  year   = {2026},
  note   = {MIT License. Process data, not a peer-reviewed article. See DATASETS.md for the data index and README for evidence tiers and known limitations.}
}
```

**引用本仓时请保留各篇「诚实边界」与「证据四档」的标注**——那不是免责声明，是结论的一部分。

## License

MIT —— 见 [LICENSE](LICENSE)。
