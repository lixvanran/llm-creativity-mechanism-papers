#!/usr/bin/env bash
# tools/pack_papers.sh —— 打包器入口（★ 薄包装：真正逻辑在 tools/pack_papers.py）
#
# ★ 为什么要 .sh 包一层 .py：★ 上一版把「打包」和「--repro 连打两次」写成两段内嵌 python
#   ⇒ 第二段忘了定义 `src` ⇒ `NameError` ⇒ ★ 且第二段没有 git 回退 ⇒ 无 git 环境下第二个包内容为空
#   ⇒ ⇒ **同一条纪律在第一个执行点落实了、第二个没落实** ⇒ ⇒ 修法不是补那一行，是【合并成一条路径】
#   ⇒ ★ 现在：`.sh` 只负责转调 ⇒ ★ **打包与自检共用同一份 build() ⇒ 不可能分叉**
#
# 用法：bash tools/pack_papers.sh <输出zip路径> [--repro] [--no-verify-extracted]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/pack_papers.py" "$@"
