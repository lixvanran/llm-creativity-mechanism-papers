#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ ★ 指针迁移的【权威对拍】：★ 不用"重跑一遍"来验证（★ 那会二次映射），
★ 而是**从 git HEAD 的旧指针直接算出期望值**，再和当前磁盘上的实际指针逐条比。
★
★ ★ 为什么必须这么验（★ 三个坑叠在一起）：
★   ① L1_MAP 的【旧号】与【新号】有交集（★ 旧 3.3→新 3.1，而旧 3.1→新 1.2）
★      ⇒ ★ **重跑会把已迁移的指针二次映射**（★ 实测：§3.3→§3.1→§1.2）
★   ② "指针能在 L1 标题里查到"**不足以证明对**（★ §1.2 确实存在 ⇒ 查得到 ⇒ 假绿）
★   ③ 因此 ★ 唯一可靠的对拍基准是**改写前的原文**（★ git HEAD）
"""
import sys, re, subprocess, pathlib, json
sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parent.parent
# ★ 基线常量从【单一事实来源】读（★ tools/baseline.json）⇒ ★ 三个工具不可能再漏
BASELINE_COMMIT = json.loads((ROOT / "tools/baseline.json").read_text(encoding="utf-8"))["baseline_commit"]
sys.path.insert(0, str(ROOT / "tools"))

from migrate_pointers import L1_MAP, LIVE, PATTERNS, L1_CTX  # noqa: E402

NUM = r"(\d+(?:\.\d+)*(?:[a-z])?)"

# ★★★ 【有意偏离登记】：★ 机械迁移之外的**语义改写**必须登记理由
# ★   （★ 不登记 = 掩盖；★ 登记 = 可审）★ 格式：(文件, 第几个指针, 期望值, 实际值, 理由)
DEVIATIONS = [
    ("papers/09_四篇初稿_合订本_2026-10-24.md", 9, "2.3b", "6.5",
     "★ 旧 `§2.3b` 在 L1 稿中【从未存在过】（★ 全仓仅见于本文件与本工具）⇒ ★ 它自始是坏指针 "
     "⇒ ★ 按『填入位置 = 方向判决被记录处』的语义重指到新稿 §6.5 判决表第 3 行（★ 与相邻 :345 同粒度）"
     "⇒ ★ **不采用机械映射 §2.3→§2.9**，★ 因 §2.9 是「问题空间」侧的既有工作（★ 外部证据节）、"
     "★ 与『方向判定』无关"),
    ("papers/09_四篇初稿_合订本_2026-10-24.md", 10, "1.5", "7.2",
     "★ 该表列的动作是『写成能力边界』⇒ ★ 指针应指向**执行该动作的章节**，★ 而不是事实被顺带提到的一格 "
     "⇒ ★ 新稿 §7 专章为这件事而建，★ 其 §7.2 就是那句规范 ⇒ ★ §1.5 成立但只是相关工作表里的一格"),
    ("papers/09_四篇初稿_合订本_2026-10-24.md", 11, "2.7", "2.7",
     "★ 旧 §2.1③ 那个『③』是旧稿的子项编号；★ 新 §2.7 没有 ③ ⇒ ★ 机械迁移把 ③ 留下了 ⇒ ★ 去掉（★ 号码不变）"),
]

# ★★ 【对拍器的盲区】（★ 本轮真踩到 ⇒ ★ 必须写进代码里，★ 不然下一个人还会踩）
#   ★ 对拍只比较**能被 PATTERNS 捕获的指针** ⇒ ★ 而 PATTERNS 只认两种形态：
#     ① 带 L1/层1 前缀的（`L1 §4.4`）｜② `| L1-N |` 编号表格行里的裸 §
#   ⇒ ★ **裸 `§N.M`（无 L1 前缀、且不在 L1-N 行里）抓不到** ⇒ ★ 本轮 :348 的
#     `L1 §6.5 末行 + §1.2`（★ 行首是 `| **L1 表示层/注意力探针** |` ⇒ 不匹配任何模式）
#     **从未被迁移过，★ 而对拍器因为两边都捕不到而报"一致"** ⇒ ★ **这是假绿的第二层**
#   ⇒ ★ 落法：★ ① 这类指针**手工核**（★ 本轮已核 4 处）★ ② 记进本注释，★ 不当它不存在


# ★★★ 基线【不能是 HEAD】（★ 同一个病根我已经在验收器里修过一次，★ 这里漏了）
# ★   HEAD 会随 commit 往前走 ⇒ ★ **第一次 commit 之后，HEAD 里已经是被迁移过的文件**
# ★   ⇒ ★ 期望值会算成「已迁移的指针再迁移一次」⇒ ★ 对拍必假红
# ★ ⇒ ★ 落法：★ 基线固定为【本轮改稿前的 commit】⇒ ★ 与迁移器/验收器同一基线
def head_text(rel):
    r = subprocess.run(["git", "show", f"{BASELINE_COMMIT}:{rel}"], cwd=ROOT,
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def main():
    print("═" * 78)
    print("★ 指针迁移对拍：★ 期望值 = f(git HEAD 的旧指针) ⇒ 实际值 = 磁盘现状")
    print("═" * 78)
    total, bad = 0, []
    for rel in LIVE:
        old = head_text(rel)
        cur = (ROOT / rel).read_text(encoding="utf-8")
        if old is None:
            print(f"· {rel}  （HEAD 里没有 ⇒ 跳过）")
            continue
        # ★ 期望：在 HEAD 原文上跑一遍映射
        expected = old
        for rx, _ in PATTERNS:
            def sub(m):
                num = m.group(2)
                new = L1_MAP.get(num)
                if not new:
                    return m.group(0)
                return m.group(1) + "§" + new
            expected = rx.sub(sub, expected)
        # ★ 实际：当前文件里所有 L1 指针
        actual = []
        for rx, _ in PATTERNS:
            for m in rx.finditer(cur):
                actual.append((m.group(1), m.group(2), m.start()))
        # ★ 期望：HEAD 映射后所有 L1 指针
        exp = []
        for rx, _ in PATTERNS:
            for m in rx.finditer(expected):
                exp.append((m.group(1), m.group(2)))
        # ★ 逐条比：★ 序列必须一致（★ 顺序 + 号码）
        a_nums = [n for _, n, _ in actual]
        e_nums = [n for _, n in exp]
        n_ok = len(a_nums) == len(e_nums) and a_nums == e_nums
        total += len(e_nums)
        # ★ 逐条比，★ 但把【有意偏离】单独挑出来
        diff_idx = []
        for i in range(max(len(a_nums), len(e_nums))):
            av = a_nums[i] if i < len(a_nums) else None
            ev = e_nums[i] if i < len(e_nums) else None
            if av != ev:
                diff_idx.append((i, ev, av))
        dev_here = [d for d in DEVIATIONS if d[0] == rel]
        unexplained = []
        for idx, ev, av in diff_idx:
            hit = next((d for d in dev_here if d[1] == idx), None)
            if hit:
                print(f"  ★ 有意偏离 {rel} 第{idx}个指针：期望 {hit[2]} → 实际 {hit[3]}")
                print(f"     理由：{hit[4]}")
            else:
                unexplained.append((idx, ev, av))
        if not unexplained and len(a_nums) == len(e_nums):
            print(f"✔ {rel}  {len(e_nums)} 个指针逐条一致"
                  + (f"（★ 含 {len(dev_here)} 处已登记的有意偏离）" if dev_here else ""))
        elif unexplained:
            print(f"✗ {rel}  ★ 有 {len(unexplained)} 处【未登记】的不一致")
            for idx, ev, av in unexplained:
                print(f"    第{idx}个：期望 {ev} ｜ 实际 {av}")
            bad.append(rel)
        else:
            print(f"✗ {rel}  ★ 不一致")
            print(f"    期望（HEAD 映射后）：{e_nums}")
            print(f"    实际（磁盘现状）  ：{a_nums}")
            bad.append(rel)
    print("─" * 78)
    print(f"★ 对拍指针总数 {total} ｜ 不一致文件 {len(bad)} 个"
          f"{' ⇒ ' + ', '.join(bad) if bad else ' ⇒ ✔ 全部一致'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
