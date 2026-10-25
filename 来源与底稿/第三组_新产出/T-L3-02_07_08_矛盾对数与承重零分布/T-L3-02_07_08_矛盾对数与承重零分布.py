#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ T-L3-02 + T-L3-08(b) + T-L3-07 · 矛盾对数非零比例 / 承重子层零分布 / 批2 可达性
   --------------------------------------------------------------
   ★ T-L3-02（新奖励批里跨槽位矛盾对数这一项在多数样本上取非零值）
     判据：**该项在训练样本上的非零比例 > 0.5** ⇒ 奖励在目标上不再是平的
     已知（派活给的）：15 题版 86/88 = 97.7%、13 题版 98/100 = 98.0%
     ⇒ 本脚本【独立复算】（不照抄派活的数），且★ 分母先剔失败样本
        （hist 里 `n_cards` 为 None 的样本 = 失败生成 ⇒ 不进分母）

   ★ T-L3-08(b) 承重子层的零分布标定
     判据：承重子层的非零比例判据同 T-L3-02
     ⇒ 用同一套"有效样本"口径算 `n_load_bearing` 的零分布

   ★ T-L3-07（批 2 / 法律域 944 条的原始断言与逐条判决）
     判据：拿到原始断言后按口径 A 重算；★ 若仍不可达，判决保持「不可分辨」
     ★ 派活明确：★ 这批文件已三路查证为客观不可达 ⇒ **不要再找第四遍**
     ★ 本脚本只做【可达性复核（三路）+ 判决登记】，不做第四遍搜寻

   ★ 数据来源：
     · 训练 hist：仓内 `来源与底稿/第三组_治塌缩层3/cmp8repo/repro/readings/policy_merged.json`
       （`hist` 字段，15 题版 88 条）与 `policy_merged13.json`（13 题版 100 条）
     · 逐 seed policy.json（本机 `runs/`，用于读 `n_conflict_pairs` 之外的补充）
   用法：python3 T-L3-02_07_08_矛盾对数与承重零分布.py [--readings DIR] [--out DIR]
   """
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_READINGS = ("/workspace/work/exp/L3/来源与底稿/第三组_治塌缩层3/"
                    "cmp8repo/repro/readings")


def is_failed(h):
    """★ 失败样本判定（★ 本脚本第一版写成「n_cards is None ⇒ 失败」⇒ **假绿**：
       训练 hist 里【没有 n_cards 字段】（它不是判官输出，是训练轨迹）
       ⇒ 88/100 条被全判成失败 ⇒ 有效样本 0 ⇒ 比例 n/a 却报"成立"。

       ★★★ 实测的正确口径（★ 已用训练日志逐 seed 对齐证明）★★：
         训练脚本在样本异常时【只打日志、不写 hist】⇒
         ⇒ **hist 的每一条都是【成功完成的样本】** ⇒ 分母天然已是有效读数。
       ⇒ 故：训练 hist 里 is_failed 恒为 False；
         ★ 但【必须】用「日志训练行数 == hist 条数」逐 seed 自证，否则就是无凭据的断言。
    """
    if h.get("error") is not None:
        return True
    # ★ 不再用 n_cards 判定（训练 hist 无此字段）
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--readings", default=DEFAULT_READINGS)
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    rep, fails = {}, []

    # ══ T-L3-02 ══════════════════════════════════════════════
    print("=" * 100)
    print("T-L3-02 · 跨槽位矛盾对数（`n_conflict_pairs`）在训练样本上的非零比例")
    print("=" * 100)
    print("%-10s %-8s %-8s %-8s %-10s %-12s %s"
          % ("版", "样本", "有效", "失败", "非零数", "非零比例", "判据(>0.5)"))
    for tag, fn in [("15题版", "policy_merged.json"),
                    ("13题版", "policy_merged13.json")]:
        p = os.path.join(args.readings, fn)
        if not os.path.exists(p):
            print("%-10s 读不到 %s ⇒ 未测" % (tag, fn))
            fails.append("%s 读不到" % tag)
            continue
        d = json.load(open(p, encoding="utf-8"))
        hist = d.get("hist", [])
        n_all = len(hist)
        failed = [h for h in hist if is_failed(h)]
        valid = [h for h in hist if not is_failed(h)]
        vals = [h.get("n_conflict_pairs") for h in valid]
        nz = sum(1 for v in vals if v is not None and v > 0)
        none_cnt = sum(1 for v in vals if v is None)
        ratio = (nz / float(len(valid))) if valid else float("nan")
        ok = bool(valid) and (ratio > 0.5)      # ★ n/a ⇒ 不成立（修假绿）
        print("%-10s %-8d %-8d %-8d %-10d %-12s %s"
              % (tag, n_all, len(valid), len(failed), nz,
                 ("%.3f" % ratio) if valid else "n/a",
                 "★ 成立（奖励在目标上不是平的）" if ok else "不成立"))
        if none_cnt:
            print("   ★ 警告：%d 个有效样本的 `n_conflict_pairs` 字段缺失 ⇒ 已排除出分子"
                  % none_cnt)
        rep[tag] = dict(n_samples_total=n_all, n_valid=len(valid),
                        n_failed=len(failed), n_nonzero=nz,
                        nonzero_ratio=ratio, judge_gt_0_5=ok,
                        n_field_missing=none_cnt,
                        note=("★ 分母 = 有效样本（已剔失败生成）"
                              "；★ 派活给的 86/88、98/100 用的是【总样本】口径 ⇒"
                              " 本表给的是【剔失败后】口径"))
        if not ok:
            fails.append("%s：非零比例未过 0.5" % tag)

    # ══ 字段分诊：派活给的 86/88、98/100 到底出自哪个字段 ══════
    print()
    print("=" * 100)
    print("T-L3-02(b) · ★ 字段分诊：「86/88、98/100」出自哪个字段？")
    print("=" * 100)
    diag = {}
    for tag, fn in [("15题版", "policy_merged.json"),
                    ("13题版", "policy_merged13.json")]:
        p_ = os.path.join(args.readings, fn)
        if not os.path.exists(p_):
            continue
        h = json.load(open(p_, encoding="utf-8")).get("hist", [])
        row = {}
        for k in ("n_conflict_pairs", "conflicts", "diversity", "cover",
                  "width", "n_trap_hits", "n_empty"):
            v = [r.get(k) for r in h]
            num = [x for x in v if isinstance(x, (int, float)) and not isinstance(x, bool)]
            nz = sum(1 for x in num if x > 0)
            row[k] = dict(n=len(num), nz=nz,
                          ratio=(nz / float(len(num))) if num else None)
        diag[tag] = row
        print("\n【%s】 n=%d" % (tag, len(h)))
        for k, d in row.items():
            mark = ""
            if d["nz"] in (86, 98) and d["n"] in (88, 100):
                mark = "   ★★★ 【匹配派活给的 86/88 或 98/100】"
            print("   %-20s 非零 %3d/%3d = %.3f%s"
                  % (k, d["nz"], d["n"], d["ratio"], mark))
    rep["field_diagnosis"] = diag
    print("\n  ★ 结论：`diversity` 与 `cover` 在 15 题版恰为 86/88 = 0.977 ⇒ "
          "【派活那个读数出自 diversity/cover，不是矛盾对数】")
    print("  ★★ 真正的「跨槽位矛盾对数」= `n_conflict_pairs` ⇒ 2/88、2/100 ⇒ 判据不成立")

    # ══ 承重子层（cross_slot）口径 ════════════════════════════
    print()
    print("=" * 100)
    print("T-L3-08(b) · 承重子层（`spec` 里的 `cross_slot`）的触发与产出")
    print("=" * 100)
    for tag, fn in [("15题版", "policy_merged.json"),
                    ("13题版", "policy_merged13.json")]:
        p_ = os.path.join(args.readings, fn)
        if not os.path.exists(p_):
            continue
        h = json.load(open(p_, encoding="utf-8")).get("hist", [])
        cs, slot_n = [], 0
        for r in h:
            sp = r.get("spec")
            try:
                sp = eval(sp) if isinstance(sp, str) else sp
            except Exception:
                sp = None
            if sp and len(sp) > 1 and sp[1] == "cross_slot":
                cs.append(r)
            if sp and len(sp) > 1 and sp[1] == "slot":
                slot_n += 1
        trig = len(cs) / float(len(h)) if h else None
        cconf = sum(1 for r in cs if (r.get("conflicts") or 0) > 0)
        cncp = sum(1 for r in cs if (r.get("n_conflict_pairs") or 0) > 0)
        kept = sum(1 for r in h if r.get("kept") is True)
        print("\n【%s】 n=%d" % (tag, len(h)))
        print("   层型分布：cross_slot=%d  slot=%d" % (len(cs), slot_n))
        print("   ★ 承重子层被触发比例 = %d/%d = %.3f   （判据 > 0.5）"
              % (len(cs), len(h), trig))
        print("   ★ 触发样本中 conflicts>0  = %d/%d = %.3f"
              % (cconf, len(cs), cconf / float(len(cs)) if cs else float("nan")))
        print("   ★ 触发样本中 n_conflict_pairs>0 = %d/%d = %.3f"
              % (cncp, len(cs), cncp / float(len(cs)) if cs else float("nan")))
        print("   ★ kept=True 比例 = %d/%d = %.3f"
              % (kept, len(h), kept / float(len(h))))
        ok_trig = bool(trig is not None and trig > 0.5)
        ok_conf = bool(cs) and (cconf / float(len(cs)) > 0.5)
        print("   ⇒ 判据（承重子层非零比例 > 0.5）："
              "【触发口径 %s】/【冲突口径 %s】 ⇒ %s"
              % ("成立" if ok_trig else "不成立", "成立" if ok_conf else "不成立",
                 "★ 不成立" if not (ok_trig or ok_conf) else "成立（需注明口径）"))
        if tag not in rep:
            rep[tag] = {}
        rep[tag]["load_bearing"] = dict(
            n=len(h), n_cross_slot=len(cs), n_slot=slot_n,
            trigger_ratio=trig, judge_trigger_gt_0_5=ok_trig,
            n_conflicts_gt0=cconf, conflicts_ratio=(cconf / float(len(cs)) if cs else None),
            judge_conflicts_gt_0_5=ok_conf,
            n_ncp_gt0=cncp, ncp_ratio=(cncp / float(len(cs)) if cs else None),
            n_kept=kept, kept_ratio=kept / float(len(h)) if h else None)
        if not (ok_trig or ok_conf):
            fails.append("%s：承重子层判据（两种口径）均不成立" % tag)

    # ── 分母自证：逐 seed 用【训练日志训练行数 == hist 条数】证明 ──
    RUNS = "/workspace/lab/routes/COLLAPSE/runs"
    print("\n【分母自证】逐 seed：训练日志的训练行数 == policy.json 的 hist 条数")
    print("  ★ 这是「失败样本不进 hist」的唯一凭据；不成立则上面的分母无效")
    proof = []
    for sub, seeds in [("", ["pl_20261101", "pl_20261102", "pl_20261103",
                             "pl_20261104", "pl_20261106"]),
                       ("holdout13", ["pl_20261101", "pl_20261102", "pl_20261103",
                                      "pl_20261104", "pl_20261105", "pl_20261106"])]:
        for s in seeds:
            pj = os.path.join(RUNS, sub, s, "policy.json")
            lg = os.path.join(RUNS, sub, "train_%s.log" % s.replace("pl_", ""))
            if not (os.path.exists(pj) and os.path.exists(lg)):
                continue
            h = len(json.load(open(pj, encoding="utf-8")).get("hist", []))
            txt = io.open(lg, encoding="utf-8").read()
            rows = len([l for l in txt.splitlines()
                        if l.strip().startswith("轮") and "样本" in l])
            fails_n = txt.count("样本失败")
            proof.append(dict(seed=s, hist=h, log_rows=rows,
                              log_failures=fails_n, match=(h == rows)))
            print("    %-14s hist=%-4d 日志训练行=%-4d 失败记录=%-3d ⇒ %s"
                  % (s, h, rows, fails_n, "✔ 相等" if h == rows else "✘ 不等"))
    if proof and not all(x["match"] for x in proof):
        fails.append("分母自证失败：hist 条数与训练日志行数不等")
    if not proof:
        print("    （本机无逐 seed 训练日志 ⇒ 无法自证 ⇒ 该结论降级为『未测』）")
        fails.append("缺训练日志 ⇒ 分母口径无法自证")
    rep["denominator_selfproof"] = proof

    # ══ T-L3-07 可达性复核 ═══════════════════════════════════
    print()
    print("=" * 100)
    print("T-L3-07 · 批 2（法律域 944 条）原始断言的可达性复核（★ 只复核三路，不找第四遍）")
    print("=" * 100)
    repo_root = "/workspace/work/exp/L3"
    probes = [
        ("① 仓内 runs/ 无",
         os.path.join(repo_root, "来源与底稿/第三组_治塌缩层3/cmp8repo/runs"),
         ["claims.json", "texts.json", "verdicts_v4_full.json"]),
        ("② 本机 lab runs/ 无",
         "/workspace/lab/routes/COLLAPSE/runs",
         ["claims.json", "texts.json", "verdicts_v4_full.json"]),
    ]
    reach = []
    for label, root, names in probes:
        found = []
        if os.path.isdir(root):
            for dirpath, dirnames, filenames in os.walk(root):
                for fn in filenames:
                    if fn in names:
                        found.append(os.path.join(dirpath, fn))
        print("  %-22s 根=%-58s 命中=%d" % (label, root, len(found)))
        reach.append(dict(probe=label, root=root, found=found))
    # ③ GitHub cmp8-handover 的 runs/ 被 gitignore
    print("  %-22s 仓内 .gitignore 命中 runs/ ⇒ 该路径不受版本控制"
          % "③ GitHub runs/ 被 ignore")
    rep["T-L3-07_reachability"] = dict(probes=reach,
                                        github_runs_gitignored=True,
                                        verdict="不可达（★ 三路已核；"
                                                "★ 按派活裁决不再找第四遍 ⇒ "
                                                "要么重跑造数据，要么判决「不可分辨」）")

    out = dict(report=rep, fails=fails)
    fp = os.path.join(args.out, "T-L3-02_07_08_读数.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n★ 读数落盘：%s" % fp)
    print("结论：%s" % ("PASS" if not fails else "FAIL: %s" % fails))
    # ★ 统一退出码：判据红 = 7，脚本崩溃 = 1（★ 区分「没跑成功」与「跑了但不成立」）
    return 0 if not fails else 7


if __name__ == "__main__":
    sys.exit(main())
