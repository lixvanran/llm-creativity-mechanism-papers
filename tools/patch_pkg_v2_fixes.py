#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_pkg_v2_fixes.py —— 包级复核 v2（绑定包 `6afcc844…`）的 11 条修复 · 【唯一一次执行脚本】

★ 为什么它进包：★ v2 报的 7 应修 + 4 建议全部落在**文本与工具**上 ⇒ ★ 「改了什么」若只写在
  收口报告里，第三方只能信我一面 ⇒ ⇒ ★ **把执行脚本留在包内** ⇒ 第三方可核「哪一行被替换成哪一行」。

★ ★ **为什么用【行号】定位而不是【字符串匹配】**（★ 2026-10-25 实踩）：
  ★ 第一版用「old_string → new_string」精确匹配 ⇒ ★ 3 条替换串因**手抄**与文件差一个全角字符而
  匹配不上 ⇒ ★ 而 Read 工具的输出**看起来**和文件一样 ⇒ ★ ⇒ **「读出来」不等于「抄对了」**。
  ⇒ ⇒ 落法：★ **按行号替换**（★ 行号从文件里数出来，不经人手抄）⇒ ★ 手抄错误彻底消失。

★ 用法：
    python3 tools/patch_pkg_v2_fixes.py text     # 阶段一：11 条文本/工具修复
    python3 tools/patch_pkg_v2_fixes.py counts   # 阶段二：把 @@占位符@@ 换成本包实测规模数
    python3 tools/patch_pkg_v2_fixes.py check    # 只报状态，不写

★ 纪律：
    ① **自下而上应用**（★ 行号替换会让后面的行号偏移 ⇒ ⇒ 倒序 ⇒ 前面的行号不动）。
    ② **替换前先校验锚点**（★ 每条编辑带一个【锚点子串】⇒ ★ 锚点不在 ⇒ 报错退出 ⇒ 不许"看起来改了"）。
    ③ ★ **不写死会变的数字**：★ 包规模类数字一律用 `@@占位符@@` ⇒ 阶段二按【最终文件集】实测填入。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OVERVIEW = "交付总览_人肉审版_2026-10-25.md"
NOTES = "交付说明_四篇改稿_2026-10-24.md"

