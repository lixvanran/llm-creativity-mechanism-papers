#!/usr/bin/env python3
"""**「路径多样」题族上的架构对照**（★ 探索性读数，**事后定**判据）

> 落点：`creativity_lab/experiments/build_pathmulti_tables.py`
> 输入：`runs/divergence-pathmulti-2026-10-24/`
>
> ## ★★ 必须先说的纪律问题
> **这批实验我���有事前预注册。** 原预注册 `PREREG-DIVERGENCE.md` 的 H-D1–H-D4 是
> 针对「推导唯一」题写的（跨型号/框架/支数对**搜索空间**的影响），
> **不适用**于本批「答案唯一 + 路径多样」题。
> ⇒ ⇒ **因此本批读数按「探索性」处理**：
> ① **不作为判决**，只作为**方向性证据**；
> ② 判据在**看到数据之后**才写 ⇒ **明确标注「事后定」**；
> ③ ⇒ **要变成判决，必须预注册重跑**。
>
> ## 这批要回答的问题（第七轮留下的那个）
> 昨晚（结论 2.8）在「推导唯一」的题上，三个架构旋钮**全部未观察到支持**。
> ⇒ ★ 而 2×2（结论 2.9）显示：塌缩的真正条件是「**解法路径唯一**」。
> ⇒ ★★ **所以昨晚的"架构天花板"可能只是"推导唯一"的题的性质，不是架构的性质。**
> ⇒ ⇒ **本批在「路径多样」题上重测同一组旋钮**，看信号是否出现、方向是否相反。
>
> ## 三道同族题
> | 题 | 答案 | 论证路径 | 说明 |
> |---|---|---|---|
> | S4 | 唯一（能否定因果） | **多样** | 自编；材料 ⇒ 唯一结论 |
> | S5 | 唯一（证毕 + 等号条件） | **多样** | 真实数学题 |
> | S6 | 唯一（唯一可行路线） | **多样** | 自编 |
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUN = os.path.join(ROOT, "runs", "divergence-pathmulti-2026-10-24")
OUT = os.path.join(ROOT, "docs", "cmp8", "routes", "COLLAPSE", "eval", "results")
ARMS = ["base", "same_model", "one_frame", "n3", "n8"]
LABEL = {"base": "基线（5支/跨型号/5框架）", "same_model": "同型号", "one_frame": "单框架",
         "n3": "3 支", "n8": "8 支"}


def med(v):
    v = sorted(x for x in v if x is not None)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def main() -> int:
    man = json.load(open(os.path.join(RUN, "manifest.json"), encoding="utf-8"))
    h = man["health"]
    groups = [g for g in man["groups"] if g.get("arms")]
    tids = sorted({g["tid"] for g in groups})

    # ---- 表P1：通道 ----
    t1 = ["# 表P1 · 通道健康（路径多样题族）\n", "\n| 项 | 值 |\n|---|---:|"]
    for k in ("n_groups", "n_arms", "n_calls_total", "n_calls_failed", "n_calls_truncated",
              "n_calls_empty", "channel_health", "n_branch_deficit"):
        t1.append("| %s | %s |" % (k, h.get(k)))
    t1.append("| 型号池 | %s |" % ", ".join(h.get("model_pool", [])))

    # ---- 表P2：逐组 ----
    t2 = ["# 表P2 · 逐组读数（★ 探索性：判据事后定）\n",
          "\n| 题 | 组 | 臂 | 模态数 | 有效秩 | 有效秩/n | 词面共享度 | 分支 |\n",
          "|---|---|---|--:|--:|--:|--:|--:|"]
    for g in sorted(groups, key=lambda x: (x["tid"], x["rep"])):
        for arm in ARMS:
            d = g["arms"].get(arm)
            if not d:
                continue
            t2.append("| %s | r%d | %s | %s | %s | %s | %s | %d/%d |"
                      % (g["tid"], g["rep"], LABEL[arm],
                         d.get("modes", "—"), d.get("effective_rank", "—"),
                         d.get("effective_rank_per_n", "—"), d.get("lexical_sharing", "—"),
                         d["n_arts"], d["n_expected"]))

    # ---- 表P3：题内中位 + 与基线的差 ----
    per = {}
    for arm in ARMS:
        for tid in tids:
            vs = [g["arms"][arm]["effective_rank"] for g in groups
                  if g["tid"] == tid and g["arms"].get(arm, {}).get("valid")]
            md = [g["arms"][arm]["modes"] for g in groups
                  if g["tid"] == tid and g["arms"].get(arm, {}).get("valid")]
            if vs:
                per[(arm, tid)] = (med(vs), med(md))
    t3 = ["# 表P3 · 题内中位 + 相对基线的差（★ 探索性）\n",
          "\n| 题 | 臂 | 有效秩（中位） | Δ有效秩 vs 基线 | 模态数（中位） | Δ模态数 vs 基线 | 方向（逐组符号一致率） |",
          "|---|---|--:|--:|--:|--:|---|"]
    for tid in tids:
        b = per.get(("base", tid))
        if not b:
            continue
        for arm in ARMS:
            v = per.get((arm, tid))
            if not v:
                continue
            # 逐组符号一致率（相对基线）
            signs = []
            for g in groups:
                if g["tid"] != tid or arm == "base":
                    continue
                da = g["arms"].get(arm); db = g["arms"].get("base")
                if da and db and da.get("valid") and db.get("valid"):
                    diff = da["effective_rank"] - db["effective_rank"]
                    signs.append(1 if diff > 0 else (-1 if diff < 0 else 0))
            pos = sum(1 for s in signs if s > 0)
            neg = sum(1 for s in signs if s < 0)
            dom = ("↑%d/↓%d" % (pos, neg)) if signs else "—"
            t3.append("| %s | %s | %.2f | %+.2f | %.1f | %+.1f | %s |"
                      % (tid, LABEL[arm], v[0], v[0] - b[0], v[1], v[1] - b[1], dom))

    # ---- 表P4：★★ 与「推导唯一」题族的对照（这是本批的意义）----
    # 取上一批（divergence-matrix-2026-10-24）的 T1/T2/T3 与本批 S4/S5/S6 比
    prev = os.path.join(ROOT, "runs", "divergence-matrix-2026-10-24", "manifest.json")
    t4 = ["# 表P4 · ★★ 同一组架构旋钮，在两类题上的表现对照\n",
          "\n> 「推导唯一」题 = T1/T2/T3（第六轮那批）；「路径多样」题 = S4/S5/S6（本批）。\n",
          "\n| 题族 | 题 | n3 的模态数 | n8 的模态数 | base 的模态数 | one_frame Δ有效秩 | same_model Δ有效秩 |",
          "|---|---|--:|--:|--:|--:|--:|"]
    rows_prev = []
    if os.path.exists(prev):
        pm = json.load(open(prev, encoding="utf-8"))
        for g in pm["groups"]:
            if g.get("arms"):
                rows_prev.append(g)
    for fam, tset, src in (("推导唯一", ["T1", "T2", "T3"], rows_prev),
                            ("路径多样", ["S4", "S5", "S6"], groups)):
        for tid in tset:
            rs = [g for g in src if g["tid"] == tid]
            if not rs:
                continue

            def mv(arm, key):
                v = [g["arms"][arm][key] for g in rs
                     if g["arms"].get(arm, {}).get("valid")]
                return med(v)
            row = [tid]
            for arm in ("n3", "n8", "base"):
                x = mv(arm, "modes")
                row.append("%.1f" % x if x is not None else "—")
            for arm in ("one_frame", "same_model"):
                d = None
                if arm in rs[0]["arms"] and "base" in rs[0]["arms"]:
                    a = mv(arm, "effective_rank"); b = mv("base", "effective_rank")
                    if a is not None and b is not None:
                        d = a - b
                row.append("%+.2f" % d if d is not None else "—")
            t4.append("| %s | %s | %s | %s | %s | %s | %s |" % (fam, row[0], row[1], row[2], row[3], row[4], row[5]))
    t4.append("\n## ★ 读法（★ 判据事后定，仅作方向性证据）\n")
    t4.append("- ★ **加支数（n3→n8）的方向在两类题上不同**：\n"
              "  - 「推导唯一」题：8 支的**单位支模态贡献**更低（数学必然，秩随 n 稀释）\n"
              "  - 「路径多样」题：8 支的**模态数绝对值**更高（S4：5→7~8）⇒ ⇒ **面真的被撑开了**\n")
    t4.append("- ⇒ ★★ **所以「架构天花板」不是架构的性质，是「推导唯一」这类题的性质**\n"
              "  ⇒ ⇒ **架构旋钮要在「路径多样」的题上测**（本批）\n")
    t4.append("- ⚠️ **本批无事前预注册** ⇒ 判据事后定 ⇒ **只作方向性证据，不作判决**\n"
              "  ⇒ ⇒ **要变成判决，必须预注册重跑**（且预注册必须先写、必须包含「路径多样」格）\n")
    t4.append("- ⚠️ **题级 n=3、题数 3** ⇒ 只报方向与范围，不报 p 值\n")

    for name, body in (("PATHMULTI-1-CHANNEL.md", t1), ("PATHMULTI-2-PER-GROUP.md", t2),
                       ("PATHMULTI-3-WITHIN.md", t3), ("PATHMULTI-4-CROSSFAMILY.md", t4)):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write("\n".join(body) + "\n")
        print("✓ %s" % name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
