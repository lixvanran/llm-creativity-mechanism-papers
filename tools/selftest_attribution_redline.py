#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ S9/S10 判据的负向测试（★ 记忆铁律：★ 判据必须能红，且红在预期处 + 负向测试必配）
★
★ ★★ 踩过的坑（★ 记下来，因为它是"负向测试自己会假阴性"的同族）：
★   第一版负向测试把仓库复制到临时目录做注入 ⇒ ★ **复制时漏了 `.git`**
★   ⇒ ★ 验收器拿不到基线（`git show 8649661:…` 失败）⇒ ★ **所有用例都判红**
★   ⇒ ★ **"绿用例也红"看起来像"判据太严"，★ 实际是"测试自己坏了"**
★   ⇒ ★ 落法：★ ① 判据逻辑抽成可单测函数（`attr_violations` / `claim_violations`）★ 直接单测
★            ② 端到端用例**必须带上 `.git`**（★ 否则基线拿不到）
"""
import sys, shutil, subprocess, tempfile, pathlib, re
sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from check_cluster_consistency import attr_violations, claim_violations  # noqa: E402

L1 = "papers/01_L1_PrematureConvergence_交差稿.md"

# (名字, 注入行, 期望 S9 判红?, 期望 S10 判红?)
CASES = [
    ("真违规：标题式无条件归因",
     "# 搜索空间过早闭合：根因在 Transformer 的注意力机制", True, False),
    ("真违规：标成「本文的主张」",
     "**本文的主张**：★ 搜索空间过早闭合的根源在 Transformer 的注意力机制。", True, True),
    ("真违规：章标题无条件归因",
     "## 2 ★ 根因论证：为什么根源在 Transformer 的注意力机制", True, False),
    ("真违规：结论条无条件归因",
     "★ 我们论证了根因在 Transformer 的注意力机制", True, False),
    ("★ 元声明：禁令条文（不该红）",
     "★ **不许**写成「因为注意力…」⇒ ★ 唯一允许的写法是「与注意力机制相容，但本文未检验该假设」", False, False),
    ("★ 限定句（不该红）",
     "★ **本文主张**过早闭合的最可能机制是注意力层的四条链 ★ **本批未检验该假设**", False, False),
    ("★ 被否证的对象（不该红）",
     "★ 不可把「注意力机制已被排除」读成本文结论", False, False),
    ("★ 关键词行（不该红）",
     "**关键词**：搜索空间塌缩 · 过早闭合 · 根因论证 · 注意力机制 · 宽度指数", False, False),
    ("★ 标题行带假说（不该红）",
     "## 2 ★ 归因论证：四条机制假说与它们各自的可失败预测", False, False),
]


def main():
    ok = True
    print("── ① 单元级：判据内核直接注入 ──")
    for name, inject, want9, want10 in CASES:
        v9, _ = attr_violations(inject)
        v10, _ = claim_violations(inject)
        got9, got10 = bool(v9), bool(v10)
        good = (got9 == want9 and got10 == want10)
        ok = ok and good
        print(f"  {'✔' if good else '✘'} {name}"
              f"  ⇒ S9 期望{'红' if want9 else '绿'}/实得{'红' if got9 else '绿'}"
              f"，S10 期望{'红' if want10 else '绿'}/实得{'红' if got10 else '绿'}"
              + ("" if good else f"  ★ 不符合预期 ⇒ {inject[:60]}"))

    print("── ② 端到端：整仓副本 + 注入（★ 必须带 .git，★ 否则基线拿不到）──")
    for name, inject, want9, want10 in CASES:
        if not want9 and not want10:
            continue
        with tempfile.TemporaryDirectory() as td:
            wd = pathlib.Path(td) / "repo"
            shutil.copytree(ROOT, wd, ignore=shutil.ignore_patterns("*.docx", "__pycache__"))
            p = wd / L1
            lines = p.read_text(encoding="utf-8").split("\n")
            lines.insert(5, inject)
            p.write_text("\n".join(lines), encoding="utf-8")
            r = subprocess.run([sys.executable, str(wd / "tools/check_cluster_consistency.py"),
                                "--head", "8649661"], cwd=wd, capture_output=True, text=True)
            out = r.stdout + r.stderr
            hit = re.search(r"✖ \[S(?:9|10)\][^\n]*", out)
            base_err = "基线" in out and "不存在" in out
            good = (r.returncode != 0 and hit is not None and not base_err)
            ok = ok and good
            print(f"  {'✔' if good else '✘'} {name}  ⇒ 端到端 EXIT={r.returncode}"
                  f"  {hit.group(0)[:96] if hit else '★ 未判红'}"
                  + ("  ★ 基线拿不到（★ 测试自身坏了）" if base_err else ""))

    print("─" * 68)
    print("★ 负向测试：" + ("★ 全部符合预期 ✔" if ok else "★ 有不符合预期的 ✘"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
