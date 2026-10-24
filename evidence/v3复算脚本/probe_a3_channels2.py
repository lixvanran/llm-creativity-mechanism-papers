#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★ v3 独立审稿人 · R-02/R-03 探针（修正版）
======================================================================
★ 上一版探针的【对照组失效】了：注入的 26 已经在 A3 的 `allowed` 集合里
  （A3 的 allowed 收割【整个 底稿目录】里的每一个数字）⇒ 抓不到它不算证据。
★ 本版先算出 allowed 集合，再挑一个【确定不在里面】的数做注入。

★ 铁律：★ 只在 /tmp 造副本 ⇒ 不动仓内任何文件。
"""
import io
import os
import re
import subprocess
import sys

REPO = "/workspace/work/llm-creativity-mechanism-papers"
DRAFT = os.path.join(REPO, "来源与底稿/第三组_治塌缩层3")
SPEC = os.path.join(REPO, "改稿规格_方向3_层3_2026-10-24.md")
RECEIPT = os.path.join(REPO, "papers/审稿回执_方向3层3_规格审计_2026-10-24.md")
SRC = os.path.join(REPO, "papers/06_L3_层3自修改_交差稿.md")
T = "/tmp/_a3_probe2"

# ── 复刻 check_l3.py 的 allowed 集合 ──
allowed = set()
for root, _d, files in os.walk(DRAFT):
    for f in files:
        p = os.path.join(root, f)
        try:
            txt = io.open(p, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for m in re.finditer(r"\d+(?:\.\d+)?", txt):
            allowed.add(m.group(0))
for p in (SPEC, RECEIPT):
    for m in re.finditer(r"\d+(?:\.\d+)?", io.open(p, encoding="utf-8").read()):
        allowed.add(m.group(0))

md0 = io.open(SRC, encoding="utf-8").read()

# ── 挑一个确定不在 allowed 里的整数 ──
probe_num = None
for cand in range(7000, 9999):
    if str(cand) not in allowed and ("%d" % cand) not in md0:
        probe_num = cand
        break
print("★ 注入用数字 = %d  （★ 确认不在 allowed 集合、也不在原稿里）" % probe_num)
print("★ allowed 集合大小 = %d" % len(allowed))
print()


def run_a3(path):
    r = subprocess.run([sys.executable, "tools/check_l3.py", path],
                       capture_output=True, text=True, cwd=REPO)
    out = r.stdout
    line = [l for l in out.split("\n") if "正文不同数字" in l]
    chans = {}
    for key, tag in (("裸行号通道", "BARE"), ("commit sha / 版本串通道", "SHA")):
        for l in out.split("\n"):
            if key in l:
                chans[tag] = l.strip()
    return (line[0].strip() if line else "(无)"), chans, r.returncode


os.makedirs(T, exist_ok=True)


def trial(name, inject_text):
    p = os.path.join(T, "probe.md")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(md0 + "\n" + inject_text + "\n")
    line, chans, rc = run_a3(p)
    print("────────────────────────────────────────────────────────")
    print("【%s】" % name)
    print("  注入：%s" % inject_text.strip()[:110])
    print("  ⇒ %s" % line)
    for k, v in chans.items():
        print("     · %s" % v[:200])
    caught = ("❌" in line) or ("不在允许集合的 0 个" not in line)
    print("  ⇒ 判据结论：%s" % ("★★★ 抓到了（假红风险低）" if caught
                                else "★★★ 没抓到 ⇒ 放过了真读数"))
    return caught


print("════════ 基线（不注入）════════")
line, chans, rc = run_a3(SRC)
print("  ⇒ %s" % line)
print()

results = {}
results["对照·裸数字"] = trial("对照 A · 裸数字（无任何通道形态）",
    "★ 本批新增读数 %d 个（未登记的新读数）" % probe_num)
results["裸行号通道"] = trial("探针 B · 裸行号形态 \":%d\"" % probe_num,
    "★ 本批新增读数:%d（未登记的新读数）" % probe_num)
results["日期通道"] = trial("探针 C · 日期通道（新写一个日期）",
    "★ 本批新增读数 %d 个（未登记的新读数）\n★ 记录日期 2026-07-31" % probe_num)
results["sha通道"] = trial("探针 D · commit sha 通道",
    "★ 基线 commit 0a1b2c3d4e5f6789\n★ 本批新增读数 %d 个（未登记的新读数）" % probe_num)
results["裸行号+文件名前缀"] = trial("探针 E · 既有 LINEREF 形态 file.py:%d" % probe_num,
    "★ 见 tools/x.py:%d 处" % probe_num)

print()
print("════════ 汇总 ════════")
for k, v in results.items():
    print("  %-22s ⇒ %s" % (k, "抓到 ✔" if v else "★ 没抓到（放过真读数）"))
