#!/usr/bin/env bash
# ★ v3 独立审稿人 · R-02/R-03 探针：A3 三条新通道【会不会放过真读数】
# ======================================================================
# ★ 铁律：★ 不改仓内任何文件 ⇒ 注入只发生在 /tmp 的副本上，
#   check_l3.py 支持 argv[1] 指定稿件路径 ⇒ 直接喂副本。
set -uo pipefail
REPO=/workspace/work/llm-creativity-mechanism-papers
SRC="$REPO/papers/06_L3_层3自修改_交差稿.md"
T=/tmp/_a3_probe
rm -rf "$T"; mkdir -p "$T"

run_a3 () {   # $1 = 稿件副本路径
  ( cd "$REPO" && python3 tools/check_l3.py "$1" 2>&1 ) \
    | grep -E "正文不同数字|不在允许集合|❌" | head -8
}

echo "════════ 基线（未注入）════════"
cp "$SRC" "$T/base.md"
run_a3 "$T/base.md"

echo
echo "════════ 探针 1：裸行号通道 —— 新读数写成 \":77\" ════════"
cp "$SRC" "$T/p1.md"
printf '\n★ 探针：本批新增读数:77 个（★ 真实存在的、但未登记的新读数）\n' >> "$T/p1.md"
run_a3 "$T/p1.md"
echo "   ⇒ 若上面没有 ❌ ⇒ ★ 裸行号通道把新读数 77 放过了"

echo
echo "════════ 探针 2：日期通道 —— 写一个日期就能新豁免它的两个数字 ════════"
cp "$SRC" "$T/p2.md"
printf '\n★ 探针：本批新增读数 26 与 77 个（★ 未登记的新读数）\n' >> "$T/p2.md"
printf '★ 探针日期：2026-07-31\n' >> "$T/p2.md"
run_a3 "$T/p2.md"
echo "   ⇒ 26/77 是否被抓住？（★ 日期 2026-07-31 会把 07 与 31 全局豁免）"

echo
echo "════════ 探针 3：对照 —— 不用任何通道形态 ════════"
cp "$SRC" "$T/p3.md"
printf '\n★ 探针：本批新增读数 26 个（★ 未登记的新读数）\n' >> "$T/p3.md"
run_a3 "$T/p3.md"
echo "   ⇒ 期望：❌（抓到了）⇒ 说明判据【基本盘】还能用，只是三条通道把它挖穿了"

echo
echo "════════ 探针 4：commit sha 通道 —— 真实 sha 片段 ════════"
cp "$SRC" "$T/p4.md"
printf '\n★ 探针：基线 commit 0a1b2c3d4e5f6789\n★ 本批新增读数 26 个\n' >> "$T/p4.md"
run_a3 "$T/p4.md"
echo "   ⇒ sha 通道是否把 26 一起放过？（★ sha 里的数字片段被全局豁免）"
