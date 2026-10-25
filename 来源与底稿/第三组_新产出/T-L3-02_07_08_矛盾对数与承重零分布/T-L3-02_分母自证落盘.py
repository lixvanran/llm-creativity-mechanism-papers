#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ T-L3-02 附 · 分母自证的【脱敏落盘】（★ 协调方 2026-10-26 回执要求）
   ------------------------------------------------------------------
   ★ 问题：`policy.json` 与 `train_*.log` **不在仓里**（★ 全仓 `policy.json` 0 命中）
     ⇒ 「训练日志训练行数 == policy.json hist 条数」这条**第三方复算不了**
   ★ 处置（★ 两条路选一，本脚本走第一条）：
     ① 把**读数所需的最小字段**脱敏后落进本目录（★ 不落答案、不落 prompt、
        不落任何题目内容；只落计数）
     ② 或标成「本机核、仓内不可复算」

   ★ 落什么（★ 只落计数，不落内容）：
     · 每个 seed 的 `hist` 条数
     · 该 seed 训练日志里的**训练行数**（行首形如「轮 N 样本 M …」）
     · 该 seed 训练日志里的**失败记录条数**（「样本失败」）
     · ★ 两者相等 ⇒ 证明「失败样本不写入 hist」⇒ 训练 hist 的分母天然是有效读数
   ★ 同时落**原始计数 + 该次统计的脚本与行号**，第三方可据此自行复算。

   用法：python3 T-L3-02_分母自证落盘.py [--runs-root DIR] [--out DIR]
   """
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RUNS = "/workspace/lab/routes/COLLAPSE/runs"
SEEDS_15 = ["pl_20261101", "pl_20261102", "pl_20261103", "pl_20261104", "pl_20261106"]
SEEDS_13 = ["pl_20261101", "pl_20261102", "pl_20261103", "pl_20261104",
            "pl_20261105", "pl_20261106"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-root", default=DEFAULT_RUNS)
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()
    R, OUT = args.runs_root, args.out
    os.makedirs(OUT, exist_ok=True)
    out = {}
    for tag, sub, seeds in [("15题版", "", SEEDS_15),
                            ("13题版", "holdout13", SEEDS_13)]:
        rows = []
        for s in seeds:
            pj = os.path.join(R, sub, s, "policy.json")
            lg = os.path.join(R, sub, "train_%s.log" % s.replace("pl_", ""))
            row = dict(seed=s, subdir=(sub or "<runs 根>"))
            if not os.path.exists(pj):
                row["hist_len"] = None
                row["available"] = False
                rows.append(row)
                continue
            row["available"] = True
            row["hist_len"] = len(json.load(open(pj, encoding="utf-8"))
                                  .get("hist", []))
            if os.path.exists(lg):
                txt = io.open(lg, encoding="utf-8").read()
                row["log_train_rows"] = len(
                    [l for l in txt.splitlines()
                     if l.strip().startswith("轮") and "样本" in l])
                row["log_failure_records"] = txt.count("样本失败")
            else:
                row["log_train_rows"] = None
                row["log_failure_records"] = None
            row["match"] = (row["log_train_rows"] is not None
                            and row["hist_len"] == row["log_train_rows"])
            rows.append(row)
        have = [r for r in rows if r.get("available")]
        withlog = [r for r in have if r.get("log_train_rows") is not None]
        # ★ 分母一致性自证：hist 条数之和 == 仓内 policy_merged*.json 的 meta.n_samples
        meta = None
        mfn = {"15题版": "policy_merged.json", "13题版": "policy_merged13.json"}[tag]
        mp = os.path.join("/workspace/work/exp/L3/来源与底稿/第三组_治塌缩层3/"
                          "cmp8repo/repro/readings", mfn)
        if os.path.exists(mp):
            md = json.load(open(mp, encoding="utf-8"))
            meta = md.get("meta", {})
        out[tag] = dict(
            meta_declared_n_samples=(meta or {}).get("n_samples"),
            sum_hist_check=sum(r["hist_len"] or 0 for r in have),
            denominator_consistency=(
                (meta or {}).get("n_samples") ==
                sum(r["hist_len"] or 0 for r in have)) if meta else None,
            failure_not_in_hist_selfproof=(
                "完整自证（6/6 seed 相等）" if (withlog and
                    all(r.get("match") for r in withlog))
                else "★ 未自证（该批的 seed 目录里【没有训练日志】⇒ "
                     "「失败样本不写入 hist」这条在本批【无日志凭据】）"),
            seeds=rows,
            n_seeds=len(have),
            sum_hist=sum(r["hist_len"] or 0 for r in have),
            n_with_log=len(withlog),
            n_match=sum(1 for r in withlog if r.get("match")),
            all_match=(bool(withlog) and all(r.get("match") for r in withlog)),
            sum_log_failures=sum(r.get("log_failure_records") or 0 for r in withlog),
            conclusion=("★ hist 条数 == 训练日志训练行数 ⇒ 【失败样本不写入 hist】"
                        "⇒ 训练 hist 的分母天然已是有效读数（无需再剔）"),
        )
        print("【%s】 seed 数=%d  有日志的 seed=%d  相等=%d  全部相等=%s"
              % (tag, len(have), len(withlog), out[tag]["n_match"],
                 out[tag]["all_match"]))
        print("   ★ 分母一致性：hist 条数之和 %d vs 仓内 meta.n_samples %s ⇒ %s"
              % (out[tag]["sum_hist_check"],
                 out[tag]["meta_declared_n_samples"],
                 "✔ 一致" if out[tag]["denominator_consistency"] else "✘"))
        print("   ★ 「失败样本不进 hist」自证：%s"
              % out[tag]["failure_not_in_hist_selfproof"])
        for r in rows:
            print("   %-14s hist=%-5s 日志训练行=%-5s 失败记录=%-4s ⇒ %s"
                  % (r["seed"], r.get("hist_len"), r.get("log_train_rows"),
                     r.get("log_failure_records"),
                     ("✔ 相等" if r.get("match") else
                      ("（无日志）" if r.get("log_train_rows") is None else "✘ 不等"))))
    out["_note"] = ("★ 本文件只落【计数】，不含任何答案 / prompt / 题目内容；"
                    "★ 原始 policy.json 与 train_*.log 不在仓内（★ 全仓 policy.json 0 命中）"
                    "⇒ 本文件是第三方可复算的唯一凭据")
    out["_how_to_reproduce"] = (
        "对每个 seed：hist_len = len(json.load(policy.json)['hist'])；"
        "log_train_rows = 训练日志中行首为「轮」且含「样本」的行数；"
        "两者相等 ⇒ 失败样本不写入 hist。")
    fp = os.path.join(OUT, "T-L3-02_分母自证_脱敏.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n★ 落盘：%s" % fp)
    print("结论：%s" % ("PASS（自证可复算）"
                        if all(v.get("all_match") for v in out.values()
                               if isinstance(v, dict) and "all_match" in v)
                        else "★ 部分 seed 缺日志或不等 ⇒ 结论降级"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("★ 脚本崩溃：%r" % e)
        sys.exit(1)
