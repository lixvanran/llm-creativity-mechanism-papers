#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 合订本「没改一个字」的判据（★ 2026-10-25）

★★★ 它怎么证明：★★
  ★ ① 把合订本**逐篇切开**（★ 靠【第 N 篇 / 共 5 篇】标记）
  ★ ② 每篇：★ 去掉合订本加的【篇首块】⇒ ★ 标题**反向平移回去**（★ `##` → `#`）
  ★ ③ 与该篇**原 md 逐字节比**（★ 读的是 git HEAD 里的版本？★ 不、★ 读磁盘当前版本）
  ★ ④ 相等 ⇒ ★ 「正文一字未改」成立

★ ★★ **负向测试**：★ 故意往合订本里塞一个字 ⇒ **必须判红** ⇒ ★ 否则这条判据是假绿。

★ **用法**：python3 tools/check_anthology.py
"""
import sys, re, pathlib, hashlib
sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parent.parent
ANTH = ROOT / "四篇正文合订本_2026-10-25.md"

PARTS = [
    ("① L1", "papers/01_L1_PrematureConvergence_交差稿.md"),
    ("② A",  "papers/02_A_SelectionIsNotCreation_稿.md"),
    ("③ C",  "papers/03_C_SixWaysToLookDone_稿.md"),
    ("④ D",  "papers/04_D_StateMachineIsNotYetAPrompt_交差稿.md"),
    ("③ L3", "papers/06_L3_层3自修改_交差稿.md"),
]
MARK = re.compile(r"^## 【第 (\d+) 篇 / 共 5 篇】")
BODY_START = "> ★ ↓↓↓ **以下为原文逐字**（★ 标题级别下移一级、★ 文字未改）"
H = re.compile(r"^(#{1,6})(\s)")

def unshift(lines):
    out = []
    for l in lines:
        m = H.match(l)
        if not m:
            out.append(l); continue
        n = len(m.group(1))
        # ★ ★ 平移是单向的 +1 ⇒ 复原时凡 h2..h6 都 −1；★ 原本 h1 的会变 h2 ⇒ 复原正确
        out.append("#" * max(1, n - 1) + m.group(2) + l[m.end():])
    return out

def split_anthology(text):
    """★ 切成 [(篇号, 该篇正文行)]

    ★★★ 分段【不能靠 `---`】（★ 2026-10-25 实测踩到）：★★
      ★ **原文件内部本来就有 `---`（★ markdown 分隔线）** ⇒ ★ 靠 `---` 分段
        ⇒ ★ 会把【篇内第一个分隔线】当成篇末 ⇒ ★ 截断 ⇒ ★ 判据报「行数不够」
      ⇒ ★ 正解：★ **靠「## 【第 N 篇 / 共 5 篇】」标记分段** ⇒ ★ 段尾精确去掉
        ★ 合订本加的那条篇末分隔（★ 形态 = 空行 + `---` + 空行）
    """
    lines = text.split("\n")
    segs, cur, inbody = [], None, False
    for l in lines:
        m = MARK.match(l)
        if m:
            cur = int(m.group(1)); inbody = False; segs.append((cur, [])); continue
        if cur is None:
            continue
        if not inbody:
            if l.strip() == BODY_START:
                inbody = True
            continue
        segs[-1][1].append(l)
    # ★ 段尾：★ 去掉合订本加的篇末分隔（★ 形态 = ["", "---", ""]）
    for _, body in segs:
        while len(body) >= 3 and body[-1].strip() == "" and body[-2].strip() == "---" and body[-3].strip() == "":
            del body[-3:]
    return segs

def compare(anth_text):
    segs = split_anthology(anth_text)
    results = []
    for idx, (tag, rel) in enumerate(PARTS, 1):
        got = [s for s in segs if s[0] == idx]
        if len(got) != 1:
            results.append((tag, rel, "★ 段数 %d（★ 期望 1）" % len(got), None, None)); continue
        body = got[0][1]
        # ★ 去掉末尾空行（★ 拼接时统一加的）
        while body and body[-1].strip() == "":
            body.pop()
        restored = unshift(body)
        orig = (ROOT / rel).read_text(encoding="utf-8").split("\n")
        while orig and orig[-1].strip() == "":
            orig.pop()
        a = "\n".join(restored).encode("utf-8")
        b = "\n".join(orig).encode("utf-8")
        if a == b:
            results.append((tag, rel, "✅ 逐字节一致", len(b), None))
        else:
            # ★ 找出第一处差异（★ 便于定位）
            al, bl = a.split(b"\n"), b.split(b"\n")
            first = next((i for i in range(max(len(al), len(bl)))
                          if (al[i] if i < len(al) else None) != (bl[i] if i < len(bl) else None)), None)
            results.append((tag, rel, "❌ 第 %s 行起不一致" % first, len(b), (al[first][:60] if first is not None and first < len(al) else None,
                                                                            bl[first][:60] if first is not None and first < len(bl) else None)))
    return results

def main():
    if not ANTH.exists():
        print("⛔ 找不到合订本：%s" % ANTH); return 2
    text = ANTH.read_text(encoding="utf-8")
    print("═" * 78)
    print("★ 合订本「没改一个字」判据（★ 反向平移后逐字节回源比）")
    print("═" * 78)
    ok = True
    for tag, rel, verdict, n, diff in compare(text):
        good = verdict.startswith("✅")
        ok &= good
        print("  %-5s %-46s %s" % (tag, rel[-46:], verdict))
        if diff:
            print("        合订本: %r" % (diff[0],))
            print("        原文件: %r" % (diff[1],))
    # ★★★ 负向测试（★ 判据必须能红且红在预期处）★★★
    #   ★ ★ **必须篡改【正文区】里的字符**（★ 2026-10-25 实测踩到）：
    #     ★ 第一版改的是【篇首块】里的标题（★ 那是合订本加的元信息、★ 不在正文区）
    #       ⇒ ★ 判据当然抓不到 ⇒ ★ **判据假绿**（★ 差点让我以为判据坏了）
    #   ⇒ ★ 正解：★ 在【BODY_START 之后的正文区】里找一处、改一个字
    lines = text.split("\n")
    bi = next((i for i, l in enumerate(lines) if l.strip() == BODY_START), None)
    if bi is None:
        print("  ⛔ 找不到正文起点标记"); return 1
    # ★ 在正文区里找一个可改的汉字
    hit = None
    for i in range(bi + 1, len(lines)):
        for j, ch in enumerate(lines[i]):
            if "\u4e00" <= ch <= "\u9fff":
                hit = (i, j, ch); break
        if hit: break
    if not hit:
        print("  ⛔ 正文区里找不到可篡改的汉字"); return 1
    i, j, ch = hit
    lines[i] = lines[i][:j] + "\u4e00" + lines[i][j + 1:]   # ★ 换成一个不同的汉字
    tampered = "\n".join(lines)
    caught = not all(r[2].startswith("\u2705") for r in compare(tampered))
    print("     （★ 篡改位置：正文区第 %d 行、★ 第 %d 字、★ 『%s』→『\u4e00』）" % (i - bi, j, ch))
    print("  ★ 负向测试：★ 篡改一个字符后判据%s" % ("★ **抓住了**（判据能红）✔" if caught else "★ **没抓住** ⇒ 判据假绿！❌"))
    ok &= caught
    print("─" * 78)
    print("★ 总体：%s" % ("✅ 五篇逐字节一致、★ 合订本没改任何一个字" if ok else "❌ 有失败"))
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
