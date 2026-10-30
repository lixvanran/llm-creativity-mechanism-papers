#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scatter_arms.py —— 「把注意力完全拆散」的三臂实现（★ 路级可并行 ★）

★★★ 机制（★ 按用户思路，★ 不加自创机制 ★）★★
把注意力完全拆散 ＝ 每一路 agent **从零开始**：
  · 自己决定从哪个角度回答（**不共享任何人的角度**）
  · 只在自己这一路的上下文里作答（**互不可见**、**无顺序依赖**）
  · **没有跨路的早停信号**（★ 前一路没产出，不会吃掉后一路的注意力预算 ★）
  · 最后**机械并集**（★ 不投票、不取交集、不 LLM 融合 ★）

★★ 三臂只差【一个变量】：角度是「共享一份」还是「各自一份」 ★★
  A1 shared_frame ：1 次 builder 造出 N 个角度 → N 路共用（★ 共同锚点 ★）
  A2 scatter      ：N 路**各自**独立 builder → 第 k 路用**自己那份**的第 k 个角度（★ 主臂 ★）
  A3 multi_sample ：不定角度（＝ direct 臂的裸题，prompt 逐字相同），采样 N 次

★ 提示词沿用 l0/agent.py 原文（★ 只把「数量 4–7 个」参数化为「恰好 N 个」★）
★ 尺子沿用 exp/dims-2026-10-26/ 的 dimtax（★ 本文件不造任何判据 ★）
"""

import json

# ★ 与 probe_dims.py 完全一致的裸题（★ direct n=30 的地板就是它 ★）
QUESTION = "湖北物理类620分，想学AI，怎么选择大学？"

# ★ 抄 l0/agent.py 的 BUILD_M_P（★ 只改数量 ★）
BUILD_P = """目标：
{goal}

★ 你现在**还没有开始回答**这个目标。第一步只做一件事：**你自己决定这个目标应该从哪些角度被考虑**。

要求：
1. **只列角度、★ 不给结论**（★ 结论是后面的事 ★）
2. 每个角度必须写清：它关注什么、它**可能与其它角度得出不同答案**（★ 这条是硬要求 ★）
3. 角度之间必须**真的可区分** —— ★ 如果两个角度必然导出同一结论，★ 就合并成一个 ★
4. 数量 **恰好 {n} 个**
5. ★ 至少包含 1 个「★ 容易被漏掉、★ 但可能改变答案 ★」的角度 ★

只输出 JSON（★ 不要任何解释文字 ★）：
{{"angles": [{{"id": "A1", "angle": "...", "why_differs": "...", "likely_missed": true}}]}}"""

# ★ 抄 l0/agent.py 的 SOLVE_M_P（★ 逐字 ★）
SOLVE_P = """目标：
{goal}

你选定的切入角度：**{angle}**
（你选它是因为：{why}）

★ 只沿这个角度作答 —— 不要顺带把别的角度也答了（★ 那是后面的轮次的事 ★）。
先说你的推理与依据，再给出你的结论。

用中文。"""

BUILD_SYSTEM = "你是一个问题空间构建者。你的价值在于**不遗漏**。"


def parse_angles(txt):
    """★ 解析 builder 的 JSON（★ 失败必须可计数、★ 不静默 ★）"""
    try:
        blob = txt[txt.index("{"): txt.rindex("}") + 1]
        arr = json.loads(blob).get("angles", []) or []
    except Exception:                                   # noqa: BLE001
        return []
    return [a for a in arr if isinstance(a, dict) and a.get("angle")]


def build_angles(llm, goal, n):
    """★ 造 N 个角度（★ 返回 (angles, ok) ★）"""
    txt, ok = llm.chat(BUILD_P.format(goal=goal, n=n), system=BUILD_SYSTEM, max_tokens=6000)
    if not ok:
        return [], False
    angles = parse_angles(txt)
    if not angles:
        return [], False
    return angles, True


def solve_angle(llm, goal, angle, why):
    """★ 沿一个角度作答（★ 返回 (text, ok) ★）"""
    return llm.chat(SOLVE_P.format(goal=goal, angle=angle, why=why), max_tokens=6000)


# ---------------------------------------------------------------- 路级任务

def route_scatter(llm, goal, n, route):
    """★ A2 的一路：★ 独立造角度 → 只沿自己那份的第 route 个角度作答 ★"""
    angles, ok = build_angles(llm, goal, n)
    if not ok:
        return {"route": route, "angle": "", "text": "", "ok": False, "stage": "build"}
    a = angles[route] if route < len(angles) else angles[-1]
    text, sok = solve_angle(llm, goal, a.get("angle", ""), a.get("why_differs", ""))
    return {"route": route, "angle": a.get("angle", ""), "text": text, "ok": sok,
            "stage": "solve"}


def route_shared(llm, goal, route, angles):
    """★ A1 的一路：沿【共享那份】角度表的第 route 个角度作答 ★"""
    if not angles:
        return {"route": route, "angle": "", "text": "", "ok": False, "stage": "build"}
    a = angles[route] if route < len(angles) else angles[-1]
    text, sok = solve_angle(llm, goal, a.get("angle", ""), a.get("why_differs", ""))
    return {"route": route, "angle": a.get("angle", ""), "text": text, "ok": sok,
            "stage": "solve"}


def route_sample(llm, goal, route):
    """★ A3 的一路：★ 裸题采样（★ prompt 与 direct 臂逐字相同 ★）"""
    text, ok = llm.chat(goal, max_tokens=6000)
    return {"route": route, "angle": "", "text": text, "ok": ok, "stage": "sample"}


def route_direct(llm, goal):
    """★ A0 同参地板的一路：★ 裸题直调（★ prompt 与 direct 臂逐字相同 ★）"""
    text, ok = llm.chat(goal, max_tokens=24000)
    return {"route": 0, "angle": "", "text": text, "ok": ok, "stage": "sample"}


def build_shared(llm, goal, n):
    """★ A1 的共享 builder（★ 一次性、★ 所有路共用它的输出 ★）"""
    angles, ok = build_angles(llm, goal, n)
    return {"angles": angles, "ok": ok}
