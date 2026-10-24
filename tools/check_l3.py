#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""层3 篇自检：A1（禁写清单 21 条）/ A3（数字 ⊆ 台账 ∪ 底稿）/ A4（档位+n）/ A5 / A7 / A10 / A11
用法: python3 check_l3.py <paper.md>"""
import io, os, re, sys, json

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # ★ 改成相对本文件 ⇒ 可随包复跑
DRAFT = os.path.join(REPO, "来源与底稿/第三组_治塌缩层3")
SPEC = os.path.join(REPO, "改稿规格_方向3_层3_2026-10-24.md")
PAPER = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "papers/06_L3_层3自修改_交差稿.md")
md = io.open(PAPER, encoding="utf-8").read()
lines = md.split("\n")
ok = True
def hdr(t): print("\n" + "=" * 78 + "\n" + t + "\n" + "=" * 78)

# ---------- 允许数字集合：台账 ∪ 底稿全文 ∪ 规格全文 ----------
allowed = set()
def harvest(txt):
    for m in re.finditer(r"\d+(?:\.\d+)?", txt):
        allowed.add(m.group(0))
for root, _d, files in os.walk(DRAFT):
    for f in files:
        p = os.path.join(root, f)
        try: harvest(io.open(p, encoding="utf-8", errors="ignore").read())
        except Exception: pass
harvest(io.open(SPEC, encoding="utf-8").read())
harvest(io.open(os.path.join(REPO, "papers/审稿回执_方向3层3_规格审计_2026-10-24.md"), encoding="utf-8").read())

# ---------- A1 ----------
hdr("A1 · 禁写清单 21 条（逐条 grep + 正例句）")
FORBID = [
 ("①", "层3 优于层2",            [r"层3\s*优于层2"]),
 ("②", "自迭代有效",              [r"自迭代有效"]),
 ("③", "训练让架构更优",          [r"训练让架构更优"]),
 ("⑪", "层3 无效",                [r"层3\s*无效"]),
 ("⑪b","不如层2",                 [r"不如层2"]),
 ("⑪c","自迭代无效",              [r"自迭代无效"]),
 ("⑪d","训练没用",                [r"训练没用"]),
 ("⑪e","与层2 等效",              [r"与层2\s*等效"]),
 ("⑬", "架构由训练产生",          [r"架构由训练产生"]),
 ("⑬b","自动的 Agent 架构搜索",    [r"自动的 ?Agent ?架构搜索"]),
 ("⑭", "策略学会了少发散",        [r"策略学会了少发散"]),
 ("⑭b","偏好 nf=1",              [r"偏好\s*nf=1"]),
 ("⑳", "层3 学到了 resolve",      [r"层3\s*学到了\s*resolve"]),
 ("⑳b","按证据裁决",              [r"按证据裁决"]),
 ("⑳c","有依据支持的一方胜",      [r"有依据支持的一方胜"]),
 ("㉑", "层2 把『该不该发散』写死了",[r"层2\s*把.{0,12}该不该发散.{0,6}写死"]),
]
a1_hits = []
for tag, name, pats in FORBID:
    hits = []
    for i, l in enumerate(lines, 1):
        for p in pats:
            if re.search(p, l):
                hits.append((i, l.strip()[:110]))
    a1_hits += [(tag, name, h) for h in hits]
    print("  %-4s %-26s 命中 %d %s" % (tag, name, len(hits), "✅" if not hits else "❌"))
    for i, t in hits[:3]:
        print("        L%-5d %s" % (i, t))
print("  ⇒ A1 逐条 grep 合计命中：%d" % len(a1_hits))
if a1_hits: ok = False

# ④ +0.75/-1.00 必须与"独立批次"同行
bad = [(i,l) for i,l in enumerate(lines,1)
       if ("+0.75" in l or "−1.00" in l or "-1.00" in l) and "独立批次" not in l]
print("  ④  +0.75/−1.00 同行缺「独立批次」：%d %s" % (len(bad), "✅" if not bad else "❌"))
for i,l in bad[:3]: print("        L%-5d %s" % (i, l.strip()[:110]))
if bad: ok = False

# ⑫ 层2 读数不得写成层3 效果：含 4.50/2.50/80–100%/路径间 Sim 的行必须含"层2"
L2READ = re.compile(r"4\.50|2\.50|80–100%|0\.461|0\.123|0\.119")
bad = [(i,l) for i,l in enumerate(lines,1) if L2READ.search(l) and "层2" not in l]
print("  ⑫  层2 读数行缺「层2」归属：%d %s" % (len(bad), "✅" if not bad else "❌"))
for i,l in bad[:6]: print("        L%-5d %s" % (i, l.strip()[:110]))
if bad: ok = False

# ⑤ holdout 读数
# ⑤-a 留出批的【效果读数】一律不得出现（任何 /8、/7 的分母，除台账第 21 行明列的 4/8、5/7、3/7 三个"未完成"分母外）
HOLD_EFFECT = re.compile(r"(?<![0-9])(?:[0-9]/8|[0-9]/7)(?![0-9])")
SANCTIONED = {"4/8", "5/7", "3/7"}
SANCTIONED |= {"7/7", "13/13"}   # 底稿自检计数（自检 13/13 + 变异注入 7/7），非留出批分母
bad = []
for i,l in enumerate(lines,1):
    for m in HOLD_EFFECT.finditer(l):
        if m.group(0) in SANCTIONED: continue
        bad.append((i,l)); break
# ⑤-b 明列的三个分母必须带"未完成/跑批中/不可比/in-progress/分母不等"
NEED_CTX = {"4/8", "5/7", "3/7"}   # ★ 只有台账第 21 行明列的三个"未完成"分母需要带不可比/未完成 声明
for i,l in enumerate(lines,1):
    if any(x in l for x in NEED_CTX):
        if not re.search(r"未完成|跑批中|不可比|in-progress|分母不等|完成度", l):
            bad.append((i,l))
print("  ⑤  引用 holdout 部分读数：%d %s" % (len(bad), "✅" if not bad else "❌"))
for i,l in bad[:4]: print("        L%-5d %s" % (i, l.strip()[:110]))
if bad: ok = False

# ⑥⑦⑯ 必须保留
for tag, phrase in [("⑥", "标量档案规模"), ("⑥b", "是定义，不是发现"), ("⑦", "查表式演化"),
                     ("⑯a", "L3-04"), ("⑯b", "L3-05"), ("⑯c", "24/24"),
                     ("⑮", "在【局部避坑行为】这一轴上成立"), ("⑩", "人画的 36 格网格")]:
    n = md.count(phrase)
    print("  %-4s 必须保留「%s」 出现 %d 次 %s" % (tag, phrase, n, "✅" if n else "❌"))
    if not n: ok = False

# ⑰ 不得给 P1/P3 下判决
p13 = [(i,l) for i,l in enumerate(lines,1) if re.search(r"\bP1\b|\bP3\b", l)]
print("  ⑰  正文出现 P1／P3 token：%d %s" % (len(p13), "✅" if not p13 else "❌"))
for i,l in p13[:4]: print("        L%-5d %s" % (i, l.strip()[:110]))
if p13: ok = False

# ⑨ 零判官 不得用于依赖判官的指标
bad = [(i,l) for i,l in enumerate(lines,1)
       if "零判官" in l and re.search(r"承重维度|维度数|判官读数(?!.{0,12}不)", l)]
print("  ⑨  「零判官」与判官依赖指标同行：%d %s" % (len(bad), "✅" if not bad else "❌"))
for i,l in bad[:6]: print("        L%-5d %s" % (i, l.strip()[:120]))
if bad: ok = False

# ⑧ in-sample 标签
for num, phrase in [("2/6", "2/6"), ("0.127", "0.127")]:
    bad = []
    for i,l in enumerate(lines,1):
        if phrase not in l: continue
        if "in-sample" in l or "in-progress" in l: continue
        ctx = "\n".join(lines[max(0,i-12):i])  # 回看 12 行（含小节标题与表题）
        if "in-sample" in ctx: continue
        bad.append((i,l))
    print("  ⑧  含「%s」且同行无 in-sample 的行：%d" % (num, len(bad)))
    for i,l in bad[:5]: print("        L%-5d %s" % (i, l.strip()[:110]))

# ---------- A3 ----------
hdr("A3 · 无新增数字（正文数字 ⊆ 台账 ∪ 底稿 ∪ 规格）")
# ★ 结构性小节编号（本篇自己的 §N.M 号，非读数）—— 与改稿报告_D 的 S1 判据同款
STRUCT = set()
for m in re.finditer(r"§(\d+(?:\.\d+)?)", md):
    STRUCT.add(m.group(1))
for m in re.finditer(r"^#{2,4} (\d+(?:\.\d+)?)", md, re.M):
    STRUCT.add(m.group(1))
allowed |= STRUCT
# ★★★ 行号通道（2026-10-25 · owner 依独立终审的提醒补）：
#   「数字白名单」类判据对【指向代码的行号】有天然盲区 ⇒ 代码引用形如 `file.py:123` / `file.py:123-124`
#   ⇒ 其中的数字是【行号】、不是读数 ⇒ ⇒ ★ 但**不能一律豁免**（那会把真读数也放过去）
#   ⇒ ⇒ ★ 只对「文件名 + 冒号 + 数字」这一种形态开通道，并把这些行号**单独打印**供「回源核对」逐条验。
LINEREF = set()
for m in re.finditer(r"[\w./-]+\.(?:py|sh|md|json|txt):(\d+)(?:-(\d+))?", md):
    for g in m.groups():
        if g: LINEREF.add(g)
nums = sorted({m.group(0) for m in re.finditer(r"\d+(?:\.\d+)?", md)})
bad = [n for n in nums if n not in allowed and n not in LINEREF]
hit_ln = sorted(LINEREF & set(nums), key=lambda x: int(x))
print("  （结构性小节编号 %d 个已按同款判据豁免：%s）" % (len(STRUCT), sorted(STRUCT)[:14]))
print("  ★ 行号通道（指向代码的行号，**非读数**；须逐条回源核对）：%s" % (hit_ln or "无"))
print("  正文不同数字 %d 个；不在允许集合的 %d 个 %s" % (len(nums), len(bad), "✅" if not bad else "❌"))
if bad:
    for n in bad: print("        ✘ %s" % n)
    ok = False

# ---------- A4 / A5 / A7 / A10 / A11 / A8 ----------
hdr("A4/A5/A7/A8/A10/A11 · 结构判据")
def chk(name, cond, extra=""):
    global ok
    print("  %-46s %s %s" % (name, "✅" if cond else "❌", extra))
    if not cond: ok = False
chk("A4  档位标记 ✅/◐/【待完成】/in-sample 齐备",
    all(x in md for x in ["✅", "◐", "【待完成】", "in-sample"]))
# ★★★ A5 改成判【表结构】而不是判【旧措辞】（★ 教训见下）
#   ★ 原判据要求「偏好只覆盖部分维度」这个措辞 ⇒ ★ 重写稿把那个轴改成了
#     「机制存在性轴（偏好覆盖度）」⇒ ★ 措辞判据假红
#   ★ 而且轴从四条变成六条 ⇒ ★ **「四轴」这个前提本身已过时**
#   ⇒ ★ **落法：★ 判「按轴分写的判决表存在，★ 且每行都有 结论/依据/限定 三列」**
#     ⇒ ★ 措辞随便改都不影响它，★ 而"某一行缺依据"这种真问题照样抓
_ax_tbl = None
# ★★★ 换行必须显式（★ 上一版 `.*$` 贪婪 ⇒ 把整行吃掉 ⇒ 捕获长度 0 ⇒ 轴数 0）
_m = re.search(r"^#{2,4}[^\n]*按轴分写[^\n]*$\n(.*?)(?=^#{2,4} |\Z)", md, re.M | re.S)
if _m:
    _rows = [ln for ln in _m.group(1).split("\n")
             if ln.strip().startswith("|") and ln.strip().endswith("|")
             and not re.match(r"^\s*\|[-: |]+\|\s*$", ln)]
    _hdr = next((ln for ln in _rows if "轴" in ln and "结论" in ln), None)
    _body = [ln for ln in _rows if _hdr and ln is not _hdr and "轴" in ln]
    _ax_tbl = (_hdr, _body)
chk("A5  按轴分写的判决表存在，★ 每行都有 结论/依据/限定 三列",
    _ax_tbl is not None
    and _ax_tbl[0] is not None
    and len(_ax_tbl[1]) >= 4
    and all(("不可分辨" in r or "未检出" in r or "成立" in r or "未测" in r) for r in _ax_tbl[1])
    and all(("n=" in r or "样本" in r or "臂" in r or "题" in r) for r in _ax_tbl[1]),
    extra=f"★ 轴数 {len(_ax_tbl[1]) if _ax_tbl else 0}")
chk("A5c 关键轴名与共线判据在位（★ 措辞可有变体）",
    all(x in md for x in ["架构级轴", "局部避坑行为", "机制存在性轴", "共线"]))
chk("A5b 避坑轴带 in-sample + n=6 + 负对照持平",
    "每臂 n=6" in md and "负对照臂" in md and "in-sample" in md)
chk("A6  P2 与 P4 判据逐字照抄",
    "VD_net(W_train_L3 − W_design_L2) > 0" in md and "Spearman ρ" in md
    and "自修改未显示增量" in md and "代理奖励未迁移" in md)
chk("A7a 推断链—证伪条件表 六列",
    "| # | 从（读数）| 到（构念解释）| 该箭头的**独立**证伪条件 | 当前状态 | 还缺什么 |" in md)
chk("A7b 数据来源与独立性声明 七列",
    "① 原始实验及其日期" in md and "⑥ 与其他篇的共享部分" in md)
# ★★★ 按【标题文本】匹配，★ 不写死节号与分隔符
#   （★ 教训：★ ③篇重编号后 `## 13. 未来工作` → `## 12 · 未来工作` ⇒ ★ 写死节号的判据必假红
#    ⇒ ★ **判据要判【内容在不在】，★ 不该判【它在第几节】**）
chk("A8  未来工作标题 + 六列表头",
    re.search(r"^#{2,4}\s*[\d.]*\s*[·.、]?\s*未来工作（不属于本文证据）", md, re.M) is not None
    and "| # | 事项 | 状态 | 是否影响本文核心结论 | 成本 | 承载位置 |" in md)
chk("A8b 未来工作前奏三件（状态列图例/编号说明/列语义）",
    "状态列图例" in md and "编号说明" in md and "是否影响本文核心结论" in md)
chk("A9  判决表（主张/支持度/依据/还缺什么）",
    "| 主张 | 支持度 | 依据（✅ 实测，全部带 n）| 还缺什么 |" in md)
chk("A10 局限重编号 L3-01… 且含 L3-01/02/04/05/06/07",
    all(("%s |" % x) in md or ("| **%s** |" % x) in md for x in ["L3-01","L3-02","L3-04","L3-05","L3-06","L3-07"]))
chk("A10b 不与 L1 篇的 L3/L8 撞号（本篇不再用裸 L3/L8 作局限号）",
    not re.search(r"^\|\s*L3\s*\|", md, re.M) and not re.search(r"^\|\s*L8\s*\|", md, re.M))
chk("A11 附录 A 无扁平化前路径 routes/",
    "routes/" not in md and "routes/COLLAPSE" not in md)
chk("A11b 附录 A 标出不在包内的组件",
    "不在包内" in md and "第三方不可复算" in md)
chk("A12 《读数口径变更记录》小节存在",
    re.search(r"^#{2,4}\s*[\d.]*\s*[·.、]?\s*读数口径变更记录", md, re.M) is not None)
chk("A16 三条代码级事实 + 复现命令与真实输出",
    "tools/verify_l3_code_facts.py" in md and "EXIT=0" in md and "全部 6 条断言成立" in md)
chk("§12 含 L3-26 条局限", md.count("| L3-") >= 20)
chk("无 U+FFFD", "\ufffd" not in md)

hdr("A2 · 限定条款计数（⚠️/【待完成】/📌）")
for m in ["⚠️", "【待完成】", "📌"]:
    print("  %-8s %d 次" % (m, md.count(m)))

print("\n" + "=" * 78)
print("★ 总体：%s" % ("✅ 全部通过" if ok else "❌ 有未通过项"))
print("=" * 78)
sys.exit(0 if ok else 1)
