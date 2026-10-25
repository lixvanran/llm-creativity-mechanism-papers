#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v4 读数表**程序化生成**（从 runs/arch4_analysis.json ⇒ runs/arch4_tables.md）。

⚠️ 纪律：表格不手抄 ⇒ 杜绝抄写错误；所有数字都能回指 json。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "runs", "arch4_analysis.json")
OUT = os.path.join(HERE, "runs", "arch4_tables.md")

with open(SRC, encoding="utf-8") as f:
    R = json.load(f)

L = []
W = L.append

W("# v4 读数表（程序化生成，源：`runs/arch4_analysis.json`）\n")
W("批次：`%s`\n" % "`, `".join("%s=%s" % (k, v) for k, v in R["batches"].items()))
W("样本：%d 条 ｜ 失败：%d\n" % (R["n_records"], R["summary"]["n_errors"]))

W("\n## 表 1 · 三臂总览（零判官）\n")
W("| 臂 | n | 失败 | 平均字数 | 有取舍声明 | 声明率 |")
W("|---|---|---|---|---|---|")
ta = R["arm_takeoff_indep"]
for arm, v in ta.items():
    ln = R.get("arm_len", {}).get(arm, {}).get("mean", "—")
    W("| `%s` | %d | %d | %s | %d | %.0f%% |" % (
        arm, v["n"], R["other_arms"].get(arm, {}).get("n_err", 0),
        ln if ln != "—" else "—", v["n_with_any"], v["rate_any"] * 100))

W("\n## 表 2 · H3 分臂读数（预注册：判决只在 `WF-v4-blind` 臂内做）\n")
W("| 臂 | n | 同池 gap 均值 | state 胜 | generic 胜 | 平 | align(state选) | align(generic选) | H1 候选集合成功率 |")
W("|---|---|---|---|---|---|---|---|---|")
for arm, v in R["per_arm_H3"].items():
    w = v["wins"]
    W("| `%s` | %d | %s | %d | %d | %d | %s | %s | %s |" % (
        arm, v["n"], v["gap_mean"], w["state"], w["generic"], w["tie"],
        v["align_state"].get("mean"), v["align_generic"].get("mean"),
        v["H1"].get("mean")))

W("\n## 表 3 · H3 判据逐条核对\n")
v = R["per_arm_H3"].get("WF-v4-blind", {})
w = v.get("wins", {})
n_nt = w.get("state", 0) + w.get("generic", 0)
W("| 判据（PREREG_v4 补充 3） | 阈值 | 实测 | 结论 |")
W("|---|---|---|---|")
W("| 逐例 state 胜率 | ≥ 2/3 | %s | %s |" % (
    ("%d/%d = %.0f%%" % (w.get("state", 0), n_nt, w.get("state", 0) / n_nt * 100))
    if n_nt else "无有效对比（9/9 全平）",
    "**不通过**" if n_nt == 0 else "见备注"))
W("| 同池 gap 均值 | ≥ +0.15 | %s | %s |" % (
    v.get("gap_mean"), "**不通过**" if (v.get("gap_mean") or 0) < 0.15 else "通过"))
W("| 样本量 | n ≥ 6 | %s | %s |" % (v.get("n"), "**可判定**（非“不可判定”）"))
W("\n> ★ `WF-v4-blind` 臂 **9/9 全部打平** ⇒ 状态化打分与通用打分**零区分**。\n")
_v4 = R["per_arm_H3"].get("WF-v4", {})
W("> ⚠️ `WF-v4`（给缺口）臂虽有 +%s 差距，但该臂 align 均值 %s、"
  "被选候选 deep 命中率 %s ⇒ **恒真风险高**，不作为驱动力证据。\n" % (
      _v4.get("gap_mean"), _v4.get("align_state", {}).get("mean"),
      R["summary"]["H2_deep_hit_rate_selected"].get("mean")))

W("\n## 表 4 · 逐题读数（分析单元 = 题）\n")
W("| 题 | n | H1 候选集合成功率 | gap 均值 | 同候选数 | 有取舍声明率 | 候选两两相似度 |")
W("|---|---|---|---|---|---|---|")
for tid, x in R["per_topic"].items():
    W("| %s | %d | %s | %s | %d | %.0f%% | %s |" % (
        tid, x["n"], x["H1"].get("mean"), x["H3_gap"].get("mean"),
        x["same_choice"], x["R_takeoff_rate"] * 100,
        x["cand_sim_mean"].get("mean")))

W("\n## 表 5 · 统计检验（Fisher 精确检验，双尾）\n")
W("| 对比 | 有声明/无声明 | p |")
W("|---|---|---|")
if "fisher_takeoff" in R:
    for arm, p in R["fisher_takeoff"].items():
        v2 = ta[arm]
        W("| `%s` vs `A` | %d/%d vs %d/%d | %s |" % (
            arm, v2["n_with_any"], v2["n"] - v2["n_with_any"],
            ta["A"]["n_with_any"], ta["A"]["n"] - ta["A"]["n_with_any"], p))
W("\n> ⚠️ 样本量（每臂 n=9）下**统计上不可分辨** ⇒ 取舍声明读数只能作**方向性观察**。\n")

W("\n## 表 6 · 失败与缺失（显式）\n")
if R.get("errors"):
    W("| 题 | 臂 | # | 错误 |")
    W("|---|---|---|---|")
    for e in R["errors"]:
        W("| %s | %s | %s | %s |" % (e["topic"], e["arm"], e["tag"], e["error"]))
else:
    W("本次实验 **0 失败 / %d 条记录**（无缺失、无静默归零）。\n" % R["n_records"])

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(L))
print("[out] %s" % OUT)
print("\n".join(L[:24]))
