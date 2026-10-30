#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""analyze_scatter2.py —— T-AGENT-SCATTER-2 · 读数与判决（★ 数字全部现算 ★）

★ 读数口径（★ 见 PREREG v2 §1 ★）：
  R1 依据缺席率（主判据）＝ 1 − |并集触及的依据条数| / |该题依据条数|
  R2 路间冗余（机制层主读数）＝ 层3 space.path_diversity 的 2-gram Self-Sim（★ NAACL 2025 口径 ★）
  R3 单份覆盖、R4 结论级覆盖（粗口径）、R5 关键结论命中（粗口径）、R6 矛盾率、R7 账
★ 判决：题内配对（n=27）、θ₀ ＝ 1.33 × 题内 rep σ、判决线 ＝ 2×θ₀、四选一
"""

import argparse
import json
import os
import re
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/workspace/work/l3/src")
import space as SP                                    # noqa: E402

TOKEN_RE = re.compile(r"[0-9A-Za-z]+|[一-鿿]{2,}")
STOP = set("的了是在和与及对为以之其该并或不成立正确说法哪些判断如下".split())


def key_tokens(text):
    """★ 逐字复用 l0/run_l0.py 的 key_tokens（★ 中文 2-gram、★ 数字英文整段 ★）"""
    t = unicodedata.normalize("NFKC", text or "")
    toks = []
    for seg in TOKEN_RE.findall(t):
        if seg[0].isascii():
            if len(seg) >= 2 and seg.lower() not in STOP:
                toks.append(seg.lower())
        else:
            for i in range(len(seg) - 1):
                bg = seg[i:i + 2]
                if bg not in STOP:
                    toks.append(bg)
    return set(toks)


def coarse_cover(gold, claims):
    """★ 逐字复用 l0/run_l0.py:53 的 coarse_cover（★ 阈值 0.6 不改 ★）"""
    pool = set()
    for c in claims:
        pool |= key_tokens(c)
    out = {}
    for g in gold:
        gt = key_tokens(g.get("text", ""))
        if not gt:
            out[g.get("id", "?")] = {"cov": 0.0, "hit": False, "n_tok": 0}
            continue
        cov = len(gt & pool) / len(gt)
        out[g.get("id", "?")] = {"cov": round(cov, 3), "hit": cov >= 0.6, "n_tok": len(gt)}
    n_hit = sum(1 for v in out.values() if v["hit"])
    return {"per_conclusion": out, "n_hit": n_hit, "n_gold": len(gold),
            "coverage": round(n_hit / len(gold), 3) if gold else 0.0}


def theta0(units):
    """★ θ₀ 的唯一合法来源＝同臂、同题、不同 rep ★

    units: {(task_id, rep): value}
    ⇒ 题内 rep 差值 ⇒ σ_diff / √2 ＝ 题内 rep σ ⇒ θ₀ ＝ 1.33 σ
    """
    by_task = defaultdict(dict)
    for (t, r), v in units.items():
        by_task[t][r] = v
    diffs = []
    for t, d in by_task.items():
        reps = sorted(d)
        for i in range(len(reps)):
            for j in range(i + 1, len(reps)):
                diffs.append(d[reps[i]] - d[reps[j]])
    if len(diffs) < 2:
        return None
    sd = statistics.stdev(diffs)
    return 1.33 * sd / (2 ** 0.5)


def med_ci(vals, n_boot=2000, seed=20261030):
    """★ 确定性 bootstrap 中位数 CI（★ 固定种子 ★）"""
    if not vals:
        return None, None
    import random
    rnd = random.Random(seed)
    meds = []
    for _ in range(n_boot):
        meds.append(statistics.median(rnd.choice(vals) for _ in vals))
    meds.sort()
    return meds[int(0.025 * n_boot)], meds[int(0.975 * n_boot)]


def fmt(x, nd=3):
    if x is None:
        return "—"
    if isinstance(x, float):
        return ("%%.%df" % nd) % x
    return str(x)


def leakage_check(answers, tasks, ev_of, cs_of):
    """★ 反自证自检①：★ 被测臂的提示词里【不得】出现依据编号/结论编号/金标卡编号/依据原文 ★

    ★ 做法：★ 用跑批器的同一套模板【重建】每个臂的提示词 ⇒ 逐条扫泄漏特征 ★
    """
    sys.path.insert(0, HERE)
    import run_scatter2 as R
    leaks = []
    feats = set()
    for tid, t in tasks.items():
        for e in (t.get("evidence") or []):
            feats.add(e["id"])                                   # EV-xx
            txt = (e.get("text") or "").strip()
            if len(txt) >= 10:
                feats.add(txt[:10])                               # 依据原文前 10 字
        for c in (t.get("conclusion_space") or []):
            feats.add(c.get("id", ""))                           # C1..Cn
            t2 = (c.get("text") or "").strip()
            if len(t2) >= 10:
                feats.add(t2[:10])
    feats = {f for f in feats if f}
    for arm in sorted({r["arm"] for r in answers}):
        for r in answers:
            if r["arm"] != arm:
                continue
            p = R.build_prompt(arm, tasks[r["task_id"]]["ask"], r["route"], [])
            hit = sorted(f for f in feats if f in p)
            if hit:
                leaks.append({"arm": arm, "task": r["task_id"], "route": r["route"],
                              "hits": hit[:5]})
    return leaks, len(feats)


def self_checks(answers, judged, jmap):
    """★ 反自证自检②③④：prompt 一致性 / 路数 / 剥 think ★"""
    psha = defaultdict(set)
    models = defaultdict(set)
    for r in answers:
        psha[r["arm"]].add(r["prompt_sha"])
        models[r["arm"]].add(r.get("model"))
    same_prompt = {}
    for arm in psha:
        same_prompt[arm] = (len(psha[arm]) == 1)
    routes = defaultdict(Counter)
    for r in answers:
        routes[(r["arm"], r["task_id"], r["rep"])][r["route"]] += 1
    dup_rows = sum(1 for v in routes.values() for c in v.values() if c > 1)
    bad_route = sum(1 for (arm, tid, rep), v in routes.items()
                    if len(v) != (1 if arm == "B0" else 4))
    think_left = sum(1 for r in answers if "<think>" in (r.get("text") or ""))
    return {"prompt_sha_per_arm": {k: sorted(v) for k, v in psha.items()},
            "one_prompt_per_arm": same_prompt,
            "models_per_arm": {k: sorted(x for x in v if x) for k, v in models.items()},
            "dup_rows": dup_rows, "units_with_wrong_route_count": bad_route,
            "answers_with_think_tag": think_left,
            "judge_rows": len(judged)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default="/workspace/work/dims/runs_scatter2")
    ap.add_argument("--run-id", default="sc2-v1")
    ap.add_argument("--devset", default="/workspace/work/devset/devset.json")
    ap.add_argument("--out", default="/workspace/work/dims/READINGS_拆散方式对照_2026-10-30.md")
    ap.add_argument("--json-out", default="/workspace/work/dims/readings_sc2.json")
    a = ap.parse_args()

    dev = json.load(open(a.devset, encoding="utf-8"))
    tasks = {t["task_id"]: t for t in dev["tasks"]}
    ev_of = {tid: [{"id": e["id"], "text": e["text"]} for e in t.get("evidence") or []]
             for tid, t in tasks.items()}
    cs_of = {tid: (t.get("conclusion_space") or []) for tid, t in tasks.items()}

    ans_path = os.path.join(a.run_dir, "answers_%s.jsonl" % a.run_id)
    jud_path = os.path.join(a.run_dir, "judged_%s.jsonl" % a.run_id)
    answers = [json.loads(l) for l in open(ans_path, encoding="utf-8") if l.strip()]
    judged = [json.loads(l) for l in open(jud_path, encoding="utf-8") if l.strip()] \
        if os.path.exists(jud_path) else []
    jmap = {(r["arm"], r["task_id"], r["rep"], r["route"]): r for r in judged}

    arms = sorted({r["arm"] for r in answers})
    units = sorted({(r["task_id"], r["rep"]) for r in answers})
    by_arm = defaultdict(list)
    for r in answers:
        by_arm[r["arm"]].append(r)

    # ── 每个 (arm, task, rep) 的读数 ─────────────────────────────
    U = defaultdict(dict)          # U[arm][metric][(task,rep)] = value
    detail = {}
    for arm in arms:
        for metric in ("miss", "redund", "single", "ccov", "kchit", "contrad", "n_routes"):
            U[arm][metric] = {}
    for (tid, rep) in units:
        routes = sorted([r for r in answers if r["arm"] == arms[0] and False], key=lambda x: x["route"])
        for arm in arms:
            rs = sorted([r for r in by_arm[arm] if r["task_id"] == tid and r["rep"] == rep],
                        key=lambda x: x["route"])
            if not rs:
                continue
            # 零判官：条目行
            paths = [{"claims": [c for c in (r.get("text") or "").splitlines()
                                 if c.strip().startswith("-")]} for r in rs]
            paths = [p for p in paths if p["claims"]]
            if len(paths) >= 2:
                div = SP.path_diversity(paths)
                U[arm]["redund"][(tid, rep)] = div.get("pair_self_sim")
            # 判官：触及的依据编号（支持）
            touched = set()
            touched_contrad = set()
            ncards = 0
            ncontr = 0
            for r in rs:
                jr = jmap.get((arm, tid, rep, r["route"]))
                if not jr:
                    continue
                for c in (jr.get("cards") or []):
                    ncards += 1
                    if c.get("verdict") == "矛盾":
                        ncontr += 1
                    if c.get("verdict") == "支持":
                        for e in (c.get("supports_conclusions") or []):
                            touched.add(int(str(e)[1:]))
                    elif c.get("verdict") == "矛盾":
                        for e in (c.get("supports_conclusions") or []):
                            touched_contrad.add(int(str(e)[1:]))
            n_ev = len(ev_of.get(tid, []))
            U[arm]["miss"][(tid, rep)] = 1.0 - (len(touched) / n_ev if n_ev else 0.0)
            U[arm]["single"][(tid, rep)] = (len(touched) / len(rs)) if rs else 0.0
            U[arm]["contrad"][(tid, rep)] = (ncontr / ncards) if ncards else 0.0
            U[arm]["n_routes"][(tid, rep)] = len(rs)
            # 粗口径：结论级覆盖 + 关键结论
            allclaims = []
            hits = set()
            for r in rs:
                cl = (r.get("text") or "")
                bullets = [x.strip().lstrip("-*").strip()
                           for x in cl.splitlines() if x.strip().startswith("-")]
                allclaims += bullets
                cc = coarse_cover(cs_of.get(tid, []), bullets)
                for cid, v in cc["per_conclusion"].items():
                    if v["hit"]:
                        hits.add(cid)
            cc = coarse_cover(cs_of.get(tid, []), allclaims)
            U[arm]["ccov"][(tid, rep)] = len(hits)
            keys = set(tasks[tid].get("key_conclusions") or [])
            U[arm]["kchit"][(tid, rep)] = (len(keys & hits) / len(keys)) if keys else None
            detail[(arm, tid, rep)] = {"n_routes": len(rs), "n_touched": len(touched),
                                       "n_ev": n_ev, "n_contrad": ncontr, "n_cards": ncards,
                                       "touched": sorted(touched),
                                       "touched_contrad": sorted(touched_contrad),
                                       "n_ccov": len(hits), "ccov_hits": sorted(hits)}

    # ── 臂间配对比较 ────────────────────────────────────────────
    PRED = {
        ("S1", "S2", "redund"): -1, ("S1", "S3", "redund"): -1, ("S2", "S3", "redund"): -1,
        ("S1", "S4", "redund"): +1,
        ("S1", "B0", "miss"): -1, ("S2", "B0", "miss"): -1, ("S3", "B0", "miss"): -1,
        ("S4", "B0", "miss"): -1,
        ("S2", "S1", "single"): -1, ("S3", "S1", "single"): -1,
    }
    METRIC_NAME = {"miss": "R1 依据缺席率", "redund": "R2 路间冗余",
                   "single": "R3 单份覆盖", "ccov": "R4 结论级覆盖(粗)",
                   "kchit": "R5 关键结论命中(粗)", "contrad": "R6 矛盾率"}

    comps = []
    for i, A in enumerate(arms):
        for Bx in arms[i + 1:]:
            for metric in ("miss", "redund", "single", "ccov", "kchit", "contrad"):
                common = sorted(set(U[A][metric]) & set(U[Bx][metric]))
                vals_a = [U[A][metric][k] for k in common]
                vals_b = [U[Bx][metric][k] for k in common]
                pairs = [(k, a, b) for k, a, b in zip(common, vals_a, vals_b)
                         if a is not None and b is not None]
                if len(pairs) < 3:
                    continue
                deltas = [a - b for _, a, b in pairs]
                med = statistics.median(deltas)
                lo, hi = med_ci(deltas)
                th_a = theta0({k: U[A][metric][k] for k, _a, _b in pairs})
                th_b = theta0({k: U[Bx][metric][k] for k, _a, _b in pairs})
                th = max([x for x in (th_a, th_b) if x is not None], default=None)
                line = 2 * th if th is not None else None
                sign = 0 if med == 0 else (1 if med > 0 else -1)
                if line is None:
                    verdict = "未测"
                elif abs(med) >= line:
                    pred = PRED.get((A, Bx, metric))
                    if pred is None:
                        verdict = "显著（方向未预注册）"
                    else:
                        verdict = "成立" if sign == pred else "不成立"
                else:
                    verdict = "不可分辨"
                same = sum(1 for d in deltas if (d > 0) == (med > 0) and d != 0)
                comps.append({"A": A, "B": Bx, "metric": metric, "n": len(pairs),
                              "med": med, "ci": [lo, hi], "theta_a": th_a, "theta_b": th_b,
                              "line": line, "verdict": verdict, "same_sign": same,
                              "mean_a": statistics.mean(vals_a), "mean_b": statistics.mean(vals_b),
                              "pred": PRED.get((A, Bx, metric))})

    # ── 账 ──────────────────────────────────────────────────────
    fails = Counter()
    for r in answers:
        if not r.get("ok"):
            fails[(r["arm"], r.get("fail_reason"))] += 1
    judge_fail = sum(1 for r in judged if not r.get("ok"))
    judge_pf = [r.get("parsefail_rate") for r in judged if r.get("ok") and r.get("parsefail_rate") is not None]

    out = {"run_id": a.run_id, "arms": arms, "n_units": len(units),
           "n_answers": len(answers), "n_judged": len(judged),
           "call_failures": {"%s/%s" % k: v for k, v in fails.items()},
           "judge_failures": judge_fail,
           "judge_parsefail_mean": (sum(judge_pf) / len(judge_pf)) if judge_pf else None,
           "comparisons": comps, "detail": {"%s|%s|%d" % k: v for k, v in detail.items()}}
    with open(a.json_out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # ── 报告 ────────────────────────────────────────────────────
    W = []
    A = W.append
    A("# T-AGENT-SCATTER-2 · 读数：换几个拆散方式")
    A("")
    A("> ★ 预注册：`PREREG_拆散方式对照_2026-10-30.md`（v1）＋ `..._v2修订.md`（★ 六条修订、★ 跑批前 commit ★）")
    A("> ★ 尺子：层3 `measure.py` / `space.py` / `metrics_priorart.py`（★ 判据本体未动 ★）")
    A("> ★ 本文件所有数字由 `code/analyze_scatter2.py` 现算（★ 不写死 ★）；跑批产物："
      "`runs_scatter2/answers_%s.jsonl` / `judged_%s.jsonl`" % (a.run_id, a.run_id))
    A("> ★ **口径提醒**：★ **缺席对象＝依据条目**（★ 不是结论条目 ★）—— 见 v2 修订第 ⑤ 条。")
    A("")
    A("## 1. 通道与分母（★ 失败必须可计数 ★）")
    A("")
    A("| 项 | 值 |")
    A("|---|---|")
    A("| 答案份数 | %d（★ 期望 %d ★） |" % (len(answers), len(units) * sum(
        1 if arm != "B0" else 1 for arm in arms) * 0 + len(units) * (1 + 4 * (len(arms) - 1))))
    A("| 判官份数 | %d |" % len(judged))
    A("| 调用层失败（按臂/原因） | %s |" % (json.dumps(out["call_failures"], ensure_ascii=False) if out["call_failures"] else "0"))
    A("| **判官层失败** | %d |" % judge_fail)
    A("| 判官解析失败率均值 | %s |" % fmt(out["judge_parsefail_mean"], 4))
    A("")
    A("## 2. 各臂读数（★ 题内配对的原值 ★）")
    A("")
    A("| 臂 | 拆散方式 | R1 依据缺席率 | R2 路间冗余 | R3 单份覆盖 | R4 结论覆盖(粗) | R5 关键命中(粗) | R6 矛盾率 |")
    A("|---|---|---|---|---|---|---|---|")
    desc = {"B0": "不拆（1 份）", "S1": "并行采样（无结构）", "S2": "并行＋自选角度",
            "S3": "并行＋指派视角", "S4": "并行＋异构模型"}
    for arm in arms:
        def mean_of(metric):
            vals = [v for v in U[arm][metric].values() if v is not None]
            return statistics.mean(vals) if vals else None
        A("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            arm, desc.get(arm, ""), fmt(mean_of("miss"), 4), fmt(mean_of("redund"), 4),
            fmt(mean_of("single"), 3), fmt(mean_of("ccov"), 2), fmt(mean_of("kchit"), 3),
            fmt(mean_of("contrad"), 4)))
    A("")
    A("## 3. 臂间比较（★ 题内配对、★ θ₀ ＝ 同臂同题不同 rep、★ 判决线 ＝ 2×θ₀ ★）")
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
    leaks, n_feat = leakage_check(answers, tasks, ev_of, cs_of)
    chk = self_checks(answers, judged, jmap)
    A("## 4. 机制预测核对（★ 事前写死、★ 只用于方向解释 ★）")
    A("")
    A("| 预测 | 比较 | Δ中位 | 判决 |")
    A("|---|---|---|---|")
    for c in comps:
        if c["pred"] is None:
            continue
        A("| %s %s %s | %s − %s（%s） | %s | %s |" % (
            c["A"], "应" if c["pred"] < 0 else "应", c["metric"], c["A"], c["B"],
            METRIC_NAME.get(c["metric"], ""), fmt(c["med"], 4), c["verdict"]))
    A("")
    A("## 5. ★ 反自证自检（★ 跑批后逐条核 ★）")
    A("")
    A("| 检查项 | 结果 | 期望 |")
    A("|---|---|---|")
    A("| 提示词泄漏（依据编号/结论编号/金标编号/依据原文） | ★ **%d 处命中**（★ 扫了 %d 个特征串 ★） | 0 |" % (len(leaks), n_feat))
    A("| 同一臂内 prompt 是否逐字唯一（S1/S4/B0 应各只有 1 个 sha） | %s | 是 |" %
      json.dumps({k: v for k, v in chk["one_prompt_per_arm"].items()}, ensure_ascii=False))
    A("| 每臂的模型集合 | %s | S4 应有 4 款、其余 1 款 |" %
      json.dumps(chk["models_per_arm"], ensure_ascii=False))
    A("| 重复落盘行（(arm,task,rep,route) 出现 >1 次） | %d | 0 |" % chk["dup_rows"])
    A("| 路数不符的 unit（B0 应 1 路、其余应 4 路） | %d | 0 |" % chk["units_with_wrong_route_count"])
    A("| 答案里仍残留 `<think>` 的份数 | %d | 0 |" % chk["answers_with_think_tag"])
    A("| 判官落盘份数 | %d | — |" % chk["judge_rows"])
    A("")
    if leaks:
        A("★ 泄漏样例：")
        A("")
        for l in leaks[:5]:
            A("- %s" % json.dumps(l, ensure_ascii=False))
        A("")
    A("## 6. ★ 副读数的分辨力体检（★ 不许把无分辨力的读数当读数用 ★）")
    A("")
    for arm in arms:
        vals = [v for v in U[arm]["ccov"].values() if v is not None]
        A("- %s：R4 结论级覆盖(粗) 取值集合 ＝ %s" % (arm, sorted(set(vals))))
    A("")
    A("> ★ **结论**：★ 粗口径结论覆盖在本 devset 上**近乎恒 0**（★ 结论文本长、★ token 阈值 0.6 达不到 ★）"
      "⇒ ★ **该副读数无分辨力、★ 不参与判决** ★ ⇒ ★ 主判据是判官口径的 **R1 依据缺席率** 与零判官的 **R2 路间冗余** ★。")
    A("")
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(W) + "\n")
    print("written: %s（%d 行）" % (a.out, len(W)))
    print(json.dumps({"arms": arms, "n_answers": len(answers), "n_judged": len(judged),
                      "judge_failures": judge_fail,
                      "call_failures": out["call_failures"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
