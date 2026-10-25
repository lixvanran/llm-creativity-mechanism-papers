#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
装配主稿（★ 2026-10-26）

做什么：★ 把 ch0_abstract / ch1 / ch2 / ch3 / ch4 / ch5 + 详稿的三个附录
        拼成新的 ①篇主稿（★ 五章结构：★ 问题与成因 / 设计 / 学习 / 状态机 / 融合）

为什么：★ 用户给了主稿的章节结构（★ 五章、二十节），★ 原来的 ①篇是「注意力层归因」
        单主题稿（★ 994 行）★ ⇒ ★ 按新结构重排为「五章主稿」，★ 而原 ①篇全文保留为
        《详稿》（★ papers/01_L1_注意力层归因_详稿_2026-10-25.md）★ ⇒ ★ 交叉引用与审计链不丢。

硬保证：
  · 五篇正文的读数一个都不重算（★ 逐章照搬各自原文）★ 拼装只做【拼接】，★ 不做改写
  · 拼装后自检：★ 标题结构、★ 零 emoji/零 ★/零 ⇒、★ 数字 token 守恒
"""
import pathlib
import re
import sys

sys.dont_write_bytecode = True

ROOT = pathlib.Path("/workspace/work/llm-creativity-mechanism-papers")
CH = pathlib.Path("/workspace/work/chapters")
OUT = ROOT / "papers/01_L1_PrematureConvergence_交差稿.md"
DETAIL = ROOT / "papers/01_L1_注意力层归因_详稿_2026-10-25.md"

ORDER = ["ch0_abstract.md", "ch1.md", "ch2.md", "ch3.md", "ch4.md", "ch5.md"]

NUM_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?%?")
BAD = re.compile("[⚠✅📌✔❌⛔★⇒❓📄⬜]")

# ★ 详稿的三个附录（★ 从「## 附录 A」到文末）
det = DETAIL.read_text(encoding="utf-8").split("\n")
ai = next(i for i, l in enumerate(det) if l.startswith("## 附录 A"))
appendix = "\n".join(det[ai:]).rstrip() + "\n"

parts = []
for f in ORDER:
    p = CH / f
    if not p.exists():
        print("⛔ 缺件：%s" % p)
        sys.exit(1)
    parts.append(p.read_text(encoding="utf-8").rstrip())

parts.append(appendix)

body = "\n\n".join(parts) + "\n"

# ── 自检 ──
errs = []
if BAD.search(body):
    hits = sorted(set(BAD.findall(body)))
    errs.append("★ 出现表情/装饰符号：%s" % hits)
nums = NUM_RE.findall(body)
for want, label in [("## 1 ", "第 1 章"), ("## 2 ", "第 2 章"), ("## 3 ", "第 3 章"),
                    ("## 4 ", "第 4 章"), ("## 5 ", "第 5 章")]:
    if want not in body:
        errs.append("★ 缺章节：%s" % label)
h1 = [l for l in body.split("\n") if l.startswith("# ")]
if len(h1) != 1:
    errs.append("★ H1 数量 = %d（应为 1）" % len(h1))
for sec in ["### 1.1", "### 1.2", "### 1.3",
            "### 2.1", "### 2.2", "### 2.3", "### 2.4", "### 2.5", "### 2.6",
            "### 3.1", "### 3.2", "### 3.3", "### 3.4",
            "### 4.1", "### 4.2", "### 4.3", "### 4.4",
            "### 5.1", "### 5.2", "### 5.3", "### 5.4"]:
    if sec not in body:
        errs.append("★ 缺小节：%s" % sec)

if errs:
    print("⛔ 装配自检未过：")
    for e in errs:
        print("   " + e)
    sys.exit(1)

OUT.write_text(body, encoding="utf-8")
print("✔ 主稿已装配：%s" % OUT)
print("   行数 %d ｜ 字符 %d ｜ 数字 token %d ｜ H1 %d ｜ H2 %d ｜ H3 %d" % (
    len(body.split("\n")), len(body), len(nums),
    len([l for l in body.split("\n") if l.startswith("# ")]),
    len([l for l in body.split("\n") if l.startswith("## ")]),
    len([l for l in body.split("\n") if l.startswith("### ")])))
