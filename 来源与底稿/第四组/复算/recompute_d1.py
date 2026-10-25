#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复算 D-1 换值同步（★ 独立实现：★ 不 import 第四组的任何模块）

═══ 这个脚本回答什么 ═══
第四组 Phase 1 的 D-1 判据："把档案里的可核锚点换掉重跑 ⇒ 产��里的可核痕迹是否跟着换"。
本脚本从【原始产出】重建全部配对，算出每个臂的同步率与臂间配对 McNemar 检验。

═══ 它读什么（★ 相对自身定位，★ 换机器不崩）═══
默认读【本文件上两级】的 `group4_state_driven/archive/runs/`：
    p2_orig.jsonl          原锚点批次的产出（★ 每行一条 kind=gen 的记录）
    p2_swap.jsonl          换值批次的产出（★ 同上）
    p2_ckf_analysis.json   ★ 【可选】第四组自己的分析产物 ⇒ 用来做【逐行对拍】（自校验）
★ 三个文件都来自第四组 v6 数据包（drive node_id 455786470490829），★ 已在
  `来源与底稿/第四组/` 内归档 ⇒ ★ 第三方可离线独立重跑。

═══ ★ 纪律 ═══
1. ★ **不写死任何基线 sha**（★ 自指量只能声明算法，不能写死值）⇒ ★ 本脚本**从原始产出重算**，
   并**打印它读到的每个文件的 sha256**，★ 第三方自己核。
2. ★ **规模数不写死**（文件几行、几个臂、几个配对 ⇒ 全部从数据里算）。
3. ★ **`sys.dont_write_bytecode = True`**（★ 工具不得在被检树里留 .pyc）。
4. ★ **不改任何输入文件**（只读）。

用法：
    python3 recompute_d1.py                # 跑复算 + 逐行对拍 + 打印所有读数
    python3 recompute_d1.py --runs <目录>  # 指定 runs 目录
    python3 recompute_d1.py --no-crosscheck  # 跳过与第四组产物���对拍
