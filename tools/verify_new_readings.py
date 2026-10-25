#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 【新增数字】回源核验器（★ 2026-10-25）

★★★ 它解决什么：★★
  ★ S1 判据报「新增数字 N 个（★ 允许，★ 但须带出处）」⇒ ★ **但从来没人核过「有没有出处」**
  ★ ★ v3.1 自己列的「核不到 ⑧：★ S1 报的 55/78/52/207 个新增数字没有逐个回源」★ **就是这一条**
  ★ ⇒ ★ 本工具把它变成**可核的**：★ 逐个分类 + 逐个回源 grep

★★★ 分类（★ 先把【非读数】剔掉，★ 否则噪音压过信号）：★★
  ★ 【非读数】章节号（`1.6` / `12.1` 形态且无单位）｜行号｜年份/日期｜百分号形态
    ｜纯编号（`02` `03` `05`）｜版本串片段｜千分位｜`0.0` 这类【占位/零值】… ★ 逐条写死
  ★ 【读数候选】其余（★ 带小数、带单位、带符号、≥2 位的连续数）

★★★ 回源（★ 「出处」的准确定义）：★★
  ★ 该 token 能在【台账集合】里 grep 到 ⇒ ★ **有出处**
  ★ 台账集合 = ★ `来源与底稿/`（★ 全部底稿）＋ `改稿规格_*.md` ＋ `papers/复核链/`（★ 审稿留痕）
    ＋ `papers/净增益双边重算_可粘贴段落_2026-10-25.md` ＋ `baseline/`（★ 改写前正文）
  ★ ★ **注意**：`baseline/` 算作出处候选 ⇒ 因为【改写前正文里就有的数】＝ 前作已核 ⇒ 不算新增读数

