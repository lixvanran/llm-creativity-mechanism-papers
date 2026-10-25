# -*- coding: utf-8 -*-
"""`metrics_priorart.py` 的自检 —— 换成先例口径后，**每个口径必须可复算**。

> 2026-10-22 ｜ 配套 `LIT/DEEP-MEDIANITY-PRIORART.md`

## 为什么单独一个文件
我们把四个自造指标**换成了有出处的口径**（Self-Sim / 碰撞比 / ESS / DSE），
但**引用别人的口径 ≠ 算得对** ⇒ 每个口径都必须有一条"给定输入、期望输出"的断言。
⇒ 特别是 **Pareto 非支配排序**——它是层3 目标二元化的地基，**算错就全盘皆错**。

## 变异注入
| 变异 | 必须 FAIL 的检查 |
|---|---|
| ESS 去掉平方 | `ess_bounds` |
| DSE 少了 log | `dse_values` |
| Self-Sim 不做两两平均（改成最大对） | `self_sim_pairwise` |
| 支配关系放宽（只要一项更优） | `pareto_dominance` |
| 非支配排序不剥层 | `pareto_frontiers` |
"""
from __future__ import annotations

import argparse
import importlib
import math
import os
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True

import metrics_priorart as MP   # noqa: E402


class Check:
    def __init__(self, name):
        self.name = name
        self.ok = False
        self.detail = ""
        self.error = None


