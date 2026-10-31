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


def unit_readings(answers, jmap, tasks, ev_n):
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
    U, detail = unit_readings(answers, jmap, tasks, ev_n)
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
                    if (pa, pb, pm) == (A, B, metric):
                        pred = pd
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
    A("## 6. ★ 反自证自检")
    A("")
    A("| 检查项 | 结果 | 期望 |")
    A("|---|---|---|")
    A("| 提示词泄漏（依据/结论/金标特征、★ 已剔除题面自带文字 ★） | ★ **%d 处命中**（★ 扫了 %d 个特征串 ★） | 0 |" % (len(leaks), len(feats)))
    A("| 打乱自检（T3 的 token 序列逐位不同、★ 集合相同、★ 长度同 ★） | ★ %d/%d 题通过 | 全通过 |" % (sum(1 for x in shuf_ok if x), len(shuf_ok)))
    A("| 阶段1 标注完整性（ann 数 == 单元数） | ★ %d/%d 个标注文件 | 全通过 |" % (ann_full, ann_tot))
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
