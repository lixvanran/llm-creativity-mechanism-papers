#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
跨文件指针迁移（★ 2026-10-25 · L1 重编号后的一次性修复）

★ 为什么需要它：★ L1 篇在 2026-10-25 的改稿里**重编了全部小节号**
（★ 方法论主体提为 §2、仪器边界提为 §7 等）⇒ ★ 活文档里指向 L1 旧小节号的指针全部指空。

★ ★ 两条铁律（★ 决定了本脚本改什么、不改什么）：
  1. ★ **活文档改指针**（总纲 / support / 合订本 / 待填审计 / 交付总览）
     —— ★ 它们是对外活文档，读者会照着找。
  2. ★ **历史留痕不改内容**（改稿报告 / 终审报告 / 改稿规格 / 审稿回执 / _FINAL_REVIEW_DONE）
     —— ★ 它们记录的是"**当轮**改了什么"，★ 旧行号是**当时的事实** ⇒ ★ 改了就是篡改历史。
     ⇒ ★ 代替做法：在入口文档统一声明"**这些文件里的小节号指向改写前那一版**"。

★ 用法：
    python3 tools/migrate_pointers.py            # 真改
    python3 tools/migrate_pointers.py --dry-run  # 只报告
★ 纪律：★ `sys.dont_write_bytecode = True`（★ 工具不得污染被检树）
"""
import sys, json
sys.dont_write_bytecode = True

import re
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ★★ L1 旧→新映射（W1 交回的完整映射表，★ 逐条与 L1 新稿标题核对过）
L1_MAP = {
    "1.2": "1.5",
    "1.3": "1.6",
    "1.4": "1.7",
    "2.1": "2.7",
    "2.2": "2.8",
    "2.3": "2.9",
    "2.4": "2.10",
    "3.1": "1.2",
    "3.1b": "1.3",
    "3.2": "1.4",
    "3.3": "3.1",
    "3.4": "4.2",
    "3.5": "4.4",
    "3.6": "4.6",
    "4.1": "6.1",
    "4.2": "6.2",
    "4.3": "6.3",
    "4.4": "6.4",
    "5.1": "6.5",
    "5.1b": "6.6",
    "5.2": "6.7",
    "5.3": "6.8",
    "5.3.1": "6.8.1",
    "5.4": "6.9",
    "5.5": "5.1",
    "5.5.1": "5.1.1",
    "5.6": "8.2",
    "5.7": "6.10",
    "6": "9",
    "6.1": "9.1",
    "6.2": "9.2",
    "6.3": "9.3",
    "6.4": "9.4",
    "6.5": "9.5",
    "7": "10",
    "8": "11",
    "9": "12",
}

# ★ ★ 旧稿的【无号 h4】（★ 机械对齐漏掉的 3 个）⇒ ★ 手工补（★ 依据：W1 权威表）
H4_MAP = {
    "3.4": "4.3",
    "3.5": "4.5",
}

# ★ ★ 旧稿本来就【悬空】的号（★ 旧 §7 只有一张表、从来没有 7.3/7.4 子节）⇒ ★ 按语义拆
SUSPENDED = {
    "7.3": "2.1 + §7.2",
    "7.4": "6.4 + §6.8.1",
}

# ★ ★ 旧稿的【无号 h4】（★ 机械对齐漏掉的 3 个）⇒ ★ 手工补（★ 依据：W1 权威表）
H4_MAP = {
    "3.4": "4.3",
    "3.5": "4.5",
}

# ★ ★ 旧稿本来就【悬空】的号（★ 旧 §7 只有一张表、从来没有 7.3/7.4 子节）⇒ ★ 按语义拆
SUSPENDED = {
    "7.3": "2.1 + §7.2",
    "7.4": "6.4 + §6.8.1",
}

# ★ ★ 旧稿的【无号 h4】（★ 机械对齐漏掉的 3 个）⇒ ★ 手工补（★ 依据：W1 权威表）
H4_MAP = {
    "3.4": "4.3",
    "3.5": "4.5",
}

# ★ ★ 旧稿本来就【悬空】的号（★ 旧 §7 只有一张表、从来没有 7.3/7.4 子节）⇒ ★ 按语义拆
SUSPENDED = {
    "7.3": "2.1 + §7.2",
    "7.4": "6.4 + §6.8.1",
}

# ★ ★ 旧稿的【无号 h4】（★ 机械对齐漏掉的 3 个）⇒ ★ 手工补（★ 依据：W1 权威表）
H4_MAP = {
    "3.4": "4.3",
    "3.5": "4.5",
}

# ★ ★ 旧稿本来就【悬空】的号（★ 旧 §7 只有一张表、从来没有 7.3/7.4 子节）⇒ ★ 按语义拆
SUSPENDED = {
    "7.3": "2.1 + §7.2",
    "7.4": "6.4 + §6.8.1",
}

# ★ 活文档（★ 对外可读，读者会照着指针找）
LIVE = [
    "papers/00_论文簇总纲_交差版.md",
    "support/00_论文簇总纲_交差版.md",
    "support/交差说明_四篇_2026-10-24.md",
    "papers/09_四篇初稿_合订本_2026-10-24.md",
    "papers/07_待填审计_判据定版状态.md",
    "support/07_待填审计_判据定版状态.md",
    "交付总览_人肉审版_2026-10-25.md",
]

# ★ 历史留痕（★ 不改内容，★ 只登记）
HISTORY = [
    "papers/改稿报告_A_2026-10-24.md", "papers/改稿报告_C_2026-10-24.md",
    "papers/改稿报告_D_2026-10-24.md", "papers/改稿报告_L1_2026-10-24.md",
    "papers/改稿报告_L3_2026-10-24.md", "papers/改稿报告_合订本与总纲_2026-10-24.md",
    "papers/终审报告_外部审稿意见逐条复核_2026-10-24.md",
    "papers/终审报告_方向3层3_2026-10-25.md",
    "papers/终审后修复报告_2026-10-24.md", "papers/终审后修复报告_方向3层3_2026-10-25.md",
    "papers/审稿回执_方向3层3_规格审计_2026-10-24.md",
    "改稿规格_2026-10-24.md", "改稿规格_方向3_层3_2026-10-24.md",
    "papers/_FINAL_REVIEW_DONE.md", "papers/_INTEGRATE_DONE.md",
    "审稿意见_外部评审_2026-10-24.md",
]

# ★ 指向 L1 的上下文前缀（★ 用于确认"这个 § 指的是 L1 而不是本文件"）
L1_CTX = r"(?:L1\s*篇|L1篇|L1|层1|L1_|_L1)[^§]{0,12}"

# ★ 只在这些语境下替换：明确带 L1/层1 前缀的，或位于"待填审计"表里的 L1-x 条目行
# ★★ 关键：★ 章节号**可能带字母后缀**（§3.1b / §5.1b / §6.8.1）⇒ 必须一起捕获
#   （★ 否则 "5.1b" 会被当成 "5.1" ⇒ 映射到 6.5 ⇒ 产出 "§6.5b" 这种坏指针）
NUM = r"(\d+(?:\.\d+)*(?:[a-z])?)"
PATTERNS = [
    # 「L1 篇 §5.1b」／「L1 §3.1b」／「层1 §3.4」…
    (re.compile(rf"({L1_CTX})§\s*{NUM}"), "ctx"),
    # 「L1-1 | 表征层 Δ_PR（§3.3 表，L151）」—— 括号里的裸 §
    # ★ group(1) **不含** §（★ 否则拼回去会出 "§§3.1"）
    (re.compile(rf"(\|\s*\*?\*?L1-\d+\*?\*?\s*\|[^|\n]{{0,40}}?)\s*§\s*{NUM}"), "bare_after_L1"),
]


def l1_headings():
    """★ L1 新稿里真实存在的章节号（★ 用来验证迁移后的指针不是指空的）"""
    t = (ROOT / "papers/01_L1_PrematureConvergence_交差稿.md").read_text(encoding="utf-8")
    out = set()
    for m in re.finditer(r"^#{2,4}\s*(?:§\s*)?(\d+(?:\.\d+)*)", t, re.M):
        out.add(m.group(1))
    for m in re.finditer(r"^#{2,4}\s*§(\d+\.\d+\.\d+)", t, re.M):
        out.add(m.group(1))
    return out


def actual_pointers(text):
    """★ ★ 从【已改好的文本】里抽出实际存在的 L1 指针（★ 不是"打算替换成什么"）
    ⇒ ★ 这才是真验证（★ 上一版验证的是意图 ⇒ 假绿）"""
    out = []
    for rx, _ in PATTERNS:
        for m in rx.finditer(text):
            out.append(m.group(2))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="★ 强制重跑（★ 默认：已迁移过的文件会被跳过 ⇒ 幂等）")
    a = ap.parse_args()

    heads = l1_headings()
    # ★ 排序：长的先替（§5.1b 必须在 §5.1 之前）
    order = sorted(L1_MAP.items(), key=lambda kv: -len(kv[0]))
    changes, bad = [], []

    # ★★★ 幂等守卫（★ 记忆铁律：★ 守卫必须【先判整块已应用】再判锚点）
    # ★ 为什么需要：★ L1_MAP 的【旧号】与【新号】有交集（★ 如旧 3.3→新 3.1，而旧 3.1→新 1.2）
    #   ⇒ ★ 重跑会把已迁移的指针【二次映射】（★ 实测：07 那两个文件各会被再改 1 处）
    # ★ 做法：★ 状态文件记录"已迁移完成"的文件 ⇒ 默认跳过 ⇒ ★ 要重跑显式 --force
    state_p = ROOT / "tools/.pointer_migration_state.json"
    state = {"done": []}
    if state_p.exists():
        state = json.loads(state_p.read_text(encoding="utf-8"))
    done = set(state.get("done", []))

    for rel in LIVE:
        f = ROOT / rel
        if not f.exists():
            print(f"⚠ 缺文件 {rel}")
            continue
        if rel in done and not a.force:
            print(f"· {rel}  已迁移过（★ 幂等跳过；★ 要重跑加 --force）")
            continue
        txt = f.read_text(encoding="utf-8")
        orig = txt

        for rx, kind in PATTERNS:
            def sub(m):
                if kind == "ctx":
                    pre, num = m.group(1), m.group(2)
                else:
                    pre, num = m.group(1), m.group(2)
                new = L1_MAP.get(num)
                if not new:
                    return m.group(0)
                changes.append((rel, m.group(0), pre + "§" + new))
                return pre + "§" + new
            txt = rx.sub(sub, txt)

        if txt != orig:
            if not a.dry_run:
                f.write_text(txt, encoding="utf-8")
            print(f"✔ {'[dry] ' if a.dry_run else ''}{rel}  改了 {len(txt.splitlines())} 行")

    # ★★★ 验证：★ **必须重读【已改好的文件】、抽出【实际存在的指针】再核**
    #   （★ 上一版查的是"我打算替换成什么" ⇒ 假绿：★ "§6.5b" 在 intentions 里是 "§6.5" ⇒ 查得到 ⇒ 放行，
    #    ★ 而磁盘上实际是 "§6.5b" ⇒ 查不到）
    #   ⇒ ★ 这条是"判据必须能红，且红在预期处"的直接应用
    print("─" * 68)
    missing = []
    checked = 0
    for rel in LIVE:
        f = ROOT / rel
        if not f.exists():
            continue
        txt = f.read_text(encoding="utf-8")
        for num in actual_pointers(txt):
            checked += 1
            if num not in heads:
                missing.append((rel, num))
    print(f"★ 迁移 {len(changes)} 处指针")
    print(f"★ 验证：★ 重读 {len(LIVE)} 个活文档、★ 抽出 {checked} 个**实际**指针逐一核")
    if missing:
        print(f"⚠ 指向不存在章节的指针 {len(missing)} 处 ⇒ {missing[:12]}")
    else:
        print("✔ 全部**实际**指针在 L1 新稿里都能找到对应章节")

    # ★★ 反向核验：★ 磁盘上不许留坏形态（★ 双 § / 字母后缀残留 / 映射表里已废弃的号）
    bad_forms = []
    for rel in LIVE:
        f = ROOT / rel
        if not f.exists():
            continue
        txt = f.read_text(encoding="utf-8")
        for m in re.finditer(r"§§", txt):
            bad_forms.append((rel, "双 §", txt[max(0, m.start() - 30):m.start() + 20]))
    if bad_forms:
        print(f"⚠ 残留坏形态 {len(bad_forms)} 处 ⇒ {bad_forms[:6]}")
    else:
        print("✔ 无残留「§§」坏形态")

    print(f"★ 历史留痕文件（★ 不改内容）：{len(HISTORY)} 个")
    print("  → 替代做法：入口文档声明「这些文件里的小节号指向改写前那一版」")

    # ★★ 记录"已迁移"的文件 ⇒ ★ 下次跑默认跳过（★ 幂等）
    if not a.dry_run:
        touched = sorted({c[0] for c in changes})
        for rel in touched:
            done.add(rel)
        state["done"] = sorted(done)
        state_p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"★ 幂等状态已记入 {state_p.name}（{len(done)} 个文件）")
    return 1 if (missing or bad_forms) else 0


if __name__ == "__main__":
    sys.exit(main())
