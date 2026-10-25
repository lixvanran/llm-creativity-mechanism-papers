# 第四组权威材料 · 精选归档索引

> ★ **归档日期**：2026-10-25 ｜ **执行**：W4（`455934034420460`）｜ **裁决**：owner（Mavis，`455919955690212`）—"第四组材料归档进仓"
> ★ **本目录的用途**：让 `papers/04_D_StateMachineIsNotYetAPrompt_交差稿.md` 里**每一个 `§` 锚点与每一条读数**都能在**仓内**定位并逐字复核。
> ★ **原文零改动**：本目录所有文件均为**从 drive 交付包原样拷贝**（未编辑、未重排、未"清洗"）⇒ ★ **原文的任何一处措辞都保持交付时的样子**。

---

## 0 · 来源与校验

★ 本目录的文件来自**第四组在 drive 上的两个交付包**（★ **第四组有两个不同的 drive 会话**：主会话 `454289901498997` 交付权威材料，改稿会话 `455860333474156` 交付改稿产物）：

| drive 交付包 | node_id | 包 sha256 | 条目数 | 本目录取用了其中 |
|---|---|---|---:|---|
| `第四组论证_交付.zip` | `454318521676058` | `2d90bfec4b487caaa2756a9717d87f7faac23942f00be57392c5333e9f474356` | 72 | 5 个文件（见下） |
| `第四组_v6_REPORT.zip` | `455786470490828` | `8b9bf20fd733d8f190c26d8ba07c1b0fdbb8836d5a659ae2bdcbf38e535eb1e2` | 29 | 3 个文件 |
| `第四组_v6_DATA.zip` | `455786470490829` | `9baf703ede4fa05ac58919da1a54a69b4464eba853d901565ed5d55c8bca76a8` | 206 | 2 个文件（`archive/top_level/`） |
| `第四组_v6_CODE.zip` | `455786470490827` | `4e4dc8ac93b5e6bc691d27f517c6db9866658c795c5cb703bcfb94b0790b22c0` | 72 | 0（代码包，本轮不引用其内容） |

★ **解包注意**：`第四组论证_交付.zip` 的中文路径名是 **UTF-8 字节被当作 cp437 存储**的 ⇒ 必须用 Python `zipfile` 逐条做 `name.encode('cp437').decode('utf-8')` 重命名后再解出，否则文件名全是乱码。
★ **精选原则**：★ **只收录 04 篇正文/§ 锚点真正引用到的文件**；★ **不收录** `第四组_v6_DATA.zip` 的 206 条原始数据与 `第四组_v6_CODE.zip` 的 72 个代码文件（★ 仓会爆、交付包会臃肿）⇒ 需要回查时按上表的 node_id 回 drive 取。

---

## 1 · 收录清单（★ 原始相对路径保留 ⇒ 仓内定位 = 包内定位）

