#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""层3 的**自动验证流水线**（下午出结果用）

> 2026-10-24 ｜ 流程：等并行训练 → 合并权重 → 造两个对照策略 → 三策略并行验证
>   → 出「钻牛角尖率 / 路径间Sim / 承重维度」三策略对照表

★ 三个策略（**只差策略，代码/题/预算全同**）：
  · `merged`  = 学出来的（多进程并行训练 + 权重平均）
  · `lookup`  = 查表策略（`ActionPolicy.from_lookup()` ⇒ 人手写的映射 ⇒ 层2 的"设计"）
  · `uniform` = 均匀策略（w=0 ⇒ 未训练基线）
⇒ ⇒ 这三者构成"**学出来的 vs 人设计的 vs 随机的**"三层对照。
"""
from __future__ import annotations

import glob
import json
import os
import statistics
import subprocess
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

DEV = os.path.join(HERE, "..", "DEV")
ADV = os.path.join(DEV, "DEV-ADV-2026-10-24.json")
RUNS = os.path.join(HERE, "runs")
POLICY_SRC_GLOB = "runs/pl_202611*"


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)


def wait_trainings(max_wait=5400):
    t0 = time.time()
    while time.time() - t0 < max_wait:
        # ★ 2026-10-24 修：只等**本轮**训练（--out runs/pl_*），
        #   不要把 holdout13 重训算进来（否则永远等不到 0 ⇒ 流水线卡死）
        # ★★ 2026-10-24 再修：**用 ^python3 锚定** ⇒ 不匹配轮询命令自身
        #   （上一版 'train_policy_w.py.*--out runs/pl_' 会被 pgrep 自己的 shell 命中 ⇒ 永远等不到 0）
        n = sh("pgrep -c -f '^python3 .*train_policy_w.py.*--out runs/pl_'").stdout.strip()
        if n in ("0", ""):
            print("[1/5] 训练全部结束", flush=True)
            return True
        print("[1/5] 还在训练（%s 个进程），已等 %.0f 分钟" % (n, (time.time() - t0) / 60), flush=True)
        time.sleep(60)
    print("[1/5] ★ 等超时，继续用已有 checkpoint", flush=True)
    return False


def merge():
    ps = sorted(glob.glob(POLICY_SRC_GLOB))
    ps = [os.path.join(p, "policy.json") for p in ps]
    ps = [p for p in ps if os.path.exists(p)]
    out = os.path.join(RUNS, "policy_merged.json")
    r = sh("python3 -B merge_policies.py %s --out %s"
           % (" ".join('"%s"' % os.path.dirname(p) for p in ps), out))
    print(r.stdout or r.stderr, flush=True)
    return out


def make_baselines():
    import workflow as W
    for name, pol in (("lookup", W.ActionPolicy.from_lookup()),
                       ("uniform", W.ActionPolicy())):
        p = os.path.join(RUNS, "policy_%s.json" % name)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(dict(policy=pol.export(), meta=dict(kind=name)), f,
                      ensure_ascii=False, indent=2)
        print("  造策略 %-8s → %s" % (name, p), flush=True)


def run_validations():
    procs = []
    for v in ("merged", "lookup", "uniform"):
        out = os.path.join(RUNS, "valid_%s" % v)
        cmd = ("python3 -B -u run_dev.py --devset %s --tasks 6 --reps 1 --slots 3 "
               "--rounds 2 --arms B0_direct,B0_bestof3,W_train_L3 --action-mode policy "
               "--policy-file %s --judge minimax --judge-model MiniMax-M2.5 --out %s"
               % (ADV, os.path.join(RUNS, "policy_%s.json" % v), out))
        log = open(os.path.join(HERE, "valid_%s.log" % v), "w", encoding="utf-8")
        procs.append((v, subprocess.Popen(cmd, shell=True, stdout=log, stderr=subprocess.STDOUT)))
        print("  验证 %-8s pid=%s" % (v, procs[-1][1].pid), flush=True)
    for v, p in procs:
        p.wait()
        print("  验证 %-8s 结束（%s）" % (v, p.returncode), flush=True)


def compare():
    import premature_closure as PC
    import space as SP
    tasks = {t["task_id"]: t for t in PC.load_tasks(ADV)}
    table = {}
    for v in ("merged", "lookup", "uniform"):
        f = os.path.join(RUNS, "valid_%s" % v, "arms.jsonl")
        if not os.path.exists(f):
            continue
        rows = [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]
        for r in rows:
            key = (r.get("arm"), v)
            pc = r.get("pc") or {}
            table.setdefault(key, []).append(dict(
                dims=r.get("n_dims"), trap=bool(pc.get("hit")),
                n_cards=r.get("n_cards"),
                paths=r.get("paths") or []))
    print()
    print("=" * 92)
    print("★ 层3 三策略对照（对抗题集 6 题 × R=1）")
    print("=" * 92)
    print("  %-13s %-9s %10s %14s %12s" % ("臂", "策略", "承重维度", "钻牛角尖率", "路径间Sim"))
    for arm in ("B0_direct", "B0_bestof3", "W_train_L3"):
        for v in ("merged", "lookup", "uniform"):
            rs = table.get((arm, v))
            if not rs:
                continue
            dims = [x["dims"] for x in rs if x["dims"] is not None]
            tr = [x["trap"] for x in rs]
            sims = []
            for x in rs:
                ps = [p for p in x["paths"] if p.get("claims")]
                if len(ps) >= 2:
                    s = SP.MP.self_sim([list(p["claims"]) for p in ps], mode="bigram") or 0.0
                    sims.append(s)
            print("  %-13s %-9s %10.2f %14s %12s" % (
                arm, v,
                statistics.median(dims) if dims else 0,
                ("%d/%d" % (sum(tr), len(tr))) if tr else "—",
                ("%.3f" % statistics.median(sims)) if sims else "—"))
    print()
    print("  ★ 判读：**W_train_L3 的钻牛角尖率若在 merged 下最低** ⇒ 学出来的策略真的更会避开陷阱")
    print("    ⇒ 若三者持平 ⇒ 学习**没有**带来效果（如实写）")


if __name__ == "__main__":
    wait_trainings()
    print("[2/5] 合并权重…", flush=True)
    merge()
    print("[3/5] 造对照策略…", flush=True)
    make_baselines()
    print("[4/5] 三策略并行验证…", flush=True)
    run_validations()
    print("[5/5] 出对照表", flush=True)
    compare()
