#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ T-L3-01 + T-L3-08 · 臂/题口径分开登记 + 分母先剔失败生成
   --------------------------------------------------------------
   ★ T-L3-01（训练 v2 批的留出题数口径；判据：臂的个数与题数两个口径【分开登记】）
     ⇒ 实测结论：底稿里被混在一起的是【两个不同批的口径】：
        · 「3 题」= `adv` 批的**真实题数**（A01/A02/A03）
        · 「4 道」= `fv2` 批的**行数**（1 臂 × 2 题 × 2 rep = 4 份）⇒ **不是题数**
          ⇒ 且论文 L646 的「4 题 × 4 rep」是【下一步的设计建议】，★ 最易被误读成"4 道题"
        ⇒ 本脚本把【行数 / 臂数 / 题数 / 份数 / 有效份数】五列**分开列**。

   ★ T-L3-08（承重子层的零分布标定 + 批 2 工作流臂的 4 支口径重算；
             ★ 提醒：报比率前【分母必须先剔失败生成】）
     ⇒ 本脚本实现【三种缺失分形】（上一轮已建，此处落地为可复用检查）：
        ① 失败单元   ：有 `error` 字段 或 `n_cards is None` ⇒ **计失败、不进分母**
        ② 仪器层零   ：`n_cards == 0`（判官/产出层什么都没产出）⇒ **不进分母**
        ③ 内容层空   ：`n_cards > 0` 但正文 0 字符 ⇒ **分清：计数可进、比例不可用**
        ⇒ ★ 每一格写「有效(原始)」双写；**✔/✘ 一律按【有效读数】判**

   ★ 读数来源（★ 全部本机文件，零 API）：
     /workspace/lab/routes/COLLAPSE/runs/<批>/arms.jsonl
   ★ ★ 注意：★ `runs/` 被 gitignore ⇒ 逐批原始数据**不在交付仓内**
     ⇒ 本目录同时落盘一份【读数快照】（arms 摘要，不含正文全文）供第三方核对口径。

   用法：python3 T-L3-01_08_口径与分母核查.py [--runs-root DIR] [--out DIR]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RUNS = "/workspace/lab/routes/COLLAPSE/runs"

# ★ 批 2（法律域 944 条那批）的工作流臂 ⇒ T-L3-08 的「4 支口径」重算对象
BATCH2_ARMS = ["B0_bestof3", "B0_direct", "W_design_L2", "W_train_L3"]