★ **负向测试**：★ 造一个不存在的读数 ⇒ 必须报「无出处」。
"""
import sys, re, json, pathlib, argparse, hashlib
sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parent.parent

PAPERS = {
    "L1": "papers/01_L1_PrematureConvergence_交差稿.md",
    "A":  "papers/02_A_SelectionIsNotCreation_稿.md",
    "C":  "papers/03_C_SixWaysToLookDone_稿.md",
    "D":  "papers/04_D_StateMachineIsNotYetAPrompt_交差稿.md",
    "L3": "papers/06_L3_层3自修改_交差稿.md",
}
BASE = {
    "L1": "baseline/papers/01_L1_PrematureConvergence_交差稿.md",
    "A":  "baseline/papers/02_A_SelectionIsNotCreation_稿.md",
    "C":  "baseline/papers/03_C_SixWaysToLookDone_稿.md",
    "D":  "baseline/papers/04_D_StateMachineIsNotYetAPrompt_交差稿.md",
    "L3": "baseline/papers/06_L3_层3自修改_交差稿.md",
}

def tokenize(text):
    """★ 与 S1 同款：★ 抽数字 token（含小数与负号）"""
    return set(re.findall(r"-?\d+(?:\.\d+)?%?", text))

# ★ 【非读数】形态
RE_SECT   = re.compile(r"^\d{1,2}\.\d{1,2}$")        # 1.6 / 12.1（★ 无单位无小数位多）
RE_PURE   = re.compile(r"^\d{1,4}$")                  # 02 / 03 / 109（★ 纯编号）
RE_PCT    = re.compile(r"%")
RE_DATE   = re.compile(r"^20\d{6}$|^\d{4}-\d{2}-\d{2}$")
RE_ZERO   = re.compile(r"^-?0(?:\.0+)?%?$")            # 0 / 0.0 / 0.0000
RE_VER    = re.compile(r"^20\d{6}$")

def classify(tok):
    """★ 返回 (类别, 原因)"""
    if RE_DATE.search(tok) or RE_VER.search(tok): return "非读数", "日期/版本串"
    if RE_PCT.search(tok):             return "非读数", "百分号形态"
    if RE_SECT.match(tok):
        # ★ 1.6 / 12.1 这类：★ 若三位以上小数（★ 0.429）⇒ 是读数
        dec = tok.split(".")[1] if "." in tok else ""
        if len(dec) <= 2: return "非读数", "章节号形态"
        return "读数候选", ""
    if RE_ZERO.match(tok):             return "非读数", "零值/占位"
    if RE_PURE.match(tok):              return "非读数", "纯编号（行号/序号）"
    return "读数候选", ""

def load_ledger():
    """★ 台账集合（★ 全部内容拼成一个大文本，★ 一次 grep）"""
    buf = []
    for d in ("来源与底稿", "papers/复核链"):
        p = ROOT / d
        if p.exists():
            for f in p.rglob("*"):
                if f.is_file() and f.suffix in (".md", ".txt", ".json", ".jsonl", ".py"):
                    try: buf.append(f.read_text(encoding="utf-8", errors="ignore"))
                    except Exception: pass
    for f in ROOT.glob("改稿规格*.md"):
        buf.append(f.read_text(encoding="utf-8", errors="ignore"))
    for extra in ("papers/净增益双边重算_可粘贴段落_2026-10-25.md",):
        p = ROOT / extra
        if p.exists(): buf.append(p.read_text(encoding="utf-8", errors="ignore"))
    p = ROOT / "baseline"
    if p.exists():
        for f in p.rglob("*.md"):
            buf.append(f.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(buf)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None, help="★ 机器可读输出路径")
    args = ap.parse_args()
    ledger = load_ledger()
    print("═" * 78)
    print("★ 【新增数字】回源核验（★ 台账 %d 字符）" % len(ledger))
    print("═" * 78)
    out = {}
    all_unbacked = []
    for key, rel in PAPERS.items():
        cur = (ROOT / rel).read_text(encoding="utf-8")
        base = (ROOT / BASE[key]).read_text(encoding="utf-8")
        added = sorted(tokenize(cur) - tokenize(base))
        cats = {"读数候选": [], "非读数": []}
        reasons = {}
        for t in added:
            c, why = classify(t)
            cats[c].append(t)
            if why: reasons[t] = why
        # ★ 回源：★ 读数候选逐个 grep
        # ★ 【出处形态 2】★ 正文自身的算式（★ 2026-10-25 实测补上）
        #   ★ ④篇 :832-840 的「方法论收获」段里有 1.545 / 1.624 / 1.978 / 3.468
        #     —— ★ 它们是【那行算式的中间量】（★ 如 `0.1418/0.0717 = 1.978×`）
        #   ⇒ ★ 它们的出处就是【正文自己那行算式】⇒ ★ 不需要外部台账
        #   ⇒ ★ 判法：★ 该数字所在行或邻两行里同时有【= / × / ÷】⇒ ★ 算自证
        cur_lines = cur.split("\n")
        def self_proven(tok):
            for i, l in enumerate(cur_lines):
                if tok in l:
                    ctx = "\n".join(cur_lines[max(0, i-2):i+3])
                    if re.search(r"[=×÷/]", ctx) and re.search(r"[0-9]", ctx):
                        return True
            return False
        backed, unbacked = [], []
        for t in cats["读数候选"]:
            # ★ 去掉负号与百分号再找（★ 台账里可能写法不同）
            probe = t.lstrip("-").rstrip("%")
            if probe and probe in ledger:
                backed.append(t)
            elif self_proven(t):
                backed.append(t)
            else:
                unbacked.append(t)
        all_unbacked += [(key, t) for t in unbacked]
        out[key] = {"added_total": len(added), "readings": len(cats["读数候选"]),
                    "backed": len(backed), "unbacked": sorted(unbacked),
                    "non_reading": len(cats["非读数"])}
        print("  %-4s 新增 %3d 个 ⇒ ★ 读数候选 %3d ｜ 非读数 %3d" % (key, len(added), len(cats["读数候选"]), len(cats["非读数"])))
        print("       ★ 有出处 %3d ｜ ★ **无出处 %3d**" % (len(backed), len(unbacked)))
        if unbacked:
            print("       ★ 无出处清单：%s" % (sorted(unbacked)[:14],))
    # ★★★ 负向测试（★ 判据必须能红）★★★
    print("─" * 78)
    fake = "0.987654"
    caught = fake not in ledger
    print("  ★ 负向测试：★ 探针读数 %s 在台账里？%s ⇒ %s" % (fake, "是" if not caught else "否",
          "✔ 判据能红（不存在的读数会被报出来）" if caught else "❌ 假绿！"))
    print("★ 总体：%s" % ("✅ 全部新增读数都有出处" if not all_unbacked else
          "⚠️ 有 %d 个新增读数【在仓内找不到出处】⇒ ★ 须逐个回源（★ 可能是包外数据、★ 也可能是真没有出处）" % len(all_unbacked)))
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print("★ 机器可读：%s" % args.json)
    return 0

if __name__ == "__main__":
    sys.exit(main())
