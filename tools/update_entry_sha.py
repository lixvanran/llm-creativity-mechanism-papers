#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 入口 md 的五篇 sha 自动回填（★ 2026-10-25）

★★★ 为什么必须自动化：★★
  · 入口 md 里有五篇论文的 sha256 ⇒ ★ **五篇一改，它就过期**
  · ★ 人手写死 sha ⇒ ★ 必然过期 ⇒ ★ 而 sha 是**第三方核验的唯一锚点** ⇒ ★ 过期 = 核验链断
  · ⇒ ★ 落法：★ **sha 一律由脚本实测回填**，★ 人不许手写

★★★ 两个已踩过的坑（★ 都留在代码注释里，★ 别再犯）：★★
  ① **锚不能带任何固定前缀**（★ 原文只有 L1 那行有 "★ "，★ 其余四篇没有）
     ⇒ ★ 锚【标签 + 反引号 + 16 位 hex】这一种形态本身
  ② **「无改动」不能由【diff 为空】判定**（★ 那会掩盖【静默半改】）
     ⇒ ★ 必须**回填后逐个复核当前值 == 实测值**
"""
import sys, re, pathlib, hashlib
sys.dont_write_bytecode = True
REPO = pathlib.Path(__file__).resolve().parent.parent
ENTRY = REPO / "交付总览_人肉审版_2026-10-25.md"

PAPERS = [
    ("L1", "papers/01_L1_PrematureConvergence_交差稿.md"),
    ("A",  "papers/02_A_SelectionIsNotCreation_稿.md"),
    ("C",  "papers/03_C_SixWaysToLookDone_稿.md"),
    ("D",  "papers/04_D_StateMachineIsNotYetAPrompt_交差稿.md"),
    ("L3", "papers/06_L3_层3自修改_交差稿.md"),
]

def sha16(rel):
    return hashlib.sha256((REPO / rel).read_bytes()).hexdigest()[:16]

vals = {k: sha16(v) for k, v in PAPERS}
lines = ENTRY.read_text(encoding="utf-8").split("\n")
anchor = next((i for i, l in enumerate(lines) if "五篇 sha256" in l), None)
if anchor is None:
    print("⛔ 入口 md 里找不到「五篇 sha256」锚行"); sys.exit(2)

old = lines[anchor]
new = old
for k, _ in PAPERS:
    # ★★★ 【替换串不许手写结构】（★ 2026-10-25 实测踩到）：★★
    #   ★ 原写法 "%s`%s`" **自带一对反引号** ⇒ ★ 而 group(1) 已含开引号、group(2) 已含闭引号
    #   ⇒ ★ 结果 = "L1 ``sha`"（★ 多一个开引号、少一个闭引号）⇒ ★ ★ 把入口 md 改坏了
    #   ⇒ ★ 正解：★ **用 group 拼**（★ group(1) + 新值 + group(2)）⇒ ★ 不手写任何分隔符
    new = re.sub(r"(\b%s `)[0-9a-f]{16}(`)" % re.escape(k),
                 lambda m, k=k: m.group(1) + vals[k] + m.group(2), new, count=1)
if new != old:
    lines[anchor] = new
    ENTRY.write_text("\n".join(lines), encoding="utf-8")
    print("✔ 已回填五篇 sha")
else:
    print("· 五篇 sha 行内容未变（★ ★ 下面仍要逐个复核）")

# ★★★ 复核段（★ 「已是最新」必须由【逐个核当前值 == 实测值】给出）★★★
cur = ENTRY.read_text(encoding="utf-8").split("\n")[anchor]
bad = []
for k, rel in PAPERS:
    m = re.search(r"\b%s `([0-9a-f]{16})`" % re.escape(k), cur)
    got = m.group(1) if m else None
    if got != vals[k]:
        bad.append((k, got, vals[k]))
if bad:
    print("⛔ 回填后复核失败（★ ★ 这就是「静默半改」）：")
    for k, got, want in bad:
        print("   %-3s 入口 md 里=%s  实测=%s" % (k, got, want))
    sys.exit(1)
print("✔ 回填后逐个复核通过（★ 五篇 sha == 实测值）")
for k, rel in PAPERS:
    print("   %-3s %s  %s" % (k, vals[k], rel))