| # | 仓内路径 | 原始包内路径 | sha256（全文） | sha256（前 8 位） | 04 篇里被引用的位置 |
|:-:|---|---|---|---|---|
| 1 | `来源与底稿/第四组/第四组交付/第四组论证.md` | `第四组交付/第四组论证.md` | `e7dfeaf7b09fa5f413d99fafbb96300e1cf7f053e582ff9a6737708a61fe65b7` | **`e7dfeaf7`** | §1.5 贡献表、§1.6.3、§1.8、§2.1（状态 8 字段 / role 对照 4.390）、§2.2、§2.3、§2.5、§3.3、§3.4、§3.5、§3.7、§4.1、§5.1、附录 C 多数行 |
| 2 | `来源与底稿/第四组/第四组交付/测量方案裁决.md` | `第四组交付/测量方案裁决.md` | `604f1fffcbc7b45d005f70c655d1fcb3df290cca164f9d7aabdaedb1136892b0` | **`604f1fff`** | 附录 A.2（判据终局的裁决依据） |
| 3 | `来源与底稿/第四组/第四组交付/data/report_p1.md` | `第四组交付/data/report_p1.md` | `f8f6d437f208f98ac175f14215e8996c6f0128757e78ef31d7640e82723209de` | **`f8f6d437`** | §3.2、§3.3（D-1 同步率）、§3.4（D-2 置换敏感度）、§3.7、§10.1、附录 C |
| 4 | `来源与底稿/第四组/第四组交付/experiment-design/PREREG_p1.md` | `第四组交付/experiment-design/PREREG_p1.md` | `08fe9e29d159f7a7f7509148447855db419c7112b598296d06bdd64ada2c7942` | **`08fe9e29`** | §3.1（预注册与总判决规则）、§3.2（设计/锚点/换值）、附录 A.3、附录 C |
| 5 | `来源与底稿/第四组/第四组交付/borrowed/BORROWED.md` | `第四组交付/borrowed/BORROWED.md` | `32c68bdad2d86d9ad9adc441e29de5fa8ae31b0d49c7e13a3a3d74a7aad3016d` | **`32c68bda`** | 附录 A.2（借用纪律：multi-mind v0.8 副本不改原件） |
| 6 | `来源与底稿/第四组/group4_state_driven/archive/top_level/DRIVER_AUDIT.md` | `group4_state_driven/archive/top_level/DRIVER_AUDIT.md` | `23533069874d08f3feba0a6c639bfa2d4c5a986d0f50799ac2ce45c074523634` | **`23533069`** | §2.4（"干净"的定义 + v1 封闭率审计）、§5.2（v1 D2/D1 3.5–5.1×）、§7.8、附录 A.2、附录 C |
| 7 | `来源与底稿/第四组/group4_state_driven/archive/top_level/REPORT_arch2.md` | `group4_state_driven/archive/top_level/REPORT_arch2.md` | `775c4f8fe607a77bccdca01d49ab8371394ff9dee097ab399b587f0ac5651134` | **`775c4f8f`** | §2.4（v2 封闭率 70% / 驱动核心 0%）、§5.2（干净≠有力）、§6（thinking 失控）、§8.2、附录 A.2、附录 C |
| 8 | `来源与底稿/第四组/group4_state_driven/REPORT_arch6_stage1.md` | `group4_state_driven/REPORT_arch6_stage1.md` | `d52cd51afc01d885058f30a3cc7164f5599fc1dc7b6e307a56e3a36f88bcd49c` | **`d52cd51a`** | §8.2（Stage-1 排序改变率 3/8 = 0.3750，CI [0.137, 0.694]）、附录 C |
| 9 | `来源与底稿/第四组/group4_state_driven/EXEC_LOG_stage1.md` | `group4_state_driven/EXEC_LOG_stage1.md` | `18585e34c0a15a53f46fd81bea1884d4b26d86f6810ce6eec5902d3e8751f526` | **`18585e34`** | §6（thinking 预算失控的 Stage-1 旁证）、附录 C |
| 10 | `来源与底稿/第四组/group4_state_driven/prereg/PREREG_v6.md` | `group4_state_driven/prereg/PREREG_v6.md` | `31c81dfc8ddf68a3cf8cd777a371683f58e4106935cecaa5cd747757c2befcfb` | **`31c81dfc`** | §8.2（v3 的三道门）、§10.1、附录 A.2、附录 C |
| 11 | `来源与底稿/第四组/group4_state_driven/PAPER_draft.md` | `group4_state_driven/PAPER_draft.md` | `1c4467c7209dfff661556916f292aa23ac87b6275372bf358d8c65e4ed870b12` | **`1c4467c7`** | ★ **§1.2 那条限定的出处**（"情感型一次都没进过实验"，★ 在该稿**五处**）⇒ ★ **V1 审稿后归档** |
| 12 | `来源与底稿/第四组/group4_state_driven/archive/runs/p2_orig.jsonl` | 同 | `3948eac2642a3fd1e99f7eb52344bae78c1341d7de718da407612af681c7bcbc` | **`3948eac2`** | ★ **D-1 复算的原始输入**（原锚点批次产出，75 条 `kind=gen`）⇒ ★ **V1 审稿后归档** |
| 13 | `来源与底稿/第四组/group4_state_driven/archive/runs/p2_swap.jsonl` | 同 | `286d6ba0857d6461d35e256161a1b69fc62e4a32cba362a6d6d681f1625d72b0` | **`286d6ba0`** | ★ **D-1 复算的原始输入**（换值批次产出，45 条）⇒ ★ **V1 审稿后归档** |
| 14 | `来源与底稿/第四组/group4_state_driven/archive/runs/p2_ckf_analysis.json` | 同 | `c78293def774b848f3762bdef710da82a85731f646080bbe6e695f7ab8e21485` | **`c78293de`** | ★ **复算逐行对拍的对照物**（第四组自己的分析产物，45 行配对）⇒ ★ **V1 审稿后归档** |
| 15 | `来源与底稿/第四组/复算/recompute_d1.py` | ★ **W4 自写**（非第四组产出） | `15329d39e0d22177eb79907d649b5038e2cadcf201874d66b67bd49312b533c5` | **`15329d39`** | ★ **本轮唯一的证伪装置**（§3.3 / §4.1 / §4.3）⇒ ★ 第三方可离线独立重跑 |
| 16 | `来源与底稿/第四组/复算/README_复算说明.md` | ★ **W4 自写** | `a1ac0a24…`（见 `SHA256SUMS.txt`） | **`a1ac0a24`** | ★ **复算脚本读什么 / 判据定义 / 统计方法 / 三条第三方核对点** |
| 17 | `来源与底稿/第四组/改稿留痕/04_D_V1复核前快照.md` | ★ **W4 自写**（★ 04 稿在 V1 复核**之前**的快照） | `369fa828fe32120073e03e8cba0a09fdb7eb6c6a700e4f69e9caba3b5cc34118` | **`369fa828`** | ★ **改前/改后的可核对凭据**（★ 与 04 稿当前版逐行 diff 即可还原本轮改了什么） |

