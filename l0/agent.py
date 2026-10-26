#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l0/agent.py —— L0 Agent：自主构建问题空间的最小实现

★★★ 本项目的总目标（★ 每一行代码都要能回答「Agent 该改哪里」★★）
======================================================================
做出一个能解决「搜索空间塌缩 / 过早闭合 / 问题空间自主构建」的 Agent。
链条 G→M→S→X→A，★ 重点在 G→M→S（★ 不是 X→A ★）。
实验只是下层落实；★ 本文件的产出是【一个 Agent 本身】+【它的路径轨迹】+【它自己的收敛声明】★★

★★★ 本文件【不是尺子】★★
======================================================================
★ 它不产出"注意力熵"这类代理量表；★ 它产出的是一个能跑的 Agent：
  · 它**自己**决定该考虑哪些角度（★ 人不给清单、★ 不给维度 ★）—— 这就是 M
  · 每个角度是一条**可分叉的路径**（★ 不是身份多样、★ 是路径多样 ★）—— 这就是 S
  · 它**自己**算边际利用率、**自己**决定何时停止、**自己**报"这轮没找到新维度"—— A3 内化
★ 任何一条读数若不能回答「Agent 该改哪里」，就不是本项目的产出。

★★★ 三条验收（A1/A2/A3）★★
======================================================================
A1 展开度可测：每轮能算出「结论集覆盖 / 有效维度数」
A2 不早闭合：边际利用率**不提前掉零**（掉零位置与预算无关 ⇒ 不是"没预算了"）
A3 可诊断  ：★ Agent 自己能报"这一轮我没找到新维度" ⇒ marginal_util 是**运行时信号**、
              不是事后测出来的 ⇒ ★ 这是它与"多采样几次"的分界线 ★
"""

import json
import re
import unicodedata

# ---------------------------------------------------------------- 归一化与去重

_PUNCT = re.compile(r"[\s，。、；：？！（）()【】\[\]\"'“”‘’·,.;:?!\-/—–_~`+*=<>|]+")


def norm_key(s):
    """★ 结论去重的 key（★ 保守口径 ★）

    ★ **刻意不做语义相似度** —— 字面相似度在本项目里是【反向指标】。
    ★ 这里只用【归一化后的精确匹配】⇒ 同一件事换个措辞会被算成两条 ⇒
    ★ **宁可高估有效维度、★ 不可低估**（★ 高估的方向是"显得 Agent 更好"★ ⇒
    ★ ★ 属���必须在报告里写明的保守方向 ★★）
    """
    s = unicodedata.normalize("NFKC", s or "")
    s = _PUNCT.sub("", s)
    return s


def dedup(claims):
    """★ 去重后的结论单元（★ 顺序保留 ★）"""
    seen, out = set(), []
    for c in claims:
        k = norm_key(c)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(c.strip())
    return out


# ---------------------------------------------------------------- prompts

BUILD_M_P = """目标：
{goal}

★ 你现在**还没有开始回答**这个目标。第一步只做一件事：**你自己决定这个目标应该从哪些角度被考虑**。

要求：
1. **只列角度、★ 不给结论**（★ 结论是后面的事 ★）
2. 每个角度必须写清：它关注什么、它**可能与其它角度得出不同答案**（★ 这条是硬要求 ★）
3. 角度之间必须**真的可区分** —— ★ 如果两个角度必然导出同一结论，★ 就合并成一个 ★
4. 数量 **4–7** 个
5. ★ 至少包含 1 个「★ 容易被漏掉、★ 但可能改变答案 ★」的角度 ★

只输出 JSON（★ 不要任何解释文字 ★）：
{{"angles": [{{"id": "A1", "angle": "...", "why_differs": "...", "likely_missed": true}}]}}"""

SOLVE_M = """目标：
{goal}

你选定的切入角度：**{angle}**
（你选它是因为：{why}）

★ 只沿这个角度作答 ★ —— 不要顺带把别的角度也答了（★ 那是后面的轮次的事 ★）。
先说你的推理与依据，再给出你的结论。

用中文。"""

EXTRACT_C = """下面是一个回答。请抽出其中**你明确主张成立**的结论，每条一句话、★ 不要带推理过程 ★。

【回答】
{text}

只输出 JSON：{{"claims": ["...", "..."]}}"""

DIRECT_M = """目标：
{goal}

请直接作答。★ 一次给全、★ 不要展开多个角度 ★ —— 把你认为最直接的那条思路走到底。
先说推理与依据，再给出结论。

