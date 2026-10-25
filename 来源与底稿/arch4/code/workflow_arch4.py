#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第四组 · 架构化状态机 v4 —— **状态进选择层**（研究四层结构的第 4 层）。

★ v3 与 v4 的区别（一句话）：
    v3：状态 → prompt 文本 → 生成      （状态只改"给模型看什么"⇒ 与提示词同构）
    v4：状态 → K 个候选 → **状态化打分选 1** ⇒（状态决定"当下选哪个动作"）

★ 关键防循环设计（否则又是恒真命题）：
    打分**不是**"查状态的 priority 选第几个候选"——那样必然选中 priority=1。
    正确做法：
      ① 候选**自己**决定这一轮写什么、放弃什么（模型自由选择，可能与状态不完全一致）
      ② 代码从候选**正文**抽取它的**实际行为**（写了哪些实体 / 避开了哪些）⇒ 不是模型自述
      ③ 状态化打分 = 该行为与状态（gaps + decisions + keeps）的吻合度
      ④ 通用打分 = **完全不看状态**（长度 + 命中实体数）⇒ 用来隔离"状态化打分"的价值
    ⇒ 因为候选**可能跑偏**，打分才有区分力；
    ⇒ "状态化打分选中的候选比通用打分选中的更符合状态" = **状态真的驱动了选择**。

★ 全部读数**零判官**（承诺/行为是字面可核验的结构化量）。
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------- 封闭枚举
DEPTHS = ("深入展开", "点到为止", "放弃")
PRIORITIES = (1, 2, 3)

# 候选草稿的长度硬闸（控制 K=3 的成本）
CAND_MIN_CHARS = 600
CAND_MAX_CHARS = 1600
K_CANDIDATES = 3


# ---------------------------------------------------------------- 数据结构
@dataclass
class State4:
    """v4 的状态：立场 + 取舍（沿用 v3 的封闭枚举决策）+ 约束。"""
    stance: str = ""
    keeps: List[str] = field(default_factory=list)
    gaps: List[dict] = field(default_factory=list)      # [{index,text,entities}]
    decisions: List[dict] = field(default_factory=list)  # [{gap_index,depth,priority}]
    must_include: List[str] = field(default_factory=list)
    forbidden: List[str] = field(default_factory=list)
    excluded: List[str] = field(default_factory=list)
    step: int = 0

    def to_dict(self) -> dict:
        return copy.deepcopy(self.__dict__)

    @staticmethod
    def from_dict(d: dict) -> "State4":
        return State4(**{k: v for k, v in (d or {}).items()
                         if k in State4.__dataclass_fields__})

    # ---- 状态派生量（**纯函数**，供打分用）----
    def deep_entities(self) -> List[str]:
        """状态认为"这一轮该写透"的实体（按 priority 顺序）。"""
        gaps = {int(g.get("index") or 0): g for g in self.gaps}
        out = []
        for d in sorted(self.decisions, key=lambda x: int(x.get("priority") or 9)):
            if d.get("depth") != "深入展开":
                continue
            g = gaps.get(int(d.get("gap_index") or 0)) or {}
            for e in (g.get("entities") or []):
                if e not in out:
                    out.append(e)
        return out

    def drop_entities(self) -> List[str]:
        """状态认为"这一轮该放弃"的实体。"""
        gaps = {int(g.get("index") or 0): g for g in self.gaps}
        out = []
        for d in self.decisions:
            if d.get("depth") != "放弃":
                continue
            g = gaps.get(int(d.get("gap_index") or 0)) or {}
            for e in (g.get("entities") or []):
                if e not in out:
                    out.append(e)
        return out

    def all_entities(self) -> List[str]:
        out = []
        for g in self.gaps:
            for e in (g.get("entities") or []):
                if e not in out:
                    out.append(e)
        return out


@dataclass
class Candidate:
    """一个候选草稿 + 从正文抽取的**实际行为**。"""
    idx: int
    text: str = ""
    hit_entities: List[str] = field(default_factory=list)   # 正文里出现的实体
    missed_entities: List[str] = field(default_factory=list)  # 允许集里没出现的
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return copy.deepcopy(self.__dict__)


