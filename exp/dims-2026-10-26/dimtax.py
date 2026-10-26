# -*- coding: utf-8 -*-
"""dimtax.py —— 「有效维度」的操作定义与候选维度表

★ 判据来源：★ 用户给的样例题（湖北物理类620分·选校）★★
★ 核心定义：★
★   有效维度 = 仍留在【问题域】内、且可落地为外部可核验实体的【正交切分】
★   无效维度 = 【跨域】分支（★ 哪怕它本身正确、★ 且明显有吸引力 ★）
★   跨域测试：★ 把该条单独抽出来 ⇒ 它【回答的还是原问题吗】？★★
★   有效 ⇒ 它在给出【选校】的切分维度；★ 无效 ⇒ 它在回答另一个问题（如"去哪就业"）★★
"""
import re

# ---- 候选维度表（★ 判据的分母 ★）★ 建议由人工核定 ★
# ★ ★★ 纪律：★ 【题面词】不许进维度关键词表 ★★
#   题面词 = 题干里【必然出现】的词（★ 本题：湖北/物理类/620分/AI/大学 ★）
#   它们出现在每个答案里 ⇒ 判据会命中【题面】而不是【维度主张】⇒
#   ⇒ 【系统性】把首维判错（★ 实测 5/5 全错 ★）⇒ 而肉眼看全是 D1 ★★
QUESTION_WORDS = ["湖北", "物理类", "620", "人工智能", "AI", "大学", "选择", "怎么"]

CANDIDATE_DIMS = [
    ("D1", "院校体系层次", "985/211/双一流",
     ["985", "211", "双一流", "重点大学", "一本", "工科强校", "强势院校", "强校"]),
    ("D2", "新型科研型院校", "南科大/西湖/上科大/诺顿/国科大",
     ["南方科技大学", "西湖大学", "上海科技大学", "宁波诺顿",
      "中国科学院大学", "深圳理工大学", "北京师范大学-香港浸会",
      "新型科研", "新型本科", "小而精"]),
    ("D3", "境外与港澳高校", "港校/澳校/海外",
     ["香港大学", "香港中文", "香港科技", "香港理工", "香港城市",
      "香港浸会", "岭南大学", "香港教育", "香港都会", "香港开放",
      "澳门大学", "澳门科技", "澳门理工", "澳门城市", "香港",
      "澳门", "港校", "赴港", "留学", "海外"]),
    ("D4", "AI学科与专业实力", "学科评估/专业排名/选专业",
     ["学科评估", "第五轮学科评估", "A类学科", "计算机学科", "人工智能专业",
      "专业排名", "CS排名", "AI强校", "学科实力", "王牌专业", "双一流学科",
      "选专业", "专业方向", "专业实力", "开设人工智能", "AI专业",
      "等专业", "计算机、人工智能"]),
    # ★ 「湖北省」「物理类」「620分」是【题面词】、★ 不是维度主张 ★
    #   ⇒ 留在表里 ⇒ 判据会命中【题面】⇒ 【系统性】把首维判成 D5（位次）★★
    ("D5", "分数位次与录取策略", "一分一段/冲稳保/录取线",
     ["位次", "一分一段", "冲稳保", "冲刺", "稳妥", "保底", "服从调剂",
      "录取线", "投档线", "能上", "压线", "分数段", "位次表", "等效分"]),
    ("D6", "城市与AI产业生态", "杭州/深圳/上海/北京的产业密度",
     ["科技企业", "互联网企业", "产业集群", "研发中心", "所在城市",
      "城市资源", "城市产业", "实习机会", "创业氛围", "算力", "人才集聚"]),
    ("D7", "费用与性价比", "学费/生活成本/性价比",
     ["学费", "生活费", "性价比", "成本", "奖助学金", "公办", "民办",
      "昂贵", "便宜"]),
    ("D8", "培养模式与升学路径", "书院制/拔尖/本硕连读/保研率",
     ["书院", "拔尖", "本硕", "直博", "保研", "升学", "培养模式",
      "导师", "科研训练", "转段"]),
    ("D9", "国际化与出口", "交换/暑校/海外合作/签证",
     ["交换", "暑校", "国际", "海外合作", "双学位", "英语"]),
    ("D10", "就业出口结构", "★ 作为【评估维度】的就业去向（★ 不是目标 ★）",
     ["就业率", "去向", "毕业去向", "深造率", "起薪", "雇主"]),
]

# ---- 跨域词（★ 作为【目标】出现 ⇒ 无效维度 ★）★ 需人工复核 ★
OFFDOMAIN = [
    ("去大厂", ["进大厂", "去大厂", "进大厂工作", "拿大厂offer"]),
    ("进华为/字节等", ["进华为", "进字节", "进腾讯", "进阿里", "进京东",
                       "进美团", "进小米", "进百度"]),
    ("考研就业二选一", ["考研还是工作", "直接工作还是", "先工作"]),
]

_DIM_PAT = {c: [re.compile(re.escape(k)) for k in keys]
            for c, _n, _d, keys in CANDIDATE_DIMS}


