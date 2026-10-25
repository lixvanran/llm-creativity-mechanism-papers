#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 修 V1 阶段一报告的 F1 / F2 / F8（★ 按【行号】定位，★ 不手抄全角串）"""
import sys, io, pathlib
sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parent.parent

# ★ (文件, 行号(1-based), 该行必须含的短锚, 新行)
FIXES = [
    # ── F1：★ 提纲 :103 与 改稿规格 G4 冲突（★ 静默废了注意力归因红线）
    ("tools/四篇提纲_2026-10-25.md", 103, "我们论证根源在 Transformer 的注意力机制",
     '| 「三、**归因到注意力机制在现有数据下不被支持**」 | 「**我们提出【注意力机制假说】并给出可失败预测的检验路径**（4 条机制链 + 各自的可失败预测），并给出**三层分离协议**来定位它落在哪一层；**本批数据排除的是解码层**；★ **按 G4：本文只主张「与注意力机制相容，但本文未检验该假设」，不主张"根源已在注意力机制"被证明**」 |'
     ' ★ **★ G4 红线（硬约束，★ 本轮恢复并显式写入）**：★ **不许写"因为注意力…"**，★ 唯一允许的表述是「与注意力机制相容，但本文未检验该假设」⇒ ★ **① 篇的主张形态 = 机制假说 + 已定版判据**，★ **不是"已证明根源"** ⇒ ★ **验收：`grep "因为注意力"` = 0**，★ 且**所有"注意力"字样所在句必须带"未检验/相容/假说"之一** |'),

    # ── F2：★ 提纲 :59 的「47 而非 36×36 ⇒ 更少参数」是错的
    ("tools/四篇提纲_2026-10-25.md", 59, "36×36",
     '| **策略表示** | `score(a) = u[repair] + v[scope] + t[strict] + m[failure][repair]`，`p ∝ exp(u+v+t+m)` | ★ **为什么因子化而不是 36 路扁平 softmax**：动作是笛卡尔积 ⇒ 概率也该分解 ⇒ ★ **对照要写准：36 路扁平 = 36 个权重；因子化 = 47 个权重 ⇒ 参数【更多】（47 > 36），不是"更少"** ⇒ ★ **但每个权重只对应一个更小的、语义明确的子空间（修复型／范围／强度／交互项）⇒ ⇒ 学的是"在哪个子空间上加权"，而不是"在 36 个整体动作里挑一个" ⇒ ⇒ **更易学、更不易过拟合**；★ **只有对照"全交互扁平"（36×6 = 216）时才是数量级上的更少** |'),

    # ── F2：★ 写作模式 :62 同一处错
    ("tools/写作模式与项目整体认识_2026-10-25.md", 62, "36×36",
     '- ★★ **策略表示（核心公式）**：`score(a) = u[repair] + v[scope] + t[strict] + m[failure][repair]`，`p ∝ exp(u+v+t+m)`；**全策略 57 权重**（动作部分 47 = 6+2+3+6×6；架构自由度 10 = arb3+nf4+mm3）★ **因子化而非 36 路扁平 softmax** ⇒ ★ **对照写准：36 路扁平 = 36 个权重，因子化 = 47 个 ⇒ 参数【更多】**（★ 不是"更少"）⇒ ★ **真正的理由是"每个权重的可学子空间更小、更语义明确" ⇒ 更易学、更不易过拟合**；★ **只有对照"全交互扁平"（36×6 = 216）时才是数量级上的更少**'),

    # ── F8：★ 对外措辞化规则引用了不存在的 tools/check_readable_marks.py
    ("tools/对外措辞化规则_2026-10-25.md", 19, "check_readable_marks",
     '| **H1** | ★ **数字零改动**：正文里任何读数（0.886 / 0.944 / 2.65 / 944 / 61.5% …）**一个都不许动** | ★ 改前/改后全文数字集合差集 ＝ ∅（★ **`tools/check_cluster_consistency.py` 的 S1**，★ **基线 = 固定 commit `8649661`**，★ **不是 `HEAD`** ⇒ ★ 否则第一次 commit 就失效） |'),

    ("tools/对外措辞化规则_2026-10-25.md", 71, "check_readable_marks",
     'python3 tools/check_cluster_consistency.py --head 8649661   # ★ 基线固定为本轮改稿前的 commit（★ 不用 HEAD）'),

    ("tools/对外措辞化规则_2026-10-25.md", 81, "check_readable_marks",
     '★ ★ **★ 必读**：★ `tools/check_cluster_consistency.py` 的 **S1 数字差集**在**基线 commit `8649661`**（= 本轮开始前的仓内状态）上取 ⇒ ★ **不要在改完之后才生成基线**（★ 那样差集恒为空、判据失效）⇒ ★ **且基线不能写成 `HEAD`**（★ 第一次 commit 就会让它失效 ⇒ ★ 本条已由审稿人 F8 抓出并修掉）。'),
]


def main():
    by_file = {}
    for f, ln, anchor, new in FIXES:
        by_file.setdefault(f, []).append((ln, anchor, new))

    changed = 0
    for f, items in by_file.items():
        p = ROOT / f
        lines = p.read_text(encoding="utf-8").split("\n")
        for ln, anchor, new in items:
            i = ln - 1
            if i < 0 or i >= len(lines):
                print(f"✗ {f}:{ln} 越界（文件只有 {len(lines)} 行）")
                sys.exit(1)
            cur = lines[i]
            if anchor not in cur:
                print(f"✗ {f}:{ln} 锚点不匹配：期望含 {anchor!r}，实际 {cur[:90]!r}")
                sys.exit(1)
            if cur == new:
                print(f"· {f}:{ln} 已是目标内容（幂等跳过）")
                continue
            lines[i] = new
            changed += 1
            print(f"✔ {f}:{ln} 已改")
        p.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n合计改动 {changed} 行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
