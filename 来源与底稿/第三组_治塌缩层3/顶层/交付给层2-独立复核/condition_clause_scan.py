# -*- coding: utf-8 -*-
"""★ 条件从句检测（纯程序、零 API、零判官）+ 题级明细

回答两件事：
① 「同族不同文」对里，有多少是【条件不同】⇒ ⇒ 发生率（把"存在"升级成"发生率 X%"）
② in-sample 三策略的【题级明细】（哪 6 题、每题方向）

★ 口径必须写死（可复算）：
  · 「同族不同文对」= 在**同一份答案(record)**内，family_key 相同、但 claim 文本不同的**无序对**
    ⇒ 分母另给一个变体：其中【至少一条承重】的对
  · 「条件从句」= 纯程序抽取的【条件签名】= ①数值/阈值 token 集合 ②比较词 ③条件引导句
    （…时 / …前提下 / 需要… / …除外 / 但书 / 仅当 / 在…情况下 / 除…外）
  · 「条件不同」= 两签名**不相等** 且 **至少一方非空**（否则只是措辞差异，不算条件差异）
"""
import json
import os
import re
import statistics
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = ["main_big", "adv", "fv2", "main"]
OUT = os.path.join(HERE, "condition_clause_report.json")

NUM = re.compile(r"[0-9]+(?:\.[0-9]+)?\s*(?:%|℃|°C|GB|TB|MB/s|IOPS|TBW|元|万|天|日|个月|年|人|项|条|款|米|mm|mg|kcal|kJ)?")
CMP = re.compile(r"(达到|超过|不低于|不超过|高于|低于|以上|以下|以内|以内|至少|最多|不得|应当|必须|仅当|除外|但书|时|前提下|需要|除|以外|内|满|超过)")
GUIDE = re.compile(r"([^，。；：]{0,24}?(时|前提下|需要|除外|但书|仅当|的情况下|的情况下|不低于|不超过|达到|超过)[^，。；]{0,28})")


def fk(card):
    return "|".join(sorted(card.get("supports_conclusions") or []))


def cond_sig(text):
    """★ 条件签名：数值 token 集合 + 比较词集合 + 条件引导句集合"""
    t = str(text or "")
    nums = set(x.strip() for x in NUM.findall(t) if x.strip())
    cmps = set(CMP.findall(t))
    guides = set(m.group(0).strip() for m in GUIDE.finditer(t) if m.group(0).strip())
    return nums, cmps, guides


def differs(a, b):
    na, ca, ga = a
    nb, cb, gb = b
    if na == nb and ca == cb and ga == gb:
        return False, "identical_signature"
    # 至少一方非空 ⇒ 才有"条件"
    if not (na or ca or ga) and not (nb or cb or gb):
        return False, "both_empty_no_condition"
    return True, "diff"


