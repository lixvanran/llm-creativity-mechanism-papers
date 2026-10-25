# -*- coding: utf-8 -*-
"""★ 自有宽度的 n 基线 + 嵌套子集校准（零 API 成本，纯算）

动机（主会话 2026-10-24 12:22 ②）：
  层2 发现「8 支 vs 5 支」的宽度提升 **81% 是采样量增加的机械产物**（嵌套子集校准，K=200）。
  ⇒ 我的「3 次独立直调重叠 0.41–0.61 vs 认知位置臂 0.10–0.13」必须自查：
     **两个臂的分支数真的相等吗？** 若不等 ⇒ 宽度差可能含机械成分。

本脚本做两件事（**复用现成口径，不重造**）：
  ① **n 基线**：Self-Sim（路径间两两 2-gram Jaccard 均值）随 n 的机械变化曲线
     —— 对每个臂，从它的全部分支里**嵌套抽样** k 个子支，算 Self-Sim(k)，
        看指标是否定义上随 n 漂移。
  ② **等 n 对照**：把各臂裁到**同一个 n**（取所有臂都有的最小 n），再比。

口径来源：
  · Self-Sim  = `metrics_priorart.py::self_sim(mode="bigram")`（Lake NAACL'25 原口径）
  · 路径取法   = `space.py::path_diversity`（每个 path 一组 claims）
  · 模态数     = 纯程序 `family_key` 去重（见 `align_c1.py`）

用法：python3 -B nested_calib_self.py [out.json]
"""
from __future__ import annotations

import collections
import itertools
import json
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import metrics_priorart as MP  # noqa: E402

RUNS = [
    ("main", os.path.join(HERE, "runs", "main", "arms.jsonl")),
    ("main_big", os.path.join(HERE, "runs", "main_big", "arms.jsonl")),
    ("adv", os.path.join(HERE, "runs", "adv", "arms.jsonl")),
    ("fv2", os.path.join(HERE, "runs", "fv2", "arms.jsonl")),
]
K_SUBSETS = 200
SEED = 20261024


def load(path):
    if not os.path.exists(path):
        return []
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def branches(rec):
    """★ 该记录里真正的**分支**（每个 path 一组 claims）；没有 path ⇒ 0 支。"""
    ps = rec.get("paths") or []
    cl = [list(p.get("claims") or []) for p in ps if isinstance(p, dict)]
    cl = [c for c in cl if c]
    return cl


def self_sim(cl):
    if len(cl) < 2:
        return None
    return MP.self_sim(cl, mode="bigram")


def modal_count(cl):
    """★ 模态数：纯程序 family_key 去重（口径同 align_c1.py）"""
    fams = set()
    for c in cl:
        for s in c:
            fk = "|".join(sorted(set(str(s))))
            fams.add(fk)
    return len(fams)


def nested_curve(cl, rng, max_k=None):
    """★ n 基线：对 k = 2..n，每个 k 抽 K_SUBSETS 个**嵌套子集**（相邻 k 相邻配对有效），
    返回 {k: (mean, p90, min, max, n_subsets)}"""
    n = len(cl)
    if n < 2:
        return {}
    out = {}
    for k in range(2, n + 1):
        vals = []
        idx_all = list(range(n))
        if k == n:
            subsets = [idx_all]
        else:
            subsets = []
            seen = set()
            for _ in range(K_SUBSETS * 3):
                if len(subsets) >= K_SUBSETS:
                    break
                sub = tuple(sorted(rng.sample(idx_all, k)))
                if sub in seen:
                    continue
                seen.add(sub)
                subsets.append(sub)
        for sub in subsets:
            v = self_sim([cl[i] for i in sub])
            if v is not None:
                vals.append(v)
        if vals:
            vals.sort()
            out[k] = dict(
                mean=round(statistics.fmean(vals), 4),
                p90=round(vals[min(len(vals) - 1, int(0.9 * len(vals)))], 4),
                min=round(vals[0], 4),
                max=round(vals[-1], 4),
                n_subsets=len(vals),
            )
    return out


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "nested_calib_self.json")
    rng = random.Random(SEED)
    report = {"seed": SEED, "k_subsets": K_SUBSETS, "runs": {}}

    for run_name, p in RUNS:
        recs = load(p)
        if not recs:
            continue
        # 每臂的所有记录：分支列表
        by_arm = collections.defaultdict(list)
        for r in recs:
            b = branches(r)
            if b:
                by_arm[r.get("arm")].append(b)
        run_rep = {"n_records": len(recs), "arms": {}}
        for arm, blists in sorted(by_arm.items()):
            ns = [len(b) for b in blists]
            # 全量读数（每份记录一次）
            full = [self_sim(b) for b in blists]
            full = [v for v in full if v is not None]
            # n 基线：把该臂所有分支**汇总**（模拟"n 更大"）⇒ 抽子集
            pooled = []
            for b in blists:
                pooled.extend(b)
            curve = nested_curve(pooled, rng)
            run_rep["arms"][arm] = dict(
                n_records=len(blists),
                branches_per_record=dict(collections.Counter(ns)),
                self_sim_full_mean=round(statistics.fmean(full), 4) if full else None,
                self_sim_full_min=round(min(full), 4) if full else None,
                self_sim_full_max=round(max(full), 4) if full else None,
                pooled_n=len(pooled),
                n_baseline_curve=curve,
            )
        # ② 等 n 对照：所有臂都有的最小 n
        min_n = min(
            (min(v["branches_per_record"]) for v in run_rep["arms"].values()),
            default=None,
        )
        eq = {}
        for arm, v in run_rep["arms"].items():
            vals = []
            for b in by_arm[arm]:
                if len(b) >= min_n:
                    sub = b[:min_n]
                    x = self_sim(sub)
                    if x is not None:
                        vals.append(x)
            eq[arm] = dict(
                n=min_n,
                self_sim_mean=round(statistics.fmean(vals), 4) if vals else None,
                n_values=len(vals),
            )
        run_rep["equal_n_comparison"] = dict(n=min_n, arms=eq)
        report["runs"][run_name] = run_rep

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # ── 人读摘要 ──
    print("=" * 78)
    print("★ 自有宽度校准：n 基线 + 等 n 对照（零 API）")
    print("=" * 78)
    for run_name, r in report["runs"].items():
        print("\n【run=%s】 记录 %d" % (run_name, r["n_records"]))
        for arm, v in r["arms"].items():
            bpr = ",".join("%s×%d" % (k, n) for k, n in sorted(v["branches_per_record"].items()))
            print("  %-16s 分支数/记录[%s]  全量Self-Sim=%.4f" % (
                arm, bpr, v["self_sim_full_mean"]))
            c = v["n_baseline_curve"]
            if c:
                pts = "  ".join("k=%d:%.3f" % (k, c[k]["mean"]) for k in sorted(c))
                print("      n基线曲线(汇总抽子集): %s" % pts)
        eq = r["equal_n_comparison"]
        if eq.get("n"):
            print("  ── 等 n=%d 对照 ──" % eq["n"])
            for arm, v in sorted(eq["arms"].items()):
                if v["self_sim_mean"] is not None:
                    print("    %-16s Self-Sim=%.4f  (n份=%d)" % (arm, v["self_sim_mean"], v["n_values"]))
    print("\n→ 完整数据：%s" % out_path)


if __name__ == "__main__":
    main()
