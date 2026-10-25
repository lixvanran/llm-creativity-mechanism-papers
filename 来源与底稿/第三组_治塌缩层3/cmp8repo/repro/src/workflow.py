# -*- coding: utf-8 -*-
"""治塌缩工作流（Collapse-Fix Workflow, 简称 **W**）—— 让 Agent 的答案不再中庸。

> 这是**可运行代码**，不是设计文档。设计依据见 `routes/COLLAPSE-REMEDY-2026-10-22.md`。

## 它针对的三个失败

| 失败 | 现象 | 本工作流的干预 |
|---|---|---|
| **横向收敛** | 多个槽位产出趋于同一（中庸） | **认知位置解耦**：每个槽位挂一个**认知帧**（vantage operator，非 persona）⇒ 被推到不同角落 |
| **纵向早熟** | 搜索提前停止、动作集固定 | **动作空间可演化**（B\* 式）：动作**失败 ⇒ 构造新动作** ⇒ 动作集本身在长 |
| **产出中庸** | 答案落在分布中心 | **行为空间照明**（MAP-Elites）：(帧组合 × 操作序列) 格子，每格留最优 ⇒ 广度是结构保证的 |

## 流程（单次运行）

```
0. 选帧    Fisher-Yates 从 15 帧池抽 K 个（互不重复、seed 可复现、必含 1 个 wild）
1. 发散    K 个槽位并行生成 —— ★ 槽位互不可见（谁也看不到别人写了什么）
2. 抽取    逐槽位抽断言
3. 去冗余  离散去冗余（数字指纹 + 4-gram，★ 不用 embedding）
4. 演化    ★ 判定哪些动作"失败" ⇒ 从失败**构造新动作** ⇒ 进动作档案
5. 重跑    若有新动作：每槽位用自己的新动作再跑一轮（★ 搜索空间在这一步变大）
6. 装配    机械装配（不重写、不让模型再总结一遍）
7. 记账    行为格归档 + 中庸度四指标
```

## 与既有路线的关系

* **路线 A**（`routes/A/route_a.py`）是**固定 7 步拓扑**、固定 facet 集合、**动作集固定** ⇒ 搜索空间不增长。
* **W 继承 A 的机械装配与去冗余口径**，但把三处换成可增长的：
  ① 固定 facet → **认知帧池**（可扩）
  ② 固定动作 → **动作档案 + 失败驱动的新动作构造**
  ③ 无照明 → **行为格档案**
* W **不引入**任何新判据：承重、去冗余、结论空间的口径**完全沿用协议**。

## 纪律

* **失败不许静默变成 0**：每个失败类型都有独立计数，且**必进**读数。
* **种子真的可复现**：用 `random.Random(seed)`（★ 修 ADHD 原版用 `Math.random()` 无 PRNG 的缺陷）。
* **不用 embedding**：去冗余、行为距离、新颖度全部用离散结构量。
* **装配必须机械**：不由模型重写答案。
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ══════════════════════════════════════════════════════════════════════
# §0 认知帧池（vantage operator，**不是** persona）
# ══════════════════════════════════════════════════════════════════════
# 逐字依据：ADHD 项目 `src/packs/core.ts`（MIT, UditAkhourii/adhd）
# —— 15 个 id/label/prompt/tags 全部照录，**英文 prompt 逐条重写为中文**，
#    但**保持 "vantage operator（重新摆出问题）" 而非 "扮演身份"** 的定位。
# ⚠️ 定位为什么重要：Diversity Collapse 证明**专家权威 persona 会压多样性**；
#    帧是**故意扭曲**，机制不同 ⇒ 论文结论**不能**直接推论到帧上。

FRAMES: List[Dict[str, Any]] = [
    dict(id="hardware-eyes", label="硬件工程师视角", wild=True,
         prompt="你从延迟、内存布局与物理约束的角度思考。把这个问题重新摆成"
                "一个硬件/固件问题来看：总线拓扑、缓存、时间预算会告诉你什么？"),
    dict(id="regulator", label="监管/审计视角", wild=False,
         prompt="你审计系统的合规性与失效模式。追问：这里什么必须是可证明的、"
                "可追溯的、可拒绝的？在这种追问下会浮出哪些想法？"),
    dict(id="ten-year-old", label="十岁小孩视角", wild=True,
         prompt="你是一个从没见过这类系统的好奇小孩。描述那些天真但不受成规束缚的做法。"
                "忽略惯例。"),
    dict(id="adversary", label="对手视角", wild=False,
         prompt="你是一个有敌意的竞争者或攻击者。生成那些能利用、搞坏、破坏显然解法的做法，"
                "然后把它们反转成想法。"),
    dict(id="biology", label="跨域：生物学", wild=True,
         prompt="从生物学搬一个机制过来——免疫系统、神经可塑性、细胞信号、进化、肠道菌群——"
                "硬套到这个工程问题上。"),
    dict(id="logistics", label="跨域：物流/供应链", wild=False,
         prompt="从物流偷机制过来：排队、批处理、准时制、枢纽辐射、退货、末端配送。"
                "把它们字面地套到这个问题上。"),
    dict(id="game-design", label="跨域：游戏设计", wild=False,
         prompt="像游戏设计师一样处理这个问题。循环是什么、奖励是什么、摩擦在哪、"
                "存档点是什么、速通技巧是什么？把用户/系统当成玩家。"),
    dict(id="markets", label="跨域：市场", wild=True,
         prompt="把问题当成一个市场。谁是买方、卖方、撮合者？在这里，拍卖、期货合约、"
                "清算所会是什么样子？"),
    dict(id="inversion", label="反转", wild=False,
         prompt="问相反的问题。如果目标是 X，就去头脑风暴「怎样保证不是 X」，"
                "再把每个答案取反变回一个想法。"),
    dict(id="extreme-zero", label="极端：零预算、一小时", wild=False,
         prompt="你没钱、没人、只有一小时。最粗糙但仍然扛得住承重职责的版本是什么？"
                "允许 hack、硬编码、手工循环。"),
    dict(id="extreme-infinite", label="极端：无限预算、十年", wild=True,
         prompt="你有无限算力、无限工程师、一十年。极简主义之外的极繁版本是什么样？"
                "只有那种规模才可能做到什么？"),
    dict(id="remove-assumption", label="去掉承重假设", wild=True,
         prompt="指出这个问题上人人当作固定不变的那件事（框架、数据库、请求/响应模型、"
                "文件系统、网络）。想象它没了。生成只存在于那个世界里的想法。"),
    dict(id="speedrunner", label="速通者视角", wild=True,
         prompt="你在速通。找 glitch、跳关、越界技巧、帧完美的捷径。"
                "穿过这个问题的那条滥用但合法的路径是什么？"),
    dict(id="ant-colony", label="蚁群视角", wild=True,
         prompt="没有中央规划者。许多笨 agents、局部规则、信息素轨迹。这个问题会如何"
                "自发地解决自己？"),
    dict(id="ops-3am", label="凌晨三点的 on-call", wild=False,
         prompt="你是被半夜叫醒的值班工程师，这个东西坏了。什么样的设计能让你不用被 call？"
                "什么才是「按 runbook 就能处理」的解法？"),
]

FRAME_IDS = [f["id"] for f in FRAMES]
_FRAME_BY_ID = {f["id"]: f for f in FRAMES}


# ══════════════════════════════════════════════════════════════════════
# §1 选帧（**有 PRNG** ⇒ seed 真可复现）
# ══════════════════════════════════════════════════════════════════════
def select_frames(k: int = 4, seed: int = 0, frame_seed: int | None = None) -> List[str]:
    """Fisher-Yates 抽 `k` 个互不重复的帧。

    ★ 必含 **1 个 wild 帧**（ADHD 原版的 `wildPick` 逻辑，见 `src/frames.ts:62`）——
      wild 帧 = 扭曲最大的一档（十岁小孩/反身蚁群/去假设/速通者…）⇒ 它们是发散的主要来源。

    ⚠️ 与 ADHD 原版的差别：原版用 `Math.random()`（**无 PRNG**）⇒ 不可复现；
      文档却声称 "deterministic per-seed"（自相矛盾）。**这里用 `random.Random(seed)`**。
    """
    # ★ 2026-10-25 解耦：frame_seed 独立于 run seed
    #   （不传 ⇒ 行为与旧版【逐字节一致】⇒ 回归要求）
    rng = random.Random(seed if frame_seed is None else frame_seed)
    ids = list(FRAME_IDS)
    rng.shuffle(ids)
    picked = ids[:max(0, k)]
    if picked and not any(_FRAME_BY_ID[i]["wild"] for i in picked):
        # ★ 必含 1 个 wild：从剩下的 wild 里换掉第一个非 wild
        wilds = [i for i in ids if _FRAME_BY_ID[i]["wild"] and i not in picked]
        if wilds:
            first_nonwild = next((n for n, i in enumerate(picked)
                                  if not _FRAME_BY_ID[i]["wild"]), 0)
            picked[first_nonwild] = wilds[0]
    return picked


# ══════════════════════════════════════════════════════════════════════
# §2 动作档案 + 失败驱动的新动作构造（★ B\* 式动作空间演化）
# ══════════════════════════════════════════════════════════════════════
# 失败类型 → **新动作模板**。新动作不是"再跑一次"，而是**换一个做法**。

ACTION_TEMPLATES: Dict[str, str] = {
    "base": ("把这个问题重新摆成下面这个视角来看，然后给出**具体**的、能落到条件与数字上的做法：\n"
             "【视角】{frame_prompt}"),

    # ── 演化出来的动作（失败 → 新做法）
    "fix_empty": ("【视角】{frame_prompt}\n"
                  "上一步没能产出任何可用内容。**先只做一件事**：从题面与依据里逐条抄出与本视角"
                  "相关的**具体名词与数字**（不要展开、不要评价），抄完再从这些名词出发写做法。"),

    "fix_unmentioned": ("【视角】{frame_prompt}\n"
                        "上一步写的东西与依据完全对不上。**先只做一件事**：从依据里挑出与本视角"
                        "最相关的 **2–3 条并写出它们的编号**，然后**只针对这几条**写做法，"
                        "不要谈依据没写的东西。"),

    "fix_zero_lb": ("【视角】{frame_prompt}\n"
                    "上一步写不出「它改变了哪个决策」。**先只做一件事**：问自己"
                    "「如果这条信息是假的，答案的哪一句会变？」，把那一句写出来，"
                    "再补上支撑它的条件。"),

    "fix_fallback": ("【视角】{frame_prompt}\n"
                     "上一步触发了兜底（内容不完整）。**先只做一件事**：只输出 **3 条**，"
                     "每条**必须**带一个具体数字或一个明确的成立条件，其余一律不写。"),

    "fix_truncated": ("【视角】{frame_prompt}\n"
                      "上一步超长被截断。**先只做一件事**：把内容压到只剩"
                      "**承重的那一句**——如果这句话不成立，答案会变；其余全删。"),

    # ★★ 2026-10-22 新增：**消解矛盾**（由 D01 的真实观测驱动）
    #   观测：层2 产出「①③④正确，②错误」，而直调是「②正确」
    #        ⇒ **同一个判断给出两种相反结论** ⇒ 这是发散的代价
    #   ⇒ 演化出的新动作：**先把自相矛盾的那几条删掉**，只留站得住的
    "fix_conflict": ("【视角】{frame_prompt}\n"
                     "★ 上一步的内容里**有互相矛盾的地方**（同一个判断出现了相反的结论）。\n"
                     "**先只做一件事**：逐条检查你写的每一句，**凡是与别的句子或与依据冲突的，"
                     "直接删掉**；只保留你能在依据里指到出处的那几条。"
                     "宁可少写，也不要写出互相打架的结论。"),
}

FAILURE_KINDS = ("empty", "all_unmentioned", "zero_load_bearing", "fallback",
                 "truncated", "conflict")

# ══════════════════════════════════════════════════════════════════════
# §2b ★ 层3 的真东西：**可组合的动作空间**（不再是 6 个查表模板）
# ══════════════════════════════════════════════════════════════════════
# 2026-10-22 自查发现：原先的「失败类型 → 预写好的动作模板」**本质上是"设计的手段"**
# ⇒ **那是层2，不是层3**。真正的层3 要求**动作本身可被选择/学习**。
#
# ⇒ 动作改成**三个正交因子的组合**：
#     action = (repair_type, scope, strictness)
#   · repair_type  改什么（6 种，含 none ⇒ 允许"什么都不改"）
#   · scope        作用范围（本槽位 / 跨槽位对照）
#   · strictness   强度（软提示 / 中：只给 3 条 / 硬：必须指到出处）
# ⇒ 6 × 2 × 3 = **36 个可组合动作**
# ⇒ ★ 关键：**提示词由这三个因子拼出来**，不是为每种失败预写一段话
#   ⇒ 于是"选哪个动作"是一个**有有限取值空间的决策问题** ⇒ 可以被策略学出来
#   （这正是 AgentSquare 模块池的思路在"动作"上的落法）

REPAIR_TYPES: Dict[str, Optional[str]] = {
    "none": None,                     # 什么都不改（保留 ⇒ 策略可选择"不作为"）
    "drop_conflicting": "凡是与别的句子、或与依据冲突的，**直接删掉**",
    "ground_in_evidence": "每一条都必须**能在依据里指到出处**（写���编号）",
    "name_decision_point": "每一条都要写明「**如果这条信息是假的，答案的哪一句会变**」",
    "compress": "只写**承重的那一句**——如果这句话不成立，答案会变；其余全删",
    "keep_all": "**不要删任何内容**",
}

SCOPES: Dict[str, str] = {
    "slot": "只针对**你自己这一路**的内容",
    "cross_slot": "**对照其它各路的内容**一起检查",
}

STRICTNESS: Dict[int, str] = {
    0: "（软：按下面的要求调整即可）",
    1: "（中：**只输出 3 条**，其余一律不写）",
    2: "（硬：**只输出你能指到依据出处的**，每条标注依据编号）",
}

ActionSpec = Tuple[str, str, int]          # (repair_type, scope, strictness)


def all_action_specs() -> List[ActionSpec]:
    """**全部可组合动作**（36 个）。顺序稳定 ⇒ 策略下标可复算。"""
    out: List[ActionSpec] = []
    for rt in REPAIR_TYPES:
        for sc in SCOPES:
            for st in (0, 1, 2):
                out.append((rt, sc, st))
    return out


ACTION_SPECS: List[ActionSpec] = all_action_specs()


def _action_name(a) -> str:
    """动作的**统一名字**（查表模式是名字，policy 模式是三因子组合）。"""
    if isinstance(a, tuple):
        return "act_%s_%s_%d" % a
    return str(a)


def action_prompt(spec: ActionSpec, frame_prompt: str, *, note: str = "") -> str:
    """由**三个因子拼出**动作提示词（不是为每种失败预写一段话）。"""
    rt, sc, st = spec
    parts = ["【视角】%s" % frame_prompt]
    if REPAIR_TYPES.get(rt):
        parts.append("【要改什么】%s" % REPAIR_TYPES[rt])
    parts.append("【作用范围】%s" % SCOPES[sc])
    parts.append("【强度】%s" % STRICTNESS[st])
    if note:
        parts.append("【上一步出了什么问题】%s" % note)
    parts.append("★ 只输出 3–6 条，每条一行，行首「- 」；每条必须具体（带数字/条件/可核查判断）；"
                 "不超过 400 字。")
    return "\n".join(parts)


def failure_note(kind: str, detail: str = "") -> str:
    """把失败类型翻成给模型看的**问题描述**（而不是直接给它修法）。"""
    base = {
        "empty": "上一步没能产出任何可用内容。",
        "all_unmentioned": "上一步写的东西与依据完全对不上。",
        "zero_load_bearing": "上一步写不出「它改变了哪个决策」。",
        "fallback": "上一步触发了兜底（内容不完整）。",
        "truncated": "上一步超长被截断。",
        "conflict": "★ 上一步的内容里**有互相矛盾的地方**（同一个判断出现了相反的结论）。",
    }.get(kind, "上一步没有达到要求。")
    return base + ((" " + detail) if detail else "")


# ══════════════════════════════════════════════════════════════════════
# §2c 层3 的策略：因子化 softmax
# ══════════════════════════════════════════════════════════════════════
# ★ 为什么是**因子化**而不是 36 路扁平 softmax：
#   动作是笛卡尔积 ⇒ 概率也该分解 ⇒ p(type,scope,strict) ∝ exp(u+v+t+m)
#   ⇒ 参数 47 个（6+2+3+6×6）而不是 36 维权重矩阵 ⇒ 更少参数、更易学、更不易过拟合
# ★ 为什么**必须**有交互项 m[失败类型][修复类型]：
#   我们实测过：线性 softmax 里**与 op 无关的状态特征对选择零作用**
#   （同一 target 换 op 得分差恒定）⇒ 只给因子偏置 ⇒ 策略学不到"什么失败该用什么修法"
#   ⇒ 交互项是**唯一**能让"当前失败类型"影响动作选择的通道
#
# ★ w=0 时：均匀分布（36 个动作等概率）⇒ 那是"未训练"基线，不是"学出来的"。

REPAIR_IDS = list(REPAIR_TYPES.keys())
SCOPE_IDS = list(SCOPES.keys())
STRICT_IDS = [0, 1, 2]
FAILURE_IDS = list(FAILURE_KINDS)


class ActionPolicy:
    """因子化 softmax 策略。**权重可学** ⇒ 这才是层3。"""

    # ★ 仲裁的三个选项（**与修复动作正交**）：0=mark（标注不删）1=keep_pos 2=keep_neg
    ARB_IDS = ("mark", "keep_pos", "keep_neg")
    # ★★ 2026-10-24：**架构的两个自由度也交给学习**
    #   `nf` = 发散程度（用几个认知位置）⇒ ★ 这是"该不该发散"的决策权
    #   `mm` = 合并方式（机械汇总 / decision-packet / 逐路投票）⇒ ★ 这是"怎么合并"的决策权
    #   ⇒ A01 实测：四个臂**全部踩坑** ⇒ 写死"每题都发散 3 路"是错的
    #   ⇒ ⇒ 让**策略自己学**在什么题上该少发散、该怎么合并
    NF_IDS = (1, 2, 3, 4)
    MM_IDS = ("mechanical", "packet", "vote")

    def __init__(self, w: Optional[Dict[str, Any]] = None):
        w = w or {}
        self.u = list(w.get("u") or [0.0] * len(REPAIR_IDS))     # 修复类型
        self.v = list(w.get("v") or [0.0] * len(SCOPE_IDS))      # 作用范围
        self.t = list(w.get("t") or [0.0] * len(STRICT_IDS))     # 强度
        # m[失败类型][修复类型]
        self.m = [list(row) for row in
                   (w.get("m") or [[0.0] * len(REPAIR_IDS) for _ in FAILURE_IDS])]
        # ★ 仲裁权重（层3 要学的第二件事：冲突时保留哪一侧 / 收不收窄）
        self.arb = list(w.get("arb") or [0.0] * len(self.ARB_IDS))
        # ★★ 架构自由度：发散程度 + 合并方式
        self.nf = list(w.get("nf") or [0.0] * len(self.NF_IDS))
        self.mm = list(w.get("mm") or [0.0] * len(self.MM_IDS))

    # ---- 打分
    def score_spec(self, spec: ActionSpec, failure_kind: Optional[str]) -> float:
        rt, sc, st = spec
        s = self.u[REPAIR_IDS.index(rt)] + self.v[SCOPE_IDS.index(sc)] \
            + self.t[STRICT_IDS.index(st)]
        if failure_kind and failure_kind in FAILURE_IDS:
            fi = FAILURE_IDS.index(failure_kind)
            s += self.m[fi][REPAIR_IDS.index(rt)]
        return s

    def scores(self, failure_kind: Optional[str]) -> List[float]:
        return [self.score_spec(sp, failure_kind) for sp in ACTION_SPECS]

    def probs(self, failure_kind: Optional[str]) -> List[float]:
        sc = self.scores(failure_kind)
        mx = max(sc) if sc else 0.0
        ex = [pow(2.718281828459045, x - mx) for x in sc]
        s = sum(ex) or 1.0
        return [e / s for e in ex]

    def choose(self, failure_kind: Optional[str], rng: random.Random) -> ActionSpec:
        """按 softmax 采样一个动作（**不是 argmax** ⇒ 保留探索）。"""
        p = self.probs(failure_kind)
        r = rng.random()
        acc = 0.0
        for sp, pi in zip(ACTION_SPECS, p):
            acc += pi
            if r <= acc:
                return sp
        return ACTION_SPECS[-1]

    def choose_arbitration(self, failure_kind, rng):
        """★ 仲裁选择（层3 的第二件事）：0=mark（标注不删）1=keep_pos 2=keep_neg。

        ⇒ **与修复动作正交** ⇒ 两个决策可以分开学
        ⇒ ★ 层3 学的不是"怎么修"，而是"**冲突时收不收窄搜索空间、留哪一侧**"
          ⇒ 这正是"优化搜索空间过早闭合"的自修改形态
        """
        sc = [self.arb[i] for i in range(len(self.ARB_IDS))]
        mx = max(sc)
        ex = [pow(2.718281828459045, x - mx) for x in sc]
        tot = sum(ex) or 1.0
        p = [e / tot for e in ex]
        r = rng.random()
        acc = 0.0
        for i, pi in enumerate(p):
            acc += pi
            if r <= acc:
                return i
        return len(self.ARB_IDS) - 1

    def param_count(self) -> int:
        return (len(self.u) + len(self.v) + len(self.t)
                + len(self.m) * len(self.m[0]) + len(self.arb)
                + len(self.nf) + len(self.mm))

    # ── ★★ 架构自由度：发散程度 + 合并方式（★ 由策略决定，不由人写死）
    def choose_architecture(self, failure_kind, rng):
        """★ 采样两个架构决策：(发散程度 n_frames, 合并方式 merge_mode)。

        ⇒ **A01 实测：四个臂全部踩坑** ⇒ 写死"每题都发散 3 路 + 机械汇总"是错的
        ⇒ ⇒ 让策略自己学：**在什么题上该少发散、该怎么合并**
        ⇒ ⇒ 三个决策正交：修复动作 × 仲裁方式 × **架构方式**
        """
        def _sample(weights):
            mx = max(weights)
            ex = [pow(2.718281828459045, w - mx) for w in weights]
            tot = sum(ex) or 1.0
            r, acc = rng.random(), 0.0
            for i, e in enumerate(ex):
                acc += e / tot
                if r <= acc:
                    return i
            return len(weights) - 1
        nf = self.NF_IDS[_sample(self.nf)]
        mm = self.MM_IDS[_sample(self.mm)]
        return nf, mm

    def export(self) -> Dict[str, Any]:
        return dict(u=self.u, v=self.v, t=self.t, m=self.m, arb=self.arb,
                    nf=self.nf, mm=self.mm)

    @staticmethod
    def load(d: Dict[str, Any]) -> "ActionPolicy":
        return ActionPolicy(d)

    @staticmethod
    def from_lookup() -> "ActionPolicy":
        """★ **查表策略**：把手写的「失败类型 → 修法」映射**编码成因子权重**。

        ⇒ 这样「查表」与「学出来的」在**同一套动作空间**里 ⇒ 可以直接消融。
        ⇒ 权重是手挑的大数（等价于确定性的查表），**不是学出来的** ⇒ 它属于**层2**。
        """
        BIG = 6.0
        pol = ActionPolicy()
        # 失败类型 → (修复类型, 范围, 强度) 的手写映射
        m = {
            "empty": ("ground_in_evidence", "slot", 1),
            "all_unmentioned": ("ground_in_evidence", "slot", 2),
            "zero_load_bearing": ("name_decision_point", "slot", 1),
            "fallback": ("compress", "slot", 1),
            "truncated": ("compress", "slot", 2),
            "conflict": ("drop_conflicting", "cross_slot", 1),
        }
        for fk, (rt, sc, st) in m.items():
            if fk not in FAILURE_IDS:
                continue
            fi = FAILURE_IDS.index(fk)
            pol.m[fi][REPAIR_IDS.index(rt)] += BIG
        return pol




# ── 矛盾检测（**零判官成本**，纯文本/结构）
# ① **选项判定冲突**：题面是选择题时（①②③④ / (1)(2) / A. B.），
#    同一选项被同时判为「成立」与「不成立」⇒ 冲突。
#    ★ 这正是我们在 D01 观测到的真实失败。
# ② **数字冲突**：两条断言共享足够多的内容词，却给出**不同的数字**⇒ 冲突候选。
_OPT_MARK = re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩]|\(\d{1,2}\)|（\d{1,2}）")
_OPT_POS = re.compile(r"(成立|正确|对|是|符合|满足|可以通过|可以|有效|无误|不成立|错误|不对|不成立|不符合|不满足|不可以|无效|有误)")
_NUM_UNIT = re.compile(r"\d+(?:\.\d+)?\s*(?:%|％|元|万|亿|毫秒|秒|分钟|小时|天|年|个月|次|人|台|条|个|米|公里|kg|g|MB|GB|TB|W|V|A|MHz|GHz|℃|度)?")
_CN_CONTENT = re.compile(r"[一-鿿]{2,}")


def _option_verdicts(text: str) -> Dict[str, str]:
    """从一段文本里抽「选项 → 成立/不成立」的映射（**只认就近的判定词**）。

    ★ 只做**结构性**判定，不做任何语义理解 ⇒ 零成本、零判官、可复算。
    """
    out: Dict[str, str] = {}
    if not text:
        return out
    for m in _OPT_MARK.finditer(text):
        mark = m.group(0)
        tail = text[m.end():m.end() + 24]
        # 判定词必须**紧跟**选项标记（允许中间有少量连接词）
        pos = _OPT_POS.search(tail)
        if not pos:
            continue
        word = pos.group(0)
        if word in ("成立", "正确", "对", "是", "符合", "满足", "可以通过", "可以", "有效", "无误"):
            v = "pos"
        else:
            v = "neg"
        out.setdefault(mark, v)          # 同一个选项出现两次 ⇒ 记第一次（冲突在下面检测）
        out.setdefault(mark + "#dup", v)
    return out


def detect_conflicts(claims: Sequence[str]) -> List[Dict[str, Any]]:
    """检测**互相矛盾**的断言。返回冲突对（每对含两条原文 + 类型）。

    ★ 动机（2026-10-22 实测）：层2 的发散带来更多维度，**也带来事实性矛盾**
      （D01：层2 写「①③④正确，②错误」，直调写「②正确」）。
      ⇒ 层3 必须能**感知**这种矛盾 ⇒ 而感知矛盾**不需要判官**。
    """
    conflicts: List[Dict[str, Any]] = []
    items = [(i, c) for i, c in enumerate(claims or []) if (c or "").strip()]

    # ① 选项判定冲突
    per_opt: Dict[str, List[Tuple[int, str, str]]] = {}
    for i, c in items:
        for m in _OPT_MARK.finditer(c):
            mark = m.group(0)
            tail = c[m.end():m.end() + 24]
            pos = _OPT_POS.search(tail)
            if not pos:
                continue
            word = pos.group(0)
            v = "pos" if word in ("成立", "正确", "对", "是", "符合", "满足",
                                  "可以通过", "可以", "有效", "无误") else "neg"
            per_opt.setdefault(mark, []).append((i, v, c))
    for mark, lst in per_opt.items():
        vs = {v for _i, v, _c in lst}
        if len(vs) > 1:
            conflicts.append(dict(kind="option_verdict", marker=mark,
                                  items=[(i, c) for i, _v, c in lst]))

    # ② 数字冲突：共享内容词但数字不同
    for x in range(len(items)):
        for y in range(x + 1, len(items)):
            i1, c1 = items[x]
            i2, c2 = items[y]
            w1 = set(_CN_CONTENT.findall(c1))
            w2 = set(_CN_CONTENT.findall(c2))
            if len(w1 & w2) < 2:
                continue
            n1 = set(_NUM_UNIT.findall(c1))
            n2 = set(_NUM_UNIT.findall(c2))
            if n1 and n2 and n1 != n2:
                conflicts.append(dict(kind="numeric", items=[(i1, c1), (i2, c2)]))

    return conflicts



class ActionArchive:
    """动作档案。**新动作从这里长出来，并且会被复用。**

    ★ 与 ADAS 的"档案 = 历史发现的累积"同形：档案不是留痕，是**搜索结构本身**。
    """

    def __init__(self) -> None:
        self.actions: Dict[str, Dict[str, Any]] = {}
        self.uses: Dict[str, int] = {}
        self.provenance: List[Dict[str, Any]] = []

    def add(self, name: str, template: str, *, born_from: str, evidence: str = "") -> str:
        if name not in self.actions:
            self.actions[name] = dict(name=name, template=template,
                                      born_from=born_from, evidence=evidence)
            self.provenance.append(dict(action=name, born_from=born_from,
                                        evidence=evidence))
        self.uses[name] = self.uses.get(name, 0) + 1
        return name

    def template(self, name: str) -> str:
        return self.actions.get(name, {}).get("template", ACTION_TEMPLATES["base"])

    def stats(self) -> Dict[str, Any]:
        return dict(n_actions=len(self.actions),
                    names=sorted(self.actions),
                    uses=dict(self.uses),
                    provenance=list(self.provenance))


def propose_new_action(failure_kind: str, slot_id: str, archive: ActionArchive) -> Optional[str]:
    """**从一次失败构造一个新动作**（Voyager 式：错误信息 → 新做法）。

    ★ 只有真的失败才提案；成功的动作**不**被替换 ⇒ 不会无节制地扩动作空间。
    ★ 同一 `failure_kind` 只产出一个动作（按 `failure_kind` 命名）⇒ 动作集是**可枚举**的，
      不是无穷生成。
    """
    if failure_kind not in FAILURE_KINDS:
        return None
    name = "act_%s" % failure_kind
    if name in archive.actions:
        return name                      # 已有 ⇒ 复用（不重复造）
    tmpl = ACTION_TEMPLATES.get("fix_%s" % failure_kind)
    if not tmpl:
        return None
    return archive.add(name, tmpl, born_from="%s@%s" % (failure_kind, slot_id),
                       evidence="failure_kind=%s slot=%s" % (failure_kind, slot_id))


# ══════════════════════════════════════════════════════════════════════
# §3 离散去冗余（★ 不用 embedding）
# ══════════════════════════════════════════════════════════════════════
_NUM_RE = re.compile(r"\d+(?:\.\d+)?%?")
_CJK_PUNCT = "，。；：、！？,.;:!?（）()【】《》“”‘’"


def _fingerprint(s: str) -> frozenset:
    """数字指纹：一条断言里出现的数值集合（⇒ 数字不同的两条几乎必然不冗余）。"""
    return frozenset(_NUM_RE.findall(s or ""))


def _ngrams(s: str, n: int = 4) -> frozenset:
    t = re.sub(r"[\s%s]" % re.escape(_CJK_PUNCT), "", (s or ""))
    if len(t) < n:
        return frozenset([t]) if t else frozenset()
    return frozenset(t[i:i + n] for i in range(len(t) - n + 1))


def is_redundant(a: str, b: str, *, num_thresh: float = 0.8, jacc_thresh: float = 0.75) -> bool:
    """两条断言是否冗余（**离散**判据，不用 embedding）。

    * 数字指纹 Jaccard ≥ `num_thresh` ⇒ 冗余（数值说的是同一件事）
    * 字符 4-gram Jaccard ≥ `jacc_thresh` ⇒ 冗余（措辞几乎一样）
    """
    fa, fb = _fingerprint(a), _fingerprint(b)
    if fa and fb:
        inter = len(fa & fb)
        uni = len(fa | fb)
        if uni and inter / uni >= num_thresh:
            return True
    ga, gb = _ngrams(a), _ngrams(b)
    if not ga or not gb:
        return False
    return len(ga & gb) / len(ga | gb) >= jacc_thresh


def dedup(items: Sequence[str], **kw) -> List[str]:
    """贪心去冗余（保持原顺序 ⇒ 定序可复现）。"""
    kept: List[str] = []
    for it in items:
        if not (it or "").strip():
            continue
        if any(is_redundant(it, k, **kw) for k in kept):
            continue
        kept.append(it.strip())
    return kept


# ══════════════════════════════════════════════════════════════════════
# §3b ★ 跨槽位冲突的检测与仲裁（**纯文本结构 ⇒ 零判官成本**）
# ══════════════════════════════════════════════════════════════════════
# ★ 为什么必须有它（2026-10-22 实测）：
#   W 臂的矛盾是**跨槽位**的（一个槽位说"①正确"、另一个说"①错误"）
#   ⇒ ⇒ **槽内的"删掉与依据冲突的"根本不可能生效**（一个槽位删不掉另一个槽位的说法）
#   ⇒ ⇒ 这解释了为什么 act_conflict 两次都没让矛盾下降 —— **它在架构上就不可能生效**。
#
# ★ 仲裁三档（**闭合必须是显式、可控、只在必要时**）：
#   "none"     —— **冲突容忍**：双方都保留、只标注 ⇒ **不收窄搜索空间**
#                  （层2 默认：我们的目标是**拓展**思维面，不是消解冲突）
#   "drop_one" —— 冲突对里丢一个（丢哪个由上游策略决定 ⇒ 层3 可学）
#   "resolve"  —— 有依据支持的一方胜（需判官 ⇒ 贵）
_POL_POS = ("正确", "成立", "符合", "满足", "可以", "有效", "无误")
_POL_NEG = ("错误", "不成立", "不符合", "不满足", "不可以", "无效", "有误", "不对")


def _polarity(text):
    """返回 (极性, 命中词)。极性 ∈ {1, 0, -1}（1 正 / 0 无 / -1 负）。"""
    t = text or ""
    best = (0, None)
    for w in _POL_POS:
        if w in t and (best[0] == 0 or len(w) > len(best[1] or "")):
            best = (1, w)
    for w in _POL_NEG:
        if w in t and (best[0] == 0 or len(w) > len(best[1] or "")):
            best = (-1, w)
    return best


def merge_claims(claims: Sequence[str], mode: str = "mechanical") -> Dict[str, Any]:
    """★ 合并方式（**由策略选，不由人写死**）。

    | mode | 行为 | 依据 |
    |---|---|---|
    | `mechanical` | 去冗余后**全部保留**（现状）| —— |
    | `packet` | **decision packet**：全部保留 + **显式标注未决异议** | DCI (arXiv:2603.11781) *"Disagreements are preserved … not flattened"* |
    | `vote` | 多数票（plurality）**收窄** | Self-Consistency (arXiv:2203.11171)；⚠️ 概率加权不如 plurality |

    ⇒ ★ **合并是"代价发生的那一步"**（§6.4.4：逐帧投票维度 4.50 vs 机械汇总 2.50）
    ⇒ ⇒ **所以它必须是学出来的决策，不是写死的。**
    """
    cl = [c for c in (claims or []) if (c or "").strip()]
    pairs = detect_opposite_pairs(cl)
    if mode == "vote" and cl:
        from collections import Counter
        cnt = Counter(cl)
        top = max(cnt.values())
        winners = {c for c, v in cnt.items() if v == top}
        kept, seen = [], set()
        for c in cl:
            if c in winners and c not in seen:
                seen.add(c)
                kept.append(c)
        return dict(claims=kept, mode=mode, n_conflicts=len(pairs),
                    note="多数票收窄")
    kept = dedup(cl)
    if mode == "packet":
        # ★ decision packet：**不删**，但把冲突双方标出来（"未决异议"）
        marked = []
        for c in kept:
            is_conf = any(c == p["pos"] or c == p["neg"] for p in pairs)
            marked.append(("⚠未决异议：" if is_conf else "") + c)
        return dict(claims=kept, marked=marked, mode=mode, n_conflicts=len(pairs),
                    note="保留全部 + 显式标注未决异议（decision packet）")
    return dict(claims=kept, mode=mode, n_conflicts=len(pairs), note="机械汇总")


def detect_opposite_pairs(claims):
    """找出**互相矛盾**的断言对：同一决策标记 + 相反极性。"""
    items = []
    for i, c in enumerate(claims or []):
        if not (c or "").strip():
            continue
        marks = set(m.group(0) for m in _OPT_MARK.finditer(c))
        pol, w = _polarity(c)
        if not marks or pol == 0:
            continue
        items.append((i, marks, pol, w, c))
    pairs = []
    for x in range(len(items)):
        for y in range(x + 1, len(items)):
            i1, m1, p1, w1, c1 = items[x]
            i2, m2, p2, w2, c2 = items[y]
            if p1 * p2 < 0 and (m1 & m2):
                pairs.append(dict(i=i1, j=i2, marks=sorted(m1 & m2),
                                  pos=c1 if p1 > 0 else c2,
                                  neg=c2 if p1 > 0 else c1))
    return pairs


def arbitrate(claims, mode="none", drop_choice=None):
    """仲裁。返回 (保留的断言, 仲裁日志)。

    ★ "none"（层2 默认）⇒ **冲突容忍**：**全部保留**，只把冲突对记进日志
      ⇒ **不收窄搜索空间**（与"拓展思维面"的目标一致）
    ★ "drop_one" ⇒ 每对丢一个；`drop_choice` 决定丢"正"还是"负"极性那条
      ⇒ ★ **层3 可以学这个选择**（什么情况下更该保留哪一侧）
    """
    pairs = detect_opposite_pairs(claims)
    log = dict(mode=mode, n_pairs=len(pairs),
               pairs=[dict(marks=p["marks"], pos=p["pos"][:60], neg=p["neg"][:60])
                      for p in pairs])
    if mode == "none" or not pairs:
        return list(claims), log
    keep_pos = (drop_choice == "keep_pos")
    drop = set()
    for p in pairs:
        # keep_pos=True ⇒ 保留"正"极性那条 ⇒ 丢"负"那条
        drop.add(p["i"] if not keep_pos else p["j"])
    kept = [c for i, c in enumerate(claims) if i not in drop]
    return kept, log


# ══════════════════════════════════════════════════════════════════════
# §4 行为空间照明（MAP-Elites：行为格，每格留最优）
# ══════════════════════════════════════════════════════════════════════
def behavior_key(frame_ids: Sequence[str], ops: Sequence[str]) -> str:
    """行为描述子 = (认知帧组合, 操作序列) ⇒ 离散格键。

    ★ **不用答案 embedding** ⇒ 绕开 embo-01 在中文句级无分辨率的问题，
      也绕开「措辞相似度在改写型环节失效」的问题（行为是结构性的，不是措辞性的）。
    """
    h = hashlib.sha256()
    h.update(("|".join(sorted(frame_ids))).encode("utf-8"))
    h.update(b"||")
    h.update((">".join(ops)).encode("utf-8"))
    return h.hexdigest()[:16]


class BehaviorArchive:
    """行为空间照明档案。**每格留表现最好的那一个** ⇒ 广度是结构保证的。"""

    def __init__(self) -> Dict[str, Dict[str, Any]]:
        self.cells: Dict[str, Dict[str, Any]] = {}

    def offer(self, key: str, *, payload: str, score: float, meta: Optional[Dict] = None) -> bool:
        """提交一个候选。返回 True = 它成了本格的新最优。"""
        cell = self.cells.get(key)
        if cell is None or score > cell["score"]:
            self.cells[key] = dict(key=key, score=float(score), payload=payload,
                                   meta=dict(meta or {}))
            return True
        return False

    def stats(self) -> Dict[str, Any]:
        scores = [c["score"] for c in self.cells.values()]
        if not scores:
            return dict(n_cells=0, scores=[], mean=0.0, var=0.0, spread=0.0)
        mean = sum(scores) / len(scores)
        var = sum((s - mean) ** 2 for s in scores) / len(scores)
        return dict(n_cells=len(self.cells), scores=sorted(scores),
                    mean=mean, var=var,
                    spread=(max(scores) - min(scores)) if scores else 0.0)

    def dump(self) -> Dict[str, Any]:
        return {k: dict(score=v["score"], meta=v["meta"]) for k, v in self.cells.items()}


# ══════════════════════════════════════════════════════════════════════
# §5 中庸度四指标（★ 全部离散，**不依赖 embedding**）
# ══════════════════════════════════════════════════════════════════════
def common_rate(arm_answers: Sequence[Sequence[str]]) -> float:
    """① **交集率**：所有臂都提到的断言比例 ⇒ 中庸的直接度量。"""
    sets = [set(a) for a in arm_answers if a]
    if len(sets) < 2:
        return 0.0
    inter = set.intersection(*sets)
    union = set.union(*sets)
    return (len(inter) / len(union)) if union else 0.0


def marginal_util(rounds: Sequence[Sequence[str]]) -> List[float]:
    """② **边际利用率**：第 k 轮带来的**新**断言占比 ⇒ **过早闭合的信号**。

    ⚠️ 返回长度 = len(rounds)-1（第一轮没有"边际"）。
    """
    out: List[float] = []
    seen: set = set()
    prev_new = None
    for k, rs in enumerate(rounds):
        cur = set()
        for a in rs:
            cur |= set(a)
        new = len(cur - seen)
        if prev_new is not None:
            total = len(cur) or 1
            out.append(new / total)
        prev_new = new
        seen |= cur
    return out


def dist_to_modal(answer: Sequence[str], all_answers: Sequence[Sequence[str]]) -> float:
    """③ **中庸距离**：与"众数答案"的离散距离（结论集交并比 + 4-gram 距离）。

    ⚠️ **只比同批内相对序**（绝对距离无意义 —— 跨题差 10×）。
    """
    if not answer or not all_answers:
        return 0.0
    scored = []
    for other in all_answers:
        if not other:
            continue
        inter = len(set(answer) & set(other))
        uni = len(set(answer) | set(other))
        jac = 1.0 - (inter / uni if uni else 1.0)
        ga, gb = _ngrams("".join(answer)), _ngrams("".join(other))
        gj = 1.0 - (len(ga & gb) / len(ga | gb) if (ga and gb) else 0.0)
        scored.append((jac + gj) / 2.0)
    if not scored:
        return 0.0
    modal = min(scored)          # 离众数最近的那个
    return max(scored) - modal   # 本答案离众数多远


def coverage_saturation(rounds: Sequence[Sequence[str]], universe: int) -> List[float]:
    """④ **覆盖饱和度**：已找到的断言集合 ÷ |C_t| ⇒ **区分「塌缩/闭合/耗尽」**。"""
    seen: set = set()
    out: List[float] = []
    for rs in rounds:
        for a in rs:
            seen |= set(a)
        out.append(len(seen) / universe if universe else 0.0)
    return out


# ══════════════════════════════════════════════════════════════════════
# §6 工作流
# ══════════════════════════════════════════════════════════════════════
_OUT_SPEC = ("【输出规格】\n"
             "- 只输出 3–6 条，每条一行，行首用「- 」\n"
             "- 每条必须**具体**：带一个数字 / 一个明确条件 / 一个可核查的判断\n"
             "- 不写开场白、不写总结、不写免责说明\n"
             "- 不超过 400 字")


# ⚠️ 2026-10-22 实测（MiniMax-M3.1-Flash-Preview，adaptive thinking）：
#    `max_tokens=2000` ⇒ **两次尝试都被思考块吃光预算**（finish_reason=length,
#    content_len=0）⇒ 返回**空串**。8000 才出正文（309 字符 / 109 秒）。
#    ⇒ 预算阶梯必须**从 8000 起**；2000 这档**不是"可能失败"，是"必然失败"**。
MIN_BUDGET = 8000


def _chat(llm, prompt: str, *, purpose: str, model: str, temp: float = 0.7,
          max_tokens: int = 0, min_ok: int = 20, stats: Optional[Dict] = None):
    """调用包装。**两件事必须同时做到**：

    1. **宽容**：不同客户端支持的 kwargs 不一样 ⇒ 逐级退化，但**不许静默失败**。
    2. **不许把"预算烧光、正文为空"当成功** ⇒ 逐档抬预算重试，
       并把「尝试次数 / 最终 finish_reason / 是否为空」**记进 stats**
       ⇒ **空输出是一条可计数的失败，不是"这条臂没话说"**。

    ⚠️ 这条是从一次真实故障来的：2000 预算 ⇒ 两次 length/0 ⇒ 静默返回空串
       ⇒ 在读数上被误读成"这条臂什么都没产出"。
    """
    base = max(int(max_tokens or 0), MIN_BUDGET)
    ladder = [base] + [b for b in (12000, 16000) if b > base]
    # ★★ 2026-10-22 修：**双阶梯嵌套** ⇒ 一次逻辑调用最多 6 次尝试
    #   旧版：外层 ladder=[8000,12000,16000] × 客户端内层 (mt, +budgets)
    #        ⇒ 8000 → 它的 12000,16000 → 12000 → 16000 → 16000 ⇒ **6 次**
    #        ⇒ 36 次/臂 ⇒ 240s 超时叠加 ⇒ **实测跑 18 小时没结束**
    #   现在：**每次尝试 budgets=()** ⇒ 一次逻辑调用一次尝试，阶梯由我独占控制
    kwargs0 = dict(model=model, temp=temp, max_tokens=base,
                   budgets=(), min_ok=min_ok, purpose=purpose)

    def _call(kw):
        try:
            return llm.chat(prompt, **kw)
        except TypeError:
            for drop in (("budgets",), ("min_ok",), ("budgets", "min_ok"), ("purpose",)):
                kw2 = {k: v for k, v in kw.items() if k not in drop}
                try:
                    return llm.chat(prompt, **kw2)
                except TypeError:
                    continue
        raise RuntimeError("llm.chat 不接受任何已知参数组合（purpose=%s）" % purpose)

    attempts = 0
    last_fr = ""
    text = ""
    for i, mt in enumerate(ladder):
        kw = dict(kwargs0)
        kw["max_tokens"] = mt
        kw["budgets"] = ()          # ★ 一次尝试 = 一次调用（不交给客户端再套一层）
        text = _call(kw) or ""
        attempts += 1
        rec = getattr(llm, "rec", None)
        if rec:
            last_fr = getattr(rec[-1], "finish_reason", "") or ""
        if text.strip() and last_fr != "length":
            break
        # 空 或 预算烧光 ⇒ 抬预算重试（**不静默吞掉**）
    info = dict(purpose=purpose, attempts=attempts, finish_reason=last_fr,
                empty=not bool((text or "").strip()),
                chars=len(text or ""))
    if stats is not None:
        stats.setdefault("calls", []).append(info)
    return text, info


def _extract_claims(llm, text: str, *, model: str, cap: int = 12) -> List[str]:
    """机械抽断言（**不判优劣**，只抽行）。"""
    if not (text or "").strip():
        return []
    prompt = ("从下面这段内容里逐条抄出其中**独立成立的具体判断**。\n"
              "只抄原文里有的，不要改写、不要补充、不要评价。每条一行，行首用「- 」。"
              "最多 %d 条。\n\n内容：\n%s" % (cap, text[:2500]))
    raw, _info = _chat(llm, prompt, purpose="W_extract", model=model, temp=0.0,
                       max_tokens=0, min_ok=10)
    out: List[str] = []
    for ln in (raw or "").splitlines():
        ln = re.sub(r"^\s*[-*\d.、)）]+\s*", "", ln).strip()
        if 8 <= len(ln) <= 160:
            out.append(ln)
    return list(dict.fromkeys(out))[:cap]


class CollapseFixWorkflow:
    """治塌缩工作流。"""

    DEFAULTS = dict(
        n_slots=4,            # 认知槽位数
        seed=0,
        model="",             # 生成侧模型
        judge_model="",       # 评价侧模型（判官）
        max_rounds=2,         # ★ 含演化后重跑 ⇒ 最多两轮
        n_slots_v2=None,      # 第二轮槽位数（默认同 n_slots）
        # ★ 2026-10-22 实测修正：默认**机械汇总**，不用模型汇总
        #   （模型汇总会丢信息，且在 adaptive thinking 下可能直接返回空
        #     ⇒ D01 实测 W 臂 dims=0 vs B0 dims=3）
        #   "model" 档保留当**消融臂**。
        aggregate_mode="mechanical",   # "mechanical" | "model"
        # ★ 冲突仲裁档（**闭合必须是显式、可控、只在必要时**）
        #   "none"     —— 冲突**容忍**：双方保留只标注 ⇒ **不收窄搜索空间**（层2 默认）
        #   "drop_one" —— 冲突对丢一个（丢哪边由策略决定 ⇒ 层3 可学）
        #   "resolve"  —— 有依据支持的一方胜（需判官 ⇒ 贵）
        arbitrate_mode="none",
        # ★★ **层2 / 层3 的分离开关**（2026-10-22 负责人定的四层结构）
        #   层2「用设计的手段优化」= 架构先验设计好、运行时**不自我修改**
        #   层3「用训练/自迭代的手段优化」= 系统**根据自身经验修改自己**
        # ⇒ `evolve=False` ⇒ 层2（固定动作集）；`evolve=True` ⇒ 层3（动作空间会演化）
        # ⇒ ★ **层2 天然就是层3 的消融臂**（只差"演化"这一个自由度）⇒ 干净的嵌套对照
        evolve=True,
        parallel_slots=True,   # ★ 槽位并行（3× 提速：MiniMax 单次 ~50-110 秒）
        # ★ 动作空间两档（★ 这本身是一个消融轴）：
        #   "lookup" = 6 个**人手写死**的模板（⇒ 属于层2 的"设计的手段"）
        #   "policy" = **36 个可组合动作**（三因子）+ 策略选（⇒ 层3 的载体）
        action_mode="lookup",
        policy=None,           # ActionPolicy 或其 export dict；None ⇒ 用 from_lookup()
        policy_seed=20261022,
        wall_clock_s=1800,     # ★ 硬墙钟上限：单臂最多 1800 秒 ⇒ 不许再挂一整夜
        # 层的标签（写进读数，便于归档时区分）
        layer="L3",
    )

    def __init__(self, llm, **cfg):
        self.llm = llm
        self.C = dict(self.DEFAULTS)
        self.C.update(cfg or {})
        self.chat_stats: Dict[str, Any] = {"calls": []}

    # ---------------- 提示词
    def slot_prompt(self, frame_id: str, action, archive: ActionArchive,
                    note: str = "") -> str:
        """按**动作**拼槽位提示。

        ★ 两种动作表示：
          · `action_mode="lookup"`  ⇒ action 是**动作名**（查表模板，人手写死）
          · `action_mode="policy"`  ⇒ action 是 **ActionSpec**（三因子组合）
        """
        fr = _FRAME_BY_ID[frame_id]
        if isinstance(action, tuple):
            body = action_prompt(action, fr["prompt"], note=note)
        else:
            body = archive.template(action).format(frame_prompt=fr["prompt"])
            if note:
                body = body + "\n【上一步出了什么问题】" + note
        return "问题：%s\n\n%s\n\n%s" % (self._ask, body, _OUT_SPEC)

    def aggregate_prompt(self, drafts: Sequence[str], frame_ids: Sequence[str],
                         archive: ActionArchive) -> str:
        """★ 汇总阶段：**只在这一步让模型看别人的稿**（前面全都互不可见）。"""
        pool = "\n\n".join("【草稿 %d】\n%s" % (i + 1, d) for i, d in enumerate(drafts))
        return ("下面是 %d 份**互相独立**产生的草稿（它们互不可见，"
                "分别从不同认知位置出发）。\n"
                "请**只做一件事**：把它们的**不重复**内容合并成一份答案，"
                "**不要**再补充任何新观点，**不要**改写它们的意思。\n\n%s\n\n%s"
                % (len(drafts), pool, _OUT_SPEC))

    # ---------------- 单槽位
    def _run_slot(self, ask: str, frame_id: str, action,
                  archive: ActionArchive, note: str = "") -> Dict[str, Any]:
        self._ask = ask
        prompt = self.slot_prompt(frame_id, action, archive, note=note)
        out, info = _chat(self.llm, prompt, purpose="W_slot_%s" % frame_id,
                          model=self.C["model"], temp=0.7, max_tokens=0,
                          min_ok=20, stats=self.chat_stats)
        claims = _extract_claims(self.llm, out, model=self.C["model"]) if out else []
        return dict(frame_id=frame_id, action=action, draft=out or "",
                    claims=claims, n_calls=2,
                    gen_empty=bool(info.get("empty")),
                    gen_attempts=info.get("attempts"),
                    gen_finish=info.get("finish_reason"))

    # ---------------- 失败判定（★ 驱动动作演化）
    def classify_failure(self, slot: Dict[str, Any], verdicts: Optional[Dict[str, str]],
                         has_conflict: bool = False) -> Optional[str]:
        """**没有独立失败通道 ⇒ 一切照常。** 失败类型决定"要演化出什么新动作"。

        ⚠️ **优先级**：`conflict`（矛盾）> 语义失败 > 空/兜底。
          理由：矛盾是**我们真实观测到**的层2 代价（2026-10-22，D01），
          而且它是**零判官成本**可测的 ⇒ 优先用它当层3 的学习信号。
        """
        if has_conflict:
            return "conflict"
        claims = slot.get("claims") or []
        if not claims:
            # ★ 区分两种"空"：**生成被预算烧光** vs **生成成功但抽不出断言**
            #   前者是**仪器故障**（必须被计数、且要演化出更省预算的动作）
            return "empty"
        if verdicts:
            sup = sum(1 for c in claims if verdicts.get(c) == "支持")
            con = sum(1 for c in claims if verdicts.get(c) == "矛盾")
            if sup == 0 and con == 0:
                return "all_unmentioned"
            if sup == 0:
                return "zero_load_bearing"
        if len(slot.get("draft") or "") < 60:
            return "fallback"
        return None

    # ---------------- 主流程
    def run(self, ask: str, *, verdicts_for=None) -> Dict[str, Any]:
        """跑一遍工作流。

        参数
        ----
        ask         题面
        verdicts_for  可选：把"断言 → 依据判定"的映射传进来（用于**失败分类**）
                       —— 由**评价侧**提供（判官），工作流本身不接触依据包。
        """
        C = self.C
        archive = ActionArchive()
        illum = BehaviorArchive()
        ops: List[str] = []
        rounds: List[List[str]] = []
        arm_records: List[Dict[str, Any]] = []
        failures: Dict[str, int] = {}

        # ── 策略先建立（架构自由度要用它选）★ 顺序：policy/_rng 必须在此之前
        _pol_src = C.get("policy")
        if _pol_src is None:
            policy = ActionPolicy.from_lookup()
        elif isinstance(_pol_src, dict):
            policy = ActionPolicy.load(_pol_src)
        else:
            policy = _pol_src
        _rng = random.Random(int(C.get("policy_seed", 20261022)) + 7919)

        # ★★ 架构自由度交给策略（"该不该发散" + "怎么合并"是**学出来的**）
        _arch_pick = None
        _merge_mode = C.get("merge_mode", "mechanical")
        if policy is not None and C.get("learn_architecture", True):
            _nf, _mm = policy.choose_architecture("conflict", _rng)
            _arch_pick = (int(_nf), str(_mm))
            C = dict(C)
            C["n_slots"] = int(_nf)
            _merge_mode = str(_mm)
            ops.append("ARCH[%df/%s]" % (int(_nf), _mm))
        frames = select_frames(C["n_slots"], seed=C["seed"], frame_seed=self.frame_seed)
        # 第 0 轮：基线动作
        # 初始动作：lookup 模式 ⇒ "base"（无修法）；policy 模式 ⇒ ("none","slot",0)
        _base_action = ("none", "slot", 0) if C.get("action_mode") == "policy" else "base"
        cur_actions = {fid: _base_action for fid in frames}
        slot_notes: Dict[str, str] = {}
        _arb_meta = None
        # ★ 策略：lookup 模式 ⇒ **手写映射**（层2 的"设计的手段"）
        #         policy 模式 ⇒ 传入的权重（w=0 ⇒ 均匀 ⇒ 未训练基线）
        n_rounds = max(1, int(C["max_rounds"]))
        slot_claims: List[List[str]] = []
        slot_records: List[Dict[str, Any]] = []
        slot_ids: List[str] = []
        n_conflicts_total = 0

        for rnd in range(n_rounds):
            drafts: List[str] = []
            slot_claims: List[List[str]] = []
            slot_records: List[Dict[str, Any]] = []
            slot_ids: List[str] = []

            # ── 1) 发散（★ 槽位互不可见：每个槽位只拿题面 + 自己的帧 + 自己的动作）
            #    ★ 2026-10-22：**并行**跑槽位（互不依赖 ⇒ 天然可并行）
            #      MiniMax 单次调用 ~50–110 秒 ⇒ 串行 3 槽 = 3× 等待
            #      ⇒ 并行后 ≈ 1× 等待（**3× 提速**，三天真跑得完的关键）
            def _one_slot(fid):
                return self._run_slot(ask, fid, cur_actions[fid], archive,
                                      note=slot_notes.get(fid, ""))

            if C.get("parallel_slots", True) and len(frames) > 1:
                with ThreadPoolExecutor(max_workers=min(len(frames), 4)) as _ex:
                    _slots = list(_ex.map(_one_slot, frames))
            else:
                _slots = [_one_slot(f) for f in frames]
            for fid, slot in zip(frames, _slots):
                slot_ids.append(fid)
                slot_records.append(slot)
                drafts.append(slot["draft"])
                slot_claims.append(slot["claims"])
                ops.append("GEN[%s:%s]" % (fid, cur_actions[fid]))

            # ── 2) 去冗余（跨槽位）+ ★ 矛盾检测（跨槽位，**零判官成本**）
            flat = [c for cs in slot_claims for c in cs]
            kept = dedup(flat)
            kept_set = set(kept)
            rounds.append([c for cs in slot_claims for c in cs])

            # ★ 矛盾检测：把扁平下标映射回槽位
            conflicts = detect_conflicts(flat)
            conflict_slots = set()
            for cf in conflicts:
                for idx, _c in cf.get("items") or []:
                    acc = 0
                    for si, cs in enumerate(slot_claims):
                        if acc <= idx < acc + len(cs):
                            if si < len(slot_ids):
                                conflict_slots.add(slot_ids[si])
                            break
                        acc += len(cs)
            n_conflicts_total += len(conflicts)
            if conflicts:
                ops.append("CONFLICT[%d]" % len(conflicts))

            # ── 3) 失败判定 → ★ 动作演化
            #    ★★ **层2 / 层3 的分叉点**（2026-10-22）：
            #      层2（`evolve=False`）：**只记录失败、不据以改动作** ⇒ 架构是先验设计的，
            #            运行时不自修改。层3（`evolve=True`）：从失败**构造新动作**。
            #      ⇒ 层2 天然就是层3 的消融臂（只差这一个自由度）⇒ 干净的嵌套对照。
            new_actions: Dict[str, str] = {}
            for slot in slot_records:
                fk = self.classify_failure(
                    slot, verdicts_for,
                    has_conflict=(slot["frame_id"] in conflict_slots))
                if fk:
                    failures[fk] = failures.get(fk, 0) + 1
                    if not C.get("evolve", True):
                        continue                       # ★ 层2：记失败，但**不改动作**
                    if C.get("action_mode") == "policy":
                        # ★ 层3：**策略选动作**（可学）⇒ 动作是三因子组合
                        spec = policy.choose(fk, _rng)
                        nm = "act_%s_%s_%d" % spec
                        archive.add(nm, "", born_from="%s@%s" % (fk, slot["frame_id"]),
                                    evidence="policy|%s|%s|%d" % spec)
                        new_actions[slot["frame_id"]] = spec
                        slot_notes[slot["frame_id"]] = failure_note(fk)
                    else:
                        # 查表（人手写死的模板）⇒ 属于"设计的手段"
                        nm = propose_new_action(fk, slot["frame_id"], archive)
                        if nm:
                            new_actions[slot["frame_id"]] = nm
                            slot_notes[slot["frame_id"]] = failure_note(fk)
            if not new_actions:
                break                       # 没有失败 ⇒ 不演化（★ 不无节制扩动作空间）

            # ── 4) 重跑（用**各自的新动作**）⇒ 搜索空间在这一步变大
            # ⚠️ **合并**而不是替换：没失败的槽位要**保留原动作**
            #    （2026-10-22 实测 bug：`dict(new_actions)` 会把其余槽位的动作冲掉
            #      ⇒ 第二轮 KeyError。**只有真跑 + 真演化才会触发**。）
            cur_actions = dict(cur_actions)
            cur_actions.update(new_actions)
            slot_notes = {}                 # 失败描述只在下一轮用一次
            ops.append("EVOLVE[%s]" % ",".join(
                sorted({_action_name(v) for v in new_actions.values()})))

        # ── 5) 汇总
        #    ★★ 2026-10-22 **实测修正**：默认改**机械汇总**，不用模型汇总。
        #    实测：模型汇总（合并 3 份稿）在 MiniMax adaptive thinking 下
        #    **预算被吃光 ⇒ 汇总为空 ⇒ 整条答案的承重维度直接变成 0**
        #    （D01 实测：W 臂 dims=0 vs B0 直调 dims=3；13 次实际调用 vs 8 次逻辑调用
        #      ⇒ 多出的 5 次全是预算烧光后的重试）。
        #    ⇒ 机械汇总（各槽位分别抽断言 → 离散去冗余 → 直接装配）
        #       **又快、不丢、且符合我们既有的「装配必须机械，不由模型重写」纪律**。
        #    "model" 档保留下来当**消融臂**（单独测「模型汇总 vs 机械汇总」的净损失）。
        final_drafts = [s["draft"] for s in slot_records] if slot_records else []
        all_slot_claims = [c for cs in slot_claims for c in cs]

        if C.get("aggregate_mode") == "model":
            if len(final_drafts) > 1:
                agg, _ai = _chat(self.llm,
                                 self.aggregate_prompt(final_drafts, frames, archive),
                                 purpose="W_aggregate", model=self.C["model"],
                                 temp=0.3, max_tokens=0, min_ok=20, stats=self.chat_stats)
                ops.append("AGGREGATE(model)")
            else:
                agg = (final_drafts[0] if final_drafts else "")
            # 装配（模型汇总档：仍走机械抽取 + 去冗余）
            final_claims = dedup(_extract_claims(self.llm, agg, model=self.C["model"])) if agg else []
            if not final_claims:
                final_claims = dedup(all_slot_claims)
        else:
            # ★ 机械汇总：**不丢任何一条**，也不多花一次调用
            _mg = merge_claims(all_slot_claims, _merge_mode)
            final_claims = _mg["claims"]
            ops.append("AGGREGATE(%s)" % _merge_mode)
            # ★★ 跨槽位冲突仲裁（层2 默认"容忍"⇒ 不收窄搜索空间）
            _am = C.get("arbitrate_mode", "none")
            _arb_pick = None
            if _am == "learned" and policy is not None:
                # ★ 层3：**仲裁的选择也由策略给出**（mark / keep_pos / keep_neg）
                _arb_pick = policy.choose_arbitration("conflict", _rng)
                _am = ("none" if _arb_pick == 0 else "drop_one")
            _before = len(final_claims)
            final_claims, _alog = arbitrate(
                final_claims, _am,
                drop_choice=("keep_pos" if _arb_pick == 1 else "keep_neg"))
            if _alog["n_pairs"]:
                ops.append("ARBITRATE[%s:%d对]" % (_am, _alog["n_pairs"]))
                _arb_meta = dict(log=_alog, pick=_arb_pick,
                                 dropped=_before - len(final_claims),
                                 mode=_am)
            agg = "\n".join("- " + c for c in final_claims)

        # ── 6) 装配（机械汇总档已经装配好了 ⇒ 这里**不再二次抽取**）
        #    ⚠️ 2026-10-22 实测修正：原实现在机械汇总之后**又抽一次断言**，
        #    那一次既是**多花的调用**，又会把刚装配好的内容**再丢一遍**。
        if C.get("aggregate_mode") != "model":
            pass                       # 已装配，不动
        else:
            final_claims = dedup(_extract_claims(self.llm, agg, model=self.C["model"])) if agg else []
            if not final_claims:
                final_claims = dedup(all_slot_claims)

        # ── 7) 照明归档 + 中庸度记账
        bkey = behavior_key(frames, ops)
        illum.offer(bkey, payload=agg, score=len(final_claims),
                    meta=dict(frames=list(frames), ops=list(ops),
                              n_actions=len(archive.actions)))

        # ★ 记录**每条分支**（每槽位一条）⇒ 供"路径间多样性 / 思维跳跃"用
        _paths = []
        for _i, _fr in enumerate(frames):
            _ops = [o for o in ops if o.startswith("GEN[%s:" % _fr)]
            _claims = slot_claims[_i] if _i < len(slot_claims) else []
            _paths.append(dict(kind="frame", frame=_fr, ops=_ops, claims=_claims))
        return dict(
            paths=_paths,
            arbitration=(_arb_meta if "_arb_meta" in dir() else None),
            arch_pick=_arch_pick, merge_mode=_merge_mode,
            n_conflicts_merge=_mg.get("n_conflicts") if "_mg" in dir() else None,
            arbitration_pick=(_arb_meta or {}).get("pick"),
            n_conflicts_final=len(detect_opposite_pairs(final_claims)),
            chat_stats=self.chat_stats,
            layer=C.get("layer"),
            evolve=bool(C.get("evolve", True)),
            answer=agg, claims=final_claims, frames=list(frames), ops=list(ops),
            rounds=rounds, archive=archive.stats(), illum=illum.stats(),
            failures=dict(failures),
            n_conflicts=n_conflicts_total,
            action_mode=C.get("action_mode"),
            policy_params=policy.export(),
            policy_param_count=policy.param_count(),
            slot_records=[dict(frame_id=s["frame_id"], action=s["action"],
                               n_claims=len(s["claims"]),
                               n_chars=len(s["draft"])) for s in slot_records],
        )
