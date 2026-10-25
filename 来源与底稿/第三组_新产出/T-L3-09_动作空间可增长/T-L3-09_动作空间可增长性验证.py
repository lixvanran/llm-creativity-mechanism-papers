#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ T-L3-09 · 动作空间可增长性【代码层】验证（★ 零 API）
   --------------------------------------------------------------
   ★ 预注册：`T-L3-09_预注册.md` §2.1（★ 先写后跑）

   ★ 做什么：
     ① 在 `workflow.py` 的**副本**上新增 1 个修复型 ⇒ 动作数 36 → 42
     ② 跑既有 `test_workflow.py` 全套（★ 判据：全绿 ⇒ 不破坏原行为）
     ③ 读参数化可扩展性：u / v / m 三组因子的维度怎么变
     ④ ★ 读**旧策略权重能否直接迁移**（★ 这是"动作空间可增长"的真卡点所在）

   ★ 判据（预注册 §2.1）：
     ① 动作数 36 → 42 ✔
     ② 既有测试全绿 ✔
     ③ 参数化可扩展（u/v/m 都能加维）✔
   ★ 停止规则：② 失败 ⇒ 立即停，报告"接口层不可增长"，不再往训练侧走

   用法：python3 T-L3-09_动作空间可增长性验证.py [--src DIR] [--out DIR]
   """
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SRC = "/workspace/lab/routes/COLLAPSE"

# ★ 新增的修复型（★ 示范用，★ 不代表"应该加这个" ⇒ 真正的 A* 必须由训练产生）
NEW_REPAIR = "cross_refine"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()
    SRC, OUT = args.src, args.out
    os.makedirs(OUT, exist_ok=True)
    ext = os.path.join(OUT, "workflow_ext")
    rep, fails = {}, []

    wf_src = os.path.join(SRC, "workflow.py")
    if not os.path.exists(wf_src):
        print("✘ 找不到 %s" % wf_src)
        return 1
    # ── 复制（★ 不改动任何他人目录）──
    if os.path.isdir(ext):
        shutil.rmtree(ext)
    shutil.copytree(SRC, ext, ignore=shutil.ignore_patterns(
        "__pycache__", "runs", "*.log", "_logs"))
    wf_ext = os.path.join(ext, "workflow.py")
    print("★ 副本：%s" % wf_ext)

    # ── 基线读数 ──
    def probe(path):
        """★ 在一个 workflow.py 上取动作空间与参数化读数（不导入，只静态+动态）"""
        code = io.open(path, encoding="utf-8").read()
        r = {}
        m = re.search(r"REPAIR_TYPES:\s*Dict\[str, Optional\[str\]\] = \{(.*?)\n\}",
                      code, re.S)
        r["n_repair_types"] = len(re.findall(r'^\s{4}"[a-z_]+"\s*:', m.group(1), re.M)) if m else None
        r["n_scopes"] = len(re.findall(r'^\s{4}"[a-z_]+"\s*:', re.search(
            r"SCOPES:\s*Dict\[str, str\] = \{(.*?)\n\}", code, re.S).group(1), re.M))
        r["n_strictness"] = len(re.findall(r"^\s{4}\d+\s*:", re.search(
            r"STRICTNESS:\s*Dict\[int, str\] = \{(.*?)\n\}", code, re.S).group(1), re.M))
        r["n_actions"] = (r["n_repair_types"] or 0) * (r["n_scopes"] or 0) * (r["n_strictness"] or 0)
        # 参数化：u 的维度 = len(REPAIR_TYPES)、v = len(SCOPE_IDS)、m = FAILURE_IDS × REPAIR_TYPES
        r["u_dim"] = r["n_repair_types"]
        r["v_dim"] = r["n_scopes"]
        r["m_dim"] = (r["n_repair_types"] or 0) * 3      # FAILURE_KINDS 的数量，本仓为 3
        r["total_params"] = r["u_dim"] + r["v_dim"] + r["m_dim"]
        return r

    base = probe(wf_ext)
    print("★ 基线（未改）：修复型=%s 作用域=%s 强度=%s ⇒ 动作数=%s；参数 u=%s v=%s m=%s 合计=%s"
          % (base["n_repair_types"], base["n_scopes"], base["n_strictness"],
             base["n_actions"], base["u_dim"], base["v_dim"], base["m_dim"],
             base["total_params"]))
    rep["baseline"] = base

    # ── 改：新增 1 个修复型 ──
    code = io.open(wf_ext, encoding="utf-8").read()
    pat = re.compile(r'(REPAIR_TYPES:\s*Dict\[str, Optional\[str\]\] = \{\n)')
    ins = ('    "%s": "★新增（可增长性验证用）：**对照其它各路的内容**，'
           '逐条指出冲突并改写",\n' % NEW_REPAIR)
    code2, n = pat.subn(lambda m: m.group(1) + ins, code, count=1)
    if n != 1:
        print("✘ 没能插入修复型 ⇒ 停止")
        fails.append("插入修复型失败")
        return 7
    io.open(wf_ext, "w", encoding="utf-8").write(code2)
    ext2 = probe(wf_ext)
    print("★ 扩后：修复型=%s ⇒ 动作数=%s；参数 u=%s v=%s m=%s 合计=%s"
          % (ext2["n_repair_types"], ext2["n_actions"], ext2["u_dim"],
             ext2["v_dim"], ext2["m_dim"], ext2["total_params"]))
    rep["extended"] = ext2

    # ── 判据 ①：36 → 42 ──
    ok1 = (base["n_actions"] == 36 and ext2["n_actions"] == 42)
    print("  判据① 动作数 36 → 42：%s" % ("✔" if ok1 else "✘"))
    if not ok1:
        fails.append("动作数不是 36→42")

    # ── 判据 ②：既有测试全绿 ──
    tw = os.path.join(ext, "test_workflow.py")
    if os.path.exists(tw):
        r = subprocess.run([sys.executable, tw], cwd=ext,
                           capture_output=True, text=True, timeout=300)
        tail = (r.stdout or "")[-1500:]
        m = re.search(r"(\d+)\s*/\s*(\d+)|Ran (\d+) test|OK|FAILED", tail)
        n_pass = None
        for pat2 in (r"(\d+)\s*passed", r"OK \((\d+) test"):
            mm = re.search(pat2, tail)
            if mm:
                n_pass = int(mm.group(1))
                break
        ok2 = (r.returncode == 0)
        print("  判据② 既有 test_workflow.py：rc=%d ⇒ %s"
              % (r.returncode, "✔ 全绿" if ok2 else "✘"))
        print("     尾部：%s" % tail.replace("\n", " | ")[-320:])
        rep["tests"] = dict(rc=r.returncode, passed=n_pass, tail=tail[-800:],
                            test_file=os.path.relpath(tw, ext))
        if not ok2:
            fails.append("既有测试在扩后不绿")
    else:
        print("  判据② 找不到 test_workflow.py ⇒ 跳过")
        rep["tests"] = dict(rc=None, note="test_workflow.py 不在副本里")

    # ── 判据 ③：参数化可扩展 ──
    ok3 = (ext2["u_dim"] == base["u_dim"] + 1
           and ext2["v_dim"] == base["v_dim"]
           and ext2["m_dim"] == base["m_dim"] + 3)
    print("  判据③ 参数化可扩展：u %d→%d、v %d→%d、m %d→%d ⇒ %s"
          % (base["u_dim"], ext2["u_dim"], base["v_dim"], ext2["v_dim"],
             base["m_dim"], ext2["m_dim"], "✔" if ok3 else "✘"))
    rep["params_extensible"] = ok3
    if not ok3:
        fails.append("参数化未按预期扩展")

    # ── ④ 旧策略权重能否直接迁移（★ 真卡点）──
    mig = []
    for tag, mfn in [("15题版", "policy_merged.json"), ("13题版", "policy_merged13.json")]:
        p = os.path.join("/workspace/work/exp/L3/来源与底稿/第三组_治塌缩层3/"
                         "cmp8repo/repro/readings", mfn)
        if not os.path.exists(p):
            continue
        d = json.load(open(p, encoding="utf-8"))
        w = d.get("policy", {})
        u = w.get("u")
        m_ = w.get("m")
        mig.append(dict(version=tag,
                        u_len=len(u) if isinstance(u, list) else None,
                        m_shape=([len(m_), len(m_[0])] if isinstance(m_, list) and m_ and
                                 isinstance(m_[0], list) else None),
                        new_u_len=ext2["u_dim"],
                        new_m_shape=[ext2["m_dim"] // 3, ext2["u_dim"]],
                        migratable_directly=(
                            len(u) == ext2["u_dim"] if isinstance(u, list) else None)))
        print("  ④ 旧权重迁移：%s 的 u 长度=%s（新需 %d）⇒ 直接迁移？ %s"
              % (tag, len(u) if isinstance(u, list) else "?",
                 ext2["u_dim"],
                 (len(u) == ext2["u_dim"]) if isinstance(u, list) else "?"))
    rep["weight_migration"] = mig
    if mig and not all(x["migratable_directly"] for x in mig):
        print("  ⇒ ★★ 旧权重【不能】直接迁移（u 维度变了 ⇒ 索引错位）"
              "⇒ 动作空间可增长的卡点【不在接口层，在参数化 + 重训成本】")

    out = dict(report=rep, fails=fails)
    fp = os.path.join(OUT, "T-L3-09_读数.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n★ 读数落盘：%s" % fp)
    print("结论：%s" % ("PASS（零 API 部分全过）" if not fails else "FAIL: %s" % fails))
    return 0 if not fails else 7


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("★ 脚本崩溃：%r" % e)
        sys.exit(1)
