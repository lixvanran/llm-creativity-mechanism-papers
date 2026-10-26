#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_manifest.py —— 生成 SHA256SUMS.txt

★ 为什么是这个形态（★ 跨项目可复用 ★）
--------------------------------------------------
1. **内容集合由 `git ls-files` 定义** ⇒ 不会列进仓里根本没有的文件
   （那会让 `sha256sum -c` 假红，读者以为包坏了）
2. **排除 SHA256SUMS.txt 自己** ⇒ 不写自指量（★ 自指量一改就过期 ★）
3. **用 `-z` + NUL 分隔** ⇒ 正确处理中文路径与含空格路径
   （★ git 默认把非 ASCII 路径转义成 `\344\273\233` 形式 ★ ⇒ 不关掉会静默算错文件）
4. **写入器（本脚本）与检查器（`sha256sum -c`）职责分离** ⇒ 一个写、一个读，
   不让同一个脚本既写又验自己
5. **不写死任何计数** ⇒ 文件数由内容集合决定，写进文档会立刻过期

用法：
    python3 tools/make_manifest.py            # 生成 SHA256SUMS.txt
    python3 tools/make_manifest.py --check    # 只比对，不写（退出码非 0 = 清单过期）
"""

import hashlib
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(REPO, "SHA256SUMS.txt")
SELF = "SHA256SUMS.txt"


def tracked_files():
    """★ git ls-files -z ★（NUL 分隔 ⇒ 中文/空格路径安全）"""
    out = subprocess.run(
        ["git", "-C", REPO, "-c", "core.quotePath=false", "ls-files", "-z"],
        capture_output=True, check=True,
    ).stdout
    return [p.decode("utf-8") for p in out.split(b"\0") if p]


def untracked_not_ignored():
    """★ 未暂存、但也不被 ignore 的文件 ★

    ★★ 为什么必须查这个（★ 本轮实测抓到的真 bug ★★）：
    内容集合 = `git ls-files` ⇒ **只含【已跟踪】的文件** ⇒
    一个新建但忘了 `git add` 的文件**不会进清单** ⇒
    `sha256sum -c` 对它**根本不会报错** ⇒ **漏文件是静默的** ★
    ⇒ 违反「失败路径不许静默归零」的同族纪律 ⇒
    ★ 这里让它【响亮】：未暂存的文件一律报出来、--check 判非 0 ★
    """
    out = subprocess.run(
        ["git", "-C", REPO, "-c", "core.quotePath=false", "ls-files", "-z",
         "--others", "--exclude-standard"],
        capture_output=True, check=True,
    ).stdout
    return [p.decode("utf-8") for p in out.split(b"\0") if p]


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build():
    rows = []
    missing = []
    for rel in sorted(tracked_files()):
        if rel == SELF:
            continue                      # ★ 不写自指量 ★
        full = os.path.join(REPO, rel)
        if not os.path.isfile(full):
            missing.append(rel)
            continue
        rows.append((sha256_of(full), rel))
    return rows, missing


def main():
    check_only = "--check" in sys.argv
    rows, missing = build()
    extra = untracked_not_ignored()

    if missing:
        print("❌ git 跟踪但工作区缺失（%d 个）：" % len(missing), file=sys.stderr)
        for m in missing:
            print("   ★ %s" % m, file=sys.stderr)
        return 2

    lines = ["%s  %s" % (h, rel) for h, rel in rows]
    body = "\n".join(lines) + "\n"

    def report_extra():
        if not extra:
            return
        print("⚠️  有 %d 个【未暂存】的文件不在清单里" % len(extra), file=sys.stderr)
        print("   ★ 内容集合 = git 跟踪的文件 ⇒ 它们还没 git add ⇒ 清单漏了它们",
              file=sys.stderr)
        for e in extra[:30]:
            print("   ★ %s" % e, file=sys.stderr)
        if len(extra) > 30:
            print("   ★ … 还有 %d 个" % (len(extra) - 30), file=sys.stderr)

    if check_only:
        try:
            with open(MANIFEST, encoding="utf-8") as f:
                cur = f.read()
        except FileNotFoundError:
            print("❌ SHA256SUMS.txt 不存在", file=sys.stderr)
            return 1
        if cur != body:
            print("❌ 清单过期：与工作区不一致（清单 %d 行 / 现算 %d 行）"
                  % (len(cur.splitlines()), len(rows)), file=sys.stderr)
            report_extra()
            return 1
        if extra:
            print("❌ 清单与已跟踪文件一致，★ 但有未暂存文件没进清单 ⇒ 漏文件会静默",
                  file=sys.stderr)
            report_extra()
            return 1
        print("✅ 清单与工作区一致（%d 个受管文件、★ 无未暂存遗漏 ★）" % len(rows))
        return 0

    with open(MANIFEST, "w", encoding="utf-8") as f:
        f.write(body)
    print("✔ SHA256SUMS.txt 已重生成：%d 个受管文件（%d 字节）"
          % (len(rows), len(body.encode("utf-8"))))
    report_extra()
    return 0


if __name__ == "__main__":
    sys.exit(main())
