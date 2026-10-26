#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l0/run_l0.py —— L0 Agent 的跑批器

★ 跑什么：★ 9 道规则应用题（D01–D09）× 两个臂
  · **展开臂**（expand）：ProblemSpaceAgent **自己**造 M → 逐角度走路径 → 自己算边际利用率 → 自己决定停
  · **塌缩臂**（direct）：一次直调（★ 不给清单、★ 不分轮 ★）
⇒ ★ 两者比的是「★ G→M 这一步值多少 ★」，★ 不是"谁写得好" ★

★ 落盘：JSONL（★ 原子写 ★），每行带 run_id / task_id / arm / n / 失败数
★ 断点续跑：★ 已完成的 (task_id, arm) 不重跑
★ 覆盖量：**粗口径**（★ 关键 token 命中率 ★）⇒ ★ 明确标注、★ 待判官复核 ★
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm import LLM, atomic_write_jsonl          # noqa: E402
from agent import ProblemSpaceAgent, DIRECT_M, EXTRACT_C, norm_key  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DEVSET = os.path.join(REPO, "来源与底稿", "第三组_治塌缩层3", "cmp8repo",
                       "repro", "devset", "devset.json")
OUT = os.path.join(HERE, "runs")

TOKEN_RE = re.compile(r"[0-9A-Za-z]+|[一-鿿]{2,}")
STOP = set("的了是在和与及对为以之其该并或不成立正确说法哪些判断如下".split())


def key_tokens(text):
    """★ 从一句话里抽关键 token（★ 中文按 2-gram 滑窗、★ 数字/英文整段 ★）"""
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
    """★ 粗覆盖：★ 金标 C_i 的关键 token 有多少出现在 Agent 的结论集里 ★

    ★ ★ 这是【粗口径】★★ ⇒ ① 有假阳性（token 命中但语义不同）② 有假阴性（换了措辞）
    ⇒ ★ 只能用来做【臂间比较的量级参照】、★ 不可当精确读数引用 ★
    ★ 精确版要判官（★ 那是下一步 ★）
    """
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


def parse_json(txt):
    try:
        return json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
    except Exception:                                   # noqa: BLE001
        return {}


def run_direct(llm, goal):
    """★ 塌缩臂：★ 一次直调 + 抽结论 ★"""
    txt, ok = llm.chat(DIRECT_M.format(goal=goal), max_tokens=6000)
    if not ok:
        return {"claims": [], "n_claims": 0, "ok": False}
    e, ok2 = llm.chat(EXTRACT_C.format(text=txt), max_tokens=3000)
    claims = parse_json(e).get("claims", []) if ok2 else []
    return {"claims": claims, "n_claims": len(claims), "ok": ok2}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="l0-v1-001")
    ap.add_argument("--limit", type=int, default=0, help="0 = 全部 9 题")
    ap.add_argument("--arms", default="expand,direct")
    a = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    out_path = os.path.join(OUT, "units_%s.jsonl" % a.run_id)

    dev = json.load(open(DEVSET, encoding="utf-8"))
    tasks = dev["tasks"]
    if a.limit:
        tasks = tasks[: a.limit]

    done = set()
    if os.path.exists(out_path):
        for line in open(out_path, encoding="utf-8"):
            try:
                r = json.loads(line)
                done.add((r["task_id"], r["arm"]))
            except Exception:                           # noqa: BLE001
                pass

    llm = LLM()
    rows = []
    if os.path.exists(out_path):
        rows = [json.loads(l) for l in open(out_path, encoding="utf-8") if l.strip()]

    arms = [x for x in a.arms.split(",") if x]
    t0 = time.time()
    for t in tasks:
        tid = t["task_id"]
        goal = "题目：%s\n问题：%s" % (t["title"], t["ask"])
        gold = json.loads(t["conclusion_space"]) if isinstance(t["conclusion_space"], str) \
            else t["conclusion_space"]

        if "expand" in arms and (tid, "expand") not in done:
            ag = ProblemSpaceAgent(llm, goal)
            ag.build_representation()
            ag.explore()
            rep = ag.report()
            cov = coarse_cover(gold, rep["claims"])
            rows.append({
                "run_id": a.run_id, "task_id": tid, "arm": "expand",
                "model": llm.model, "temperature": llm.temperature,
                "n_angles": rep["n_angles"], "n_claims": rep["n_claims"],
                "claims": rep["claims"], "representation_M": rep["representation_M"],
                "trail": rep["trail"], "diagnostics": rep["diagnostics"],
                "stopped_reason": rep["stopped_reason"],
                "self_reported_no_new_dimension": rep["self_reported_no_new_dimension"],
                "cover_coarse": cov, "cover_note": "★ 粗口径、★ 阈值 0.6、★ 待判官复核 ★",
            })
            atomic_write_jsonl(out_path, rows)
            print("   ✔ %s expand | 角度 %d | 结论 %d | 粗覆盖 %d/%d"
                  % (tid, rep["n_angles"], rep["n_claims"], cov["n_hit"], cov["n_gold"]))

        if "direct" in arms and (tid, "direct") not in done:
            d = run_direct(llm, goal)
            cov = coarse_cover(gold, d["claims"])
            rows.append({
                "run_id": a.run_id, "task_id": tid, "arm": "direct",
                "model": llm.model, "temperature": llm.temperature,
                "n_claims": d["n_claims"], "claims": d["claims"],
                "cover_coarse": cov, "cover_note": "★ 粗口径、★ 阈值 0.6、★ 待判官复核 ★",
            })
            atomic_write_jsonl(out_path, rows)
            print("   ✔ %s direct  | 结论 %d | 粗覆盖 %d/%d"
                  % (tid, d["n_claims"], cov["n_hit"], cov["n_gold"]))

    print("\n── 调用统计 ──")
    print("   %s" % json.dumps(llm.stats(), ensure_ascii=False)[:400])
    print("   耗时 %.1f 秒" % (time.time() - t0))
    print("   落盘: %s（%d 行）" % (out_path, len(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
