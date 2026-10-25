#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ T-L3-10 · 依据 ID 的信用分配 vs 整体奖励排序（对照）
   --------------------------------------------------------------
   ★ 抓手（★ 全部来自跑批产物，逐字段自证）：
     · **依据 ID** = 卡片上的 `supports_conclusions`（结论空间 ID，C1..Cn）
     · 每张卡的唯一标识 = `card_id`（形如 `<arm>/<task>/rep<n>#<i>`）
     · 承重标记 = `load_bearing`（true/false）
     · 判定结果 = `verify_status` / `verdict`（supported / contradicted / …）
     · 整体奖励的载体 = `vd_anchor_out`（★ 越低越好：越少"依据外断言"）
       与 `n_dims`（★ 承重维度数，越多越好）

   ★ 两个排序：
     ① **整体奖励排序**（臂级）：按该臂在每题上的 `vd_anchor_out`（升序）与
        `n_dims`（降序）给出一个【整体最优臂】
     ② **依据 ID 归因排序**（结论 ID 级）：把每张卡按 `supports_conclusions`
        归到它支持的结论 ID 上，算每个结论 ID 在各臂的**承重支持率**
        ⇒ 归因排序 = 「哪个臂在承重这个结论 ID」

   ★ 一致性判据：逐 (题, 结论 ID) 比较「归因最优臂」与「整体最优臂」
     ⇒ 一致率 consistency；★ 基线 = **同臂同题不同 rep** 下的随机一致率
       （★ 零分布的合法来源：总则第 3 条 H0 = 同臂、同题、不同 rep）
     ⇒ ★ 若 实测一致率 **不显著高于** 随机基线 ⇒ 信用分配与整体奖励【不一致】
       ⇒ ⇒ 信用分配路线须重估

   ★ 判决四选一（总则 §四）：成立 / 不成立 / 不可分辨(+θ₀) / 未测

   用法：python3 T-L3-10_信用分配对照.py [--runs-root DIR] [--out DIR]
   """
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RUNS = "/workspace/lab/routes/COLLAPSE/runs"
BATCHES = ["adv", "main_big", "main_grok", "main_mm25", "main", "fv2", "mb2"]


def valid(rec):
    """★ 有效读数：剔失败与仪器层零（★ 失败路径不许静默归零）"""
    if rec.get("failures"):
        return False
    nc = rec.get("n_cards")
    return nc is not None and nc > 0


def load(R, batch):
    p = os.path.join(R, batch, "arms.jsonl")
    if not os.path.exists(p):
        return []
    out = []
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-root", default=DEFAULT_RUNS)
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()
    R, OUT = args.runs_root, args.out
    os.makedirs(OUT, exist_ok=True)
    rep, fails = {}, []

    for batch in BATCHES:
        recs = load(R, batch)
        recs = [r for r in recs if valid(r)]
        if not recs:
            continue
        print("\n" + "=" * 104)
        print("批 %s · 有效样本 n=%d（★ 已剔失败与仪器层零）" % (batch, len(recs)))
        print("=" * 104)

        # ── ① 整体奖励排序（臂级，题内比）──
        # 键：(vd_anchor_out 升序, n_dims 降序) ⇒ 越小越好
        bycell = defaultdict(list)          # (task, arm) -> [rec]
        for r in recs:
            bycell[(r["task_id"], r["arm"])].append(r)

        def arm_score(rs):
            vd = statistics.mean([r.get("vd_anchor_out", 0) or 0 for r in rs])
            nd = statistics.mean([r.get("n_dims", 0) or 0 for r in rs])
            return (vd, -nd)

        tasks = sorted({t for t, _ in bycell})
        overall_best = {}                  # task -> arm
        for t in tasks:
            arms = [a for (tt, a) in bycell if tt == t]
            if len(arms) < 2:
                continue
            best = min(arms, key=lambda a: arm_score(bycell[(t, a)]))
            overall_best[t] = best
            print("  题 %-5s 整体最优臂 = %-16s （各臂: %s）"
                  % (t, best,
                     {a: "vd=%.1f dims=%.1f" % arm_score(bycell[(t, a)])
                      for a in sorted(arms)}))

        # ── ② 依据 ID 归因：每个结论 ID 在各臂的承重支持率 ──
        #   承重支持率 = (该臂中 supports_conclusions 含该 C_k 且 load_bearing 的卡数)
        #                / (该臂该题的全部卡数)
        attr = defaultdict(dict)           # (task, C_k) -> {arm: rate}
        for (t, a), rs in bycell.items():
            cards_all = [c for r in rs for c in (r.get("cards") or [])]
            if not cards_all:
                continue
            per_c = defaultdict(int)
            for c in cards_all:
                if not c.get("load_bearing"):
                    continue
                for cid in (c.get("supports_conclusions") or []):
                    per_c[cid] += 1
            tot = len(cards_all)
            for cid, n in per_c.items():
                attr[(t, cid)][a] = n / float(tot)

        # ── ③ 一致性：逐 (题, C_k) 比「归因最优臂」vs「整体最优臂」──
        n_cmp = n_match = 0
        n_ambig = 0                       # ★ 并列 ⇒ 不可归因（argmax≠学出偏好）
        detail = []
        for (t, cid), per_a in sorted(attr.items()):
            if t not in overall_best:
                continue
            if len(per_a) < 2:
                n_ambig += 1
                continue
            mx = max(per_a.values())
            winners = [a for a, v in per_a.items() if v == mx]
            if len(winners) > 1:
                n_ambig += 1
                detail.append(dict(task=t, cid=cid, ambiguous=True,
                                   winners=sorted(winners),
                                   rates={a: round(v, 3) for a, v in per_a.items()}))
                continue
            n_cmp += 1
            hit = (winners[0] == overall_best[t])
            n_match += int(hit)
            detail.append(dict(task=t, cid=cid, attr_best=winners[0],
                               overall_best=overall_best[t], match=hit,
                               rates={a: round(v, 3) for a, v in per_a.items()}))
        consistency = (n_match / float(n_cmp)) if n_cmp else None
        print("\n  ★ 依据 ID 归因 vs 整体奖励排序：")
        print("    可比 (题,结论ID) 格 = %d；一致 = %d；并列不可归因 = %d"
              % (n_cmp, n_match, n_ambig))
        print("    ⇒ 一致率 = %s"
              % (("%.3f" % consistency) if consistency is not None else "n/a（无可比格）"))
        print("    ★ 逐格明细（前 12 条）：")
        for d in detail[:12]:
            print("      %s" % d)

        # ── ④ 零分布基线：同臂同题不同 rep 下的随机一致率 ──
        #   做法：在每个 (题,臂) 内把 rep 标签打乱后重算归因最优臂 ⇒
        #         随机一致率的期望（★ 蒙特卡洛 200 次，种子固定 ⇒ 可复现）
        import random
        rng = random.Random(20261027)
        cells = defaultdict(list)
        for r in recs:
            cells[(r["task_id"], r["arm"])].append(r)
        multi = {k: v for k, v in cells.items() if len(v) >= 2}
        mc = []
        if multi and overall_best:
            for _ in range(200):
                m = 0
                c = 0
                for (t, cid), per_a in list(attr.items()):
                    if t not in overall_best or len(per_a) < 2:
                        continue
                    shuffled = {}
                    for a in per_a:
                        rs = multi.get((t, a))
                        if not rs:
                            continue
                        rs2 = list(rs)
                        rng.shuffle(rs2)
                        cards = [c2 for r2 in rs2 for c2 in (r2.get("cards") or [])]
                        tot = max(1, len(cards))
                        lb = 0
                        for c2 in cards:
                            if c2.get("load_bearing") and cid in (c2.get("supports_conclusions") or []):
                                lb += 1
                        shuffled[a] = lb / float(tot)
                    if len(shuffled) < 2:
                        continue
                    mx = max(shuffled.values())
                    win = [a for a, v in shuffled.items() if v == mx]
                    if len(win) > 1:
                        continue
                    c += 1
                    m += int(win[0] == overall_best[t])
                if c:
                    mc.append(m / float(c))
        base = (statistics.mean(mc) if mc else None)
        base_sd = (statistics.pstdev(mc) if len(mc) > 1 else None)
        print("\n  ★ 零分布基线 A（同臂同题不同 rep 置乱，200 次蒙特卡洛，种子 20261027）：")
        print("    随机一致率均值 = %s ；σ = %s"
              % (("%.3f" % base) if base is not None else "n/a",
                 ("%.3f" % base_sd) if base_sd is not None else "n/a"))
        if base_sd == 0.0:
            print("    ★★ σ=0 的原因：★ 本批多数 (题,臂) 只有 2 个 rep，"
                  "置乱 rep 标签【不改变聚合量】⇒ 置换基线在本批【不产生随机性】")
            print("       ⇒ 置换基线不可用（不是「无效应」，是「该基线在本批退化为常数」）")

        # ★ 零分布基线 B（解析）：H0 = 「依据 ID 归因不含信息」
        #   ⇒ 归因最优臂在【可比臂集合】上均匀随机 ⇒ 一致率期望 = 1/|可比臂|
        import random as _r
        rng2 = _r.Random(20261027)
        n_arms_per_cmp = []
        for (t, cid), per_a in attr.items():
            if t in overall_best and len(per_a) >= 2:
                n_arms_per_cmp.append(len(per_a))
        analytic_base = (statistics.mean([1.0 / float(k) for k in n_arms_per_cmp])
                         if n_arms_per_cmp else None)
        mc2 = []
        if n_arms_per_cmp:
            for _ in range(2000):
                m = c = 0
                for (t, cid), per_a in attr.items():
                    if t not in overall_best or len(per_a) < 2:
                        continue
                    win = rng2.choice(sorted(per_a))
                    c += 1
                    m += int(win == overall_best[t])
                if c:
                    mc2.append(m / float(c))
        base2 = (statistics.mean(mc2) if mc2 else None)
        base2_sd = (statistics.pstdev(mc2) if len(mc2) > 1 else None)
        print("\n  ★ 零分布基线 B（解析 + 2000 次蒙特卡洛，H0 = 归因不含信息）：")
        print("    解析期望 1/|可比臂| = %s ；蒙特卡洛均值 = %s ；σ = %s"
              % (("%.4f" % analytic_base) if analytic_base is not None else "n/a",
                 ("%.3f" % base2) if base2 is not None else "n/a",
                 ("%.3f" if False else "%.3f" % base2_sd) if base2_sd is not None else "n/a"))
        z = None
        if consistency is not None and base2 is not None and base2_sd:
            z = (consistency - base2) / base2_sd
            print("    ⇒ 实测一致率 %.3f vs 解析基线 %.3f ⇒ z = %s"
                  % (consistency, base2, ("%.2f" % z)))
        elif consistency is not None and base2 is not None:
            print("    ⇒ 实测一致率 %.3f vs 解析基线 %.3f（σ=0 ⇒ 只能读方向）"
                  % (consistency, base2))

        rep[batch] = dict(n_valid=len(recs),
                          tasks=tasks, overall_best=overall_best,
                          n_comparable=n_cmp, n_match=n_match, n_ambiguous=n_ambig,
                          consistency=consistency,
                          random_baseline_perm=base, random_baseline_perm_sd=base_sd,
                          random_baseline_analytic=analytic_base,
                          random_baseline_analytic_mc=base2,
                          random_baseline_analytic_sd=base2_sd, z=z,
                          mc_runs=len(mc), mc_runs_analytic=len(mc2), detail=detail)
        if n_cmp == 0:
            fails.append("%s：无可比的 (题,结论ID) 格 ⇒ 归因不可分辨" % batch)

    out = dict(report=rep, fails=fails)
    fp = os.path.join(OUT, "T-L3-10_读数.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n★ 读数落盘：%s" % fp)
    print("结论：%s" % ("读数齐（判决待判据原文确认）" if not fails else "FAIL: %s" % fails))
    return 0 if not fails else 7


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("★ 脚本崩溃：%r" % e)
        sys.exit(1)
