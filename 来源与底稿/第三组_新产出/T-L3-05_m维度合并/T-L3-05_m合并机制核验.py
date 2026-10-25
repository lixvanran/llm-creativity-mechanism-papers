#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ T-L3-05 · `m` 维度合并为什么全零 —— 定位 + 重算 + 回归断言
   --------------------------------------------------------------
   ★ 任务（派活 T-L3-05）：
     「15 题版 `m` 为何 36 格全为 0.0（合并是逐元素平均且 `m_pad_cells`=0，
       每个 seed 的 `m` 必为全零）」
     判据：三个候选成因逐一排除（训练时写入尚未进代码 / 写进了别的对象 /
           合并环节抹掉（已排除））⇒ 确认成因，并判定是否也影响 13 题版。

   ★★★ 结论（本脚本实测得出，与派活里的前提【不一致】，两处）：
     ① 派活的前提「每个 seed 的 `m` 必为全零」**不成立**：
        每个 seed 的 `m` 都【有】非零（15 题版 5–7/36，13 题版 5–6/36），
        且非零**只落在第 5 行**（第 6 种失败类型）。
     ② 派活的预设「合并环节抹掉（已排除）」**应当推翻**：
        正是合并环节抹掉的 —— 但机制不是「逐元素平均 + m_pad_cells=0」，
        而是 `merge_policies.py::avg_m` 里的**变量遮蔽 bug**（见下）。

   ★★★ 机制（★ 本脚本用三个独立证据锁定，不是靠读代码猜）：
     源码 `avg_m` 里：
         out = [[sum(pm[i][j] for i in range(len(padded))) / float(len(padded))
                 for j in range(ncol)] for i in range(nrow)]
     ⇒ ★ 外层列表推导的 `i`（行索引）被**内层生成器表达式自己的 `i`** 遮蔽
     ⇒ ★ **每一行都求同一个和**：`sum(pm[k][j] for k in range(N))`，
        其中 `pm` = **最后一个 seed** 的 padded（外层 for 循环遗留变量），
              `N` = `len(padded)` = **seed 个数**（不是行数 nrow）
     ⇒ 输出 = (最后一个 seed 的**前 N 行**按列求和) / N，**广播到全部 nrow 行**

     ⇒ 推论：
       · 15 题版：N=5 ⇒ 只取最后 seed 的前 **5** 行（0..4）⇒ 唯一非零行是**第 5 行**
         ⇒ **恰好被跳过** ⇒ 36 格全 0.0
       · 13 题版：N=6 ⇒ 取满 6 行 ⇒ 输出 = (最后 seed 的 6 行列和)/6 广播
         ⇒ ★ **也不是逐元素平均** ⇒ 13 题版**同样受影响**

   ★ 三个独立证据（本脚本自证，不依赖阅读源码的自觉）：
     E1 最小复现：两个 seed 的 m[0][0] = 1.0 / 9.0 ⇒ buggy 写法给出 **4.5**
        （= 9.0/2 ⇒ 证明「pm 取最后一个 seed」且「sum 的范围是 N 个 seed」）
     E2 15 题版重跑 ⇒ 逐位复现仓内 `policy_merged.json` 的 m（全零）
     E3 13 题版重跑 ⇒ 逐位复现仓内 `policy_merged13.json` 的 m，
        且 == 预测式（最后 seed 的 m[5] / 6 广播到所有行）

   ★ 复现路径（★ 全部来自本机，★ 不依赖任何 API）：
     仓内产物 : 来源与底稿/第三组_治塌缩层3/cmp8repo/repro/readings/policy_merged.json
                来源与底稿/第三组_治塌缩层3/cmp8repo/repro/readings/policy_merged13.json
     逐 seed  : /workspace/lab/routes/COLLAPSE/runs/pl_2026110{1,2,3,4,6}/policy.json
                /workspace/lab/routes/COLLAPSE/runs/holdout13/pl_2026110{1..6}/policy.json
   ★ ★ 注意：★ 逐 seed 的 policy.json **不在交付仓内**（`runs/` 被 gitignore），
     ★ 本脚本的读数依赖本机路径 ⇒ **仓内可复现的部分只有 E1（最小复现）与
       「重算正确 m」**（后者需要逐 seed 文件）。★ 这一点如实标注。

   用法：python3 T-L3-05_m合并机制核验.py [--runs-root DIR] [--out DIR]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RUNS = "/workspace/lab/routes/COLLAPSE/runs"
DEFAULT_READINGS = ("/workspace/work/exp/L3/来源与底稿/第三组_治塌缩层3/"
                    "cmp8repo/repro/readings")

