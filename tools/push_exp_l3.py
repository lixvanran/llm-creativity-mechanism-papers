#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 三组 · 推送 `exp/L3-2026-10-26` 到 `lixvanran/agent-creativity-mechanism-study`
   ---------------------------------------------------------------------------
   ★ 为什么不用 `git push`：★ 本沙箱里 git 自己的 gnutls 握手会被掐
     （`gnutls_handshake() failed`），而 curl / urllib 走 HTTPS 正常
     ⇒ ★ 正解：★ dulwich（纯 Python git 实现，走 urllib）

   ★★★ 四条硬纪律（★ 全部来自既往事故，写死在脚本里）★★★
     ① 凭据**只走 kwargs**（username/password），**绝不进 URL**
        ⇒ dulwich/requests 会把带凭据的 URL 原样打印到 stdout ⇒ token 会进日志
     ② 输出流加 `[REDACTED]` 过滤兜底（任何含 token 的行一律替换）
     ③ **绝不 force push**；推前核对远端 base，推后核对远端 tree sha
     ④ **绝不碰 `main`**：本脚本只写 `refs/heads/exp/L3-2026-10-26`

   用法：
     GITHUB_TOKEN_LIXVANRAN=xxx python3 tools/push_exp_l3.py [--dry-run] [--repo DIR]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import urllib.request

REPO_SLUG = "lixvanran/llm-creativity-mechanism-papers"   # ★ 不是 agent-creativity-mechanism-study（那是外部仓）
BRANCH = "exp/L3-2026-10-26"
API = "https://api.github.com"


class _Filter(io.TextIOWrapper):
    """★ 输出流过滤：任何含 token 的行替换成 [REDACTED]（★ 凭据绝不能进会被打印的字符串）"""

    def __init__(self, buf, secret):
        super().__init__(buf, encoding="utf-8", errors="replace", line_buffering=True)
        self._secret = secret or "\x00__none__"

    def write(self, s):
        if self._secret and self._secret in s:
            s = s.replace(self._secret, "[REDACTED]")
        return super().write(s)


def token():
    for k in ("GITHUB_TOKEN_LIXVANRAN", "GITHUB_TOKEN", "GH_TOKEN"):
        v = os.environ.get(k)
        if v:
            return v
    raise SystemExit("★ 找不到 token 环境变量（GITHUB_TOKEN_LIXVANRAN）")


