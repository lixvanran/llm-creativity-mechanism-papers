#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并多个并行训练进程的权重（并行 REINFORCE 的权重平均）。

> 2026-10-24 ｜ 配合 `launch_train.sh`（多进程同奖励、不同 seed）
> 用法：python3 -B merge_policies.py runs/pl_* --out runs/policy_merged.json

★ 为什么可以平均：所有进程**用同一份奖励函数**（局部不钻牛角尖 + 整体更宽）、
  只是采样种子不同 ⇒ 它们的梯度估计是**同一目标的不同蒙特卡洛样本** ⇒ 平均是标准做法。
⇒ ⇒ 与"用不同奖励各跑各的"不同 —— 那种不能平均（目标不一致）。
"""
from __future__ import annotations

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def avg_vectors(vectors):
    n = len(vectors)
    return [sum(v[i] for v in vectors) / float(n) for i in range(len(vectors[0]))]



def merge(paths):
    pols, hists = [], []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        pols.append(d["policy"])
        hists.extend(d.get("hist", []))
    if not pols:
        raise SystemExit("没有可合并的策略")

    # 矩阵类权重（m）逐元素平均
    # ★ 2026-10-24 修：各 seed 的 m **内层行长不齐**（遇到的失败类型数不同）
    #   ⇒ 原实现用 ms[0][j] 的长度索引所有 seed ⇒ IndexError ⇒ 合并静默失败
    #   ⇒ 修法：按**并集**补齐（缺的补 0 = 该 seed 没遇到过这个失败类型 ⇒ 无意见），再平均
    def avg_m(ms):
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
        # ★ m 是 **2D**（失败类型 × 修复动作）⇒ 逐元素平均（**不是 3D**）
        out = [[sum(pm[i][j] for i in range(len(padded))) / float(len(padded))
                for j in range(ncol)] for i in range(nrow)]
        avg_m.pad_cells = pad_cells
        avg_m.shape = (nrow, ncol)
        return out

    out = dict(
        u=avg_vectors([p["u"] for p in pols]),
        v=avg_vectors([p["v"] for p in pols]),
        t=avg_vectors([p["t"] for p in pols]),
        m=avg_m([p["m"] for p in pols]),
        arb=avg_vectors([p.get("arb") or [0.0] * 3 for p in pols]),
        nf=avg_vectors([p.get("nf") or [0.0] * 4 for p in pols]),
        mm=avg_vectors([p.get("mm") or [0.0] * 3 for p in pols]),
    )
    meta = dict(n_runs=len(pols), sources=paths, n_samples=len(hists),
                lam=hists[0].get("lam") if hists else None,
                m_shape=getattr(avg_m, "shape", None),
                m_pad_cells=getattr(avg_m, "pad_cells", None),
                per_source_samples={os.path.basename(os.path.dirname(p)): len(h)
                                    for p, h in zip(paths, hists)},
                per_source_samples_NOTE='★ 注意：此字段取的是 hist 条目【键数】，不是样本数；★ 真实样本总数以 n_samples 为准（外部核验请用 n_samples）')
    return out, meta, hists


if __name__ == "__main__":
    # ★★ 2026-10-25 修【反馈循环 bug】：原写法只过滤了 "--out" 这个**标志**，
    #   却没过滤它的**值** ⇒ ⇒ "--out runs/policy_merged.json" 里的路径被当成
    #   第 6 个**输入源** ⇒ ⇒ 每次重跑都把上一次的输出再平均进去（88→176→264→352）
    #   ⇒ ⇒ 而且【第一次合并是干净的】（输出文件当时还不存在）⇒ ⇒ 既有读数未受影响
    _argv = sys.argv[1:]
    args, i = [], 0
    while i < len(_argv):
        a = _argv[i]
        if a == "--out":
            i += 2          # ★ 跳过 --out 及其【值】
            continue
        if a.startswith("--"):
            i += 1
            continue
        args.append(a)
        i += 1
    outp = None
    if "--out" in sys.argv:
        outp = sys.argv[sys.argv.index("--out") + 1]
    paths = []
    for a in args:
        paths.extend(sorted(glob.glob(a)) if any(c in a for c in "*?[") else [a])
    paths = [os.path.join(p, "policy.json") if os.path.isdir(p) else p for p in paths]
    paths = [p for p in paths if os.path.exists(p)]
    if not paths:
        raise SystemExit("找不到 policy.json")
    pol, meta, hists = merge(paths)
    outp = outp or "runs/policy_merged.json"
    os.makedirs(os.path.dirname(os.path.abspath(outp)), exist_ok=True)
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(dict(policy=pol, meta=meta, hist=hists), f,
                  ensure_ascii=False, indent=2)
    print("✔ 合并 %d 个进程 / %d 样本 → %s" % (meta["n_runs"], meta["n_samples"], outp))
    print("  u(修复型) ", [round(x, 2) for x in pol["u"]])
    print("  v(范围)   ", [round(x, 2) for x in pol["v"]])
    print("  t(强度)   ", [round(x, 2) for x in pol["t"]])
    print("  arb(仲裁) ", [round(x, 2) for x in pol["arb"]])
    print("  nf(发散度)", [round(x, 2) for x in pol["nf"]], "  (1,2,3,4)")
    print("  mm(合并)  ", [round(x, 2) for x in pol["mm"]],
          "  (mechanical, packet, vote)")
