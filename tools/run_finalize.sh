#!/usr/bin/env bash
# ★ 收口链路（★ 一条命令，★ 顺序固化，★ 顺序错一次就出一次事故）
#
# ★★★ 为什么顺序是硬的（★ 每一条都来自一次真实事故）：
#   ① md 定稿 → ② 重建 docx → ③ embed 指纹 → ④ 只读新鲜度检查 → ⑤ 重建基线快照
#     → ⑥ 验收器（两种模式）→ ⑦ 负向测试 → ⑧ 指针对拍 → ⑨ 提交 → ⑩ 打包
#     → ⑪ 交付态验收（在【解包副本】里跑）→ ⑫ 可复现重建比对
#   ⇒ ★ **③ 必须在 ② 之后**：★ `embed_src_sha.py` 是写入器，★ 对着旧 docx 跑它
#     会把"可检出的不同步"变成"查不出的不同步"（★ 比不做指纹更危险）
#   ⇒ ★ **⑩ 必须在 ⑨ 之后**：★ 打包器按 `git ls-files` 取内容集 ⇒ ★ 未受管文件进不了包
#   ⇒ ★ **⑪ 必须在 ⑩ 之后**：★ 断言必须在【交付态】读，★ 不在仓里读
#   ⇒ ★ **⑫ 是最后一道**：★ 自己重建一遍并逐字节比对 ⇒ ★ 不靠嘴说"可复现"
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
OUT_ZIP="/workspace/deliver/四篇改稿+方向③层3_交付包_2026-10-25_v2.zip"
DELIVER="/workspace/deliver"

hr() { printf '\n\033[1m═══ %s ═══\033[0m\n' "$*"; }

hr "①b 回填入口 md 的可实测事实（★ sha / 行数 / 三标记计数 ⇒ ★ 全部实测、★ 不许手写）"
python3 tools/update_entry_facts.py 2>&1 | tail -8

hr "② 重建 docx（★ 口径：★【已有 docx 的那个 md】⇒ ★ 覆盖全仓交付面、★ 不给底稿凭空造 docx）"
# ★★★ 为什么改成这个口径（★ 2026-10-25 实测踩到）：★★
#   ★ 原来只重建 `papers/` 和 `support/` ⇒ ★ **根目录的 md（含唯一入口 md）不在覆盖范围**
#     ⇒ ★ 入口 md 的 docx 指纹过期 ⇒ ★ 而指纹是【docx↔md 同步】的唯一判据 ⇒ ★ 判据失效
#   ★ 而"目录下全部 md"也不行 ⇒ ★ 仓内 119 个 md、只有 40 个 docx ⇒ ★ 会给底稿凭空造 79 个
#   ⇒ ★ 正解：★ **对每个已存在的 docx，重建它对应的 md**（★ = 交付面的准确口径）
#   ⇒ ★ ★ **必须排除 baseline/** ⇒ ★ 那是 S1「数字零改动」的基线快照 ⇒ ★ 重建它 = 破坏基线
# ★★★ `core.quotepath=false`（★ 2026-10-25 实测踩到）：★★
#   ★ `git ls-files` 默认对【非 ASCII 路径】加引号（★ core.quotepath=true）
#   ⇒ ★ 拿到的是 `"papers/00_论文簇总纲_交差版.docx"`（★ 连引号一起）⇒ ★ 文件找不到 ⇒ ★ 静默跳过
#   ⇒ ★ ⇒ ★ 修法：★ 关掉 quotepath
# ★ `--others --exclude-standard`（★ 2026-10-25 实测踩到）：★ 只用 `ls-files` **只含已追踪**的文件
#   ⇒ ★ 本轮【新建】的 docx（★ 尚未 git add）不会进 mapfile ⇒ ★ 收口漏重建 ⇒ ★ 指纹过期
mapfile -t DOCX_MDS < <(git -c core.quotepath=false ls-files --cached --others --exclude-standard '*.docx' | grep -v '^baseline/' | sed 's/\.docx$/.md/')
echo "  交付面 md：${#DOCX_MDS[@]} 个（★ 已排除 baseline/）"
bash tools/build_docx.sh "${DOCX_MDS[@]}" 2>&1 | tail -1

hr "③ embed 指纹"
python3 - <<'PY'
import sys, pathlib, subprocess
sys.dont_write_bytecode = True
root = pathlib.Path("."); n = ok = 0
for d in ("papers", "support", "来源与底稿"):
    for dx in sorted(root.glob(f"{d}/*.docx")):
        md = dx.with_suffix(".md")
        if not md.exists(): continue
        n += 1
        r = subprocess.run([sys.executable, "tools/embed_src_sha.py", str(md), str(dx)],
                           capture_output=True, text=True)
        if r.returncode == 0: ok += 1
        else: print("  ✘", dx, r.stdout[-100:], r.stderr[-100:])
print(f"★ embed {ok}/{n}")
assert ok == n, "★ embed 有失败"
PY

hr "④ 只读新鲜度检查"
python3 tools/check_docx_freshness.py 2>&1 | tail -2

hr "⑤ 重建基线快照（★ 交付态可核 S1/S2）"
python3 tools/build_baseline_snapshot.py

hr "⑥ 验收器（仓内模式）"
python3 tools/check_cluster_consistency.py --head 8649661 2>&1 | tail -3
hr "⑥ 验收器（★ 交付态模式）"
python3 tools/check_cluster_consistency.py --baseline-dir baseline 2>&1 | tail -3

hr "⑦ 注意力红线负向测试"
python3 tools/selftest_attribution_redline.py 2>&1 | tail -2