退出码：0 = 正常跑完（★ 对拍不一致只**打印**，不作为退出码，★ 因为那属于【别人的产物变了】）。
"""
import sys

sys.dont_write_bytecode = True

import hashlib
import json
import re
from math import comb, erfc, sqrt
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_RUNS = HERE.parent / "group4_state_driven" / "archive" / "runs"

ORIG_NAME = "p2_orig.jsonl"
SWAP_NAME = "p2_swap.jsonl"
CROSS_NAME = "p2_ckf_analysis.json"


# ---------------------------------------------------------------- 统计（纯标准库）
def binom_two_sided(k, n, p=0.5):
    """精确二项检验（双尾）。"""
    if n == 0:
        return 1.0
    probs = [comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(n + 1)]
    pk = probs[k]
    return min(1.0, sum(x for x in probs if x <= pk * (1 + 1e-9)))


def mcnemar_exact(b, c):
    """McNemar 精确检验（双尾）：b / c = 各自独赢的对数 ⇒ 配对二项。"""
    n = b + c
    if n == 0:
        return 1.0
    probs = [comb(n, i) * 0.5 ** n for i in range(n + 1)]
    pk = probs[min(b, c)]
    return min(1.0, sum(x for x in probs if x <= pk * (1 + 1e-9)))


def mcnemar_chi2_cc(b, c):
    """McNemar χ²（带连续校正）。"""
    if b + c == 0:
        return 1.0
    chi2 = (abs(b - c) - 1) ** 2 / (b + c)
    return min(1.0, erfc(sqrt(chi2 / 2.0)))


# ---------------------------------------------------------------- D-1 判定（独立实现）
_PUNCT = re.compile(r"[^\w一-鿿]+", re.U)
_IDRE = re.compile(r"[A-Za-z]*\d+[A-Za-z]*")


def norm(t):
    """归一化：去标点、压空白（用于子串匹配）。"""
    return _PUNCT.sub("", t or "")


def anchor_keys(anchor):
    """从锚点里抽可核标识：优先数字/字母数字串（"48200"），否则用整句短语。

    ★ 为什么不能用整句：档案里注入的是整句（"这款罕见病药的年治疗费用是 48200 元"），
      而正文里模型只写 "48200" ⇒ 用整句去正文里找**永远匹配不上**。
    """
    if not anchor:
        return []
    ids = _IDRE.findall(anchor)
    if ids:
        return list(dict.fromkeys(ids))
    a = anchor.strip()
    return [a.lower(), a] if a.lower() != a else [a]


def hit_any(text, keys):
    """任一候选键命中即算。★ 数字型锚点精确匹配；短语型大小写不敏感。"""
    if any(any(ch.isdigit() for ch in k) for k in keys):
        return any(norm(k) in norm(text) for k in keys)
    tl = norm(text).lower()
    return any(norm(k).lower() in tl for k in keys)


def sync_flags(text_orig, text_swap, anchor_old, anchor_new):
    """同步 = 换值版有新值 ∧ 换值版无旧值 ∧ 原版无新值（三条件，缺一不可）。"""
    ko, kn = anchor_keys(anchor_old), anchor_keys(anchor_new)
    if not ko or not kn:
        return None
    r = {
        "new_in_new": hit_any(text_swap, kn),
        "old_in_new": hit_any(text_swap, ko),
        "new_in_orig": hit_any(text_orig, kn),
        "old_in_orig": hit_any(text_orig, ko),
    }
    r["synchronized"] = bool(r["new_in_new"] and not r["old_in_new"] and not r["new_in_orig"])
    return r


# ---------------------------------------------------------------- IO
def sha256_of(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_gen(path):
    """读一个 jsonl，取 kind=gen 的记录 ⇒ {（题, 臂, 样本）: 记录}"""
    out = {}
    n_lines = 0
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        n_lines += 1
        d = json.loads(line)
        if d.get("kind") != "gen":
            continue
        out[(d["topic_id"], d["arm"], d["sample"])] = d
    return out, n_lines


# ---------------------------------------------------------------- main
def main(argv):
    runs = DEFAULT_RUNS
    crosscheck = True
    args = list(argv[1:])
    if "--runs" in args:
        i = args.index("--runs")
        runs = Path(args[i + 1]).resolve()
        del args[i:i + 2]
    if "--no-crosscheck" in args:
        crosscheck = False
        args.remove("--no-crosscheck")

    orig_p = runs / ORIG_NAME
    swap_p = runs / SWAP_NAME
    cross_p = runs / CROSS_NAME

    print("=== 本次复算读到的文件（★ sha256 由脚本现算，★ 第三方请自行核对）===")
    for p in (orig_p, swap_p):
        if not p.is_file():
            print("  ⛔ 缺文件：%s" % p)
            return 2
        print("  %s" % p)
        print("      sha256 = %s" % sha256_of(p))
    if crosscheck:
        if cross_p.is_file():
            print("  %s  （★ 可选：用于逐行对拍）" % cross_p)
            print("      sha256 = %s" % sha256_of(cross_p))
        else:
            print("  （未找到 %s ⇒ 跳过对拍）" % cross_p)
            crosscheck = False

    orig, n_o = load_gen(orig_p)
    swap, n_s = load_gen(swap_p)
    print("\n=== 规模（★ 全部从数据里数出来，★ 未写死）===")
    print("  %s：%d 行，其中 kind=gen %d 条" % (ORIG_NAME, n_o, len(orig)))
    print("  %s：%d 行，其中 kind=gen %d 条" % (SWAP_NAME, n_s, len(swap)))
    print("  臂（从数据里取）：%s" % ", ".join(sorted({k[1] for k in orig})))
    print("  题（从数据里取）：%s" % ", ".join(sorted({k[0] for k in orig})))
    print("  样本号（从数据里取）：%s" % ", ".join(str(x) for x in sorted({k[2] for k in orig})))

    # ---- 逐配对重建 ----
    mine = {}
    for key in sorted(set(orig) & set(swap)):
        go, gs = orig[key], swap[key]
        a_old = go.get("ckf_anchor") or ""
        a_new = gs.get("ckf_anchor") or ""
        if not (a_old and a_new):
            continue
        r = sync_flags(go.get("text") or "", gs.get("text") or "", a_old, a_new)
        if r is None:
            continue
        r.update({"topic_id": key[0], "arm": key[1], "sample": key[2],
                  "anchor_old": a_old, "anchor_new": a_new})
        mine[key] = r

    # ---- 可选：与第四组自己的产物逐行对拍（★ 复算脚本自身的可信度证据）----
    if crosscheck:
        ref = json.load(open(cross_p, encoding="utf-8"))
        refmap = {(r["topic_id"], r["arm"], r["sample"]): r for r in ref.get("rows", [])}
        common = set(mine) & set(refmap)
        mismatch = [k for k in sorted(common)
                    if mine[k]["synchronized"] != refmap[k].get("synchronized")]
        print("\n=== 逐行对拍（★ 本脚本 vs 第四组自己的分析产物）===")
        print("  我的配对数 %d ｜ 对方 %d ｜ 交集 %d" % (len(mine), len(refmap), len(common)))
        print("  ★ synchronized 逐行不一致数：%d %s"
              % (len(mismatch), mismatch if mismatch else "（★ 全部一致）"))
        print("  ★ 我独有：%s ｜ 对方独有：%s"
              % (sorted(set(mine) - set(refmap)) or "∅", sorted(set(refmap) - set(mine)) or "∅"))

    # ---- 分臂同步率 ----
    by = {}
    for k, r in mine.items():
        by.setdefault(r["arm"], []).append(r)
    print("\n=== 分臂 D-1 换值同步（★ 本脚本复算）===")
    print("  臂    n   同步数   同步率    新值进换值版  旧值残留  新值进原版   vs 随机基线 0.5")
    for arm in sorted(by):
        rs = by[arm]
        n = len(rs)
        k = sum(1 for r in rs if r["synchronized"])
        print("  %-4s %3d  %3d     %6.1f%%    %5.1f%%       %5.1f%%     %5.1f%%      p=%.4f" % (
            arm, n, k, 100.0 * k / n,
            100.0 * sum(r["new_in_new"] for r in rs) / n,
            100.0 * sum(r["old_in_new"] for r in rs) / n,
            100.0 * sum(r["new_in_orig"] for r in rs) / n,
            binom_two_sided(k, n, 0.5)))

    # ---- 臂间配对 2×2 + McNemar ----
    keys = sorted({(r["topic_id"], r["sample"]) for r in mine.values()})
    arms = sorted(by)
    print("\n=== 臂间配对 2×2 + McNemar（★ 本脚本复算）===")
    for i in range(len(arms)):
        for j in range(i + 1, len(arms)):
            a1, a2 = arms[i], arms[j]
            both = only1 = only2 = neither = 0
            for tid, smp in keys:
                r1 = mine.get((tid, a1, smp))
                r2 = mine.get((tid, a2, smp))
                if not r1 or not r2:
                    continue
                s1, s2 = r1["synchronized"], r2["synchronized"]
                if s1 and s2:
                    both += 1
                elif s1:
                    only1 += 1
                elif s2:
                    only2 += 1
                else:
                    neither += 1
            p_ex = mcnemar_exact(only1, only2)
            p_cc = mcnemar_chi2_cc(only1, only2)
            print("  %s vs %s : both=%d  only_%s=%d  only_%s=%d  neither=%d  n_disc=%d"
                  % (a1, a2, both, a1, only1, a2, only2, neither, only1 + only2))
            print("       McNemar 精确(两侧) p=%.4f  ｜ χ²(连续校正) p=%.4f" % (p_ex, p_cc))

    # ---- 逐配对明细（人肉核用）----
    print("\n=== 逐配对同步明细（人肉核用）===")
    print("  题  样本  臂   同步  新值在换值版 旧值在换值版 新值在原版  锚点")
    for k in sorted(mine, key=lambda x: (x[0], x[2], x[1])):
        r = mine[k]
        print("  %-4s %-4d %-4s  %-5s %-12s %-12s %-10s %s" % (
            r["topic_id"], r["sample"], r["arm"],
            "YES" if r["synchronized"] else "-",
            "Y" if r["new_in_new"] else ".",
            "Y" if r["old_in_new"] else ".",
            "Y" if r["new_in_orig"] else ".",
            r["anchor_old"][:34]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