def find_dims(text):
    """★ 返回 (首次出现顺序的维度代码列表, 各维度最早字符位置) ★"""
    hits = {}
    for code, pats in _DIM_PAT.items():
        pos = -1
        for p in pats:
            m = p.search(text)
            if m and (pos < 0 or m.start() < pos):
                pos = m.start()
        if pos >= 0:
            hits[code] = pos
    order = [c for c, _ in sorted(hits.items(), key=lambda kv: kv[1])]
    return order, hits


def first_dim(text):
    order, _ = find_dims(text)
    return order[0] if order else None


def mentioned(text):
    order, _ = find_dims(text)
    return order


def offdomain_hits(text):
    out = []
    for name, pats in OFFDOMAIN:
        for p in pats:
            if p in text:
                out.append(name)
                break
    return out


def entities(text):
    """★ ★ 库驱动抽实体（★ 正则抽实体已被实测证伪：★ 非贪婪会吞掉修饰语 ★）★★

    ★ 返回 (真实校名集合, 库外嫌疑片段列表) ★
    """
    import schools
    hit, seen = set(), set()
    for name in schools.KNOWN_CANON:
        if name and name in text:
            hit.add(name)
    susp = []
    import re as _re
    for m in _re.finditer(r"([\u4e00-\u9fa5A-Za-z0-9·]{2,12}?)(大学|学院)", text):
        frag = m.group(0)
        for name in sorted(schools.KNOWN_CANON, key=len, reverse=True):
            if name in frag:
                frag = frag.replace(name, "")
        frag = _re.sub(r"[\u4e00-\u9fa5]{0,4}(可以|考虑|推荐|选择|建议|包括|比如|例如|以及|还有|优先|首选|就读|报考|也|就|该|所|的|和|与|在|去|报|以|这类|各|多|上|中|里)+", "", frag)
        frag = frag.strip()
        if len(frag) >= 4 and frag not in seen and frag not in susp:
            seen.add(frag)
            susp.append(frag)
    return sorted(hit), susp


# ---- 首维双口径（★ 全文最早出现【已被实测证伪】★）----------------------
# ★ 教训：★ LLM 普遍「先说结论」⇒ 小节标题「一、先看位次」会出现在结论里的「985」之后
#   ⇒ 用【全文最早出现】判首维 ⇒ 3/3 全判成 D5（位次）⇒ 而肉眼 3/3 都是 D1（985/211）
#   ⇒ 这是【系统性】判据错误、★ 不是个别样本问题 ★
# ★ 落法：★ 两个独立口径同时报、★ 报告分歧率、★ 两者一致才敢引用

HEAD_N = 400      # ★ 口径A：结论先行的窗口长度（★ 字符 ★）
_SEC = re.compile(r"^\s*(?:#{1,4}\s*)?(?:\*\*)?\s*(?:[一二三四五六七八九十]+[、．.]|\d+[.、])[^\n]{0,80}",
                  re.M)


def first_dim_head(text, n=HEAD_N):
    """★ 口径A：★ 开头 n 字符内最早出现的维度（★ 结论先行口径 ★）"""
    return first_dim(text[:n])


def first_dim_section(text):
    """★ 口径B：★ 第一个【小节标题】内出现的维度（★ 结构口径 ★）"""
    m = _SEC.search(text)
    if not m:
        return None
    head = m.group(0)
    pos = []
    for code, pats in _DIM_PAT.items():
        for p in pats:
            mm = p.search(head)
            if mm:
                pos.append((mm.start(), code))
                break
    if not pos:
        return None
    return sorted(pos)[0][1]


def first_dims(text):
    """★ 返回 (口径A, 口径B, 是否一致) ★"""
    a = first_dim_head(text)
    b = first_dim_section(text)
    return a, b, (a == b)


# ---- 口径C：★ 结论段内的首个维度（★ 最贴近「第一步想到」的语义 ★）--------
_CUE = re.compile(r"(先说结论|结论|总体|综上|简要|总结|直接说|我的建议|建议如下|核心建议)")
_PARA = re.compile(r"\n\s*\n")


def first_dim_concl(text):
    """★ 取【第一段含结论性措辞】、★ 在其中找最早维度；★ 找不到则退回第一段 ★"""
    paras = [p for p in _PARA.split(text) if p.strip()]
    if not paras:
        return None
    tgt = None
    for p in paras[:4]:                 # ★ 只看前 4 段（★ 结论应在最前 ★）
        if _CUE.search(p):
            tgt = p
            break
    if tgt is None:
        tgt = paras[0]
    # ★ 结论段里、★ 若首行是「结论句」⇒ 先取首行（★ 排序主张通常在首行 ★）
    lines = [l for l in tgt.split("\n") if l.strip()]
    for scope in (lines[:1], lines, [tgt]):
        for line in scope:
            d = first_dim(line)
            if d:
                return d
    return None


def first_dims3(text):
    """★ 返回 (A开头400字, C结论段, B首个小节标题) ★"""
    return first_dim_head(text), first_dim_concl(text), first_dim_section(text)