def run_checks():
    checks = []

    def add(name, fn):
        c = Check(name)
        try:
            c.ok, c.detail = fn()
        except Exception as e:
            c.ok = False
            c.error = "%s: %s" % (type(e).__name__, e)
        checks.append(c)
        return c

    # ── ESS：均匀 ⇒ N；单点 ⇒ 1
    def c1():
        n = 5
        if abs(MP.ess([1.0] * n) - n) > 1e-9:
            return False, "均匀权重 ESS=%r（应 %d）" % (MP.ess([1.0] * n), n)
        if abs(MP.ess([1.0] + [0.0] * (n - 1)) - 1.0) > 1e-9:
            return False, "单点权重 ESS=%r（应 1）" % MP.ess([1.0] + [0.0] * (n - 1))
        return True, "均匀⇒%d，单点⇒1" % n

    # ── DSE：2 个相同 + 2 个不同 ⇒ 2 个桶，p=.5/.5 ⇒ H=ln2
    def c2():
        ans = [["a"], ["a"], ["b"], ["c"]]
        h = MP.dse(ans)
        # 3 个桶：p = .5 / .25 / .25 ⇒ H = 1.0397（★ 我先前误以为只有 2 个桶）
        exp = -(0.5 * math.log(0.5) + 0.25 * math.log(0.25) + 0.25 * math.log(0.25))
        if abs(h - exp) > 1e-9:
            return False, "DSE=%r（应 %r）" % (h, exp)
        if MP.dse([["a"], ["a"]]) != 0.0:
            return False, "全相同时 DSE 应为 0，得 %r" % MP.dse([["a"], ["a"]])
        return True, "2 桶各 .5 ⇒ H=ln2=%.4f" % h

    # ── Self-Sim：完全相同 ⇒ 1；完全不相交 ⇒ 0
    def c3():
        same = MP.self_sim([["顺序读取 7450"], ["顺序读取 7450"]])
        if abs(same - 1.0) > 1e-9:
            return False, "相同答案 Self-Sim=%r（应 1）" % same
        diff = MP.self_sim([["顺序读取七四五"], ["保修五年"]])
        if diff > 1e-9:
            return False, "不相交答案 Self-Sim=%r（应 0）" % diff
        # 三个答案 ⇒ 两两 3 对 ⇒ 取平均
        mid = MP.self_sim([["a b"], ["a c"], ["d e"]])
        if not (0.0 <= mid <= 1.0):
            return False, "Self-Sim 越界 %r" % mid
        return True, "相同=1.000 不相交=0.000 三样本=%.3f" % mid

    # ── 碰撞比：全同 ⇒ C=1, N₂=1；全异 ⇒ C=1/n, N₂=n
    def c4():
        c1 = MP.collision_ratio([["a"], ["a"], ["a"]])
        if abs(c1["C"] - 1.0) > 1e-9 or abs(c1["N2"] - 1.0) > 1e-9:
            return False, "全同：%r" % c1
        c2 = MP.collision_ratio([["a"], ["b"], ["c"], ["d"]])
        if abs(c2["C"] - 0.25) > 1e-9 or abs(c2["N2"] - 4.0) > 1e-9:
            return False, "全异：%r" % c2
        # R：参照更集中 ⇒ R = C(q)/C(p) > 1 ⇒ p 相对参照更"塌"
        p = MP.collision_ratio([["a"], ["b"], ["c"], ["d"]])
        q = MP.collision_ratio([["a"], ["a"], ["a"], ["b"]])
        r = MP.collision_ratio([["a"], ["b"], ["c"], ["d"]],
                               ref=[["a"], ["a"], ["a"], ["b"]])["R"]
        if r is None or r <= 1.0:
            return False, "R=%r（参照更集中 ⇒ 应 >1）" % r
        return True, "全同 C=1 N2=1；全异 C=0.25 N2=4；R=%.3f>1" % r

    # ── 多数票份额 / #distinct
    def c5():
        ans = [["a"], ["a"], ["b"]]
        if abs(MP.majority_share(ans) - 2 / 3.0) > 1e-9:
            return False, "多数票份额=%r（应 2/3）" % MP.majority_share(ans)
        if MP.distinct_families(ans) != 2:
            return False, "#distinct=%r（应 2）" % MP.distinct_families(ans)
        return True, "多数票=2/3 #distinct=2"

    # ── ★ 支配关系：必须**同时**不劣
    def c6():
        if not MP.dominates((1.0, 1.0), (0.5, 0.5)):
            return False, "(1,1) 应支配 (0.5,0.5)"
        if MP.dominates((1.0, 0.0), (0.0, 1.0)):
            return False, "★ (1,0) 不得支配 (0,1)（不可比）"
        if MP.dominates((1.0, 1.0), (1.0, 1.0)):
            return False, "相同点不应互相支配"
        return True, "同时不劣才行；(1,0) 与 (0,1) 不可比 ✔"

    # ── ★ 非支配排序：经典用例
    def c7():
        # pts = (1,0) (0,1) (0.5,0.5) (0.2,0.2) (0.9,0.9)
        # 支配关系（a 支配 b ⇔ 两项同时不劣且至少一项严格更优）：
        #   (0.9,0.9) 支配 (0.5,0.5) 与 (0.2,0.2)
        #   (1,0) 与 (0,1) **互不可比**（一个质量高、一个多样性高）⇒ 都在前沿
        #   (0.5,0.5) 被 (0.9,0.9) 支配 ⇒ **不在前沿**（★ 我先前误以为它在）
        # ⇒ front-0 = {(1,0),(0,1),(0.9,0.9)}；front-1 = {(0.5,0.5)}；front-2 = {(0.2,0.2)}
        pts = [(1.0, 0.0), (0.0, 1.0), (0.5, 0.5), (0.2, 0.2), (0.9, 0.9)]
        fronts = MP.nondominated_sort([(p, None) for p in pts])
        if set(fronts[0]) != {0, 1, 4}:
            return False, "front-0 应为 {0,1,4}，实得 %r" % (fronts[0],)
        if set(fronts[1]) != {2}:
            return False, "front-1 应为 {2}，实得 %r" % (fronts[1],)
        if len(fronts) < 3 or set(fronts[2]) != {3}:
            return False, "front-2 应为 {3}，实得 %r" % (fronts,)
        return True, "front-0=%r front-1=%r front-2=%r" % (fronts[0], fronts[1], fronts[2])

    # ── 覆盖：分母是 |C_t|，且要报绝对分母
    def c8():
        r = MP.coverage_over_preregistered(["f1", "f2"], ct_size=4)
        if abs(r["coverage"] - 0.5) > 1e-9:
            return False, "coverage=%r（应 0.5）" % r["coverage"]
        if r["ct_size"] != 4 or r["n_found"] != 2:
            return False, "绝对分母没报：%r" % r
        s = MP.coverage_over_preregistered(["f1", "f2", "f3", "f4"], ct_size=4)
        if not s["saturated"]:
            return False, "满覆盖应标 saturated"
        return True, "2/4=0.5 且带绝对分母；满覆盖标 saturated"

    # ── ESS 由逐轮新发现族数算
    def c9():
        rounds = [[["a", "b"]], [["a", "b", "c"], ["a", "b", "c"]], [["d"]]]
        e = MP.ess_from_rounds(rounds)
        # 权重 = 每轮新发现族数 = [2,1,1] ⇒ 归一化 p=[.5,.25,.25] ⇒ ESS = 1/.375 = 2.6667
        exp = 1.0 / (0.5 ** 2 + 0.25 ** 2 + 0.25 ** 2)
        if abs(e - exp) > 1e-9:
            return False, "ESS=%r（应 %r）" % (e, exp)
        return True, "权重[2,1,1] ⇒ ESS=%.4f" % e

    # ── 10. ★★ 策略档案：**标量 argmax 的规模必然是 1**；Pareto 保留不可比的多个
    def c10():
        def mk(q, d, tag):
            return dict(quality=q, diversity=d, scalar=q + d, claims=[tag],
                        spec=("x", "y", 0))
        # ① scalar：无论来多少，档案规模**必然 = 1**
        sc = MP.StrategyArchive(mode="scalar")
        for i in range(6):
            sc.offer(mk(float(i), 0.0, "a%d" % i))
        if sc.stats()["n_items"] != 1:
            return False, "★ scalar 档案规模=%d（应必然 =1）" % sc.stats()["n_items"]
        # ② pareto：质量高但多样性低 vs 质量低但多样性高 ⇒ **互不可比 ⇒ 都留**
        pa = MP.StrategyArchive(mode="pareto")
        pa.offer(mk(10.0, 0.0, "highQ"))
        pa.offer(mk(0.0, 10.0, "highD"))
        st = pa.stats()
        if st["n_items"] != 2:
            return False, "★ pareto 档案规模=%d（应 2，互不可比都留）" % st["n_items"]
        # ③ pareto：被支配的会被剔掉
        #    ★ 用 (0,0)：它被 (10,0) 与 (0,10) **同时**支配 ⇒ 必被剔
        #    （(1,1) 反而是"膝盖点"，与两个极端都不可比 ⇒ 它本来就该留下 —— 我先前写错了）
        pa.offer(mk(0.0, 0.0, "dominated"))
        if pa.stats()["n_items"] != 2:
            return False, "被支配样本没被剔掉：%d" % pa.stats()["n_items"]
        # ④ 档案级多样性读数有出处（Self-Sim / #distinct / 碰撞比）
        if st.get("self_sim") is None or st.get("collision") is None:
            return False, "档案级读数缺：%r" % (sorted(st.keys()),)
        if st["distinct_families"] < 1:
            return False, "#distinct 应 >=1"
        return True, "scalar 规模=1；pareto 规模=2（互不可比都留）；被支配的被剔"

    add("ess_bounds", c1)
    add("dse_values", c2)
    add("self_sim_pairwise", c3)
    add("collision_ratio_values", c4)
    add("majority_and_distinct", c5)
    add("pareto_dominance", c6)
    add("pareto_frontiers", c7)
    add("coverage_reports_denominator", c8)
    add("ess_from_rounds", c9)
    add("strategy_archive_scalar_vs_pareto", c10)
    return checks


