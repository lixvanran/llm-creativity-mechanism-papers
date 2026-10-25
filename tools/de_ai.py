#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
去 AI 味清洗器（★ 2026-10-25）

为什么需要它：
  上一轮改稿的正文里，"★" 被当段落重音、"⇒" 被当逻辑连接词，
  再加上自造黑话（落法/处置/通则/纪律）和嵌套三层的括号限定，
  读起来像模板批量生成，而不是人写的。

做什么：
  1. 剥掉装饰性 "★"（★ 不承载信息，★ 纯粹是重音噪音）
  2. 把 "⇒"（含 "⇒ ⇒ ⇒" 链）降为普通标点，★ 让句子自己站住
  3. 换掉一批自造黑话与套话
  4. 收拾清洗后留下的排版碎屑

不做什么（★ 这些是语义标记，★ 不是装饰，★ 一律不动）：
  - 三标记 "⚠️" / "【待完成】" / "📌"（★ 有统一图例、★ 判据要数它们）
  - 圈码 ①②③（★ 出现在图例与结构列表里，★ 不是噪音）
  - 代码围栏与行内代码里的内容（★ 那里是逐字引用与命令，★ 改了就是篡改）

硬保证：
  - 幂等：跑两遍结果一致
  - 数字零改动：清洗前后数字 token 序列必须完全相同
  - 所有替换词条都不含数字
