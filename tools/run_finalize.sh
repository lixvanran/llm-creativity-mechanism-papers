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

hr "⑨a 断言：★ 每个 docx 的【内嵌源指纹】必须 == 对应 md 的当前 sha（★ docx↔md 不同步 ⇒ 就是 S-3 的实质）"
# ★★★★ 口径说明（★ 2026-10-25 · 经审稿人 v3 指正后重定）：★★★★
#   ★ v2 说的「S-3：包里装旧 docx」⇒ ★ **在本打包器实现下【本来就不成立】**：
#     ★ `pack_papers.py` 的 `shutil.copy2(os.path.join(root, n), dst)` ⇒ ★ **取的是【工作树字节】**
#     ⇒ ★ 索引里的旧版本【不会】进包 ⇒ ★ 那条担忧是【伪 S-3】
#   ★ ★ **真正成立、且真正要防的是**：★ **docx 与它的源 md 【不同步】**（★ 指纹过期）
#     ⇒ ★ 那会让 docx 里的表格/正文与 md 对不上 ⇒ ★ 读者读 docx 会读到旧内容
#   ⇒ ★ 因此 ⑨a 改成核【指纹】⇒ ★ 这是**内容级**判据（★ 不依赖时间戳、★ 不依赖索引字节）
python3 - <<'PYEOF'
import subprocess, os, re, sys, zipfile, hashlib
REPO = os.getcwd()
def sh(*a): return subprocess.run(list(a), capture_output=True, cwd=REPO)
out = sh("git", "-c", "core.quotepath=false", "ls-files", "--cached", "--others",
         "--exclude-standard", "*.docx").stdout.decode("utf-8")
docs = [x for x in out.split() if x and not x.startswith("baseline/")]
bad, skipped = [], []
for rel in docs:
    md = rel[:-5] + ".md"
    if not os.path.exists(os.path.join(REPO, md)):
        skipped.append((rel, "★ 无同名 md")); continue
    try:
        with zipfile.ZipFile(os.path.join(REPO, rel)) as z:
            core = z.read("docProps/core.xml").decode("utf-8", "ignore")
    except Exception as e:
        bad.append((rel, "★ 打不开：%s" % e)); continue
    m = re.search(r"([0-9a-f]{16})", core)
    cur = hashlib.sha256(open(os.path.join(REPO, md), "rb").read()).hexdigest()[:16]
    if not m:
        skipped.append((rel, "★ docx 内无指纹（★ 老版 docx）")); continue
    if m.group(1) != cur:
        bad.append((rel, "★ 指纹 %s ≠ md %s" % (m.group(1), cur)))
if bad:
    print("⛔ docx ↔ md 不同步（★ 读者读 docx 会读到旧内容）：")
    for r, why in bad: print("   %s  %s" % (r, why))
    sys.exit(1)
print("✅ %d 个 docx：内嵌指纹 == 对应 md 的当前 sha（★ docx↔md 同步）" % (len(docs) - len(skipped)))
for r, why in skipped[:6]: print("   （跳过 %s：%s）" % (r, why))
PYEOF

hr "⑧b 合订本（★ 生成 + 「没改一个字」判据）"
python3 tools/build_anthology.py 2>&1 | tail -7
python3 tools/check_anthology.py 2>&1 | tail -3

hr "⑨ 提交（★ 打包器按 git ls-files 取内容集 ⇒ 必须先提交）"
git add -A
git -c user.name="Mavis" -c user.email="mavis@local" commit -q -m "★ 收口：四篇定稿 + docx 全量重建 + 交付态基线快照" || echo "（★ 无改动）"
git log --oneline -1

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