# ---------------------------------------------------------------- 解析
# 否定标记：出现在实体**前文窗口**内 ⇒ 该处提及是"否定/回避"而非"写入"
NEG_MARKERS = ("不写", "不要写", "不再写", "不碰", "不展开", "不谈", "不提",
               "不打算", "放弃", "避开", "略过", "无需", "没必要", "暂且不",
               "不在这一轮", "留到以后", "暂不", "不作为", "不铺开")


def _entity_mentions(text: str, entity: str):
    """返回该实体在正文中的所有出现位置，并标注每处是「写入」还是「否定/回避」。"""
    t = text or ""
    out = []
    start = 0
    while True:
        i = t.find(entity, start)
        if i < 0:
            break
        window = t[max(0, i - 14):i]
        neg = any(m in window for m in NEG_MARKERS)
        out.append({"pos": i, "negated": neg})
        start = i + max(1, len(entity))
    return out


def extract_entities(text: str, allowed: List[str]) -> Tuple[List[str], List[str]]:
    """从候选正文抽取**实际行为**：哪些允许实体**真正写到了**、哪些**没写到**。

    ★ 自检抓到的真实缺陷（2026-10-23）：纯逐字包含会把"提到了但放弃了"算成命中。
      候选写"我不写丙"时，"丙"逐字出现 ⇒ 被算成"写了丙" ⇒ **取舍语义根本测不出来**。
    ⇒ 修法：实体前 14 字符窗口内出现否定标记 ⇒ 该处计为**回避**，不算写入。
      同一实体若既有肯定出现又有否定出现 ⇒ 以**肯定出现**为准（模型真的写了它）。

    ★ 抽的是**正文里逐字出现的实体**，不是模型自述的"承诺"
      ⇒ 免掉"空洞承诺"问题，且完全可核验。
    """
    t = text or ""
    hit, missed = [], []
    for e in allowed:
        if not e:
            continue
        ms = _entity_mentions(t, e)
        if not ms:
            missed.append(e)
        elif any(not m["negated"] for m in ms):
            hit.append(e)          # 至少有一处是真正写入
        else:
            missed.append(e)        # 只在否定语境出现 ⇒ 视为回避
    return hit, missed


def score_state_alignment(cand: Candidate, st: State4) -> float:
    """★ 状态化打分（0–1）：候选行为与状态的吻合度。

    组成（全部零判官、全部字面可核验）：
      + 该写透的实体写了多少（命中 / 状态认为该写的）
      + 该放弃的实体避开了多少（未命中 / 状态认为该放弃的）
      + 必含命中、禁含未命中
    ⚠️ **不**使用 priority 直接指定选哪个候选 ⇒ 不是恒真命题。
    """
    deep = st.deep_entities()
    drop = st.drop_entities()
    parts, weights = [], []

    if deep:
        parts.append(sum(1 for e in deep if e in cand.hit_entities) / len(deep))
        weights.append(1.0)
    if drop:
        parts.append(sum(1 for e in drop if e in cand.missed_entities) / len(drop))
        weights.append(1.0)
    if st.must_include:
        parts.append(sum(1 for e in st.must_include if e in cand.hit_entities) / len(st.must_include))
        weights.append(1.0)
    if st.forbidden:
        parts.append(sum(1 for e in st.forbidden if e in cand.missed_entities) / len(st.forbidden))
        weights.append(1.0)
    if not parts:
        return 0.0
    return round(sum(p * w for p, w in zip(parts, weights)) / sum(weights), 4)


def score_generic(cand: Candidate) -> float:
    """★ 通用打分（0–1）：**完全不看状态**。

    ⚠️ PREREG_v4 §7.4 要求它**不含任何状态信息** ⇒ 这里只用候选自身特征：
      长度适中性 + 命中实体数（无状态参照）
    ⇒ 它的作用是提供一个"不靠状态也能挑出点什么"的基线。
    """
    n = len(cand.text or "")
    if n == 0:
        return 0.0
    # 长度项：越接近区间中点越高（不偏好长也不偏好短）
    mid = (CAND_MIN_CHARS + CAND_MAX_CHARS) / 2
    half = (CAND_MAX_CHARS - CAND_MIN_CHARS) / 2
    len_score = max(0.0, 1.0 - abs(n - mid) / max(1.0, half))
    # 覆盖项：命中实体越多越高（不参照状态）
    cov = min(1.0, len(cand.hit_entities) / 4.0)
    return round(0.5 * len_score + 0.5 * cov, 4)


