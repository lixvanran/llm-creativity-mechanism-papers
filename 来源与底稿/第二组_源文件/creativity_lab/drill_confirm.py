# -*- coding: utf-8 -*-
"""决定性补充实验：p1 的优势是真的，还是 5 题选冠军选出来的噪声？

把 p1 冠军与基线放到**从未参与选择**的另外 13 道训练题上跑一遍。
- 若 p1 仍然胜出 → 巡练不是无效，是**欠采样**（该扩题重跑）
- 若 p1 不胜出   → p1 就是噪声，巡练确实无效
"""
from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from creativity_lab.client import LLM              # noqa: E402
from creativity_lab.workflow import (DEFAULT_SPEC, describe,  # noqa: E402
                                     run_spec, spec_key)
from creativity_lab.verify import (check_claims, extract_claims,  # noqa: E402
                                   score_of)

OUT = "runs/drill"
DATA = json.load(open("creativity_lab/data/legal_topics_v2.json", encoding="utf-8"))
LAWS, TOPICS = DATA["laws"], DATA["topics"]
law_of = {t["tid"]: t["law"] for t in TOPICS}

DRILL = TOPICS[:5]          # 选冠军用的题
REST = TOPICS[5:-4]         # 从未参与选择的题（13 道）
HOLD = TOPICS[-4:]          # 最终留出

P1 = dict(DEFAULT_SPEC); P1["preflight"] = ["P1"]
BASE = dict(DEFAULT_SPEC)
CAND = [("冠军 b3-select-p1", P1), ("基线 b3-select-p0", BASE)]


def evaluate(spec, topics, tag):
    def one(T):
        ans = run_spec(LLM(), T, spec)
        cs = extract_claims(LLM(), ans)
        v = check_claims(LLM(), T["ask"], LAWS[law_of[T["tid"]]]["evidence"], cs)
        sc = score_of(v, cs)
        sc.update(tid=T["tid"], len=len(ans))
        return sc
    res = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        for f in as_completed([ex.submit(one, T) for T in topics]):
            try:
                res.append(f.result())
            except Exception as e:
                print("  ERR %s" % str(e)[:60], flush=True)
    agg = dict(score=sum(r["score"] for r in res) / max(len(res), 1),
               n_sup=sum(r["n_sup"] for r in res), n_con=sum(r["n_con"] for r in res),
               n_non=sum(r["n_non"] for r in res), len=sum(r["len"] for r in res) / max(len(res), 1),
               n=len(res))
    json.dump(dict(spec=spec, key=spec_key(spec), agg=agg, per=res),
              open("%s/%s_%s.json" % (OUT, tag, spec_key(spec)), "w"),
              ensure_ascii=False, indent=1)
    return agg, res


def main():
    t0 = time.time()
    print("复验题（从未参与选择）%d 道：%s" % (len(REST), ",".join(t["tid"] for t in REST)), flush=True)
    out = {}
    for name, spec in CAND:
        agg, res = evaluate(spec, REST, "confirm")
        out[name] = (agg, res)
        print("%-18s 分数 %6.2f  支持%3d 矛盾%2d 非主张%3d 均长%4d"
              % (name, agg["score"], agg["n_sup"], agg["n_con"], agg["n_non"], agg["len"]),
              flush=True)

    # 逐题配对比较
    print("\n逐题对比（冠军 − 基线）:", flush=True)
    a = {r["tid"]: r for r in out["冠军 b3-select-p1"][1]}
    b = {r["tid"]: r for r in out["基线 b3-select-p0"][1]}
    wins = losses = 0
    for tid in sorted(set(a) & set(b)):
        d = a[tid]["score"] - b[tid]["score"]
        wins += d > 0; losses += d < 0
        print("  %s  冠军%5.1f 基线%5.1f  差%+5.1f" % (tid, a[tid]["score"], b[tid]["score"], d),
              flush=True)
    print("  冠军胜 %d / 负 %d（共 %d 题）" % (wins, losses, len(set(a) & set(b))), flush=True)

    sa = out["冠军 b3-select-p1"][0]["score"]
    sb = out["基线 b3-select-p0"][0]["score"]
    print("\n判决: %s" % ("p1 的优势真实存在 → 巡练欠采样，扩题后重跑" if sa > sb
                          else "p1 不胜出 → p1 是噪声，巡练确实无效"))
    json.dump(dict(confirm={k: v[0] for k, v in out.items()},
                   per_topic={k: v[1] for k, v in out.items()},
                   rest_tids=[t["tid"] for t in REST]),
              open("%s/confirm.json" % OUT, "w"), ensure_ascii=False, indent=1)
    print("总耗时 %.0f 分钟" % ((time.time() - t0) / 60))


if __name__ == "__main__":
    main()
