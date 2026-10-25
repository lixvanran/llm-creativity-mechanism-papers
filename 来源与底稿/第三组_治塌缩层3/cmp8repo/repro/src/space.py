# -*- coding: utf-8 -*-
"""搜索空间拓展 & 思维跳跃的**零判官**度量

> 2026-10-23 ｜ 配套论文 §6.4 ｜ **这是回到核心目标的主指标**

## 为什么必须零判官
我们实测：**判官读数的中位波动 = 1**（即使换成最理想的 non-thinking 判官，n=12），
而维度数本身只有 1–5 ⇒ ⇒ **任何 ≤1 的架构级效应在原理上就看不见**（§6.2c）。
⇒ ⇒ **架构"搜索空间确实拓展了"这件事，不能靠判官读数来证明** ——
⇒ ⇒ 必须用**不依赖判官的、结构性的**度量来证明。

## 三个指标（全部纯程序计算 ⇒ 零噪声）

| 指标 | 定义 | 对应用户目标 |
|---|---|---|
| **路径间多样性** `path_diversity` | N 条并行分支**彼此**的 Self-Sim（**越低越分散**）| **搜索空间拓展能力** |
| **思维跳跃** `ops_entropy` | 单条路径的**操作序列 n-gram 熵**（归一化）⇒ 跳得有多"不规则" | **思维跳跃能力** |
| **认知位置覆盖** `frame_coverage` | 用了几种不同的认知位置（帧）| 拓展的**来源**是否多样 |

### 公平性（关键）
`B0_bestof3`（等预算臂）的 N 条分支 = **N 次独立直调**；
`W`（层2/层3）的 N 条分支 = **N 个不同认知位置**。
⇒ ⇒ **两者都是"N 条并行分支"** ⇒ ⇒ **路径间多样性直接可比**
⇒ ⇒ ★ **这才是"搜索空间拓展"的干净证据**：不是"我们调用得多"，而是
**"同样数量的并行分支，我们彼此更不一样"**。

★ Self-Sim 口径：Lake, Choi & Durrett, **NAACL 2025** (arXiv:2406.17692) —— 有出处、零 embedding。
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence

import metrics_priorart as MP


# ══════════════════════════════════════════════════════════════════════
# 1. 路径间多样性（搜索空间拓展）
# ══════════════════════════════════════════════════════════════════════
def path_diversity(paths: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """N 条并行分支**彼此**的重叠度（**越低越分散**）。

    ★ 2026-10-22 修正（口径错了 ⇒ 指标不区分）：
      先前把"每个分支的 claims 列表"当成**一个族**来比 ⇒ ⇒ 三条不同分支必然完全不同
      ⇒ ⇒ **所有臂都是 0** ⇒ 指标零分辨力。
      ⇒ ⇒ **正确粒度 = 字符 2-gram 集合**（**Self-Sim 的原口径**，Lake et al. NAACL'25）：
      "把每个响应转成唯一词干集合，对所有响应两两算 Jaccard 并取平均"
      ⇒ ⇒ claim 级**精确匹配**太严（三条分支一个字都不重合 ⇒ 恒 0 ⇒ 零分辨力）
      ⇒ ⇒ 2-gram 粒度才有分辨率，且**有出处**。
    """
    cl = [list(p.get("claims") or []) for p in (paths or [])]
    cl = [c for c in cl if c]
    if len(cl) < 2:
        return dict(n_paths=len(cl), self_sim=None, pair_self_sim=None,
                    distinct=None, note="分支数 < 2 ⇒ 无法算路径间多样性")
    ss = MP.self_sim(cl, mode="bigram")          # ★ Self-Sim 原口径（2-gram 集合）
    sets = [set(c) for c in cl]
    exact = []
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            a, b = sets[i], sets[j]
            uni = len(a | b)
            exact.append((len(a & b) / float(uni)) if uni else 0.0)
    return dict(n_paths=len(cl), self_sim=ss, pair_self_sim=ss,
                exact_match_jaccard=(sum(exact) / len(exact)) if exact else None,
                distinct=len(set().union(*sets)),
                note="Self-Sim 原口径（2-gram 集合两两 Jaccard）；越低 ⇒ 分支越分散 ⇒ 搜索空间越宽")


# ══════════════════════════════════════════════════════════════════════
# 2. 思维跳跃（操作序列的"不规则度"）
# ══════════════════════════════════════════════════════════════════════
def ops_entropy(ops: Sequence[str], n: int = 2) -> Dict[str, Any]:
    """操作序列的 n-gram 熵（归一化到 [0,1]）⇒ **跳得有多不规则**。

    ★ 熵高 = 路径不总是同一步 ⇒ ⇒ **有"跳"**；
      熵低 = 一直在同一条轨道上 ⇒ ⇒ **没跳**（哪怕总步数一样）。
    ★ 归一化：H / log(不同 n-gram 数) ⇒ 跨不同长度的序列可比。
    """
    # ★ 扁平化：某些臂的 ops 里会嵌一层 list（每条路径一个子列表）
    _flat = []
    for o in (ops or []):
        if isinstance(o, (list, tuple)):
            _flat.extend([x for x in o if isinstance(x, str)])
        elif isinstance(o, str):
            _flat.append(o)
    seq = [o for o in _flat if o]
    if len(seq) < n:
        return dict(n_ops=len(seq), entropy=None, distinct_ngrams=0,
                    note="操作数 < n ⇒ 无法算 n-gram 熵")
    grams = ["\x00".join(seq[i:i + n]) for i in range(len(seq) - n + 1)]
    cnt = Counter(grams)
    tot = float(len(grams))
    H = -sum((c / tot) * math.log(c / tot) for c in cnt.values())
    D = len(cnt)
    return dict(n_ops=len(seq), entropy=H, distinct_ngrams=D,
                norm_entropy=(H / math.log(D)) if D > 1 else 0.0,
                seq=seq)


# ══════════════════════════════════════════════════════════════════════
# 3. 认知位置覆盖
# ══════════════════════════════════════════════════════════════════════
def frame_coverage(frames: Sequence[str]) -> Dict[str, Any]:
    """用了几种认知位置（帧）⇒ 拓展的**来源**是否多样。"""
    fs = [f for f in (frames or []) if f]
    return dict(n_frames=len(fs), n_distinct=len(set(fs)), frames=sorted(set(fs)))


# ══════════════════════════════════════════════════════════════════════
# 汇总：一个臂的全部零判官指标
# ══════════════════════════════════════════════════════════════════════
def space_report(arm: Dict[str, Any]) -> Dict[str, Any]:
    """从一条臂的记录里算全部零判官指标。"""
    paths = arm.get("paths") or []
    if not paths:
        # 退化：从 ops 里切（GEN[...] 是每条分支一条）
        paths = [dict(claims=[], ops=[o]) for o in (arm.get("ops") or [])]
    out = dict(arm=arm.get("arm"),
               path_diversity=path_diversity(paths),
               frame_coverage=frame_coverage(arm.get("frames") or []),
               ops_entropy=ops_entropy(arm.get("ops") or []))
    # 每条分支各自的思维跳跃
    per = [ops_entropy(p.get("ops") or []) for p in paths if p.get("ops")]
    ent = [p["norm_entropy"] for p in per if p.get("norm_entropy") is not None]
    out["branch_entropy"] = dict(per_branch=per,
                                 mean_norm_entropy=(sum(ent) / len(ent)) if ent else None)
    return out
