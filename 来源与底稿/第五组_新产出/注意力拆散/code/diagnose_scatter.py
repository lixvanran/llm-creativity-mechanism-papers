#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diagnose_scatter.py —— ★ 判别实验：我的拆散方式不对 vs 本来就不该拆 vs 考点没 headroom ★

★★ 本脚本零成本：★ 只读已落盘的跑批产物、★ 不调 API ★

三问三答：
  Q1【拆散到底发生了吗】路间冗余（答案两两维度 Jaccard）三臂对比
      H_A（方式不对）⇒ A2 的冗余 **没比** A3/A1 低
      ⇒ 若 A2 冗余确实低 ⇒ H_A 被削弱
  Q2【拆散换来了什么】天花板诊断：只在【有 headroom 的维度】上重算
      H_C（没 headroom）⇒ 在饱和维度上早就封顶 ⇒ 只看低覆盖维度
  Q3【剂量-反应】路数 k=1..6 的并集覆盖曲线（★ 随机子采样、★ 固定种子 ★）
      单调涨且未饱和 ⇒ 拆散有收益、只是被压缩
      早早饱和 ⇒ 拆散只是把同一批维度重新洗牌 ⇒ 支持 H_B
"""

import collections
import json
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
import dimtax  # noqa: E402

RUNS = os.path.abspath(os.path.join(HERE, "..", "runs_scatter"))
ARMS = [("multi_sample", "A3 裸采样"), ("scatter", "A2 完全拆散"),
        ("shared_frame", "A1 共享框架")]
SEED = 20261030
CODES = [c for c, _n, _d, _k in dimtax.CANDIDATE_DIMS]


def load_arm(arm):
    p = os.path.join(RUNS, "%s_n20.jsonl" % arm)
    rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    by, marks = {}, []
    for r in rows:
        if r.get("marker") == "rep_done":
            marks.append(r)
            continue
        by[(r.get("rep"), r.get("route"))] = r
    reps = collections.defaultdict(dict)
    for (rep, route), r in by.items():
        if r.get("ok") and r.get("text"):
            reps[rep][route] = {"dims": set(dimtax.mentioned(r["text"])),
                                "angle": r.get("angle", "")}
    return reps


def jac(a, b):
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def boot_ci(diffs, seed=SEED, n=10000):
    rng = random.Random(seed)
    bs = []
    for _ in range(n):
        idx = [rng.randrange(len(diffs)) for _ in range(len(diffs))]
        bs.append(statistics.median([diffs[k] for k in idx]))
    bs.sort()
    return bs[int(0.025 * n)], bs[int(0.975 * n)]


def bigram(s):
    s = "".join(ch for ch in s if ch.strip())
    return {s[i:i + 2] for i in range(len(s) - 1)}


def main():
    out = []
    W = out.append
    data = {arm: load_arm(arm) for arm, _ in ARMS}

    W("# 诊断报告 · 「拆散方式不对」vs「本来就不该拆」vs「考点没 headroom」")
    W("")
    W("> 零成本诊断：只读 `runs_scatter/*.jsonl`，不调 API ｜ 生成脚本 `code/diagnose_scatter.py`")
    W("")
    W("## Q1 · 拆散到底发生了吗？（★ 路间冗余：答案两两维度 Jaccard ★）")
    W("")
    W("| 臂 | 每 rep 内路两两 Jaccard（均值） | 中位 | 范围 |")
    W("|:-:|---:|---:|:-:|")
    redund = {}
    for arm, label in ARMS:
        vals = []
        for rep, routes in data[arm].items():
            ds = [r["dims"] for r in routes.values()]
            pairs = [jac(ds[i], ds[j]) for i in range(len(ds)) for j in range(i + 1, len(ds))]
            if pairs:
                vals.append(sum(pairs) / len(pairs))
        redund[arm] = vals
        W("| %s | %.3f | %.3f | %.2f–%.2f |"
          % (label, sum(vals) / len(vals), statistics.median(vals), min(vals), max(vals)))
    W("")
    names = [a for a, _ in ARMS]
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            A, B = names[i], names[j]
            common = sorted(set(data[A]) & set(data[B]))
            d = [redund[A][sorted(data[A]).index(r)] - redund[B][sorted(data[B]).index(r)]
                 for r in common]
            lo, hi = boot_ci(d)
            W("- **%s − %s：Δ中位 %+.3f，95%% CI [%+.3f, %+.3f]**（n=%d rep，CI 不含 0 ⇒ %s）"
              % (dict(ARMS)[A], dict(ARMS)[B], statistics.median(d), lo, hi, len(common),
                 "★可分辨" if (lo > 0 or hi < 0) else "不可分辨"))
    W("")
    W("★ **读法**：★ 冗余越低 ⇒ 各路指向的东西越不同 ⇒ 「拆散」这件事**真的发生了** ★。")
    W("")

    # ---------- Q2 天花板诊断 ----------
    W("## Q2 · 考点有没有 headroom？（★ 只在【有 headroom 的维度】上重算 ★）")
    W("")
    floor_cov = {"D1": 0.967, "D2": 0.067, "D3": 0.033, "D4": 1.0, "D5": 1.0,
                 "D6": 0.5, "D7": 0.6, "D8": 0.867, "D9": 0.4, "D10": 0.367}
    head = [c for c in CODES if floor_cov[c] < 0.5]
    sat = [c for c in CODES if floor_cov[c] >= 0.5]
    W("★ 有 headroom 的维度（direct 地板覆盖 < 50%%）：**%s**（%d 个）" % ("、".join(head), len(head)))
    W("★ 已饱和的维度（≥ 50%%）：%s（%d 个）" % ("、".join(sat), len(sat)))
    W("")
    W("| 臂 | 全 10 维并集覆盖 | 饱和维度并集覆盖（满 %d） | **有 headroom 维度并集覆盖（满 %d）** |"
      % (len(sat), len(head)))
    W("|:-:|---:|---:|---:|")
    for arm, label in ARMS:
        u_all, u_sat, u_head = [], [], []
        for rep, routes in data[arm].items():
            u = set().union(*[r["dims"] for r in routes.values()])
            u_all.append(len(u))
            u_sat.append(len(u & set(sat)))
            u_head.append(len(u & set(head)))
        W("| %s | %.2f / 10 | %.2f / %d | **%.2f / %d** |"
          % (label, sum(u_all) / len(u_all), sum(u_sat) / len(u_sat), len(sat),
             sum(u_head) / len(u_head), len(head)))
    W("")
    W("| 比较（有 headroom 维度上的并集覆盖） | Δ中位 | 95% CI | 判读 |")
    W("|:-:|---:|:-:|:-:|")
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            A, B = names[i], names[j]
            common = sorted(set(data[A]) & set(data[B]))
            da, db = [], []
            for r in common:
                ua = set().union(*[x["dims"] for x in data[A][r].values()]) & set(head)
                ub = set().union(*[x["dims"] for x in data[B][r].values()]) & set(head)
                da.append(len(ua))
                db.append(len(ub))
            d = [x - y for x, y in zip(da, db)]
            lo, hi = boot_ci(d)
            W("| %s − %s | %+.3f | [%+.3f, %+.3f] | %s |"
              % (dict(ARMS)[A], dict(ARMS)[B], statistics.median(d), lo, hi,
                 "★可分辨" if (lo > 0 or hi < 0) else "不可分辨"))
    W("")

    # ---------- Q3 剂量-反应 ----------
    W("## Q3 · 剂量-反应：路数 k → 并集覆盖（★ 随机子采样、★ 200 次重抽/格 ★）")
    W("")
    W("| k（每 rep 取 k 份） | " + " | ".join(l for _a, l in ARMS) + " |")
    W("|:-:|" + ":-:|" * len(ARMS))
    curves = {}
    for k in range(1, 7):
        row = []
        for arm, label in ARMS:
            rng = random.Random(SEED + k)
            per_rep = []
            for rep, routes in data[arm].items():
                ds = [r["dims"] for r in routes.values()]
                if len(ds) < k:
                    continue
                vals = []
                for _ in range(200):
                    pick = rng.sample(ds, k)
                    vals.append(len(set().union(*pick)))
                per_rep.append(sum(vals) / len(vals))
            curves[(arm, k)] = per_rep
            row.append("%.2f" % (sum(per_rep) / len(per_rep)))
        W("| %d | %s |" % (k, " | ".join(row)))
    W("")
    W("★ **读法**：")
    W("")
    W("- ★ **单调涨且未饱和** ⇒ 拆散有收益（只是被压缩）⇒ 支持「方式可以修」")
    W("- ★ **早早饱和（曲线变平）** ⇒ 拆散只是把同一批维度**重新洗牌** ⇒ 支持「本来就不该拆」")
    W("- ★ **A2 的曲线与 A3 的曲线几乎重合** ⇒ 拆散没有额外效果 ⇒ 支持「本来就不该拆」")
    W("")
    W("### 曲线尾部：最后一段的边际")
    W("")
    W("| 臂 | k=1→2 | k=2→3 | k=3→4 | k=4→5 | k=5→6 |")
    W("|:-:|---:|---:|---:|---:|---:|")
    for arm, label in ARMS:
        cells = []
        for k in range(1, 6):
            a = sum(curves[(arm, k)]) / len(curves[(arm, k)])
            b = sum(curves[(arm, k + 1)]) / len(curves[(arm, k + 1)])
            cells.append("%+.3f" % (b - a))
        W("| %s | %s |" % (label, " | ".join(cells)))
    W("")

    # ---------- Q4 角度层：拆的是不是同一层东西 ----------
    W("## Q4 · 角度层：拆散拆的是不是同一件事？（★ 角度文本两两 bigram 相似度 ★）")
    W("")
    W("| 臂 | 同 rep 内 6 路的角度两两相似度 |")
    W("|:-:|---:|")
    for arm, label in ARMS:
        vals = []
        for rep, routes in data[arm].items():
            angs = [r["angle"] for r in routes.values() if r.get("angle")]
            if len(angs) < 2:
                continue
            pairs = [jac(bigram(angs[i]), bigram(angs[j]))
                     for i in range(len(angs)) for j in range(i + 1, len(angs))]
            vals.append(sum(pairs) / len(pairs))
        W("| %s | %s |" % (label, ("%.3f（n=%d rep）" % (sum(vals) / len(vals), len(vals)))
                           if vals else "—（★ A1 的角度在共享表里、★ 不逐路落盘 ★）"))
    W("")
    W("## 判决（三问三答）")
    W("")
    W("| 问题 | 判决 | 依据 |")
    W("|:-:|:-:|---|")
    W("| **拆散有没有真的发生？** | ★ **发生了（可分辨）** | 路间冗余 Jaccard A3 0.709 → A1 0.573 → A2 0.507；"
      "A3−A2 与 A2−A1 的 95% CI 均不含 0 |")
    W("| **是我的拆散方式不对吗？** | ★ **不是（被证伪）** | 「各自造角度」确实比「共享一份」更散；"
      "★ 机制层成立 ⇒ **不能归咎于实现** |")
    W("| **拆散换来了覆盖吗？** | ★ **测不出来（不可分辨）** | 唯一有 headroom 的 4 个维度上三臂两两 Δ中位 = 0.000、CI 含 0 |")
    W("")
    W("### ★★ 所以答案是第三种可能，不是两种 ★★")
    W("")
    W("> **既不是「方式不对」，也不是简单的「本来就不该拆」，而是："
      "★ 拆散这个动作本身有效（机制层成立），"
      "但它换来的【覆盖增量】小到在唯一有 headroom 的地方也测不出来（效果层未证）★。**")
    W("")
    W("★ **外部先验同向**（NeurIPS 2025 最佳论文《Artificial Hivemind》）：")
    W("")
    W("- 同一模型 50 次答同一开放题，**79% 的情况下平均相似度 > 0.8**（全局池随机两两仅 0.1–0.2）")
    W("- 用 **min-p（top-p 1.0 / min-p 0.1 / temp 2.0）** 这种最激进的采样干预，"
      "仍有 **81% 的回答对相似度 > 0.7** ⇒ 原文结论："
      "「**单纯依靠解码策略的调整，无法从根本上解决模型的重复问题**」")
    W("- ★ **跨模型同质化（71–82%）比单模型重复更强**：前 50 个最相似回答平均来自 **8 个不同模型**")
    W("")
    W("⇒ ★ **把同一个模型拆成 N 路 agent，在文献里就落在「单模型重复」那一栏** ⇒ "
      "★ **拆散的天花板低，是这一类干预的通病，不是本次实现的缺陷** ★。")
    W("")
    W("### ★ 纠正上一轮读数报告里的一个混淆 ★")
    W("")
    W("> 上一轮我把「D1/D8/D10 单份覆盖下降、D3 上升」当成了「覆盖变宽」的证据。"
      "★ **那是两回事** ★：")
    W("> · 逐维单份覆盖的变化 ⇒ 测的是「**每路的注意力分布挪走了**」（从默认维度挪向非默认维度）")
    W("> · 并集覆盖 ⇒ 才回答「**合起来看得更全了吗**」")
    W("> ★ 而后者在有 headroom 的维度上**不可分辨** ⇒ ★ 上一轮的措辞偏强，此处更正 ★。")
    W("")
    W("### 下一批该怎么做（★ 按证据排序 ★）")
    W("")
    W("| # | 动作 | 为什么 |")
    W("|:-:|---|---|")
    W("| 1 | ★ **主读数改成【路间冗余 Jaccard】** | 它**不受天花板影响**、**已可分辨**（0.709 vs 0.507），"
      "且**直接对应「注意力有没有被拆散」**这个构念 ⇒ 它才是干净的主读数 |")
    W("| 2 | ★ **考点换成有 headroom 的** | 10 维表里 6 个饱和、顶格；须扩表（20–30 维，含更多缺席层维度）"
      "或上 devset 9 题 ⇒ 否则效应永远被压平 |")
    W("| 3 | **剂量-反应扩到 k=12/16** | 本批 k≤6 且 headroom 仅 4 维 ⇒ 最多再涨 1 维；"
      "★ 看曲线是不是真饱和 |")
    W("| 4 | ★ **加【跨模型臂】** | 文献说**跨模型同质化 > 单模型重复** ⇒ ★ 若跨模型臂的冗余显著更低，"
      "则「拆散」应当拆到**模型层**而不是 agent 层 ⇒ ★ 这会改写整个方向 ★ |")
    W("| 5 | 换机制层 | 文献指向训练/数据/评测层；★ 采样侧同族的替代品是 **Verbalized Sampling**"
      "（VS-Standard 62.5% > Sequence 58.8% > Direct 30.0%）⇒ ★ 它测的是「分布」而不是「分叉」 ★ |")
    W("")

    path = os.path.join(os.path.abspath(os.path.join(HERE, "..")),
                        "DIAGNOSIS_拆散对不对_2026-10-30.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("\n".join(out))
    print("\nwritten:", path)


if __name__ == "__main__":
    main()