SEEDS15 = ["pl_20261101", "pl_20261102", "pl_20261103", "pl_20261104",
           "pl_20261106"]
SEEDS13 = ["pl_20261101", "pl_20261102", "pl_20261103", "pl_20261104",
           "pl_20261105", "pl_20261106"]


# ── 被核对象：★ 原样照抄 `merge_policies.py::avg_m`（**故意保留 bug**）──
def avg_m_BUGGY(ms):
    """★ 复制 `merge_policies.py` 现行实现的 avg_m（**含变量遮蔽 bug**）"""
    nrow = max(len(m) for m in ms)
    ncol = max((len(row) for m in ms for row in m), default=0)
    pad_cells = 0
    padded = []
    for m in ms:
        pm = []
        for j in range(nrow):
            row = list(m[j]) if j < len(m) else []
            if len(row) < ncol:
                pad_cells += (ncol - len(row))
                row = row + [0.0] * (ncol - len(row))
            pm.append(row)
        padded.append(pm)
    # ★★ 这三行就是被核对象：外层 i 被内层生成器的 i 遮蔽；
    #    且 `pm` 是外层 for 遗留的【最后一个 seed】；且 sum 的范围是 len(padded)。
    out = [[sum(pm[i][j] for i in range(len(padded))) / float(len(padded))
            for j in range(ncol)] for i in range(nrow)]
    return out, pad_cells, nrow, ncol


# ── 修正版：★ 真正��逐元素平均（`padded[i]`，且 sum 范围 = nrow）──
def avg_m_FIXED(ms):
    nrow = max(len(m) for m in ms)
    ncol = max((len(row) for m in ms for row in m), default=0)
    pad_cells = 0
    padded = []
    for m in ms:
        pm = []
        for j in range(nrow):
            row = list(m[j]) if j < len(m) else []
            if len(row) < ncol:
                pad_cells += (ncol - len(row))
                row = row + [0.0] * (ncol - len(row))
            pm.append(row)
        padded.append(pm)
    # ★★ 关键：三层索引 padded[k][i][j]（k=seed、i=行、j=列）⇒ 内层 k 不与外层 i 遮蔽
    out = [[sum(padded[k][i][j] for k in range(len(padded))) / float(len(padded))
            for j in range(ncol)] for i in range(nrow)]
    return out, pad_cells, nrow, ncol


def avg_m_FIXED_independent(ms):
    """★ 独立第三实现（★ 不用推导式、显式循环）⇒ 交叉验证修正版"""
    nrow = max(len(m) for m in ms)
    ncol = max((len(row) for m in ms for row in m), default=0)
    out = []
    for i in range(nrow):
        row_out = []
        for j in range(ncol):
            vals = []
            for m in ms:
                v = m[i][j] if i < len(m) and j < len(m[i]) else 0.0
                vals.append(v)
            row_out.append(sum(vals) / float(len(vals)))
        out.append(row_out)
    return out


def flat(m):
    return [x for row in m for x in row]


