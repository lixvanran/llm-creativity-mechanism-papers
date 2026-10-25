#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T-L1-01 · 分析：θ₀（题内 rep σ 的中位数）+ 判决线 2×θ₀ + H1–H7 逐条机制侧相容性判断。

★ 判决四选一：成立 / 不成立 / 不可分辨（带 θ₀ 与区间）/ 未测（写清卡在哪）
★ 本批【不判决 H1–H7 成立与否】——这里的「成立/不成立」= 【本批内部量与该 H 的机制侧预测相容/不相容】。

★ 通用规则（PREREG-EXEC-T-L1-01.md §3）：
  设 z 为待检验量（单元级读数或由它导出的单元内对比）：
    σ_{q,a} = std_r(z_{q,a,:}, ddof=1)          （同臂、同题、不同 rep ⇒ θ₀ 的唯一来源）
    θ₀      = median_{(q,a)} σ_{q,a}            （跨题取中位，不取均值）
    判决线   = 2 × θ₀
  效应量    = 跨题中位数 of 每题聚合（臂内量：跨 rep 均值；臂间量：两臂 rep 均值之差）
  方向      = 本批内部侧预测的方向；不成立 = 效应越过判决线且**方向相反**
  一致性门  = 逐题效应同号数 ≥ 7/9（n=9 的单侧符号检验 p=0.0898 < 0.10，事前定版 α=0.10）
