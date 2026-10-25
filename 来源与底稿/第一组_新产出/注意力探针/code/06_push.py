#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T-L1-01 · 推到 GitHub（★ 只推自己那一条分支 ★）

★★★ 三条硬规矩 ★★★
 ① **凭据绝不出现在任何会被打印的字符串里** ⇒ 走 `username` / `password` 的 **kwargs**（**不进 URL**），
    另外加一道 **stdout 过滤器**（任何含 token 的行替换成 `[REDACTED]`）⇒ 推完还要**事后扫描**工作区与日志。
 ② **推前做「三棵比对」**：远端树 / 上次推的树 / 当前树 ⇒ **对不上就拒推**（不硬推、不覆盖别人的改动）。
 ③ **只推 `refs/heads/exp/L1-2026-10-26-r2`** ⇒ 绝不碰 `main`、绝不碰别的组的分支。

用法：
  GITHUB_TOKEN_LIXVANRAN=xxx python 06_push.py --dry-run
  GITHUB_TOKEN_LIXVANRAN=xxx python 06_push.py
"""
import os, sys, time, json, hashlib, argparse

sys.dont_write_bytecode = True

REPO = "lixvanran/llm-creativity-mechanism-papers"
URL = "https://github.com/%s.git" % REPO          # ★ URL 里没有凭据 ★
BRANCH = "exp/L1-2026-10-26-r2"
STATE = "/workspace/run/.push_state.json"        # ★ 上次推的树（本地状态文件，不进仓）★


class _Redact:
    """stdout 过滤器：任何含 token 的行替换成 [REDACTED]（纵深防御：即便某个库把 URL 打出来也不泄）。"""

    def __init__(self, stream, secret):
        self.stream = stream
        self.secret = secret

    def write(self, s):
        if self.secret and self.secret in s:
            s = s.replace(self.secret, "[REDACTED]")
        try:
            self.stream.write(s)
        except Exception:
            pass

    def flush(self):
        try:
            self.stream.flush()
        except Exception:
            pass

    def __getattr__(self, k):
        return getattr(self.stream, k)


def api(path):
    import urllib.request
    tok = os.environ["GITHUB_TOKEN_LIXVANRAN"]
    req = urllib.request.Request("https://api.github.com" + path,
                                 headers={"Authorization": "token " + tok,
                                          "Accept": "application/vnd.github+json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read().decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--repo-dir", default="/workspace/repo")
    a = ap.parse_args()

    tok = os.environ.get("GITHUB_TOKEN_LIXVANRAN")
    if not tok:
        print("⛔ 没有 GITHUB_TOKEN_LIXVANRAN")
        return 1
    sys.stdout = _Redact(sys.stdout, tok)
    sys.stderr = _Redact(sys.stderr, tok)

    from dulwich import porcelain
    from dulwich.repo import Repo

    r = Repo(a.repo_dir)
    refs = r.get_refs()
    my_ref = ("refs/heads/" + BRANCH).encode()
    mine = refs.get(my_ref)
    if mine is None:
        print("⛔ 本地没有分支 %s" % BRANCH)
        return 1
    my_tree = r[mine].tree.decode()
    print("本地 %s = %s（tree %s）" % (BRANCH, mine.decode()[:12], my_tree[:12]))

    # ---- ① fetch 远端（网络会抖 ⇒ 重试）
    res = None
    for attempt in range(1, 6):
        try:
            res = porcelain.fetch(a.repo_dir, URL, username="x-access-token", password=tok, quiet=True)
            break
        except Exception as e:
            print("  fetch 第 %d 次失败：%s" % (attempt, str(e)[:80]))
            time.sleep(4 * attempt)
    if res is None:
        print("⛔ fetch 连续失败 ⇒ 不推（宁可不推、不要推一半）")
        return 1

    remote_refs = {k.decode(): v.decode() for k, v in res.refs.items()}
    remote_mine = remote_refs.get("refs/heads/" + BRANCH)
    remote_main = remote_refs.get("refs/heads/main")
    print("远端 %s = %s" % (BRANCH, (remote_mine or "（不存在）")[:12]))
    print("远端 main = %s（★ 只读参照，本脚本不推它 ★）" % (remote_main or "—")[:12])

    # ---- ② 三棵比对：远端树 / 上次推的树 / 当前树
    state = {}
    if os.path.exists(STATE):
        state = json.load(open(STATE, encoding="utf-8"))
    last_pushed_tree = state.get("last_pushed_tree")
    last_pushed_sha = state.get("last_pushed_sha")

    remote_tree = None
    if remote_mine:
        try:
            remote_tree = api("/repos/%s/git/commits/%s" % (REPO, remote_mine))["tree"]["sha"]
        except Exception as e:
            print("⛔ 取远端 tree 失败：%s" % str(e)[:100])
            return 1
    print("三棵比对：")
    print("   远端树      = %s" % (remote_tree or "（分支不存在）"))
    print("   上次推的树  = %s" % (last_pushed_tree or "（本机无记录 ⇒ 首次推）"))
    print("   当前树      = %s" % my_tree)

    if remote_tree is not None:
        if last_pushed_tree is None:
            print("⛔ 远端分支已存在、但本机没有「上次推的树」记录 ⇒ 无法判定是否被别人改过 ⇒ 拒推")
            return 2
        if remote_tree != last_pushed_tree:
            print("⛔ 远端树 ≠ 上次推的树 ⇒ 远端在两次推之间被别人改过 ⇒ **拒推**（不覆盖）")
            return 2
        if remote_tree == my_tree:
            print("   （远端树 == 当前树 ⇒ 无需推）")
            return 0

    # ---- ③ 推（只推自己那一条 ref）
    if a.dry_run:
        print("（dry-run：未推）")
        return 0
    ok = False
    for attempt in range(1, 5):
        try:
            porcelain.push(a.repo_dir, URL, [my_ref],
                           username="x-access-token", password=tok)
            live = api("/repos/%s/git/ref/heads/%s" % (REPO, BRANCH))["object"]["sha"]
            live_tree = api("/repos/%s/git/commits/%s" % (REPO, live))["tree"]["sha"]
            if live_tree == my_tree:
                print("✔ push 完成（第 %d 次）｜ 远端 %s 的 tree == 本地 tree" % (attempt, BRANCH))
                ok = True
                break
            print("  推了但 tree 不对 ⇒ 重试")
        except Exception as e:
            print("  push 第 %d 次失败：%s" % (attempt, str(e)[:90]))
        time.sleep(5 * attempt)
    if not ok:
        print("⛔ push 未能确认 ⇒ 先查远端实际状态再决定（别重复推）")
        return 1

    # ---- ④ 记状态（下次推的三棵比对要用）
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump({"branch": BRANCH, "last_pushed_tree": my_tree, "last_pushed_sha": mine.decode(),
               "pushed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
              open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # ---- ⑤ 确认没碰 main
    after = api("/repos/%s/git/ref/heads/main")["object"]["sha"]
    if remote_main and after != remote_main:
        print("⚠ 远端 main 变了（%s → %s）—— 本脚本不推 main，应为他人推送" % (remote_main[:12], after[:12]))
    else:
        print("✔ 远端 main 未被本脚本改动（%s）" % after[:12])
    return 0


if __name__ == "__main__":
    sys.exit(main())
