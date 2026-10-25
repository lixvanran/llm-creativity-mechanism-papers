#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T-A-03 · 支数口径回源核验（零 API，可复跑）

★ 目的：核实「型号池静默下架 ⇒ 5 支臂实测 4 支」这条根因的【一手代码证据】，
  ★ 并把结论钉在【对方 HEAD 的 sha】上（不带 sha 的核对结论一律降级为「待核」）。

★ 取数方式：GitHub contents API（凭据走 header，不进 URL）⇒ 拉
  ★   lixvanran/agent-creativity-mechanism-study @ main
  ★     creativity_lab/client.py       （MODELS 型号池）
  ★     creativity_lab/arms/dual.py     （N_BRANCH / _branch_specs / 空串过滤）
  ★ 不读任何 runlog / 不做统计 —— 本脚本只核「机制」。

★ 零 API 依赖：只用 GitHub 读接口；不调用任何模型 API。

用法：
    GITHUB_TOKEN_LIXVANRAN=xxx python3 verify_branch_caliber.py
    # 输出：out_verify_branch_caliber.json（同目录）
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

REPO = "lixvanran/agent-creativity-mechanism-study"
BRANCH = "main"
PATHS = ["creativity_lab/client.py", "creativity_lab/arms/dual.py"]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "out_verify_branch_caliber.json")


def api_raw(path: str) -> tuple[str, str]:
    """返回 (内容, 该 path 的 blob sha)。凭据走 header。"""
    tok = os.environ.get("GITHUB_TOKEN_LIXVANRAN", "")
    if not tok:
        raise SystemExit("⛔ 没有 GITHUB_TOKEN_LIXVANRAN")
    url = ("https://api.github.com/repos/%s/contents/%s?ref=%s"
           % (REPO, path, BRANCH))
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + tok,
        "Accept": "application/vnd.github+json",
    })
    meta = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
    if "content" not in meta:
        raise SystemExit("⛔ %s 取不到：%s" % (path, meta))
    import base64
    body = base64.b64decode(meta["content"]).decode("utf-8", "replace")
    return body, meta["sha"]


def api_ref_sha() -> str:
    tok = os.environ.get("GITHUB_TOKEN_LIXVANRAN", "")
    req = urllib.request.Request(
        "https://api.github.com/repos/%s/git/ref/heads/%s" % (REPO, BRANCH),
        headers={"Authorization": "Bearer " + tok,
                 "Accept": "application/vnd.github+json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read()
                      .decode())["object"]["sha"]


def main() -> int:
    ref_sha = api_ref_sha()
    files = {}
    for p in PATHS:
        body, sha = api_raw(p)
        files[p] = {"blob_sha": sha, "lines": body.split("\n")}

    # ---- 1. 型号池 ----
    cl = files["creativity_lab/client.py"]["lines"]
    models, mline = [], None
    for i, ln in enumerate(cl, 1):
        if re.match(r"\s*MODELS\s*=\s*\[", ln):
            mline = i
            rest = ln.split("[", 1)[1]
        else:
            rest = ln
        if mline and i >= mline:
            for tok in re.findall(r'"([^"]+)"', rest):
                models.append(tok)
            if "]" in rest:
                break

    # ---- 2. 支数与取模 ----
    du = files["creativity_lab/arms/dual.py"]["lines"]
    n_branch, nb_line = None, None
    for i, ln in enumerate(du, 1):
        m = re.match(r"\s*N_BRANCH\s*=\s*(\d+)", ln)
        if m:
            n_branch, nb_line = int(m.group(1)), i
            break
    spec_line = next((i for i, ln in enumerate(du, 1)
                      if "MODELS[i % len(MODELS)]" in ln), None)
    filter_line = next((i for i, ln in enumerate(du, 1)
                        if re.search(r"return \[o for o in outs if o\]", ln)), None)

    # ---- 3. 支 i 用的型号 ----
    branch_models = [models[i % len(models)] for i in range(n_branch)] \
        if (n_branch and models) else []
    # 已被 ②组 实测为死型号的（见 02 篇附录 D.1 / 交付报告 结论 4①）
    DEAD = {"MiniMax-M2.1", "MiniMax-M2", "MiniMax-M2.1-highspeed"}

    dead_in_5 = [m for m in branch_models if m in DEAD]
    live_in_5 = [m for m in branch_models if m not in DEAD]
    # 6 支场合（若把 N_BRANCH 提到 6）
    branch_models_6 = [models[i % len(models)] for i in range(6)]
    dead_in_6 = [m for m in branch_models_6 if m in DEAD]

    res = {
        "task": "T-A-03",
        "purpose": "回源核验：型号池静默下架 ⇒ N_BRANCH=5 的 dual 臂实测支数",
        "source_repo": REPO,
        "source_branch": BRANCH,
        "source_ref_sha": ref_sha,
        "files": {p: {"blob_sha": files[p]["blob_sha"]} for p in PATHS},
        "models_pool": {"line": mline, "n": len(models), "list": models},
        "models_pool_index_map": {str(i): m for i, m in enumerate(models)},
        "n_branch": {"value": n_branch, "line": nb_line},
        "branch_specs_line": spec_line,
        "empty_filter_line": filter_line,
        "branch_i_to_model": branch_models,
        "dead_models_declared": sorted(DEAD),
        "dead_models_in_5_branch_arms": dead_in_5,
        "live_branch_count_5_arm": len(live_in_5),
        "live_branch_models_5_arm": live_in_5,
        "six_branch_check": {
            "branch_i_to_model": branch_models_6,
            "dead_models_in_6_branch_arms": dead_in_6,
            "note": "凡声称用满 6 支的场合，必须先核支数是否真为 6",
        },
        "verdict": {
            "mechanism_confirmed": bool(dead_in_5) and filter_line is not None,
            "statement": ("N_BRANCH=5，第 5 支（i=4）取到 MODELS[4]=%s，"
                          "该型号已下架返空，被 arms/dual.py:%s 的 `if o` 过滤 ⇒ "
                          "5 支静默变 %d 支；表上看不出来。"
                          % (branch_models[4] if branch_models else "?",
                             filter_line, len(live_in_5))),
        },
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