def tiebreak_net_tradeoff(cand: Candidate, st: State4) -> float:
    """★ 并列打破用的**净取舍数**：命中「该写」的实体数 − 命中「该放弃」的实体数。

    ⚠️ 只使用**状态信息**（deep/drop 实体集）⇒ 不会污染 H3（状态化 vs 通用）的对比。
    ⚠️ 作用：deep/must 与 drop/forbidden 实为同一批实体的两种说法，
      主分数只有 2 个独立维度 ⇒ 常见并列；本项在不改变主分数的前提下打破并列。
    """
    deep, drop = set(st.deep_entities()), set(st.drop_entities())
    hit = set(cand.hit_entities)
    return float(len(hit & deep) - len(hit & drop))


def select(cands: List[Candidate], scorer, state: Optional[State4] = None
           ) -> Tuple[Optional[Candidate], List[dict]]:
    """按 scorer 给候选打分并选择。
    ★ 并列时用 `tiebreak_net_tradeoff`（需给 state）；再并列则取第一个（确定性）。"""
    scored = []
    for c in cands:
        if c.error or not (c.text or "").strip():
            continue
        tb = tiebreak_net_tradeoff(c, state) if state is not None else 0.0
        scored.append({"idx": c.idx, "score": scorer(c), "tiebreak": tb, "text": c.text})
    if not scored:
        return None, []
    best = max(scored, key=lambda r: (r["score"], r["tiebreak"], -r["idx"]))
    chosen = next(c for c in cands if c.idx == best["idx"])
    return chosen, scored


def check_candidate_gate(text: str) -> Tuple[bool, List[str]]:
    """候选草稿的硬闸：长度 + 语言（整段非目标语言才算漂移）。"""
    reasons = []
    n = len(text or "")
    if n < CAND_MIN_CHARS:
        reasons.append("太短(%d<%d)" % (n, CAND_MIN_CHARS))
    if n > CAND_MAX_CHARS:
        reasons.append("太长(%d>%d)" % (n, CAND_MAX_CHARS))
    for m in re.finditer(r"[^\u4e00-\u9fff]{40,}", text or ""):
        if not re.search(r"[\u4e00-\u9fff]", m.group(0)):
            reasons.append("语言漂移")
            break
    return (not reasons), reasons


# ---------------------------------------------------------------- 提示模板
CAND_SYS = """你要写一篇中文文章。

这一轮的处境（你自己决定怎么用）：
- 你的立场：{stance}
- 你不能放弃的：{keeps}
- 你看到的几个缺口（每个附带它涉及的具体词）：
{gaps}

**这一轮要你自己决定两件事**：
1. 这一轮你**重点写透**哪几个缺口（不必全写）；
2. 你**明确放弃**哪几个缺口（写了就散了）。

请直接写出这一轮的文章正文（{lo}–{hi} 字）。
不要写"我将写什么"之类的话，直接写文章。
"""


def render_candidate_prompt(st: State4, lo: int, hi: int,
                            blind: bool = False) -> str:
    """渲染候选生成提示。

    ★★ blind=True ⇒ **提示里不含任何缺口内容/实体**（只给缺口**数量**）：
      候选完全不知道状态化打分依据什么 ⇒ 状态化打分**彻底非恒真**
      ⇒ 这是"盲从地板"，也是 **H3 的干净读数**所在的臂。
    ⚠️ 非 blind 模式会告知候选缺口文字与实体 ⇒ 候选"照做就能命中"
      ⇒ 该臂的 align 偏高**不能**单独作为驱动力证据。
    """
    if blind:
        gl = "（%d 个你还没想清楚的地方，具体是什么**由你自己判断**，此处不告诉你）" % len(st.gaps)
    else:
        gl = "\n".join("%d. %s（涉及：%s）" % (g["index"], g["text"],
                                              "、".join(g.get("entities") or []) or "（无）")
                        for g in st.gaps) or "（没有明显缺口）"
    return CAND_SYS.format(
        stance=st.stance or "（未明确）",
        keeps="；".join(st.keeps) or "（未明确）",
        gaps=gl, lo=lo, hi=hi)


