#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_scatter.py —— 跑「注意力完全拆散」三臂（★ 路级并发 + 按路落盘 + 去重 ★）

★ 纪律（★ 全部来自本项目既有教训 ★）：
1. **失败必须可计数且看得见**（总则第 4 条）—— 失败落行、带 fail_reason、留在分母里
2. **按路增量落盘 + 断点续跑**（★ 沙箱会杀长跑进程 ★）—— 落盘粒度必须比任务粒度细
3. **每任务一个 LLM 实例**（★ LLM 里有计数器、★ 多线程共享会串 ★）
4. **rep 完成打标记**（★ 断点续跑只认标记、★ 半截 rep 必须重跑 ★）
5. **重复行必须去重**（★ 续跑会重跑半截 rep 的路 ⇒ 同 (rep,route) 会出现多行 ★）
6. **builder 失败 ⇒ 不派路**（★ 否则 6 路全部空跑、★ 失败原因还会被吞掉 ★）

用法：
  python3 run_scatter.py --arms scatter,shared_frame,multi_sample --reps 20 --routes 6 --workers 16
  python3 run_scatter.py --arms direct_m3 --floor-reps 30 --workers 14
  ★ 再跑一次同一命令即可续跑（★ 已完成的 rep 跳过 ★）
"""

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

from llm import LLM, atomic_write_jsonl      # noqa: E402
import scatter_arms as SA                     # noqa: E402

RUNS = os.path.abspath(os.path.join(HERE, "..", "runs_scatter"))   # ★ 与权威尺子的 runs/ 物理隔离 ★
THINK_OFF = os.environ.get("THINK_OFF", "1") == "1"   # ★ 关思考（★ 截断根因 ★）
# ★ direct_m3 另起名 ⇒ 绝不覆盖仓内 M2.5 的 direct_n30.jsonl ★
ARMS = ("scatter", "shared_frame", "multi_sample", "direct_m3")


def out_path(arm, n):
    return os.path.join(RUNS, "%s_n%d.jsonl" % (arm, n))


def angles_path(rep):
    return os.path.join(RUNS, "_shared_angles_rep%d.json" % rep)


def load_rows(path):
    if not os.path.exists(path):
        return []
    rows = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:                            # noqa: BLE001
            continue
    return rows


def dedupe(rows):
    """★ 同 (rep, route) 保留【最后一行】；marker 行单独保留 ★"""
    by = {}
    markers = []
    for r in rows:
        if r.get("marker") == "rep_done":
            markers.append(r)
            continue
        by[(r.get("rep"), r.get("route"))] = r          # ★ 后写覆盖先写 ★
    out = list(by.values()) + markers
    out.sort(key=lambda r: (r.get("rep") if r.get("rep") is not None else -1,
                             r.get("route") if r.get("route") is not None else -1))
    return out


def done_reps(path):
    """★ 只认 rep_done 标记（★ 半截 rep 不算完成 ★）"""
    return {r["rep"] for r in load_rows(path) if r.get("marker") == "rep_done"}


class Store:
    """★ 按臂的文件 + 锁（★ 原子写、★ 增量落盘、★ 去重 ★）"""

    def __init__(self, arm, n):
        self.arm = arm
        self.n = n
        self.path = out_path(arm, n)
        self.lock = threading.Lock()
        self.rows = dedupe(load_rows(self.path))

    def add(self, rec):
        with self.lock:
            key = (rec.get("rep"), rec.get("route"))
            self.rows = [r for r in self.rows
                         if r.get("marker") == "rep_done"
                         or (r.get("rep"), r.get("route")) != key]
            self.rows.append(rec)
            self._flush()

    def mark(self, rep):
        with self.lock:
            self.rows = [r for r in self.rows
                         if not (r.get("marker") == "rep_done" and r.get("rep") == rep)]
            self.rows.append({"arm": self.arm, "rep": rep, "marker": "rep_done",
                              "ok": True, "text": "", "i": 0})
            self._flush()

    def _flush(self):
        for i, r in enumerate(self.rows):
            r["i"] = i
        atomic_write_jsonl(self.path, self.rows)


def run_task(fn, model, temp, max_tok, effort, *extra):
    """★ 一个任务单元 = 一个 LLM 实例（★ 线程安全 ★）

    ★ 预算阶梯：★ 截断 / 空正文 ⇒ ★ 换新实例 + 翻倍 max_tokens 重试（★ 最多 2 级 ★）
    —— 依据：★ MiniMax 的推理 token 会【随机暴涨】⇒ ★ 不重试 ⇒ 截断的答案系统性更短
    ⇒ 【覆盖更低】⇒ ★ 样本被仪器削短 ★
    """
    llm = LLM(model=model, temperature=temp, max_tokens=max_tok,
              reasoning_effort=effort, thinking_disabled=THINK_OFF)
    try:
        rec = fn(llm, *extra)
        st = llm.stats()
        if not rec.get("ok"):
            fl = st.get("failure_log") or []
            reason = fl[-1]["reason"] if fl else "unknown"
            if reason in ("truncated", "empty_after_strip_think"):
                for _ in range(2):
                    llm2 = LLM(model=model, temperature=temp, max_tokens=max_tok * 2,
                               reasoning_effort=effort, thinking_disabled=THINK_OFF)
                    rec2 = fn(llm2, *extra)
                    st2 = llm2.stats()
                    rec, st = rec2, st2
                    max_tok = max_tok * 2
                    if rec.get("ok"):
                        break
        return rec, st, None
    except Exception as e:                            # noqa: BLE001
        st = llm.stats()
        return {"ok": False, "text": "", "angle": "", "route": None, "stage": "except"}, st, \
            "%s: %s" % (type(e).__name__, str(e)[:80])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="scatter,shared_frame,multi_sample,direct_m3")
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--floor-reps", type=int, default=30, help="★ 同参地板 A0 的 rep 数 ★")
    ap.add_argument("--routes", type=int, default=6)
    ap.add_argument("--model", default=os.environ.get("MODEL", "MiniMax-M3"))
    ap.add_argument("--temp", type=float, default=1.0)
    ap.add_argument("--max-tok", type=int, default=12000)
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--question", default=SA.QUESTION)
    a = ap.parse_args()
    os.makedirs(RUNS, exist_ok=True)

    sel = [x for x in a.arms.split(",") if x]
    arms_all = [x for x in ARMS if x in sel]
    nreps = {arm: (a.floor_reps if arm == "direct_m3" else a.reps) for arm in arms_all}
    stores = {arm: Store(arm, nreps[arm]) for arm in arms_all}
    done = {arm: done_reps(out_path(arm, nreps[arm])) for arm in arms_all}
    todo = {arm: [r for r in range(nreps[arm]) if r not in done[arm]] for arm in arms_all}
    n_todo = sum(len(v) for v in todo.values())
    if n_todo == 0:
        print("★ 全部 rep 已完成、★ 无需重跑")
        return 0
    print("★ 待跑：%s ｜ routes=%d workers=%d"
          % (json.dumps(todo, ensure_ascii=False), a.routes, a.workers), flush=True)

    stats = []
    t_start = time.time()

    # ---------------- 阶段 0：A1 的共享 builder（★ 一次性、★ 所有路共用 ★）
    built_ok = set()
    build_jobs = [(arm, rep) for arm in arms_all if arm == "shared_frame"
                  for rep in todo.get(arm, [])]
    if build_jobs:
        print("── 阶段0：A1 共享 builder（%d 次）" % len(build_jobs), flush=True)
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            futs = {}
            for arm, rep in build_jobs:
                futs[ex.submit(run_task, SA.build_shared, a.model, a.temp, a.max_tok,
                               a.effort, a.question, a.routes)] = (arm, rep)
            for fut in as_completed(futs):
                arm, rep = futs[fut]
                rec, st, err = fut.result()
                angles = rec.get("angles") or []
                fl = st.get("failure_log") or []
                reason = fl[-1]["reason"] if fl else "unknown"
                with open(angles_path(rep), "w", encoding="utf-8") as f:
                    json.dump({"rep": rep, "ok": bool(rec.get("ok")) and bool(angles),
                               "angles": angles, "fail_reason": reason}, f,
                              ensure_ascii=False)
                stats.append({"arm": arm + "_build", "calls": st["calls"],
                              "failures": st["failures"], "usage": st["usage"]})
                if angles:
                    built_ok.add(rep)
                else:
                    print("  ✗ A1 builder rep=%d 失败（%s）★ 不派路、★ 留给续跑 ★"
                          % (rep, reason), flush=True)
                print("  ✓ A1 builder rep=%-3d 角度 %d 个  %.0fs"
                      % (rep, len(angles), time.time() - t_start), flush=True)

    # ---------------- 阶段 1：所有路（★ 路级并发 ★）
    jobs = []
    for rep in todo.get("scatter", []):
        for r in range(a.routes):
            jobs.append(("scatter", rep, r, SA.route_scatter))
    for rep in todo.get("multi_sample", []):
        for r in range(a.routes):
            jobs.append(("multi_sample", rep, r, SA.route_sample))
    for rep in todo.get("direct_m3", []):
        jobs.append(("direct_m3", rep, 0, SA.route_direct))
    for rep in todo.get("shared_frame", []):
        if rep not in built_ok:
            print("  ⚠ A1 rep=%d 的 builder 未成功 ⇒ 本轮不派路" % rep, flush=True)
            continue
        for r in range(a.routes):
            jobs.append(("shared_frame", rep, r, SA.route_shared))
    print("── 阶段1：路级任务 %d 个（★ 每完成一路立刻落盘 ★）" % len(jobs), flush=True)

    route_count = {}
    if jobs:
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            futs = {}
            for arm, rep, r, fn in jobs:
                if arm == "scatter":
                    extra = (a.question, a.routes, r)
                elif arm == "direct_m3":
                    extra = (a.question,)
                elif arm == "multi_sample":
                    extra = (a.question, r)
                else:
                    extra = (a.question, r,
                             json.load(open(angles_path(rep), encoding="utf-8")).get("angles", []))
                futs[ex.submit(run_task, fn, a.model, a.temp, a.max_tok, a.effort,
                               *extra)] = (arm, rep, r)
            done_n = 0
            for fut in as_completed(futs):
                arm, rep, r = futs[fut]
                rec, st, err = fut.result()
                rec = dict(rec)
                rec.update({"arm": arm, "rep": rep, "chars": len(rec.get("text", "") or "")})
                if not rec.get("ok"):
                    fl = st.get("failure_log") or []
                    rec["fail_reason"] = (fl[-1]["reason"] if fl else "unknown") + \
                        ((" | " + err) if err else "")
                    rec["fail_calls"] = st.get("calls")
                    print("  ✗ %s rep=%s route=%s 失败：%s"
                          % (arm, rep, r, rec["fail_reason"]), flush=True)
                stats.append({"arm": arm, "calls": st["calls"], "failures": st["failures"],
                              "usage": st["usage"]})
                stores[arm].add(rec)
                key = (arm, rep)
                route_count[key] = route_count.get(key, 0) + 1
                done_n += 1
                if route_count[key] == (1 if arm == "direct_m3" else a.routes):
                    stores[arm].mark(rep)
                if done_n % 20 == 0 or done_n == len(jobs):
                    print("  … %d/%d 路完成（%.0fs）" % (done_n, len(jobs), time.time() - t_start),
                          flush=True)

    # ---------------- 元数据（★ 参数必须显式 ★）
    for arm in arms_all:
        rows = dedupe(stores[arm].rows)
        ok = [r for r in rows if r.get("ok") and r.get("text")]
        per_rep = {}
        for r in ok:
            per_rep.setdefault(r["rep"], []).append(r)
        need = 1 if arm == "direct_m3" else a.routes
        full = [k for k, v in per_rep.items() if len(v) == need]
        u = {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0}
        calls = failures = 0
        for s in stats:
            if not s["arm"].startswith(arm):
                continue
            calls += s["calls"]
            failures += s["failures"]
            for k in u:
                u[k] += s["usage"].get(k, 0) or 0
        meta = {"question": a.question, "arm": arm, "reps": nreps[arm], "routes": need,
                "model": a.model, "temperature": a.temp, "max_tokens": a.max_tok,
                "reasoning_effort": a.effort, "thinking_disabled": THINK_OFF,
                "rows": len(rows), "ok_rows": len(ok),
                "fail_rows": len([r for r in rows if not r.get("ok") and not r.get("marker")]),
                "reps_with_full_N_answers": len(full), "reps_total": len(per_rep),
                "calls": calls, "failures": failures, "usage": u,
                "price_table_date": "2026-10-30（MiniMax 订阅侧 $0 ⇒ 成本轴退化为 token 轴）"}
        with open(os.path.join(RUNS, "%s_n%d.meta.json" % (arm, nreps[arm])), "w",
                  encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print("★ %s：行 %d（有效 %d / 失败 %d）｜满额 rep %d/%d｜调用 %d 失败 %d｜token %s"
              % (arm, len(rows), len(ok), meta["fail_rows"], len(full), len(per_rep),
                 calls, failures, json.dumps(u, ensure_ascii=False)), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
