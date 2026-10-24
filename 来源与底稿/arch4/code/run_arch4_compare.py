#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第四组 · v4 主实验：状态进选择层。

★ 三个臂（等预算可比）：
  A        单次直答                          1 次调用
  S-self   等预算自我说明（无状态）          4 次调用
  WF-v4    状态 → K=3 候选 → **两个打分器评估同一批候选** → 各选 1   4 次调用
           ⇒ 一次生成、两次选择 ⇒ 差值**只来自打分器**（不是两次独立采样）
           ⇒ 记录 chosen_state（状态化打分）与 chosen_generic（通用打分）

★ 全部读数零判官（候选的实际行为由代码从正文逐字抽取）。
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import api_any                                            # noqa: E402
import workflow_arch4 as WA4                              # noqa: E402
from run_arch3_compare import (                           # noqa: E402
    step_stance3, step_observe3, step_decide, strip_think, chat)

from run_multitopic import MINIMAL  # ★ 极简题面（不含 audience/genre/dilemma 等装饰）

QUESTION = "你如何看待高考英语作文？写成一篇文章。"
K = WA4.K_CANDIDATES
CAND_LO, CAND_HI = 600, 900


# ---------------------------------------------------------------- 状态构建
def build_state(question):
    """复用 v3 的状态链：立场 → 初稿 → 观测 → 决策（封闭枚举）。"""
    st, raw_s, _ = step_stance3(question)
    brief1 = WA4.render_candidate_prompt(st, CAND_LO, CAND_HI)
    draft = chat([{"role": "user", "content": brief1}], max_tokens=6000)
    draft = strip_think(draft)
    obs, raw_o, o_st = step_observe3(question, draft)
    if not obs:
        obs = {"used": [], "gaps": [], "new_constraints": [], "entities": [],
               "sharpest": "", "_missing": ["*"]}
    gaps = obs.get("gaps") or []
    if not gaps:
        # 观测没给缺口 ⇒ 状态退化为"无取舍"（显式标记）
        return WA4.State4(stance=st.stance, keeps=st.keeps,
                           gaps=[], decisions=[], must_include=[], forbidden=[],
                           excluded=[], step=1), {"obs_status": o_st, "n_gaps": 0}
    decs, raw_d, d_meta = step_decide(question, draft, gaps)
    s4 = WA4.State4(stance=st.stance, keeps=st.keeps, gaps=gaps, decisions=decs,
                    step=1)
    # 代码推导必含/禁含（沿用 v3 口径：深入展开 ⇒ 必含；放弃 ⇒ 禁含）
    gm = {int(g.get("index") or 0): g for g in gaps}
    must, forb = [], []
    for d in sorted(decs, key=lambda x: int(x.get("priority") or 9)):
        g = gm.get(int(d.get("gap_index") or 0)) or {}
        if d.get("depth") == "深入展开":
            for e in (g.get("entities") or []):
                if e not in must:
                    must.append(e)
        elif d.get("depth") == "放弃":
            for e in (g.get("entities") or []):
                if e not in forb:
                    forb.append(e)
    s4.must_include = must[:4]
    s4.forbidden = forb[:5]
    return s4, {"obs_status": o_st, "n_gaps": len(gaps), "n_decisions": len(decs),
                "decisions": decs, "must": s4.must_include, "forbidden": s4.forbidden}