# ══════════════════════════════════════════════════════════════════════
# (文件, 行号, 锚点子串, [新行...])
# ★ 锚点必须出现在该行里（★ 用来证明「我改的是我以为的那一行」）
# ══════════════════════════════════════════════════════════════════════
LINE_EDITS = [
    # ─────────────────────── 交付总览 ───────────────────────
    (OVERVIEW, 171, "owner（Mavis）自撰", [
        "*2026-10-25 · owner（Mavis）自撰 · ★ 本文所有断言均带回源（文件路径 / 行字节 / sha256）· "
        "★ 未核到的写成\"未核到\"/\"待重打\"，★ **没有编造**。*",
        "*★ 本文件所在包的内容锚点 ＝ `sha256sum SHA256SUMS.txt`（★ 非循环）· "
        "★ 包级复核 v2 绑定 `6afcc844…` · ★ **改稿过程史（旧分支 33 commits）随 2026-10-25 "
        "沙箱重置丢失且从未推送 ⇒ 不可核、不在包内**。*",
    ]),
    (OVERVIEW, 167, "`tools/`", [
        "| `papers/包级复核报告_交付包_2026-10-25.md` | ★ **包级复核 v2**（绑定 `6afcc844…`）："
        "阻断 0 · 应修 7 · 建议 4 |",
        "| `papers/包级复核报告_交付包_2026-10-25_v1.md` | ★ **包级复核 v1**（绑定 `7a602aa3…`）："
        "5/5 通过（★ 保留 ⇒ 复核链不断） |",
        "| `papers/包级复核收口报告_2026-10-25.md` | ★ **本轮收口**：11 条逐条处置 + 版本台账 + "
        "一条新发现（★ 工具会污染被检树） |",
        "| `tools/` | ★ `build_docx.sh`（固化构建命令）· `embed_src_sha.py`（源指纹内嵌）· "
        "`check_docx.py` · `check_l3.py`（原仪器）· `check_package.py` · `verify_l3_code_facts.py` · "
        "`pack_papers.py/.sh` · `patch_pkg_v2_fixes.py`（★ 本轮 11 条修复的执行脚本） |",
    ]),
    (OVERVIEW, 154, "还有三条纪律是这轮逼出来的", [
        "★ **还有三条纪律是这轮逼出来的**（已写进工具与文档）：★ ① **断言必须回头读产物**"
        "（写入中 = 读中间态 = 假红）★ ② **断言必须在交付态读**（\"我这边绿\" ≠ \"交付就绿\"）"
        "★ ③ **打包产物字节不依赖本地 FS 状态**（时间戳/权限位 ⇒ 跨环境可复现）。",
        "★ ★ **v2 又逼出两条新的**：★ ④ **文档里的数字要么当场重算，要么改成可复算的判据**"
        "（★ 「继承旧包的数字」＝ 自己给自己埋过期雷）★ ⑤ **包不能自证自己的 sha**"
        "（★ 自指悖论）⇒ ⇒ 只能给**非循环锚点**（清单自身的 sha）。",
    ]),
    (OVERVIEW, 152, "同一件事写了两遍", [
        "| 5 | ★ **同一件事写了两遍**（打包 与 `--repro` 两段独立代码）⇒ 第二段漏变量、漏 git 回退 | "
        "审稿人包级复核 | ★ **合并成一条代码路径**（唯一一份 `build()`）⇒ 不可能再分叉 |",
        "| 6 | ★ **两份入口文档把旧包的数字「继承」了下来**（6 处过期 ＋ 1 处自相矛盾："
        "32 vs 31 个 commit）⇒ ★ 第三方读到的会是**错数字** | 审稿人包级复核 v2 | ★ 全部改正 ⇒ "
        "★ 并且**改成不写死易变数字**（★ 规模数写成本版实测并注明以清单为准；★ 包自身 sha/字节数"
        "**不写死在包内** ⇒ 改用**非循环锚点**） |",
        "| 7 | ★ **我把「包 sha 是稳定标识符」当成无条件成立** ⇒ ★ 实际**缺三条边界**"
        "（★ 重建 docx 会改 `dcterms:created` ⇒ 包 sha 必变｜★ 跨 zlib 实现不保证压缩字节相同｜"
        "★ 它标识的是「这一份包字节」，不是「这批内容的语义」） | 审稿人包级复核 v2 | "
        "★ 已按三段式改写（★ 入口文档 ×2 ＋ `pack_papers.py` 的打印文案） |",
        "| 8 | ★ **上一轮我答应「3 分钟把论文交给你」，结果那一轮没交出来**"
        "（会话在修 7 条的过程中断了）⇒ ★ 而且**沙箱一重置，33 个 commit 的过程史也一起没了** | "
        "沙箱重置 | ★ 本轮**先把论文原文交出去**，再交包；★ 过程史丢失这件事**如实写进 §5② "
        "与收口报告**（★ 不粉饰成「可恢复」） |",
    ]),
    (OVERVIEW, 140, "打包器的 git 依赖", [
        "| ★ **打包器的 git 依赖** | ★ 内容集合优先取 `git ls-files`；★ **无 git 时回退目录遍历** ⇒ "
        "★ 包可脱离 git 重建，但**重建出来的是「无 git 视角」的内容集**（★ 本次两者一致，已实测）｜"
        "★ 复核人另实测：**git 完全不在 PATH** 时重建仍产出同一 sha ⇒ 回退分支真的走通了 |",
    ]),
    (OVERVIEW, 136, "Word 侧", [
        "| ★ **Word 侧** | ★ **未验**（本环境无 Microsoft Office / WPS）⇒ ★ 审稿人只验到结构层"
        "（★ **本包 @@DOCXCOUNT@@ 个 docx**（★ `papers/` @@PAPERSDOCX@@ ＋ `support/` 5 ＋ "
        "底稿索引 1）逐个 `testzip()` 0 损坏 · 全部 `.xml`/`.rels` 可解析 · "
        "`[Content_Types].xml` 声明在）⇒ ★ **另**：审稿人用**独立渲染器**（LibreOffice）实开 "
        "`papers/` 下全部 docx ⇒ 全部打开成功且 UTF-8 内容保真 100% "
        "⇒ ★ **不替 Microsoft Word / WPS 背书** |",
    ]),
    (OVERVIEW, 96, "不推的后果", [
        "- ★ **不推的后果**：包里的一切都能从 drive 恢复，★ 但**下一次沙箱重置，连内容集合的"
        "演进过程都没了**",
    ]),
    (OVERVIEW, 95, "我的建议：推", [
        "- ★ ★ **一件必须先说清的事**：★ **旧分支的 33 个 commit（改稿过程史）随 2026-10-25 的"
        "沙箱重置永久丢失了** ⇒ ★ 它们**从未推送**到 GitHub（`main` 停在改稿前的 `faedf371…`）⇒ ⇒ "
        "★ **不可核、不在包内、本地也回不来了** ⇒ ★ **能回来的只有内容**"
        "（★ 本包内容集合 ＝ 被审包 `6afcc844…` 的内容集合，★ **逐字节可核**）⇒ ★ **本仓是重建的**",
        "- ★ **我的建议：推** ⇒ ★ 理由：★ **这正是刚刚发生过的损失**（沙箱一重置，过程史就没了）⇒ "
        "★ 而现在**包已经能自重建、内容锚点非循环** ⇒ ⇒ ★ **推了才是真备份**；"
        "★ 代价是**只备份内容，不备份过程史**（★ 过程史已经没了）",
    ]),
    (OVERVIEW, 93, "push 分支", [
        "### ② 要不要 **push 分支**（★ 沙箱重置后仓已重建；main 未碰）",
    ]),
    (OVERVIEW, 45, "v1→v2 的账", [
        "★ **v1→v2 的账**：包级复核 v1 报了 2 应修 + 1 建议（P-01 交付态时间戳判据假红 · "
        "P-02 `--repro` 崩 · S-01 缺交付态自检）⇒ ★ 我全修完 ⇒ v2 复跑 **5/5 通过、0 新发现** "
        "⇒ ★ **三条的根因与修法都写在包级复核报告里**。",
        "★ **v2→v3 的账**：★ **v2 不是「0 新发现」** ⇒ 报回 **阻断 0 · 应修 7 · 建议 4** ⇒ "
        "★ **7 条应修里 6 条是「入口文档把旧包的数字继承了下来」、1 条是仓级清单失配（R-01）** ⇒ "
        "★ 全部处置（★ 逐条见 `papers/包级复核收口报告_2026-10-25.md`）⇒ "
        "★ **v2 还抓到一个我此前没意识到的东西**：★ 「包 sha 是稳定标识符」这句话**缺边界**"
        "（★ 重建 docx 会改 `dcterms:created` ⇒ 包 sha 必变；★ 跨 zlib 实现不保证压缩字节相同）⇒ "
        "★ 已按 v2 给的三段式改写。",
    ]),
    (OVERVIEW, 43, "包级独立复核", [
        "| 5 | ★ **包级独立复核 v1** | ★ 同一个审稿会话 | ★ **交付包本体**（在解包副本里跑） | "
        "★ **5/5 通过 · 0 新发现**（★ **绑定旧包 `7a602aa3…`**）｜P-01/P-02/S-01 全关闭｜"
        "★ `papers/包级复核报告_交付包_2026-10-25_v1.md`（342 行 / 26,289 B / `62381da6…`） |",
        "| 6 | ★ **包级独立复核 v2** | ★ 同一个审稿会话 | ★ **交付包本体**（在解包副本里跑） | "
        "★ **有条件通过（阻断 0 · 应修 7 · 建议 4）**（★ **绑定 `6afcc844…`**）"
        "｜★ **11 条已全部处置**｜"
        "★ `papers/包级复核报告_交付包_2026-10-25.md`（393 行 / 31,819 B / `b5077789…`） |",
        "| 7 | ★ **owner 收口（包级）** | 我 | v2 的 11 条 | ★ 逐条处置并留痕｜"
        "★ `papers/包级复核收口报告_2026-10-25.md`（★ 含版本台账） |",
    ]),
    (OVERVIEW, 31, "两处副本", [
        "★ **两处副本**：★ 仓内 `<仓库>/dist/…zip` ＋ **交付给用户的那一份** ⇒ 逐字节相同"
        "（★ 打包时实测）。★ `dist/` 已 gitignore ⇒ 包本体不进受管集。",
    ]),
    (OVERVIEW, 29, "三个硬性质", [
        "| ★ 三个硬性质 | ① **可复现打包**：★ **同一批文件字节** ⇒ 两次打包 sha 相同"
        "（★ 成员时间戳固定）② **无 git 原地重建**：解包后自己重建 ⇒ **逐字节相同**"
        "（★ 打包器在包里）③ **交付态验收**：打包时自动解包复跑清单/双向自检/原仪器 "
        "⇒ **不通过就不出包**<br>★ ★ **边界（v2 实测加的）**：★ **重建 docx 会改 "
        "`dcterms:created` ⇒ 包 sha 必变**（⇒ 「重建包」可复现，**「重建 docx」不可**）｜"
        "★ **跨 zlib 实现不保证压缩字节相同**（⇒ 跨实现请用 `SHA256SUMS.txt` 做"
        "**内容级**等价核验） |",
    ]),
    (OVERVIEW, 27, "上一版包", [
        "| 被审包（v2 的对象，供参照） | sha "
        "`6afcc84454236bce57bfcdae713ceb09ae2a1cb7ac4806d8f49f39fec4fd16a0`｜2,590,134 B"
        "｜203 成员 / 202 清单 |",
        "| 更早一版（v1 的对象） | sha "
        "`7a602aa3d2af502e29a5daada0fff9f764ddb4789650f7faefa691bfdeecb341`｜2,545,302 B"
        "｜200 成员 / 199 清单 |",
        "| 本包规模（本版实测） | ★ **@@MEMBERS@@ 成员 / @@MANIFEST@@ 清单条**"
        "（★ 清单自身不入清单）｜★ md **@@MDCOUNT@@** 个 · docx **@@DOCXCOUNT@@** 个 "
        "· 非 ASCII 成员 **@@NONASCII@@** 个（★ 以 `SHA256SUMS.txt` 为准） |",
    ]),
    (OVERVIEW, 26, "待重打", [
        "| ★ 状态 | ★ **终版候选**（★ 含包级复核 v1（绑定 `7a602aa3…`）＋ v2（绑定 `6afcc844…`）"
        "＋ 本轮收口报告；★ **v2 报的 7 应修 + 4 建议已全部处置**）"
        "⇒ ★ **本 sha 的包级复核 v3 尚未出** |",
        "| ★ **本包内容锚点** | ★ **＝ `SHA256SUMS.txt` 自身的 sha256**"
        "（★ 清单覆盖其余全部成员、**自身不入清单** ⇒ **非循环** ⇒ 稳定标识整包内容集）<br>"
        "★ 第三方一行核：`sha256sum SHA256SUMS.txt`<br>"
        "★ ★ **为什么本文件不写死这个值**：★ 写死它就是**自指**"
        "（★ 改这个值 ⇒ 改本文件 ⇒ 改清单 ⇒ 改锚点）★ ⇒ ⇒ **锚点只能算，不能写死** "
        "⇒ ★ 同理，**本包自己的 sha256 与字节数也不写死在包内**（★ 那是外部事实） |",
    ]),
    (OVERVIEW, 17, "等你两句话", [
        "| **★ 等你两句话** | ① 方向①「整体组」这个**称谓**对应哪些组（详见 §4）"
        "② **要不要 push 分支**（★ 沙箱重置后仓已重建；★ 改稿过程史（旧分支 33 commits）"
        "随旧沙箱丢失且**从未推送** ⇒ **现无「未推 commit」可数**；main 未碰） |",
    ]),
    (OVERVIEW, 15, "复核", [
        "| **复核** | ★ **论文级**：独立审稿人（另拉会话，零 API、零网络、不采信我的自述）"
        "⇒ **终局裁决：通过（阻断 0）**，R-01/R-02 关闭<br>★ **包级**"
        "（★ 同一个审稿人，对**交付包本体**复核；★ **每一轮都绑定具体包 sha**）："
        "v1 绑定 `7a602aa3…` ⇒ **5/5 通过 · 0 新发现**；"
        "★ **v2 绑定 `6afcc844…` ⇒ 「有条件通过」（阻断 0 · 应修 7 · 建议 4）⇒ 11 条已全部处置** |",
    ]),
    (OVERVIEW, 14, "依据", [
        "| **依据** | 外部评审的《大修》意见（★ **原始 pasted 394 行 / 18,460 B**；"
        "★ **包内是整理版 270 行 / 18,375 B**，逐字存档）｜★ 改稿按 25 条规格执行"
        "（G1 不新增未验证数字 · G2 限定条款只增不减 · G6 回源优先） |",
    ]),
    (OVERVIEW, 4, "本文件待你审", [
        "> ★ **状态**：★ **论文级复核已通过**；★ **包级复核做了两轮** —— v1 绑定旧包 `7a602aa3…` ⇒ "
        "**5/5 通过**；★ **v2 绑定 `6afcc844…` ⇒ 裁定「有条件通过」（阻断 0 · 应修 7 · 建议 4）"
        "⇒ 11 条已全部处置**（逐条见 `papers/包级复核收口报告_2026-10-25.md`）"
        "⇒ ★ **本包是终版候选**（★ **本 sha 的包级复核 v3 尚未出**）。",
    ]),

    # ─────────────────────── 交付说明 ───────────────────────
    (NOTES, 125, "基线 commit", [
        "★ **版本**：`feature/revise-per-external-review-2026-10-24` 分支；"
        "★ **内容锚点 ＝ `sha256sum SHA256SUMS.txt`**（★ 非循环）。"
        "★ ★ **本仓是 2026-10-25 沙箱重置后重建的**"
        "（★ 旧分支 33 个 commit 的**过程史已永久丢失**，且从未推送 ⇒ `cf72f94` 那个基线 commit "
        "在 GitHub 上**也不存在** ⇒ **不可核**）⇒ ★ **能核的是内容**："
        "本包内容集合 ＝ 被审包 `6afcc844…` 的内容集合（★ 逐字节可核）。",
    ]),
    (NOTES, 109, "## 3 · 目录", [
        "## 2·ter · ★★ 包级复核第二轮（v2 · 2026-10-25）· **有条件通过 ⇒ 11 条已处置**",
        "",
        "★ v2 复核绑定包 `6afcc844…`（203 成员 / 202 清单），裁定 "
        "**有条件通过（阻断 0 · 应修 7 · 建议 4）** ⇒ ★ **不是「0 新发现」** ⇒ 处置摘要如下"
        "（★ 完整版含证据、回源与版本台账见 `papers/包级复核收口报告_2026-10-25.md`）：",
        "",
        "| # | v2 报的 | 处置 | 落点 |",
        "|:-:|---|---|---|",
        "| **R-01** | ★ **仓级：HEAD 的 `SHA256SUMS.txt` 与 HEAD 自己的文件对不上 ⇒ 新 clone 必红** | "
        "★ 重建后**重算并提交清单** ⇒ ★ 验收加一条：`git archive HEAD` 解出后 "
        "`sha256sum -c SHA256SUMS.txt` ⇒ **EXIT=0** | ★ 仓 ＋ `交付总览` §6 ⑧ |",
        "| **R-02** | ★ 过期数字：「183 个非 ASCII 成员」 | ★ 改成本包实测值，并注明「以清单为准」 | "
        "★ 本文件 L92 |",
        "| **R-03** | ★ 过期数字：「24 个 docx」 | ★ 改成本包实测总数，并补**分目录构成** | "
        "★ `交付总览` §7 |",
        "| **R-04** | ★ 口径混用：「包内 25 个 md ＋ 25 个 docx」 | ★ 改成「`papers/` 内 … ／整包 …」"
        "双口径 | ★ `交付总览` §1 |",
        "| **R-05** | ★ 指向错误对象：「《大修》意见 394 行，原文在包内」⇒ 包内那份是 270 行 | "
        "★ 改成「★ 原始 pasted 394 行；★ **包内整理版 270 行**」⇒ ★ **两份入口文档都改**"
        "（★ v2 只点了总览，★ 同一措辞在**本文件**里也有 ⇒ 按「一处错要全链复扫」一起改） | "
        "★ 本文件 L32 ＋ `交付总览` §0 |",
        "| **R-06** | ★ **同一文件内自相矛盾**：L17「32 个 commit」vs §5②「31 个 commit」 | "
        "★ 两处统一 ⇒ ★ 并写明**可核的口径**（★ 现在是：★ 过程史随沙箱丢失且从未推送 ⇒ "
        "**不可核**；★ 可核的是内容集合） | ★ `交付总览` §0 ＋ §5② |",
        "| **R-07** | ★ 悬空交叉引用（「下方『交付包身份』」小节不存在）＋ **入口文档身份缺失** | "
        "★ ① 删掉悬空指引 ② 用**非循环锚点** ＝ `sha256sum SHA256SUMS.txt` ⇒ ★ **并写明为什么"
        "不能写死值**（自指悖论） | ★ 本文件 §2·ter ＋ `交付总览` §1 |",
        "| **S-01** | ★ 工具**污染它自己检查的树**（`verify_l3_code_facts.py` 落 `__pycache__`） | "
        "★ 加 `sys.dont_write_bytecode = True` ⇒ **被检树一个字节都不动** | "
        "★ `tools/verify_l3_code_facts.py` |",
        "| **S-02** | ★ 6 个 docx 无源指纹（`support/` ×5 ＋ 底稿索引 ×1） | "
        "★ **重建并内嵌指纹**（★ 重建而不是只贴标签 ⇒ 指纹才是真的）⇒ ★ 全包 docx 指纹覆盖率 "
        "**100%** | ★ `tools/build_docx.sh`（★ 改成也接单个文件） |",
        "| **S-03** | ★ 措辞边界：「包 sha256 是稳定标识符」过读 | ★ 改成三段式"
        "（★ 入口文档 ×2 ＋ `pack_papers.py` 的打印文案） | ★ 本文件 L89 ＋ `交付总览` §1 ＋ "
        "`tools/pack_papers.py` |",
        "| **S-04** | ★ 入口文档的自我描述（终版包内还写「待重打」；「5/5 通过」没绑 sha） | "
        "★ 状态行改成绑定当前版本；★ 复核链里 v1/v2 **分行写、各自绑 sha** | ★ `交付总览` §1 ＋ §2 |",
        "",
        "★ ★ **v2 还让我发现一件我此前没意识到的事**（★ 已写进 `交付总览` §1）："
        "★ **包不能自证自己的 sha** —— ★ 写死它就是**自指**（★ 改那个值 ⇒ 改入口文档 ⇒ 改清单 ⇒ "
        "改锚点）★ ⇒ ⇒ **锚点只能算，不能写死** ⇒ ★ 唯一非循环的做法是「清单自身的 sha」"
        "（★ 清单覆盖其余全部成员、**自身不入清单**）。",
        "",
        "### ★ 复核链登记（★ 两轮各绑各的包 sha）",
        "",
        "| 轮次 | 报告文件 | sha256 | 行 / 字节 | 绑定的包 | 裁定 |",
        "|:-:|---|---|---|---|---|",
        "| v1 | `papers/包级复核报告_交付包_2026-10-25_v1.md` | `62381da63d15c5df105109b5b9b4be8"
        "31a7d998cea2419735376b304b433bdca` | 342 / 26,289 | `7a602aa3…`（200 成员 / 199 清单） | "
        "**5/5 通过 · 0 新发现** |",
        "| v2 | `papers/包级复核报告_交付包_2026-10-25.md` | `b5077789de6bb438476394634a9a2abf7"
        "8b47ef442c76a1b37678366263f40ed` | 393 / 31,819 | `6afcc844…`（203 成员 / 202 清单） | "
        "**有条件通过（阻断 0 · 应修 7 · 建议 4）** |",
        "",
        "★ **返工留痕**：★ v1 报告曾有一版「修复前」的字节（sha `397d607074e53675…`，340 行 / 26,161 B）"
        "⇒ ★ 我在审稿人修好之前就复制进仓（时间差 60 秒）⇒ ★ **审稿人当场喊停** ⇒ ★ 已换成修复版 "
        "`62381da6…` ⇒ ★ **本表即留痕处**。",
        "★ ★ **一件必须说清的**：★ ★ **审计人 v2 审的那一版 `交付说明`（比包内 `7a602aa3` 版多 29 行，"
        "含上面这张登记表与返工留痕段）随 2026-10-25 的沙箱重置丢失了** ⇒ ★ 本表是**依审计报告 "
        "§D2.1 的逐字引用重建**的（★ 审计人当时已逐条核对过那几行）⇒ ★ **重建段的字节与当时不同** ⇒ "
        "★ 按【重建】读，**不按原版读**。",
        "",
        "## 3 · 目录",
    ]),
    (NOTES, 92, "UTF-8 标志位", [
        "| **UTF-8 标志位** | ★ 本包实测 **@@NONASCII@@ 个非 ASCII 成员**（★ 以清单为准）⇒ "
        "**中央目录 + 本地头** 两处**都**带 0x800 ⇒ "
        "★ 复核人另写了独立字节解析器复验（不依赖本包检查器） |",
    ]),
    (NOTES, 89, "可复现打包", [
        "| **可复现打包** | 同一份 `build()` 连打两次 ⇒ sha256 **一致** ⇒ "
        "★ **同一批文件字节 ⇒ 同一份包 sha**（★ **边界**：★ **重建 docx 会改 "
        "`dcterms:created` ⇒ 包 sha 必变**（⇒ 可复现的是「重建包」，不是「重建 docx」）｜"
        "★ **跨 zlib 实现不保证压缩字节相同**（⇒ 跨实现请用 `SHA256SUMS.txt` 做"
        "**内容级**等价核验）｜★ 它标识的是「这一份包字节」，不是「这批内容的语义」） |",
    ]),
    (NOTES, 32, "外部审稿意见原文", [
        "| 6 | `审稿意见_外部评审_2026-10-24.md` | ★ **外部审稿意见**"
        "（★ 原始 pasted **394 行 / 18,460 B**；★ **包内是整理版 270 行 / 18,375 B**，逐字存档） |",
    ]),

    # ─────────────────────── 工具 ───────────────────────
    ("tools/build_docx.sh", 33, "交付前请跑", [
        'echo "★ 交付前请跑：python3 $(dirname "$0")/check_docx.py <交付面目录> '
        '&& python3 $(dirname "$0")/check_package.py <本包>.zip"',
    ]),
    ("tools/build_docx.sh", 9, "用法：bash build_docx.sh", [
        "# ★ 用法（2026-10-25 S-02 扩展）：",
        "#   bash build_docx.sh <目录>              ⇒ 该目录下全部 md",
        "#   bash build_docx.sh <文件1> [文件2] …   ⇒ 只处理列出的文件",
        "#   ★ 两种入口走【同一条构建路径】⇒ ★ 不会出现「目录入口修了、文件入口没修」",
        "set -euo pipefail",
        'FROM="markdown-smart+pipe_tables+raw_html"',
        "",
        'if [ "$#" -eq 0 ]; then',
        '  D="$(cd "$(dirname "$0")" && pwd)"',
        '  set -- "$D"/*.md',
        'elif [ -d "$1" ]; then',
        '  D="$1"; shift',
        '  set -- "$D"/*.md',
        "else",
        '  D="$(dirname "$1")"',
        "fi",
        "",
        "n=0; fails=0",
        'for f in "$@"; do',
    ], 7),
    ("tools/build_docx.sh", 7, "把 `smart` 关掉", [
        "#   ⇒ 下面这条命令把 `smart` 关掉（★ 实测：`markdown-smart` ＝ **关闭**；`markdown` ＝ 开启",
        "#     ⇒ 弯引号与省略号会被替换掉）⇒ **md 与 docx 逐字一致** ⇒ 「单元格零丢失」才是个真判据。",
    ]),
    ("tools/verify_l3_code_facts.py", 18, "import types", [
        "import types",
        "",
        "# ★★ S-01（2026-10-25 包级复核 v2）：★ 本脚本 import 底稿的 workflow.py ⇒ 默认会在",
        "#   【被检树】里落 `__pycache__/workflow.cpython-311.pyc` ⇒ ★ **污染它自己检查的对象**",
        "#   （★ 不污染交付包 —— 打包器已排除 `__pycache__` —— ★ 但会脏仓，且会让「从脏树重建」",
        "#     这条路径看起来不可靠）⇒ 落法：★ 关掉字节码写入（★ 被检树的字节一个都不动）",
        "sys.dont_write_bytecode = True",
    ]),
    ("tools/pack_papers.py", 231, "可复现：两次打包 sha256 一致", [
        '            print("★ ✔ 可复现：两次打包 sha256 一致（%s…）⇒ ★ **同一批文件字节 ⇒ 同一份包 sha**"',
        '                  "（★ 边界见 交付总览 §1：重建 docx 会改包 sha；跨 zlib 实现不保证压缩字节相同）"',
        '                  % a[:16])',
    ]),
    ("tools/pack_papers.py", 43, "EXTRAS =", [
        'EXTRAS = ["交付说明_四篇改稿_2026-10-24.md", "交付总览_人肉审版_2026-10-25.md",',
        '          "tools/check_package.py"]',
    ]),
    ("tools/pack_papers.py", 9, "可复现", [
        "  ④ ★ **可复现**：成员时间戳固定（1980-01-01 = ZIP 格式下限）⇒ ★ 清单文件的 mtime 不会随打包时刻漂移",
        "     ⇒ **同一批文件字节 ⇒ 同包 ⇒ 同 sha256** ⇒ ★ 包 sha256 稳定标识【这一份包字节】",
        "     （★ 边界：★ **重建 docx 会改 `dcterms:created` ⇒ 包 sha 必变**；★ **跨 zlib 实现不保证",
        "       压缩字节相同** ⇒ 跨实现请用 `SHA256SUMS.txt` 做【内容级】核验）（附带：不泄漏打包时刻）",
    ], 2),
]

