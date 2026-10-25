#!/usr/bin/env python3
"""**数值答案一致性**（理科题的质量代理量，零判官、零成本）

> 落点：`creativity_lab/experiments/num_consistency.py`
>
> ## 为什么需要它
> 前面所有读数测的都是**面**（模态数 / 两两距离），**没有一个测质量**。
> 而「理科题会不会钻牛角尖」这个问题**必须**同时看质量：
> ⇒ **塌缩到 1 个模态，在有唯一解的题上可能是"对的"** ⇒ ⇒
> ⇒ 没有质量轴，就无法判断塌缩是病还是 feature。
>
> ## ★ 关键设计：**不判对错，只判一致**
> 理科题有标准答案，但：
> - 自己算的"标准答案"不可靠（⇒ 引用纪律：自算 ≠ 标准）
> - 不同支可能给不同问的答案
> ⇒ ⇒ 所以**不判谁对**，只测**「5 支对同一问给出的数值是否相同」** ⇒
> ⇒ 这是**零外部依赖**的一致性指标（不需要金标、不需要判官）。
> ⇒ ⇒ 与模态数对照 ⇒ 就能回答：**「5 支都算出同一个数」时，模态数是 1 还是 5？**
>
> ## 口径
> 1. 按 `(1)`/`(2)`/`(3)` 把每支切成**逐问片段**（题干里的问号编号）
> 2. 每片段取**最后一个**「数值+单位」对作为该问的答案（物理题惯例：结论在最后）
> 3. 一致性 = 5 支在该问上给出同一数值的支数（最大簇）
> 4. **不许当 0**：抽不出数值的片段记为 `None`，**报 n**（分母 = 能抽出的片段数）
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 数值 + 单位（物理量常见单位）；单位为空时只收带明确单位的
NUM = re.compile(r"(-?\d+(?:\.\d+)?)\s*"
                  r"(m/s\^?2|m/s|m\^?2|m|N|J|s|kJ|kg|cm|°|度|倍|%)")
# 问号编号切分
QSPLIT = re.compile(r"[（(]\s*([1-9])\s*[)）]")


def split_by_question(text: str) -> Dict[str, str]:
    """按 (1)(2)(3) 把答案切成逐问片段。"""
    marks = [(m.start(), m.group(1)) for m in QSPLIT.finditer(text or "")]
    out: Dict[str, str] = {}
    if not marks:
        return {"all": text or ""}
    for i, (pos, q) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        out[q] = text[pos:end]
    return out


def last_number(seg: str) -> Optional[str]:
    """片段里**最后**一个「数值+单位」⇒ 作为该问的答案。"""
    ms = NUM.findall(seg or "")
    if not ms:
        return None
    num, unit = ms[-1]
    # 归一化：去尾零，统一小数位
    try:
        f = float(num)
    except Exception:                                  # noqa: BLE001
        return None
    s = ("%.4f" % f).rstrip("0").rstrip(".")
    unit = unit.replace("^", "")
    return "%s%s" % (s, unit)


def consistency_of(arts: List[str]) -> Dict[str, Any]:
    """一组产出在逐问上的数值一致性。"""
    per_q: Dict[str, List[Optional[str]]] = {}
    for a in arts:
        segs = split_by_question(a)
        for q, seg in segs.items():
            per_q.setdefault(q, []).append(last_number(seg))
    out: Dict[str, Any] = {"per_q": {}, "n_arts": len(arts)}
    agree_all = []
    for q, vals in sorted(per_q.items()):
        good = [v for v in vals if v is not None]
        c = Counter(good)
        top, n = (c.most_common(1)[0] if c else (None, 0))
        out["per_q"][q] = {"n_extractable": len(good), "n_total": len(vals),
                           "modal_value": top, "n_agree": n,
                           "agreement": round(n / len(good), 4) if good else None,
                           "distinct_values": len(c)}
        if good:
            agree_all.append(n / len(good))
    out["mean_agreement"] = round(sum(agree_all) / len(agree_all), 4) if agree_all else None
    out["n_questions_with_values"] = len(agree_all)
    return out


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="runs/divergence-matrix-2x2-2026-10-24")
    a = ap.parse_args()
    run = os.path.join(ROOT, a.run)
    man_p = os.path.join(run, "manifest.json")
    if not os.path.exists(man_p):
        print("请先跑 divergence_matrix.py --topics creativity_lab/data/topics_2x2.json")
        return 1
    man = json.load(open(man_p, encoding="utf-8"))
    rows = []
    for g in man["groups"]:
        gp = os.path.join(run, "group_%s_r%d.json" % (g["tid"], g["rep"]))
        if not os.path.exists(gp):
            continue
        full = json.load(open(gp, encoding="utf-8"))
        d = g["arms"].get("base")
        if not d or not d.get("valid"):
            continue
        arts = full["arms"]["base"]["arts"]
        cons = consistency_of(arts)
        rows.append({"tid": g["tid"], "rep": g["rep"],
                     "modes": d["modes"], "effective_rank": d["effective_rank"],
                     "eff_rank_per_n": d["effective_rank_per_n"],
                     "lexical_sharing": d["lexical_sharing"],
                     "consistency": cons})
    # 汇总：按题
    tids = sorted({r["tid"] for r in rows})
    md = ["# 表N1 · 数值答案一致性 × 面宽（理科题）\n",
          "> 指标：**不判对错，只判一致**（零判官、零金标依赖）\n",
          "\n| 题 | 组 | 模态数 | 有效秩 | 词面共享度 | 可抽数值的问数 | 逐问一致率 | 一致率中位 |",
          "|---|---|--:|--:|--:|--:|---|--:|"]
    for r in sorted(rows, key=lambda x: (x["tid"], x["rep"])):
        c = r["consistency"]
        per = "；".join("(%s) %d/%d→%s" % (q, v["n_agree"], v["n_extractable"], v["modal_value"])
                        for q, v in c["per_q"].items())
        md.append("| %s | r%d | %d | %.2f | %.3f | %d | %s | %s |"
                  % (r["tid"], r["rep"], r["modes"], r["effective_rank"], r["lexical_sharing"],
                     c["n_questions_with_values"], per,
                     ("%.2f" % c["mean_agreement"]) if c["mean_agreement"] is not None else "—"))
    md.append("\n## 按题汇总\n")
    md.append("\n| 题 | 格子 | 模态数（中位） | 数值一致率（中位） | n 组 |\n|---|---|--:|--:|--:|")
    cells = {"T1": "文科·多解", "S4": "文科·唯一解",
             "T2": "理科·唯一解", "S1": "理科·唯一解", "S2": "理科·唯一解", "S3": "理科·唯一解",
             "T3": "理科·多解"}
    for tid in tids:
        rs = [r for r in rows if r["tid"] == tid]
        md.append("| %s | %s | %.1f | %s | %d |"
                  % (tid, cells.get(tid, "?"), med([r["modes"] for r in rs]),
                     ("%.2f" % med([r["consistency"]["mean_agreement"] for r in rs
                                    if r["consistency"]["mean_agreement"] is not None]))
                     if any(r["consistency"]["mean_agreement"] is not None for r in rs) else "—",
                     len(rs)))
    md.append("\n## ★ 读法\n")
    md.append("- **理科题上若「模态数 ≈ 1」同时「数值一致率 ≈ 1.0」** ⇒ ⇒ "
              "**5 支都算出了同一个数** ⇒ ⇒ **塌缩在理科题上是「大家都算对了」**，"
              "**不是钻牛角尖**。\n")
    md.append("- ⇒ 真正的「钻牛角尖」签名应是：**模态数 ≈ 1 且数值一致率低**"
              "（5 支挤在同一模态里、但答案不同）⇒ ⇒ 那才是坏的。\n")
    md.append("- ⚠️ **一致性不是正确性**：5 支一致但一致错，也算高一致 ⇒ ⇒ "
              "本表只回答「是否挤在同一个答案上」，**不回答「对不对」**。\n")
    md.append("- ⚠️ 抽不出数值的问**记 None 并报 n**，**不当 0**。\n")

    out_dir = os.path.join(ROOT, "docs", "cmp8", "routes", "COLLAPSE", "eval", "results")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "NUMCONSISTENCY-2026-10-24.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    with open(os.path.join(out_dir, "num_consistency.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print("== 数值一致性 × 面宽 ==")
    for tid in tids:
        rs = [r for r in rows if r["tid"] == tid]
        ma = [r["consistency"]["mean_agreement"] for r in rs
              if r["consistency"]["mean_agreement"] is not None]
        print("  %-3s %-10s 模态数中位 %.1f ｜ 数值一致率中位 %s"
              % (tid, cells.get(tid, "?"), med([r["modes"] for r in rs]),
                 ("%.2f" % med(ma)) if ma else "—"))
    print("\n✓ 落盘 %s" % out_dir)
    return 0


def med(v):
    v = sorted(x for x in v if x is not None)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


if __name__ == "__main__":
    raise SystemExit(main())
