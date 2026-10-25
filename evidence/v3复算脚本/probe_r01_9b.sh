#!/usr/bin/env bash
# ★ v3 独立审稿人 · R-01 探针：run_finalize.sh ⑨b 断言到底拦不拦得住？
# ======================================================================
# ★ 铁律：★ **绝不改仓内任何文件** ⇒ 本脚本只在 /tmp 下造最小 git 仓。
#
# ★ 探针设计（两个方向都要试）：
#   A（假红）：索引与工作树【真的完全一致】⇒ 断言应当说「一致」⇒ 它怎么说？
#   B（假绿）：非 ASCII 名的 docx【索引真的过期】⇒ 断言应当说「不一致」⇒ 它怎么说？
#   C（对照）：ASCII 名的 docx【索引真的过期】⇒ 断言应当说「不一致」⇒ 它怎么说？
set -uo pipefail
T=/tmp/_r01_probe
rm -rf "$T"; mkdir -p "$T/papers"
cd "$T"
git init -q .
git config user.name t; git config user.email t@t

# 一个非 ASCII 名的 docx（模拟 02_A_…docx）+ 一个 ASCII 名的 docx
printf 'VERSION-OLD-ASCII\n'   > papers/_FINAL_REVIEW_DONE.docx
printf 'VERSION-OLD-NONASCII\n' > papers/02_A_稿.docx
git add -A; git commit -q -m init

# ★ ⑨b 断言块（★ 逐字复制自 tools/run_finalize.sh:79-98）
run_9b () {
python3 - <<'PYEOF'
import subprocess, hashlib, os, sys
REPO = os.path.dirname(os.path.dirname(os.path.abspath("tools/run_finalize.sh")))
tracked = subprocess.run(["git", "ls-files", "papers/*.docx"], capture_output=True, text=True,
                         cwd=REPO).stdout.split()
bad = []
for rel in tracked:
    idx = subprocess.run(["git", "ls-files", "-s", rel], capture_output=True, text=True,
                         cwd=REPO).stdout.split()
    idx_sha = idx[1] if len(idx) > 1 else ""
    wt = os.path.join(REPO, rel)
    wt_sha = hashlib.sha256(open(wt, "rb").read()).hexdigest() if os.path.exists(wt) else ""
    if idx_sha != wt_sha:
        bad.append((rel, idx_sha[:12], wt_sha[:12]))
if bad:
    print("⛔ 索引与工作树不一致：")
    for r, a, b in bad: print("   %s  索引 %s ≠ 工作树 %s" % (r, a, b))
    sys.exit(1)
print("✅ %d 个 docx：索引 == 工作树" % len(tracked))
PYEOF
}

echo "════════ A（假红探针）：索引与工作树【真的完全一致】═══════"
printf 'VERSION-OLD-ASCII\n'   > papers/_FINAL_REVIEW_DONE.docx   # 未改
printf 'VERSION-OLD-NONASCII\n' > papers/02_A_稿.docx                # 未改
run_9b; echo "   ⇒ ⑨b 退出码 = $?  （★ 期望 0 = 一致）"

echo
echo "════════ B（假绿探针）：非 ASCII 名 docx 的索引【真的过期】═══════"
printf 'VERSION-NEW-NONASCII\n' > papers/02_A_稿.docx   # ★ 工作树改了，索引没改
echo "   真实状态：索引 blob=$(git ls-files -s papers/02_A_稿.docx | awk '{print $2}')"
echo "             工作树 sha256=$(sha256sum papers/02_A_稿.docx | cut -c1-16)…  ★ 两个值本就不同算法，不可能相等"
run_9b; echo "   ⇒ ⑨b 退出码 = $?  （★ 期望 1 = 抓到了；但它抓的是 ASCII 那个）"

echo
echo "════════ B2（假绿探针·纯净版）：【只有】非 ASCII 名 docx 过期 ════"
rm -f papers/_FINAL_REVIEW_DONE.docx
git rm -q --cached papers/_FINAL_REVIEW_DONE.docx; rm -f papers/_FINAL_REVIEW_DONE.docx
git commit -q -m "remove ascii docx"
printf 'VERSION-OLD-NONASCII\n' > papers/02_A_稿.docx; git add -A; git commit -q -m "reset nonascii to OLD"
printf 'VERSION-NEW-NONASCII\n' > papers/02_A_稿.docx   # ★ 只有这个过期
echo "   真实状态：★ 索引里是 OLD、工作树是 NEW ⇒ 【真的不一致】"
run_9b; echo "   ⇒ ⑨b 退出码 = $?  （★ 若 =0 ⇒ ★★ 假绿：它没抓到真正过期的 docx ★★）"

echo
echo "════════ C（对照）：ASCII 名 docx 过期，且【索引与工作树同版本】时的行为 ════"
printf 'VERSION-OLD-ASCII\n' > papers/_FINAL_REVIEW_DONE.docx
git add -A; git commit -q -m "add ascii docx"
echo "   真实状态：★ 索引与工作树【完全一致】（同一个 commit）"
run_9b; echo "   ⇒ ⑨b 退出码 = $?  （★ 期望 0；若 =1 ⇒ ★★ 假红 ★★）"
