#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v3 独立审稿人 · 自写复算：②篇「承重子层」四序列
======================================================================
★ 设计原则：★ **不 import calc_net_gain.py 的任何函数** ⇒ 自己重写归一化、
  集合运算、承重聚合 ⇒ ★ 若两边一致 ⇒ 是两个独立实现的交叉验证。

★ 口径（与稿内声明对齐）：
  · 断言元素 = 归一化后的 claim 文本（去重）
  · 配对 = 同 (task_id, rep)，基线 = B0_direct
  · 仪器层零（n_cards==0 且 parsefail_rate is None）⇒ 该配对跳过
  · added = W\B, lost = B\W
  · 承重 OR  = 该断言在【该侧臂】任一卡片行 load_bearing=true
  · 承重 AND = 该断言在【该侧臂】全部卡片行 load_bearing=true
  · 承重新增的承重标记取【臂】的表；承重丢失的承重标记取【基线】的表
  · 净(OR) 序列 = 逐配对 (added_lb_OR − lost_lb_OR)

★ 输出：四个序列 + 汇总 + 与「登记台账」逐位对拍
"""
import json
import os
import re
import sys
import unicodedata
from collections import OrderedDict, defaultdict

REPO = "/workspace/work/llm-creativity-mechanism-papers"
READINGS = os.path.join(
    REPO, "来源与底稿/第三组_治塌缩层3/cmp8repo/repro/readings/main_big_arms.jsonl")

BASELINE = "B0_direct"
ARMS = ("W_design_L2", "W_train_L3")

# ── 自己的归一化（刻意写成与 calc_net_gain.py 不同的实现形状）──────────
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_WS = re.compile(r"\s+")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3})")


def my_normalize(text):
    """归一化 v1（独立实现）。"""
    t = unicodedata.normalize("NFKC", text or "")
    t = _THOUSANDS.sub("", t)          # 去千分位逗号
    t = _WS.sub(" ", t).strip()        # 压空白
    t = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", t)  # 汉字间空格
    t = re.sub(r"\s+(?=[\u4e00-\u9fff])", "", t)
    t = re.sub(r"(?<=[\u4e00-\u9fff])\s+", "", t)
    return t


def my_assertion_map(row):
    """⇒ {归一化文本: {"lb_or":bool, "lb_and":bool, "n_rows":int}}"""
    agg = OrderedDict()
    for c in (row.get("cards") or []):
        txt = my_normalize(c.get("claim"))
        if not txt:
            continue
        d = agg.setdefault(txt, {"lb_or": False, "lb_and": True, "n_rows": 0})
        lb = bool(c.get("load_bearing"))
        d["n_rows"] += 1
        d["lb_or"] = d["lb_or"] or lb
        d["lb_and"] = d["lb_and"] and lb
    return agg


def is_instrument_zero(row):
    return (row.get("n_cards") or 0) == 0 and row.get("parsefail_rate") is None


def main():
    rows = [json.loads(l) for l in open(READINGS, encoding="utf-8") if l.strip()]
    idx = {(r["task_id"], r["rep"], r["arm"]): r for r in rows}
    tasks = sorted({r["task_id"] for r in rows})
    reps = sorted({r["rep"] for r in rows})

    print("=" * 78)
    print("v3 独立复算 · ②篇 承重子层四序列（★ 不 import 生产者代码）")
    print("=" * 78)
    print("数据：%s" % READINGS)
    print("行数 %d ｜ 题 %s ｜ rep %s" % (len(rows), tasks, reps))
    print()

    seqs = defaultdict(lambda: defaultdict(list))   # arm -> (口径, "OR"/"AND") -> [net per pair]
    detail = []

    for t in tasks:
        for rep in reps:
            b = idx.get((t, rep, BASELINE))
            if b is None:
                continue
            for arm in ARMS:
                w = idx.get((t, rep, arm))
                if w is None:
                    continue
                if is_instrument_zero(w) or is_instrument_zero(b):
                    print("  【SKIPPED】%s#r%d#%s 仪器层零" % (t, rep, arm))
                    continue
                am = my_assertion_map(w)
                bm = my_assertion_map(b)
                added = [x for x in am if x not in bm]
                lost = [x for x in bm if x not in am]
                rec = {"task": t, "rep": rep, "arm": arm,
                       "n_added": len(added), "n_lost": len(lost)}
                for cname in ("OR", "AND"):
                    key = "lb_or" if cname == "OR" else "lb_and"
                    a_lb = sum(1 for x in added if am[x][key])
                    l_lb = sum(1 for x in lost if bm[x][key])
                    net = a_lb - l_lb
                    rec[cname] = (a_lb, l_lb, net)
                    seqs[arm][cname].append(net)
                detail.append(rec)

    print()
    print("【逐配对明细】")
    for rec in detail:
        print("  %-4s rep%s %-14s 新增%-2d 丢失%-2d ｜ OR 承重 +%d/−%d 净%+d"
              " ｜ AND 承重 +%d/−%d 净%+d"
              % (rec["task"], rec["rep"], rec["arm"], rec["n_added"], rec["n_lost"],
                 rec["OR"][0], rec["OR"][1], rec["OR"][2],
                 rec["AND"][0], rec["AND"][1], rec["AND"][2]))

    print()
    print("【四序列 + 汇总】")
    LEDGER = {
        "W_design_L2": {"OR": ([-1, 2, 1, 4], 20, 14, 6), "AND": ([-4, -1, -2, 0], 7, 14, -7)},
        "W_train_L3": {"OR": ([-2, 1, 2, 6], 21, 14, 7), "AND": ([-4, -1, -1, 4], 12, 14, -2)},
    }
    all_ok = True
    for arm in ARMS:
        for cname in ("OR", "AND"):
            s = seqs[arm][cname]
            tot = sum(s)
            exp_seq, exp_a, exp_l, exp_n = LEDGER[arm][cname]
            # 独立汇总：added/lost 由逐配对相加
            if cname == "OR":
                pass
            print("  %-14s %-3s 序列 %-22s 汇总净 %+d"
                  % (arm, cname, str(s), tot))
            print("       ★ 台账序列 %-22s 汇总净 %+d  ⇒ %s"
                  % (str(exp_seq), exp_n, "一致 ✅" if s == exp_seq else "★ 不一致 ❌"))
            if s != exp_seq:
                all_ok = False
    # 汇总 added/lost（用逐配对相加，独立于 calc_net_gain 的累加顺序）
    print()
    print("【汇总 added/lost（逐配对相加）】")
    sums = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for rec in detail:
        for cname in ("OR", "AND"):
            sums[rec["arm"]][cname][0] += rec[cname][0]
            sums[rec["arm"]][cname][1] += rec[cname][1]
    for arm in ARMS:
        for cname in ("OR", "AND"):
            a, l = sums[arm][cname]
            exp_a, exp_l, exp_n = LEDGER[arm][cname][1], LEDGER[arm][cname][2], LEDGER[arm][cname][3]
            ok = (a, l, a - l) == (exp_a, exp_l, exp_n)
            all_ok &= ok
            print("  %-14s %-3s 新增%3d 丢失%3d 净%+3d ｜ 台账 +%d/+%d/%+d ⇒ %s"
                  % (arm, cname, a, l, a - l, exp_a, exp_l, exp_n,
                     "一致 ✅" if ok else "★ 不一致 ❌"))

    print()
    print("【符号稳健性】")
    for arm in ARMS:
        for cname in ("OR", "AND"):
            s = seqs[arm][cname]
            pos = sum(1 for x in s if x > 0)
            neg = sum(1 for x in s if x < 0)
            zer = sum(1 for x in s if x == 0)
            print("  %-14s %-3s 正%2d 负%2d 零%2d  符号一致=%s"
                  % (arm, cname, pos, neg, zer,
                     "是" if (pos == len(s) or neg == len(s)) else "否（★ 方向随口径/配对翻转）"))

    print()
    print("★ 总体：%s" % ("✅ 四序列与台账逐位一致" if all_ok else "❌ 与台账不一致"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
