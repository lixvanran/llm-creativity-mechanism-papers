#!/usr/bin/env bash
# build_docx.sh —— 从 md 重建全部 docx（**构建命令固化**，保证外部能逐字节重建出同样的 docx）
#
# ★ 为什么把命令写死随包交付：
#   pandoc 的默认 `smart` 扩展会把 `"` → `“”`、`...` → `…` ⇒ ⇒ **同一份 md 在不同机器/不同
#   pandoc 版本下可能产出不同的 docx** ⇒ ⇒ 外部就"复核不了"我们交付的 docx。
#   ⇒ 下面这条命令把 `smart` 关掉 ⇒ **md 与 docx 逐字一致** ⇒ 「单元格零丢失」才是个真判据。
#
# 用法：bash build_docx.sh [目录]
set -euo pipefail
D="${1:-$(cd "$(dirname "$0")" && pwd)}"
FROM="markdown-smart+pipe_tables+raw_html"

n=0
for f in "$D"/*.md; do
  [ -e "$f" ] || continue
  b="${f%.md}"
  pandoc "$f" -o "$b.docx" --from="$FROM"
  echo "  ✔ $(basename "$b").docx  $(stat -c%s "$b.docx") B"
  n=$((n+1))
done
echo "★ 重建完成：$n 个 docx（from=$FROM）"
echo "★ 交付前请跑：python3 check_docx.py \"$D\"  && python3 check_package.py <本包>.zip"
