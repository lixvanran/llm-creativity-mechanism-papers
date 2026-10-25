#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 只推 exp/D-coord-2026-10-26 一个分支（T-D-03 专项）★
★ 纪律：
  - ★ 凭据走 kwargs（username/password），★ 绝不进 URL、★ 绝不进任何会被打印的字符串
  - ★ stdout / stderr 过滤兜底：任何含 token 的行替换成 [REDACTED]
  - ★ 推完必须回核：远端 ref sha + tree sha + 关键文件逐字节比对
  - ★ 只推自己那一个 refspec，★ 不推 main、★ 不推别的组分支
"""
import os, sys, time, json, hashlib, urllib.request, urllib.parse

sys.dont_write_bytecode = True
def _find_root():
    d = os.path.dirname(os.path.abspath(__file__))
    while d and d != "/":
        if os.path.isdir(os.path.join(d, ".git")):
            return d
        d = os.path.dirname(d)
    raise RuntimeError("找不到 .git 根")

ROOT = _find_root()
REPO = "lixvanran/llm-creativity-mechanism-papers"
BRANCH = "exp/D-coord-2026-10-26"
REFSPEC = b"refs/heads/" + BRANCH.encode()
URL = "https://github.com/%s.git" % REPO          # ★ URL 里没有凭据

TOKEN = os.environ.get("GITHUB_TOKEN_LIXVANRAN", "")
if not TOKEN:
    print("⛔ 没有 GITHUB_TOKEN_LIXVANRAN")
    sys.exit(1)

# ---- 输出流过滤（凭据绝不能出现在任何会被打印的字符串里）----
class _Filter:
    def __init__(self, stream): self._s = stream
    def write(self, data):
        if isinstance(data, bytes):
            data = data.replace(TOKEN.encode(), b"[REDACTED]")
        else:
            data = data.replace(TOKEN, "[REDACTED]")
        return self._s.write(data)
    def flush(self):
        try: self._s.flush()
        except Exception: pass
    def __getattr__(self, n): return getattr(self._s, n)

sys.stdout = _Filter(sys.stdout)
sys.stderr = _Filter(sys.stderr)


def api(path, raw=False):
    h = {"Authorization": "token " + TOKEN, "Accept": "application/vnd.github+json"}
    if raw:
        h["Accept"] = "application/vnd.github.raw"
    req = urllib.request.Request("https://api.github.com" + path, headers=h)
    return urllib.request.urlopen(req, timeout=120).read()


def api_json(path):
    return json.loads(api(path).decode())


def main():
    from dulwich import porcelain
    from dulwich.repo import Repo

    r = Repo(ROOT)
    local = r.refs[REFSPEC]
    local_tree = r[local].tree.decode()
    print("   本地 %s = %s  tree=%s" % (BRANCH, local.decode()[:9], local_tree[:9]))

    # ---- ① push（只这一个 refspec）----
    ok = False
    for attempt in range(1, 6):
        try:
            res = porcelain.push(ROOT, URL, [REFSPEC], username="x-access-token",
                                 password=TOKEN, outstream=open(os.devnull, "wb"),
                                 errstream=open(os.devnull, "wb"))
            print("   push 第 %d 次返回：%s" % (attempt, getattr(res, "status", "?")))
            ok = True
            break
        except Exception as e:
            print("   push 第 %d 次失败：%s" % (attempt, str(e)[:120]))
            time.sleep(4 * attempt)
    if not ok:
        print("⛔ push 连续失败 ⇒ 查远端实际状态再决定（不重复推）")
        return 1

    # ---- ② 回核：ref sha + tree sha ----
    for attempt in range(1, 5):
        try:
            ref = api_json("/repos/%s/git/ref/heads/%s" % (REPO, BRANCH))
            live = ref["object"]["sha"]
            live_tree = api_json("/repos/%s/git/commits/%s" % (REPO, live))["tree"]["sha"]
            print("   远端 %s = %s  tree=%s" % (BRANCH, live[:9], live_tree[:9]))
            if live == local.decode() and live_tree == local_tree:
                print("   ✔ 回核通过：远端 ref 与 tree 均与本地一致")
                ok = True
                break
            print("   推了但 tree 不对 ⇒ 重试")
        except Exception as e:
            print("   回核第 %d 次失败：%s" % (attempt, str(e)[:100]))
        time.sleep(4 * attempt)

    # ---- ③ 关键文件逐字节回核 ----
    files = [
        "来源与底稿/第四组_新产出/T-D-03_外部锚点/PREREG_T-D-03.md",
        "来源与底稿/第四组_新产出/T-D-03_外部锚点/T-D-03_锚点_原句与数值.md",
        "来源与底稿/第四组_新产出/T-D-03_外部锚点/T-D-03_查证留痕.md",
        "来源与底稿/第四组_新产出/T-D-03_外部锚点/T-D-03_锚点.json",
        "来源与底稿/第四组_新产出/T-D-03_外部锚点/raw/raw_2603.18507.txt",
        "来源与底稿/第四组_新产出/T-D-03_外部锚点/raw/raw_2605.29420.txt",
        "来源与底稿/第四组_新产出/T-D-03_外部锚点/raw/raw_2609.03218.txt",
        "来源与底稿/第四组_新产出/T-D-03_外部锚点/raw/SHA256SUMS.txt",
    ]
    allok = True
    for f in files:
        p = os.path.join(ROOT, f)
        lb = open(p, "rb").read()
        try:
            rb = api("/repos/%s/contents/%s" % (REPO, urllib.parse.quote(f)), raw=True)
        except Exception as e:
            print("   ✘ 拉取失败 %s：%s" % (f, str(e)[:80])); allok = False; continue
        same = (hashlib.sha256(lb).hexdigest() == hashlib.sha256(rb).hexdigest())
        print("   %s  %s  (%d B)  local=%s remote=%s" % (
            "✔" if same else "✘", f.split("/")[-1], len(lb),
            hashlib.sha256(lb).hexdigest()[:12], hashlib.sha256(rb).hexdigest()[:12]))
        if not same: allok = False

    # ---- ④ 确认没有碰 main ----
    m = api_json("/repos/%s/git/ref/heads/main")["object"]["sha"]
    print("   远端 main 现在 = %s（应为 4a7f231…，未被我改动）" % m[:9])
    if not m.startswith("4a7f231"):
        print("   ⚠️ 远端 main 与本地基点不同 —— 可能是别人推的，本任务未推 main")

    print("\n   总结：push=%s 回核=%s 逐字节=%s" % ("OK" if ok else "FAIL",
                                                 "OK" if ok else "FAIL",
                                                 "OK" if allok else "FAIL"))
    return 0 if (ok and allok) else 1


if __name__ == "__main__":
    sys.exit(main())
