#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
my_own_d1.py · ④ 篇 Phase 1「D-1 换值同步」独立复算器
======================================================================
★ 为什么这个文件在包里：
    审稿人对 ④ 篇主读数的唯一证伪手段。★ 第三方必须能**独立重跑**它，
    并得到与稿内相同的数字。⇒ 本文件刻意做到：
      1. **路径相对自身**（不写死任何绝对路径、★ 不写死基线 sha）
      2. **打印它读的是哪些文件**（含每个文件的 sha256）⇒ 复算对象可核
      3. **判定逻辑自己写**（不 import 任何生产者代码）⇒ 不继承生产者的假设
      4. **退出码语义**：0 = 复算完成；2 = 找不到数据目录

★ 判据（复算者自己定义，★ 与第四组包的实现独立）：
    D-1「换值同步」= 该条产出在**换值版**里出现了**新值**，
                      且**旧值不再出现**。
    · 新值 = 换值版记录 `ckf_anchor` 里的数字
    · 旧值 = 原版记录（同 topic）`ckf_anchor` 里的数字
    · 数字边界匹配：前后不得再接数字（避免 "270" 命中 "2700"）

★ 本脚本**只读**，不写任何文件；不依赖网络；不需要任何 API 额度。

用法：
    python3 my_own_d1.py                     # 自动定位数据目录
    python3 my_own_d1.py --data-dir <路径>    # 显式指定
