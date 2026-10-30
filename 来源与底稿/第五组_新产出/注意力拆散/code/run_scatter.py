#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_scatter.py —— 跑「注意力完全拆散」三臂

★ 纪律（★ 全部来自本项目既有教训 ★）：
1. **失败必须可计数**（总则第 4 条）—— 失败落行、留在分母里、不静默归零
2. **增量落盘 + 断点续跑**（★ 沙箱会杀长跑进程 ★）—— 每完成一个 (arm, rep) 立刻写
3. **每线程一个 LLM 实例**（★ LLM 里有计数器、★ 多线程共享会串 ★）
4. **参数全部显式记录**（★ 模型/温度/思考档/上限/用量/价目表日期 ★）

用法：
  python3 run_scatter.py --arms scatter,shared_frame,multi_sample --reps 20
  python3 run_scatter.py --arms scatter --reps 20      # ★ 断点续跑：已完成的 (arm,rep) 跳过 ★
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

from llm import LLM, atomic_write_jsonl      # noqa: E402
from scatter_arms import ARMS, QUESTION       # noqa: E402

RUNS = os.path.abspath(os.path.join(HERE, "..", "runs"))


def out_path(arm, n):
    return os.path.join(RUNS, "%s_n%d.jsonl" % (arm, n))


def load_done(path):
    """★ 断点续跑：已完成的 (rep) 不重跑 ★"""
    done = set()
    if not os.path.exists(path):
        return done
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:                        # noqa: BLE001
            continue
        if r.get("rep") is not None:
            done.add(r["rep"])
    return done


def run_one_rep(arm_name, rep, goal, n_routes, model, temp, max_tok, effort):
    """★ 一个 (arm, rep) = 一个任务单元（★ 自带一个 LLM 实例 ★）"""
    llm = LLM(model=model, temperature=temp, max_tokens=max_tok, reasoning_effort=effort)
    t0 = time.time()
    rows = ARMS[arm_name](llm, goal, n_routes)
    recs = []
    for r in rows:
        recs.append({
            "i": len(recs),
            "ok": bool(r.get("ok")),
            "text": r.get("text", "") or "",
            "arm": arm_name,
            "rep": rep,
            "route": r.get("route"),
            "angle": r.get("angle", ""),
            "stage": r.get("stage"),
            "chars": len(r.get("text", "") or ""),
        })
    st = llm.stats()
    return rep, recs, {"arm": arm_name, "rep": rep, "secs": round(time.time() - t0, 1),
                       "calls": st["calls"], "failures": st["failures"],
                       "usage": st["usage"], "failure_log": st["failure_log"][:20],
                       "n_answers": sum(1 for x in recs if x["ok"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="scatter,shared_frame,multi_sample")
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--routes", type=int, default=6, help="★ 每 rep 交付几份答案 ★")
    ap.add_argument("--model", default=os.environ.get("MODEL", "MiniMax-M2.5"))
    ap.add_argument("--temp", type=float, default=1.0)
    ap.add_argument("--max-tok", type=int, default=6000)
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--question", default=QUESTION)
    a = ap.parse_args()

    os.makedirs(RUNS, exist_ok=True)
    arms = [x for x in a.arms.split(",") if x]
    jobs = []
    for arm in arms:
        done = load_done(out_path(arm, a.reps))
        for rep in range(a.reps):
            if rep in done:
                continue
            jobs.append((arm, rep))
    if not jobs:
        print("★ 全部已完成、★ 无需重跑")
        return 0
    print("★ 待跑单元 %d 个（臂 %s × rep %d × 路 %d）"
          % (len(jobs), "/".join(arms), a.reps, a.routes), flush=True)

    # ★ 按臂分文件；每臂一个写锁（★ 同一臂的 append 串行 ★）
    rows_by_arm = {arm: [] for arm in arms}
    for arm in arms:
        p = out_path(arm, a.reps)
        if os.path.exists(p):
            rows_by_arm[arm] = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    stats = []

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(run_one_rep, arm, rep, a.question, a.routes,
                           a.model, a.temp, a.max_tok, a.effort): (arm, rep)
                for arm, rep in jobs}
        for fut in as_completed(futs):
            arm, rep = futs[fut]
            try:
                rep, recs, st = fut.result()
            except Exception as e:                # noqa: BLE001
                print("  ✗ %s rep=%s 异常：%s: %s" % (arm, rep, type(e).__name__, str(e)[:80]),
                      flush=True)
                continue
            rows_by_arm[arm].extend(recs)
            stats.append(st)
            okn = sum(1 for x in recs if x["ok"])
            print("  ✓ %-13s rep=%-3d 交付 %d/%d 份  用时 %5.1fs  调用 %2d 失败 %d"
                  % (arm, rep, okn, a.routes, st["secs"], st["calls"], st["failures"]),
                  flush=True)
            # ★ 增量落盘（★ 每完成一个 rep 立刻写 ★）
            rows_by_arm[arm].sort(key=lambda r: (r.get("rep", 0), r.get("route", 0)))
            for i, r in enumerate(rows_by_arm[arm]):
                r["i"] = i
            atomic_write_jsonl(out_path(arm, a.reps), rows_by_arm[arm])

    # ★ 汇总元数据（★ 参数必须显式 ★）
    for arm in arms:
        rows = rows_by_arm[arm]
        ok = [r for r in rows if r["ok"]]
        per_rep = {}
        for r in ok:
            per_rep.setdefault(r["rep"], []).append(r)
        full = [k for k, v in per_rep.items() if len(v) == a.routes]
        u = {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0}
        calls = failures = 0
        for s in stats:
            if s["arm"] != arm:
                continue
            calls += s["calls"]
            failures += s["failures"]
            for k in u:
                u[k] += s["usage"].get(k, 0) or 0
        meta = {"question": a.question, "arm": arm, "reps": a.reps, "routes": a.routes,
                "model": a.model, "temperature": a.temp, "max_tokens": a.max_tok,
                "reasoning_effort": a.effort,
                "rows": len(rows), "ok_rows": len(ok), "fail_rows": len(rows) - len(ok),
                "reps_with_full_N_answers": len(full),
                "reps_total": len(per_rep),
                "calls": calls, "failures": failures, "usage": u,
                "price_table_date": "2026-10-30（MiniMax 订阅侧 $0）"}
        with open(os.path.join(RUNS, "%s_n%d.meta.json" % (arm, a.reps)), "w",
                  encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print("★ %s：%d 行（有效 %d / 失败 %d）｜ 满额 rep %d/%d ｜ 调用 %d 失败 %d"
              % (arm, len(rows), len(ok), len(rows) - len(ok), len(full), len(per_rep),
                 calls, failures), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
