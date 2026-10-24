# -*- coding: utf-8 -*-
"""★ 口径自查 + 重算：我的「模态数」到底是不是 family_key 口径？

★ 结论（2026-10-25 实测）：**不是**。
  `align_c1.py:27` / `nested_calib_self.py:80` 都是 `"|".join(sorted([c]))` 对 **claim 字符串**去重
  ⇒ ⇒ **算的是「不同断言文本的条数」**（同一条结论的不同措辞会被算成多个）
  ⇒ ⇒ **代码注释"覆盖多少个不同结论"是错的** ⇒ ⇒ **与层2 的 family_key 口径不可直接比**

本脚本用卡里的 `supports_conclusions`（零 API）**重算成真正的结论族口径**，
并与原读数并排，看**排序是否存活**。

口径（与层2 的 `family_three_calibers` 对齐）：
  · n_families_loadbearing : 承重卡 ⇒ family_key 集合去重
  · n_families_all         : 全部卡 ⇒ family_key 集合去重（含 '' 聚合族）
  · n_uncovered            : 承重 ∧ supports_conclusions==[]  ⇒ 单列
  · coverage               : 1 − n_uncovered / n_load_bearing
"""
import collections
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def family_key(card):
    """族键 = supports_conclusions 排序后用 | 连接（与 routes/C/optimizer.py:75 同口径）"""
    return "|".join(sorted(card.get("supports_conclusions") or []))


def three_calibers(cards):
    lb = [c for c in cards if c.get("load_bearing")]
    allf = {family_key(c) for c in cards}
    lbf = {family_key(c) for c in lb}
    unc = [c for c in lb if not (c.get("supports_conclusions") or [])]
    n_lb = len(lb)
    cov = (1.0 - len(unc) / float(n_lb)) if n_lb else None
    return dict(n_families_loadbearing=len(lbf), n_families_all=len(allf),
                n_uncovered=len(unc), n_load_bearing=n_lb,
                coverage=round(cov, 3) if cov is not None else None)


def literal_modal(claims):
    """原口径：claim 字符串去重（= 不同断言文本条数）"""
    fams = set()
    for c in claims:
        for s in c:
            fams.add("|".join(sorted([str(s)])))
    return len(fams)


def main():
    out = {}
    for run in ("main_big", "adv", "fv2"):
        p = os.path.join(HERE, "runs", run, "arms.jsonl")
        if not os.path.exists(p):
            continue
        recs = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        by = collections.defaultdict(list)
        for r in recs:
            cards = r.get("cards") or []
            claims = [list(x.get("claims") or []) for x in (r.get("paths") or []) if isinstance(x, dict)]
            if not cards and not claims:
                continue
            by[r.get("arm")].append((cards, claims))
        run_out = {}
        for arm, items in sorted(by.items()):
            cal = [three_calibers(c) for c, _ in items]
            lit = [literal_modal(cl) for _, cl in items if cl]
            run_out[arm] = dict(
                n=len(items),
                fam_loadbearing=round(statistics.median([x["n_families_loadbearing"] for x in cal]), 2),
                fam_all=round(statistics.median([x["n_families_all"] for x in cal]), 2),
                uncovered=round(statistics.median([x["n_uncovered"] for x in cal]), 2),
                coverage=round(statistics.median([x["coverage"] for x in cal if x["coverage"] is not None]), 3)
                if any(x["coverage"] is not None for x in cal) else None,
                literal_modal=round(statistics.median(lit), 2) if lit else None,
            )
        out[run] = run_out
        print("═" * 86)
        print("【run=%s】  ★ 原口径(断言文本数) vs 重算口径(结论族) —— 排序是否存活" % run)
        print("  %-16s %5s %12s %10s %10s %10s" % ("臂", "n", "原:断言文本数", "新:承重族", "新:全卡族", "未覆盖"))
        for arm, v in run_out.items():
            print("  %-16s %5d %12s %10s %10s %10s" % (
                arm, v["n"], v["literal_modal"], v["fam_loadbearing"],
                v["fam_all"], v["uncovered"]))
        # 排序是否存活
        arms = [a for a, v in run_out.items() if v["literal_modal"] is not None]
        if len(arms) >= 2:
            o1 = sorted(arms, key=lambda a: -(run_out[a]["literal_modal"] or 0))
            o2 = sorted(arms, key=lambda a: -(run_out[a]["fam_loadbearing"] or 0))
            o3 = sorted(arms, key=lambda a: -(run_out[a]["fam_all"] or 0))
            print("  原排序(大→小):", " > ".join(o1))
            print("  承重族排序    :", " > ".join(o2))
            print("  全卡族排序    :", " > ".join(o3))
            print("  ★ 承重族排序与原排序一致?", o1 == o2, "｜全卡族一致?", o1 == o3)
    with open(os.path.join(HERE, "family_recompute.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n→ family_recompute.json 已落盘")


if __name__ == "__main__":
    main()
