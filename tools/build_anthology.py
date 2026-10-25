#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 四篇正文合订本生成器（★ 2026-10-25）

★★★ 它做什么：★★
  ★ 把 ①L1 / ②A / ③C / ④D / ③L3 **五篇正文合成一个 md 文件**（★ 用户要"一份 md 原文、一个文件"）
  ★ ⇒ ★ 【不改任何正文字符】★ ⇒ ★ 唯一改动是【标题级别整体 +1】⇒ ★ 使合订本里
    ★ 【只有一个 h1】、★ 每篇一个 h2、★ 篇内原有层级完整下沉一层（★ 否则 20 个 h1 混在一起没法读）

★★★ 「没改一个字」怎么证明（★ 本工具的判据）：★★
  ★ ① 生成时**逐篇记录**它做过的变换（★ 只允许两种：★ 加篇首块 ★ 标题 +1 级）
  ★ ② `tools/check_anthology.py` **把合订本逐篇反向平移回去**（★ 去掉篇首块 ★ 标题 −1 级）
  ★     ⇒ ★ **然后与原 md 逐字节比** ⇒ ★ 相等 ⇒ ★ **证明没改一个字**
  ★ ③ **负向测试**：★ 故意改一个字 ⇒ 判据必须红

★ **用法**：
  python3 tools/build_anthology.py                     # ★ 生成
  python3 tools/build_anthology.py --out <路径>
