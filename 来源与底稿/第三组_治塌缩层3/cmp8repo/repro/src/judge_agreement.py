# -*- coding: utf-8 -*-
"""三个判官在**同一批答案**上的读数对照 —— "我们的读数可信吗"的直接答案

> 2026-10-23 ｜ 配套论文 §6.5(f) / §6.6

## 为什么必须"同一批答案"
三份 δ 测量（`delta_judge_minimax` / `_openrouter` / `_mm25`）用的是 **runs/main/arms.jsonl
里的同一批答案** ⇒ 只有这样，判官之间的差异才**只**来自判官本身。
（各批次自己生成的答案不能直接比 —— 生成侧 temp=0.7 不确定。）

## 输出
1. 逐 (题,臂,rep) × 判官 的读数矩阵
2. **判官内**波动（δ_judge，逐份极差）
3. **判官间**波动（同答案、不同判官，逐份极差）⇒ **"读数在判官之间就不稳"** 与
   "读数在判官内部就不稳" 是**两件不同的事**
4. 三判官**多数一致率**（同一份答案，三个判官的读数是否落在同一档）
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

JUDGES = [
    ("MiniMax-M3.1-Flash(thinking)", "runs/main/delta_judge_minimax.jsonl"),
    ("MiniMax-M2.5(non-thinking)", "runs/main/delta_judge_mm25.json.jsonl"),
    ("grok-4.3", "runs/main/delta_judge_openrouter.json.jsonl"),
]


def load(path):
    if not os.path.exists(path):
        return {}
    out = {}
    for ln in open(path, encoding="utf-8"):
        try:
            d = json.loads(ln)
        except Exception:
            continue
        m = d.get("meas") or {}
        out.setdefault((d.get("task_id"), d.get("arm"), d.get("rep")), []).append(
            (d.get("judge_rep"), m.get("n_dims"), m.get("n_load_bearing"),
             m.get("n_cards")))
    return out


def main():
    data = {name: load(p) for name, p in JUDGES}
    data = {k: v for k, v in data.items() if v}
    if not data:
        print("没有可用的 δ 数据")
        return 1

    print("=" * 100)
    print("三个判官 · 同一批答案 · temp=0 · 每份重复判定")
    print("=" * 100)
    keys = sorted(set().union(*[set(v.keys()) for v in data.values()]))
    names = list(data.keys())

    print("\n【1】读数矩阵（每格＝该判官对该答案的逐次读数）")
    hdr = "%-20s %-13s %-4s" % ("题", "臂", "rep")
    for n in names:
        hdr += " | %-26s" % n
    print(hdr)
    within = defaultdict(list)
    across = defaultdict(list)
    for k in keys:
        line = "%-20s %-13s %-4s" % (k[0], k[1], k[2])
        meds = []
        for n in names:
            rs = sorted(data[n].get(k, []))
            if not rs:
                line += " | %-26s" % "—"
                continue
            vals = [r[1] for r in rs if r[1] is not None]
            within[n].append((max(vals) - min(vals)) if vals else 0)
            meds.append(statistics.median(vals) if vals else None)
            line += " | %-26s" % ("%s (波%d)" % (vals, max(vals) - min(vals)))
        got = [m for m in meds if m is not None]
        if len(got) >= 2:
            across["spread"].append(max(got) - min(got))
            across["same"].append(1 if len(set(got)) == 1 else 0)
        print(line)

    print("\n【2】判官内波动（δ_judge：同答案、同判官、重复判定）")
    for n in names:
        ws = within[n]
        if not ws:
            continue
        print("  %-30s n=%-3d 中位波动=%.1f  最大=%d  读数全同的份=%d/%d"
              % (n, len(ws), statistics.median(ws), max(ws),
                 sum(1 for x in ws if x == 0), len(ws)))

    print("\n【3】判官间波动（同答案、不同判官）")
    sp = across.get("spread", [])
    same = across.get("same", [])
    if sp:
        print("  n=%d  逐份极差：中位=%.1f 最大=%d  三判官读数全同的份=%d/%d (%.0f%%)"
              % (len(sp), statistics.median(sp), max(sp), sum(same), len(same),
                 100.0 * sum(same) / len(same)))
        print("  ⇒ ★ 读数在**判官之间**就不稳 ⇒ 架构级结论必须以「跨判官一致」为前提")
    else:
        print("  （配对不足）")

    print("\n" + "=" * 100)
    print("★ 判读：若「判官内波动」远小于「判官间波动」⇒ 噪声主要来自**判官个体**"
          "（⇒ 换判官即可）；")
    print("  若两者同量级 ⇒ 读数整体不可信，只能报告方向性结论。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
