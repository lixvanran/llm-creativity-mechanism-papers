#!/usr/bin/env python3
"""★ **嵌套子集校准**：「加支数让面变宽」是真实效应，还是采样量增加的机械产物？

> 落点：`creativity_lab/experiments/nested_calibration.py`
> 2026-10-24 ｜ 第二组 · 层2
> 触发：外部问卷 Q1.4 的嵌套陷阱提醒 ——
>   「比较 5 支与 8 支时，8 支是否包含原来那 5 支？加入分支后是否重新聚类？
>   如果 8 支包含原来 5 支，那么"模态数 4→7"可能**只是采样量增加的机械效应**
>   （点更多 ⇒ 聚类更容易多出簇），不是真实的路径变宽。」
>
> ## ★ 为什么必须做（★ 这条质疑是对的）
> **模态数**（余弦阈值连通分量）与 **Vendi** 都是"分块数/有效块数"的量
> ⇒ ⇒ **在固定分布下，样本点越多 ⇒ 越容易偶然分裂出更多块** ⇒ ⇒
> **"8 支的模态数比 5 支多" 可能纯机械**，与"路径真的变宽"无关。
> ⇒ ⇒ 昨晚结论 2.10「加支数有效」**必须过这一关**。
>
> ## ★ 校准方法（★ 零成本、零新调用：数据全在 `runs/*/group_*.json` 里）
> **嵌套子集法**：对每个 `n8` 组（8 支原文都在），
>   ① 把它**随机抽成 5 支子集**，重复 K 次（K=200）
>   ② 得到"**同样这 8 支的分布**下，5 支时面宽的典型值" = **机械基线**
>   ③ 与 8 支全集的读数比
> ⇒ ⇒ **判据**：
>   - 若「8 支实测」显著高于「5 支嵌套子集中位」 ⇒ **有超出机械的效应**
>   - 若二者落在同一区间 ⇒ **纯机械 ⇒ 昨晚结论作废**
> ⇒ ⇒ ★★ 这正是我 `metrics_ext.n_baseline()` 的思路，
>   但**必须用真实分支做**（随机向量的基线只回答"一般情况下会怎样"，不回答"这批数据会怎样"）
>
> ## ★ 顺带回答 Q1.4 的另一半
> - **8 支是否包含原来那 5 支？** ★ **不包含** —— `n8` 臂是**独立生成 8 支**（`_branch_specs` 前 8 个槽位），
#   与 `base` 臂（5 支）**不是嵌套关系** ⇒ ⇒ 所以"包含"这一条陷阱不成立
#   ⇒ ★ **但"采样量增加的机械效应"这一条陷阱成立** ⇒ ⇒ 本脚本就是校准它
# - **加入分支后是否重新聚类？** ★ **是**（每次都从全量向量重新算连通分量）⇒ ⇒ 所以更可能出簇
"""
import json
import os
import random
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from creativity_lab.client import LLM                      # noqa: E402
from creativity_lab.metrics import effective_rank, modes   # noqa: E402
from creativity_lab.metrics_ext import self_bleu, vendi_score  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNS = [
    ("divergence-matrix-2026-10-24", "第六轮 T1-T3"),
    ("divergence-pathmulti-2026-10-24", "第七轮 S4-S6"),
    ("divergence-matrix-B2-2026-10-24", "第六轮复现批"),
]
K = 200          # 每个组的嵌套抽样子集次数
SEED = 20261024


def med(v):
    v = sorted(x for x in v if x is not None)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def pct(v, q):
    v = sorted(x for x in v if x is not None)
    if not v:
        return None
    i = min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))
    return v[i]


