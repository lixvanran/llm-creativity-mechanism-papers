#!/usr/bin/env bash
# ★ v3 独立审稿人 · R-09 探针：tools/update_entry_sha.py 能不能正确回填？
# ======================================================================
# ★ 铁律：★ **绝不改仓内任何文件** ⇒ 整个测试在 /tmp 的副本仓里做。
set -uo pipefail
REPO=/workspace/work/llm-creativity-mechanism-papers
T=/tmp/_r09_probe
rm -rf "$T"; mkdir -p "$T/tools" "$T/papers"

# ★ 只复制脚本真正需要的三个东西
cp "$REPO/tools/update_entry_sha.py" "$T/tools/"
cp "$REPO/交付总览_人肉审版_2026-10-25.md" "$T/"
cp "$REPO/papers/01_L1_PrematureConvergence_交差稿.md" "$T/papers/"
cp "$REPO/papers/02_A_SelectionIsNotCreation_稿.md" "$T/papers/"
cp "$REPO/papers/03_C_SixWaysToLookDone_稿.md" "$T/papers/"
cp "$REPO/papers/04_D_StateMachineIsNotYetAPrompt_交差稿.md" "$T/papers/"
cp "$REPO/papers/06_L3_层3自修改_交差稿.md" "$T/papers/"

cd "$T"
echo "════════ 步骤 0：副本初始状态 ════════"
grep -n "五篇 sha256" 交付总览_人肉审版_2026-10-25.md | cut -c1-260

echo
echo "════════ 步骤 1：先跑一次（应当已是最新 / 或回填）════════"
python3 tools/update_entry_sha.py; echo "EXIT=$?"

echo
echo "════════ 步骤 2：★ 故意改一篇 md 的内容 ★ ⇒ sha 必须过期 ════════"
printf '\n★ v3 探针注入的一句话（用于改变文件 sha）\n' >> "papers/03_C_SixWaysToLookDone_稿.md"
echo "   改后 03_C 的实测 sha16 = $(sha256sum papers/03_C_SixWaysToLookDone_稿.md | cut -c1-16)"
echo "   入口 md 里写的 C = $(grep -o 'C `[0-9a-f]\{16\}`' 交付总览_人肉审版_2026-10-25.md | head -1)"

echo
echo "════════ 步骤 3：再跑一次（★ 必须把 C 同步成新 sha）════════"
python3 tools/update_entry_sha.py; echo "EXIT=$?"
echo "   回填后入口 md 里写的 C = $(grep -o 'C `[0-9a-f]\{16\}`' 交付总览_人肉审版_2026-10-25.md | head -1)"
echo "   ★ 实测 C sha16        = $(sha256sum papers/03_C_SixWaysToLookDone_稿.md | cut -c1-16)"

echo
echo "════════ 步骤 4：★ 幂等性（再跑一次，应报「未变」且仍复核通过）════════"
python3 tools/update_entry_sha.py; echo "EXIT=$?"

echo
echo "════════ 步骤 5：★ 破坏性检验 —— 把入口 md 的 sha 行整行删掉 / 改成非 hex ════════"
cp 交付总览_人肉审版_2026-10-25.md /tmp/_r09_backup.md
python3 - <<'PY'
import io,re,pathlib
p=pathlib.Path("交付总览_人肉审版_2026-10-25.md")
t=p.read_text(encoding="utf-8")
# 把 C 的 sha 换成一个非 16 位 hex 的值（模拟"半改"）
t2=re.sub(r"(C `)[0-9a-f]{16}(`)", r"\1ZZZZ\2", t, count=1)
p.write_text(t2,encoding="utf-8")
print("   ★ 已把 C 的 sha 改成非 hex 形态 'ZZZZ'")
PY
python3 tools/update_entry_sha.py; echo "EXIT=$?  （★ 期望：★ 复核失败并退出 1 ⇒ 静默半改被挡住）"

echo
echo "════════ 步骤 6：★ 恢复后复跑（确认脚本没把文件写坏）════════"
cp /tmp/_r09_backup.md 交付总览_人肉审版_2026-10-25.md
python3 tools/update_entry_sha.py; echo "EXIT=$?"
echo
echo "★ 仓内原件是否被动过？（应当没有）"
cd "$REPO" && git status --porcelain | head
echo "   ★ 仓内入口 md sha16 = $(sha256sum 交付总览_人肉审版_2026-10-25.md | cut -c1-16)"
echo "   ★ 审计开始时记录的 sha16 = 2c37a4424e67f04a"
