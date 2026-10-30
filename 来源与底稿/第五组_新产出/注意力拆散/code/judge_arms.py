#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""judge_arms.py —— ★ 薄封装：复用已定版尺子，不改判据本体 ★

★★ 纪律 ★★
· 覆盖率/缺席率算法**逐行照抄** `judge_dims.py:74-88`（★ 同一套 dimtax、★ 同一张候选维度表 ★）
· 本文件**只加**：① 按臂读取入口 ② 按 rep 分组 ③ 合并覆盖与合并增益 ④ θ₀ 与判决
· ★ 自检义务：在 direct_n30.jsonl 上，本文件的覆盖率表必须与 `judge_dims.py` **逐行一致** ★
  （不一致 ⇒ 封装有 bug ⇒ 不许开跑）

读数定义（★ 本方向的核心 ★）：
  per_answer_cov = 单份答案命中的维度数
  union_cov      = 该 rep 内 N 份答案的**并集**命中的维度数
  merge_gain     = union_cov − mean(per_answer_cov)
                   ★★ 「注意力有没有被拆散」的直接读数：
                      注意力集中 ⇒ 各路答案指向同一批维度 ⇒ 并集不比单份多
                      注意力拆散 ⇒ 各路指向不同维度 ⇒ 并集显著多于单份 ★★
"""

import collections
import glob
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
import dimtax  # noqa: E402


def load(path):
    rows = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def coverage_table(ok_rows, out=sys.stdout):
    """★ 与 judge_dims.py:74-88 **同格式、同算法** ★"""
    cov = collections.Counter()
    per = []
    for r in ok_rows:
        m = set(dimtax.mentioned(r["text"]))
        per.append(m)
        cov.update(m)
    print("═══ ★★★ 塌缩主指标：维度覆盖率（★ 缺席率 = 1 − 覆盖率 ★）★★★ ═══")
    print("  %-4s %-8s %-10s %-10s %s" % ("代码", "覆盖率", "缺席率", "绝对分母", "维度"))
    for c, nm, _d, _k in dimtax.CANDIDATE_DIMS:
        c1, c2 = cov[c], len(ok_rows)
        print("  %-4s %3d/%-3d  %5.1f%%  %9.1f%%  %s"
              % (c, c1, c2, 100.0 * c1 / c2, 100.0 * (c2 - c1) / c2, nm), file=out)
    union = set().union(*per) if per else set()
    print("  ★ %d 条并集覆盖 %d/%d 个候选维度"
          % (len(ok_rows), len(union), len(dimtax.CANDIDATE_DIMS)))
    print("  ★ 从未出现的维度: %s"
          % ([c for c, _n, _d, _k in dimtax.CANDIDATE_DIMS if cov[c] == 0] or "无"))
    print("  ★ 单条覆盖维度数: 均值 %.1f  范围 %d–%d"
          % (sum(len(x) for x in per) / len(per), min(len(x) for x in per),
             max(len(x) for x in per)))
    print("  ★ 从未出现的维度: %s"
          % ([c for c, _n, _d, _k in dimtax.CANDIDATE_DIMS if cov[c] == 0] or "无"))
    return cov, per, union


def rep_readings(ok_rows):
    """★ 按 rep 分组：合并覆盖 / 合并增益 ★"""
    by = {}
    for r in ok_rows:
        by.setdefault(r.get("rep", r.get("i")), []).append(r)
    out = []
    for rep in sorted(by):
        rs = by[rep]
        sets = [set(dimtax.mentioned(r["text"])) for r in rs]
        u = set().union(*sets)
        mean = sum(len(s) for s in sets) / len(sets)
        out.append({
            "rep": rep, "n_answers": len(rs),
            "union_cov": len(u), "mean_per_answer_cov": round(mean, 4),
            "merge_gain": round(len(u) - mean, 4),
            "union_dims": sorted(u),
            "offdomain": 1 if dimtax.offdomain_hits(" ".join(r["text"] for r in rs)) else 0,
        })
    return out


def theta0(vals):
    """★ 题内 rep σ（★ 总则第 3 条：H0 的唯一合法来源 ★）"""
    if len(vals) < 2:
        return None
    return statistics.stdev(vals)


def main():
    args = sys.argv[1:]
    if not args:
        print("用法：judge_arms.py <runs/*.jsonl> [...]")
        return 2
    all_rep = {}
    for path in args:
        rows = load(path)
        ok = [r for r in rows if r.get("ok")]
        bad = len(rows) - len(ok)
        arm = os.path.basename(path).replace(".jsonl", "")
        print("\n═══ 臂：%s ═══" % arm)
        print("  样本 %d 条（有效 %d / 失败 %d）" % (len(rows), len(ok), bad))
        if not ok:
            print("  ★ 无有效样本 ⇒ 读数不生效")
            continue
        coverage_table(ok)
        rr = rep_readings(ok)
        all_rep[arm] = {r["rep"]: r for r in rr}
        print("\n═══ 合并读数（★ 本方向主读数 ★）═══")
        print("  %-6s %-9s %-9s %-10s %s" % ("rep", "交付份数", "并集覆盖", "单份均值", "合并增益"))
        for r in rr:
            print("  %-6s %-9d %-9d %-10.2f %.2f"
                  % (r["rep"], r["n_answers"], r["union_cov"], r["mean_per_answer_cov"],
                     r["merge_gain"]))
        gains = [r["merge_gain"] for r in rr]
        unions = [r["union_cov"] for r in rr]
        print("  ★ 合并增益: 均值 %.3f  中位 %.3f  范围 %.2f–%.2f"
              % (sum(gains) / len(gains), statistics.median(gains), min(gains), max(gains)))
        print("  ★ 并集覆盖: 均值 %.3f  中位 %.1f  范围 %d–%d"
              % (sum(unions) / len(unions), statistics.median(unions),
                 min(unions), max(unions)))
        print("  ★ 含跨域分支的 rep: %d/%d" % (sum(r["offdomain"] for r in rr), len(rr)))

    # ---- 臂间配对比较（★ 判决线 = 2 × θ₀，★ θ₀ 来自同臂同题不同 rep ★）----
    if len(all_rep) >= 2:
        print("\n═══ 臂间配对比较（★ 判决线 = 2 × θ₀ ★）═══")
        names = list(all_rep)
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = names[i], names[j]
                common = sorted(set(all_rep[a]) & set(all_rep[b]))
                if not common:
                    continue
                d = [all_rep[a][r]["merge_gain"] - all_rep[b][r]["merge_gain"] for r in common]
                th = theta0(d)
                med = statistics.median(d)
                same = sum(1 for x in d if x > 0) - sum(1 for x in d if x < 0)
                if th is None or th == 0:
                    print("  %s − %s: Δ中位 %+.3f（n=%d）★ θ₀ 不可估 ⇒ 只报描述性"
                          % (a, b, med, len(d)))
                    continue
                verdict = ("显著更优" if abs(med) > 2 * th else "不可分辨")
                print("  %s − %s: Δ中位 %+.3f  θ₀=%.4f  判决线=%.4f  n=%d  同向 %+d  ⇒ %s"
                      % (a, b, med, th, 2 * th, len(d), same, verdict))
    return 0


if __name__ == "__main__":
    sys.exit(main())
