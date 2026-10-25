#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第四组 · v4 分析：全部主读数**零判官**（候选行为由代码从正文逐字抽取）。

读数清单（对照 PREREG_v4.md）：
  H1 候选集合成功率   = align>0.5 的候选数 / K
  H2 承诺兑现率       = 被选候选中「该写透实体」的命中率（deep_hit_rate）
  H3 状态化打分命中率 = 被选候选的 align（状态化选择器）
     通用打分命中率   = 被选候选的 align（通用选择器，同一批候选）
  H4 违禁率           = 被选候选命中的 forbidden 实体比例
  ★ 选择差距          = align(state选) − align(generic选)  ← **同一批候选内部**比较
  ★ R_takeoff         = 产出中出现"明确回避取舍对象"表述的比例（零判官取证）
  诊断：候选多样性（两两相似度）、候选长度、失败率
"""
import argparse
import json
import os
import re
import statistics as stx
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
import sys
sys.path.insert(0, HERE)
import workflow_arch4 as WA4          # noqa: E402

NEG_MARKERS = WA4.NEG_MARKERS


def takeoff_statements(text, forbidden):
    """★ 产出里"明确回避某个取舍对象"的表述（零判官）。
    判据：实体属于 forbidden 集，在正文中出现，且前 14 字窗口含否定标记。"""
    t = text or ""
    hits = []
    for e in (forbidden or []):
        for m in WA4._entity_mentions(t, e):
            if m["negated"]:
                hits.append(e)
                break
    return sorted(set(hits))


# ★★ 状态无关的"取舍声明"抽取（措辞级存在性判断）
# ⚠️ 判据**不看状态**：只问"这段话有没有明确声明放弃某件事"。
# ⚠️ 存在性判断用措辞是合理的（连续相似度才不行）；
#    但**抽取器必须先证明自己能抓到东西** ⇒ 抽样人工核验（见 build_takeoff_samples.py）
# ★★ 状态无关的"取舍声明"抽取（措辞级**存在性**判断）
# ⚠️ 判据**不看状态**：只问"这段话有没有明确声明**放弃文章层面的某件事**"。
# ⚠️ 收紧要点（第一版有假阳性：把"以避免加重课业负担"当成取舍声明）：
#    ① "以免/避免"必须**紧跟**失焦类词（失焦/冲淡/发散/散掉/跑题）才算；
#    ② 删掉裸"其他/其余…方面"（太常见）；
#    ③ 保留"不再展开/铺开/讨论/赘述/重复/细分/一一/逐项"、
#       "只保留/只写/只讲…"、"放弃这…"、"就此收束/收束到/点到为止"、
#       "不铺开/不一一罗列/其余不写"等**指向文章取舍**的说法。
TAKEOFF_PAT = re.compile(
    r"不再(?:展开|铺开|讨论|谈|赘述|重复|细分|一一|逐项|面面俱到|另述|另议)|"
    r"本文不(?:再)?(?:展开|讨论|赘述|铺开|细说|一一)|"
    r"(?:不再|不予|暂不|暂且不)(?:展开|铺开|讨论|赘述|重复|细分|另述|另议)|"
    r"收束到|(?:就此|于是|这里)收束|点到为止|不再铺陈|"
    r"只(?:保留|留下|写|讲|谈|说|取)(?:其中|一条|一点|一层|一个|一种|一个原则|一个方向)|"
    r"放弃(?:了)?(?:这[一几][个些]点?|该项|此项|该项内容)|"
    r"以免(?:文章|全文|论述)?(?:失焦|冲淡|发散|散掉|跑题|喧宾夺主|题不符)|"
    r"避免(?:文章|全文|论述)?(?:失焦|冲淡|发散|散掉|跑题|喧宾夺主)|"
    r"为免(?:文章|全文|论述)?(?:失焦|冲淡|发散|散掉)|"
    r"不(?:再)?(?:一一|逐项|全部|逐一)铺(?:开|陈|列)|"
    r"(?:其余|其他|另外)(?:的)?(?:部分|内容|问题|方面|几个问题)(?:就)?不(?:再)?(?:写|谈|论|展开)?|"
    r"其余(?:问题|内容|部分)(?:暂且)?不(?:再)?(?:展开|讨论|论)|"
    r"不再一一罗列|不铺开|不逐项|不予展开")


def takeoff_statements_indep(text):
    """★★ 状态无关的"取舍声明"抽取：返回 (数量, 命中句列表)。
    ⚠️ 判据是**存在性**（文中有没有明确声明放弃某事），不是连续相似度。
    ⚠️ 只用于**探测"工作流是否让模型做出取舍"**；
       与"取舍是否对齐状态"是两件事，后者仍用 takeoff_alignment。"""
    t = text or ""
    hits = []
    for sent in re.split(r"[。！？\n]", t):
        s_ = sent.strip()
        if not s_:
            continue
        if TAKEOFF_PAT.search(s_):
            hits.append(s_[:80])
    return len(hits), hits


def takeoff_alignment(cand_text, st):
    """★★ 取舍结构对齐度（零判官、**非恒真**）。

    候选在正文里明确"回避/放弃"了哪些实体（否定语境标注），
    与状态要求的"放弃集"比对：
      ① 交集率   = |候选回避集 ∩ 状态放弃集| / |状态放弃集|   ← ★ 非恒真：
                    候选**不知道**状态的放弃集是谁，命中只能靠真实取舍
      ② 结构匹配 = 1 - |候选回避数 − 状态要求放弃数| / max(1, 状态要求放弃数)
    ⇒ 两者均只用"候选正文实际写了什么"与"状态要求什么"，
      **不含"候选被告知了什么"** ⇒ 盲态臂上完全干净。
    """
    forb = list(st.forbidden or [])
    all_ents = sorted(set(list(st.deep_entities()) + list(st.drop_entities()) +
                          list(st.must_include or []) + forb))
    cand_av = set(takeoff_statements(cand_text, all_ents))
    if not forb:
        inter = None
    else:
        inter = len(cand_av & set(forb)) / len(forb)
    n_req = len(forb)
    struct = (1.0 - abs(len(cand_av) - n_req) / max(1, n_req)) if n_req else None
    return {"cand_avoid": sorted(cand_av), "inter_rate": inter,
            "struct_match": struct,
            "align": (round((inter or 0.0) * 0.7 + (struct or 0.0) * 0.3, 4)
                      if (inter is not None or struct is not None) else None)}


def deep_hit_rate(cand, st):
    deep = set(st.deep_entities())
    if not deep:
        return None
    return len(set(cand["hit_entities"]) & deep) / len(deep)


def forb_hit_rate(cand, st):
    forb = set(st.forbidden)
    if not forb:
        return None
    return len(set(cand["hit_entities"]) & forb) / len(forb)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inp", default=os.path.join(HERE, "runs", "arch4_compare.jsonl"))
    ap.add_argument("--out", default=os.path.join(HERE, "runs", "arch4_analysis.json"))
    args = ap.parse_args()

    recs = []
    with open(args.inp, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                recs.append(json.loads(ln))
    # 只保留每题最新批次
    by_topic = defaultdict(list)
    for r in recs:
        by_topic[r.get("topic_id", "?")].append(r)
    latest = {}
    for tid, rs in by_topic.items():
        bids = sorted({r.get("batch_id", "") for r in rs})
        latest[tid] = bids[-1] if bids else ""
    recs = [r for r in recs if r.get("batch_id") == latest[r.get("topic_id", "?")]]

    res = {"n_records": len(recs), "batches": latest, "topics": {}}
    # ⚠️ 两个工作流臂都要进 per（blind 臂是 H3 的判决所在）
    wf = [r for r in recs if str(r.get("arm", "")).startswith("WF-v4")]
    other = [r for r in recs if not str(r.get("arm", "")).startswith("WF-v4")]

    # ---------------- 逐样本读数 ----------------
    per = []
    for r in wf:
        if r.get("error"):
            per.append({"topic": r.get("topic_id"), "tag": r.get("tag"),
                        "error": r.get("error")})
            continue
        st = WA4.State4(**{k: v for k, v in (r.get("state") or {}).items()
                           if k in WA4.State4.__dataclass_fields__})
        cands = r.get("candidates") or []
        by_idx = {c["idx"]: c for c in cands}
        ss = {x["idx"]: x for x in (r.get("score_state") or [])}
        gg = {x["idx"]: x for x in (r.get("score_generic") or [])}
        cs, cg = r.get("chosen_state_idx"), r.get("chosen_generic_idx")
        align_state = r.get("chosen_state_align")
        align_generic = r.get("chosen_generic_align")
        # ★ 同批候选内部的"选择差距"（同一池 ⇒ 排除题目与采样方差）
        gap = (align_state - align_generic) if (align_state is not None and
                                                align_generic is not None) else None
        aligns = [ss[i]["score"] for i in ss]
        c_ok = [c for c in cands if not c.get("error") and (c.get("text") or "").strip()]
        item = {
            "topic": r.get("topic_id"), "tag": r.get("tag"), "arm": r.get("arm"),
            "blind": r.get("blind"),
            "n_cand": len(cands), "n_cand_ok": len(c_ok),
            "n_gaps": len(st.gaps), "n_decisions": len(st.decisions),
            "must_include": st.must_include, "forbidden": st.forbidden,
            "aligns_all": aligns,
            "H1_cand_set_success_rate": (sum(1 for a in aligns if a > 0.5) / len(aligns)
                                         if aligns else None),
            "chosen_state_idx": cs, "chosen_generic_idx": cg,
            "same_choice": (cs == cg),
            "align_state": align_state, "align_generic": align_generic,
            "H3_gap_same_pool": gap,
            "H2_deep_hit_rate": (deep_hit_rate(by_idx[cs], st) if cs in by_idx else None),
            "H4_forb_hit_rate": (forb_hit_rate(by_idx[cs], st) if cs in by_idx else None),
            "deep_hit_generic_choice": (deep_hit_rate(by_idx[cg], st)
                                        if cg in by_idx else None),
            "R_takeoff_final": takeoff_statements(r.get("text"), st.forbidden),
            # ★ 状态无关的取舍声明（探索性；措辞级存在性判断）
            "R_takeoff_indep_n": takeoff_statements_indep(r.get("text"))[0],
            "R_takeoff_indep_sents": takeoff_statements_indep(r.get("text"))[1],
            # ★★ 取舍结构对齐度：state 选的 vs generic 选的（同池比较）
            "takeoff_state": (takeoff_alignment(by_idx[cs].get("text"), st)
                              if cs in by_idx else None),
            "takeoff_generic": (takeoff_alignment(by_idx[cg].get("text"), st)
                                if cg in by_idx else None),
            "R_takeoff_cands": {c["idx"]: takeoff_statements(c.get("text"), st.forbidden)
                                for c in cands},
            "cand_sim_mean": (round(sum(r.get("candidate_pair_sim") or [0]) /
                                    max(1, len(r.get("candidate_pair_sim") or [1])), 4)),
            "cand_len": [len(c.get("text") or "") for c in cands],
        }
        per.append(item)
    res["per_sample"] = per

    # ---------------- 汇总 ----------------
    def agg(vals):
        vals = [v for v in vals if v is not None]
        if not vals:
            return {"n": 0}
        return {"n": len(vals), "mean": round(sum(vals) / len(vals), 4),
                "min": round(min(vals), 4), "max": round(max(vals), 4),
                "median": round(stx.median(vals), 4)}

    ok = [p for p in per if "error" not in p]
    res["summary"] = {
        "H1_cand_set_success_rate": agg([p["H1_cand_set_success_rate"] for p in ok]),
        "H2_deep_hit_rate_selected": agg([p["H2_deep_hit_rate"] for p in ok]),
        "H4_forb_hit_rate_selected": agg([p["H4_forb_hit_rate"] for p in ok]),
        "align_state_selected": agg([p["align_state"] for p in ok]),
        "align_generic_selected": agg([p["align_generic"] for p in ok]),
        "H3_gap_same_pool": agg([p["H3_gap_same_pool"] for p in ok]),
        "same_choice_rate": (round(sum(1 for p in ok if p["same_choice"]) / len(ok), 4)
                              if ok else None),
        "cand_sim_mean": agg([p["cand_sim_mean"] for p in ok]),
        "R_takeoff_final_rate": (round(sum(1 for p in ok if p["R_takeoff_final"]) / len(ok), 4)
                                 if ok else None),
        "★H3p_takeoff_align_state": agg([(p["takeoff_state"] or {}).get("align")
                                         for p in ok]),
        "★H3p_takeoff_align_generic": agg([(p["takeoff_generic"] or {}).get("align")
                                           for p in ok]),
        "★H3p_takeoff_gap": agg([((p["takeoff_state"] or {}).get("align") or 0) -
                                 ((p["takeoff_generic"] or {}).get("align") or 0)
                                 for p in ok
                                 if p.get("takeoff_state") and p.get("takeoff_generic")]),
        "★takeoff_inter_rate_state": agg([(p["takeoff_state"] or {}).get("inter_rate")
                                          for p in ok]),
        "n_errors": len([p for p in per if "error" in p]),
    }
    # H3 逐例：state 赢 / generic 赢 / 平
    wins = {"state": 0, "generic": 0, "tie": 0}
    for p in ok:
        g = p["H3_gap_same_pool"]
        if g is None:
            continue
        if g > 1e-9:
            wins["state"] += 1
        elif g < -1e-9:
            wins["generic"] += 1
        else:
            wins["tie"] += 1
    res["summary"]["H3_wins"] = wins

    # ★★ 分臂 H3（预注册补充 3：H3 判决只在 blind 臂内做；给缺口臂只作参考）
    def fisher_2x2(a, b, c, d):
        """双尾 Fisher 精确检验（手算，避免依赖 scipy）。"""
        from math import comb
        n = a + b + c + d
        r1, r2 = a + b, c + d
        c1 = a + c

        def p(x):
            return (comb(r1, x) * comb(r2, c1 - x)) / comb(n, c1)
        obs = p(a)
        lo = max(0, c1 - r2); hi = min(r1, c1)
        return round(sum(p(x) for x in range(lo, hi + 1)
                         if p(x) <= obs * (1 + 1e-9)), 4)

    res["per_arm_H3"] = {}
    for arm in sorted({p_arm.get("arm") for p_arm in recs
                       if p_arm.get("arm", "").startswith("WF-v4")}):
        ps = [p for p in ok if p.get("arm") == arm]
        g = [p["H3_gap_same_pool"] for p in ps if p["H3_gap_same_pool"] is not None]
        w = {"state": 0, "generic": 0, "tie": 0}
        for x in g:
            if x > 1e-9:
                w["state"] += 1
            elif x < -1e-9:
                w["generic"] += 1
            else:
                w["tie"] += 1
        nw = w["state"] + w["generic"]
        res["per_arm_H3"][arm] = {
            "n": len(ps), "gap_mean": (round(sum(g) / len(g), 4) if g else None),
            "wins": w,
            "non_tie_rate": (round(w["state"] / nw, 4) if nw else None),
            "align_state": agg([p["align_state"] for p in ps]),
            "align_generic": agg([p["align_generic"] for p in ps]),
            "H1": agg([p["H1_cand_set_success_rate"] for p in ps]),
            "H4_forb": agg([p["H4_forb_hit_rate"] for p in ps]),
        }
    # 逐题（分析单元=题）
    by_t = defaultdict(list)
    for p in ok:
        by_t[p["topic"]].append(p)
    res["per_topic"] = {}
    for tid, ps in sorted(by_t.items()):
        gaps = [p["H3_gap_same_pool"] for p in ps if p["H3_gap_same_pool"] is not None]
        res["per_topic"][tid] = {
            "n": len(ps),
            "H1": agg([p["H1_cand_set_success_rate"] for p in ps]),
            "align_state": agg([p["align_state"] for p in ps]),
            "align_generic": agg([p["align_generic"] for p in ps]),
            "H3_gap": agg(gaps),
            "same_choice": sum(1 for p in ps if p["same_choice"]),
            "R_takeoff_rate": round(sum(1 for p in ps if p["R_takeoff_final"]) / len(ps), 4),
            "cand_sim_mean": agg([p["cand_sim_mean"] for p in ps]),
        }
    # 其他臂（对照）
    res["other_arms"] = {}
    for arm in sorted({r.get("arm") for r in other}):
        rs = [r for r in other if r.get("arm") == arm]
        res["other_arms"][arm] = {
            "n": len(rs),
            "n_err": sum(1 for r in rs if r.get("error")),
            "len_mean": round(sum(len((r.get("text") or "").strip()) for r in rs) / len(rs), 1),
        }
    # ★★ 按臂汇总：状态无关的取舍声明（探索性读数）
    arm_take = defaultdict(list)
    for r in recs:
        if r.get("error"):
            continue
        arm_take[r.get("arm")].append(takeoff_statements_indep(r.get("text"))[0])
    arm_len = defaultdict(list)
    for r in recs:
        if r.get("error"):
            continue
        arm_len[r.get("arm")].append(len((r.get("text") or "").strip()))
    res["arm_len"] = {k: {"n": len(v), "mean": round(sum(v) / len(v), 1)}
                      for k, v in arm_len.items()}
    res["arm_takeoff_indep"] = {}
    for arm, v in sorted(arm_take.items()):
        res["arm_takeoff_indep"][arm] = {
            "n": len(v), "sum": sum(v), "mean": round(sum(v) / len(v), 4),
            "n_with_any": sum(1 for x in v if x > 0),
            "rate_any": round(sum(1 for x in v if x > 0) / len(v), 4),
            "values": v,
        }
    # Fisher：A 臂"有取舍声明" vs 工作流臂
    at = res["arm_takeoff_indep"]
    if "A" in at:
        a_any = at["A"]["n_with_any"]; a_n = at["A"]["n"]
        for arm in ("WF-v4", "WF-v4-blind"):
            if arm in at:
                b_any = at[arm]["n_with_any"]; b_n = at[arm]["n"]
                res.setdefault("fisher_takeoff", {})[arm] = fisher_2x2(
                    b_any, b_n - b_any, a_any, a_n - a_any)
    # 失败清单（显式）
    res["errors"] = [{"topic": r.get("topic_id"), "tag": r.get("tag"), "arm": r.get("arm"),
                      "error": r.get("error")} for r in recs if r.get("error")]

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)

    # ---------------- 控制台 ----------------
    s = res["summary"]
    print("=" * 72)
    print("v4 分析（零判官）｜ 批次: %s" % latest)
    print("=" * 72)
    print("WF-v4 有效样本 %d ｜ 失败 %d" % (len(ok), s["n_errors"]))
    print("-- H1 候选集合成功率(align>0.5) : %s" % s["H1_cand_set_success_rate"])
    print("-- H2 被选候选 deep 命中率      : %s" % s["H2_deep_hit_rate_selected"])
    print("-- H4 被选候选 forbidden 命中率  : %s" % s["H4_forb_hit_rate_selected"])
    print("-- align(状态化选择)             : %s" % s["align_state_selected"])
    print("-- align(通用选择)               : %s" % s["align_generic_selected"])
    print("-- ★H3 同池选择差距              : %s" % s["H3_gap_same_pool"])
    print("-- ★H3 逐例胜负 state/generic/tie: %s" % s["H3_wins"])
    print("-- 同候选率                      : %s" % s["same_choice_rate"])
    print("-- ★R_takeoff 最终产出含取舍声明 : %s" % s["R_takeoff_final_rate"])
    print("-- ★★H3p 取舍对齐 align(state选)  : %s" % s["★H3p_takeoff_align_state"])
    print("-- ★★H3p 取舍对齐 align(generic选): %s" % s["★H3p_takeoff_align_generic"])
    print("-- ★★H3p 取舍对齐差距（同池）      : %s" % s["★H3p_takeoff_gap"])
    print("-- ★★ 回避集与状态放弃集交集率(state选): %s" % s["★takeoff_inter_rate_state"])
    print("-- 诊断 候选两两相似度均值       : %s" % s["cand_sim_mean"])
    print("-- ★★R_takeoff-indep（状态无关，措辞级，探索性）:")
    for arm, v in res["arm_takeoff_indep"].items():
        print("     %-14s n=%d  有声明=%d (%.0f%%)  均值=%.2f  值=%s" % (
            arm, v["n"], v["n_with_any"], v["rate_any"] * 100, v["mean"], v["values"]))
    print("-- ★★分臂 H3（预注册：判决只在 blind 臂内做）:")
    for arm, v in res["per_arm_H3"].items():
        print("     %-14s n=%d gap均值=%s 胜/负/平=%s 非平率=%s align(state)=%s align(gen)=%s H4=%s" % (
            arm, v["n"], v["gap_mean"], v["wins"], v["non_tie_rate"],
            v["align_state"].get("mean"), v["align_generic"].get("mean"),
            v["H4_forb"].get("mean")))
    if "fisher_takeoff" in res:
        print("-- Fisher（工作流臂有声明 vs A 臂有声明，双尾）: %s" % res["fisher_takeoff"])
    print("-- 对照臂:")
    for k, v in res["other_arms"].items():
        print("     %-8s n=%d err=%d 均长=%s" % (k, v["n"], v["n_err"], v["len_mean"]))
    print("-- 逐题:")
    for tid, v in res["per_topic"].items():
        print("     %-5s n=%d  H1=%s  gap=%s  同选=%d  takeoff=%s" % (
            tid, v["n"], v["H1"].get("mean"), v["H3_gap"].get("mean"),
            v["same_choice"], v["R_takeoff_rate"]))
    print("\n[out] %s" % args.out)


if __name__ == "__main__":
    main()