def classify(r):
    """★ 三种缺失分形 ⇒ 返回 (kind, note)
       kind ∈ {'ok', 'fail', 'zero_instr', 'empty_content'}"""
    if r.get("error") is not None:
        return "fail", str(r.get("error"))[:80]
    nc = r.get("n_cards")
    if nc is None:
        return "fail", "n_cards is None"
    if nc == 0:
        return "zero_instr", "n_cards==0（判官/产出层零产出）"
    # 内容层：正文 0 字符
    nch = r.get("n_chars")
    if nch is not None and nch == 0:
        return "empty_content", "n_cards>0 但正文 0 字符"
    ans = r.get("answer")
    if isinstance(ans, str) and ans.strip() == "":
        return "empty_content", "answer 为空串"
    return "ok", ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-root", default=DEFAULT_RUNS)
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()
    R = args.runs_root
    os.makedirs(args.out, exist_ok=True)

    batches = {}
    for run in sorted(os.listdir(R)):
        p = os.path.join(R, run, "arms.jsonl")
        if not os.path.isfile(p):
            continue
        rows = []
        for ln in open(p, encoding="utf-8"):
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append(json.loads(ln))
            except Exception:
                pass
        if not rows:
            continue

        arms = sorted(set(r.get("arm") for r in rows))
        tasks = sorted(set(r.get("task_id") for r in rows))
        kinds = Counter()
        per = defaultdict(lambda: defaultdict(Counter))
        for r in rows:
            k, note = classify(r)
            kinds[k] += 1
            per[r.get("arm")][r.get("task_id")][k] += 1

        # ★ 每臂每题：有效(原始) 双写
        cells = {}
        for a in arms:
            row = {}
            for t in tasks:
                c = per[a][t]
                eff = c["ok"] + c["empty_content"]      # ★ 内容层空：计数可进分母
                raw = sum(c.values())
                row[t] = dict(eff=eff, raw=raw, **dict(c))
            cells[a] = row

        # ★ 承重子层的零分布（承重 = n_load_bearing > 0）
        lb = []
        for r in rows:
            k, _ = classify(r)
            v = r.get("n_load_bearing")
            lb.append((k, v))
        lb_zero = Counter()
        for k, v in lb:
            if v is None:
                lb_zero["缺字段"] += 1
            elif v == 0:
                lb_zero["零(可计入分母)"] += 1
            else:
                lb_zero["非零"] += 1

        batches[run] = dict(
            n_rows=len(rows), n_arms=len(arms), n_tasks=len(tasks),
            arms=arms, tasks=tasks,
            rows_per_arm=round(len(rows) / float(len(arms)), 3),
            kind_counts=dict(kinds),
            cells=cells,
            load_bearing_zero_dist=dict(lb_zero),
        )

    # ── 表 1：五列口径分开登记（T-L3-01）────────────────────────
    print("=" * 108)
    print("表 1 · T-L3-01 臂/题/份数口径【分开登记】（★ 行数 ≠ 题数）")
    print("=" * 108)
    print("%-12s %-6s %-6s %-6s %-9s %-9s %-9s %s"
          % ("批", "行数", "臂数", "题数", "行/臂", "有效份/臂", "题号", "缺失分形"))
    for run, b in batches.items():
        kc = b["kind_counts"]
        eff_total = kc.get("ok", 0) + kc.get("empty_content", 0)
        miss = "失败%d/仪器零%d/内容空%d" % (kc.get("fail", 0),
                                            kc.get("zero_instr", 0),
                                            kc.get("empty_content", 0))
        print("%-12s %-6d %-6d %-6d %-9.2f %-9.2f %-22s %s"
              % (run, b["n_rows"], b["n_arms"], b["n_tasks"],
                 b["rows_per_arm"], eff_total / float(b["n_arms"]),
                 ",".join(b["tasks"][:4]), miss))

    # ── 表 2：每臂每题的有效(原始) 双写（T-L3-08 分母）─────────
    print()
    print("=" * 108)
    print("表 2 · T-L3-08 每臂×题 有效(原始) 份数（★ 有效 = 剔失败 + 剔仪器层零）")
    print("=" * 108)
    for run, b in batches.items():
        tasks = b["tasks"]
        print("\n【%s】" % run)
        print("  %-20s %s" % ("arm", "  ".join("%-9s" % t for t in tasks)))
        for a in b["arms"]:
            cells = []
            for t in tasks:
                c = b["cells"][a][t]
                cells.append("%-9s" % ("%d(%d)" % (c["eff"], c["raw"])))
            print("  %-20s %s" % (a, "  ".join(cells)))
        # ★ 不齐的格（有效份数跨臂不等）⇒ 分母必须按【每臂各自】算，不能用统一分母
        for t in tasks:
            effs = {a: b["cells"][a][t]["eff"] for a in b["arms"]}
            if len(set(effs.values())) > 1:
                print("  ★ %s 上各臂有效份数不等：%s ⇒ ★ 跨臂比率的分母必须逐臂给"
                      % (t, effs))

    # ── 表 3：批 2 工作流臂的 4 支口径（T-L3-08）────────────────
    print()
    print("=" * 108)
    print("表 3 · T-L3-08 批 2 工作流臂【4 支口径】重算（★ 分母先剔失败生成）")
    print("=" * 108)
    b2 = {}
    for run, b in batches.items():
        have = [a for a in BATCH2_ARMS if a in b["arms"]]
        if len(have) < 4:
            continue
        rows_eff = {}
        for a in BATCH2_ARMS:
            tot_eff = tot_raw = 0
            per_task = {}
            for t in b["tasks"]:
                c = b["cells"][a][t]
                per_task[t] = c["eff"]
                tot_eff += c["eff"]
                tot_raw += c["raw"]
            rows_eff[a] = dict(eff=tot_eff, raw=tot_raw, per_task=per_task)
        b2[run] = rows_eff
        print("\n【%s】4 支 = %s" % (run, BATCH2_ARMS))
        print("  %-16s %-10s %-10s %-10s %s"
              % ("arm", "有效分母", "原始行数", "剔除数", "逐题有效份数"))
        for a in BATCH2_ARMS:
            r = rows_eff[a]
            print("  %-16s %-10d %-10d %-10d %s"
                  % (a, r["eff"], r["raw"], r["raw"] - r["eff"],
                     r["per_task"]))
        # ★ 4 支是否等分母（等分母才可做"错误率最高的是融合门"这类跨臂比较）
        effs = [rows_eff[a]["eff"] for a in BATCH2_ARMS]
        print("  ★ 四支有效分母：%s ⇒ %s"
              % (effs, "等分母 ✔ 可跨臂比" if len(set(effs)) == 1
                 else "★ 不等分母 ⇒ 跨臂比率必须逐臂给分母（不能只报一个数）"))

    out = dict(batches=batches, batch2_4arm=b2,
               note=("★ 行数 ≠ 题数 ≠ 臂数（T-L3-01）；"
                    "★ 有效分母已剔「失败单元」与「仪器层零」（T-L3-08）"))
    fp = os.path.join(args.out, "T-L3-01_08_读数.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n★ 读数落盘：%s" % fp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