用中文。"""


# ---------------------------------------------------------------- Agent

class ProblemSpaceAgent:
    """★ 自主构建问题空间的 Agent（★ L0 的最小实现 ★）"""

    def __init__(self, llm, goal, max_angles=7, zero_rounds_to_stop=2):
        self.llm = llm
        self.goal = goal
        self.max_angles = max_angles
        self.zero_rounds_to_stop = zero_rounds_to_stop

        # ---- 内部状态（★ 全是运行时状态、★ 不是事后统计 ★）
        self.representation = []        # M：自己造的角度清单
        self.claims = []                # 去重后的结论单元（跨轮累积）
        self._claim_keys = set()
        self.trail = []                 # 每轮的边际利用率轨迹
        self.diagnostics = []           # ★ A3：Agent 自己的诊断信号 ★
        self.stopped_reason = None
        self.zero_streak = 0

    # -------------------------------------------------- Step 0：造 M
    def build_representation(self):
        txt, ok = self.llm.chat(BUILD_M_P.format(goal=self.goal),
                                system="你是一个问题空间构建者。你的价值在于**不遗漏**。",
                                max_tokens=6000)
        angles = []
        if ok:
            try:
                blob = txt[txt.index("{"): txt.rindex("}") + 1]
                angles = json.loads(blob).get("angles", []) or []
            except Exception as e:                       # noqa: BLE001
                self.diagnostics.append("M 解析失败：%s" % str(e)[:60])
        if not angles:
            # ★ 失败不许静默：★ 记进诊断、★ 并让 Agent 明确知道自己没拿到 M ★
            self.diagnostics.append("★ 没能造出 M（★ 解析失败或通道失败 ★）")
        self.representation = angles[: self.max_angles]
        return self.representation

    # -------------------------------------------------- Step 1/2：逐轮探索
    def _add_claims(self, raw_claims):
        new = []
        for c in raw_claims:
            k = norm_key(c)
            if not k or k in self._claim_keys:
                continue
            self._claim_keys.add(k)
            new.append(c.strip())
        self.claims.extend(new)
        return new

    def _solve_angle(self, ang):
        """★ 走一条路径：作答 → 抽结论 → 落成新的结论单元 ★

        ★ ★ 返回 (新结论, 产出条数, 通道是否成功) ★★
        ★ **通道失败必须与「真的没找到新维度」分开** —— 否则一次 API 失败会被
        ★ 记成「这轮没找到新维度」⇒ **失败路径静默归零** ⇒ ★ 违反纪律 ★★
        """
        a_txt, a_ok = self.llm.chat(
            SOLVE_M.format(goal=self.goal, angle=ang.get("angle", ""),
                           why=ang.get("why_differs", "")),
            max_tokens=6000)
        if not a_ok:
            self.diagnostics.append("★ 角度 %s 作答失败（★ 通道失败、★ 不计入零轮 ★）"
                                     % ang.get("id", "?"))
            return [], 0, False
        e_txt, e_ok = self.llm.chat(EXTRACT_C.format(text=a_txt), max_tokens=3000)
        if not e_ok:
            self.diagnostics.append("★ 角度 %s 抽结论失败（★ 通道失败、★ 不计入零轮 ★）"
                                     % ang.get("id", "?"))
            return [], 0, False
        try:
            blob = e_txt[e_txt.index("{"): e_txt.rindex("}") + 1]
            claims = json.loads(blob).get("claims", []) or []
        except Exception as e:                           # noqa: BLE001
            self.diagnostics.append("★ 角度 %s 抽结论解析失败：%s（★ 不计入零轮 ★）"
                                     % (ang.get("id", "?"), str(e)[:50]))
            return [], 0, False
        return self._add_claims(claims), len(claims), True

    def explore(self):
        """★ 逐角度探索、★ 每轮记边际利用率、★ 连续掉零就自己停并自报 ★"""
        if not self.representation:
            self.build_representation()
        for i, ang in enumerate(self.representation):
            new_claims, produced, ch_ok = self._solve_angle(ang)
            mu = (len(new_claims) / produced) if produced else 0.0
            self.trail.append({
                "round": i + 1,
                "angle_id": ang.get("id", "A%d" % (i + 1)),
                "angle": ang.get("angle", "")[:120],
                "likely_missed": bool(ang.get("likely_missed")),
                "claims_produced": produced,
                "claims_new": len(new_claims),
                "marginal_util": round(mu, 4),
                "cumulative_claims": len(self.claims),
                "channel_ok": ch_ok,
            })
            if not ch_ok:
                # ★ 通道失败 ⇒ ★ 不算「没找到新维度」★ ⇒ ★ 也不计零轮 ★
                continue
            if len(new_claims) == 0:
                self.zero_streak += 1
                if self.zero_streak >= self.zero_rounds_to_stop:
                    # ★★★ A3：★ Agent 自己报"这一轮我没找到新维度" ★★★
                    self.diagnostics.append(
                        "★ 这一轮我没找到新维度（marginal_util = 0，★ 连续 %d 轮 ★）"
                        % self.zero_streak)
                    self.stopped_reason = "marginal_util_zero"
                    break
            else:
                self.zero_streak = 0
        return self.trail

    # -------------------------------------------------- 输出
    def report(self):
        return {
            "goal": self.goal,
            "representation_M": self.representation,
            "n_angles": len(self.representation),
            "claims": self.claims,
            "n_claims": len(self.claims),
            "trail": self.trail,
            "diagnostics": self.diagnostics,
            "stopped_reason": self.stopped_reason,
            "self_reported_no_new_dimension": any(
                "没找到新维度" in d for d in self.diagnostics),
        }