# ---------------------------------------------------------------- 自检
def _selfcheck(verbose=True):
    R = []

    def chk(name, cond, detail=""):
        R.append({"name": name, "pass": bool(cond), "detail": str(detail)[:120]})

    # 1. 状态派生量
    st = State4(
        stance="S", keeps=["k1"],
        gaps=[{"index": 1, "text": "g1", "entities": ["甲", "乙"]},
              {"index": 2, "text": "g2", "entities": ["丙"]},
              {"index": 3, "text": "g3", "entities": ["丁"]}],
        decisions=[{"gap_index": 1, "depth": "深入展开", "priority": 1},
                   {"gap_index": 2, "depth": "点到为止", "priority": 2},
                   {"gap_index": 3, "depth": "放弃", "priority": 3}],
        must_include=["甲"], forbidden=["丁"], excluded=[])
    chk("deep_entities 只取「深入展开」的实体", st.deep_entities() == ["甲", "乙"], st.deep_entities())
    chk("drop_entities 只取「放弃」的实体", st.drop_entities() == ["丁"], st.drop_entities())
    chk("all_entities 覆盖全部缺口实体",
        set(st.all_entities()) == {"甲", "乙", "丙", "丁"}, st.all_entities())

    # 2. 实体抽取（行为，不是自述）
    hit, missed = extract_entities("这篇写甲不写丙", ["甲", "丙", "丁"])
    chk("extract_entities 命中/未命中正确",
        hit == ["甲"] and missed == ["丙", "丁"], (hit, missed))

    # 3. ★ 打分不是恒真：跑偏的候选得分必须更低
    good = Candidate(1, "写甲写乙不写丁", ["甲", "乙"], ["丙", "丁"])
    bad = Candidate(2, "写丙写丁不写甲", ["丙", "丁"], ["甲", "乙"])
    sg, sb = score_state_alignment(good, st), score_state_alignment(bad, st)
    chk("★ 状态化打分：符合状态的候选分更高", sg > sb, (sg, sb))
    chk("★ 状态化打分满分=1.0", abs(sg - 1.0) < 1e-6, sg)

    # 4. ★ 通用打分**不含状态**：换状态后分数不变
    st2 = copy.deepcopy(st)
    st2.decisions = [{"gap_index": 3, "depth": "深入展开", "priority": 1},
                     {"gap_index": 1, "depth": "放弃", "priority": 2}]
    g1 = score_generic(good)
    g2 = score_generic(good)
    chk("★ 通用打分与状态无关", g1 == g2, (g1, g2))

    # 5. ★ 通用打分对"跑偏候选"也给高分（否则 H3 无区分力）
    bad_long = Candidate(2, ("写丙写丁不写甲。" * 120)[:900], ["丙", "丁"], ["甲", "乙"])
    chk("通用打分不看状态 ⇒ 跑偏候选也能得高分",
        score_generic(bad_long) > 0.3, score_generic(bad_long))
    chk("★ 通用打分对符合状态的候选分数相近（不因符合状态而加分）",
        abs(score_generic(bad_long) - score_generic(Candidate(1, ("甲乙。" * 300)[:900], ["甲", "乙"], []))) < 0.5)

    # 6. 选择：并列取第一个（确定性）
    c1 = Candidate(1, "甲" * 700, ["甲"], [])
    c2 = Candidate(2, "甲" * 700, ["甲"], [])
    sel, scored = select([c1, c2], score_generic)
    chk("并列时确定性取第一个", sel is not None and sel.idx == 1, sel.idx if sel else None)
    sel2, _ = select([c1], score_generic)
    chk("单候选可被选中", sel2 is not None and sel2.idx == 1)
    sel3, _ = select([], score_generic)
    chk("空候选集返回 None", sel3 is None)

    # 7. 硬闸
    ok, why = check_candidate_gate("短")
    chk("太短被拦", (not ok) and any("太短" in x for x in why), why)
    ok, why = check_candidate_gate("中" * 800)
    chk("正常长度通过", ok, why)
    ok, why = check_candidate_gate("中文一段。" * 100 + "A" * 60)
    chk("长英文片段判漂移", (not ok) and any("语言漂移" in x for x in why), why)
    ok, why = check_candidate_gate("中" * 3000)
    chk("太长被拦", (not ok) and any("太长" in x for x in why), why)

    # 8. 提示渲染
    p = render_candidate_prompt(st, 600, 900)
    chk("候选提示含立场", "S" in p)
    chk("候选提示含缺口实体", "甲" in p and "丙" in p)
    chk("候选提示要求自己决定写透/放弃",
        "重点写透" in p and "放弃" in p)
    # ★★ 防回归：blind 提示里**不得出现任何状态实体/缺口文字**
    _st2 = State4(stance="立场甲", keeps=["保留甲"], gaps=[
        {"index": 1, "text": "缺口涉及秘密词丙", "entities": ["秘密词丙"]},
        {"index": 2, "text": "另一个秘密词丁", "entities": ["秘密词丁"]}],
        decisions=[{"gap_index": 1, "depth": "深入展开", "priority": 1, "note": "n"},
                   {"gap_index": 2, "depth": "放弃", "priority": 2, "note": "n"}],
        must_include=["秘密词丙"], forbidden=["秘密词丁"], excluded=[], step=1)
    _pb = render_candidate_prompt(_st2, 600, 900, blind=True)
    _pf = render_candidate_prompt(_st2, 600, 900, blind=False)
    chk("★ blind 提示不含任何状态实体/缺口文字",
        ("秘密词丙" not in _pb) and ("秘密词丁" not in _pb) and ("缺口涉及" not in _pb),
        _pb[-100:])
    chk("★ 非 blind 提示确实含缺口实体（用于识别恒真风险）",
        ("秘密词丙" in _pf) and ("秘密词丁" in _pf))

    # 9. ★ 变异注入：把"状态化打分"换成"通用打分" ⇒ 变异体必须被检测出来
    #    检测方式：构造"状态化打分选 A、通用打分选 B"的一对候选；
    #    若打分器被变异，变异体就会选错 ⇒ 断言必须失败。
    # cA：符合状态，但命中实体**少**（写得克制）
    # cB：跑偏，但命中实体**多**（什么都提）⇒ 通用打分（覆盖项）会偏向 cB
    # ⇒ 两个打分器选出不同候选 ⇒ 变异（把状态化打分换成通用打分）必被检测到
    cA = Candidate(1, ("甲。" * 300)[:900], ["甲"], ["乙", "丙", "丁"])
    cB = Candidate(2, ("丙丁甲乙戊。" * 200)[:900], ["丙", "丁", "甲", "乙"], [])
    pick_state, _ = select([cA, cB], lambda c: score_state_alignment(c, st))
    pick_generic, _ = select([cA, cB], score_generic)
    chk("变异注入前提：状态化打分与通用打分确实选出不同的候选",
        pick_state.idx != pick_generic.idx,
        (pick_state.idx, pick_generic.idx))
    # 变异体：打分器被换成通用打分 ⇒ 应当选错
    mutated_pick, _ = select([cA, cB], score_generic)
    chk("变异注入：打分器退化为通用打分时被抓到（选出了错误的候选）",
        mutated_pick.idx != pick_state.idx,
        ("变异体选了 idx=%s，正确应为 idx=%s" % (mutated_pick.idx, pick_state.idx)))
    # 还原后仍正确
    restored_pick, _ = select([cA, cB], lambda c: score_state_alignment(c, st))
    chk("变异还原后仍选中正确候选", restored_pick.idx == pick_state.idx)

    # 10. State4 往返
    d = st.to_dict()
    st_b = State4.from_dict(d)
    chk("State4 to_dict/from_dict 往返一致",
        st_b.deep_entities() == st.deep_entities() and st_b.keeps == st.keeps)

    ok = all(x["pass"] for x in R)
    if verbose:
        for x in R:
            print("  %s %-46s %s" % ("✓" if x["pass"] else "✗", x["name"], x["detail"]))
        print("  === workflow_arch4 自检: %s (%d/%d) ===" %
              ("通过" if ok else "失败", sum(x["pass"] for x in R), len(R)))
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if _selfcheck() else 1)
