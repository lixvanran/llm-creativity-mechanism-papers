#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 入口 md 的【可实测事实】自动回填（★ 2026-10-25）

★★★ 为什么必须有这个脚本：★★
  ★ 入口 md 是【人肉审版】⇒ ★ 里面的每个数字都是给读者当锚点用的
  ★ ⇒ ★ 一旦过期，★ **读者拿它去核，核不上** ⇒ ★ 整份入口 md 的可信度一起塌
  ★ ⇒ ★ **凡是可以实测出来的数字，一律不许手写**（★ sha / 行数 / 三标记计数）

★ **口径固定（★ 别改）**：
  · 行数 = `wc -l` 口径（★ 换行符个数）⇒ ★ 与 `wc -l` 一致（★ 不是 `split("\\n")`，★ 那个会多 1）
  · 两个状态标记 = 全文出现次数（★ 【待完成】 / 【待回查】）
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
lines = ENTRY.read_text(encoding="utf-8").split("\n")

def facts(rel):
    raw = (REPO / rel).read_bytes()
    txt = raw.decode("utf-8")
    return {
        "sha": hashlib.sha256(raw).hexdigest()[:16],
        "lines": raw.count(b"\n"),
        "todo": txt.count("【待完成】"),
        "pin":  txt.count("【待回查】"),
    }
F = {k: facts(v) for k, v in PAPERS}

def find(anchor):
    """★ 锚【不许带装饰前缀】（★ 2026-10-25 实测踩到）：
       去装饰那一轮把入口 md 的 "★ " 前缀剥掉了 ⇒ ★ 原来靠 "| ★ **五篇 sha256…** |"
       找行的写法【整条失效】⇒ ★ 回填静默不执行 ⇒ ★ 而复核段会报"不一致"、★ 整轮收口停住。
       ⇒ ★ 正解：★ 锚只取【不会被装饰改动的核心词】。"""
    return next((i for i, l in enumerate(lines) if anchor in l), None)

# ① 五篇 sha
i = find("五篇 sha256")
if i is not None:
    new = lines[i]
    for k, _ in PAPERS:
        new = re.sub(r"(\b%s `)[0-9a-f]{16}(`)" % re.escape(k),
                     lambda m, k=k: m.group(1) + F[k]["sha"] + m.group(2), new, count=1)
    lines[i] = new
    print("✔ 五篇 sha 已回填")

# ② 五篇正文（★ 行数）
i = find("**五篇正文**")
if i is not None:
    body = "｜".join("`%s`（%d 行）" % (k, F[k]["lines"]) for k, _ in PAPERS)
    lines[i] = "| **五篇正文** | " + body + " |"
    print("✔ 五篇行数已回填")

# ③ 三标记
i = find("**三标记")
if i is not None:
    parts = []
    for k, _ in PAPERS:
        if k == "C":
            continue      # ★ ③C 不在这三标记口径里（★ 原文也没写它）
        f = F[k]
        parts.append("%s 待完成%d/待回查%d" % (k, f["todo"], f["pin"]))
    lines[i] = "| **三标记（只增不减）** | " + "｜".join(parts) + " |"
    print("✔ 三标记计数已回填")

ENTRY.write_text("\n".join(lines), encoding="utf-8")

# ★★★ 复核段：★ 回填完必须逐个再核一遍（★ 同一个教训：★ 「已是最新」不能由 diff 为空给出）★★★
cur = ENTRY.read_text(encoding="utf-8").split("\n")
bad = []
for k, rel in PAPERS:
    m = re.search(r"\b%s `([0-9a-f]{16})`" % re.escape(k), "\n".join(cur))
    if not m or m.group(1) != F[k]["sha"]:
        bad.append(("sha", k, m.group(1) if m else None, F[k]["sha"]))
    m2 = re.search(r"`%s`（\s*(\d+)\s*行）" % re.escape(k), "\n".join(cur))
    if not m2 or int(m2.group(1)) != F[k]["lines"]:
        bad.append(("lines", k, m2.group(1) if m2 else None, F[k]["lines"]))
if bad:
    print("⛔ 回填后复核失败：")
    for x in bad: print("   ", x)
    sys.exit(1)
print("✔ 回填后逐个复核通过（★ sha 与行数 == 实测值）")
for k, rel in PAPERS:
    f = F[k]
    print("   %-3s %s  %4d 行  待完成%d/待回查%d" % (k, f["sha"], f["lines"], f["todo"], f["pin"]))