def nz(m):
    return sum(1 for x in flat(m) if abs(x) > 1e-12)


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-root", default=DEFAULT_RUNS)
    ap.add_argument("--readings", default=DEFAULT_READINGS)
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()
    R = args.runs_root

    report = {}
    fails = []

    # ── E1 最小复现：证明「pm 取最后一个 seed」且「sum 范围 = N 个 seed」──
    A = [[1.0, 0.0], [0.0, 0.0]]
    B = [[9.0, 0.0], [0.0, 0.0]]
    mo, _, _, _ = avg_m_BUGGY([A, B])
    co, _, _, _ = avg_m_FIXED([A, B])
    # ★ 交叉验证：修正版 == 独立第三实现（显式循环）
    ind = avg_m_FIXED_independent([A, B])
    cross_ok = all(abs(co[i][j] - ind[i][j]) < 1e-12
                   for i in range(len(co)) for j in range(len(co[0])))
    e1_ok = (abs(mo[0][0] - 4.5) < 1e-12
             and abs(co[0][0] - 5.0) < 1e-12
             and cross_ok)
    print("E1 最小复现：buggy m[0][0] = %.4f（应为 4.5 = 9.0/2）｜ "
          "修正版 = %.4f（应为 5.0）⇒ %s"
          % (mo[0][0], co[0][0], "PASS" if e1_ok else "FAIL"))
    if not e1_ok:
        fails.append("E1 最小复现与预测不符")
    report["E1_minimal_repro"] = dict(buggy=mo[0][0], fixed=co[0][0],
                                       fixed_independent=ind[0][0],
                                       cross_check_pass=cross_ok, pass_=e1_ok)

    # ── 两版的逐 seed 与合并复现 ──────────────────────────────
    for tag, seeds, sub, reading in [
            ("15题版", SEEDS15, "", "policy_merged.json"),
            ("13题版", SEEDS13, "holdout13", "policy_merged13.json")]:
        paths = [os.path.join(R, sub, s, "policy.json") for s in seeds]
        if not all(os.path.exists(p) for p in paths):
            print("%s：逐 seed policy.json 不全在 %s ⇒ 该版只报仓内可复现部分"
                  % (tag, R))
            report[tag] = dict(available=False)
            continue
        ms = [load(p)["policy"]["m"] for p in paths]
        bug, pad, nrow, ncol = avg_m_BUGGY(ms)
        fix, _, _, _ = avg_m_FIXED(ms)
        fix_ind = avg_m_FIXED_independent(ms)
        fix_cross_ok = all(abs(a - b) < 1e-12
                           for ra, rb in zip(fix, fix_ind) for a, b in zip(ra, rb))
        if not fix_cross_ok:
            fails.append("%s：修正版与独立实现不一致" % tag)

        # 仓内合并产物
        rp = os.path.join(args.readings, reading)
        rep = dict(available=True, n_seeds=len(seeds), m_shape=[nrow, ncol],
                   m_pad_cells=pad,
                   per_seed_nonzero={s: nz(m) for s, m in zip(seeds, ms)},
                   per_seed_nonzero_rows={
                       s: [i for i, row in enumerate(m)
                           if any(abs(x) > 1e-12 for x in row)]
                       for s, m in zip(seeds, ms)},
                   buggy_nonzero=nz(bug), fixed_nonzero=nz(fix),
                   fixed_cross_check_pass=fix_cross_ok)
        if os.path.exists(rp):
            cm = load(rp)["policy"]["m"]
            rep["in_repo_merged_nonzero"] = nz(cm)
            rep["buggy_reproduces_repo"] = all(
                abs(a - b) < 1e-12 for ra, rb in zip(bug, cm) for a, b in
                zip(ra, rb))
            rep["fixed_equals_repo"] = all(
                abs(a - b) < 1e-12 for ra, rb in zip(fix, cm) for a, b in
                zip(ra, rb))
            # ★ 预测式：最后 seed 的前 N 行列和 / N，广播
            last = ms[-1]
            N = len(ms)
            pred = [[sum(last[k][j] for k in range(N)) / float(N)
                     for j in range(ncol)] for i in range(nrow)]
            rep["buggy_equals_prediction"] = all(
                abs(a - b) < 1e-12 for ra, rb in zip(bug, pred)
                for a, b in zip(ra, rb))
            print("%s：仓内 m 非零=%d ｜ buggy 重跑非零=%d（逐位复现仓内=%s）｜"
                  " 修正版非零=%d ｜ buggy==预测式=%s"
                  % (tag, rep["in_repo_merged_nonzero"], rep["buggy_nonzero"],
                     rep["buggy_reproduces_repo"], rep["fixed_nonzero"],
                     rep["buggy_equals_prediction"]))
            if not rep["buggy_reproduces_repo"]:
                fails.append("%s：buggy 重跑未复现仓内读数" % tag)
            if not rep["buggy_equals_prediction"]:
                fails.append("%s：buggy 输出与预测式不符" % tag)
            # 修正版落盘（★ 供论文重算用）
            os.makedirs(args.out, exist_ok=True)
            fp = os.path.join(args.out, "policy_m_%s_fixed.json" % tag)
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(dict(
                    note=("★ T-L3-05 重算：m 维度用【修正版逐元素平均】；"
                          "★ 仓内 policy_merged*.json 的 m 是【buggy 合并】的产物"
                          "（最后一个 seed 的前 N 行列和/N 广播），不可用"),
                    n_seeds=len(seeds), m_shape=[nrow, ncol],
                    m_pad_cells=pad,
                    per_seed_m={s: m for s, m in zip(seeds, ms)},
                    m_fixed=fix, m_buggy_reproduced=bug),
                    f, ensure_ascii=False, indent=2)
            rep["fixed_output"] = fp
        report[tag] = rep

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "T-L3-05_读数.json"), "w",
              encoding="utf-8") as f:
        json.dump(dict(report=report, fails=fails), f,
                  ensure_ascii=False, indent=2)
    print("\n结论：%s" % ("全部证据 PASS" if not fails else "FAIL: %s" % fails))
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main())