======================================================================
"""
import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from math import comb

ORIG_NAME = "p2_orig.jsonl"
SWAP_NAME = "p2_swap.jsonl"

# 数字抽取：至少 2 位（避开 "0.0" 之类噪声），前后不接数字
NUM_RE = re.compile(r"(?<![\d.])(\d{2,7})(?![\d])")

# 相对自身向上搜索的候选数据目录（按优先级）
CANDIDATE_SUFFIXES = [
    os.path.join("来源与底稿", "第四组交付", "data"),
    os.path.join("第四组交付", "data"),
    os.path.join("data",),
    os.path.join("evidence", "第四组交付", "data"),
    os.path.join("w4", "第四组交付", "data"),
]


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def find_data_dir(explicit=None, start=None):
    """★ 路径相对自身：先试显式路径，再从脚本所在目录向上找候选后缀。"""
    if explicit:
        if os.path.isdir(explicit) and os.path.exists(os.path.join(explicit, ORIG_NAME)):
            return os.path.abspath(explicit)
        return None
    start = start or os.path.dirname(os.path.abspath(__file__))
    cur = start
    for _ in range(8):                       # 向上最多 8 层
        for suf in CANDIDATE_SUFFIXES:
            p = os.path.join(cur, suf)
            if os.path.exists(os.path.join(p, ORIG_NAME)):
                return p
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    # 兜底：脚本同级或子目录里任何含 p2_orig.jsonl 的目录
    for root, _dirs, files in os.walk(start):
        if ORIG_NAME in files:
            return root
    return None


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                rows.append(json.loads(ln))
    return rows


def num_of(anchor):
    m = NUM_RE.findall(anchor or "")
    return m[0] if m else None


def has_num(text, num):
    if not num:
        return False
    return bool(re.search(r"(?<![\d.])" + re.escape(num) + r"(?![\d])", text or ""))


def exact_binom_two_sided(k, n, p=0.5):
    """精确二项检验（双侧）。"""
    if n == 0:
        return 1.0
    pr = sum(comb(n, i) for i in range(n + 1)) * (p ** n)  # 归一化项 = 1
    probs = [comb(n, i) * (p ** i) * ((1 - p) ** (n - i)) for i in range(n + 1)]
    obs = probs[k]
    return min(1.0, sum(pr2 for pr2 in probs if pr2 <= obs * (1 + 1e-9)))


def mcnemar_exact(a, b):
    """McNemar 精确检验（配对二元）。返回 (both, only_a, only_b, n_disc, p)。"""
    both = sum(1 for x, y in zip(a, b) if x and y)
    oa = sum(1 for x, y in zip(a, b) if x and not y)
    ob = sum(1 for x, y in zip(a, b) if (not x) and y)
    n = oa + ob
    if n == 0:
        return both, oa, ob, 0, 1.0
    lo = min(oa, ob)
    p = sum(comb(n, i) for i in range(lo + 1)) / (2 ** n) * 2
    return both, oa, ob, n, min(1.0, p)


def main():
    ap = argparse.ArgumentParser(description="④ 篇 D-1 换值同步 · 独立复算器")
    ap.add_argument("--data-dir", default=None, help="含 p2_orig.jsonl / p2_swap.jsonl 的目录")
    args = ap.parse_args()

    d = find_data_dir(args.data_dir)
    if not d:
        print("✘ 找不到数据目录（需要 p2_orig.jsonl / p2_swap.jsonl）")
        print("  用 --data-dir 指定；或把本脚本放在仓内（含 来源与底稿/第四组交付/data/）")
        return 2

    op = os.path.join(d, ORIG_NAME)
    sp = os.path.join(d, SWAP_NAME)

    print("=" * 72)
    print("④ 篇 Phase 1 · D-1 换值同步 —— 独立复算")
    print("=" * 72)
    print("【本脚本读的文件】（★ 复算对象可核）")
    for p in (op, sp):
        if os.path.exists(p):
            print("  %s" % os.path.abspath(p))
            print("      bytes=%d  sha256=%s" % (os.path.getsize(p), sha256_of(p)))
        else:
            print("  %s  ✘ 不存在" % os.path.abspath(p))
    print("  脚本自身：%s" % os.path.abspath(__file__))
    print("  ★ 判据由本脚本独立实现：未 import 任何生产者代码")
    print("-" * 72)

    O = [r for r in load_jsonl(op) if r.get("kind") == "gen"]
    S = [r for r in load_jsonl(sp) if r.get("kind") == "gen"]
    print("原版 gen 记录 = %d ；换值版 gen 记录 = %d" % (len(O), len(S)))

    orig_val = {}
    for r in O:
        n = num_of(r.get("ckf_anchor"))
        if n:
            orig_val[r["topic_id"]] = n
    print("主题 → 原值：%s" % orig_val)
    print("换值映射（取自换值版 ckf_swap）：%s"
          % (S[0].get("ckf_swap") if S else "—"))
    print("-" * 72)

    def key(r):
        return (r["arm"], r["topic_id"], r.get("sample"))

    om = {key(r): r for r in O}
    sm = {key(r): r for r in S}
    pairs = sorted([k for k in sm if k in om])
    print("配对数 = %d（按 arm+topic+sample 配对）  臂 = %s  题 = %s"
          % (len(pairs), sorted({k[0] for k in pairs}), sorted({k[1] for k in pairs})))
    print("-" * 72)

    rows = []
    for k in pairs:
        o, s = om[k], sm[k]
        old = orig_val.get(o["topic_id"])
        new = num_of(s.get("ckf_anchor"))
        txt = s.get("text") or ""
        sync = has_num(txt, new) and not has_num(txt, old)
        rows.append(dict(arm=k[0], topic=k[1], sample=k[2], old=old, new=new,
                         sync=bool(sync), empty=len(txt.strip()) < 5))

    per = defaultdict(list)
    for r in rows:
        per[r["arm"]].append(r)

    print("【逐臂 D-1 换值同步率】")
    print("  臂      n   sync   rate    精确二项(vs .5,双侧)   空产出(<5字符)")
    for arm in sorted(per):
        rr = per[arm]
        n = len(rr)
        k = sum(1 for r in rr if r["sync"])
        p = exact_binom_two_sided(k, n)
        print("  %-6s %3d  %4d  %6.4f      %-12.6f        %d"
              % (arm, n, k, k / n if n else 0.0, p, sum(1 for r in rr if r["empty"])))
    print("-" * 72)

    print("【McNemar 精确检验（配对）】")
    order = {}
    for arm in per:
        order[arm] = sorted(per[arm], key=lambda r: (r["topic"], r["sample"]))
    seen = set()
    for a in sorted(per):
        for b in sorted(per):
            if a >= b or (a, b) in seen:
                continue
            seen.add((a, b))
            A = [r["sync"] for r in order[a]]
            B = [r["sync"] for r in order[b]]
            both, oa, ob, nd, p = mcnemar_exact(A, B)
            print("  %-3s vs %-3s : both=%d  only_%s=%d  only_%s=%d  n_disc=%d  p_exact=%.10f"
                  % (a, b, both, a, oa, b, ob, nd, p))
    print("-" * 72)

    print("【读法提示（★ 这几个数各自支持什么，不支持什么）】")
    print("  · C2 vs C1 显著  ⇒  『带事实层的双层状态机在事实守恒上优于只有取舍的状态机』")
    print("  · C2 vs C0 未达阈值 ⇒  『状态机 ≠ 提示词』**尚未被证明**（★ 标题前提）")
    print("  · C0 vs C1 不可分辨 ⇒  『取舍会丢事实』**只能是方向性观察，不能写成因果**")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