def api(path, raw=False, accept=None):
    tok = token()
    h = {"Authorization": "token " + tok,
         "Accept": accept or "application/vnd.github+json"}
    req = urllib.request.Request(API + path, headers=h)
    with urllib.request.urlopen(req, timeout=90) as r:
        data = r.read()
    return data if raw else json.loads(data.decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="/workspace/work/exp/L3")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    repo_dir = args.repo
    tok = token()
    sys.stdout = _Filter(sys.stdout.buffer, tok)
    sys.stderr = _Filter(sys.stderr.buffer, tok)

    from dulwich import porcelain
    from dulwich.porcelain import Error

    def sh(*a):
        return subprocess.run(["git", "-C", repo_dir] + list(a),
                              capture_output=True, text=True, timeout=180).stdout.strip()

    def git_out(d, *a):
        r = subprocess.run(["git", "-C", d] + list(a),
                           capture_output=True, text=True, timeout=180)
        return r.returncode, r.stdout.strip(), r.stderr

    # ── 本地状态 ──
    head = sh("rev-parse", "HEAD")
    branch = sh("branch", "--show-current")
    tree = sh("rev-parse", "HEAD^{tree}")
    print("★ 本地：branch=%s  HEAD=%s  tree=%s" % (branch, head[:12], tree[:12]))
    if branch != BRANCH:
        print("✘ 当前分支不是 %s（是 %s）⇒ 中止" % (BRANCH, branch))
        return 2

    # ── 远端状态（★ 推前核对 base）──
    try:
        ref = api("/repos/%s/git/ref/heads/%s" % (REPO_SLUG, BRANCH))
        remote_exists = True
        remote_sha = ref["object"]["sha"]
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print("✘ 查远端分支失败：%s" % e)
            return 1
        remote_exists, remote_sha = False, None
    main_sha = api("/repos/%s/git/ref/heads/main" % REPO_SLUG)["object"]["sha"]
    print("★ 远端 main = %s" % main_sha[:12])
    print("★ 远端 %s = %s" % (BRANCH, (remote_sha[:12] if remote_exists else "（不存在）")))

    # ★ 本地线与远端 main 的关系（★ 基点必须是 main@5678ffba）
    base = subprocess.run(["git", "-C", repo_dir, "merge-base", "--is-ancestor",
                           main_sha, head], capture_output=True)
    ancestor = base.returncode == 0
    print("★ 本地 HEAD 是远端 main 的祖先？ %s（0=是 ⇒ ★ 本地线【不含】main 的新提交）"
          % ("是" if ancestor else "否"))

    if args.dry_run:
        print("★ --dry-run：不推")
        return 0

    # ── ★ 双父 merge commit（★ 历史不同源：远端 main 与本地线共同祖先 = 0）──
        # ★★★ 用原生 git 造 commit（★ dulwich 的 Commit 对象缺 committer_time 字段，坑）
        import time as _t
        tree_sha = sh("rev-parse", "HEAD^{tree}")
        msg = ("[三组] exp/L3-2026-10-26 新分支\n\n"
               "基点 = main@5678ffba；双父合并 commit：两条历史都留在仓里。\n")
        mp = os.path.join(repo_dir, ".git", "merge_msg_tmp")
        with open(mp, "w", encoding="utf-8") as f:
            f.write(msg)
        rc2, new_sha, err = git_out(repo_dir, "commit-tree", tree_sha,
                                    "-p", main_sha, "-p", head, "-F", mp)
        os.remove(mp)
        if rc2 != 0:
            print("✘ commit-tree 失败：%s" % err)
            return 1
        git_out(repo_dir, "update-ref", "refs/heads/" + BRANCH, new_sha)
        head = new_sha
        tree = tree_sha
        print("★ 双父 commit = %s" % head[:12])
        rc3, pshow, _ = git_out(repo_dir, "log", "-1", "--format=%H %P", head)
        print("   %s" % pshow)

        head = c.id.decode()
        tree = rp.object_store[c.tree].id.decode() if False else c.tree.decode()
        print("★ 双父 commit = %s  parents=%s" % (head[:12], [p[:8] for p in c.parents]))
        print("   tree = %s" % tree[:12])
        need_merge = False

    # ── 推（★ 凭据走 kwargs，不进 URL）──
    url = "https://github.com/%s.git" % REPO_SLUG
    refspec = "refs/heads/%s:refs/heads/%s" % (BRANCH, BRANCH)
    print("★ 开始推送 …（refspec=%s）" % refspec)
    try:
        res = porcelain.push(repo_dir, url, [refspec],
                             username="x-access-token", password=tok)
    except Error as e:
        print("✘ 推送失败：%r" % e)
        return 1
    print("★ push 返回：%r" % (res,))
    if getattr(res, "err", None):
        print("✘ push 有错误：%s" % res.err)
        return 1

    # ── 推后核对（★ 判据：远端 tree sha == 本地 tree sha ⇒ 内容逐字节相同）──
    ref2 = api("/repos/%s/git/ref/heads/%s" % (REPO_SLUG, BRANCH))
    new_sha = ref2["object"]["sha"]
    remote_tree = api("/repos/%s/git/commits/%s" % (REPO_SLUG, new_sha))["tree"]["sha"]
    main2 = api("/repos/%s/git/ref/heads/main" % REPO_SLUG)["object"]["sha"]
    print("\n" + "=" * 84)
    print("推后核对")
    print("  远端分支 HEAD      = %s" % new_sha[:12])
    print("  本地 HEAD           = %s" % head[:12])
    print("  远端 tree sha       = %s" % remote_tree[:12])
    print("  本地 tree sha       = %s" % tree[:12])
    print("  远端 main（推后）   = %s" % main2[:12])
    ok_tree = (remote_tree == tree)
    ok_main = (main2 == main_sha)
    ok_head = (new_sha == head)
    print("  ⇒ tree sha 相同（内容逐字节相同）：%s" % ("✔" if ok_tree else "✘"))
    print("  ⇒ 远端 HEAD == 本地 HEAD：%s" % ("✔" if ok_head else "✘"))
    print("  ⇒ main 未被改动：%s" % ("✔" if ok_main else "✘"))
    print("=" * 84)
    if not (ok_tree and ok_main):
        print("★ 核对未全过 ⇒ 判失败")
        return 1
    print("★ 推送完成并核对通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