COUNT_FILES = [OVERVIEW, NOTES]


def _has_block(lines, block):
    """★ 新内容块是否已【连续】出现在文件里（★ 精确的幂等判据）"""
    n = len(block)
    if n == 0:
        return False
    for i in range(len(lines) - n + 1):
        if lines[i:i + n] == block:
            return True
    return False


def apply_text(dry=False):
    """阶段一：按行号替换（★ 自下而上 ⇒ 行号不漂移）。★ 锚点对不上 ⇒ 报错退出。"""
    by_file = {}
    for item in LINE_EDITS:
        fname, lineno, anchor, new = item[:4]
        span = item[4] if len(item) > 4 else 1
        by_file.setdefault(fname, []).append((lineno, anchor, new, span))

    applied = 0
    skipped = 0
    missing = []
    for fname, edits in by_file.items():
        p = os.path.join(ROOT, fname)
        if not os.path.isfile(p):
            missing.append((fname, 0, "文件不存在", ""))
            continue
        lines = open(p, encoding="utf-8").read().split("\n")
        for lineno, anchor, new, span in sorted(edits, key=lambda e: -e[0]):
            if lineno + span - 1 > len(lines):
                missing.append((fname, lineno, "行号越界", ""))
                continue
            # ★★ 顺序很关键：★ **先判「已应用」，再判锚点** ★★
            #   ⇒ 否则当【锚点恰好出现在新内容里】时，★ 重跑会【重复应用】（★ 本轮真踩过 ⇒ 8 条被应用两次）
            if _has_block(lines, new):
                skipped += 1
                continue
            cur = lines[lineno - 1]
            if anchor not in cur:
                missing.append((fname, lineno, "★ 锚点不在该行", cur[:80]))
                continue
            lines[lineno - 1:lineno - 1 + span] = new
            applied += 1
        if not dry and not any(m[0] == fname for m in missing):
            with open(p, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
    print("★ 阶段一：已应用 %d 条 · 幂等跳过 %d 条 · 失败 %d 条" % (applied, skipped, len(missing)))
    for f, n, why, frag in missing:
        print("   ⛔ %s L%s：%s\n      %r" % (f, n, why, frag))
    if missing:
        sys.exit(1)


def apply_counts(dry=False):
    """阶段二：按【最终文件集】实测规模数，替换 @@占位符@@"""
    import hashlib
    import re
    import subprocess

    # ★ 内容集合与打包器【同源】：git ls-files（不在仓内则目录遍历）⇒ ★ 不另写一套口径
    try:
        raw = subprocess.check_output(["git", "-C", ROOT, "ls-files", "-z"])
        names = [b.decode("utf-8") for b in raw.split(b"\0") if b]
    except Exception:
        names = []
    if not names:
        for dp, dn, fn in os.walk(ROOT):
            dn[:] = [d for d in dn if d not in {".git", "dist", "__pycache__"}]
            for f in fn:
                names.append(os.path.relpath(os.path.join(dp, f), ROOT).replace(os.sep, "/"))
    names = sorted(set(n for n in names if n != "SHA256SUMS.txt"))
    members = len(names) + 1                       # + 清单自身（清单自身不入清单）
    manifest = len(names)
    md = sum(1 for n in names if n.endswith(".md"))
    docx = sum(1 for n in names if n.endswith(".docx"))
    papers_docx = sum(1 for n in names if n.startswith("papers/") and n.endswith(".docx"))
    nonascii = sum(1 for n in names if any(ord(c) > 127 for c in n))
    nonascii += 1 if any(ord(c) > 127 for c in "SHA256SUMS.txt") else 0

    vals = {
        "@@MEMBERS@@": str(members),
        "@@MANIFEST@@": str(manifest),
        "@@MDCOUNT@@": str(md),
        "@@DOCXCOUNT@@": str(docx),
        "@@PAPERSDOCX@@": str(papers_docx),
        "@@NONASCII@@": str(nonascii),
    }
    print("★ 阶段二实测：成员 %d · 清单 %d · md %d · docx %d（papers/ %d）· 非 ASCII %d"
          % (members, manifest, md, docx, papers_docx, nonascii))
    for fname in COUNT_FILES:
        p = os.path.join(ROOT, fname)
        s = open(p, encoding="utf-8").read()
        orig = s
        for k, v in vals.items():
            s = s.replace(k, v)
        if s != orig:
            if not dry:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(s)
            print("   ✔ %s 已填入规模数" % fname)
    left = []
    for fname in COUNT_FILES:
        s = open(os.path.join(ROOT, fname), encoding="utf-8").read()
        for m in re.findall(r"@@[A-Z]+@@", s):
            left.append((fname, m))
    if left:
        print("   ⛔ 仍有未填占位符：%s" % left)
        sys.exit(1)
    print("★ 阶段二：填入后 sha256 →")
    for fname in COUNT_FILES:
        h = hashlib.sha256(open(os.path.join(ROOT, fname), "rb").read()).hexdigest()
        print("   %s  %s" % (h[:16], fname))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "text"
    dry = "--dry" in sys.argv
    if mode == "text":
        apply_text(dry)
    elif mode == "counts":
        apply_counts(dry)
    elif mode == "check":
        apply_text(dry=True)
    else:
        print(__doc__)
        sys.exit(2)
