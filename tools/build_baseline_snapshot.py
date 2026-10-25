#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 建【基线快照】目录：★ 交付包里必须带它
★★ 为什么（★ 本轮在交付态真踩到）：
★   验收器 S1「数字零改动」与 S2「标记不减」都是【逐篇 vs 基线】的判据
★   ⇒ ★ 基线来自 `git show 8649661:<path>` ⇒ ★ **交付包里有 .git 吗？没有**
★   ⇒ ★ ⇒ **收件人拿到包，S1 这条最重要的判据直接跑不起来**（★ 本轮实测：交付态报"基线不存在"）
★   ⇒ ★ **⇒ 落法：★ 把改稿前的那些文件原样收进包内 `baseline/`，★ 并给验收器加 `--baseline-dir`**
★   ⇒ ★ **这样"数字一个都没动"在交付态可核，★ 而不只是在仓里可核**
"""
import sys, subprocess, pathlib, hashlib, json
sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parent.parent
# ★ 基线常量从【单一事实来源】读（★ tools/baseline.json）
BASE_COMMIT = json.loads((ROOT / "tools/baseline.json").read_text(encoding="utf-8"))["baseline_commit"]
OUT = ROOT / "baseline"

# ★ 需要基线的文件（★ 与验收器里用 git_show 的两处一致：★ 四篇 + 簇级载体）
TARGETS = [
    "papers/01_L1_PrematureConvergence_交差稿.md",
    "papers/02_A_SelectionIsNotCreation_稿.md",
    "papers/06_L3_层3自修改_交差稿.md",
    "papers/04_D_StateMachineIsNotYetAPrompt_交差稿.md",
    "papers/03_C_SixWaysToLookDone_稿.md",
    "papers/00_论文簇总纲_交差版.md",
    "papers/09_四篇初稿_合订本_2026-10-24.md",
    "papers/07_待填审计_判据定版状态.md",
    "support/00_论文簇总纲_交差版.md",
    "support/07_待填审计_判据定版状态.md",
    "support/交差说明_四篇_2026-10-24.md",
]


def main():
    OUT.mkdir(exist_ok=True)
    (OUT / "README.md").write_text(
        "# baseline · 本轮改稿前的快照\n\n"
        f"★ **基线 commit = `{BASE_COMMIT}`**（★ 本轮改稿开始前的仓内状态）\n"
        "★ **这些文件是原样拷贝，★ 一个字未改**（★ 用来给 `tools/check_cluster_consistency.py` "
        "提供**不依赖 git** 的基线）\n\n"
        "★ **为什么需要**：★ 验收器的 **S1「数字零改动」** 与 **S2「标记不减」** 都是"
        "「逐篇 vs 基线」的判据 ⇒ ★ **基线来自 `git show`，★ 而交付包里没有 `.git`** ⇒ ★ "
        "**收件人拿到包，S1 这条最重的判据直接跑不起来** ⇒ ★ **有了这个目录，"
        "`--baseline-dir baseline` 就能在交付态核**。\n\n"
        "★ **核验**：\n```bash\n"
        "python3 tools/check_cluster_consistency.py --baseline-dir baseline\n"
        "```\n\n"
        "★ ★ **对照表见 `baseline/BASELINE_SHA256.txt`**（★ 每个文件一个 sha256）\n",
        encoding="utf-8")
    rows = []
    n = 0
    for rel in TARGETS:
        r = subprocess.run(["git", "show", f"{BASE_COMMIT}:{rel}"], cwd=ROOT,
                           capture_output=True)
        if r.returncode != 0:
            print(f"⚠ 基线无此文件：{rel}")
            continue
        dst = OUT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(r.stdout)
        h = hashlib.sha256(r.stdout).hexdigest()
        rows.append(f"{h}  {rel}")
        n += 1
    (OUT / "BASELINE_SHA256.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"★ 基线快照已建：{n} 个文件（★ 出处 commit `{BASE_COMMIT}`）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
