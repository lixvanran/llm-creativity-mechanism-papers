#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ T-L3-03 + T-L3-06 · 三条代码级发现在【产出批②那一版代码】上是否成立
   --------------------------------------------------------------
   ★ T-L3-03（三条代码级发现）：
     ① 特征维数
     ② `f[6]` 的写入顺序
     ③ 候选集是否含 `MERGE`
   ★ T-L3-06（修复前版本的代码；★ 派活说「该行在本仓任何源码里都不存在，
              全仓零命中」⇒ **判据：拿到可逐字引用的修复前代码**）

   ★★★ 关键突破：★★ 「全仓零命中」只对【当前工作树】成立；
     ★★ **git 全历史里有** ⇒ 用 `git show <commit>:<path>` 取回逐字原文。
     ★ 命中位置：**`cmp8/creativity_lab/ops.py`**（★ 不是治塌缩层3 的文件）
     ★ 修复前 commit：**`777a5fe`**（`docs(cmp8): 完整执行树 + 交接文件`）
     ★ 修复后 commit：**`11f3f27`** 等（含「修 f[6] 索引冲突（2026-10-21）」注释）

   ★★ 三条发现在【修复前那一版】上的核对结果：
     ① 特征维数 = **14**（`f = [0.0] * 14`）⇒ ★ 与"57 维"**不是同一套特征**
        （57 维是治塌缩层3 的 `ActionPolicy` 维数；14 维是 cmp8 执行树的 op 特征）
        ⇒ ★ **两条线要分开登记**，不能互相代入
     ② `f[6]` 的写入顺序：★ **有冲突** ⇒ 修复前 `f[OPS.index(op)] = 1.0` 先写
        （STOP 落在索引 6），★ 之后 `f[6] = min(depth/6.0, 1.0)` **又写一次** ⇒ **覆盖**
        ⇒ ★ 机制（修复后注释原文）：
          - STOP 的 one-hot 被 depth 覆盖 ⇒ **STOP 永远选不中**（只有 ε 能触发）
          - depth 对**所有** op 是同一个值 ⇒ softmax 里是**公共常数** ⇒ **完全抵消、零作用**
          - 实测：STOP 在 depth=3 时 `f[6] = 0.5`（应为 1.0）
     ③ 候选集是否含 `MERGE`：★ **不含** ⇒ `OPS` 是 7 个算子（索引 0..6），
        **合并（MERGE）是执行树上的一个阶段/边，不是候选算子**
        ⇒ ★ 治塌缩层3 那条线的"合并方式"在 `mm` 维度（mechanical/packet/vote），
        **与 cmp8 执行树的 MERGE 不是同一个东西** ⇒ 不能混谈

   ★ 用法：python3 T-L3-03_06_代码级发现核验.py [--repo DIR] [--out DIR]
   """
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO = "/workspace/lab/cmp8repo"

# ★ 修复前 / 后 的 commit（★ 由 `git log -S` 定位，不是手填）
BEFORE_COMMIT = "777a5fe"
AFTER_COMMITS = ["11f3f27", "e95d186", "03640d5"]
OPS_PATH = "cmp8/creativity_lab/ops.py"

# ★ 产出批② 的候选：按 arms.jsonl 的 mtime 排序，取第二个
BATCH_TIMES = {
    "main": "2026-10-23 01:39",
    "main_mm25": "2026-10-23 08:04",
    "main_grok": "2026-10-23 06:58",
    "fv2": "2026-10-24 02:10",
    "main_big": "2026-10-24 02:54",
    "adv": "2026-10-24 10:23",
}


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo] + list(args),
                       capture_output=True, text=True, timeout=180)
    return r.returncode, r.stdout, r.stderr


def show_file(repo, commit, path):
    rc, out, err = git(repo, "show", "%s:%s" % (commit, path))
    return out if rc == 0 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()
    repo = args.repo
    os.makedirs(args.out, exist_ok=True)
    rep = {}
    fails = []

    # ── 步骤 0：证明「git 全历史里有 f[6]」（★ 派活说全仓零命中）──
    rc, out, err = git(repo, "log", "--all", "--oneline", "-S" "f[6]")
    hits = [l for l in out.splitlines() if l.strip()]
    rep["git_all_history_f6_hits"] = len(hits)
    rep["git_all_history_f6_commits"] = hits[:12]
    print("① git 全历史搜 `f[6]`：命中 %d 个 commit ⇒ ★ 派活说的"
          "「全仓零命中」只对当前工作树成立" % len(hits))
    if not hits:
        fails.append("git 全历史也搜不到 f[6] ⇒ 无法取回修复前代码")

    # ── 步骤 1：取回修复前的原文（★ T-L3-06 的判据）──
    before = show_file(repo, BEFORE_COMMIT, OPS_PATH)
    if before is None:
        fails.append("取不到修复前 ops.py（%s）" % BEFORE_COMMIT)
        print("✘ 取不到修复前 ops.py")
    else:
        # ★ 逐字截取特征函数里与 f[6] 相关的行
        lines = before.splitlines()
        idx_f6 = [i for i, l in enumerate(lines)
                  if "f[6]" in l or "f[OPS.index(op)]" in l or
                  "f = [0.0]" in l or "return f" in l]
        lo = max(0, min(idx_f6) - 3) if idx_f6 else 0
        hi = min(len(lines), max(idx_f6) + 2) if idx_f6 else 0
        snippet = "\n".join("%4d| %s" % (i + 1, lines[i])
                            for i in range(lo, hi))
        rep["before_commit"] = BEFORE_COMMIT
        rep["before_snippet"] = snippet
        rep["before_has_f6_depth_write"] = any(
            "f[6] = min(depth" in l for l in lines)
        rep["before_feature_dim"] = next(
            (int(l.split("*")[1].split("]")[0].strip())
             for l in lines if "f = [0.0]" in l and "*" in l), None)
        print("\n② ★ 修复前代码（%s，%s）逐字原文：" % (BEFORE_COMMIT, OPS_PATH))
        print(snippet)
        if not rep["before_has_f6_depth_write"]:
            fails.append("修复前代码里没有 `f[6] = min(depth...` 这一行")
        print("   ⇒ 特征维数 = %s ｜ 存在 `f[6] = min(depth/6.0,1.0)` = %s"
              % (rep["before_feature_dim"],
                 rep["before_has_f6_depth_write"]))

    # ── 步骤 2：修复后（当前）的对照 ──────────────────────────
    after_src = None
    for c in AFTER_COMMITS:
        s = show_file(repo, c, OPS_PATH)
        if s and "修 f[6] 索引冲突" in s:
            after_src = (c, s)
            break
    if after_src:
        c, s = after_src
        lines = s.splitlines()
        i = next((k for k, l in enumerate(lines)
                  if "修 f[6] 索引冲突" in l), None)
        rep["after_commit"] = c
        rep["after_explanation"] = "\n".join(
            lines[i:i + 9]) if i is not None else ""
        print("\n③ 修复后（%s）的机制说明（注释原文）：" % c)
        print(rep["after_explanation"])
    else:
        fails.append("取不到修复后 ops.py 的说明注释")

    # ── 步骤 3：候选集是否含 MERGE ───────────────────────────
    ops_line = None
    src = before or ""
    for l in src.splitlines():
        if l.strip().startswith("OPS") and "=" in l:
            ops_line = l.strip()
            break
    rep["ops_definition_line"] = ops_line
    has_merge = bool(ops_line and "MERGE" in ops_line.upper())
    rep["candidates_contain_merge"] = has_merge
    print("\n④ 候选集：%s ⇒ 含 MERGE？ %s"
          % (ops_line or "(未在修复前文件里找到 OPS 定义行)",
             "是" if has_merge else "★ 否"))
    if has_merge:
        fails.append("候选集竟含 MERGE ⇒ 与结论相反，需重核")

    # ── 步骤 4：产出批② 的定位（★ 按 mtime 排序）────────────
    ordered = sorted(BATCH_TIMES.items(), key=lambda kv: kv[1])
    rep["batches_by_time"] = ordered
    rep["batch2_candidates"] = ordered[1][0] if len(ordered) > 1 else None
    print("\n⑤ 产出批按产出时间排序（★ 第二个 = 批②）：")
    for k, v in ordered:
        print("     %-12s %s" % (k, v))
    print("   ⇒ 批② 候选 = %s" % rep["batch2_candidates"])

    out = dict(report=rep, fails=fails)
    fp = os.path.join(args.out, "T-L3-03_06_读数.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n★ 读数落盘：%s" % fp)
    print("结论：%s" % ("PASS" if not fails else "FAIL: %s" % fails))
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main())