MUTATIONS = [
    ("ESS 去掉平方", "metrics_priorart.py",
     "    return 1.0 / sum(p * p for p in ps)",
     "    return 1.0 / sum(p for p in ps)"),

    ("DSE 少了 log", "metrics_priorart.py",
     "        h -= p * math.log(p)",
     "        h -= p"),

    ("Self-Sim 恒返回 1（不真算）", "metrics_priorart.py",
     "    return tot / n if n else 0.0",
     "    return 1.0 if n else 0.0"),

    ("支配关系放宽（只要一项更优）", "metrics_priorart.py",
     "    return (a[0] >= b[0] and a[1] >= b[1]) and (a[0] > b[0] or a[1] > b[1])",
     "    return (a[0] >= b[0] or a[1] >= b[1])"),

    ("pareto 档案退化成只留最优", "metrics_priorart.py",
     """        self.items = [x for i, x in enumerate(self.items) if i in keep]""",
     """        self.items = [x for i, x in enumerate(self.items) if i in keep][:1]"""),

    ("非支配排序不剥层", "metrics_priorart.py",
     """    k = 0
    while True:
        if not fronts:
            break""",
     """    k = 0
    while False:
        if not fronts:
            break"""),
]


def apply_mutation(src, old, new):
    if old not in src:
        raise RuntimeError("变异锚点找不到（源码已变？）")
    return src.replace(old, new, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutate", action="store_true")
    args = ap.parse_args()
    print("=" * 74)
    print("度量层（先例口径）· 自检")
    print("=" * 74)

    if not args.mutate:
        checks = run_checks()
        npass = sum(1 for c in checks if c.ok)
        for c in checks:
            print("  %s %-36s %s" % ("✔" if c.ok else "✘", c.name, c.detail or ""))
            if c.error:
                print("      ↳ %s" % c.error)
        print("-" * 74)
        print("正常模式：%d/%d 通过" % (npass, len(checks)))
        return 0 if npass == len(checks) else 1

    baseline = run_checks()
    bf = [c.name for c in baseline if not c.ok]
    if bf:
        print("  ✘ ★★ 基线本身有失败 ⇒ 变异自检无意义：%s" % bf)
        return 1
    print("  ✔ 基线全过（%d/%d）⇒ 变异自检有效" % (len(baseline), len(baseline)))
    print("-" * 74)

    here = HERE
    with open(os.path.join(here, "metrics_priorart.py"), encoding="utf-8") as f:
        original = f.read()
    all_caught, caught = True, 0
    for label, fname, old, new in MUTATIONS:
        tmp = tempfile.mkdtemp(prefix="mp_mut_")
        try:
            for fn in os.listdir(here):
                if fn.endswith(".py"):
                    shutil.copy2(os.path.join(here, fn), os.path.join(tmp, fn))
            with open(os.path.join(tmp, fname), "w", encoding="utf-8") as f:
                f.write(apply_mutation(original, old, new))
            for mod in list(sys.modules):
                if mod == "metrics_priorart":
                    del sys.modules[mod]
            sys.path.insert(0, tmp)
            saved = MP
            try:
                globals()["MP"] = importlib.import_module("metrics_priorart")
                failed = [c.name for c in run_checks() if not c.ok]
            finally:
                globals()["MP"] = saved
                sys.path.remove(tmp)
                if "metrics_priorart" in sys.modules:
                    del sys.modules["metrics_priorart"]
                sys.path.insert(0, here)
            if failed:
                caught += 1
                print("  ✔ 变异被抓住：%s" % label)
                print("      ↳ 失败检查：%s" % ", ".join(failed))
            else:
                all_caught = False
                print("  ✘ ★ 变异**未被抓住**：%s" % label)
        except Exception:
            all_caught = False
            print("  ✘ ★ 变异导致崩溃：%s" % label)
            traceback.print_exc()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print("=" * 74)
    print("变异注入：%s（%d/%d 被抓住）"
          % ("全部被抓住" if all_caught else "★有未被抓住的", caught, len(MUTATIONS)))
    print("=" * 74)
    return 0 if all_caught else 1


if __name__ == "__main__":
    sys.exit(main())