### 1b · ★ 复算装置（`复算/`）

| 文件 | 是什么 |
|---|---|
| `recompute_d1.py` | ★ **独立复算 D-1 换值同步**（★ **不 import 第四组任何模块**、★ **不写死基线 sha**、★ **规模数全部从数据里数**、★ **`sys.dont_write_bytecode = True`**、★ 纯标准库、★ **只读输入**） |
| `README_复算说明.md` | ★ 它读什么 / 判据定义 / 统计方法 / **第三方按这三条核**（★ 能复现第四组自己公布的三个 p 值 ｜ ★ 逐行对拍不一致数 = 0 ｜ ★ 臂间 2×2 与 p 值） |

★ **跑法**（★ 路径相对自身定位 ⇒ 换机器不崩）：
```bash
python3 来源与底稿/第四组/复算/recompute_d1.py
```

### 1c · ★ 改稿留痕（`改稿留痕/`）

| 文件 | 是什么 |
|---|---|
| `04_D_V1复核前快照.md` | ★ **04 稿在 V1 审稿阶段一复核【之前】的完整快照**（★ 149,317 B，★ sha256 `369fa828…`）⇒ ★ **与当前 04 稿逐行 diff ⇒ 即可机械还原本轮（F4/F5/F7）改了什么** |

---

## 2 · 校验方法（★ 任何第三方可独立复现）

```bash
cd <仓根>
sha256sum -c SHA256SUMS.txt          # ★ 全部条目应为 OK
# 单文件核对（以第四组论证主文档为例）：
sha256sum 来源与底稿/第四组/第四组交付/第四组论证.md
#   期望：e7dfeaf7b09fa5f413d99fafbb96300e1cf7f053e582ff9a6737708a61fe65b7
```

★ **04 篇正文里的引用格式**：`来源与底稿/第四组/<路径> §X（sha256 前 8 位）` ⇒ ★ **仓内可核优先于 drive 节点**；★ drive 的 node_id 只在 §0 与本索引里作为**次级溯源**保留。

### 2b · ★★ 复算的核对方法（★ 本轮唯一的证伪装置）

```bash
# 在仓根直接跑（★ 路径相对自身定位 ⇒ 换机器不崩）
python3 来源与底稿/第四组/复算/recompute_d1.py
```
★ **第三方按这三条核**（★ 详见 `复算/README_复算说明.md` §6）：
1. ★ **能否复现第四组自己公布的三个 p 值** —— **0.0010**（C1 vs 随机基线）｜ **0.0923**（C2 vs C0）｜ **0.0063**（C2 vs C1）。
2. ★ **与第四组 `p2_ckf_analysis.json` 逐行对拍的不一致数 = 0**（45/45 行一致）。
3. ★ **臂间 2×2** —— **C2 vs C1**：both=0／only_C2=11／only_C1=1／neither=3 ⇒ **p=0.0063**；★ **C2 vs C0**：both=1／only_C2=10／only_C0=3／neither=1 ⇒ **p=0.0923**；★ **C0 vs C1**：both=1／only_C0=3／only_C1=0／neither=11 ⇒ **p=0.2500** ⇒ ⇒ **C0 与 C1 不可分辨**。
⇒ ★ **第 3 条的第三条，是 04 篇 §4 从"因果"降为"不可分辨"的依据**（★ 04 篇 `T-D-07`）。

