#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 从 git HEAD 的旧稿 + 当前新稿里，**机械地**对齐章节号，得出 旧→新 映射表
★ 用途：指针迁移（★ 外部文件引用的小节号必须跟着改）
★ 方法：抽标题行（`^#{2,4} <号> <标题>`）⇒ 按【标题文本相似度】对齐 ⇒ ★ 不用手抄
★ ★ 纪律：★ 相似度低的对齐**必须人工看一眼**，不自动采信（★ 标题改写过的会低分）
"""
import sys, re, subprocess, difflib, pathlib
sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parent.parent

FILES = {
    "L1": "papers/01_L1_PrematureConvergence_交差稿.md",
    "L3": "papers/06_L3_层3自修改_交差稿.md",
}

HEAD_RE = re.compile(r"^(#{2,4})\s*(?:§\s*)?(\d+(?:\.\d+)*)\s*(.*)$")


def headings(text):
    out = []
    for i, line in enumerate(text.split("\n"), 1):
        m = HEAD_RE.match(line)
        if m:
            num = m.group(2)
            title = m.group(3).strip()
            # ★ 去掉标题里的 ★/【】等装饰，只留可比的语义部分
            clean = re.sub(r"[★☆🔸•·—\-–|]+", " ", title)
            clean = re.sub(r"[【】\[\]（）()「」“”\"']+", " ", clean)
            clean = re.sub(r"\s+", " ", clean).strip()
            out.append({"num": num, "title": title, "clean": clean, "line": i, "raw": line})
    return out


def main():
    for tag, rel in FILES.items():
        old_txt = subprocess.run(
            ["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
        new_txt = (ROOT / rel).read_text(encoding="utf-8")
        old_h, new_h = headings(old_txt), headings(new_txt)
        print("═" * 78)
        print(f"★ {tag}  {rel}")
        print(f"  旧稿 {len(old_txt.splitlines())} 行 / 标题 {len(old_h)} 个 ｜ "
              f"新稿 {len(new_txt.splitlines())} 行 / 标题 {len(new_h)} 个")

        # ★ 贪心对齐：新稿的每个标题找旧稿里最像的一个
        used_old = set()
        mapping, low = [], []
        for nh in new_h:
            best, best_score = None, 0.0
            for oh in old_h:
                if oh["num"] in used_old:
                    continue
                s = difflib.SequenceMatcher(None, nh["clean"], oh["clean"]).ratio()
                if s > best_score:
                    best, best_score = oh, s
            if best is None:
                continue
            used_old.add(best["num"])
            if best["num"] != nh["num"]:
                mapping.append((best["num"], nh["num"], best_score, best["clean"][:34], nh["clean"][:34]))
                if best_score < 0.55:
                    low.append(mapping[-1])
        print(f"  ★ 发生重编号的 {len(mapping)} 条：")
        for o, n, s, ot, nt in mapping:
            mark = "  ⚠低分" if s < 0.55 else ""
            print(f"     §{o:<6} → §{n:<6}  sim={s:.2f}  「{ot}」→「{nt}」{mark}")
        # ★ 旧稿里没被对上的（= 被删掉的小节）
        matched = {o for o, _, _, _, _ in mapping} | {
            oh["num"] for oh in old_h if oh["num"] == next((n for o, n, _, _, _ in mapping if o == oh["num"]), None)
        }
        gone = [oh for oh in old_h if oh["num"] not in used_old]
        if gone:
            print(f"  ★ 旧稿中被删/合并的小节 {len(gone)} 个："
                  f"{', '.join('§' + g['num'] for g in gone[:14])}"
                  f"{' …' if len(gone) > 14 else ''}")
        if low:
            print(f"  ★ ★ 低分对齐 {len(low)} 条 ⇒ 需人工确认（★ 标题改写过）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