def main():
    total_pairs = 0
    cond_diff = 0
    lb_pairs = 0
    lb_cond_diff = 0
    per_run = {}
    examples = []
    for run in RUNS:
        p = os.path.join(HERE, "runs", run, "arms.jsonl")
        if not os.path.exists(p):
            continue
        rt = dict(pairs=0, cond_diff=0, lb_pairs=0, lb_cond_diff=0)
        for line in open(p, encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            cards = r.get("cards") or []
            by = defaultdict(list)
            for c in cards:
                f = fk(c)
                if f:
                    by[f].append(c)
            for f, cs in by.items():
                if len(cs) < 2:
                    continue
                for i in range(len(cs)):
                    for j in range(i + 1, len(cs)):
                        t1 = str(cs[i].get("claim") or "")
                        t2 = str(cs[j].get("claim") or "")
                        if t1 == t2:
                            continue
                        total_pairs += 1
                        rt["pairs"] += 1
                        s1 = cond_sig(t1)
                        s2 = cond_sig(t2)
                        d, why = differs(s1, s2)
                        if d:
                            cond_diff += 1
                            rt["cond_diff"] += 1
                        lb = bool(cs[i].get("load_bearing")) or bool(cs[j].get("load_bearing"))
                        if lb:
                            lb_pairs += 1
                            rt["lb_pairs"] += 1
                            if d:
                                lb_cond_diff += 1
                                rt["lb_cond_diff"] += 1
                        if d and len(examples) < 12:
                            examples.append(dict(run=run, arm=r.get("arm"), task=r.get("task_id"),
                                                  family_key=f,
                                                  lb=(cs[i].get("load_bearing"), cs[j].get("load_bearing")),
                                                  a=t1[:200], b=t2[:200]))
        per_run[run] = rt

    rep = {
        "definition": {
            "同族不同文对": "同一份答案(record)内 family_key 相同但 claim 文本不同的无序对",
            "条件从句": "纯程序抽取：①数值/阈值 token 集合 ②比较词集合 ③条件引导句集合（…时/…前提下/需要…/除外/但书/仅当/在…情况下）",
            "条件不同": "两签名不相等 且 至少一方非空（否则只是措辞差异）",
            "零成本": "纯程序、零 API、零判官",
        },
        "denominators": {
            "all_same_family_different_text_pairs": total_pairs,
            "pairs_with_at_least_one_load_bearing": lb_pairs,
        },
        "rates": {
            "condition_diff_over_all_pairs": round(cond_diff / float(total_pairs), 4) if total_pairs else None,
            "condition_diff_over_lb_pairs": round(lb_cond_diff / float(lb_pairs), 4) if lb_pairs else None,
            "counts": {"condition_diff": cond_diff, "lb_condition_diff": lb_cond_diff},
        },
        "per_run": per_run,
        "examples": examples,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)

    print("★ 条件从句检测（全量，纯程序）")
    print("  分母：同族不同文对 = %d（其中至少一条承重 = %d）" % (total_pairs, lb_pairs))
    print("  条件不同：%d ⇒ 发生率 = %.1f%%" % (cond_diff, 100.0 * cond_diff / max(total_pairs, 1)))
    print("  （限承重对）%d ⇒ %.1f%%" % (lb_cond_diff, 100.0 * lb_cond_diff / max(lb_pairs, 1)))
    for r, v in per_run.items():
        print("    %-9s pairs=%-4d cond_diff=%-4d (%.1f%%)  lb_pairs=%-4d lb_cond=%d"
              % (r, v["pairs"], v["cond_diff"], 100.0 * v["cond_diff"] / max(v["pairs"], 1),
                 v["lb_pairs"], v["lb_cond_diff"]))

    # ── 题级明细 ──
    print("\n★ in-sample 题级明细（W_train_L3，6 题 × 3 策略）")
    R = os.path.join(HERE, "runs")
    rows = {}
    for v in ("merged", "lookup", "uniform"):
        f = os.path.join(R, "valid_%s" % v, "arms.jsonl")
        if not os.path.exists(f):
            continue
        for line in open(f, encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("arm") != "W_train_L3":
                continue
            hit = bool((r.get("pc") or {}).get("hit"))
            rows.setdefault(r.get("task_id"), {})[v] = hit
    print("  %-6s %-8s %-8s %-8s  %s" % ("题", "merged", "lookup", "uniform", "方向"))
    for t in sorted(rows):
        d = rows[t]
        cells = []
        for v in ("merged", "lookup", "uniform"):
            cells.append("踩坑" if d.get(v) else "干净")
        if d.get("merged") and not (d.get("lookup") or d.get("uniform")):
            dirn = "★ merged 独好"
        elif d.get("merged") and d.get("lookup") and d.get("uniform"):
            dirn = "三者皆踩"
        elif not d.get("merged"):
            dirn = "merged 干净"
        else:
            dirn = "—"
        print("  %-6s %-8s %-8s %-8s  %s" % (t, cells[0], cells[1], cells[2], dirn))
    print("  ⇒ 提示：6 题 = 6 个 bit，读者可自行判断强度（主会话要求）")


if __name__ == "__main__":
    main()
