#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 推送到 GitHub（★ 2026-10-26）

★★★ 为什么不用 `git push`：★★
  ★ 本沙箱里 **git 自己的 gnutls 握手会被掐**（★ `gnutls_handshake() failed`）⇒ ★ 而 curl 走 HTTPS 正常
  ⇒ ★ 正解：★ 用 **dulwich**（★ 纯 Python 的 git 实现、★ 走 urllib 而非 gnutls）★ 做 fetch/push
  ⇒ ★ 装：★ `python3 -m venv .venv-git && .venv-git/bin/pip install dulwich`

★★★ 本脚本干三件事：★★
  1. ★ **双父 merge commit**：★ 远端 main 与本地改动线【历史不同源】（★ 共同祖先 0）
     ⇒ ★ 直推会断掉远端那条线 ⇒ ★ 造一个父为「远端 main + 本地 tip」的 commit、★ 内容取本地
     ⇒ ★ **两条历史都留在仓里、★ 且 main 的内容 = 当前状态**
  2. ★ push main ＋ 改动分支
  3. ★ **回核**：★ 远端取回关键文件、★ 与本地逐字节比对（★ 推完不核等于没推）

★★★ 用法：★★
  GITHUB_TOKEN_LIXVANRAN=xxx /workspace/.venv-git/bin/python tools/push_to_github.py
  ★ 加 `--dry-run` 只造 commit 不推。