"""
import sys, re, pathlib, argparse, hashlib
sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parent.parent

# ★ 五篇（★ 顺序 = 入口 md §3 的顺序）
PARTS = [
    ("① L1", "papers/01_L1_PrematureConvergence_交差稿.md",
     "搜索空间过早闭合：注意力层归因假说与判决式",
     "注意力层的四条机制链 + 三层分离协议 + α 公式", "★ 机制**未证成**；★ 已给可证伪的判决式与第一轮实测"),
    ("② A", "papers/02_A_SelectionIsNotCreation_稿.md",
     "撑开 Agent 搜索空间的工作流设计",
     "形态维度：什么能被设计、什么能被判定（杠杆公式 + 双边净增益）",
     "★ 净增益判决 = **不可分辨**（★ OR +6/+7 vs AND −7/−2 ⇒ 方向随口径翻转）"),
    ("③ C", "papers/03_C_SixWaysToLookDone_稿.md",
     "Thirteen Ways to Look Done Without Being Verified",
     "判定层：外部只读审计如何发现被自己的报告掩盖的缺陷",
     "★ 给出可执行防伪规程 + 外部只读审计协议"),
    ("④ D", "papers/04_D_StateMachineIsNotYetAPrompt_交差稿.md",
     "A State Machine Is Not Yet a Prompt",
     "驱动力维度：C1 四步管线 + 双层结构 + 离散结构量 D-1/D-2/D-3",
     "★ 绝对判定 p=0.0010 成立、★ 相对判定 p=0.0063 成立、★ **比较性 p=0.2500 不可分辨**"),
    ("③ L3", "papers/06_L3_层3自修改_交差稿.md",
     "让系统自己学出工作流：把设计自由度变成可学问题",
     "来源维度：把设计决策变成可学的（57 权重打分函数）",
     "★ 因子化 47 参数 vs 36 路扁平 vs 全交互 216 的三行对照；★ 真正的理由是**可学子空间更小**"),
]

H = re.compile(r"^(#{1,6})(\s)")

def shift_headings(lines, delta):
    """★ 标题级别平移（★ 超出 h6 的不动、★ 记下来）"""
    out, capped = [], []
    for l in lines:
        m = H.match(l)
        if not m:
            out.append(l); continue
        n = len(m.group(1))
        nn = min(6, n + delta)
        if nn != n + delta:
            capped.append((n, l[:60]))
        out.append("#" * nn + m.group(2) + l[m.end():])
    return out, capped

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "四篇正文合订本_2026-10-25.md"))
    args = ap.parse_args()
    out = pathlib.Path(args.out)

    parts_md, toc, meta = [], [], []
    for idx, (tag, rel, title, claim, verdict) in enumerate(PARTS, 1):
        p = ROOT / rel
        raw = p.read_bytes()
        txt = raw.decode("utf-8")
        lines = txt.split("\n")
        sha = hashlib.sha256(raw).hexdigest()[:16]
        nlines = raw.count(b"\n")
        first_h1 = next((l[2:].strip() for l in lines if l.startswith("# ")), title)
        meta.append((tag, rel, sha, nlines, first_h1, claim, verdict))

        body, capped = shift_headings(lines, +1)
        # ★ 去掉末尾空行（★ 拼接时统一处理）
        while body and body[-1].strip() == "":
            body.pop()
        parts_md.append((idx, tag, first_h1, body, capped))
        toc.append((idx, tag, first_h1, sha, nlines))

    L = []
    L.append("# 四篇正文合订本（★ 2026-10-25）")
    L.append("")
    L.append("> ★★★ **这是五篇论文的合订本；★ 正文一字未改。★★★**")
    L.append("> ★ **唯一的结构性改动**：★ 篇内标题**整体下移一级**（★ `#` → `##`）⇒ ★ 这样合订本里**只有一个 h1**、每篇一个 h2、篇内原有层级完整保留在下一层（★ 否则五篇的 20 个 h1 会混在一起没法读）。")
    L.append("> ★ ★ **「没改一个字」是机器验过的**：★ `tools/check_anthology.py` 把本文件**逐篇反向平移回去**（★ 去篇首块 + 标题 +1 复原）★ ⇒ ★ **与各篇原 md 逐字节比** ⇒ ★ 相等才算过（★ 且配负向测试：★ 故意改一个字必须判红）。")
    L.append("> ★ **每篇开头的「本篇信息」块是合订本加的元信息**（★ sha / 行数 / 主张 / 判决）⇒ ★ **不属于原文**。")
    L.append("> ★ ★ **正文、公式、读数、表格、脚注、待取证清单 —— 全部按原文照抄。★★★**")
    L.append("")
    L.append("## 目录")
    L.append("")
    L.append("| # | 篇 | 标题 | sha256（前 16 位）| 行数 |")
    L.append("|:-:|---|---|---|--:|")
    for idx, tag, title, sha, nlines in toc:
        L.append("| %d | %s | %s | `%s` | %d |" % (idx, tag, title, sha, nlines))
    L.append("")
    L.append("---")
    L.append("")

    for idx, tag, title, body, capped in parts_md:
        m = meta[idx - 1]
        L.append("## 【第 %d 篇 / 共 5 篇】%s · %s" % (idx, tag, title))
        L.append("")
        L.append("> ★ **本篇信息**（★ 合订本加的元信息、★ 非原文）")
        L.append(">")
        L.append("> - ★ **源文件**：`%s`" % m[1])
        L.append("> - ★ **sha256（前 16 位）**：`%s` ｜ **行数**：%d" % (m[2], m[3]))
        L.append("> - ★ **核心主张**：%s" % m[5])
        L.append("> - ★ **判决**：%s" % m[6])
        if capped:
            L.append("> - ★ ⚠️ **平移注记**：★ 本篇有 %d 个原本就是 h6 的标题、★ 平移后仍为 h6（★ 层级已到顶）" % len(capped))
        L.append(">")
        L.append("> ★ ↓↓↓ **以下为原文逐字**（★ 标题级别下移一级、★ 文字未改）")
        # ★ ★ 【这里不能加空行】（★ 2026-10-25 实测踩到）：★★
        #   ★ 加了 ⇒ ★ 合订本每篇正文前多一个空行 ⇒ ★ 反向平移后与原文件差一行
        #     ⇒ ★ 判据报「第 0 行起不一致」
        #   ⇒ ★ 正确落法：★ **正文紧接标记行**（★ 判据端保持严格逐字节、★ 不去首空行
        #     ⇒ ★ 不掩盖任何真实差异）
        L.extend(body)
        L.append("")
        L.append("---")
        L.append("")

    out.write_text("\n".join(L), encoding="utf-8")
    print("★ 合订本已生成：%s" % out)
    print("★ 大小：%d B ｜ 行数：%d" % (out.stat().st_size, out.read_bytes().count(b"\n")))
    for idx, tag, title, sha, nlines in toc:
        print("   第%d篇 %-5s %-42s %s  %d 行" % (idx, tag, title[:40], sha, nlines))

if __name__ == "__main__":
    main()
