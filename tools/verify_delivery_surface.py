#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 交付面承诺核验（★ 2026-10-25）

★★★ 为什么必须有这个：★★
  ★ 入口 md 的 §7 写着「第三方怎么自己核」⇒ ★ **那 9 条命令是【我给用户的承诺】**
  ★ ⇒ ★ **承诺必须先在自己手上跑通** ⇒ ★ 否则用户照着跑第一条就卡住
  ★ ⇒ ★ ★ 而且：**§7 里的命令如果【在交付态假绿】**（★ 如指针数=0 却报「全一致」）
     ⇒ ★ 用户会白信 ⇒ ★ ⇒ ★ 这比命令直接报错更危险

★ ★ **落法**：★ **从入口 md 里【把命令抽出来】**（★ 不是在这里另抄一份 ⇒ ★ 文档改了它就跟着改）
★ ⇒ ★ 在【交付态那棵树】上逐条实跑 ⇒ ★ 汇总 ⇒ ★ 任何一条挂 ⇒ ★ 整体判红

★ **用法**：
  python3 tools/verify_delivery_surface.py                    # ★ 跑仓内那棵
  python3 tools/verify_delivery_surface.py --dir /path/to/x    # ★ 跑指定的树（★ 交付态）
"""
import sys, re, pathlib, subprocess, argparse
sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parent.parent

ap = argparse.ArgumentParser()
ap.add_argument("--dir", default=str(ROOT), help="★ 在哪棵树上跑（★ 交付态就指解包副本）")
ap.add_argument("--entry", default=None, help="★ 入口 md（★ 默认 <dir>/交付总览_人肉审版_2026-10-25.md）")
ap.add_argument("--zip", default=None, help="★ 用来替换命令里【zip 路径占位符】的真实 zip")
args = ap.parse_args()
TREE = pathlib.Path(args.dir).resolve()
ENTRY = pathlib.Path(args.entry) if args.entry else (TREE / "交付总览_人肉审版_2026-10-25.md")

if not ENTRY.exists():
    print("⛔ 找不到入口 md：%s" % ENTRY); sys.exit(2)
txt = ENTRY.read_text(encoding="utf-8")
if "## 7 ·" not in txt:
    print("⛔ 入口 md 里没有「## 7 ·」小节 ⇒ ★ 抽不出承诺列表"); sys.exit(2)
sec = txt[txt.index("## 7 ·"):]
sec = sec[:sec.index("\n## ")] if "\n## " in sec else sec

CMDS = []
for m in re.finditer(r"^python3 .+$", sec, re.M):
    c = m.group(0).strip()
    CMDS.append(c)

# ★ 占位符（★ 如 `<本包>.zip`）⇒ ★ 替换成真实路径后跑
# ★ zip 路径占位符 ⇒ ★ 替换规则（★ ★ 交付态核验时，★ 我们手里有真 zip ⇒ ★ 那条命令也能真跑）
_ZIP = args.zip
if not _ZIP:
    for cand in sorted(TREE.glob("*.zip")):
        _ZIP = str(cand); break
PLACEHOLDER = {
    "<本包>.zip": _ZIP or "<需填 zip 路径>",
    "/path/to/本包.zip": _ZIP or "<需填 zip 路径>",
    "<你手上那个 zip 的路径>": _ZIP or "<需填 zip 路径>",
}
print("═" * 78)
print("★ 交付面承诺核验 · 树 = %s" % TREE)
print("★ 从入口 md §7 抽出 %d 条命令（★ 文档改了这里就跟着改）" % len(CMDS))
print("═" * 78)
fails, skipped, ok = [], [], 0
for c in CMDS:
    real = c
    for k, v in PLACEHOLDER.items():
        real = real.replace(k, v)
    # ★ 注释尾巴剥掉
    real = re.sub(r"\s+#.*$", "", real)
    if "<" in real or ">" in real:
        skipped.append((c, "★ 含未替换的占位符")); 
        print("  ⏭ %s  ⇒ ★ 占位符未替换、★ 跳过（★ 文档里要写清怎么替）" % c)
        continue
    r = subprocess.run(real, shell=True, cwd=TREE, capture_output=True, text=True)
    if r.returncode == 0:
        ok += 1
        last = [l for l in (r.stdout + r.stderr).strip().split("\n") if l.strip()]
        print("  ✔ EXIT=0  %s" % c)
        if last: print("      … %s" % last[-1][:150])
    else:
        fails.append((c, r.returncode))
        print("  ⛔ EXIT=%d  %s" % (r.returncode, c))
        tail = (r.stdout + r.stderr).strip().split("\n")[-3:]
        for l in tail: print("      … %s" % l[:150])
print("─" * 78)
print("★ 交付面命令：%d 条 ｜ 通过 %d ｜ 失败 %d ｜ 跳过 %d" % (len(CMDS), ok, len(fails), len(skipped)))
if fails:
    print("⛔ 有命令在【这棵树上】跑不通 ⇒ ★ **入口 md §7 的承诺不成立** ⇒ ★ 不许发")
    for c, rc in fails: print("   %s (EXIT=%d)" % (c, rc))
    sys.exit(1)
print("★ 总体：✅ 入口 md 承诺的每条命令在这棵树上都跑通了")