"""
import sys, os, time, json, base64, hashlib, argparse, subprocess, urllib.parse

class _Redact:
    """★ 输出流过滤：★ 凭据绝不能出现在任何会被打印/回显的字符串里。★
    （★ dulwich 会把 URL 原样打到 stdout ⇒ URL 里就不能有凭据；★
      ★ 这里再加一道兜底：★ 万一哪里又拼进去了、★ 打印前先脱敏。★）"""

    def __init__(self, stream, secret):
        self._s = stream
        self._buf = getattr(stream, "buffer", None)
        self._secret = (secret or b"")
        if isinstance(self._secret, str):
            self._secret = self._secret.encode()

    def _fix(self, data):
        if not self._secret:
            return data
        if isinstance(data, bytes):
            return data.replace(self._secret, b"[REDACTED]")
        return data.replace(self._secret.decode(), "[REDACTED]")

    def write(self, data):
        if isinstance(data, bytes):
            tgt = self._buf if self._buf is not None else self._s
            return tgt.write(self._fix(data))
        return self._s.write(self._fix(data))

    def flush(self):
        try:
            self._s.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._s, name)


sys.dont_write_bytecode = True

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "lixvanran/llm-creativity-mechanism-papers"
BRANCH = "feature/revise-per-external-review-2026-10-24"
# ★ 回核要逐字节比的文件（★ 覆盖三件：叙述层 / 过程数据 / 索引）
VERIFY = [
    "README.md", "DATASETS.md", "PROVENANCE.md",
    "data/negative_results.jsonl", "data/open_tasks.jsonl", "data/readings.jsonl",
    "papers/01_L1_PrematureConvergence_交差稿.md",
]


def api(path):
    import urllib.request
    tok = os.environ.get("GITHUB_TOKEN_LIXVANRAN", "")
    req = urllib.request.Request("https://api.github.com" + path,
                                 headers={"Authorization": "token " + tok,
                                          "Accept": "application/vnd.github+json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read().decode())


def api_bytes(path, raw=False):
    import urllib.request
    tok = os.environ.get("GITHUB_TOKEN_LIXVANRAN", "")
    h = {"Authorization": "token " + tok}
    if raw:
        h["Accept"] = "application/vnd.github.raw"
    req = urllib.request.Request("https://api.github.com" + path, headers=h)
    return urllib.request.urlopen(req, timeout=180).read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not os.environ.get("GITHUB_TOKEN_LIXVANRAN"):
        print("⛔ 没有 GITHUB_TOKEN_LIXVANRAN")
        return 1

    _TOK = os.environ.get("GITHUB_TOKEN_LIXVANRAN", "")
    if _TOK:
        sys.stdout = _Redact(sys.stdout, _TOK)
        sys.stderr = _Redact(sys.stderr, _TOK)
    from dulwich import porcelain
    from dulwich.repo import Repo
    from dulwich.objects import Commit

    # ★ 凭据【绝不进 URL】：★ dulwich 会把 URL 原样打印 ⇒ URL 必须干净 ★
    url = "https://github.com/%s.git" % REPO
    cred = {"username": "x", "password": os.environ["GITHUB_TOKEN_LIXVANRAN"]}

    # ① fetch 远端（★ 网络会抖 ⇒ 必须重试；★ dulwich 自己不重试）
    res = None
    for attempt in range(1, 6):
        try:
            res = porcelain.fetch(ROOT, url, quiet=True, **cred)
            break
        except Exception as e:
            print("   fetch 第 %d 次失败：%s" % (attempt, str(e)[:80]))
            time.sleep(4 * attempt)
    if res is None:
        print("   fetch 连续失败 ⇒ 不推（★ 宁可不推、★ 不要推一半）")
        return 1
    remote_main = res.refs[b"refs/heads/main"]
    r = Repo(ROOT)
    refs = r.get_refs()
    mine = refs.get(("refs/heads/" + BRANCH).encode())
    if mine is None:
        print("⛔ 本地没有分支 %s" % BRANCH)
        return 1
    print("   远端 main: %s   本地 tip: %s" % (remote_main.decode()[:9], mine.decode()[:9]))

    # ② 双父 merge commit
    c = Commit()
    c.tree = r[mine].tree
    c.parents = [remote_main, mine]
    c.author = c.committer = b"Mavis <mavis@local>"
    c.commit_time = c.author_time = int(time.time())
    c.commit_timezone = c.author_timezone = 0
    c.encoding = b"UTF-8"
    c.message = ("merge: 过程数据定位 —— 远端线与本地改稿线合流\n\n"
                 "父 1 = 远端 main；父 2 = 本地改稿线。内容取本地侧。\n").encode("utf-8")
    r.object_store.add_object(c)
    new = c.id
    r.refs[b"refs/heads/main"] = new
    r.close()
    print("   merge commit: %s  父: %s" % (new.decode()[:9], [p.decode()[:9] for p in c.parents]))
    if a.dry_run:
        print("   （dry-run：未推）")
        return 0

    # ③ push（★ 沙箱里连接会被掐 ⇒ 必重试；★ 且【判据用 tree sha】⇒ 内容相同 <=> tree 相同）
    import time as _t
    ok = False
    for attempt in range(1, 5):
        try:
            porcelain.push(ROOT, url, [b"refs/heads/main", ("refs/heads/" + BRANCH).encode()],
                                outstream=_Redact(sys.stdout.buffer, _TOK),
                                errstream=_Redact(sys.stderr.buffer, _TOK),
                                **cred)
            # ★ 推完立刻核远端 main 的 tree
            live = api("/repos/%s/git/ref/heads/main" % REPO)["object"]["sha"]
            live_tree = api("/repos/%s/git/commits/%s" % (REPO, live))["tree"]["sha"]
            if live_tree == c.tree.decode():
                print("   push 完成（第 %d 次）｜ 远端 main tree = 本地 tree" % attempt)
                ok = True
                break
            print("   推了但 tree 不对 ⇒ 重试")
        except Exception as e:
            print("   push 第 %d 次失败：%s" % (attempt, str(e)[:90]))
        _t.sleep(5 * attempt)
    if not ok:
        print("   push 未能确认 ⇒ 查远端实际状态再决定")
        return 1

    # ④ 回核（★ 推完不核等于没推）
    # ★ ★ 权威判据 = 【远端 main 的 tree sha】：tree 相同 ⇒ 内容必然逐字节相同；★
    # ★   一次 API 调用核全局、★ 且不会被网络抖动误报。★★
    # ★ ★ 逐文件核对只作补充、★ 且【取不回来 ≠ 内容不一致】★ ——★
    # ★   混为一谈会假红、★ 而【假红会让读者以为「没推上去」】★ ⇒ 交接文档里写的就是这条命令。★
    bad = 0
    unchecked = []
    for f in VERIFY:
        try:
            local = open(os.path.join(ROOT, f), "rb").read()
        except FileNotFoundError:
            continue
        # ★ contents API 只内联 1MB；★ 大的走 blob API
        remote = None
        for attempt in range(3):
            try:
                # ★ 中文路径必须 URL 编码（★ 否则 404/取不回来 ⇒ 假「未核对」★）
                meta = api("/repos/%s/contents/%s?ref=main"
                           % (REPO, urllib.parse.quote(f)))
                remote = api_bytes("/repos/%s/git/blobs/%s" % (REPO, meta["sha"]), raw=True)
                break
            except Exception:
                time.sleep(3 * (attempt + 1))
        if remote is None:
            unchecked.append(f)
            print("   %-46s 取不回来（★ 未核对、★ 不计为不一致 ★）" % f)
            continue
        same = hashlib.sha256(remote).hexdigest() == hashlib.sha256(local).hexdigest()
        if not same:
            bad += 1
        print("   %-46s %s" % (f, "逐字节一致" if same else "不一致"))
    live_tree = None
    try:
        live = api("/repos/%s/git/ref/heads/main" % REPO)["object"]["sha"]
        live_tree = api("/repos/%s/git/commits/%s" % (REPO, live))["tree"]["sha"]
    except Exception:
        pass
    tree_ok = (live_tree is not None and live_tree == c.tree.decode())
    n_same = len(VERIFY) - bad - len(unchecked)
    print("   回核：逐字节 %d/%d 一致、%d 不一致、%d 未核对 ｜ 远端 tree %s"
          % (n_same, len(VERIFY), bad, len(unchecked),
             ("== 本地 tree ✔" if tree_ok else "≠ 本地 tree ✘")))
    if unchecked:
        print("   ★ 未核对区（★ 取不回来 ≠ 不一致、★ 但 ≠ 已核 ★）：%s" % ", ".join(unchecked))
    return 0 if (tree_ok and bad == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
