#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★ v3 独立审稿人 · ④篇 D-1 产出口径体检：★ 分母里有没有失败生成？
======================================================================
★ 背景（★ 我的跨项目记忆里的一条同族纪律）：
  「全 0 错误」是【日志口径】，不是【产出层事实】⇒ 0 字产出可能被记为 ok
  ⇒ ⇒ 报【分母型读数】（同步率/胜率/命中率）时必须给【剔除失败生成后】的口径。

★ 本脚本：直接从 p2_orig.jsonl / p2_swap.jsonl 逐条读出
  · 每个 (arm, topic, sample) 的换值版产出长度
  · 空的 / 极短的产出
  ⇒ ★ 并给出【含失败生成】与【剔除失败生成】两套同步率与 McNemar。
"""
import json
import os
import re
from collections import defaultdict
from math import comb

REPO = "/workspace/work/llm-creativity-mechanism-papers"
RUNS = os.path.join(REPO, "来源与底稿/第四组/group4_state_driven/archive/runs")
ORIG = os.path.join(RUNS, "p2_orig.jsonl")
SWAP = os.path.join(RUNS, "p2_swap.jsonl")

NUM_RE = re.compile(r"(?<![\d.])(\d{2,7})(?![\d])")


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def gen_text(rec):
    """★ 尽最大努力取出正文（★ 多种字段名）"""
    for k in ("text", "answer", "output", "content", "resp", "response", "body"):
        v = rec.get(k)
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            for kk in ("text", "content", "answer", "output"):
                if isinstance(v.get(kk), str):
                    return v[kk]
    return ""


def main():
    orig = load(ORIG)
    swap = load(SWAP)
    print("=" * 78)
    print("★ v3 独立体检 · ④篇 D-1 产出口径")
    print("=" * 78)
    print("orig %d 行 ｜ swap %d 行" % (len(orig), len(swap)))

    # 看一行 gen 记录的字段
    g = next((r for r in swap if r.get("kind") == "gen"), None)
    if g:
        print("gen 记录字段：%s" % sorted(g.keys()))
        print("  样例：%s" % json.dumps({k: (str(v)[:60]) for k, v in g.items()},
                                 ensure_ascii=False)[:600])
    print()

    def index(rows):
        d = {}
        for r in rows:
            if r.get("kind") != "gen":
                continue
            arm = r.get("arm")
            topic = (r.get("topic") or r.get("topic_id") or r.get("task")
                     or r.get("task_id"))
            sample = r.get("sample") or r.get("rep") or r.get("sample_id")
            d[(arm, topic, sample)] = r
        return d

    oi, si = index(orig), index(swap)
    print("orig gen 索引 %d 条 ｜ swap gen 索引 %d 条" % (len(oi), len(si)))
    print()

    # ── 产出口径：长度体检 ──
    print("【产出层体检 · 换值版】")
    lens = []
    empties = []
    for k, r in sorted(si.items()):
        t = gen_text(r)
        n = len(t.strip())
        lens.append((k, n))
        if n < 5:
            empties.append((k, n, t[:60]))
    print("  换值版产出总条数 = %d" % len(lens))
    print("  ★ 长度 < 5 字符（空/近空产出）= %d 条" % len(empties))
    for k, n, t in empties:
        print("     ★ %s  长度=%d  内容=%r" % (k, n, t))
    if empties:
        print("  ★★ 长度分布（全量）★：%s" % sorted(n for _k, n in lens))
    else:
        print("  长度分布（全量）：%s" % sorted(n for _k, n in lens))
    print()

    print("【产出层体检 · 原版】")
    olens = []
    oempty = []
    for k, r in sorted(oi.items()):
        t = gen_text(r)
        n = len(t.strip())
        olens.append(n)
        if n < 5:
            oempty.append((k, n))
    print("  原版产出总条数 = %d ｜ 长度 < 5 的 = %d 条 %s"
          % (len(olens), len(oempty), oempty if oempty else ""))
    print("  长度分布：%s" % sorted(olens))
    print()

    # ── 同步判定（独立实现）──
    def num_of(a):
        m = NUM_RE.findall(a or "")
        return m[0] if m else None

    def ckf_anchor(r):
        for k in ("ckf_anchor", "anchor", "ckf", "anchor_out"):
            v = r.get(k)
            if isinstance(v, str) and v:
                return v
        return ""

    arms = sorted({k[0] for k in si if k[0] in ("C0", "C1", "C2")})
    topics = sorted({k[1] for k in si if k[0] == "C2"})
    samples = sorted({k[2] for k in si if k[0] == "C2"}, key=str)

    # 换值映射
    swap_map = {}
    for k, r in si.items():
        a = ckf_anchor(r)
        if "swap" in r and isinstance(r.get("ckf_swap"), str):
            on = num_of(a)
            nn = num_of(r["ckf_swap"])
            if on and nn:
                swap_map.setdefault(on, nn)

    sync = {}
    for arm in arms:
        rows = []
        for tp in topics:
            for sm in samples:
                wr = si.get((arm, tp, sm))
                orr = oi.get((arm, tp, sm))
                if wr is None or orr is None:
                    continue
                wt = gen_text(wr)
                ot = gen_text(orr)
                oa = num_of(ckf_anchor(orr))
                na = swap_map.get(oa) if oa else None
                if na is None:
                    na = num_of(ckf_anchor(wr))
                ok = False
                if na and oa:
                    ok = (na in wt) and (oa not in wt) and (na not in ot)
                rows.append({"tp": tp, "sm": sm, "sync": ok,
                             "len": len(wt.strip()), "n_new": na, "n_old": oa})
        sync[arm] = rows

    def mcnemar(a_rows, b_rows):
        ka = {(r["tp"], r["sm"]): r["sync"] for r in a_rows}
        kb = {(r["tp"], r["sm"]): r["sync"] for r in b_rows}
        both = only_a = only_b = neither = 0
        for k in set(ka) & set(kb):
            if ka[k] and kb[k]:
                both += 1
            elif ka[k]:
                only_a += 1
            elif kb[k]:
                only_b += 1
            else:
                neither += 1
        n = only_a + only_b
        if n == 0:
            return 1.0, both, only_a, only_b, neither
        lo = min(only_a, only_b)
        p = sum(comb(n, i) for i in range(lo + 1)) / (2.0 ** n) * 2
        return min(1.0, p), both, only_a, only_b, neither

    def report(label, rows_by_arm):
        print("── %s ──" % label)
        for arm in arms:
            rows = rows_by_arm[arm]
            n = len(rows)
            s = sum(1 for r in rows if r["sync"])
            print("   %-4s n=%2d 同步=%2d  同步率=%5.1f%%" % (arm, n, s, 100.0 * s / n if n else 0))
        for x, y in (("C2", "C1"), ("C2", "C0"), ("C0", "C1")):
            p, both, oa, ob, ne = mcnemar(rows_by_arm[x], rows_by_arm[y])
            print("   %s vs %s : both=%d only_%s=%d only_%s=%d neither=%d  p=%.4f"
                  % (x, y, both, x, oa, y, ob, ne, p))
        print()

    print("【口径 A：含全部配对（★ = 稿内现用口径）】")
    report("含全部配对", sync)

    # 剔除空/近空产出（★ 任一侧为空 ⇒ 该配对的产出层失败 ⇒ 不进分母）
    print("【口径 B：剔除产出 < 5 字符的配对（★ 失败生成不进分母）】")
    sync_b = {}
    dropped = {}
    for arm in arms:
        keep = []
        for r in sync[arm]:
            orr = oi.get((arm, r["tp"], r["sm"]))
            olen = len(gen_text(orr).strip()) if orr is not None else -1
            if r["len"] >= 5 and olen >= 5:
                keep.append(r)
            else:
                r["_olen"] = olen
        dropped[arm] = len(sync[arm]) - len(keep)
        sync_b[arm] = keep
    for arm in arms:
        for r in sync[arm]:
            if r not in sync_b[arm]:
                print("   ★ %s 剔除配对 %s/%s：换值版长度=%d ｜ 原版长度=%s"
                      % (arm, r["tp"], r["sm"], r["len"], r.get("_olen")))
        print("   ★ %s 剔除 %d 条" % (arm, dropped[arm]))
    report("剔除失败生成", sync_b)

    print("【结论】")
    changed = False
    for x, y in (("C2", "C1"), ("C2", "C0"), ("C0", "C1")):
        p1, *_ = mcnemar(sync[x], sync[y])
        p2, *_ = mcnemar(sync_b[x], sync_b[y])
        if abs(p1 - p2) > 1e-9:
            changed = True
            print("   ★★ %s vs %s：口径A p=%.4f → 口径B p=%.4f  ⇒ ★ 判决可能翻转" % (x, y, p1, p2))
    for arm in arms:
        n1 = len(sync[arm]); s1 = sum(1 for r in sync[arm] if r["sync"])
        n2 = len(sync_b[arm]); s2 = sum(1 for r in sync_b[arm] if r["sync"])
        if (n1, s1) != (n2, s2):
            print("   ★★ %s：口径A %d/%d=%.1f%% → 口径B %d/%d=%.1f%%"
                  % (arm, s1, n1, 100.0 * s1 / n1, s2, n2, 100.0 * s2 / n2 if n2 else 0))
    if not changed:
        print("   ★ 两套口径的 McNemar 判决【不变】")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
