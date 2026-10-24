#!/usr/bin/env python3
"""**发散层对照**（层2 第二个设计变量）—— 5 臂，每臂只差一个因子。

> 2026-10-24 ｜ 第二组 · 层2 ｜ 落点：`creativity_lab/experiments/divergence_matrix.py`
> 预注册：`docs/cmp8/routes/COLLAPSE/eval/PREREG-DIVERGENCE.md`（**事前**写死因变量与判决规则）
>
> ## 臂（每臂只差一个因子 ⇒ 单因子对照）
> | 臂 | 分支数 | 型号 | 认知框架 | persona |
> |---|--:|---|---|---|
> | `base` | 5 | 跨 5 个活型号 | 5 个（错位） | 5 个（错位） |
> | `same_model` | 5 | **同一型号** | 5 个 | 5 个 |
> | `one_frame` | 5 | 跨 5 个 | **1 个** | 5 个 |
> | `n3` | **3** | 跨 5 个 | 5 个 | 5 个 |
> | `n8` | **8** | 跨 5 个 | 5 个 | 5 个 |
>
> ## ★ 因变量全是**零判官**的
> - **有效秩 `effective_rank`**（embedding PCA 谱参与比）＝ 面分成几块 = **搜索空间的模态数** ★主因变量
> - `modes`（字面模态数）、`spread`（几何宽度）、词面**共享度**（独立性的**下界**）
>
> ★ 口径（预注册里已写死）：**有效秩随 n 单调增** ⇒ 分支数之间**不可比绝对值**
>   ⇒ 主读数用 **有效秩 / n**（单位支的模态贡献），绝对有效秩只作辅读数。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from creativity_lab.arms.dual import _branch_specs          # noqa: E402
from creativity_lab.client import DEFAULT_EFFORT, LLM      # noqa: E402
from creativity_lab.metrics import (branch_diversity, effective_rank,  # noqa: E402
                                    keywords, modes, spread)
from creativity_lab.prompts import BRANCH_ASK, OUT_SPEC     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARMS = {
    "base":       {"n": 5, "same_model": False, "one_frame": False},
    "same_model": {"n": 5, "same_model": True,  "one_frame": False},
    "one_frame":  {"n": 5, "same_model": False, "one_frame": True},
    "n3":         {"n": 3, "same_model": False, "one_frame": False},
    "n8":         {"n": 8, "same_model": False, "one_frame": False},
}
SEED_BASE = 20261024


def lexical_sharing(arts: List[str]) -> float:
    """分支两两 2-gram Jaccard 的**中位数**（越高 = 共用内容越多 = 越不独立）。

    ⚠️ 这是**独立性/差异度的下界**：措辞改写会**低估**重叠 ⇒ 报下界，不报"真独立性"。
    """
    if len(arts) < 2:
        return 0.0
    ks = [keywords(a) for a in arts]
    vals = []
    for i in range(len(ks)):
        for j in range(i + 1, len(ks)):
            u = len(ks[i] | ks[j])
            vals.append((len(ks[i] & ks[j]) / u) if u else 0.0)
    vals.sort()
    return float(vals[len(vals) // 2])


def build_specs(arm: str, alive: List[str]) -> List[tuple]:
    """按臂构造分支扇出（框架 / 型号 / persona 三者错位绑定）。"""
    cfg = ARMS[arm]
    base = _branch_specs()
    n = cfg["n"]
    specs = []
    for i in range(n):
        frame, _m, persona = base[i % len(base)]
        if cfg["one_frame"]:
            frame = base[0][0]                # 全部用第 1 个认知框架
        model = alive[0] if cfg["same_model"] else alive[i % len(alive)]
        specs.append((frame, model, persona))
    return specs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topics", default=None)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--model", default="MiniMax-M3")
    ap.add_argument("--effort", default=DEFAULT_EFFORT)
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--only-tid", default=None, help="只跑这些 tid（逗号分隔）")
    ap.add_argument("--out", default="runs/divergence-matrix-2026-10-24")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()

    from creativity_lab import topics as T
    from creativity_lab.experiments.probe_models import probe
    pr = probe()
    alive = pr["alive"]
    if len(alive) < 5:
        print("⚠️ 活型号不足 5 个：%s" % alive)

    ts = T.load(a.topics or T.DEFAULT_TOPIC_FILE)
    if a.only_tid:
        keep = set(a.only_tid.split(","))
        ts = [t for t in ts if t["tid"] in keep]
    arms = a.arms.split(",")
    out_dir = os.path.join(ROOT, a.out)
    os.makedirs(out_dir, exist_ok=True)
    print("题：%s｜rep=%d｜臂：%s｜effort=%s" % ([t["tid"] for t in ts], a.reps, arms, a.effort))

    llm = LLM()
    emb_llm = LLM()
    groups: List[Dict[str, Any]] = []

    for topic in ts:
        for rep in range(1, a.reps + 1):
            g: Dict[str, Any] = {"tid": topic["tid"], "rep": rep, "arms": {}}
            for arm in arms:
                specs = build_specs(arm, alive)
                prompts = []
                for frame, _m, persona in specs:
                    prompts.append(BRANCH_ASK.format(
                        topic=topic["ask"], frame_name=frame["name"], frame_text=frame["text"],
                        persona=persona, spec=OUT_SPEC,
                        extra="\n直接写出**完整的答复本身**，不要写判断片段。"))
                n0 = len(llm.rec)
                t0 = time.time()
                with ThreadPoolExecutor(max_workers=a.workers) as ex:
                    futs = [ex.submit(llm.chat, prompts[i], model=specs[i][1],
                                      purpose="diverge:%s:%s" % (arm, specs[i][1]))
                            for i in range(len(prompts))]
                    outs = [f.result() for f in futs]
                arts = [o for o in outs if o.strip()]
                d: Dict[str, Any] = {
                    "n_expected": len(specs), "n_arts": len(arts),
                    "models": [m for _f, m, _p in specs],
                    "frames": [f["name"] for f, _m, _p in specs],
                    "secs": round(time.time() - t0, 1),
                    "n_calls": len(llm.rec) - n0,
                    "arts_chars": [len(a2) for a2 in arts],
                }
                if len(arts) < 2:
                    d["valid"] = False
                    d["reason"] = "too_few_arts(%d)" % len(arts)
                else:
                    vecs = emb_llm.embed(list(arts))
                    d["valid"] = True
                    d["effective_rank"] = round(effective_rank(vecs), 4)
                    d["effective_rank_per_n"] = round(effective_rank(vecs) / len(arts), 4)
                    d["modes"] = modes(vecs)
                    d["spread"] = round(spread(vecs), 4)
                    d["lexical_sharing"] = round(lexical_sharing(arts), 4)
                    d["branch_diversity"] = round(branch_diversity(arts), 4)
                d["arts"] = arts
                g["arms"][arm] = d
                print("  %s r%d %-11s 支=%d/%d 有效秩=%s 秩/n=%s 模态=%s 共享=%s (%.0fs)"
                      % (topic["tid"], rep, arm, d["n_arts"], d["n_expected"],
                         d.get("effective_rank"), d.get("effective_rank_per_n"),
                         d.get("modes"), d.get("lexical_sharing"), d["secs"]), flush=True)
            groups.append(g)
            with open(os.path.join(out_dir, "group_%s_r%d.json" % (g["tid"], g["rep"])),
                      "w", encoding="utf-8") as f:
                json.dump(g, f, ensure_ascii=False, indent=2)

    health = {
        "n_groups": len(groups),
        "n_arms": len(arms), "arms": arms,
        "n_calls_total": len(llm.rec),
        "n_calls_failed": sum(1 for c in llm.rec if not c.ok),
        "n_calls_truncated": sum(1 for c in llm.rec if c.finish_reason == "length"),
        "n_calls_empty": sum(1 for c in llm.rec if c.content_len == 0),
        "model": a.model, "effort": a.effort,
        "model_pool": alive, "dead_models": pr["dead"],
        "n_branch_deficit": sum(1 for g in groups for arm in arms
                                if g["arms"][arm]["n_arts"] < g["arms"][arm]["n_expected"]),
    }
    health["channel_health"] = round(1 - health["n_calls_failed"] / max(health["n_calls_total"], 1), 4)
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"health": health,
                   "groups": [{k: v for k, v in g.items()} for g in groups]},
                  f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "calllog.jsonl"), "w", encoding="utf-8") as f:
        for c in llm.rec:
            f.write(json.dumps(c.__dict__, ensure_ascii=False) + "\n")
    print("\n== 通道健康 ==")
    for k, v in health.items():
        print("  %-22s %s" % (k, v))
    print("\n✓ 落盘 %s" % out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
