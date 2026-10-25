#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★ v3 独立审稿人 · 阶段二 #9「②编辑残留 5 处」逐条回源核对
======================================================================
★ 阶段二报告（papers/复核链/阶段二_独立终审报告_2026-10-25.md:133）列的 5 处：
  ① :183/184 完全重复行
  ② :959/960 重复编号
  ③ :1368 行内重复子句
  ④ :462/495/651 加粗 `**` 计数为奇数
  ⑤ :27 一处 `**` 嵌套错位
  ⑥（内容冲突）:1754 附录 D.6「"工作流无增益"…独立复现」与 :766/769
     （"没有任何一条结论有外部独立复现"）冲突
★ 行号会随改稿漂移 ⇒ ★ 本脚本按【结构特征】全量扫，不按行号。
"""
import io
import re
import sys

REPO = "/workspace/work/llm-creativity-mechanism-papers"
PAPER = REPO + "/papers/02_A_SelectionIsNotCreation_稿.md"
lines = io.open(PAPER, encoding="utf-8").read().split("\n")

print("=" * 78)
print("★ 阶段二 #9 · ②篇 编辑残留 5 处（★ 按结构特征全量扫）")
print("=" * 78)
print("稿件：%s（%d 行）" % (PAPER, len(lines)))
print()

# ① 完全重复的相邻行
dup_adj = []
for i in range(len(lines) - 1):
    a, b = lines[i].strip(), lines[i + 1].strip()
    if len(a) >= 12 and a == b:
        dup_adj.append((i + 1, a[:90]))
print("① 完全重复的相邻行：%d 处" % len(dup_adj))
for n, t in dup_adj[:10]:
    print("   ★ L%-5d %s" % (n, t))
print()

# ② 重复编号（同一列表里出现两次的编号）
num_seen = {}
dup_num = []
for i, l in enumerate(lines, 1):
    m = re.match(r"^\s*(\d+)\.\s+\S", l)
    if m:
        key = (m.group(1), l[:60])
        num_seen.setdefault(m.group(1), []).append(i)
# 只报【紧邻】同号（真正的重复编号）
for i in range(len(lines) - 1):
    a = re.match(r"^\s*(\d+)\.\s+\S", lines[i])
    b = re.match(r"^\s*(\d+)\.\s+\S", lines[i + 1])
    if a and b and a.group(1) == b.group(1):
        dup_num.append((i + 1, a.group(1), lines[i][:80]))
print("② 紧邻的重复编号：%d 处" % len(dup_num))
for n, k, t in dup_num[:10]:
    print("   ★ L%-5d 编号 %s：%s" % (n, k, t))
print()

# ③ 行内重复子句（同一行里出现两遍的长片段）
dup_clause = []
for i, l in enumerate(lines, 1):
    # 取行内最长重复的 12 字片段
    for L in (24, 16, 12):
        found = None
        for s in range(len(l) - L):
            frag = l[s:s + L]
            if l.count(frag) > 1 and re.search(r"[一-鿿]", frag):
                found = frag
                break
        if found:
            dup_clause.append((i, found, l[:80]))
            break
print("③ 行内重复子句（≥12 字片段出现两次）：%d 处" % len(dup_clause))
for n, f, t in dup_clause[:10]:
    print("   ★ L%-5d 重复片段 %r：%s" % (n, f, t))
print()

# ④ 加粗 `**` 计数为奇数
odd = []
for i, l in enumerate(lines, 1):
    if l.count("**") % 2 == 1:
        odd.append((i, l.count("**"), l[:80]))
print("④ `**` 计数为奇数的行：%d 处" % len(odd))
for n, c, t in odd[:12]:
    print("   ★ L%-5d (**×%d)：%s" % (n, c, t))
print()

# ⑤ 嵌套错位：`**` 内部又出现 `**`（连续四个以上）
nest = []
for i, l in enumerate(lines, 1):
    if "****" in l or re.search(r"\*\*[^*]{0,40}\*\*[^*]{0,40}\*\*", l):
        nest.append((i, l[:90]))
print("⑤ `**` 嵌套/连续可疑：%d 处" % len(nest))
for n, t in nest[:12]:
    print("   ★ L%-5d %s" % (n, t))
print()

# ⑥ 内容冲突：附录 D.6「独立复现」vs「没有任何一条结论有外部独立复现」
print("⑥ 内容冲突点（★『独立复现』相关句子全量列出）★")
hits = []
for i, l in enumerate(lines, 1):
    if "独立复现" in l:
        hits.append((i, l.strip()[:200]))
for n, t in hits:
    print("   L%-5d %s" % (n, t))
if not hits:
    print("   （全文无『独立复现』字样 ⇒ 冲突点已消失）")
print()

# ⑦ #3「该层未标定 ⇒ 只作方向性证据」是否在稿内
print("⑦ #3『该层未标定 ⇒ 只作方向性证据』的落点：")
n3 = 0
for i, l in enumerate(lines, 1):
    if "未标定" in l and ("方向性证据" in l or "只作方向性" in l):
        n3 += 1
        if n3 <= 4:
            print("   L%-5d %s" % (i, l.strip()[:170]))
print("   ⇒ 命中 %d 处" % n3)
print()

# ⑧ #11「批 2」标注
print("⑧ #11『批 2』标注：")
n11 = 0
for i, l in enumerate(lines, 1):
    if "批 2" in l or "批2" in l:
        n11 += 1
        if n11 <= 4:
            print("   L%-5d %s" % (i, l.strip()[:170]))
print("   ⇒ 命中 %d 处" % n11)
