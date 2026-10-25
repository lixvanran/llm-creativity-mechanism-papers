#!/usr/bin/env bash
# ★ v3.1 独立审稿人 · 探针：新 ⑨a（docx ↔ md 内嵌指纹）能不能真红？
# ======================================================================
# ★ 铁律：★ 不改仓内任何文件 ⇒ 只在 /tmp 造等价仓。
# ★ 探针：
#   A  真·指纹过期（docx 内嵌的是旧 md 的 sha，md 已改）⇒ 应当红
#   B  docx 内没有指纹（老版 docx）⇒ 应当【跳过】而不是红
set -uo pipefail
T=/tmp/_r9a_probe
rm -rf "$T"; mkdir -p "$T/papers"; cd "$T"
git init -q .; git config user.name t; git config user.email t@t
printf 'MD-VERSION-1\n' > papers/a.md
python3 - <<'PY'
import zipfile, hashlib, os
md = "papers/a.md"
h = hashlib.sha256(open(md,'rb').read()).hexdigest()[:16]
with zipfile.ZipFile("papers/a.docx","w") as z:
    z.writestr("docProps/core.xml", '<?xml version="1.0"?><cp:coreProperties xmlns:cp="x"><dc:description>%s</dc:description></cp:coreProperties>' % h)
    z.writestr("word/document.xml", "<w:document/>")
# 一个无指纹的老 docx
with zipfile.ZipFile("papers/old.docx","w") as z:
    z.writestr("word/document.xml", "<w:document/>")
print("   已造：papers/a.md（v1）、papers/a.docx（内嵌 v1 指纹）、papers/old.docx（无指纹）")
PY
git add -A; git commit -q -m init

# ★ ⑨a 段（★ 逐字复制自修后的 tools/run_finalize.sh）
run_9a () {
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
}

echo "════════ A（基线）：docx 与 md 同步 ⇒ 期望 ✅ ════════"
run_9a; echo "   ⇒ 退出码=$?"

echo
echo "════════ A2：docx 无指纹（老版 docx）⇒ 期望【跳过】而不是红 ════════"
run_9a; echo "   ⇒ 退出码=$?  （★ skipped 列表里有 old.docx 吗？）"

echo
echo "════════ B：★ md 改了、docx 指纹没重嵌 ⇒ 期望红 ════════"
printf 'MD-VERSION-2-CHANGED\n' > papers/a.md   # ★ 只改 md，不重嵌 docx
run_9a; echo "   ⇒ 退出码=$?  （★ 期望 1 = 能红）"
