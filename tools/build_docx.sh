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

n=0; fails=0
for f in "$D"/*.md; do
  [ -e "$f" ] || continue
  b="${f%.md}"
  # ★ 单个失败不许中断整轮（`set -e` 会让后面的 docx 保持陈旧 ⇒ 后续「单元格丢失」是假的）
  if ! pandoc "$f" -o "$b.docx" --from="$FROM"; then
    echo "  ⛔ 失败：$(basename "$f")"; fails=$((fails+1)); continue
  fi
  # ★★ 内嵌【源 md 的 sha256】⇒ 「docx 是否与源同步」改用【内容指纹】判 ⇒ 与时间戳彻底解耦
  #   （★ 理由见 tools/embed_src_sha.py 头部：可复现打包 + extractall 不还原 mtime ⇒
  #     时间戳判据在【交付态】会假红，且红不红取决于用哪个工具解压）
  if ! python3 "$(dirname "$0")/embed_src_sha.py" "$f" "$b.docx"; then
    echo "  ⛔ 指纹内嵌失败：$(basename "$f")"; fails=$((fails+1)); continue
  fi
  echo "  ✔ $(basename "$b").docx  $(stat -c%s "$b.docx") B"
  n=$((n+1))
done
echo "★ 重建完成：$n 个 docx，失败 $fails（from=$FROM）"
[ "$fails" -eq 0 ] || { echo "⛔ 有 $fails 个文件转换失败 ⇒ 不要继续交付"; exit 1; }
echo "★ 交付前请跑：python3 check_docx.py \"$D\"  && python3 check_package.py <本包>.zip"
