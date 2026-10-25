#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★★★ 【已被取代 · 勿据此下结论】★★★
   ★ 本脚本测的是【cmp8 批】(runs/cmp8/A*_r*_A5*.json，3 轮 × 4 臂 × 3 变体)，
   ★★ 而 T-L3-04 的判据对象是【REPORT-ARCHLEARN-2026-10-19.md §3 的 7 轮表】⇒ 本脚本【不是判据对象】。
   ★★ 本脚本另一处错：它审的是 `777a5fe:cmp8/creativity_lab/...`（★ 另一棵树的另一个 commit），
   ★★ 而论文审计对象是 `e012f1e2:creativity_lab/...`（仓根结构，无 cmp8/ 前缀）⇒ ★★ 审错对象。
   ★★ 正确核验见同目录上一级：T-L3-03_04_06_代码级与7轮表核验/（已 PASS）。
   ★★ 保留本脚本仅因为它测的【cmp8 批逐轮分布】本身是有效读数（36 份记录，MERGE 实际 0 次被选）。
   """
★ T-L3-04 · 批②「7 轮记录」与「排序键缺陷」的先后关系
   --------------------------------------------------------------
   ★ 判据（派活）：7 轮表里操作分布**逐轮有变化**
        （派活举例：`GEN_PLAIN` 24→3、第 5 轮 `EXTRACT=18`、第 7 轮…）
   ★★★ 实测结论：★★
     ① 判据【成立】：操作分布逐轮确有变化（见下方三张矩阵）
     ② ★ 派活举的三个数（24→3 / EXTRACT=18 / 第 7 轮）**与实测全部对不上**
        ⇒ ★ 那组数来自【另一份数据】，不是这批 ⇒ 本判据按【判据本身】核，不按例子核
     ③ ★★ 判据成立 ⇒ 推出【排序键缺陷在这批产出之前已修】：
        · 排序键修复（`scored.sort(key=lambda x: -x[0])` + 机制注释）
          = commit `777a5fe` @ **2026-10-20 17:03**
        · 这批「7 轮记录」（A5 记录）产出 = commit `9fb0e5e` @ **2026-10-20 19:18**
        ⇒ ★ 修复早于产出 **2 小时 15 分** ⇒ ★ 这批**不是在排序键 bug 还在的代码下跑的**
        ⇒ ★ 反证：若 bug 还在，op 会「永远选字母序第一个动作」⇒ 分布会被固定
          ⇒ 分布逐轮在变，正是"排序键已修"的佐证
     ④ ★★ 另一条缺陷的先后【相反】：
        · `f[6]` 索引冲突修复 = commit `8b2ba41` / `240775b` @ **2026-10-21 00:04**
        ⇒ ★ **晚于**这批产出（19:18）⇒ ★★ **这批 7 轮记录是在 `f[6]` 仍有 bug 的代码下跑的**
        ⇒ ★★ ⇒ T-L3-03 的第②条（`f[6]` 写入顺序冲突）**在这一版上成立**
        ⇒ ★★ ⇒ **这批读数的 `f[6]` 特征是坏的**：STOP 的 one-hot 被 depth 覆盖 ⇒
          STOP 永远选不中（只有 ε 能触发）；depth 对所有 op 同值 ⇒ softmax 里是公共常数
          ⇒ **完全抵消、零作用**（修复后注释原文）
     ⑤ ★★ 候选集含 MERGE（OPS 7 个算子），但 ★ **这 36 份记录里 MERGE 实际 0 次被选中**
        ⇒ 候选集与实际执行集**不是一回事** ⇒ 报"动作空间"时必须区分这两层

   ★ 数据来源（★ 全在本机 / 本仓，零 API）：
     · 7 轮记录：`cmp8/runs/cmp8/A{臂}_r{轮}_A5{变体}.json`（36 份）
     · 修复前代码：`git show 777a5fe:cmp8/creativity_lab/ops.py`（★ 含 `f[6] = min(depth/6.0,1.0)`）
     · 排序键修复：`git show 777a5fe:cmp8/creativity_lab/learnarch.py`（★ 修复后 + 机制注释）
     · ★ 带 `x[1][0]` 的排序键 bug 版：**从未进过 git**（`learnarch.py` 在 git 里只有 1 个 commit）
       ⇒ ⇒ 按 T-L3-06 的口径：**「未找到原始出处」，不降级也不引用**

   用法：python3 T-L3-04_7轮与排序键先后.py [--repo DIR] [--out DIR]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO = "/workspace/lab/cmp8repo"
OPS = ["GEN_PLAIN", "GEN_ANGLE", "EXTRACT", "SPLIT", "VERIFY", "MERGE", "STOP"]
VARIANTS = ["a", "b", "c"]
ROUNDS = [1, 2, 3]


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo] + list(args),
                       capture_output=True, text=True, timeout=180)
    return r.returncode, r.stdout, r.stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()
    repo = args.repo
    os.makedirs(args.out, exist_ok=True)
    rundir = os.path.join(repo, "cmp8/runs/cmp8")
    rep, fails = {}, []

    # ── 1. 逐（变体 × 轮）的 ops 分布 ─────────────────────────
    mat = defaultdict(Counter)
    nfiles = defaultdict(int)
    files = []
    for p in sorted(glob.glob(os.path.join(rundir, "A*_r*_A5*.json"))):
        m = re.match(r"A(\d+)_r(\d+)_A5([abc])\.json", os.path.basename(p))
        if not m:
            continue
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict) or "ops" not in d:
            continue
        v, rd = m.group(3), int(m.group(2))
        mat[(v, rd)].update(d["ops"])
        nfiles[(v, rd)] += 1
        files.append(dict(file=os.path.basename(p), arm="A" + m.group(1),
                          variant="⑤" + v, round=rd, ops=d["ops"]))
    rep["n_records"] = len(files)
    rep["files"] = files
    if not files:
        fails.append("找不到 A5 记录")
        print("✘ 找不到 A5 记录")

    print("=" * 104)
    print("表 A · 「7 轮记录」逐（变体 × 轮）操作分布（★ 判据：逐轮有变化）")
    print("=" * 104)
    for v in VARIANTS:
        print("\n【⑤%s】" % v)
        print("  轮   文件数  " + "  ".join("%-10s" % o for o in OPS))
        prev = None
        for rd in ROUNDS:
            c = mat[(v, rd)]
            if not nfiles[(v, rd)]:
                continue
            print("  r%-2d %-7d " % (rd, nfiles[(v, rd)])
                  + "  ".join("%-10d" % c.get(o, 0) for o in OPS))
            if prev is not None:
                diff = {o: (prev.get(o, 0), c.get(o, 0)) for o in OPS
                        if prev.get(o, 0) != c.get(o, 0)}
                print("        ★ 与上一轮变化：%s" % (diff if diff else "无"))
            prev = c
        rep.setdefault("matrix", {})["⑤" + v] = {
            "r%d" % rd: dict(mat[(v, rd)]) for rd in ROUNDS if nfiles[(v, rd)]}

    # ★ 判据判定：逐轮是否有变化
    changed_any = False
    for v in VARIANTS:
        for i in range(len(ROUNDS) - 1):
            a, b = mat[(v, ROUNDS[i])], mat[(v, ROUNDS[i + 1])]
            if not a or not b:
                continue
            if any(a.get(o, 0) != b.get(o, 0) for o in OPS):
                changed_any = True
    rep["ops_distribution_changes_by_round"] = changed_any
    print("\n★ 判据（操作分布逐轮有变化）：%s"
          % ("成立 ✔" if changed_any else "不成立 ✘"))
    if not changed_any:
        fails.append("操作分布逐轮无变化 ⇒ 判据不成立")

    # ★ MERGE：候选集里有、实际选了几次
    allops = Counter()
    for f in files:
        allops.update(f["ops"])
    rep["ops_total"] = dict(allops)
    rep["merge_selected_times"] = allops.get("MERGE", 0)
    print("★ 候选集 OPS = %s（★ 含 MERGE）" % (OPS,))
    print("★ 实际选中次数：%s" % {o: allops.get(o, 0) for o in OPS})
    print("   ⇒ ★ MERGE 在候选集但实际 %d 次被选中 ⇒ 候选集 ≠ 实际执行集"
          % allops.get("MERGE", 0))

    # ── 2. 三个关键 commit 的日期（★ 先后关系）────────────────
    print()
    print("=" * 104)
    print("表 B · 缺陷修复 vs 7 轮记录产出的【先后关系】")
    print("=" * 104)
    dates = {}
    for label, args_ in [
            ("排序键修复（-x[0] + 机制注释）",
             ["log", "-1", "--format=%H%x09%ad%x09%s", "--date=format:%Y-%m-%d %H:%M",
              "777a5fe"]),
            ("7 轮记录产出（A5 json 进 git）",
             ["log", "-1", "--format=%H%x09%ad%x09%s", "--date=format:%Y-%m-%d %H:%M",
              "9fb0e5e"]),
            ("f[6] 索引冲突修复",
             ["log", "--all", "-1", "--format=%H%x09%ad%x09%s",
              "--date=format:%Y-%m-%d %H:%M", "-S修 f[6] 索引冲突",
              "--", "cmp8/creativity_lab/ops.py"])]:
        rc, out, err = git(repo, *args_)
        line = out.strip().splitlines()[0] if out.strip() else "(未找到)"
        dates[label] = line
        print("  %-36s %s" % (label, line))

    # ★ 解析出可比较的时间戳
    def ts(label):
        parts = dates.get(label, "").split("\t")
        if len(parts) >= 2:
            return parts[1]
        return ""
    t_sort = ts("排序键修复（-x[0] + 机制注释）")
    t_batch = ts("7 轮记录产出（A5 json 进 git）")
    t_f6 = ts("f[6] 索引冲突修复")
    rep["timestamps"] = dict(sort_fix=t_sort, batch=t_batch, f6_fix=t_f6)
    order = {}
    if t_sort and t_batch:
        order["sort_fix_before_batch"] = t_sort < t_batch
        print("\n  ★ 排序键修复(%s) 【早于】7 轮记录产出(%s)？ %s"
              % (t_sort, t_batch, "是 ✔" if t_sort < t_batch else "否 ✘"))
    if t_f6 and t_batch:
        order["f6_fix_after_batch"] = t_f6 > t_batch
        print("  ★ f[6] 修复(%s) 【晚于】7 轮记录产出(%s)？ %s"
              % (t_f6, t_batch, "是 ✔" if t_f6 > t_batch else "否 ✘"))
    rep["order"] = order
    if not order.get("sort_fix_before_batch"):
        fails.append("排序键修复与产出的先后关系未确立")
    if not order.get("f6_fix_after_batch"):
        fails.append("f[6] 修复与产出的先后关系未确立")

    # ── 3. 逐字引用的两段代码 ────────────────────────────────
    print()
    print("=" * 104)
    print("表 C · 可逐字引用的代码原文")
    print("=" * 104)
    rc, ops_src, _ = git(repo, "show", "777a5fe:cmp8/creativity_lab/ops.py")
    rc2, la_src, _ = git(repo, "show",
                         "777a5fe:cmp8/creativity_lab/learnarch.py")
    f6_lines = [l for l in ops_src.splitlines() if "f[6]" in l]
    sort_lines = [l for l in la_src.splitlines()
                  if "scored.sort" in l or "排序键" in l or "x[1][0]" in l]
    rep["f6_before_code"] = "\n".join(f6_lines)
    rep["sortkey_after_code"] = "\n".join(sort_lines)
    print("【修复前 · f[6] 写入顺序冲突】（777a5fe:cmp8/creativity_lab/ops.py）")
    for l in f6_lines:
        print("   " + l.strip())
    print("\n【修复后 · 排序键】（777a5fe:cmp8/creativity_lab/learnarch.py）")
    for l in sort_lines:
        print("   " + l.strip())
    print("\n★ 带 `x[1][0]` 的排序键 bug 版：【从未进过 git】")
    print("   （`learnarch.py` 在 git 里只有 1 个 commit ⇒ 按 T-L3-06 口径："
          "「未找到原始出处」，不降级也不引用）")

    # ★ 带 bug 的排序键版是否在别处（rebuild/）
    rc3, rb, _ = git(repo, "show", "777a5fe:cmp8/rebuild/cmp8_p1.py")
    rb_hits = [l for l in rb.splitlines() if "x[1][0]" in l]
    rep["sortkey_bug_version_found_elsewhere"] = bool(rb_hits)
    print("   旁证：`cmp8/rebuild/cmp8_p1.py` 同处有相同注释 ⇒ %s"
          % ("有" if rb_hits else "无"))

    out = dict(report=rep, fails=fails)
    fp = os.path.join(args.out, "T-L3-04_读数.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n★ 读数落盘：%s" % fp)
    print("结论：%s" % ("PASS" if not fails else "FAIL: %s" % fails))
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main())
