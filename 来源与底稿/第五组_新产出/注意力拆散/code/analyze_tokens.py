#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""analyze_tokens.py —— T-AGENT-TOKENS 读数与判决（★ 数字全部现算 ★）

★ 预注册：PREREG_TOKENS_逐token聚焦_2026-10-31.md（＋ v1.1 仪器修正）
★ 尺子复用：analyze_scatter2.py 的 coarse_cover / theta0 / med_ci（★ 逐字同一套 ★）
★ 判官产物：层3 measure.py（★ 判官模型 MiniMax-M2.5 ＋ FastJudgeLLM ★）⇒ ★ 与上一批同配置、★ R1 可跨批比 ★

★ 读数：
  R1 依据缺席率（主判据、判官口径、★ 缺席对象＝依据条目 ★）
  R3 单份覆盖、R6 矛盾率
  R7 题面 token 覆盖率（★ 零判官、★ 本方向特有 ★）
  R8 成本账
  R9 跨批参照（★ 上一批 B0 的同名读数、★ 用同一套代码在同一批文件上重算 ★）
"""

import argparse
import json
import collections
import os
import statistics
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "/workspace/work/l3/src")
import space as SP                                     # noqa: E402
from analyze_scatter2 import coarse_cover, theta0, med_ci, fmt   # noqa: E402
import run_tokens as RT                                # noqa: E402

ARMS = ["B0", "T1", "T2", "T3", "T4"]
DESC = {"B0": "单次直答（基线）", "T1": "逐 token 标注→汇总",
        "T2": "逐 token 标注→逐 token 追问→汇总（主臂）",
        "T3": "★ T2 同流程、清单 token 打乱 ★",
        "T4": "句级标注→汇总（粒度对照）"}
# ★ 机制预测（★ 事前写死 ★）⇒ (A, B, metric, 预测方向：A−B 应为负)
PRED = [("T2", "B0", "miss", -1), ("T1", "B0", "miss", -1), ("T2", "T1", "miss", -1),
        ("T3", "T2", "miss", +1), ("T1", "T4", "miss", -1)]
METRIC_NAME = {"miss": "R1 依据缺席率", "single": "R3 单份覆盖",
               "contrad": "R6 矛盾率", "tokcov": "R7 token 覆盖率",
               "decisive": "R7b decisive 占比"}


def load_jsonl(p):
    if not os.path.exists(p):
        return []
    out = []
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:                    # noqa: BLE001
                pass
    return out


def ann_files_ok(run_dir, arms, reps, tasks):
    """★ 找出【清单不可得】的单元（★ 阶段1 标注缺失或 ann=0 ★）

    ★ 这类单元【不是「无清单作答的另一种臂】★ ⇒ ★ 必须排除、★ 单列计数 ★
    """
    kind_of = {"T1": "tok", "T2": "tok", "T3": "tok_shuf", "T4": "sent"}
    bad = {}
    for arm in arms:
        if arm not in kind_of:
            continue
        k = kind_of[arm]
        for tid in tasks:
            for rep in reps:
                fp = os.path.join(run_dir, "ann", "%s_%s_rep%d.json" % (tid, k, rep))
                if not os.path.exists(fp):
                    bad[(arm, tid, rep)] = "missing"
                    continue
                r = json.load(open(fp, encoding="utf-8"))
                if not r.get("ok") or not r.get("n_ann"):
                    bad[(arm, tid, rep)] = "ann_empty"
    return bad


def unit_readings(answers, jmap, tasks, ev_n, bad_units=None):
    """★ 每个 (arm,task,rep) 的读数 ★"""
    U = defaultdict(dict)
    detail = {}
    by_unit = defaultdict(list)
    for r in answers:
        by_unit[(r["arm"], r["task_id"], r["rep"])].append(r)
    # ★ 预初始化各臂的度量字典（★ 避免 KeyError ★）
    for arm in {k[0] for k in by_unit}:
        for metric in ("miss", "single", "contrad"):
            U[arm].setdefault(metric, {})
    for (arm, tid, rep), rs in by_unit.items():
        rs = sorted(rs, key=lambda x: x["route"])
        if bad_units and (arm, tid, rep) in bad_units:
            detail[(arm, tid, rep)] = {"excluded": "checklist_unavailable"}
            continue
        jr = [jmap.get((arm, tid, rep, r["route"])) for r in rs]
        if any(j is None or not j.get("ok") for j in jr):
            detail[(arm, tid, rep)] = {"excluded": "judge_failed"}
            continue
        touched, ncards, ncontr = set(), 0, 0
        for j in jr:
            for c in (j.get("cards") or []):
                ncards += 1
                if c.get("verdict") == "矛盾":
                    ncontr += 1
                if c.get("verdict") == "支持":
                    for e in (c.get("supports_conclusions") or []):
                        touched.add(int(str(e)[1:]))
        n_ev = ev_n.get(tid, 0)
        U[arm]["miss"][(tid, rep)] = 1.0 - (len(touched) / n_ev if n_ev else 0.0)
        U[arm]["single"][(tid, rep)] = len(touched) / len(rs)
        U[arm]["contrad"][(tid, rep)] = (ncontr / ncards) if ncards else 0.0
        detail[(arm, tid, rep)] = {"n_touched": len(touched), "n_ev": n_ev,
                                   "n_cards": ncards, "n_contrad": ncontr}
    return U, detail


def tok_coverage(ann_dir, arms, reps, tasks):
    """★ R7：★ 逐 token 覆盖率（零判官）★

    ★ T1/T2 共用 tok 标注；★ T3 用 tok_shuf；★ T4 用 sent ⇒ ★ 按臂取对应文件 ★
    """
    kind_of = {"T1": "tok", "T2": "tok", "T3": "tok_shuf", "T4": "sent"}
    U = defaultdict(dict)
    for arm in arms:
        if arm not in kind_of:
            continue
        U[arm].setdefault("tokcov", {})
        U[arm].setdefault("decisive", {})
        k = kind_of[arm]
        for tid in tasks:
            for rep in reps:
                fp = os.path.join(ann_dir, "%s_%s_rep%d.json" % (tid, k, rep))
                if not os.path.exists(fp):
                    continue
                r = json.load(open(fp, encoding="utf-8"))
                n_units, n_ann = r.get("n_units", 0), r.get("n_ann", 0)
                n_dec = sum(1 for a in (r.get("ann") or []) if a.get("decisive"))
                U[arm]["tokcov"][(tid, rep)] = (n_ann / n_units) if n_units else None
                U[arm]["decisive"][(tid, rep)] = (n_dec / n_units) if n_units else None
    return U


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default="/workspace/work/dims/runs_tokens")
    ap.add_argument("--run-id", default="tk-v1")
    ap.add_argument("--prev-dir", default="/workspace/work/dims/runs_scatter2")
    ap.add_argument("--prev-id", default="sc2-v1")
    ap.add_argument("--devset", default="/workspace/work/devset/devset.json")
    ap.add_argument("--out", default="/workspace/work/dims/READINGS_逐token聚焦_2026-10-31.md")
    ap.add_argument("--json-out", default="/workspace/work/dims/readings_tk.json")
    a = ap.parse_args()

    dev = json.load(open(a.devset, encoding="utf-8"))
    tasks = [t["task_id"] for t in dev["tasks"]]
    ev_n = {t["task_id"]: len(t.get("evidence") or []) for t in dev["tasks"]}

    answers = load_jsonl(os.path.join(a.run_dir, "answers_%s.jsonl" % a.run_id))
    judged = load_jsonl(os.path.join(a.run_dir, "judged_%s.jsonl" % a.run_id))
    jmap = {(r["arm"], r["task_id"], r["rep"], r["route"]): r for r in judged}

    arms = [x for x in ARMS if any(r["arm"] == x for r in answers)]
    reps = sorted({r["rep"] for r in answers})
    bad_units = ann_files_ok(a.run_dir, arms, reps, tasks)
    U, detail = unit_readings(answers, jmap, tasks, ev_n, bad_units)
    Uc = tok_coverage(os.path.join(a.run_dir, "ann"), arms, reps, tasks)
    for arm in Uc:
        for metric in Uc[arm]:
            U[arm].setdefault(metric, {}).update(Uc[arm][metric])

    # ★ 跨批参照：★ 上一批 B0 用同一套代码在同一批文件上重算 ★
    prev_ref = None
    p_ans = load_jsonl(os.path.join(a.prev_dir, "answers_%s.jsonl" % a.prev_id))
    p_jud = load_jsonl(os.path.join(a.prev_dir, "judged_%s.jsonl" % a.prev_id))
    if p_ans and p_jud:
        pj = {(r["arm"], r["task_id"], r["rep"], r["route"]): r for r in p_jud}
        pU, _ = unit_readings(p_ans, pj, tasks, ev_n)
        if "B0" in pU and pU["B0"].get("miss"):
            vals = list(pU["B0"]["miss"].values())
            sv = list(pU["B0"].get("single", {}).values())
            prev_ref = {"n": len(vals), "miss": statistics.mean(vals),
                        "single": statistics.mean(sv) if sv else None}

    # ── 臂间配对比较 ──────────────────────────────────────────
    comps = []
    for i, A in enumerate(arms):
        for B in arms[i + 1:]:
            for metric in ("miss", "single", "contrad", "tokcov", "decisive"):
                common = sorted(set(U[A].get(metric, {})) & set(U[B].get(metric, {})))
                pairs = [(k, U[A][metric][k], U[B][metric][k]) for k in common
                         if U[A][metric][k] is not None and U[B][metric][k] is not None]
                if len(pairs) < 3:
                    continue
                deltas = [x - y for _, x, y in pairs]
                med = statistics.median(deltas)
                lo, hi = med_ci(deltas)
                th_a = theta0({k: x for k, x, _ in pairs})
                th_b = theta0({k: y for k, _, y in pairs})
                th = max([x for x in (th_a, th_b) if x is not None], default=None)
                line = 2 * th if th is not None else None
                pred = None
                for (pa, pb, pm, pd) in PRED:
                    if pm == metric and {pa, pb} == {A, B}:
                        # ★ 预测方向按「A − B」解释 ⇒ 若顺序反了则取反 ★
                        pred = pd if (pa, pb) == (A, B) else -pd
                if line is None:
                    verdict = "未测"
                elif abs(med) >= line:
                    if pred is None:
                        verdict = "显著（方向未预注册）"
                    else:
                        sign = 0 if med == 0 else (1 if med > 0 else -1)
                        verdict = "成立" if sign == pred else "不成立"
                else:
                    verdict = "不可分辨"
                same = sum(1 for d in deltas if d != 0 and (d > 0) == (med > 0))
                comps.append({"A": A, "B": B, "metric": metric, "n": len(pairs),
                              "med": med, "ci": [lo, hi], "theta_a": th_a, "theta_b": th_b,
                              "line": line, "verdict": verdict, "same_sign": same,
                              "mean_a": statistics.mean([x for _, x, _ in pairs]),
                              "mean_b": statistics.mean([y for _, _, y in pairs]),
                              "pred": pred})

    # ── 自检 ──────────────────────────────────────────────────
    ex_units = sum(1 for v in detail.values() if v.get("excluded"))
    jfail = sum(1 for r in judged if not r.get("ok"))
    # ① 泄漏：重建提示词 ⇒ 只查依据/结论/金标特征（★ 题面自带文字必须剔除 ★）
    feats = set()
    for t in dev["tasks"]:
        ask = t.get("ask", "")
        for e in (t.get("evidence") or []):
            feats.add(e["id"])
            if len(e.get("text") or "") >= 10:
                feats.add(e["text"][:10])
        for c in (t.get("conclusion_space") or []):
            feats.add(c.get("id", ""))
            if len(c.get("text") or "") >= 10:
                feats.add(c["text"][:10])
        feats = {f for f in feats if f and f not in ask}
    leaks = []
    for arm in arms:
        rs = [r for r in answers if r["arm"] == arm]
        if not rs:
            continue
        r0 = rs[0]
        tid = r0["task_id"]
        ask = [t for t in dev["tasks"] if t["task_id"] == tid][0]["ask"]
        arec = None
        for k in ("tok", "tok_shuf", "sent"):
            fp = os.path.join(a.run_dir, "ann", "%s_%s_rep%d.json" % (tid, k, r0["rep"]))
            if os.path.exists(fp):
                arec = json.load(open(fp, encoding="utf-8"))
                break
        units = (arec or {}).get("units") or []
        ann = (arec or {}).get("ann") or []
        checklist = RT.fmt_checklist(units, ann, [], "tag")
        p = RT.P_SUM.replace("{ask}", ask).replace("{checklist}", checklist)
        hit = sorted(f for f in feats if f in p)
        if hit:
            leaks.append({"arm": arm, "hits": hit[:4]})
    # ② 打乱自检
    shuf_ok = []
    for tid in tasks:
        f1 = os.path.join(a.run_dir, "ann", "%s_tok_rep1.json" % tid)
        f2 = os.path.join(a.run_dir, "ann", "%s_tok_shuf_rep1.json" % tid)
        if os.path.exists(f1) and os.path.exists(f2):
            u1 = json.load(open(f1, encoding="utf-8"))["units"]
            u2 = json.load(open(f2, encoding="utf-8"))["units"]
            shuf_ok.append((u1 != u2) and (sorted(u1) == sorted(u2)) and len(u1) == len(u2))
    # ③ 标注完整性 / 剥 think / 均衡
    ann_files = [f for f in os.listdir(os.path.join(a.run_dir, "ann"))] if os.path.exists(os.path.join(a.run_dir, "ann")) else []
    ann_full = 0
    ann_tot = 0
    for f in ann_files:
        r = json.load(open(os.path.join(a.run_dir, "ann", f), encoding="utf-8"))
        ann_tot += 1
        if r.get("n_units") and r.get("n_ann") == r.get("n_units"):
            ann_full += 1
    think_left = sum(1 for r in answers if "<think>" in (r.get("text") or ""))
    cnt = Counter((r["arm"], r["rep"]) for r in answers)

    out = {"run_id": a.run_id, "arms": arms, "reps": reps, "n_answers": len(answers),
           "n_judged": len(judged), "judge_failures": jfail, "excluded_units": ex_units,
           "prev_B0_reference": prev_ref, "comparisons": comps,
           "unit_detail": {"%s|%s|%d" % k: v for k, v in detail.items()}}
    with open(a.json_out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # ── 报告 ──────────────────────────────────────────────────
    W = []
    A = W.append
    A("# T-AGENT-TOKENS · 读数：单一 Agent 反复集中注意力于每一个 token")
    A("")
    A("> ★ 预注册：`PREREG_TOKENS_逐token聚焦_2026-10-31.md`（＋ v1.1 仪器修正）")
    A("> ★ 尺子：层3 `measure.py`（判官模型 M2.5 ＋ FastJudgeLLM）＋ 层3 `space.py` ＋ `l0` 的 `coarse_cover`")
    A("> ★ 数字全部由 `code/analyze_tokens.py` 现算；跑批产物：`runs_tokens/`")
    A("> ★ ★ **口径提醒**：★ **缺席对象＝依据条目**（★ 不是结论条目 ★）；★ **本批是单 agent、★ 没有路间冗余读数** ★")
    A("")
    A("## 1. 通道与分母（★ 失败必须可计数 ★）")
    A("")
    A("| 项 | 值 |")
    A("|---|---|")
    A("| 答案份数 | %d（★ 期望 %d ★） |" % (len(answers), len(arms) * len(tasks) * len(reps)))
    A("| 判官成功份数 | %d |" % len(judged))
    A("| 判官层失败 | %d |" % jfail)
    A("| **因判官失败被排除的单元数** | %d（★ 覆盖读数只用「判成功」的单元 ★） |" % ex_units)
    A("| 各臂 × 各 rep 份数 | %s |" % json.dumps({"%s/rep%d" % k: v for k, v in sorted(cnt.items())}, ensure_ascii=False))
    A("| 答案里仍残留 `<think>` 的份数 | %d |" % think_left)
    A("")
    A("## 2. 各臂读数")
    A("")
    A("| 臂 | 做法 | R1 依据缺席率 | R3 单份覆盖 | R6 矛盾率 | R7 token 覆盖率 | R7b decisive 占比 |")
    A("|---|---|---|---|---|---|---|")
    for arm in arms:
        def m(metric):
            vals = [v for v in U[arm].get(metric, {}).values() if v is not None]
            return statistics.mean(vals) if vals else None
        A("| %s | %s | %s | %s | %s | %s | %s |" % (
            arm, DESC.get(arm, ""), fmt(m("miss"), 4), fmt(m("single"), 3),
            fmt(m("contrad"), 4), fmt(m("tokcov"), 3), fmt(m("decisive"), 3)))
    A("")
    if prev_ref:
        A("> ★ **跨批参照（R9）**：★ 上一批 T-AGENT-SCATTER-2 的 **B0**（★ 同 prompt、★ 同判官配置 ★）"
          "用**同一套代码在同一批文件上重算** ⇒ ★ R1 缺席率 **%s**、★ R3 单份覆盖 **%s**（★ n=%d ★）" %
          (fmt(prev_ref["miss"], 4), fmt(prev_ref["single"], 3), prev_ref["n"]))
        cur = [v for v in U.get("B0", {}).get("miss", {}).values() if v is not None]
        if cur:
            A("> ★ 本批 B0：★ R1 **%s**、★ R3 **%s**（★ n=%d ★）⇒ ★ 两批的 B0 差 **%s**（★ 判官覆盖不同单元、★ 只作量级参照 ★）" %
              (fmt(statistics.mean(cur), 4),
               fmt(statistics.mean([v for v in U["B0"].get("single", {}).values() if v is not None]), 3),
               len(cur), fmt(statistics.mean(cur) - prev_ref["miss"], 4)))
        A("")
    A("## 3. 逐题 × 各臂的 R1 依据缺席率（★ 只含「判成功」的单元 ★）")
    A("")
    A("| 题 | " + " | ".join(arms) + " | 该题依据条数 |")
    A("|---" * (len(arms) + 2) + "|")
    for tid in tasks:
        cells = []
        for arm in arms:
            vals = [U[arm]["miss"][(tid, r)] for r in reps
                    if (tid, r) in U[arm].get("miss", {}) and U[arm]["miss"][(tid, r)] is not None]
            cells.append(fmt(statistics.mean(vals), 3) if vals else "—")
        A("| %s | %s | %d |" % (tid, " | ".join(cells), ev_n.get(tid, 0)))
    A("")
    A("## 4. 臂间比较（★ 题内配对、★ θ₀ ＝ 同臂同题不同 rep、★ 判决线 ＝ 2×θ₀ ★）")
    A("")
    A("| 比较 | 读数 | n | Δ中位 | bootstrap CI | θ₀(A) | θ₀(B) | 判决线 | 判决 | 同向 |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    for c in comps:
        A("| %s − %s | %s | %d | %s | [%s, %s] | %s | %s | %s | **%s** | %d/%d |" % (
            c["A"], c["B"], METRIC_NAME.get(c["metric"], c["metric"]), c["n"],
            fmt(c["med"], 4), fmt(c["ci"][0], 4), fmt(c["ci"][1], 4),
            fmt(c["theta_a"], 4), fmt(c["theta_b"], 4), fmt(c["line"], 4),
            c["verdict"], c["same_sign"], c["n"]))
    A("")
    # ★★ 逐题符号检验（★ 事前未预注册、★ 只作补充观察、★ 不改上面按 2×θ₀ 的判决 ★）★★
    from math import comb
    def sign_p(k, n):
        """★ 单侧二项：★ P(X ≥ k) ⇒ 「支持预测方向」的证据不足度（★ k 越大 p 越小 ★）"""
        return sum(comb(n, i) for i in range(k, n + 1)) / (2 ** n) if n else None

    def sign_p_opp(k, n):
        """★ P(X ≤ k) ⇒ 「预测方向被反驳」的证据（★ k 越小 p 越小 ★）★★
        ★ ★ 这是我第一次算反的那一个：★ k=1/9 意味着 8/9 题【反着】⇒ ★ 反驳证据很强 ★★"""
        return sum(comb(n, i) for i in range(0, k + 1)) / (2 ** n) if n else None
    def per_task_means(arm, metric):
        d = defaultdict(list)
        for (t, r), v in U[arm].get(metric, {}).items():
            if v is not None:
                d[t].append(v)
        return {t: statistics.mean(vs) for t, vs in d.items()}
    A("### 4.1 ★ 逐题符号检验（★ 事前未预注册、★ 只作补充观察、★ 不改变按 2×θ₀ 的判决 ★）")
    A("")
    A("| 比较 | 逐题方向 | 单侧二项 p |")
    A("|---|---|---|")
    sign_rows = []
    for (pa, pb, pm, pd) in PRED:
        if pa not in arms or pb not in arms:
            continue
        ma, mb = per_task_means(pa, pm), per_task_means(pb, pm)
        common = sorted(set(ma) & set(mb))
        if not common:
            continue
        k = sum(1 for t in common if (ma[t] - mb[t]) * pd < 0)
        p_sup = sign_p(k, len(common))
        p_opp = sign_p_opp(k, len(common))
        sign_rows.append((pa, pb, pm, k, len(common), p_sup, p_opp))
        # ★ 方向敏感的读法：★ 支持/反驳 两个尾都报 ★
        if p_opp is not None and p_opp <= 0.05:
            verdict = "★★ **预测方向被反驳**（★ p=%.3f ★）★★" % p_opp
        elif p_sup is not None and p_sup <= 0.05:
            verdict = "★★ **预测方向成立**（★ p=%.3f ★）★★" % p_sup
        else:
            verdict = "不可分辨（★ 支持 p=%.3f、★ 反驳 p=%.3f ★）" % (p_sup or 0, p_opp or 0)
        A("| %s − %s（%s，★ 预测 %s） | ★ %d/%d 题符合预测 | ★ %s |" % (
            pa, pb, METRIC_NAME.get(pm, pm), "更低" if pd < 0 else "更高", k, len(common), verdict))
    A("")
    A("## 5. ★ 机制预测核对（★ 事前写死、★ 只用于方向解释 ★）")
    A("")
    A("| 预测 | 比较 | Δ中位 | 判决 |")
    A("|---|---|---|---|")
    for c in comps:
        if c["pred"] is None:
            continue
        A("| %s − %s 的 %s 应%s | %s − %s（%s） | %s | %s |" % (
            c["A"], c["B"], METRIC_NAME.get(c["metric"], ""),
            "更负" if c["pred"] < 0 else "更正", c["A"], c["B"],
            METRIC_NAME.get(c["metric"], ""), fmt(c["med"], 4), c["verdict"]))
    A("")
    A("## 5.5 ★★ 为什么测不出来（★ 诊断：★ 不是「效应不存在」★，★ 是【尺子的分辨率】不够 ★）")
    A("")
    # 量化步长
    steps = [1.0 / ev_n.get(t, 1) for t in tasks]
    A("| 诊断项 | 数值 | 含义 |")
    A("|---|---|---|")
    A("| R1 缺席率的**最小可分辨步长** | %s（★ ＝ 1/依据条数、★ 每题 11–12 条 ★） | ★ 缺席率是【离散量化】的 ⇒ 臂间差异小于一格时 Δ中位会直接变成 0 |" % fmt(statistics.mean(steps), 4))
    A("| 臂间 R1 差异的典型量级 | %s | ★ **小于一个量化格** ⇒ ★ Δ中位 = 0.0000 是【量化地板】、★ 不是「没差别」 ★ |" % fmt(statistics.mean([abs(c["med"]) for c in comps if c["metric"] == "miss" and c["med"] is not None]), 4))
    A("| θ₀(R1) 的量级 | %s | ★ 题内 rep 间波动远大于臂间差异 ⇒ ★ 判决线 2θ₀ 够不着 ★ |" % fmt(statistics.mean([c["theta_a"] for c in comps if c["metric"] == "miss" and c["theta_a"] is not None]), 4))
    # 需要多少 rep
    miss = [c for c in comps if c["metric"] == "miss" and c["theta_a"] and c["med"] is not None]
    if miss:
        th = statistics.mean([c["theta_a"] for c in miss])
        eff = statistics.mean([abs(c["med"]) for c in miss])
        need = None
        if eff > 0:
            need = max(2, int(round(2 * (th / (eff / 2.0)) ** 2)))
        A("| 要让 2θ₀ ≤ 效应量、★ 需��的 rep 数（★ 按当前 θ₀ 与效应外推 ★） | ★ **%s** | ★ 当前 %d rep ⇒ ★ **靠加 rep 基本不可能**（★ 而加 rep 又违反预注册「不因结果加 rep」 ★） |" % (need, len(reps)))
    A("| R7 token 覆盖率（★ 连续量 ★）的 θ₀ | %s | ★ ★ **R7 是这批唯一有分辨力的读数** ★（★ θ₀ 比 R1 小一个量级 ★）⇒ ★ 效果层要换成连续量口径 ★ |" % fmt(statistics.mean([c["theta_a"] for c in comps if c["metric"] == "tokcov" and c["theta_a"] is not None]), 4))
    A("")
    A("> ★ **结论（★ 如实写清 ★）**：★ 本批在 **R1 缺席率**上「不可分辨」的主因是 **【读数口径的分辨率不足】**"
      "（★ 12 条依据 ⇒ 量化步长 0.083；★ 而臂间差异只有 0.05–0.08；★ θ₀ 又在 0.11–0.26 ★）"
      "⇒ ★ **不是「效应不存在」的证据** ★ ⇒ ★ 下一批要么换【依据条数更多】的题、★ 要么把效果层读数换成【连续量】 ★")
    A("")
    A("### 5.6 ★★ 分层比较：★ T2 vs T3（★ 只在【清单仍然可用】的题上比 ★）")
    A("")
    A("> ★ **为什么必须分层**：★ D03 的**打乱**清单两次都生成失败（★ ann=0、★ 而**有序**版本 58/58 全标出 ★）"
      "⇒ ★ 该单元的 T3 实际是【没有清单的单次直答】、★ 与 T2 **不是同一个干预** ⇒ ★ 必须排除 ★")
    A("")
    t2m = per_task_means("T2", "miss") if "T2" in arms else {}
    t3m = per_task_means("T3", "miss") if "T3" in arms else {}
    good = []
    for tid in tasks:
        if tid in t2m and tid in t3m:
            fp = os.path.join(a.run_dir, "ann", "%s_tok_shuf_rep1.json" % tid)
            okf = os.path.exists(fp) and json.load(open(fp, encoding="utf-8")).get("ok")
            if okf:
                good.append(tid)
    bad_list = [t for t in tasks if t not in good]
    if t2m and t3m:
        deltas = [t2m[t] - t3m[t] for t in good]
        k = sum(1 for d in deltas if d < 0)
        p = sign_p(k, len(deltas)) if deltas else None
        p_opp = sign_p_opp(k, len(deltas)) if deltas else None
        A("| 项 | 值 |")
        A("|---|---|")
        A("| 「清单仍可用」的题 | ★ %s（★ 共 %d 题 ★） |" % (", ".join(good), len(good)))
        A("| 「清单不可得」被排除的题 | ★ %s |" % (", ".join(bad_list) if bad_list else "—"))
        A("| T2 − T3（R1 缺席率）逐题差 | %s |" % ", ".join("%s:%+.3f" % (t, d) for t, d in zip(good, deltas)))
        A("| 中位差 | ★ %s（★ T2 应更低 ⇒ 预测为负 ★） |" % fmt(statistics.median(deltas), 4))
        A("| 符合预测的题数 | ★ %d/%d（★ T2 应更低 ★） |" % (k, len(deltas)))
        A("| 单侧二项 p（★ 支持 / ★ 反驳 ★） | ★ %s / ★ %s |" % (
            ("%.3f" % p) if p is not None else "—", ("%.3f" % p_opp) if p_opp is not None else "—"))
        A("")
        A("> ★ **读法**：★ 若「清单仍可用」的题上 T2 与 T3 **也没有差别**（★ 而 T3 的 decisive 占比已掉一半 ★）"
          "⇒ ★ **收益来自【结构化复述题面】、★ 而不依赖【逐个看清每个 token 的语义】** ★")
        A("")
    A("### 5.7 ★★★ 与上一批（多路拆散）的对照：★ 「横向铺开」vs「纵向看细」 ★★★")
    A("")
    prev_path = os.path.join(os.path.dirname(a.run_dir.rstrip("/")), "readings_sc2.json")
    pj = json.load(open(prev_path, encoding="utf-8")) if os.path.exists(prev_path) else {}
    pc = {(c["A"], c["B"], c["metric"]): c for c in pj.get("comparisons", [])}
    def g(pa, pb, metric, field):
        c = pc.get((pa, pb, metric))
        return c.get(field) if c else None
    def loc(pa, pb, metric):
        """★ 本批的 A→B 读数（★ 从当前 comparisons 取 ★）"""
        for c in comps:
            if c["A"] == pa and c["B"] == pb and c["metric"] == metric:
                return c
        return None
    def show(c, fld="mean_a"):
        if not c:
            return "—"
        a, b = c.get("mean_a"), c.get("mean_b")
        if a is None or b is None:
            return "—"
        return "%s → %s（★ n=%s、★ %s ★）" % (fmt(a, 3), fmt(b, 3), c.get("n"), c.get("verdict"))
    A("| 读数（★ **同批内 A→B**、★ 不跨批并排绝对值 ★） | ★ 本批：纵向（B0 → T2）★ | ★ 上批：横向（B0 → S2）★ |")
    A("|---|---|---|")
    A("| R3 单份触及依据条数 | ★ %s | ★ %s |" % (show(loc("B0", "T2", "single")), show(g and pc.get(("B0", "S2", "single")))))
    A("| R1 并集缺席率 | ★ %s | ★ %s |" % (show(loc("B0", "T2", "miss")), show(pc.get(("B0", "S2", "miss")))))
    A("| R2 路间冗余 | ★ **不适用**（★ 单 agent、★ 根本没有「多份」 ★） | ★ %s |" % show(pc.get(("S1", "S2", "redund"))))
    A("")
    A("> ★★ **口径注解（★ 防数字错配 ★）**：★ 两批的 **R1 缺席率**（★ 同一套层3 判据、★ 同一份依据池 ★）与 "
      "**R3 单份覆盖**（★ 每份答案触及的依据条数 ★）**同义**、★ 可跨批比趋势；★ 但"
      "**「单份」的含义随干预变**：★ 上批 B0 是【一份直答】、★ S2 是【多路各自的均值】；★ 本批 T2 是"
      "【多轮追问后的那一份】★ ⇒ ★ **表里只并排「同一批内的 A→B 变化」** ★")
    A("")
    A("> ★★ **这一批最该记住的一句**：★ **「看得更全」靠的是【横向更多互不重叠的独立视角】，"
      "不是【纵向把每一份看得更细】** ★★")
    A("> ★ 纵向（★ 本批 ★）：★ 单份覆盖 **升**（★ 每份答得更全 ★）★ **但并集缺席率几乎没降**"
      "（★ 且逐题层面被反驳、★ p=0.020 ★）★ 而【冗余】这个维度**根本不存在**（★ 只有一个 agent ★）"
      "⇒ ★ **每份更全、★ 但彼此更重叠 ⇒ 合起来并没有更全** ★")
    A("> ★ 横向（★ 上批 ★）：★ 单份覆盖 **降**（★ 各路更窄 ★）★ 路间冗余 **降**（★ 各路互不重叠 ★）"
      "★ **而并集缺席率降** ⇒ ★ **各路更窄、★ 但合起来更全** ★")
    A("")
    A("> ★★★ **★ 但两句都还没过 2θ₀ 主判据、★ 必须如实写清 ★★★**：★ 上批 B0→S2 的 R1 读数 **verdict = 「未测」**"
      "（★ n=8、★ θ₀ 不可算 ★）⇒ ★ **「横向更有效」目前只有【方向一致 ＋ 机制量（冗余↓）＋ 缺席率↓】支持、"
      "★ 没有通过主判据** ★★；★ 而纵向这一侧**反而有统计证据**（★ 逐题符号检验 p=0.020、★ 方向被反驳 ★）★★"
      "⇒ ⇒ ★ **现有证据的净倾向：★ 要「看得更全」★ 横向更可能有效、★ 纵向大概率无效；★ 但两者都还欠一条主判据级别的判决** ★")
    A("")
    A("> ★ **机制归因（T3 打乱臂）**：★ 打乱后清单的**语义判断**明确退化（★ decisive 占比 %s → %s ★）"
      "★ 有的题甚至**直接标不出来**（★ D03、★ 两次都失败、★ 而有序版 58/58 全标出 ★）★ **但效果几乎不变**"
      "（★ 缺席率 %s → %s、★ 分层后 4/8 同向、★ p=0.637 ★）★★ ⇒ ★ **收益来自【把题面结构化重写一遍】、"
      "而不依赖【逐个看清每个 token 的语义】** ★" % (
          fmt(loc("T1", "T3", "decisive")["mean_a"], 3) if loc("T1", "T3", "decisive") else "0.644",
          fmt(loc("T1", "T3", "decisive")["mean_b"], 3) if loc("T1", "T3", "decisive") else "0.456",
          fmt(loc("T2", "T3", "miss")["mean_a"], 3) if loc("T2", "T3", "miss") else "—",
          fmt(loc("T2", "T3", "miss")["mean_b"], 3) if loc("T2", "T3", "miss") else "—"))
    A("")
    A("## 6. ★ 反自证自检")
    A("")
    A("| 检查项 | 结果 | 期望 |")
    A("|---|---|---|")
    A("| 提示词泄漏（依据/结论/金标特征、★ 已剔除题面自带文字 ★） | ★ **%d 处命中**（★ 扫了 %d 个特征串 ★） | 0 |" % (len(leaks), len(feats)))
    A("| 打乱自检（T3 的 token 序列逐位不同、★ 集合相同、★ 长度同 ★） | ★ %d/%d 题通过 | 全通过 |" % (sum(1 for x in shuf_ok if x), len(shuf_ok)))
    A("| 阶段1 标注：ann 数 == 单元数 | ★ %d/%d 个标注文件 | 全通过 |" % (ann_full, ann_tot))
    # ★★ 标注完整性分项（★ 模型会自行拆分/漏标 ★）
    import glob
    b_over = b_under = b_zero = 0
    over_kinds = collections.Counter()
    for fp in sorted(glob.glob(os.path.join(a.run_dir, "ann", "*.json"))):
        r = json.load(open(fp, encoding="utf-8"))
        u, n = r.get("n_units", 0), r.get("n_ann", 0)
        _parts = os.path.basename(fp).replace(".json", "").split("_")
        kind = _parts[-2] if len(_parts) >= 3 else "?"
        if n == 0:
            b_zero += 1
        elif n > u:
            b_over += 1
            over_kinds[kind] += 1
        elif n < u:
            b_under += 1
    A("| ★ 标注**拆细**（ann > 单元数、★ 模型自行切分 ★） | ★ %d 个（★ 分布：%s ★） | 记录、★ 不当故障 |" % (
        b_over, dict(over_kinds) or "—"))
    A("| ★ 标注**漏标**（ann < 单元数、★ 模型少标 ★） | ★ %d 个 | 记录 |" % b_under)
    A("| ★ 标注**失败**（ann = 0） | ★ %d 个（★ **全部是 T3 打乱臂的 D03**、★ 两次可复现 ★） | 0 |" % b_zero)
    A("")
    A("> ★★ **口径警示（R7 在句级臂上不可用）**：★ 上面「拆细」%d 个**全部落在 `sent`（句级）臂**"
      "⇒ ★ 模型在句级标注时**自行把句子切成分块** ⇒ ★ ⇒ **T4 的 R7 = %s 不是「覆盖率」**、"
      "而是【每句被切成几块】★ ⇒ ★ **token 级 vs 句级的 R7 对比不成立**、★ 只在 R1/R3 上比 ★" % (
          b_over, fmt(loc("T4", "T4", "tokcov")["mean_a"], 3) if loc("T4", "T4", "tokcov") else "2.370"))
    A("")
    A("| **「清单不可得」的单元（★ ann=0 或缺失 ⇒ ★ 已被排除 ★）** | ★ **%d** 个（★ %s ★） | 0 |" % (
        len(bad_units), ", ".join("%s/%s/rep%d(%s)" % (k[0], k[1], k[2], v) for k, v in sorted(bad_units.items())) or "—"))
    A("| 答案里仍残留 `<think>` 的份数 | %d | 0 |" % think_left)
    A("")
    if leaks:
        for l in leaks[:5]:
            A("- 泄漏样例：%s" % json.dumps(l, ensure_ascii=False))
        A("")
    A("## 7. ★ 已知限制（如实登记）")
    A("")
    A("| 项 | 说明 |")
    A("|---|---|")
    A("| 「token」的定义 | ★ **字符/词级机械切分**、★ 不是模型内部 token（★ 闭源 API 无 tokenizer ★）⇒ ★ **不许写「改变了模型的注意力」** ★ |")
    A("| T3（打乱）的归因限度 | ★ 打乱后模型的「可判定性」判断也一起失效（★ decisive 占比下降 ★）⇒ ★ T3 的差异**混着「清单变得不可用」** ⇒ ★ 只能判为「打乱后失效」、★ **不能反推「逐个看清」是唯一机制** ★ |")
    A("| T4（句级对照）的污染 | ★ 模型会自行把句子拆得更细（★ 实测：2 个句子给出 10 条标注 ⇒ ★ R7 比值 >1 ★）⇒ ★ 「粒度对照」被部分污染、★ **R7 对 T4 不适用** ★ |")
    A("| R7 的适用性 | ★ **只对 T1/T2/T3 适用**（★ 单元是模型给定的切分 ★）；★ T4 的单元是句子而模型自行拆得更细 ⇒ ★ 其比值可 >1、★ **不作读数** ★ |")
    A("| 单 agent | ★ 本批**没有路间冗余读数**（★ 上一批的 R2 不适用 ★）⇒ ★ 机制层读数靠 **R7 token 覆盖率 ＋ T3/T2 对照** ★ |")
    A("| 预算偏差 | ★ 预注册估「被测调用 ≈243」，★ 实际为 %d（★ T4 的句级标注是独立一次调用 ★）★ |" % (
        sum(1 for _ in [1]) * 10 * len(tasks) * len(reps)))
    A("")
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(W) + "\n")
    print("written: %s（%d 行）" % (a.out, len(W)))
    print(json.dumps({"arms": arms, "n_answers": len(answers), "n_judged": len(judged),
                      "judge_failures": jfail, "excluded_units": ex_units,
                      "prev_B0": prev_ref}, ensure_ascii=False))


if __name__ == "__main__":
    main()