---

## 3 · ★ 本目录**没有**收录什么（★ 如实登记）

| 未收录 | 在哪 | 为什么未收录 |
| `group4_state_driven/paper/PAPER_draft.md`（★ 83 KB，★ v6 稿的**另一个版本**） | drive node `455786470490828` | ★ 包根的 `PAPER_draft.md`（96 KB）已收录，★ 本篇引用的是它（★ "情感型"边界声明在两版里都有，★ 但行号锚点以包根版为准） |
| `第四组_v6_REPORT.zip` 的 `DELIVERY_stage1.md` / `WORKPACK2_STATE_PIPELINE.md` / `WORKPACK3_MIN_ARCHITECTURE.md` / `REPRO_MINIMAL_SET.md` / `SHASUMS.md` / `prereg/PREREG_v3~v5` / `prereg/STAGE1_SPEC.md` / `prereg/STAGE2_*.md` / `prereg/TOPIC_SPEC_*.md` / `reports/LIT_*.md` / `reports/REPORT_arch3~5.md` | drive node `455786470490828` | ★ 本篇**未按 § 锚点引用**它们 ⇒ 暂不入库；★ 若审稿 Agent 需要核 v6 的中间轮次，按 node_id 取 |
| `第四组_v6_DATA.zip` 的其余原始数据（`runs/arch*_compare.jsonl` / `probe*.jsonl` / `ckf*.jsonl` / `gk_*.jsonl` 等）与 `archive/top_level/*.py` | drive node `455786470490829` | ★ 全量入库会让仓与交付包臃肿；★ **但 D-1 复算真正需要的三份（`p2_orig` / `p2_swap` / `p2_ckf_analysis`）已收录** ⇒ ★ **第三方可离线独立复核本篇的 D-1 读数** |
| `第四组_v6_CODE.zip` 的 72 个代码文件 | drive node `455786470490827` | ★ 本篇**不引用其代码内容**（代码侧的引用在仓内 `来源与底稿/arch4/code/`） |
| `第四组论证_交付.zip` 的 `mechanism-design/deliverable.md`（104 KB）/ `red-team/deliverable.md`（133 KB）/ `evidence-check/deliverable.md`（79 KB）/ `experiment-design/*.py` / `data/*.jsonl` | drive node `454318521676058` | ★ 未被本篇按 § 锚点引用 ⇒ 暂不入库（★ **`evidence-check/deliverable.md` 是「Digital Twin R² 0.10→0.50 黑名单 B5」的原始记录**，★ 若要复核 `T-D-01` 的"外部支撑已撤回"这一事实，★ 需从该 node 取 —— ★ 登记为 `T-D-01` 的取证入口） |
| `第四组规划.md` / `第四组论证.pdf`（35 页）/ `g4_metrics.py` 等 | drive node `454318521676058` | ★ 未被本篇引用 |

★ **★ 交付态的一条原则（本目录存在的理由）**：★ **凡是包内正文引用到的材料，就必须在包内** ⇒ ★ **第三方没有我们的 drive、也打不开 node_id** ⇒ ⇒ ★ **drive 的 node_id 只作次级溯源**（★ 本索引 §0 与 04 篇附录 A.2 保留它们）。

---

## 4 · 引用纪律（本目录对 04 篇的约束）

1. ★ **原文零改动**：本目录任何文件都**不得**被"顺手修正" ⇒ 第四组材料里的**已撤回主张、黑名单条目、措辞瑕疵全部保持原样**（★ 例：`第四组论证.md §5.1` 里那条"4.35 → 4.39 方向反了"的引用更正，就是第四组自己写下的撤回记录 ⇒ 04 篇引用它时**必须连"已撤回"这个事实一起引**）。
2. ★ **04 篇引本目录时必须带 `§` 锚点 + 文件 sha256 前 8 位** ⇒ 便于第三方判断"引的是哪一版"。
3. ★ **本目录的 sha256 已登记进仓根 `SHA256SUMS.txt`** ⇒ `sha256sum -c` 可一次核完。

---

*本索引由 W4 生成于 2026-10-25（owner 裁决"第四组材料归档进仓"）。★ 原文未改动。*
