# -*- coding: utf-8 -*-
"""巡练：搜索更好的「思维工作流」。

循环：
    提议规格变体 → 在巡练题上执行 → 外部核验器打分 → 保留胜者 → 在留出题上判决

硬约束：
1. preflight 只从固定目录取，**目录里没有答案**（防作者先验注入）
2. 所有变体长度封顶相同（400 字）——密度奖励被长度劫持的教训
3. 打分只用外部核验器，工作流内部的自检只是被测组件，不参与打分
4. 留出题在整轮里**从不被用于选择**，只在最后判决一次
5. 停止条件：留出集不再提升，或达到轮数上限
"""
from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from creativity_lab.client import LLM              # noqa: E402
from creativity_lab.workflow import (DEFAULT_SPEC, PREFLIGHT_CATALOG,  # noqa: E402
                                     describe, run_spec, spec_key)
from creativity_lab.verify import (check_claims, extract_claims,  # noqa: E402
                                   score_of)

OUT = "runs/drill"
os.makedirs(OUT, exist_ok=True)
N_DRILL = int(os.environ.get("N_DRILL", "5"))

DATA = json.load(open("creativity_lab/data/legal_topics_v2.json", encoding="utf-8"))
LAWS, TOPICS = DATA["laws"], DATA["topics"]
law_of = {t["tid"]: t["law"] for t in TOPICS}
ask_of = {t["tid"]: t["ask"] for t in TOPICS}

# 巡练题 = 前 N_DRILL 题（覆盖多部法）；留出题 = 最后 4 题
DRILL = TOPICS[:N_DRILL]
HOLD = TOPICS[-4:]

# 候选规格：先做单维度消融（可靠），再加 LLM 提议的组合
def candidate_specs():
    specs = [dict(DEFAULT_SPEC)]                      # incumbent
    for p in sorted(PREFLIGHT_CATALOG):              # 单个 preflight
        s = dict(DEFAULT_SPEC); s["preflight"] = [p]; specs.append(s)
    s = dict(DEFAULT_SPEC); s["mode"] = "fuse"; specs.append(s)
    s = dict(DEFAULT_SPEC); s["n_branches"] = 1; specs.append(s)
    s = dict(DEFAULT_SPEC); s["n_branches"] = 5; specs.append(s)
    s = dict(DEFAULT_SPEC); s["selfcheck"] = True; specs.append(s)
    s = dict(DEFAULT_SPEC); s["preflight"] = ["P2", "P6"]; specs.append(s)
    s = dict(DEFAULT_SPEC); s["preflight"] = ["P2", "P6", "P3"]; specs.append(s)
    s = dict(DEFAULT_SPEC); s["preflight"] = ["P2", "P6", "P3", "P8"]; specs.append(s)
    s = dict(DEFAULT_SPEC); s["mode"] = "fuse"; s["preflight"] = ["P2", "P6"]; specs.append(s)
    s = dict(DEFAULT_SPEC); s["n_branches"] = 1; s["preflight"] = ["P2", "P6"]; specs.append(s)
    # 去重
    seen, out = set(), []
    for s in specs:
        k = spec_key(s)
        if k not in seen:
            seen.add(k); out.append(s)
    return out


def evaluate(spec, topics, tag):
    """在给定题集上执行规格 → 抽取 → 核验 → 打分。"""
    llm = LLM()
    results = []

    def one(T):
        ans = run_spec(LLM(), T, spec)
        cs = extract_claims(LLM(), ans)
        v = check_claims(LLM(), T["ask"], LAWS[law_of[T["tid"]]]["evidence"], cs)
        sc = score_of(v, cs)
        sc.update(tid=T["tid"], len=len(ans), n_claims=len(cs))
        return sc

    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(one, T) for T in topics]
        for f in as_completed(futs):
            try:
                results.append(f.result())
            except Exception as e:
                print("    ERR %s" % str(e)[:70], flush=True)
    if not results:
        return None
    agg = dict(
        score=sum(r["score"] for r in results) / len(results),
        n_sup=sum(r["n_sup"] for r in results),
        n_con=sum(r["n_con"] for r in results),
        n_non=sum(r["n_non"] for r in results),
        n_unment=sum(r["n_unment"] for r in results),
        len=sum(r["len"] for r in results) / len(results),
        n=len(results))
    json.dump(dict(spec=spec, key=spec_key(spec), desc=describe(spec),
                   agg=agg, per=results),
              open("%s/%s_%s.json" % (OUT, tag, spec_key(spec)), "w"),
              ensure_ascii=False, indent=1)
    return agg


def main():
    t0 = time.time()
    specs = candidate_specs()
    print("巡练题 %d：%s" % (len(DRILL), ",".join(t["tid"] for t in DRILL)), flush=True)
    print("留出题 %d：%s（整轮不用于选择，只在最后判决一次）"
          % (len(HOLD), ",".join(t["tid"] for t in HOLD)), flush=True)
    print("候选规格 %d 个\n" % len(specs), flush=True)

    print("%-26s %8s %6s %6s %6s %6s" % ("规格", "分数", "支持", "矛盾", "非主张", "均长"))
    rows = []
    for i, s in enumerate(specs, 1):
        a = evaluate(s, DRILL, "drill")
        if a is None:
            continue
        rows.append((a["score"], spec_key(s), s, a))
        print("%-26s %8.2f %6d %6d %6d %6d"
              % (spec_key(s), a["score"], a["n_sup"], a["n_con"], a["n_non"], a["len"]),
              flush=True)

    rows.sort(key=lambda x: -x[0])
    print("\n== 巡练题排名 ==", flush=True)
    for sc, k, s, a in rows:
        print("  %-26s %7.2f  %s" % (k, sc, describe(s)), flush=True)

    # ---- 留出判决：冠军 vs incumbent ----
    inc = dict(DEFAULT_SPEC)
    best = rows[0][2] if rows else inc
    print("\n== 留出题判决 ==", flush=True)
    ai = evaluate(inc, HOLD, "hold")
    ab = evaluate(best, HOLD, "hold")
    print("  incumbent  %-22s 分数 %7.2f (支持%d 矛盾%d 非主张%d)"
          % (spec_key(inc), ai["score"], ai["n_sup"], ai["n_con"], ai["n_non"]), flush=True)
    print("  冠军      %-22s 分数 %7.2f (支持%d 矛盾%d 非主张%d)"
          % (spec_key(best), ab["score"], ab["n_sup"], ab["n_con"], ab["n_non"]), flush=True)
    win = ab["score"] > ai["score"]
    print("\n  判决: %s" % ("冠军在留出集上更好 → 巡练有效" if win else
                            "冠军在留出集上没有更好 → 巡练无效，不采用"))
    json.dump(dict(rows=[dict(score=r[0], key=r[1], spec=r[2], agg=r[3]) for r in rows],
                   incumbent=inc, best=best,
                   holdout=dict(incumbent=ai, best=ab), win=win,
                   drill_tids=[t["tid"] for t in DRILL],
                   hold_tids=[t["tid"] for t in HOLD]),
              open("%s/summary.json" % OUT, "w"), ensure_ascii=False, indent=1)
    print("\n总耗时 %.0f 分钟" % ((time.time() - t0) / 60))


if __name__ == "__main__":
    main()