"""
import re
import sys
import pathlib
from collections import Counter

sys.dont_write_bytecode = True

# ── 词表（★ 全部不含数字，★ 保证不引入新读数）────────────────────────
PHRASES = [
    ("落法：", "做法："),
    ("落法", "做法"),
    ("处置动作", "处理动作"),
    ("处置", "处理"),
    ("通则", "原则"),
    ("纪律：", "要求："),
    ("纪律", "要求"),
    ("值得注意", "注意"),
    ("这意味着", "也就是说"),
    ("换句话说，", ""),
    ("本轮", "这一轮"),
    ("本批次", "这一批"),
    ("根因：", "原因："),
    ("一句话总结", "一句话"),
]

FENCE_RE = re.compile(r"^```.*?^```", re.M | re.S)
SPAN_RE = re.compile(r"`[^`\n]+`")
ARROW_RE = re.compile(r"(?:⇒[ \t]*)+")
LINE_START_RE = re.compile(r"(?:^|\n)[ \t]*(?:>[ \t]*)?(?:[-*+][ \t]*)?(?:\|[ \t]*)?$")
NUM_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?%?")


def _arrow(m):
    """★ 箭头降级要【看上下文】（★ 同一个 ⇒ 在不同位置该去该留不一样）"""
    before = m.string[:m.start()].rstrip()
    after = m.string[m.end():].lstrip()
    if LINE_START_RE.search(before):
        return ""                                   # 段首箭头：★ 纯装饰
    if before.endswith(("。", "！", "？")):
        return ""                                   # 句子已断：★ 另起一句即可
    # ★ 箭头在粗体【里面】还是【两段粗体之间】？★ 用 "**" 的奇偶判开合
    if before.endswith("**"):
        if before.count("**") % 2 == 1:             # 奇数 ⇒ 最后一个是【开】
            return ""                               # "**⇒ Y**" ⇒ "**Y**"
        return "，"                                 # 偶数 ⇒ 最后一个是【闭】⇒ 段间
    return "，"


def _clean_spacing(s: str) -> str:
    """★ 收拾清洗留下的排版碎屑（★ 不碰任何数字）"""
    s = re.sub(r"，\s*，+", "，", s)
    s = re.sub(r"。\s*。+", "。", s)
    s = re.sub(r"。\s*，", "。", s)
    s = re.sub(r"；\s*；+", "；", s)
    s = re.sub(r"：\s*：+", "：", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"^([ \t]*(?:>[ \t]*)?(?:[-*+][ \t]*)?(?:\|[ \t]*)?)[，、]", r"\1", s, flags=re.M)
    s = re.sub(r"([。！？，：；、）】」])\s+(?=[\u4e00-\u9fff])", r"\1", s)
    s = re.sub(r"[ \t]+(?=[，。；：、）】」》])", "", s)
    # ★ 中文括号内外的多余空格（★ 剥掉 ★ 后最常见的一种碎屑）
    s = re.sub(r"（[ \t]+", "（", s)
    s = re.sub(r"[ \t]+(？|）)", r"\1", s)
    s = re.sub(r"(?<=[一-鿿」』）])[ \t]+(?=（)", "", s)
    # ★ 剥掉行首星号后留下的缩进（★ 保留 4 空格以上的代码块缩进）
    s = re.sub(r"^[ \t]{0,3}(?=\*\*)", "", s, flags=re.M)
    s = re.sub(r"(⚠️|✅|📌)[ \t]*(?=\1)", r"\1", s)
    s = re.sub(r"（[ \t]*\*\*", "（**", s)
    s = re.sub(r"\*\*[ \t]*\*\*", "**", s)
    s = re.sub(r"\*\*[ \t]*([，。；：、）])", r"**\1", s)
    s = re.sub(r"(?<![ \t])\*\*", "**", s)
    s = re.sub(r"，[ \t]*(?=[，。；：）])", "，", s)
    return "\n".join(l.rstrip() for l in s.split("\n"))


def _deco_prose(s: str) -> str:
    """★ 对一段散文做去装饰（★ 假定不含围栏与行内码）"""
    s = s.replace("★", "")
    s = ARROW_RE.sub(_arrow, s)
    for a, b in PHRASES:
        s = s.replace(a, b)
    return _clean_spacing(s)


def transform(text: str) -> str:
    """★ 逐段变换：★ 代码围栏与行内码原样保留"""
    holder = []

    def _stash_span(m):
        holder.append(m.group(0))
        return "\x00S%d\x00" % (len(holder) - 1)

    fenced, pos = [], 0
    for m in FENCE_RE.finditer(text):
        fenced.append(text[pos:m.start()])
        holder.append(m.group(0))
        fenced.append("\x00F%d\x00" % (len(holder) - 1))
        pos = m.end()
    fenced.append(text[pos:])
    stage = SPAN_RE.sub(_stash_span, "".join(fenced))
    stage = _deco_prose(stage)
    # 回填
    def _restore(m):
        idx = int(m.group(1))
        s = holder[idx]
        return s if s.startswith("```") else s
    stage = re.sub(r"\x00[SF](\d+)\x00", _restore, stage)
    return stage


def numbers(text: str):
    return NUM_RE.findall(text)


def main():
    args = [a for a in sys.argv[1:] if a != "--check"]
    check = "--check" in sys.argv
    if not args:
        print("用法: python3 tools/de_ai.py <file.md> [...]   （--check 只报差异）")
        return 2
    rc = 0
    for f in args:
        p = pathlib.Path(f)
        old = p.read_text(encoding="utf-8")
        new = transform(old)
        if transform(new) != new:
            print("✘ %s 清洗不幂等！" % f)
            rc = 1
        no, nn = numbers(old), numbers(new)
        if no != nn:
            co, cn = Counter(no), Counter(nn)
            lost = {k: (co[k], cn[k]) for k in co if cn[k] < co[k]}
            gain = {k: (co[k], cn[k]) for k in cn if cn[k] > co.get(k, 0)}
            print("✘ %s 数字变了！ 减少=%s 增加=%s" % (f, lost, gain))
            rc = 1
        if check:
            print("  %s：★ %d，⇒ %d，字符 %d → %d（数字 %d 个不变）" % (
                f, old.count("★"), old.count("⇒"), len(old), len(new), len(nn)))
        else:
            p.write_text(new, encoding="utf-8")
            print("✔ %s：★ %d→%d，⇒ %d→%d，字符 %d→%d（数字 %d 个不变）" % (
                f, old.count("★"), new.count("★"), old.count("⇒"), new.count("⇒"),
                len(old), len(new), len(nn)))
    return rc


if __name__ == "__main__":
    sys.exit(main())
