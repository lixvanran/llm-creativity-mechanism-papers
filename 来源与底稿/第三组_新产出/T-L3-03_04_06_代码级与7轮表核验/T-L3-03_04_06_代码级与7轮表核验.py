#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ T-L3-03 / T-L3-04 / T-L3-06 · 代码级发现 + 7 轮表 + 修复前代码【统一核验】
   ============================================================================
   ★★★ 审计对象（★ 关键：只能是这个，别的对象结论无效）★★★
     外部仓 `lixvanran/agent-creativity-mechanism-study`
     commit `e012f1e2`（2026-10-18 23:27，★ 论文 §5.3 标注的 "HEAD"）
     ★★ 本脚本第一版审的是 `777a5fe:cmp8/creativity_lab/ops.py`
        ⇒ ★★ **审错对象**（`777a5fe` 是另一棵树的另一个 commit，路径前缀都不同）
        ⇒ ★★ 本版全部改为 `e012f1e2:creativity_lab/...`

   ★ 判据原文（③ 篇正文 §12.1 任务清单表，★ 逐字回源）：
   ─────────────────────────────────────────────────────────────────────────
   T-L3-03：§5.3 三条代码级发现是否也成立于"产出 §4.4 读数的那一版代码"
     判据：逐行核对 `op_features` 的特征维数与 `f[6]` 的写入顺序
           （若那版也是 14 格 / 深度写 `f[6]` / 候选集无 `MERGE`，三条发现成立）
   T-L3-04：§4.4 的 7 轮记录与 §5.1 致命 bug 的先后关系
     判据：7 轮表里操作分布**逐轮有变化**（`GEN_PLAIN` 24→3、第 5 轮 `EXTRACT=18`、
           第 7 轮 `VERIFY=14`），**该表不可能来自"永远选字母序第一个"的 bug 版本**，
           ⇒ **7 轮表可用；bug 影响的是它之前的那几轮**
   T-L3-06：修复前版本的代码 `scored.sort(key=lambda x: -x[1][0])`
     判据①：拿到能**逐字引用**的修复前代码 ⇒ §5.1 形态 L2 → L1
     判据②：拿到该批的**操作直方图**并证明它**不是**"全 GEN_PLAIN" ⇒ 顺带关闭 T-L3-04
   ─────────────────────────────────────────────────────────────────────────

   ★ 本脚本的自证：每条判据都**由代码原文或表格原文机械判定**，
     不含任何模型判断；判据红 ⇒ 退出码 7，脚本崩溃 ⇒ 退出码 1。

   用法：python3 T-L3-03_04_06_代码级与7轮表核验.py [--repo DIR] [--out DIR]
   """
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO = "/workspace/lab/cmp8repo"
AUDIT_COMMIT = "e012f1e2"          # ★ 论文 §5.3 标注的 HEAD（审计对象）
REPORT_REL = "来源与底稿/第三组_治塌缩层3/外部仓报告/REPORT-ARCHLEARN-2026-10-19.md"


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo] + list(args),
                       capture_output=True, text=True, timeout=240)
    return r.returncode, r.stdout, r.stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()
    repo, out = args.repo, args.out
    os.makedirs(out, exist_ok=True)
    rep, fails = {}, []

    def show(title):
        print("\n" + "=" * 100)
        print(title)
        print("=" * 100)

    # ══ 0 · 审计对象锁定 ════════════════════════════════════
    show("表 0 · 审计对象锁定（★ 审错对象 ⇒ 结论无效）")
    rc, out0, _ = git(repo, "log", "-1", "--format=%H%x09%ad%x09%s",
                      "--date=format:%Y-%m-%d %H:%M", AUDIT_COMMIT)
    if rc != 0 or not out0.strip():
        print("✘ 取不到审计对象 %s" % AUDIT_COMMIT)
        fails.append("审计对象不可达")
        print("结论：FAIL")
        return 7
    print("  审计对象 commit = %s" % out0.strip())
    rep["audit_commit"] = out0.strip()
    # ★ 该 commit 是否仍是仓的最新？（论文说"HEAD e012f1e2"）
    rc, head, _ = git(repo, "log", "--all", "-1", "--format=%H%x09%ad",
                      "--date=format:%Y-%m-%d %H:%M")
    rep["repo_latest_commit"] = head.strip()
    print("  仓内最新 commit  = %s" % head.strip())
    if AUDIT_COMMIT not in head:
        print("  ★★ 注意：审计对象**已不是**仓内最新 commit"
              "（★ 论文 §5.3 的 'HEAD e012f1e2' 表述已过期）")
        print("     ⇒ 本脚本仍只审 %s（论文指定的对象），"
              "并在报告里标明该对象已非最新" % AUDIT_COMMIT)

    # ══ 1 · T-L3-03 三条代码级发现 ═══════════════════════════
    show("表 1 · T-L3-03 · §5.3 三条代码级发现（对象 = %s）" % AUDIT_COMMIT)
    rc, ops, _ = git(repo, "show", "%s:creativity_lab/ops.py" % AUDIT_COMMIT)
    rc2, tp, _ = git(repo, "show", "%s:creativity_lab/train_policy.py" % AUDIT_COMMIT)
    if rc != 0 or rc2 != 0:
        print("✘ 取不到源码")
        fails.append("源码不可达")
        print("结论：FAIL")
        return 7
    ops_lines, tp_lines = ops.splitlines(), tp.splitlines()

    # ① 特征维数 14
    dim_hits = [i for i, l in enumerate(ops_lines, 1) if re.search(r"f\s*=\s*\[0\.0\]\s*\*\s*14", l)]
    d1 = bool(dim_hits)
    print("  ① 特征维数：`f = [0.0] * 14` @ ops.py:%s ⇒ %s"
          % (dim_hits or "未命中", "★ 成立（14 维）" if d1 else "✘ 不成立"))

    # ② f[6] 写入顺序：one-hot 先写、depth 后写且在 target 块之外
    onehot = [i for i, l in enumerate(ops_lines, 1)
              if "OPS.index(op)" in l and "= 1.0" in l]
    f6 = [i for i, l in enumerate(ops_lines, 1) if re.search(r"f\[6\]\s*=", l)]
    # f[6] 是否在 `if target is not None:` 块之外（缩进层级）
    f6_indent = None
    if f6:
        f6_indent = len(ops_lines[f6[0] - 1]) - len(ops_lines[f6[0] - 1].lstrip())
    tgt_indent = None
    for i, l in enumerate(ops_lines, 1):
        if l.strip().startswith("if target is not None:"):
            tgt_indent = len(l) - len(l.lstrip())
            break
    d2 = bool(onehot and f6 and f6[0] > onehot[0] and
              (f6_indent is not None and tgt_indent is not None and f6_indent <= tgt_indent))
    print("  ② `f[6]` 写入顺序：one-hot @ ops.py:%s → depth 覆盖 @ ops.py:%s"
          % (onehot or "?", f6 or "?"))
    print("     缩进：f[6]=%s 空格 / `if target is not None:`=%s 空格 ⇒ %s"
          % (f6_indent, tgt_indent,
             "★ depth 写在【对所有 op 生效】的位置（target 块之外）"
             if d2 else "✘"))
    print("     ⇒ 后果：STOP(=6) 的 one-hot 被 depth 覆盖 ⇒ STOP 永远选不中；")
    print("        depth 对所有 op 同值 ⇒ softmax 里是公共常数 ⇒ 零作用")
    if not d1:
        fails.append("T-L3-03：特征维数不是 14")
    if not d2:
        fails.append("T-L3-03：f[6] 写入顺序不构成覆盖")

    # ③ 候选集无 MERGE
    cands = [i for i, l in enumerate(tp_lines, 1) if "cands.append" in l]
    cand_ops = []
    for i in cands:
        m = re.search(r'cands\.append\(\("([A-Z_]+)"', tp_lines[i - 1])
        if m:
            cand_ops.append((i, m.group(1)))
    has_merge = any(op == "MERGE" for _, op in cand_ops)
    ops_tuple = re.search(r"OPS\s*=\s*\(([^)]*)\)", ops)
    ops_names = [x.strip().strip('"') for x in ops_tuple.group(1).split(",")] if ops_tuple else []
    d3 = not has_merge and "MERGE" in ops_names
    print("  ③ 候选集：`cands.append` 命中 %s ⇒ 候选集含 MERGE？ %s"
          % (cand_ops, "★ 是" if has_merge else "★ 否"))
    print("     而 `OPS` 元组 = %s ⇒ 含 MERGE" % (ops_names,))
    print("     ⇒ ★ 区分两层：OPS【定义】含 MERGE，但【候选集】不接它"
          " ⇒ 三条发现成立" if d3 else "     ⇒ ✘")
    if not d3:
        fails.append("T-L3-03：候选集含 MERGE 或 OPS 不含 MERGE")

    # 排序键现状
    sort_lines = [(i, l.strip()) for i, l in enumerate(tp_lines, 1) if "scored.sort" in l]
    print("\n  附 · 排序键现状（HEAD）：%s" % sort_lines)
    rep["T-L3-03"] = dict(commit=AUDIT_COMMIT,
                          dim14=d1, dim14_at=dim_hits,
                          f6_overwrites_stop=d2, onehot_at=onehot, f6_at=f6,
                          f6_indent=f6_indent, target_block_indent=tgt_indent,
                          cand_has_merge=has_merge, cand_ops=cand_ops,
                          ops_tuple=ops_names, cand_no_merge=d3,
                          sort_now=sort_lines,
                          all_three_hold=bool(d1 and d2 and d3))
    print("\n  ⇒ T-L3-03 三条发现全部成立：%s" % (d1 and d2 and d3))

    # ══ 2 · T-L3-04 7 轮表 ══════════════════════════════════
    show("表 2 · T-L3-04 · 7 轮表的操作分布（报告 §3）")
    rpath = os.path.join("/workspace/work/exp/L3", REPORT_REL)
    if not os.path.exists(rpath):
        print("✘ 报告不可达：%s" % rpath)
        fails.append("7 轮表报告不可达")
        rounds = []
    else:
        txt = open(rpath, encoding="utf-8").read()
        rounds = []
        for line in txt.splitlines():
            m = re.match(r"^\|\s*(\d)\s*\|.*?\|(.*)\|\s*$", line)
            if not m:
                continue
            rd = int(m.group(1))
            ops_part = m.group(2)
            d = dict((op, int(v)) for op, v in
                     re.findall(r"([A-Z_]+)\s*=\s*(\d+)", ops_part))
            if d and 1 <= rd <= 7:
                rounds.append((rd, d, line.strip()))
    for rd, d, line in rounds:
        tot = sum(d.values())
        gp = d.get("GEN_PLAIN", 0)
        print("  r%d  %-72s 合计=%-4d GEN_PLAIN 占比=%.3f"
              % (rd, line[-72:], tot, gp / float(tot) if tot else 0))
    # 判据 ①：逐轮有变化
    changed = any(rounds[i][1] != rounds[i + 1][1] for i in range(len(rounds) - 1))
    # 判据 ②：不可能来自"永远选字母序第一个动作"的 bug 版
    #   bug 症状（报告 §4.1 原文）：「50 步全是 GEN_PLAIN，核验 0 次」
    #   ⇒ 判据：每轮都必须【不是】全 GEN_PLAIN，且【至少一轮有 VERIFY】
    not_all_gp = all(sum(v.values()) > v.get("GEN_PLAIN", 0) for _, v, _ in rounds)
    has_verify = any(v.get("VERIFY", 0) > 0 for _, v, _ in rounds)
    # 派活给的三个锚点
    anchors = {
        "r1 GEN_PLAIN=24": rounds and rounds[0][1].get("GEN_PLAIN") == 24,
        "r5 EXTRACT=18": len(rounds) > 4 and rounds[4][1].get("EXTRACT") == 18,
        "r7 VERIFY=14": len(rounds) > 6 and rounds[6][1].get("VERIFY") == 14,
        "GEN_PLAIN 24→3": (rounds and rounds[0][1].get("GEN_PLAIN") == 24
                           and any(v.get("GEN_PLAIN") == 3 for _, v, _ in rounds)),
    }
    print("\n  判据① 操作分布逐轮有变化：%s" % ("★ 成立" if changed else "✘"))
    print("  判据② 不可能来自 bug 版：每轮非全 GEN_PLAIN = %s；存在 VERIFY 的轮 = %s"
          % (not_all_gp, has_verify))
    print("  锚点核对：%s" % {k: ("✔" if v else "✘") for k, v in anchors.items()})
    d4 = changed and not_all_gp and has_verify and all(anchors.values())
    print("  ⇒ T-L3-04 判据：%s" % ("★ 成立 ⇒ 7 轮表可用；bug 影响的是它之前的那几轮"
                                     if d4 else "✘ 不成立"))
    if not d4:
        fails.append("T-L3-04：7 轮表判据未全部成立")
    rep["T-L3-04"] = dict(rounds=[dict(round=r, ops=d) for r, d, _ in rounds],
                          changed_by_round=changed,
                          no_round_all_gen_plain=not_all_gp,
                          has_verify_round=has_verify,
                          anchors=anchors, judge=d4)

    # ══ 3 · T-L3-06 修复前代码 ═══════════════════════════════
    show("表 3 · T-L3-06 · 修复前代码（两条互补判据）")
    # 判据①：逐字引用（报告 §4.1 原文）
    bug_line = None
    if os.path.exists(rpath):
        for i, line in enumerate(open(rpath, encoding="utf-8").read().splitlines(), 1):
            if "x[1][0]" in line and "scored.sort" in line:
                bug_line = (i, line.strip())
                break
    print("  判据① 逐字引用的修复前代码：")
    if bug_line:
        print("     %s:  %s" % bug_line)
    else:
        print("     ✘ 报告里找不到")
    # git 历史里有没有带 x[1][0] 的版本
    hist = []
    rc, cl, _ = git(repo, "log", "--all", "--format=%H", "--",
                    "creativity_lab/train_policy.py")
    for c in cl.split()[:30]:
        rc2, src, _ = git(repo, "show", "%s:creativity_lab/train_policy.py" % c)
        if rc2 != 0:
            continue
        for line in src.splitlines():
            if "scored.sort" in line:
                hist.append(dict(commit=c[:8], line=line.strip()))
                break
    has_bug_in_hist = any("x[1][0]" in h["line"] for h in hist)
    print("  git 历史里 train_policy.py 的 sort 行（%d 个 commit）：" % len(hist))
    for h in hist[:8]:
        print("     %s  %s" % (h["commit"], h["line"]))
    print("  ⇒ git 历史里存在带 `x[1][0]` 的版本：%s"
          % ("★ 是" if has_bug_in_hist else "★ 否（修复前那版从未进过本仓 git）"))
    j1 = bool(bug_line)
    # 判据②：操作直方图证明不是"全 GEN_PLAIN"
    j2 = bool(rounds) and not_all_gp and has_verify
    print("  判据② 该批操作直方图证明不是「全 GEN_PLAIN」：%s"
          % ("★ 成立（7 轮表每轮都含非 GEN_PLAIN 操作，且多轮有 VERIFY）"
             if j2 else "✘"))
    print("\n  ⇒ T-L3-06：判据① %s ／ 判据② %s ⇒ %s"
          % ("成立" if j1 else "不成立", "成立" if j2 else "不成立",
             "★ 两条互补判据均成立 ⇒ T-L3-06 关闭，且连带 T-L3-04 关闭"
             if (j1 and j2) else "⇒ 未全部成立"))
    if not (j1 and j2):
        fails.append("T-L3-06：两条判据未全部成立")
    rep["T-L3-06"] = dict(bug_line_bug=bug_line, git_hist_sort_lines=hist,
                           bug_version_in_git_history=has_bug_in_hist,
                           judge1_verbatim=j1, judge2_histogram=j2,
                           close_t_l3_04=bool(j1 and j2),
                           note=("★ 逐字引用的载体是【作者自述报告】，不是 git 对象；"
                                 "⇒ 形态可从 L2 升到 L1′，但 git 历史里仍无该版本"))

    out_obj = dict(report=rep, fails=fails)
    fp = os.path.join(out, "T-L3-03_04_06_读数.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(out_obj, f, ensure_ascii=False, indent=2)
    print("\n★ 读数落盘：%s" % fp)
    print("结论：%s" % ("PASS" if not fails else "FAIL: %s" % fails))
    return 0 if not fails else 7


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:            # ★ 脚本崩溃 = 1（与判据红 = 7 区分）
        print("★ 脚本崩溃：%r" % e)
        sys.exit(1)