"""
import os, sys, json, math, glob, argparse
import statistics as st
from collections import defaultdict

sys.dont_write_bytecode = True

RUN_DIR = "/workspace/run/units"
OUT_JSON = "/workspace/run/05_analysis.json"
OUT_TSV = "/workspace/run/05_verdicts.tsv"

# ---- 事前定版的失败判定（总则 §一.4：失败必须可计数，分母要写清含不含失败生成）
MIN_GEN_TOKENS = 6
MIN_TEXT_CHARS = 4

TASKS = ["D%02d" % i for i in range(1, 10)]
ARMS = ["A_bare", "A_list"]
REPS = [0, 1, 2]


# ------------------------------------------------------------------ 工具
def median(xs):
    xs = [x for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return st.median(xs) if xs else None


def sd(xs):
    xs = [x for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return st.stdev(xs) if len(xs) >= 2 else None


def thirds(vals):
    """vals: list of floats（按生成步序）→ (first_third_mean, last_third_mean)"""
    n = len(vals)
    if n < 3:
        return None, None
    a = max(1, int(math.ceil(n / 3.0)))
    b = max(1, int(math.floor(n / 3.0)))
    return sum(vals[:a]) / a, sum(vals[n - b:]) / b


def sign_test_p(pos, n, alpha_note=0.10):
    """单侧符号检验：p = P(X>=pos | n, p=0.5)"""
    if n == 0:
        return 1.0
    p = sum(math.comb(n, k) for k in range(pos, n + 1)) / (2.0 ** n)
    return p


# ------------------------------------------------------------------ 读单元
def load_units():
    units = []
    for p in sorted(glob.glob(os.path.join(RUN_DIR, "units_batch*.jsonl"))):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            r["_src"] = os.path.basename(p)
            units.append(r)
    return units


def unit_readings(r):
    """把一个单元的逐步内部量压成单元级读数。返回 (readings: dict, ok: bool, why: str)"""
    out = {}
    if r.get("status") != "ok":
        return out, False, "run_fail:%s" % str(r.get("error", ""))[:80]
    text = (r.get("gen_text") or "").strip()
    K = r.get("n_generated", 0)
    if K < MIN_GEN_TOKENS or len(text) < MIN_TEXT_CHARS:
        return out, False, "short_gen:K=%d,chars=%d" % (K, len(text))
    steps = r["steps"]
    lg = r.get("logit", {})

    def series(key, only_gen=True):
        out_ = []
        for s in steps:
            if only_gen and s.get("n_gen_in_ctx", 0) < 1:
                continue
            v = s.get(key)
            if v is None or (isinstance(v, float) and math.isnan(v)):
                continue
            out_.append(float(v))
        return out_

    def mean_series(key, only_gen=False):
        v = series(key, only_gen)
        return (sum(v) / len(v)) if v else None

    # ---- 单元级标量读数
    out["x_gen_odds"] = mean_series("gen_odds", True)
    out["x_logit_ent_raw"] = mean_series("logit_entropy_raw", False)
    out["x_logit_ent_sampled"] = mean_series("logit_entropy_sampled", False)
    out["x_logit_top1"] = mean_series("logit_top1_raw", False)
    out["x_h4_idx"] = mean_series("h4_early_late", False)
    out["x_d6"] = mean_series("d6_list_minus_ask", False)
    out["x_d6_placebo"] = mean_series("d6_placebo_ask_split", False)
    out["x_list_share"] = mean_series("list_share_of_prompt", False)
    out["x_attn_entropy"] = mean_series("attn_entropy", False)
    out["x_attn_supp"] = mean_series("attn_supp", False)
    out["x_attn_rank_pr"] = mean_series("attn_rank_pr", False)
    out["x_attn_sink"] = mean_series("attn_sink", False)
    out["x_head_sim"] = mean_series("head_attn_sim", False)
    out["x_hs_cos_prompt_end"] = mean_series("hs_cos_prompt_end", False)
    out["x_hs_adj_cos"] = mean_series("hs_adj_cos", False)
    out["x_h1_recency"] = mean_series("h1_recency", True)
    out["x_attn_meandist"] = mean_series("attn_meandist", False)
    out["n_gen"] = K
    out["n_prompt"] = r.get("n_prompt")

    # ---- 位置趋势（首 1/3 vs 末 1/3）
    for key, name in (("gen_odds", "d_gen_odds"),
                      ("h1_recency", "d_h1_recency"),
                      ("h4_early_late", "d_h4_idx"),
                      ("d6_list_minus_ask", "d_d6"),
                      ("d6_placebo_ask_split", "d_d6_placebo"),
                      ("logit_entropy_raw", "d_logit_ent"),
                      ("attn_entropy", "d_attn_entropy"),
                      ("hs_cos_prompt_end", "d_hs_cos_prompt_end"),
                      ("head_attn_sim", "d_head_sim")):
        s = series(key, False if key in ("d6_list_minus_ask", "d6_placebo_ask_split",
                                         "logit_entropy_raw", "attn_entropy",
                                         "hs_cos_prompt_end", "head_attn_sim") else True)
        a, b = thirds(s)
        out[name] = (b - a) if (a is not None and b is not None) else None
    return out, True, ""


# ------------------------------------------------------------------ 判决
def decide(effects, theta0, direction, n_expected=9):
    """effects: list of per-question effects（可含 None）
    direction: +1 / -1
    返回 (verdict, dict)"""
    eff = [e for e in effects if e is not None and not (isinstance(e, float) and math.isnan(e))]
    n = len(eff)
    if n == 0 or theta0 is None:
        return "未测", {"reason": "无有效读数"}
    med = st.median(eff)
    line = 2.0 * theta0
    npos = sum(1 for e in eff if e * direction > 0)
    p = sign_test_p(npos, n)
    info = {
        "n_questions": n, "effect_median": med, "effect_mean": sum(eff) / n,
        "theta0": theta0, "decision_line_2theta0": line,
        "n_same_sign": npos, "sign_test_p_one_sided": p,
        "per_question": eff,
    }
    if med * direction >= line and npos >= 7 and p < 0.10:
        verdict = "成立"
    elif med * direction <= -line and (n - npos) >= 7 and (1 - p) < 0.10:
        verdict = "不成立"
    else:
        verdict = "不可分辨"
    return verdict, info


def theta0_of(tab, arm=None):
    """tab[(q,a)][rep] = z；θ₀ = median over (q,a) of std_r(z)（ddof=1）"""
    sig = []
    for (q, a), d in tab.items():
        if arm and a != arm:
            continue
        s = sd([d[r] for r in REPS if r in d])
        if s is not None:
            sig.append(s)
    return median(sig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-json", default=OUT_JSON)
    ap.add_argument("--out-tsv", default=OUT_TSV)
    a = ap.parse_args()

    units = load_units()
    # 去重：同一 (q,a,rep) 只取最后一次成功的记录；失败记录单独计数
    best = {}
    fails = []
    for r in units:
        key = (r["task_id"], r["arm"], r["rep"])
        if r.get("status") != "ok":
            fails.append(r)
            continue
        if key not in best or r.get("attempt", 1) > best[key].get("attempt", 1):
            best[key] = r

    readings = {}
    fail_reasons = []
    n_ok = 0
    for key, r in best.items():
        rd, ok, why = unit_readings(r)
        if not ok:
            fail_reasons.append({"key": list(key), "why": why, "src": r.get("_src")})
            continue
        readings[key] = rd
        n_ok += 1

    # ---- 建表
    def tab_of(name):
        t = defaultdict(dict)
        for (q, arm, rep), rd in readings.items():
            v = rd.get(name)
            if v is not None:
                t[(q, arm)][rep] = v
        return t

    NAMES = ["x_gen_odds", "x_logit_ent_raw", "x_logit_ent_sampled", "x_logit_top1",
             "x_h4_idx", "x_d6", "x_d6_placebo", "x_list_share", "x_attn_entropy",
             "x_attn_supp", "x_attn_rank_pr", "x_attn_sink", "x_head_sim",
             "x_hs_cos_prompt_end", "x_hs_adj_cos", "x_h1_recency", "x_attn_meandist",
             "d_gen_odds", "d_h1_recency", "d_h4_idx", "d_d6", "d_d6_placebo",
             "d_logit_ent", "d_attn_entropy", "d_hs_cos_prompt_end", "d_head_sim"]
    tabs = {n: tab_of(n) for n in NAMES}

    def per_q_effect(tab, mode, arm=None):
        """mode: 'arm' ⇒ 题内跨 rep 均值；'between' ⇒ 两臂 rep 均值之差（bare − list）"""
        eff = []
        for q in TASKS:
            if mode == "arm":
                if arm is None:
                    vals = [st.mean([tab[(q, aa)][r] for r in REPS if r in tab[(q, aa)]])
                            for aa in ARMS if tab.get((q, aa))]
                    if not vals:
                        eff.append(None); continue
                    eff.append(sum(vals) / len(vals))
                else:
                    d = tab.get((q, arm))
                    if not d:
                        eff.append(None); continue
                    eff.append(st.mean([d[r] for r in REPS if r in d]))
            else:
                db, dl = tab.get((q, "A_bare")), tab.get((q, "A_list"))
                if not db or not dl:
                    eff.append(None); continue
                mb = st.mean([db[r] for r in REPS if r in db])
                ml = st.mean([dl[r] for r in REPS if r in dl])
                eff.append(mb - ml)
        return eff

    results = {}

    # ---------------- H1：臂内位置趋势（gen_odds）——每臂各判一次
    h1 = {}
    for arm in ARMS:
        eff = per_q_effect(tabs["d_gen_odds"], "arm", arm)
        th = theta0_of(tabs["d_gen_odds"], arm)
        v, info = decide(eff, th, +1)
        h1[arm] = {"verdict": v, **info}
        eff2 = per_q_effect(tabs["d_h1_recency"], "arm", arm)
        th2 = theta0_of(tabs["d_h1_recency"], arm)
        v2, info2 = decide(eff2, th2, +1)
        h1[arm]["secondary_recency"] = {"verdict": v2, **info2}
    # 臂间半边的可判性（臂与生成长度是否共线）
    lens = {}
    for q in TASKS:
        for arm in ARMS:
            k = (q, arm, 0)
            lens[(q, arm)] = readings.get(k, {}).get("n_gen")
    longer = []
    for q in TASKS:
        lb, ll = lens.get((q, "A_bare")), lens.get((q, "A_list"))
        if lb is None or ll is None:
            continue
        longer.append("A_list" if ll > lb else ("A_bare" if lb > ll else "tie"))
    n_list_longer = sum(1 for x in longer if x == "A_list")
    n_bare_longer = sum(1 for x in longer if x == "A_bare")
    h1["between_arm_identifiable"] = bool(n_list_longer >= 3 and n_bare_longer >= 3)
    h1["length_direction_counts"] = {"A_list_longer": n_list_longer,
                                      "A_bare_longer": n_bare_longer, "ties": longer.count("tie"),
                                      "per_question": longer}
    if h1["between_arm_identifiable"]:
        eff = []
        for q in TASKS:
            if longer and q in TASKS:
                pass
        # 长臂减短臂：逐题取生成长的那一臂
        eff = []
        for i, q in enumerate(TASKS):
            d = longer[i] if i < len(longer) else "tie"
            if d == "tie":
                eff.append(None); continue
            tab = tabs["x_gen_odds"]
            ln, sh = (tab.get((q, "A_list")), tab.get((q, "A_bare")))
            if not ln or not sh:
                eff.append(None); continue
            ml = st.mean([ln[r] for r in REPS if r in ln])
            mb = st.mean([sh[r] for r in REPS if r in sh])
            eff.append((ml - mb) if d == "A_list" else (mb - ml))
        th = theta0_of(tabs["x_gen_odds"])
        v, info = decide(eff, th, +1)
        h1["between_arm"] = {"verdict": v, **info}
    else:
        h1["between_arm"] = {"verdict": "未测",
                              "reason": "臂与生成长度共线（%d 题 A_list 更长 / %d 题 A_bare 更长）⇒ 臂间半边不可识别"
                                        % (n_list_longer, n_bare_longer)}
    results["H1"] = h1

    # ---------------- H2：臂间 logit 熵（A_bare − A_list，预测 > 0）
    eff = per_q_effect(tabs["x_logit_ent_raw"], "between")
    th = theta0_of(tabs["x_logit_ent_raw"])
    v, info = decide(eff, th, +1)
    eff_s = per_q_effect(tabs["x_logit_ent_sampled"], "between")
    th_s = theta0_of(tabs["x_logit_ent_sampled"])
    v_s, info_s = decide(eff_s, th_s, +1)
    eff_p = per_q_effect(tabs["d_logit_ent"], "arm", None)
    th_p = theta0_of(tabs["d_logit_ent"])
    v_p, info_p = decide(eff_p, th_p, -1)
    results["H2"] = {"verdict": v, **info,
                     "secondary_sampled_entropy": {"verdict": v_s, **info_s},
                     "secondary_positional": {"verdict": v_p, **info_p}}

    # ---------------- H3：未测（缺「去权威化」臂）
    results["H3"] = {"verdict": "未测",
                     "reason": "F-H3 是【臂间对比型】判决式且要求「去权威化/先独立后汇总」的流程臂；"
                               "本批两臂是输入侧的「有清单/无清单」，与 F-H3 的臂不是同一个 ⇒ 不可识别；"
                               "且 2×θ₀ 只能判【差】不能判【水平】，而「头间是否同质」是水平命题",
                     "deposited_reading": {"x_head_sim": per_q_effect(tabs["x_head_sim"], "arm", None),
                                           "theta0_x_head_sim": theta0_of(tabs["x_head_sim"])},
                     "d_head_sim_secondary": {"verdict": decide(*_decide_args(tabs["d_head_sim"]))}}

    # ---------------- H4：臂内位置趋势（h4_early_late，预测 < 0）
    eff = per_q_effect(tabs["d_h4_idx"], "arm", None)
    th = theta0_of(tabs["d_h4_idx"])
    v, info = decide(eff, th, -1)
    per_arm = {}
    for arm in ARMS:
        e2 = per_q_effect(tabs["d_h4_idx"], "arm", arm)
        t2 = theta0_of(tabs["d_h4_idx"], arm)
        vv, ii = decide(e2, t2, -1)
        per_arm[arm] = {"verdict": vv, **ii}
    eff_b = per_q_effect(tabs["x_h4_idx"], "between")   # A_bare − A_list，预测 > 0（A_list 更负）
    th_b = theta0_of(tabs["x_h4_idx"])
    v_b, info_b = decide(eff_b, th_b, +1)
    results["H4"] = {"verdict": v, **info, "per_arm": per_arm,
                     "secondary_between_arm": {"verdict": v_b, **info_b}}

    # ---------------- H5：未测
    results["H5"] = {"verdict": "未测",
                     "reason": "缺矛盾判官（判不出 P5a 的方向性）＋ 缺删除反事实重生成 ⇒ "
                               "F-H5 的两个必要条件（矛盾方向性 + 删除反事实）本批一个都跑不了"}

    # ---------------- H6：清单吸住注意力（D6 = 清单每 token 质量 − 题面每 token 质量，预测 > 0）
    eff = per_q_effect(tabs["d_d6"], "arm", "A_list")
    th = theta0_of(tabs["d_d6"], "A_list")
    v, info = decide(eff, th, +1)
    eff_ph = per_q_effect(tabs["d_d6_placebo"], "arm", "A_list")
    th_ph = theta0_of(tabs["d_d6_placebo"], "A_list")
    v_ph, info_ph = decide(eff_ph, th_ph, +1)
    # 负对照门：|placebo| >= |effect| ⇒ 降级为不可分辨
    med_e = info.get("effect_median")
    med_ph = info_ph.get("effect_median")
    placebo_guard = ""
    if med_e is not None and med_ph is not None and abs(med_ph) >= abs(med_e):
        placebo_guard = "负对照（题面前半 vs 后半的每 token 质量差）中位 |%.6g| ≥ 效应 |%.6g| ⇒ 位置梯度可解释该效应 ⇒ 降级为不可分辨" % (abs(med_ph), abs(med_e))
        if v == "成立":
            v = "不可分辨"
    results["H6"] = {"verdict": v, **info,
                     "negative_control": {"verdict": v_ph, **info_ph, "guard": placebo_guard}}

    # ---------------- H7：不适用
    results["H7"] = {"verdict": "不适用",
                     "reason": "H7 是流程层量（掉零位置 vs 预算/轮数）；本批是单轮单次生成，"
                               "没有轮数/预算轴 ⇒ 量纲不存在"}

    # ---------------- 汇总数据
    aux = {}
    for n in NAMES:
        t = tabs[n]
        aux[n] = {"per_question_arm_mean": {q: {arm: (st.mean([t[(q, arm)][r] for r in REPS if r in t[(q, arm)]])
                                                  if t.get((q, arm)) else None) for arm in ARMS} for q in TASKS},
                  "theta0": theta0_of(t),
                  "theta0_by_arm": {arm: theta0_of(t, arm) for arm in ARMS}}
    # 跨 rep 文本层辅助（2-gram Jaccard）——★ 只落盘、不在本批判决（边界：文本层归②/③组）
    aux_text = {}
    for q in TASKS:
        for arm in ARMS:
            texts = []
            for r in REPS:
                k = (q, arm, r)
                if k in best and best[k].get("status") == "ok":
                    texts.append((r, best[k].get("gen_text", "")))
            js = []
            for i in range(len(texts)):
                for j in range(i + 1, len(texts)):
                    js.append(jaccard_2gram(texts[i][1], texts[j][1]))
            if js:
                aux_text["%s|%s" % (q, arm)] = round(sum(js) / len(js), 6)

    out = {
        "run_id": "T-L1-01-2026-10-26",
        "n_units_total_planned": 54,
        "n_units_ok": n_ok,
        "n_units_failed": len(fail_reasons),
        "failure_reasons": fail_reasons,
        "n_records_read": len(units),
        "verdicts": results,
        "aux_readings": aux,
        "aux_text_cross_rep_2gram_jaccard": aux_text,
        "note": "判决词 = 机制侧相容性（内部侧），不是 H1–H7 成立与否；后者需②/③组文本层读数",
    }
    with open(a.out_json, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    with open(a.out_tsv, "w", encoding="utf-8") as f:
        f.write("H\tverdict\teffect_median\ttheta0\tline_2theta0\tn_q\tn_same_sign\tsign_p\n")
        for h in ["H1", "H2", "H3", "H4", "H5", "H6", "H7"]:
            r = results[h]
            f.write("%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" % (
                h, r.get("verdict"), r.get("effect_median"), r.get("theta0"),
                r.get("decision_line_2theta0"), r.get("n_questions"),
                r.get("n_same_sign"), r.get("sign_test_p_one_sided")))
    print("→ %s / %s" % (a.out_json, a.out_tsv))
    print("单元：计划 54 / 成功 %d / 失败 %d" % (n_ok, len(fail_reasons)))
    for h in ["H1", "H2", "H3", "H4", "H5", "H6", "H7"]:
        r = results[h]
        print("  %-3s %-8s effect=%s θ₀=%s line=%s" % (
            h, r.get("verdict"), _fmt(r.get("effect_median")), _fmt(r.get("theta0")),
            _fmt(r.get("decision_line_2theta0"))))
    return 0


def _fmt(x):
    if x is None:
        return "—"
    if isinstance(x, float):
        return "%.6g" % x
    return str(x)


def _decide_args(tab):
    eff = []
    for q in TASKS:
        vals = []
        for arm in ARMS:
            d = tab.get((q, arm))
            if d:
                vals.append(st.mean([d[r] for r in REPS if r in d]))
        eff.append(st.mean(vals) if vals else None)
    return eff, theta0_of(tab), -1


def jaccard_2gram(a, b):
    def grams(s):
        toks = [t for t in s.replace("\n", " ").split() if t]
        return set(tuple(toks[i:i + 2]) for i in range(len(toks) - 1))
    ga, gb = grams(a), grams(b)
    if not ga and not gb:
        return 1.0
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


if __name__ == "__main__":
    sys.exit(main())
