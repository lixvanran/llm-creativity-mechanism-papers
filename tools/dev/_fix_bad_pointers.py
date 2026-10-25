#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 修指针迁移留下的三处坏指针（★ 按【行号】定位，★ 不手抄全角串）
坏指针成因（★ migrate_pointers.py 的三个缺陷）：
  ① 正则不吃字母后缀 ⇒ "5.1b" 被当成 "5.1" ⇒ 映射到 6.5 ⇒ 产出 "§6.5b"
  ② group(1) 已含 § 又拼了一个 ⇒ 产出 "§§3.1"
  ③ 验证步骤查的是"打算替换成什么"而非"文本实际变成什么" ⇒ 假绿
"""
import sys, pathlib
sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parent.parent

# ★ (文件, 行号, 该行必须含的短锚, 新行)
FIXES = [
    ("papers/00_论文簇总纲_交差版.md", 169, "§6.5b",
     "> ② **2×2 任务结构对照**（塌缩的真正条件 = 解法路径唯一）⇒ **L1 篇 §6.6**"),
    ("support/00_论文簇总纲_交差版.md", 139, "§6.5b",
     "> ② **2×2 任务结构对照**（塌缩的真正条件 = 解法路径唯一）⇒ **L1 篇 §6.6**"),
    ("support/交差说明_四篇_2026-10-24.md", 14, "§6.5b",
     "> ② **2×2 任务结构对照**（「塌缩的真正条件 = 解法路径唯一」）⇒ 进 **L1 篇 §6.6**"),
    ("papers/09_四篇初稿_合订本_2026-10-24.md", 99, "§1.2b",
     "| 「过早闭合现象存在」 ★ **本文此处特指【输出表述层同质化 / 相对覆盖不足】**（L1 §1.3：「过早停止探索」**本文未测**） | **中**（现象成立，归因不成立） | 每份答案 9 条断言去重后只剩 **5.2 条**不同考虑；实例内互相余弦 **0.91–0.97**；分支数↑但有效信息维度不增（**0.457 vs 基线 0.500**，⚠️ **条件性证据**：该指标有**已知循环风险**且**未做正负对照验证** ⇒ **不能单独支持「没有产生新维度」**，只与本行其它读数同向）|"),
    ("papers/07_待填审计_判据定版状态.md", 42, "§§3.1",
     "| L1-1 | 表征层 `Δ_PR`（§3.1 表，L151）| `Δ_PR = PR(跨档) − PR(同档 K=32)` | `◐` | **判据公式定版** | ① 塌缩判据的定版公式 | ① 本批已用 | ✅ |"),
    ("support/07_待填审计_判据定版状态.md", 42, "§§3.1",
     "| L1-1 | 表征层 `Δ_PR`（§3.1 表，L151）| `Δ_PR = PR(跨档) − PR(同档 K=32)` | `◐` | **判据公式定版** | ① 塌缩判据的定版公式 | ① 本批已用 | ✅ |"),
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
                print(f"✗ {f}:{ln} 越界"); sys.exit(1)
            cur = lines[i]
            if anchor not in cur:
                print(f"✗ {f}:{ln} 锚点 {anchor!r} 不匹配；实际：{cur[:100]!r}"); sys.exit(1)
            if cur == new:
                print(f"· {f}:{ln} 已正确（幂等跳过）"); continue
            lines[i] = new
            changed += 1
            print(f"✔ {f}:{ln} 已改")
        p.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n合计改动 {changed} 行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
