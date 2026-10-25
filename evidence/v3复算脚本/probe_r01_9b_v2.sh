#!/usr/bin/env bash
# ★ v3 独立审稿人 · R-01 复验（★ 针对 owner 修后的版本）
# ======================================================================
# ★ owner 的修法：git -c core.quotepath=false ls-files --cached --others
#   + git show :<rel> 与工作树逐字节比
# ★ 我要验三件事：
#   ① 真不一致时能不能红（owner 的主张）
#   ② ★ 未追踪（untracked）的 docx 会不会【假红】（★ --others 新引入的）
#   ③ ★ ⑨b 在脚本里排在 ⑨（git add -A + commit）★ 之后 ⇒ 还能不能红？
set -uo pipefail
T=/tmp/_r01_probe2
rm -rf "$T"; mkdir -p "$T/papers" "$T/tools"
cd "$T"
git init -q .; git config user.name t; git config user.email t@t
printf 'OLD-ASCII\n' > papers/_FINAL_REVIEW_DONE.docx
printf 'OLD-NONASCII\n' > "papers/02_A_稿.docx"
git add -A; git commit -q -m init

# ★ 当前 ⑨b 段（★ 逐字复制自修后的 tools/run_finalize.sh:79-106）
run_9b () {
python3 - <<'PYEOF'
import subprocess, hashlib, os, sys
REPO = os.path.dirname(os.path.dirname(os.path.abspath("tools/run_finalize.sh")))
def sh(*a):
    return subprocess.run(list(a), capture_output=True, cwd=REPO)
out = sh("git", "-c", "core.quotepath=false", "ls-files", "--cached", "--others",
         "--exclude-standard", "*.docx").stdout.decode("utf-8")
tracked = [x for x in out.split() if x and not x.startswith("baseline/")]
bad = []
for rel in tracked:
    wt = os.path.join(REPO, rel)
    if not os.path.exists(wt):
        continue
    idx_bytes = sh("git", "show", ":" + rel).stdout
    wt_bytes = open(wt, "rb").read()
    if idx_bytes != wt_bytes:
        bad.append((rel, hashlib.sha256(idx_bytes).hexdigest()[:12],
                       hashlib.sha256(wt_bytes).hexdigest()[:12]))
if bad:
    print("⛔ 索引与工作树不一致：")
    for r, a, b in bad: print("   %s  索引 %s ≠ 工作树 %s" % (r, a, b))
    sys.exit(1)
print("✅ %d 个 docx：索引字节 == 工作树字节" % len(tracked))
PYEOF
}

echo "════════ ① 真不一致（索引旧 / 工作树新）能不能红？ ════════"
printf 'NEW-ASCII\n' > papers/_FINAL_REVIEW_DONE.docx
printf 'NEW-NONASCII\n' > "papers/02_A_稿.docx"
run_9b; echo "   ⇒ 退出码=$?  （★ 期望 1 = 能红）"

echo
echo "════════ ② ★ 未追踪（untracked）的 docx ⇒ 会不会假红？ ════════"
git checkout -q -- . 2>/dev/null; git reset -q --hard
printf 'OLD-ASCII\n' > papers/_FINAL_REVIEW_DONE.docx
printf 'OLD-NONASCII\n' > "papers/02_A_稿.docx"
git add -A; git commit -q -m "sync"
printf 'BRAND-NEW-UNTRACKED\n' > papers/_NEW_untracked.docx   # ★ 未追踪
echo "   ★ 新增一个未追踪 docx（★ 工作树有、索引无）"
run_9b; echo "   ⇒ 退出码=$?  （★ 若=1 ⇒ ★★ 假红：git show :<未追踪路径> = 空 ⇒ 必然不等 ★★）"

echo
echo "════════ ③ ★ 脚本真实顺序：⑨(git add -A + commit) → ⑨b ⇒ 还能红吗？ ════════"
rm -f papers/_NEW_untracked.docx
git reset -q --hard; git clean -qfd
printf 'OLD-ASCII\n' > papers/_FINAL_REVIEW_DONE.docx
printf 'OLD-NONASCII\n' > "papers/02_A_稿.docx"
git add -A; git commit -q -m "base"
printf 'STALE-INDEX-ASCII\n' > papers/_FINAL_REVIEW_DONE.docx   # ★ 索引旧、工作树新
printf 'STALE-INDEX-NONASCII\n' > "papers/02_A_稿.docx"        # ★ 索引旧、工作树新
echo "   ★ 真实状态：索引 = OLD，工作树 = STALE ⇒ 【真的不一致】"
echo "   --- 先跑 ⑨（★ git add -A + commit）---"
git add -A
git -c user.name="Mavis" -c user.email="mavis@local" commit -q -m "收口" || echo "（★ 无改动）"
echo "   --- 再跑 ⑨b ---"
run_9b; echo "   ⇒ 退出码=$?  （★ 若=0 ⇒ ★★ ⑨b 排在 ⑨ 之后 ⇒ 恒真 ⇒ 抓不到任何东西 ★★）"
echo
echo "   ★ 复核：⑨ 之后索引里到底是什么字节？"
echo "     git show :papers/_FINAL_REVIEW_DONE.docx = $(git show :papers/_FINAL_REVIEW_DONE.docx | head -c 30)"
echo "     工作树 = $(head -c 30 papers/_FINAL_REVIEW_DONE.docx)"