# ---------------------------------------------------------------- 候选生成
def gen_candidates(question, st, k=K, blind=False):
    """生成 K 个候选草稿。★ 同一提示、独立采样 ⇒ 候选之间自然不同。"""
    prompt = WA4.render_candidate_prompt(st, CAND_LO, CAND_HI, blind=blind)
    allowed = st.all_entities()

    def one(i):
        try:
            raw = chat([{"role": "user", "content": prompt}], max_tokens=3000)
            txt = strip_think(raw)
            ok, why = WA4.check_candidate_gate(txt)
            if not ok:
                # 重试一次（长文本步偶发截断/漂移）
                raw = chat([{"role": "user", "content": prompt}], max_tokens=4000)
                txt = strip_think(raw)
                ok, why = WA4.check_candidate_gate(txt)
            hit, missed = WA4.extract_entities(txt, allowed)
            return WA4.Candidate(idx=i, text=txt, hit_entities=hit,
                                 missed_entities=missed,
                                 error=None if ok else "; ".join(why))
        except Exception as e:
            return WA4.Candidate(idx=i, text="", error="%s: %s" % (type(e).__name__, e))

    cands = []
    with ThreadPoolExecutor(max_workers=min(3, k)) as ex:
        futs = {ex.submit(one, i): i for i in range(1, k + 1)}
        for fu in as_completed(futs):
            cands.append(fu.result())
    cands.sort(key=lambda c: c.idx)
    return cands


# ---------------------------------------------------------------- 臂
def run_A4(tag):
    t0 = time.time()
    raw = chat([{"role": "user", "content": QUESTION}], max_tokens=6000)
    txt = strip_think(raw)
    return {"arm": "A", "tag": tag, "text": txt,
            "calls": ["direct"], "elapsed": round(time.time() - t0, 1),
            "error": None if len(txt.strip()) >= 50 else "text_too_short"}


def run_S_self4(tag):
    """等预算自我说明（无状态）：立场 → 初稿 → 转移 → 定稿，4 次调用。"""
    t0 = time.time()
    st, raw_s, _ = step_stance3(QUESTION)
    brief1 = WA4.render_candidate_prompt(st, CAND_LO, CAND_HI)
    draft = strip_think(chat([{"role": "user", "content": brief1}], max_tokens=6000))
    obs, raw_o, _ = step_observe3(QUESTION, draft)
    obs = obs or {"used": [], "gaps": [], "new_constraints": [], "entities": []}
    brief2 = (draft + "\n\n---\n\n请根据上面的观察，写出这一轮的文章正文（%d–%d 字）。"
              % (CAND_LO, CAND_HI))
    final = strip_think(chat([{"role": "user", "content": brief2}], max_tokens=4000))
    return {"arm": "S-self", "tag": tag, "text": final, "draft": draft,
            "calls": ["stance", "draft", "observe", "final"],
            "elapsed": round(time.time() - t0, 1),
            "error": None if len(final.strip()) >= 50 else "text_too_short"}


def run_WF_v4_blind(tag):
    """★ 盲态对照：状态照常构建（观测+决策），但**候选提示不含任何缺口信息**
    ⇒ 候选完全不知道状态化打分依据什么 ⇒ 状态化打分**彻底非恒真**
    ⇒ 这是 H3 的干净读数所在臂，也是"盲从地板"。"""
    return _run_wf(tag, blind=True)


def _run_wf(tag, blind=False):
    """状态 → K 候选 → 两个打分器评估同一批候选 → 各选 1。"""
    t0 = time.time()
    st, meta = build_state(QUESTION)
    cands = gen_candidates(QUESTION, st, blind=blind)
    ok_cands = [c for c in cands if not c.error and (c.text or "").strip()]
    if not ok_cands:
        return {"arm": "WF-v4", "tag": tag, "text": "", "error": "no_valid_candidate",
                "state": st.to_dict(), "candidates": [c.to_dict() for c in cands],
                "meta": meta, "calls": ["stance", "draft", "observe", "decide"] + ["cand"] * K,
                "elapsed": round(time.time() - t0, 1)}
    chosen_state, scored_state = WA4.select(
        ok_cands, lambda c: WA4.score_state_alignment(c, st), state=st)
    # ⚠️ 通用打分**不给 state** ⇒ 它的 tiebreak 为 0 ⇒ 纯通用、不含状态
    chosen_generic, scored_generic = WA4.select(ok_cands, WA4.score_generic, state=None)

    def align(c):
        if c is None:
            return None
        return round(WA4.score_state_alignment(c, st), 4)

    # 候选两两相似度（诊断：候选是否退化）
    from analyze_arch3 import J
    sims = []
    for i in range(len(ok_cands)):
        for j in range(i + 1, len(ok_cands)):
            sims.append(round(J(ok_cands[i].text, ok_cands[j].text), 4))

    rec = {"arm": "WF-v4-blind" if blind else "WF-v4", "tag": tag,
           "blind": blind,
           "text": chosen_state.text if chosen_state else "",
           "state": st.to_dict(), "meta": meta,
           "candidates": [c.to_dict() for c in cands],
           "score_state": scored_state, "score_generic": scored_generic,
           "chosen_state_idx": chosen_state.idx if chosen_state else None,
           "chosen_generic_idx": chosen_generic.idx if chosen_generic else None,
           "chosen_state_align": align(chosen_state),
           "chosen_generic_align": align(chosen_generic),
           "candidate_pair_sim": sims,
           "calls": ["stance", "draft", "observe", "decide"] + ["cand"] * K,
           "elapsed": round(time.time() - t0, 1),
           "error": None}
    if chosen_state is None:
        rec["error"] = "no_state_choice"
    return rec