def main() -> int:
    emb = LLM()
    rows: List[Dict[str, Any]] = []
    for run, label in RUNS:
        d = os.path.join(ROOT, "runs", run)
        if not os.path.exists(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.startswith("group_"):
                continue
            g = json.load(open(os.path.join(d, fn), encoding="utf-8"))
            arms = g.get("arms") or {}
            n8 = arms.get("n8")
            base = arms.get("base")
            if not n8 or not base:
                continue
            arts8 = n8.get("arts") or []
            if len(arts8) < 8:
                continue
            rng = random.Random(SEED + g.get("rep", 0))
            sub_modes, sub_vendi, sub_er, sub_sb = [], [], [], []
            for _ in range(K):
                idx = rng.sample(range(len(arts8)), 5)
                sub = [arts8[i] for i in idx]
                vec = emb.embed(list(sub))
                sub_modes.append(modes(vec))
                sub_vendi.append(vendi_score(vec))
                sub_er.append(effective_rank(vec))
                sub_sb.append(self_bleu(sub))
            vec8 = emb.embed(list(arts8))
            rows.append({
                "run": run, "label": label, "tid": g.get("tid"), "rep": g.get("rep"),
                "modes8": modes(vec8), "vendi8": round(vendi_score(vec8), 4),
                "er8": round(effective_rank(vec8), 4), "sb8": round(self_bleu(arts8), 4),
                "sub_modes_med": med(sub_modes), "sub_modes_p90": pct(sub_modes, 0.90),
                "sub_vendi_med": round(med(sub_vendi), 4), "sub_vendi_p90": round(pct(sub_vendi, 0.90), 4),
                "sub_er_med": round(med(sub_er), 4), "sub_sb_med": round(med(sub_sb), 4),
                "base_modes": (base.get("read") or {}).get("modes") or base.get("modes"),
                "base_vendi": (base.get("read") or {}).get("vendi"),
            })

    if not rows:
        print("✘ 没有可校准的 n8 组")
        return 1

    print("★ 嵌套校准：从每组的 8 支里随机抽 5 支（K=%d 次）⇒ 机械基线\n" % K)
    print("| 批次 | 题 | 组 | 模态: 8支实测 | 5支嵌套中位 | 5支嵌套p90 | 超机械? | Vendi: 8支 | 5支中位 | 超机械? |")
    print("|---|---|---|--:|--:|--:|:--:|--:|--:|:--:|")
    for r in rows:
        sm = r["sub_modes_med"]
        over_m = "★是" if (r["modes8"] or 0) > (r["sub_modes_p90"] or 0) else "否"
        over_v = "★是" if (r["vendi8"] or 0) > (r["sub_vendi_p90"] or 0) else "否"
        print("| %s | %s | r%s | %s | %.1f | %.1f | %s | %.2f | %.2f | %s |"
              % (r["label"], r["tid"], r["rep"], r["modes8"], sm, r["sub_modes_p90"], over_m,
                 r["vendi8"], r["sub_vendi_med"], over_v))

    print()
    for key, name, thr in (("modes8", "模态数", 0.5), ("vendi8", "Vendi", 0.3)):
        over = 0
        tot = 0
        for r in rows:
            base = r["sub_modes_p90"] if key == "modes8" else r["sub_vendi_p90"]
            tot += 1
            if (r[key] or 0) > (base or 0):
                over += 1
        print("★ %s：8 支实测 **超过** 5 支嵌套子集 p90 的组次 = **%d / %d**" % (name, over, tot))
    print()
    print("★★ 读法：")
    print("   · 若「超过 p90」的组次接近 0 ⇒ **8 支的面宽是采样量增加的机械产物**")
    print("     ⇒ ⇒ **昨晚结论 2.10「加支数有效」在「模态数」口径上不成立**")
    print("   · 若接近全部 ⇒ 有超出机械的效应 ⇒ 结论保留")
    print()
    print("★ 另注（回答 Q1.4 的另一半）：`n8` 臂是**独立生成 8 支**，与 `base`（5 支）**不是嵌套**")
    print("   ⇒ 「8 支包含原来 5 支」这条陷阱**不成立**；但「采样量增加 ⇒ 聚类易多出簇」**成立** ⇒ 本脚本校准它。")
    out = os.path.join(ROOT, "runs", "nested-calibration-2026-10-24")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "nested_calibration.json"), "w", encoding="utf-8") as f:
        json.dump({"K": K, "seed": SEED, "rows": rows}, f, ensure_ascii=False, indent=1)
    print("✔ 落盘：%s" % os.path.join(out, "nested_calibration.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