hr "⑧ 指针迁移对拍"
python3 tools/verify_pointer_migration.py 2>&1 | tail -2

hr "⑨ 提交（★ 打包器按 git ls-files 取内容集 ⇒ 必须先提交）"
git add -A
git -c user.name="Mavis" -c user.email="mavis@local" commit -q -m "★ 收口：四篇定稿 + docx 全量重建 + 交付态基线快照" || echo "（★ 无改动）"
git log --oneline -1

hr "⑨b 断言：★ 索引里的每个 docx 必须 == 工作树（★ 否则包里装的是旧 docx）"
python3 - <<'PYEOF'
import subprocess, hashlib, os, sys
REPO = os.path.dirname(os.path.dirname(os.path.abspath("tools/run_finalize.sh")))
def sh(*a):
    return subprocess.run(list(a), capture_output=True, cwd=REPO)
# ★★★ 全部 docx（★ 含未追踪的 ⇒ ★ 新建的也要查）★★★
out = sh("git", "-c", "core.quotepath=false", "ls-files", "--cached", "--others",
         "--exclude-standard", "*.docx").stdout.decode("utf-8")
tracked = [x for x in out.split() if x and not x.startswith("baseline/")]
bad = []
for rel in tracked:
    wt = os.path.join(REPO, rel)
    if not os.path.exists(wt):
        continue
    # ★★★ 判据用【字节比对】（★★ 2026-10-25 实测踩到）：★★
    #   ★ 原写法拿 `git ls-files -s` 的值去比 sha256 ⇒ ★ **那是 git blob sha1**（★ 40 位）
    #     ⇒ ★ **两种不同算法** ⇒ ★ 永远不等 ⇒ ★ **假红**（★ 而工作树其实和索引是一致的）
    #   ⇒ ★ 正解：★ `git show :<path>` 取【索引里的字节】⇒ ★ 与工作树逐字节比
    idx_bytes = sh("git", "show", ":" + rel).stdout
    wt_bytes = open(wt, "rb").read()
    if idx_bytes != wt_bytes:
        bad.append((rel, hashlib.sha256(idx_bytes).hexdigest()[:12],
                       hashlib.sha256(wt_bytes).hexdigest()[:12]))
if bad:
    print("⛔ 索引与工作树不一致（★ 打包器按 git ls-files 取内容集 ⇒ 包里会是旧 docx）：")
    for r, a, b in bad: print("   %s  索引 %s ≠ 工作树 %s" % (r, a, b))
    sys.exit(1)
print("✅ %d 个 docx：索引字节 == 工作树字节（★ 打包内容与工作树一致）" % len(tracked))
PYEOF

hr "⑩ 打包（★ 含交付态验收 + 回读断言）"
python3 tools/pack_papers.py "$OUT_ZIP" --repro 2>&1 | tail -12

hr "⑪ 交付态验收（★ 在解包副本里跑）"
rm -rf /tmp/_final_verify && mkdir -p /tmp/_final_verify
cd /tmp/_final_verify
python3 -c "import zipfile; zipfile.ZipFile('$OUT_ZIP').extractall('.')"
echo "── 清单全量核对 ──"
sha256sum -c SHA256SUMS.txt 2>&1 | grep -c "OK" || true
sha256sum -c SHA256SUMS.txt 2>&1 | grep -c "FAILED" || echo "FAILED 0"
echo "── 验收器（交付态）──"
python3 tools/check_cluster_consistency.py --baseline-dir baseline 2>&1 | tail -3
echo "── 负向测试（交付态）──"
python3 tools/selftest_attribution_redline.py 2>&1 | tail -2
echo "── docx 指纹（交付态）──"
python3 tools/check_docx_freshness.py 2>&1 | tail -2
echo "── ★ 指针迁移对拍（★ 交付态）★ ──"
python3 tools/verify_pointer_migration.py 2>&1 | tail -2
echo "── ★★★ 交付面承诺核验（★ 入口 md §7 的每条命令在【交付态】实跑）★★★"
python3 tools/verify_delivery_surface.py --dir . --zip "$OUT_ZIP" 2>&1 | tail -4

hr "⑫ 可复现重建（★ 无 git 环境原地重建 ⇒ 逐字节比对）"
python3 tools/pack_papers.py /tmp/_final_rebuild.zip --no-verify-extracted 2>&1 | tail -3
if cmp -s "$OUT_ZIP" /tmp/_final_rebuild.zip; then
  echo "★ 逐字节相同 ✔"
else
  echo "★ ✘ 不同！"; exit 1
fi

hr "⑬ 交付面"
cd "$ROOT"
rm -f "$DELIVER"/*.md
for f in 01_L1_PrematureConvergence_交差稿 02_A_SelectionIsNotCreation_稿 \
         03_C_SixWaysToLookDone_稿 04_D_StateMachineIsNotYetAPrompt_交差稿 \
         06_L3_层3自修改_交差稿; do
  cp "papers/$f.md" "$DELIVER/$f.md"
done
cp "交付总览_人肉审版_2026-10-25.md" "$DELIVER/"
ls -la "$DELIVER"
echo
echo "★ 包 sha256:"; sha256sum "$OUT_ZIP"
echo "★ 清单锚点:"; sha256sum "$OUT_ZIP" >/dev/null; python3 -c "
import zipfile,hashlib
z=zipfile.ZipFile('$OUT_ZIP')
print('  ', hashlib.sha256(z.read('SHA256SUMS.txt')).hexdigest(), ' SHA256SUMS.txt')
print('   成员', len(z.namelist()))
"
echo
echo "★★ 收口完成 ★★"
