#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""judge_scatter2.py —— T-AGENT-SCATTER-2 · 判官阶段（★ 复用层3 的尺子、★ 不改判据本体 ★）

★ 尺子来源（★ 逐字复用、★ 不新造判官 ★）：
  `来源与底稿/第三组_治塌缩层3/cmp8repo/repro/src/judge/measure.py`（`MEAS_VERSION = U1-measure-v2-2026-10-22+singleattempt+par`）
  `.../repro/src/judge/u1_lib.py`（`MiniMaxLLM`、判官模型 `MiniMax-M3.1-Flash-Preview`）
  `.../repro/src/space.py`（`path_diversity` = ★ 分支间 Self-Sim、★ 出处 NAACL 2025 ★）
  `.../repro/src/metrics_priorart.py`（`self_sim`）
★ 判官侧拿：题面 ＋ 依据包 ＋ 结论空间 `C_t`（★ ＝「核验/裁决侧」★）
★ 被测侧（答题阶段）只拿题面 ⇒ **依据包没进被测臂**（★ devset 规格 §3.5 ★）

★ 输出：judged.jsonl（★ 每行一份答案的判官结果 ★；★ 可续跑 ★）
"""

import argparse
import json
import os
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, "/workspace/work/l3/src")          # ★ 尺子路径（★ 仓内为 repro/src ★）

import measure as M                                    # noqa: E402
import space as SP                                     # noqa: E402
import u1_lib as U                                     # noqa: E402
from llm2 import atomic_write_jsonl                    # noqa: E402

JUDGE_MODEL = os.environ.get("SC2_JUDGE_MODEL", "MiniMax-M2.5")


def ev_items(task):
    """★ 逐字复制层3 `run_dev.py:76` ★"""
    return [{"id": e["id"], "text": e["text"]} for e in task.get("evidence") or []]


def ct_text(task):
    """★ 逐字复制层3 `run_dev.py:80`（★ 编号即结论编号 ★）★"""
    cs = task.get("conclusion_space") or []
    return "\n".join("%d. [%s] %s" % (i + 1, c.get("id", ""), c.get("text", ""))
                     for i, c in enumerate(cs))


def dims_from_cards(cards):
    """★ 逐字复制层3 `run_dev.py:136`（★ 承重维度数＝去冗余后的不同结论族数 ★）★"""
    fams = set()
    for c in cards:
        if c.get("load_bearing") and c.get("verify_status") == "supported" \
                and c.get("supports_conclusions"):
            fams.add("|".join(sorted(c["supports_conclusions"])))
    return fams


def bullet_claims(text):
    """★ 零判官口径的「条目行」（★ 层3 判官也是从这些行抽断言 ★）★"""
    out = []
    for ln in (text or "").splitlines():
        s = ln.strip()
        if s.startswith("-"):
            s = s.lstrip("-*").strip()
            if s:
                out.append(s)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--devset", default="/workspace/work/devset/devset.json")
    ap.add_argument("--max-workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--fast", action="store_true", help="★ 只换传输层（关 thinking）、★ 判据本体不动 ★")
    a = ap.parse_args()

    dev = json.load(open(a.devset, encoding="utf-8"))
    tasks = {t["task_id"]: t for t in dev["tasks"]}

    rows = []
    if os.path.exists(a.out):
        for line in open(a.out, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:                # noqa: BLE001
                    pass
    # ★ 只把【判成功】的行算作已判 ⇒ ★ 判失败的行下次会被重判（★ 否则失败被固化 ★）
    seen = {(r["arm"], r["task_id"], r["rep"], r["route"]): r for r in rows if r.get("ok")}
    rows = list(seen.values())

    answers = []
    for line in open(a.answers, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            answers.append(json.loads(line))
        except Exception:                        # noqa: BLE001
            pass
    todo = [r for r in answers if (r["arm"], r["task_id"], r["rep"], r["route"]) not in seen]
    # ★ 排序：★ 先 rep、再臂、★ 后题 ⇒ ★ 额度不够时【先保住完整的 rep】（★ θ₀ 至少要 2 个 rep ★）
    todo.sort(key=lambda r: (r["rep"], r["arm"], r["task_id"], r["route"]))
    if a.limit:
        todo = todo[:a.limit]
    print("[judge] 待判 %d 份（已判 %d）| judge_model=%s" % (len(todo), len(rows), JUDGE_MODEL), flush=True)

    if a.fast:
        from fast_judge_llm import FastJudgeLLM
        llm = FastJudgeLLM(model=JUDGE_MODEL)
        print("[judge] 传输层＝FastJudgeLLM（★ thinking disabled、★ 判据本体＝层3 measure.py 未动 ★）", flush=True)
    else:
        llm = U.MiniMaxLLM()
    lock = threading.Lock()
    t0 = time.time()

    def judge_one(ans):
        task = tasks[ans["task_id"]]
        aid = "%s/%s/rep%d#%d" % (ans["arm"], ans["task_id"], ans["rep"], ans["route"])
        rec = {"arm": ans["arm"], "task_id": ans["task_id"], "rep": ans["rep"],
               "route": ans["route"], "model": ans.get("model"), "answer_id": aid,
               "judge_model": JUDGE_MODEL, "measure_version": M.MEAS_VERSION,
               "n_chars": ans.get("n_chars", 0), "n_bullets": ans.get("n_bullets", 0),
               "bullets": bullet_claims(ans.get("text", "")),
               "D": 0, "covered": [], "dims": [], "n_cards": 0,
               "n_load_bearing": 0, "parsefail_rate": None,
               "verdicts": {}, "ok": False, "err": None}
        if not ans.get("ok"):
            rec["err"] = "answer_failed:%s" % ans.get("fail_reason")
            return rec
        try:
            claims = M.extract_claims(llm, ans.get("text", ""), model=JUDGE_MODEL)
            res = M.measure_answer(llm, task["ask"], ev_items(task), ct_text(task),
                                   ans.get("text", ""), aid, claims=claims,
                                   judge_model=JUDGE_MODEL)
        except Exception as e:                   # noqa: BLE001
            rec["err"] = "%s: %s" % (type(e).__name__, str(e)[:160])
            return rec
        cards = []
        for i, c in enumerate(res.get("cards_all") or []):
            v = c.get("verdict")
            st = {"支持": "supported", "矛盾": "contradicted",
                  "未提及": "unmentioned", "非主张": "unverifiable"}.get(v, "unverifiable")
            cards.append(dict(card_id="%s#%d" % (aid, i), claim=c.get("claim"),
                              verify_status=st, verdict=v,
                              load_bearing=bool(c.get("load_bearing")),
                              supports_conclusions=["C%d" % int(x) for x in (c.get("supports_conclusions") or [])]))
        cov = sorted({int(x) for x in (res.get("conclusions_supported") or [])})
        rec.update(D=int(res.get("D") or 0), covered=["C%d" % x for x in cov],
                   dims=sorted(dims_from_cards(cards)),
                   n_cards=int(res.get("n_cards") or 0),
                   n_load_bearing=int(res.get("n_load_bearing_cards") or 0),
                   parsefail_rate=res.get("parsefail_rate"),
                   verdicts=dict(Counter(c["verdict"] for c in cards)),
                   cards=cards, ok=True)
        return rec

    done = 0
    with ThreadPoolExecutor(max_workers=a.max_workers) as ex:
        for rec in ex.map(judge_one, todo):
            with lock:
                rows.append(rec)
                seen[(rec["arm"], rec["task_id"], rec["rep"], rec["route"])] = rec
            done += 1
            if done % 10 == 0:
                atomic_write_jsonl(a.out, rows)
                print("[judge %5.1fs] %d/%d" % (time.time() - t0, done, len(todo)), flush=True)
    atomic_write_jsonl(a.out, rows)
    bad = sum(1 for r in rows if not r.get("ok"))
    print("[judge done] 共 %d 份、失败/异常 %d、elapsed=%.1fs" % (len(rows), bad, time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
