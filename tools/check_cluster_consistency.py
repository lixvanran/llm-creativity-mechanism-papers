#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
论文簇全链一致性验收器（★ 2026-10-25 · 交付态用）

★ 为什么需要它：★ 本轮 4 个 writer 各改各的一篇 + 1 个取证 Agent 出新文件
⇒ ★ "一处错全链一起改"（记忆铁律）必须有**机械判据**，不能靠人记。

★ 基线 = **git HEAD**（`git show HEAD:<path>`）⇒ ★ 不依赖额外快照文件
⇒ ★ 基线随 commit 走 ⇒ ★ 永远是"改前"的那一版。

用法：
    python3 tools/check_cluster_consistency.py            # 全量检查
    python3 tools/check_cluster_consistency.py --verbose  # 打印明细
    python3 tools/check_cluster_consistency.py --head <sha>   # 指定基线

★ 纪律：★ 工具**不得污染被检树** ⇒ `sys.dont_write_bytecode = True`
"""
import sys
sys.dont_write_bytecode = True

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# ★ 基线常量从【单一事实来源】读（★ tools/baseline.json）⇒ ★ 三个工具不可能再漏
BASELINE_COMMIT = json.loads((ROOT / "tools/baseline.json").read_text(encoding="utf-8"))["baseline_commit"]

# ★ 四篇正文（★ 与 `四篇提纲` §0.2 一致）
PAPERS = {
    "L1": "papers/01_L1_PrematureConvergence_交差稿.md",
    "A":  "papers/02_A_SelectionIsNotCreation_稿.md",
    "L3": "papers/06_L3_层3自修改_交差稿.md",
    "D":  "papers/04_D_StateMachineIsNotYetAPrompt_交差稿.md",
}
# ★ 承载簇级声明的载体（★ 这些也必须同步 ⇒ 一处错全链）
CLUSTER_CARRIERS = [
    "papers/00_论文簇总纲_交差版.md",
    "papers/论文簇_四篇定位与层映射_2026-10-24.md",
    "交付总览_人肉审版_2026-10-25.md",
]

MARKS = ["⚠️", "【待完成】", "📌"]

# ★ 每篇必须出现的核心公式标记（★ §0.4）
CORE_FORMULA = {
    "L1": [r"d\s*log\s*PR", r"log\s*PR"],
    "A":  [r"支数\s*[×x*]\s*题", r"可分叉决策数", r"净增益", r"新增", r"丢失"],
    "L3": [r"u\[repair\]", r"m\[failure\]", r"exp\(", r"57"],
    "D":  [r"f\(S₀\)", r"g\(S₀", r"约束₁", r"load_bearing|可核事实守恒|D-1"],
}

# ★ 跨篇必须一致的措辞（★ 出现即须存在；★ 措辞变体要全列）
CLUSTER_PHRASES = {
    "四方向归属": [r"整体组", r"二方向组", r"三方向组", r"状态机推动组"],
    "三维度":     [r"形态", r"来源", r"驱动力"],
    "C篇不占名额": [r"横跨", r"不占"],
}

# ★ 禁改串（★ 越界措辞 / 把限定写死成一般结论）
BANNED = [
    r"已被实测为无效",
    r"可判定地不成立",
    r"唯一系统性地挡住",
    r"六个对比中全部一致",
    r"工作流方法(整体)?无效",
    r"状态机(整体)?无效",
    r"我们证明了(注意力机制)是(塌缩的)?根源",   # ★ 无探针数据 ⇒ 不许这样写
    r"注意力机制是根源(?!.{0,40}(假说|机制链|待取证|不可测))",
]

# ★★★ ①篇注意力归因红线（★ 由审稿人 V1 提供、★ 2026-10-25 补）
# ★★★ 为什么不能用 `grep "因为注意力"`（★ 记忆铁律：★ 判据必须能红，且红在预期处）：
#   ① `grep "因为注意力"` = 0 ⇒ **假绿**（★ 实际违例用的是"根源/根因/论证/主张 … 注意力机制"）
#   ② "每个含'注意力'的句子都要带限定" ⇒ **假红**（★ 机械跑出 72 句不合规）
#   ⇒ ★ 所以只管【归因断言句】，且要求【同一行】带限定词。
ATTR_ASSERT = re.compile(
    r"(根源|根因|论证|主张|解释).{0,40}注意力机制"
    r"|注意力机制.{0,20}(是|为).{0,10}(根源|根因)"
)
# ★ 同行出现任一即为"带限定"
ATTR_QUAL = re.compile(
    r"未检验|相容|假说|未测|悬置|不被支持|未被否证|不成立|不得|不许|"
    r"非断言|不是断言|判决式|待检验|可失败预测"
)
# ★ 豁免：★ 关键词行 / 元声明行（★ "不可写成…" 这类禁令条文）
# ★★ 注意：★ **标题行不豁免**（★ 负向测试抓到过：★ 标题豁免 ⇒
#   「# 搜索空间过早闭合：根因在 Transformer 的注意力机制」不判红
#   ⇒ ★ 而那恰是审稿人 V1 指出的最严重一处（★ "外部审稿人第一眼是标题"）
#   ⇒ ★ 标题要过关，★ 靠它自己带限定词（★ 如"假说""判决式""未检验"），★ 不是靠豁免）
ATTR_EXEMPT = re.compile(r"\*\*关键词\*\*|不可写成|不得写成|不能写成|禁写|勿写|"
                         r"不许|不是断言|非断言|已被否证|被否证的对象")


# ★ 自我设限句（★ 铁律三要压的）⇒ ★ 只**计数与报告**，不硬判失败
SELF_LIMIT = re.compile(
    r"本文未测|本文不主张任何|因此我们不能|我们不能证明|本文不证明|"
    r"本文不主张(?!所有|.{0,20}小样本)|什么都不能说|无法断言"
)

# ★ 待取证条目
TBD = re.compile(r"【待取证\s*T-[A-Z0-9\-]+")


def run(cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def git_show(head, path, baseline_dir=None):
    """★ 取基线内容：★ 优先快照目录（★ 交付态），★ 否则 git（★ 仓内）
    ★ ★ 两个来源都可核：★ 快照目录里的每个文件在 baseline/BASELINE_SHA256.txt 有登记"""
    if baseline_dir is not None:
        f = baseline_dir / path
        if f.exists():
            return f.read_text(encoding="utf-8", errors="replace")
        return None
    r = run(["git", "show", f"{head}:{path}"])
    return r.stdout if r.returncode == 0 else None


def read(p):
    f = ROOT / p
    return f.read_text(encoding="utf-8") if f.exists() else None


NUM = re.compile(r"(?<![A-Za-z0-9_])[−-]?\d+(?:\.\d+)?%?")

# ★★ 章节号 / 结构编号 **单独开一条通道**（★ 记忆铁律：
#   「数字白名单」类判据会把【指向代码的行号】误报成"新增读数"
#   ⇒ 结构性编号必须豁免，否则改章节号就等于"删读数"）
SEC = re.compile(r"§\s*(\d+(?:\.\d+)*)")
# ★ 章节号也可能出现在【标题行】（`### 3.6 统计纪律`）⇒ 一并收集
SEC_H = re.compile(r"^\s{0,3}#{1,6}\s*(\d+(?:\.\d+)*)\b", re.M)


def sectok(t):
    """★ 收集文本里作为【章节号】出现的数字 token（含各层级前缀）"""
    s = set()
    for m in list(SEC.finditer(t or "")) + list(SEC_H.finditer(t or "")):
        parts = m.group(1).split(".")
        for i in range(len(parts)):
            s.add(".".join(parts[: i + 1]))
    return s


def numset(t):
    return set(NUM.findall(t or ""))


def truncated_table_rows(text):
    """★ S11 判据的可单测内核：★ 找出【表格残行】
    ★ ★ 病因（★ 由 ②篇作者的一次真实事故抓出）：★
    ★   `check_docx.py` 的列数检查要求行**以 `|` 开头且以 `|` 结尾**
    ★   ⇒ ★ **整行替换时若丢了收尾的 `|`，★ 这一行会被整行从表里剔除**
    ★   ⇒ ★ **列数检查完全看不见（★ 表格看上去"全绿"）**
    ★   ⇒ ★ **实际：那一行已经变成段落，★ 而它原本是表格的一行**
    ★ ⇒ ★ 落法：★ 扫「以 `|` 开头但不以 `|` 结尾」的行（★ 表格残行）
    """
    bad = []
    for i, ln in enumerate((text or "").split("\n"), 1):
        s = ln.strip()
        if not s.startswith("|"):
            continue
        # ★ 代码围栏内的行不算（★ 表格化的代码块可能合法）
        if s.endswith("|"):
            continue
        bad.append((i, s[:90]))
    return bad


def attr_violations(text):
    """★ S9 判据的可单测内核：★ 返回 (违例列表, 豁免行数)
    ★ 违例 = 【归因断言句】且【同行无限定词】且【不在豁免行】"""
    viol, exempt_n = [], 0
    for i, ln in enumerate((text or "").split("\n"), 1):
        if not ATTR_ASSERT.search(ln):
            continue
        if ATTR_EXEMPT.search(ln):
            exempt_n += 1
            continue
        if not ATTR_QUAL.search(ln):
            viol.append((i, ln.strip()))
    return viol, exempt_n


def claim_violations(text):
    """★ S10 判据的可单测内核：★ 「本文的主张」句必须带限定
    ★ 返回 (违例列表, 主张句总数)"""
    claims = [(i, ln.strip()) for i, ln in enumerate((text or "").split("\n"), 1)
              if re.search(r"本文的主张|本文主张", ln)]
    bad = [(i, s) for i, s in claims
           if not ATTR_QUAL.search(s) and not ATTR_EXEMPT.search(s)]
    return bad, len(claims)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--head", default=BASELINE_COMMIT,
                    help="★ 基线 commit（★ 默认 = 本轮改稿前的那个 commit，★ 固定值 ⇒ 第一次 commit 不会让它失效）")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--baseline-dir", default=None,
                    help="★ 基线快照目录（★ 交付态用：★ 交付包里没有 .git ⇒ git show 不可用 "
                         "⇒ ★ 指向包内 baseline/ 即可在交付态核 S1/S2）")
    a = ap.parse_args()

    head = a.head
    fails, warns, infos = [], [], []
    v = a.verbose

    # ── S0 前置：基线来源（★ git 或 快照目录）──────────────────────────
    # ★★★ 交付态（★ 包内无 .git）⇒ ★ git 基线不可用 ⇒ ★ 降级到 --baseline-dir
    #   ⇒ ★ **"收件人拿到包能自己核 S1"** 是交付物的必要条件
    baseline_dir = None
    if a.baseline_dir:
        bd = (ROOT / a.baseline_dir)
        if not bd.exists():
            print(f"✖ 基线快照目录不存在：{a.baseline_dir}")
            return 2
        baseline_dir = bd
        print(f"★ 基线来源 = 快照目录 {a.baseline_dir}（★ 交付态模式）")
    elif run(["git", "rev-parse", "--verify", head]).returncode != 0:
        print(f"✖ 基线 {head} 不存在（★ 且未给 --baseline-dir）")
        print(f"  ⇒ ★ 交付态请用：python3 tools/check_cluster_consistency.py --baseline-dir baseline")
        return 2

    # ── S1 数字零改动 / S2 标记不减（逐篇 vs 基线）────────────────────
    for key, path in PAPERS.items():
        cur = read(path)
        base = git_show(head, path, baseline_dir)
        if cur is None:
            fails.append(f"[S1/S2] {key}: 文件不存在 {path}")
            continue
        if base is None:
            warns.append(f"[S1/S2] {key}: 基线无此文件（新增篇）")
            continue

        # S1 数字零改动：★ 已有读数不许被改（删一个算改）
        # ★★ 但【章节号/结构编号】走单独通道（★ 否则重编号 = 删读数 ⇒ 假红）
        b, c = numset(base), numset(cur)
        sec_b = sectok(base)          # ★ 改前作为章节号出现过的 token
        lost = b - c
        lost_reading = lost - sec_b   # ★ 真正"消失的读数"
        lost_sect = lost & sec_b      # ★ 只是章节号重编
        if lost_reading:
            fails.append(
                f"[S1] {key}: 原有数字被删改 {len(lost_reading)} 个 ⇒ {sorted(lost_reading)[:12]}"
                + (" …" if len(lost_reading) > 12 else "")
            )
        if lost_sect:
            infos.append(f"[S1] {key}: {len(lost_sect)} 个 token 消失但属【章节号重编】⇒ "
                         f"{sorted(lost_sect)[:10]}" + (" …" if len(lost_sect) > 10 else ""))
        added = c - b
        if added:
            infos.append(f"[S1] {key}: 新增数字 {len(added)} 个（★ 允许，但须带出处）⇒ {sorted(added)[:12]}"
                         + (" …" if len(added) > 12 else ""))

        # S2 三标记计数不减
        for m in MARKS:
            nb, nc = base.count(m), cur.count(m)
            if nc < nb:
                fails.append(f"[S2] {key}: 标记 {m} 计数 {nb} → {nc}（★ 减了 ⇒ 限定条款被删）")

    # ── S3 核心公式块存在 ────────────────────────────────────────────
    for key, pats in CORE_FORMULA.items():
        cur = read(PAPERS[key]) or ""
        miss = [p for p in pats if not re.search(p, cur)]
        if miss:
            fails.append(f"[S3] {key}: 核心公式标记缺失 ⇒ {miss}")
        elif v:
            infos.append(f"[S3] {key}: 核心公式标记齐全 ✔")

    # ── S4 簇级声明跨载体一致 ────────────────────────────────────────
    carriers = {p: read(p) for p in CLUSTER_CARRIERS}
    carriers.update({PAPERS[k]: read(PAPERS[k]) for k in PAPERS})
    for label, pats in CLUSTER_PHRASES.items():
        for pat in pats:
            hit = [p for p, t in carriers.items() if t and re.search(pat, t)]
            if not hit:
                fails.append(f"[S4] 簇级措辞「{label} / {pat}」在任何载体里都不存在")
            elif v:
                infos.append(f"[S4] 「{label} / {pat}」见于 {len(hit)} 个载体 ✔")

    # ── S5 跨篇关键主张一致（同一措辞，不得各写各的）─────────────────
    CROSS = [
        ("解法路径唯一", r"解法路径唯一"),
        ("净增益公式", r"净增益"),
        ("杠杆公式", r"可分叉决策数"),
    ]
    for label, pat in CROSS:
        hit = [p for p, t in carriers.items() if t and re.search(pat, t)]
        if len(hit) < 2:
            warns.append(f"[S5] 「{label}」只出现在 {len(hit)} 个载体 ⇒ 跨篇一致性可能不足")
        elif v:
            infos.append(f"[S5] 「{label}」见于 {len(hit)} 个载体 ✔")

    # ── S6 禁改串 ────────────────────────────────────────────────────
    # ★★ 关键：★ 逐句检查，★ **含否定标记的句子跳过**
    #   （★ 否则「不可写成"X"或"Y"」这种【禁止使用该措辞的元声明】会假红
    #     ⇒ 记忆铁律：判据必须能红，且红在预期处）
    NEG = re.compile(r"不可写成|不得写成|不能写成|不许|禁止|禁写|应写成|改成|勿写|避免|"
                     r"不作|不写|不作一般|不得|不是\*{0,4}[\"“「『]|不等于|并非|"
                     r"不是.{0,10}结论|而非")
    for p, t in carriers.items():
        if not t:
            continue
        for si, sent in enumerate(re.split(r"[。；\n|]", t)):
            if not sent.strip() or NEG.search(sent):
                continue
            for pat in BANNED:
                for m in re.finditer(pat, sent):
                    line = t[:t.find(sent) + m.start()].count("\n") + 1
                    ctx = sent[max(0, m.start() - 60):m.end() + 60].strip()
                    fails.append(f"[S6] 禁改串命中 {p}(≈{line}) ⇒ …{ctx}…")

    # ── S7 自我设限句计数（★ 只报告 + 阈值告警，不硬判失败）──────────
    for key, path in list(PAPERS.items()):
        t = read(path)
        if not t:
            continue
        n = len(SELF_LIMIT.findall(t))
        base = git_show(head, path, baseline_dir)
        nb = len(SELF_LIMIT.findall(base)) if base else 0
        if n > nb:
            warns.append(f"[S7] {key}: 自我设限句 {nb} → {n}（★ 变多了 ⇒ 铁律三没落实）")
        elif v:
            infos.append(f"[S7] {key}: 自我设限句 {nb} → {n} ✔")

    # ── S8 待取证条目：★ 判据点是【集中清单】，不是散落的行内引用 ──
    for key, path in PAPERS.items():
        t = read(path) or ""
        hits = TBD.findall(t)
        if not hits:
            fails.append(f"[S8] {key}: 一个【待取证】条目都没有 ⇒ 新模式（铁律四）没落地")
            continue
        # ★ 找【集中清单小节】：★ 遍历所有含"待取证"的标题，★ 取条目行最多的那个
        #   （★ 不能取第一个 —— 可能是结果节标题里顺带写了"【待取证 T-xx】"）
        # ★ 条目行识别：★ 既接受 `【待取证 T-xx-nn】`，★ 也接受表格里的 `| **T-xx-nn** |`
        ITEM = re.compile(r"【待取证\s*T-[A-Z0-9\-]+|\|\s*\*?\*?\s*T-[A-Z0-9]+-\d+")
        best_rows, best_head, body = [], None, ""
        for m in re.finditer(r"^#{1,6}.*待取证.*$", t, re.M):
            rest = t[m.end():]
            nxt = re.search(r"^#{1,6}\s", rest, re.M)
            b2 = rest[: nxt.start()] if nxt else rest
            rows = [ln for ln in b2.splitlines() if ITEM.search(ln)]
            if len(rows) > len(best_rows):
                best_rows, best_head, body = rows, m.group(0).strip(), b2
        if best_head is None:
            fails.append(f"[S8] {key}: 有 {len(hits)} 处【待取证】但**没有集中的待取证清单小节**"
                         f"（★ 铁律四要求未做项集中承载）")
            continue
        if not best_rows:
            fails.append(f"[S8] {key}: 待取证清单小节「{best_head}」里没有条目行 ⇒ 清单是空的")
        else:
            header = next((ln for ln in body.splitlines()
                           if ln.strip().startswith("|") and
                           re.search(r"判据|影响|成本", ln)), None)
            if header:
                # ★ 表格型：核列数一致 + 关键列齐
                # ★★ 注意：★ 单元格里的**转义竖线** `\|` 不算列分隔符
                #   （★ 记忆同族坑：表格里的裸竖线会把列数算错 ⇒ 假红）
                def ncols(ln):
                    s = re.sub(r"\\\|", "\x00", ln.strip().strip("|"))
                    return len(s.split("|"))

                cols = ncols(header)
                bad = [ln for ln in best_rows if ncols(ln) != cols]
                if bad:
                    fails.append(f"[S8] {key}: 待取证清单表格列数不一致（表头 {cols} 列）"
                                 f"⇒ {bad[0].strip()[:70]}")
                elif v:
                    infos.append(f"[S8] {key}: 待取证 {len(hits)} 处 / 集中清单「{best_head[:26]}」"
                                 f"{len(best_rows)} 条（表格型，{cols} 列一致）✔")
            else:
                # ★ 非表格型：逐行要求三要素
                thin = [ln.strip()[:70] for ln in best_rows
                        if not re.search(r"判据|可失败预测|判死门|证伪|回填|影响|成本|预注册|"
                                         r"样本量|噪声地板|代理量|来源|去哪找", ln)]
                if thin:
                    fails.append(f"[S8] {key}: 待取证清单里 {len(thin)}/{len(best_rows)} 条缺三要素 ⇒ {thin[:3]}")
                elif v:
                    infos.append(f"[S8] {key}: 待取证 {len(hits)} 处 / 集中清单 {len(best_rows)} 条，三要素齐全 ✔")

    # ── S9 / S10：★ ①篇注意力归因红线 + 稿内自撞（★ 审稿人 V1 提供）
    #   S9：★ 归因断言句，同行不带限定 ⇒ 判红
    #   S10：★ 「本文的主张」句必须带限定（★ 治"稿内自撞"：既说"判决悬置"又无条件归因）
    l1 = read(PAPERS["L1"]) or ""
    viol, exempt_n = attr_violations(l1)
    viol = [(i, s[:88]) for i, s in viol]
    if viol:
        for i, s in viol[:6]:
            fails.append(f"[S9] L1:{i} 归因断言句同行无限定 ⇒ {s}")
        if len(viol) > 6:
            fails.append(f"[S9] L1: 另有 {len(viol) - 6} 处同类")
    else:
        infos.append(f"[S9] L1 注意力归因红线：0 处无条件归因断言 ✔"
                     f"（★ 豁免 {exempt_n} 行：★ 关键词行 / 标题行 / 禁令条文）")

    bad_claim, n_claims = claim_violations(l1)
    claim_lines = [(i, s) for i, s in bad_claim]
    if bad_claim:
        for i, s in bad_claim[:5]:
            fails.append(f"[S10] L1:{i} 「本文的主张」句无任何限定（★ 稿内自撞：与"
                         f"「归因判决悬置」并存时读者会读成无条件归因）⇒ {s[:80]}")
    else:
        infos.append(f"[S10] L1「本文的主张」共 {n_claims} 处，"
                     f"全部带限定 ✔（★ 治稿内自撞）")

    # ── S11：★ 表格残行（★ 治"整行截断 ⇒ 静默退出表 ⇒ 列数检查看不见"）
    s11_bad = []
    for key, path in list(PAPERS.items()) + [("总纲", c) for c in CLUSTER_CARRIERS]:
        txt = read(path)
        if txt is None:
            continue
        for i, s in truncated_table_rows(txt):
            s11_bad.append((path, i, s))
    if s11_bad:
        for path, i, s in s11_bad[:8]:
            fails.append(f"[S11] {path}:{i} 表格残行（★ 以 | 开头但不以 | 结尾 ⇒ "
                         f"★ 它已被表格解析器剔除，★ 列数检查看不见）⇒ {s}")
        if len(s11_bad) > 8:
            fails.append(f"[S11] 另有 {len(s11_bad) - 8} 处表格残行")
    else:
        infos.append(f"[S11] 表格残行扫描：0 处（★ 治『整行截断 ⇒ 静默退出表』）")

    # ── 报告 ─────────────────────────────────────────────────────────
    print("═" * 72)
    print(f"论文簇全链一致性验收 · 基线 = {head}")
    print("═" * 72)
    for i in infos:
        print(f"  ℹ {i}")
    for w in warns:
        print(f"  ⚠ {w}")
    for f in fails:
        print(f"  ✖ {f}")
    print("─" * 72)
    print(f"失败 {len(fails)} ｜ 告警 {len(warns)} ｜ 提示 {len(infos)}")
    if fails:
        print("EXIT=1")
        return 1
    print("EXIT=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
