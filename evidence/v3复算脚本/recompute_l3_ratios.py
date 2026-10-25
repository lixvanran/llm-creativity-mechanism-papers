#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★ v3 独立审稿人 · 自写复算：③篇（06_L3）§3.3 的两条比例读数
======================================================================
★ 稿内读数（06_L3:436-437 / :1045 / :1242）：
    15 题版 policy_merged.json    ｜样本 88 ｜ 其中 n_conflict_pairs=0 的 86 ｜ 97.7%
    13 题版 policy_merged13.json  ｜样本 100｜ 其中 n_conflict_pairs=0 的 98 ｜ 98.0%
  ★ 复算命令在稿内 §3.2（★ 我独立重写，不 import 生产者代码）

★ 判读纪律（★ 我的记忆里的同族教训）：
  · "n_conflict_pairs = 0 的比例" = 「奖励恒为 0 的比例」
  · 分母口径：★ 必须查【产出层】⇒ ★ 有没有【空产出 / 缺字段】混进分母
  · 报告：给剔除失败生成后的口径
"""
import json
import os
from collections import Counter

REPO = "/workspace/work/llm-creativity-mechanism-papers"
BASE = os.path.join(REPO, "来源与底稿/第三组_治塌缩层3/cmp8repo/repro/readings")


def analyse(fname, claim_n, claim_zero):
    path = os.path.join(BASE, fname)
    d = json.load(open(path, encoding="utf-8"))
    hist = d["hist"]
    meta = d.get("meta") or {}
    n = len(hist)
    zero = 0
    missing = 0
    nonzero_vals = []
    for h in hist:
        # ★ 判据：hist[] 每条样本的 n_conflict_pairs
        v = h.get("n_conflict_pairs", None) if isinstance(h, dict) else None
        if v is None:
            missing += 1
            continue
        if v == 0:
            zero += 1
        else:
            nonzero_vals.append(v)
    print("═══ %s ═══" % fname)
    print("  hist 条数        = %d   （稿内声称分母 = %d ⇒ %s）"
          % (n, claim_n, "一致 ✔" if n == claim_n else "★ 不一致 ❌"))
    print("  meta.n_samples   = %r" % meta.get("n_samples"))
    print("  n_conflict_pairs 缺失条数 = %d" % missing)
    print("  =0 的条数        = %d   （稿内声称 = %d ⇒ %s）"
          % (zero, claim_zero, "一致 ✔" if zero == claim_zero else "★ 不一致 ❌"))
    if n:
        print("  比例 = %d/%d = %.4f%%  （稿内写 97.7 / 98.0）" % (zero, n, 100.0 * zero / n))
    if nonzero_vals:
        print("  非零值的分布：%s" % Counter(nonzero_vals).most_common(8))
    else:
        print("  ★ 非零值：无 ⇒ 全部为 0")
    # 产出层体检：★ 有没有空产出 / 缺字段混进分母
    if isinstance(hist[0], dict):
        keys = Counter()
        for h in hist:
            for k, v in h.items():
                if v is None:
                    keys[k] += 1
        nz = {k: c for k, c in keys.items() if c}
        print("  ★ 产出层体检：None 值字段 %s" % (nz if nz else "无"))
        # 看有没有文本/答案为空
        for probe in ("text", "answer", "output", "resp", "content"):
            empt = sum(1 for h in hist if isinstance(h, dict) and not (h.get(probe) or "").strip()
                       if probe in h)
            if probe in (hist[0] or {}):
                print("     · %s 为空的样本数 = %d / %d" % (probe, empt, n))
    return n, zero


print("★ v3 独立复算 · ③篇（06_L3）§3.3 两条比例读数")
print("数据：%s" % BASE)
print()
r1 = analyse("policy_merged.json", 88, 86)
print()
r2 = analyse("policy_merged13.json", 100, 98)
print()
print("═══ 汇总 ═══")
ok = (r1 == (88, 86)) and (r2 == (100, 98))
print("  15 题版 86/88 = 97.7%%  → %s" % ("复算一致 ✔" if r1 == (88, 86) else "★ 不一致"))
print("  13 题版 98/100 = 98.0%% → %s" % ("复算一致 ✔" if r2 == (100, 98) else "★ 不一致"))
print("  ★ 总体：%s" % ("✅ 与稿内一致" if ok else "❌ 与稿内不一致"))
raise SystemExit(0 if ok else 1)
