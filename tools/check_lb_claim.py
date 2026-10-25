#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 【散文层】承重子层口径判据（★ 2026-10-25 · 依审稿人 v3 的 NEW-1 增）

★★★ 为什么需要这条（★ v3 抓到的）：★★
  ★ ②篇正文已经改成「承重子层不可分辨（方向随口径翻转）」✔
  ★ ★ **但** `papers/净增益双边重算_可粘贴段落_2026-10-25.md`（★ 它在交付包里、★ 入口 md 把它当交付物列出）
    ★ 还在讲【旧口径的承重故事】：★ 「口径 B 净 +14 → +14（不变）」「确实净增（+6/+7）」
    ⇒ ★ **★ 第三方读这份「完整复算报告」⇒ 会得出与正文【相反】的结论 ⇒ ★ 这是最坏的一种错**
  ★ ⇒ ★ 根因：**「+14」这个数在【断言层】与【承重子层】两个口径下含义不同（★ 14 是断言层总净）**
    ⇒ ★ 散文里没有限定词 ⇒ 读者按最近的上下文（承重）理解 ⇒ ★ 就读错了

★★ 判据（★ 逐句、★ 排除元声明）：★★
  ★ 凡一个【句/表格格】里同时出现「承重」与「+14」（或「14（不变）」这类），
    ⇒ ★ 该处必须同时出现【断言层】这个限定词 ⇒ ★ 否则判红
  ★ ★ 排除：★ 「不可写成…」「不得写成…」这类【元声明】上下文（同族教训：★ 禁用串判据默认假红）

★ **负向测试**：★ 造一句「承重子层净 +14（不变）」⇒ 必须红。
"""
import sys, re, pathlib
sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGETS = [
    ROOT / "papers/净增益双边重算_可粘贴段落_2026-10-25.md",
    ROOT / "papers/02_A_SelectionIsNotCreation_稿.md",
]
# ★ 元声明上下文（★ 同族教训：★ 「不可写成 X」不是 X）
META = re.compile(r"不可写成|不得写成|不能写成|不许|禁止|禁写|应写成|改成|勿写|避免|不作|不写|不是结论|元声明")
# ★ 「承重」与「+14」同处
CLAIM = re.compile(r"承重")
NUM14 = re.compile(r"\+14|14（不变）|14 → \+14|\+14 → \+14")
LIMIT = re.compile(r"断言层")

def sentences(md):
    """★ 逐句切分（★ 表格行也按「格」拆开，★ 因为表格里的错误同样致命）"""
    for i, line in enumerate(md.split("\n"), 1):
        s = line.strip()
        if not s:
            continue
        if s.startswith("|"):
            for cell in s.strip("|").split("|"):
                if cell.strip():
                    yield i, cell.strip()
        else:
            for part in re.split(r"(?<=[。；])", s):
                if part.strip():
                    yield i, part.strip()

def check(path):
    md = path.read_text(encoding="utf-8")
    bad = []
    for ln, sent in sentences(md):
        if CLAIM.search(sent) and NUM14.search(sent) and not LIMIT.search(sent):
            if META.search(sent):
                continue
            bad.append((ln, sent))
    return bad

def main():
    ok = True
    print("═" * 78)
    print("★ 散文层承重口径判据（★ 「+14」必须标明是【断言层】）")
    print("═" * 78)
    for t in TARGETS:
        if not t.exists():
            print("  · %s （不存在 ⇒ 跳过）" % t.name); continue
        bad = check(t)
        if bad:
            ok = False
            print("  ⛔ %s：%d 处「承重」与「+14」同处、★ 但未标明是断言层" % (t.name, len(bad)))
            for ln, s in bad[:6]:
                print("        L%-5d %s" % (ln, s[:150]))
        else:
            print("  ✔ %s：0 处" % t.name)
    # ★★★ 负向测试（★ 判据必须能红且红在预期处）★★★
    probe = "★ 承重聚合 OR → AND：口径 B 净 +14 → +14（不变）"
    if check_pure(probe):
        print("  ✔ 负向测试：★ 探针句被抓住（★ 判据能红）")
    else:
        print("  ⛔ 负向测试：★ 探针句【没被抓住】⇒ ★ 判据假绿！")
        ok = False
    print("─" * 78)
    print("★ 总体：%s" % ("✅ 通过" if ok else "❌ 有失败"))
    return 0 if ok else 1

def check_pure(text):
    md = text
    for ln, sent in sentences(md):
        if CLAIM.search(sent) and NUM14.search(sent) and not LIMIT.search(sent):
            if META.search(sent):
                continue
            return True
    return False

if __name__ == "__main__":
    sys.exit(main())
