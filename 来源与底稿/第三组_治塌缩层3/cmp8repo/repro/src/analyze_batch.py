# -*- coding: utf-8 -*-
"""批次读数分析 —— **按预注册出表**（P1–P4）

> 2026-10-22 ｜ 预注册：`routes/PREREG-DECISION-RULES-2026-10-22.md`
> 度量口径：`metrics_priorart.py`（Self-Sim / 碰撞比 / ESS / DSE —— 全部有出处）

## 铁律
1. **分析单元 = 题**；臂间差按**题配对**；主读数取**中位数**
2. 差值落在噪声地板内 ⇒ 写「**不可分辨**」，**不写"无效应"**
3. **必报绝对分母**
4. 臂的顺序固定：`B0_direct`（1 次生成）/ `B0_bestof3`（等预算）/ `W_design_L2` / `W_train_L3`
5. **P1 的主对照是 `B0_bestof3`**（等预算）⇒ 与 `B0_direct` 的差**单独报**（= "多花的钱买到了什么"）

## 用法
```bash
python3 -B analyze_batch.py --run runs/main/w_dev_run.json
python3 -B analyze_batch.py --run runs/main/w_dev_run.json --json-out runs/main/analysis.json
```
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True

import metrics_priorart as MP   # noqa: E402

ARMS = ("B0_direct", "B0_bestof3", "W_design_L2", "W_train_L3")
# 预注册 §5：等预算对照臂是 P1 的**主**对照
P1_REF = "B0_bestof3"
P1_REF_SEC = "B0_direct"     # 次对照（"多花的钱买到了什么"）


def load(run_path):
    """★ 支持 w_dev_run.json **或** 增量落盘的 arms.jsonl（批次被杀时只有后者）"""
    if run_path.endswith(".jsonl"):
        rows = {}
        for ln in open(run_path, encoding="utf-8"):
            try:
                d = json.loads(ln)
            except Exception:
                continue
            rows.setdefault((d.get("task_id"), d.get("rep")), {})[d.get("arm")] = d
        return dict(rows=[dict(task_id=k[0], rep=k[1], arms=v) for k, v in rows.items()],
                    judge_model="(见各行)", judge_same_vendor=None)
    with open(run_path, encoding="utf-8") as f:
        return json.load(f)


def per_row(run):
    """把 rows 摊平成 (task, arm, rep) 的长表。"""
    out = []
    for row in run.get("rows", []):
        for arm, a in (row.get("arms") or {}).items():
            if not isinstance(a, dict):
                continue
            _d = dict(a)
            _d["arm"] = arm
            _d["err"] = a.get("error")
            out.append(_d)
    return out


def dims_by_task(rows, arm):
    """某臂逐题的中位数（题为单位）。"""
    by = defaultdict(list)
    for r in rows:
        if r["arm"] == arm and not r.get("err") and r.get("n_dims") is not None:
            by[r["task_id"]].append(r["n_dims"])
    return {t: statistics.median(v) for t, v in by.items()}


def paired_diff(rows, a_arm, b_arm, field="n_dims"):
    """逐 (题, rep) 配对差 b − a；再按题取中位数。"""
    key = {}
    for r in rows:
        if r.get("err") or r.get(field) is None:
            continue
        key[(r["task_id"], r["rep"], r["arm"])] = r[field]
    by = defaultdict(list)
    for (t, rep, arm), v in key.items():
        if arm == a_arm:
            other = key.get((t, rep, b_arm))
            if other is not None:
                by[t].append(other - v)
    return {t: statistics.median(v) for t, v in by.items()}, by


def medianity(rows, arm):
    """某臂的**中庸度**读数（用先例口径）：跨 rep 的答案自相似 + 跨 rep 的族多样性。"""
    by = defaultdict(list)
    for r in rows:
        if r["arm"] == arm and not r.get("err"):
            by[r["task_id"]].append(r)
    out = {}
    for t, rs in by.items():
        answers = []
        for r in rs:
            answers.append([c.get("claim") or "" for c in (r.get("cards") or [])])
        answers = [a for a in answers if a]
        if len(answers) < 2:
            out[t] = dict(n_rep=len(answers), self_sim=None, dse=None,
                          distinct=None, collision=None)
            continue
        out[t] = dict(
            n_rep=len(answers),
            self_sim=MP.self_sim(answers, mode="bigram"),
            self_sim_decision=MP.self_sim(answers, mode="decision"),
            dse=MP.dse(answers),
            distinct=MP.distinct_families(answers),
            collision=MP.collision_ratio(answers),
        )
    return out


def fmt(x, nd=3):
    if x is None:
        return "—"
    if isinstance(x, float):
        return ("%." + str(nd) + "f") % x
    return str(x)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()

    run = load(args.run)
    rows = per_row(run)
    tasks = sorted({r["task_id"] for r in rows if r.get("task_id")})
    arms = [a for a in ARMS if any(r["arm"] == a for r in rows)]

    L = []
    def P(s=""):
        L.append(s)
        print(s)

    P("=" * 96)
    P("批次读数 · 预注册判读 ｜ run=%s" % os.path.basename(args.run))
    P("判官=%s  judge_same_vendor=%s  臂=%s  题=%s"
      % (run.get("judge_model", run.get("judge")), run.get("judge_same_vendor"),
         ",".join(arms), ",".join(tasks)))
    P("=" * 96)

    # ── 0. 有效性与绝对分母
    P()
    P("【0】有效性与绝对分母（先例纪律：比率必须配分母）")
    P("  %-4s %-13s %-5s %7s %7s %7s %8s %8s %7s  %s"
      % ("题", "臂", "rep", "承重卡", "维度数", "锚外数", "矛盾数", "调用数", "解析失败", "0 的类型"))
    for r in sorted(rows, key=lambda x: (x.get("task_id") or "", x.get("rep") or 0, x.get("arm") or "")):
        if r.get("err"):
            P("  %-4s %-13s %-5s  ★ 失败：%s" % (r.get("task_id"), r.get("arm"), r.get("rep"), r["err"][:60]))
            continue
        cards = r.get("cards") or []
        n_con = sum(1 for c in cards if c.get("verdict") == "矛盾")
        # ★ 区分**两种 0**：仪器层（卡片没出来）vs 内容层（卡片在、判定翻转）
        if (r.get("n_dims") or 0) == 0:
            zero_kind = ("★仪器层(卡片没出来)" if (r.get("n_cards") or 0) == 0
                         else "★内容层(卡片在,承重判定翻转)")
        else:
            zero_kind = ""
        P("  %-4s %-13s %-5s %7s %7s %7s %8s %8s %7s  %s"
          % (r.get("task_id"), r.get("arm"), r.get("rep"),
             r.get("n_load_bearing"), r.get("n_dims"),
             r.get("vd_anchor_out", (r.get("anchor_out") or {}).get("n_anchor_out", 0)),
             n_con, r.get("calls"), fmt(r.get("parsefail_rate")), zero_kind))

    # ── 逐臂汇总（题为单位，中位数）
    P()
    P("【1】逐臂汇总（分析单元＝题；题内取中位数）")
    P("  %-13s %5s %10s %10s %10s %10s"
      % ("臂", "题数", "维度数中位", "维度数均值", "锚外合计", "调用数合计"))
    for a in arms:
        dm = dims_by_task(rows, a)
        if not dm:
            continue
        ao = sum((r.get("vd_anchor_out") or (r.get("anchor_out") or {}).get("n_anchor_out") or 0)
                 for r in rows if r["arm"] == a and not r.get("err"))
        calls = sum(r.get("calls") or 0 for r in rows if r["arm"] == a and not r.get("err"))
        P("  %-13s %5d %10.2f %10.2f %10s %10s"
          % (a, len(dm), statistics.median(dm.values()),
             sum(dm.values()) / len(dm), ao, calls))

    # ── P1
    P()
    P("【P1】层2 相对**等预算臂**（%s）有增益吗？（预注册：主对照必须是等预算臂）" % P1_REF)
    for ref, tag in ((P1_REF, "主对照（等预算）"), (P1_REF_SEC, "次对照（1 次生成）")):
        if ref not in arms:
            continue
        dm, by = paired_diff(rows, ref, "W_design_L2")
        if not dm:
            P("  （%s vs W_design_L2 无配对数据）" % ref)
            continue
        vals = list(dm.values())
        pos = sum(1 for v in vals if v > 0)
        med = statistics.median(vals)
        P("  vs %-12s [%s] 逐题配对差：%s ｜ 中位数 %+.2f ｜ 为正的题数 %d/%d"
          % (ref, tag, "  ".join("%s:%+.1f" % (t, dm[t]) for t in sorted(dm)),
             med, pos, len(vals)))
        P("      ⇒ 判定：%s" % ("**显示增益**（配对差中位 > 0）" if med > 0
                              else ("**未显示增益**（配对差中位 ≤ 0）" if med < 0
                                    else "不可分辨（中位 = 0）")))

    # ── P2
    P()
    P("【P2】层3 相对层2 有增量吗？（只差 evolve 一个开关 ⇒ 最干净的对照）")
    dm, by = paired_diff(rows, "W_design_L2", "W_train_L3")
    if dm:
        vals = list(dm.values())
        med = statistics.median(vals)
        P("  逐题配对差：%s ｜ 中位数 %+.2f ｜ 为正的题数 %d/%d"
          % ("  ".join("%s:%+.1f" % (t, dm[t]) for t in sorted(dm)), med,
             sum(1 for v in vals if v > 0), len(vals)))
        P("      ⇒ 判定：%s" % ("**显示增量**" if med > 0
                              else ("**未显示增量**" if med < 0 else "不可分辨（中位 = 0）")))
    else:
        P("  （无配对数据）")

    # ── P3
    P()
    P("【P3】锚外发现成立吗？★ 这是主命题的可失败判据")
    P("  ⚠️ 必须用**锚外判官**（不给 C_t）测 ⇒ 普通判官下恒为 0 **不代表**没发现")
    for a in arms:
        if a not in arms:
            continue
        ao = [(r.get("vd_anchor_out") or (r.get("anchor_out") or {}).get("n_anchor_out") or 0)
              for r in rows if r["arm"] == a and not r.get("err")]
        if not ao:
            continue
        st = all(x > 0 for x in ao)
        P("  %-13s 锚外数逐 rep：%s ｜ %s"
          % (a, ao, "**稳定 > 0 ⇒ 支持『能发现锚外维度』**" if st
             else ("**恒为 0 ⇒ 主命题不成立（我们做的是检索，不是发现）**" if max(ao) == 0
                   else "⚠️ 不稳定（有 0）⇒ 不可分辨")))

    # ── 中庸度（先例口径）
    P()
    P("【中庸度】用先例口径（Self-Sim / DSE / #distinct / 碰撞比）—— 跨 rep")
    for a in arms:
        m = medianity(rows, a)
        if not m:
            continue
        for t in sorted(m):
            d = m[t]
            P("  %-13s %-4s rep=%d  Self-Sim=%s  DSE=%s  #distinct=%s  碰撞C=%s"
              % (a, t, d.get("n_rep", 0), fmt(d.get("self_sim")),
                 fmt(d.get("dse")), d.get("distinct"),
                 fmt((d.get("collision") or {}).get("C"))))

    P()
    P("=" * 96)
    P("★ 判读纪律：差值落在噪声地板内写「不可分辨」；**不得**写'无效应'。")
    P("★ 本表只报读数，**最终结论与标注由负责人完成**。")

    if args.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(dict(text="\n".join(L),
                           rows=[{k: v for k, v in r.items() if k != "cards"} for r in rows]),
                      f, ensure_ascii=False, indent=2)
        print("落盘：%s" % args.json_out)


if __name__ == "__main__":
    main()
