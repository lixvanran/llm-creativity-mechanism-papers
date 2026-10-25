#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T-L1-01 · 用 dulwich 克隆远端仓到本地工作副本（★ 凭据走 kwargs、★ 绝不进 URL ★）

★ 为什么不用 `git clone`：本沙箱里 git 自己的 gnutls 握手会被掐（`gnutls_handshake() failed`），
  而 curl / urllib 走 HTTPS 正常 ⇒ 用 dulwich（纯 Python、走 urllib）★
★ 凭据：`username` / `password` 走 kwargs ⇒ **URL 里没有 token** ⇒ dulwich 打印 URL 时不会泄 token ★
"""
import os, sys, time, json

sys.dont_write_bytecode = True

REPO = "lixvanran/llm-creativity-mechanism-papers"
URL = "https://github.com/%s.git" % REPO
DEST = "/workspace/repo"


def main():
    tok = os.environ.get("GITHUB_TOKEN_LIXVANRAN")
    if not tok:
        print("⛔ 没有 GITHUB_TOKEN_LIXVANRAN")
        return 1
    from dulwich import porcelain

    if os.path.isdir(os.path.join(DEST, ".git")) or os.path.isdir(os.path.join(DEST, "objects")):
        print("工作副本已存在 ⇒ 改为 fetch")
        rc = fetch(DEST, tok)
    else:
        os.makedirs(DEST, exist_ok=True)
        rc = clone(DEST, tok)
    return rc


def clone(dest, tok):
    from dulwich import porcelain
    for attempt in range(1, 6):
        try:
            r = porcelain.clone(URL, dest, username="x-access-token", password=tok, checkout=True)
            print("✔ clone 成功（仓库对象已在本地）")
            return 0
        except Exception as e:
            print("  clone 第 %d 次失败：%s" % (attempt, str(e)[:120]))
            time.sleep(4 * attempt)
    return 1


def fetch(dest, tok):
    from dulwich import porcelain
    for attempt in range(1, 6):
        try:
            res = porcelain.fetch(dest, URL, username="x-access-token", password=tok, quiet=True)
            refs = {k.decode(): v.decode() for k, v in res.refs.items()}
            print("✔ fetch 成功，远端 refs：")
            for k in sorted(refs):
                print("   %-44s %s" % (k, refs[k][:12]))
            return 0
        except Exception as e:
            print("  fetch 第 %d 次失败：%s" % (attempt, str(e)[:120]))
            time.sleep(4 * attempt)
    return 1


if __name__ == "__main__":
    sys.exit(main())