run_WF_v4 = lambda tag: _run_wf(tag, blind=False)   # 主臂（候选提示含缺口）

DISPATCH = {"A": run_A4, "S-self": run_S_self4, "WF-v4": run_WF_v4,
            "WF-v4-blind": run_WF_v4_blind}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", default="1,2,3")
    ap.add_argument("--arms", default="A,WF-v4,WF-v4-blind")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--out", default=os.path.join(HERE, "runs", "arch4_compare.jsonl"))
    ap.add_argument("--batch-id", default=None)
    ap.add_argument("--append", action="store_true")
    ap.add_argument("--topics", default="G01",
                    help="★ 逗号分隔题号（G01/T06/T07/T10）；每题一批")
    args = ap.parse_args()

    reps = [int(x) for x in args.reps.split(",") if x.strip()]
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    for a in arms:
        assert a in DISPATCH, a
    tids = [x.strip() for x in args.topics.split(",") if x.strip()]
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    out_f = open(args.out, "a" if args.append else "w", encoding="utf-8")
    for tid in tids:
        global QUESTION
        QUESTION = MINIMAL.get(tid, QUESTION)
        batch = args.batch_id or ("arch4-%s-%s" % (tid, time.strftime("%Y%m%d-%H%M%S")))
        print("\n===== %s | batch=%s =====" % (tid, batch), flush=True)
        futs, meta = [], {}
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            for a in arms:
                for s_ in reps:
                    fu = ex.submit(DISPATCH[a], s_)
                    futs.append(fu); meta[fu] = (a, s_)
            for fu in as_completed(futs):
                a, s_ = meta[fu]
                try:
                    r = fu.result()
                except Exception as e:
                    r = {"arm": a, "tag": s_, "text": "",
                         "error": "%s: %s" % (type(e).__name__, e)}
                r["batch_id"] = batch
                r["model"] = "MiniMax-M3"
                r["topic_id"] = tid
                r["question"] = QUESTION
                out_f.write(json.dumps(r, ensure_ascii=False) + "\n"); out_f.flush()
                extra = ""
                if a.startswith("WF-v4"):
                    extra = " | state_pick=%s generic_pick=%s align(state)=%s align(generic)=%s" % (
                        r.get("chosen_state_idx"), r.get("chosen_generic_idx"),
                        r.get("chosen_state_align"), r.get("chosen_generic_align"))
                print("  [%s] %-8s #%s %5d字 %s%s" % (
                    batch, a, s_, len((r.get("text") or "").strip()),
                    ("ERR:" + str(r.get("error"))[:50]) if r.get("error") else "ok", extra),
                    flush=True)
    out_f.close()
    c = api_any.cost_estimate()
    print("[total] 调用 %d 次 ｜ prompt=%d completion=%d"
          % (c["calls"], c["prompt_tokens"], c["completion_tokens"]))


if __name__ == "__main__":
    main()
