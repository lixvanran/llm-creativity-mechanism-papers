#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ T-L3-08 · 批 2 四支的承重子层非零比例 + 本批零分布标定
   --------------------------------------------------------------
   ★ 读数口径（★ 逐字段自证，不采信任何转述）：
     · 承重子层指标 = `n_load_bearing`（承重子层里真正被用上的断言数）
     · 分母 = **有效读数**（★ 剔三种缺失分形：失败 / 仪器层零 / 内容层空）
         - 失败生成：`failures` 非空 或 `n_cards` 为 None
         - 仪器层零：`n_cards == 0`（判官没产出卡片 ⇒ 不是内容层空，是仪器坏了）
         - 内容层空：`n_cards > 0` 但 `n_load_bearing == 0`（★ 这是【真零】，要进分母）
     · 零分布（★ 总则第 3 条：H0 的唯一合法来源 = 同臂、同题、不同 rep）
       ⇒ θ₀ 用【同臂同题不同 rep】的 σ 为单位，锚在本批自己的噪声地板

   ★ 数据源：`/workspace/lab/routes/COLLAPSE/runs/<批>/arms.jsonl`
   用法：python3 T-L3-08_承重子层与零分布.py [--runs-root DIR] [--out DIR]
   """
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RUNS = "/workspace/lab/routes/COLLAPSE/runs"
BATCHES = ["adv", "main_big", "main_grok", "main_mm25", "main", "fv2", "mb2"]
FOUR = ["B0_bestof3", "B0_direct", "W_design_L2", "W_train_L3"]



def wilson(k, n, z=1.96):
    """★ Wilson 95% 区间（★ 比例型读数的检出力地板；★ 不用正态近似，
       因为 n 小且 p 接近 0.5 时正态近似会给出越界区间）"""
    if n == 0:
        return (None, None)
    ph = k / float(n)
    d = 1.0 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def classify(rec):
    """★ 返回 (状态, n_load_bearing)；状态 ∈ ok / failed / instrument_zero"""
    if rec.get("failures"):
        return "failed", None
    nc = rec.get("n_cards")
    if nc is None:
        return "failed", None
    if nc == 0:
        return "instrument_zero", None
    return "ok", rec.get("n_load_bearing")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-root", default=DEFAULT_RUNS)
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()
    R, OUT = args.runs_root, args.out
    os.makedirs(OUT, exist_ok=True)
    rep, fails = {}, []

    for batch in BATCHES:
        p = os.path.join(R, batch, "arms.jsonl")
        if not os.path.exists(p):
            continue
        recs = []
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except Exception:
                continue
        if not recs:
            continue
        print("\n" + "=" * 104)
        print("批 %s · n(原始行)=%d" % (batch, len(recs)))
        print("=" * 104)
        binfo = dict(batch=batch, n_raw=len(recs), arms={})

        # 按臂统计
        byarm = defaultdict(list)
        for r in recs:
            byarm[r.get("arm")].append(r)
        print("  %-18s %-7s %-7s %-9s %-9s %-9s %-10s %s"
              % ("臂", "原始", "有效", "失败", "仪器零", "真零", "承重非零", "非零比例"))
        for arm in sorted(byarm):
            rs = byarm[arm]
            n_raw = len(rs)
            st = [classify(r) for r in rs]
            n_failed = sum(1 for s, _ in st if s == "failed")
            n_instr = sum(1 for s, _ in st if s == "instrument_zero")
            vals = [v for s, v in st if s == "ok" and v is not None]
            n_valid = len(vals)
            n_zero = sum(1 for v in vals if v == 0)
            n_nz = sum(1 for v in vals if v > 0)
            ratio = (n_nz / float(n_valid)) if n_valid else None
            print("  %-18s %-7d %-7d %-9d %-9d %-9d %-10d %s"
                  % (arm, n_raw, n_valid, n_failed, n_instr, n_zero, n_nz,
                     ("%.3f" % ratio) if ratio is not None else "n/a"))
            binfo["arms"][arm] = dict(n_raw=n_raw, n_valid=n_valid,
                                      n_failed=n_failed, n_instrument_zero=n_instr,
                                      n_true_zero=n_zero, n_nonzero=n_nz,
                                      nonzero_ratio=ratio,
                                      n_missing_field=sum(
                                          1 for s, v in st if s == "ok" and v is None))

        # ★ 零分布：同臂、同题、不同 rep 的 σ
        cell = defaultdict(list)          # (arm, task) -> [v]
        for r in recs:
            s, v = classify(r)
            if s == "ok" and v is not None:
                cell[(r.get("arm"), r.get("task_id"))].append(v)
        with_rep = {k: vs for k, vs in cell.items() if len(vs) >= 2}
        if with_rep:
            sds = []
            for vs in with_rep.values():
                if len(vs) >= 2:
                    sds.append(statistics.pstdev(vs))
            # 题内 rep σ 的中位
            med_sigma = statistics.median(sds) if sds else 0.0
            print("\n  ★ 本批零分布（同臂同题不同 rep）：%d 个格有 ≥2 个 rep" % len(with_rep))
            print("    题内 rep σ（pstdev）逐格：%s"
                  % (["%.2f" % x for x in sorted(sds)[:12]] + (["…"] if len(sds) > 12 else [])))
            print("    ⇒ 题内 rep σ 的中位 = %.4f  （θ₀ 的单位）" % med_sigma)
            binfo["zero_distribution"] = dict(
                n_cells_with_rep=len(with_rep),
                sigma_per_cell=sds, median_rep_sigma=med_sigma,
                note="★ H0 来源 = 同臂同题不同 rep（总则第 3 条）")
        else:
            print("\n  ★ 零分布：★ 本批【没有】任何 (臂,题) 有 ≥2 个 rep"
                  " ⇒ 无法从本批定零分布 ⇒ 阈值不可从本批得出")
            binfo["zero_distribution"] = dict(n_cells_with_rep=0, median_rep_sigma=None,
                                              note="★ 无同臂同题多 rep ⇒ 本批零分布不可得")
        # ── 判据判定：阈值 0.5 + Wilson 区间（★ 判决线锚本批噪声地板）──
        #   ★ 判据「>0.5」是硬阈值；n=88/100 时翻转一个样本就变号 ⇒ 本身无分辨率
        #   ⇒ 判决规则：区间【不覆盖】0.5 ⇒ 成立/不成立；区间【覆盖】0.5 ⇒ 不可分辨
        THRESH = 0.5
        for arm, d in binfo["arms"].items():
            n, k = d["n_valid"], d["n_nonzero"]
            lo, hi = wilson(k, n)
            d["wilson95"] = [lo, hi]
            d["threshold"] = THRESH
            d["distance_in_samples"] = (k - THRESH * n)
            if lo is None:
                d["judgement"] = "未测（无有效样本）"
            elif lo > THRESH:
                d["judgement"] = "成立（区间下界 %.3f > 0.5）" % lo
            elif hi < THRESH:
                d["judgement"] = "不成立（区间上界 %.3f < 0.5）" % hi
            else:
                d["judgement"] = ("★ 不可分辨（Wilson 95%% 区间 [%.3f, %.3f] 覆盖阈值 0.5；"
                                  "距阈值 %+.1f 个样本）" % (lo, hi, k - THRESH * n))
            print("  ★ %-18s 承重非零 %d/%d = %.3f  Wilson95=[%s, %s]  ⇒ %s"
                  % (arm, k, n, (k / n if n else 0),
                     ("%.3f" % lo) if lo is not None else "n/a",
                     ("%.3f" % hi) if hi is not None else "n/a",
                     d["judgement"]))
        rep[batch] = binfo

    out = dict(report=rep, fails=fails)
    fp = os.path.join(OUT, "T-L3-08_读数.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n★ 读数落盘：%s" % fp)
    print("结论：%s" % ("PASS（读数齐；判决待判据原文确认）" if not fails else "FAIL"))
    return 0 if not fails else 7


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("★ 脚本崩溃：%r" % e)
        sys.exit(1)
