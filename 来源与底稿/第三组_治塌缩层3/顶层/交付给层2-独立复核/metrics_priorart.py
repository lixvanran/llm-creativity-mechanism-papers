# -*- coding: utf-8 -*-
"""度量层 · **换成有出处的口径**（2026-10-22 先例审计后）

> 依据 `LIT/DEEP-MEDIANITY-PRIORART.md`（逐条核实过 arXiv id / venue）

## 为什么有这份文件
我们原先自造了四个指标（交集率 / 边际利用率 / 中庸距离 / 覆盖饱和度）。
先例审计的结论是：**三个的"形"已经被做过了** ⇒ 继续用自造名字会被审稿人当作
"不知道有前人工作" ⇒ ⇒ **正确动作不是"换掉"或"不换"，而是：换口径 + 引用，
保留我们的数据组织（`family_key` 等价类）。**

## 换用/对齐清单（逐条带出处）

| 我们的旧指标 | 换成 | 出处 | 本文件里的实现 |
|---|---|---|---|
| 交集率 | **多数票份额** + **#distinct** + **离散语义熵 DSE** | Self-Consistency (ICLR'23) / Kuhn et al. (ICLR'23, arXiv:2302.09664) | `majority_share` / `distinct_families` / `dse` |
| 边际利用率 | **ESS**（1/Σw²）+ 逐轮曲线 | ePF (arXiv:2510.05825) | `ess` / `marginal_util`（曲线保留） |
| 中庸距离 | **Self-Sim**（字元集合两两 Jaccard 均值）+ **碰撞概率 C / N₂ / 碰撞比 R** | Lake et al. (NAACL'25, arXiv:2406.17692) / Skobelev et al. (arXiv:2609.16454) | `self_sim` / `collision_ratio` |
| 覆盖饱和度 | **保留 + 改名** "coverage over a pre-registered conclusion space" | 形式同 OvertonScore (ICLR'26) | `coverage_over_preregistered` |
| — | **保留** `VD_anchor_out`（参照系无先例） | — | 在 `anchor_out.py` |

## 三处**必须自己定口径**的地方（不能直接抄英文文献）

1. **"词干"在中文里没有对应物** ⇒ Self-Sim 的"唯一词干集合"⇒ 我们用
   **字符 2-gram 集合**（并同时提供**决策指纹版**）。
   ⚠️ Self-Sim 原文读数（0.11–0.45）是**英文**的 ⇒ **我们的中文读数不可与之直接比大小**，
   只能比**同批内的相对序**。这一条必须写进论文。
2. **DSE 的等价类来源不同**：Kuhn 用 NLI 模型聚类；**我们用 `family_key`（决策指纹）** ⇒
   ⇒ **零外部模型**，但**不是同一个等价类** ⇒ 论文必须写明。
3. **碰撞比 R 的分母是"目标分布"** ⇒ 我们**没有人类目标分布** ⇒ 用**批内自参照**
   ⇒ ⇒ **R 只能读"同批内相对中庸"，不能读"相对人类"。**

## 纪律
* **必须同时报 #distinct**（Kuhn 自己就这么做，并说"# distinct 本身就是个合理的测度"）
* **比率必须配绝对分母**
* 4-gram 降为**辅助列**（form-sensitive，中文更脆）
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ══════════════════════════════════════════════════════════════════════
# 基础：离散等价类与字符集合
# ══════════════════════════════════════════════════════════════════════
_CJK = re.compile(r"[一-鿿]")
_NUM = re.compile(r"\d+(?:\.\d+)?")
_PUNCT = re.compile(r"[\s，。；：、！？,.;:!?（）()【】《》“”‘’\-—/]")


def char_bigrams(text: str) -> frozenset:
    """中文版的"唯一词干集合"⇒ **字符 2-gram 集合**（Self-Sim 的中文口径）。

    ⚠️ 这是**我们自己定的口径**（英文原文用 stemmer）⇒ 读数不可与英文表直接比大小。
    """
    t = _PUNCT.sub("", (text or ""))
    if len(t) < 2:
        return frozenset([t]) if t else frozenset()
    return frozenset(t[i:i + 2] for i in range(len(t) - 1))


def decision_set(text: str) -> frozenset:
    """决策指纹版（与 `anchor_out.decision_fingerprint` 同源）：选项标记 + 数值 + 内容词。"""
    from anchor_out import decision_fingerprint
    o, n, w = decision_fingerprint(text or "")
    return frozenset(list(o) + list(n) + list(w))


# ══════════════════════════════════════════════════════════════════════
# A 组 · 趋同 / 众数吸引
# ══════════════════════════════════════════════════════════════════════
def majority_share(answers: Sequence[Sequence[str]]) -> float:
    """**多数票份额**（Self-Consistency 的原语，ICLR'23 arXiv:2203.11171）。

    定义：把每个答案映射到它的**族**（等价类）⇒ 找最大的族 ⇒ 其占比。
    ⚠️ 与原论文的差别：原论文按**完整答案文本**投票；我们按**族**投票
    ⇒ 必须同时报 `#distinct` 与 DSE（Kuhn 的做法）。
    """
    from workflow import _fingerprint
    fams = [_family_of(a) for a in answers if a]
    if not fams:
        return 0.0
    cnt = {}
    for f in fams:
        cnt[f] = cnt.get(f, 0) + 1
    return max(cnt.values()) / float(len(fams))


def distinct_families(answers: Sequence[Sequence[str]]) -> int:
    """**#distinct answers**（Kuhn et al. ICLR'23）—— 最朴素、最可比的收敛度读数。

    ★ 论文里**必须与 DSE 同时报**（Kuhn 自己说"# distinct 本身就是个合理的测度"）。
    """
    fams = set(_family_of(a) for a in answers if a)
    return len(fams)


def dse(answers: Sequence[Sequence[str]]) -> float:
    """**离散语义熵 DSE**（Kuhn, Gal & Farquhar, ICLR'23 Spotlight, arXiv:2302.09664）。

    定义：按语义等价类分桶 ⇒ 桶内样本比例 p_i ⇒ H = −Σ p_i log p_i（自然对数）。
    ⚠️ **我们的等价类 = `family_key`（决策指纹），不是 NLI** ⇒ 零外部模型，
      但**不是同一个等价类** ⇒ 论文必须写明这一差别。
    """
    fams = [_family_of(a) for a in answers if a]
    if not fams:
        return 0.0
    cnt = {}
    for f in fams:
        cnt[f] = cnt.get(f, 0) + 1
    n = float(len(fams))
    h = 0.0
    for c in cnt.values():
        p = c / n
        h -= p * math.log(p)
    return h


def self_sim(answers: Sequence[Sequence[str]], *, mode: str = "bigram") -> float:
    """**Self-Sim**（Lake, Choi & Durrett, NAACL 2025 Main, arXiv:2406.17692）。

    逐字定义："把每个响应转成**唯一词干集合**，对**所有响应两两**算 Jaccard 相似度并取平均；
    **每个 input 用 N = 5 个样本**。"

    ⚠️ **我们必须自己定的口径**：英文用 stemmer ⇒ 中文用 `mode`：
      · "bigram"   ⇒ 字符 2-gram 集合（默认）
      · "decision" ⇒ 决策指纹集合（选项标记 + 数值 + 内容词）
    ⇒ **读数不可与英文表（0.11–0.45）直接比大小**，只比同批内相对序。
    """
    sets = []
    for a in answers:
        if not a:
            continue
        s = char_bigrams(" ".join(a)) if mode == "bigram" else decision_set(" ".join(a))
        if s:
            sets.append(s)
    if len(sets) < 2:
        return 0.0
    tot, n = 0.0, 0
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            a, b = sets[i], sets[j]
            uni = len(a | b)
            tot += (len(a & b) / uni) if uni else 0.0
            n += 1
    return tot / n if n else 0.0


def collision_ratio(answers: Sequence[Sequence[str]],
                    ref: Optional[Sequence[Sequence[str]]] = None) -> Dict[str, Any]:
    """**碰撞概率 C / 逆 Simpson N₂ / 碰撞比 R**（Skobelev, Fithian & Han, arXiv:2609.16454）。

    ```
    C(π)  = Σ_a π(a)²          # 两次独立采样撞在一起的概率
    N₂(π) = 1 / C(π)           # 逆 Simpson 指数
    R     = C(q) / C(p)        # 碰撞比；R>1 ⇒ mode collapse
    ```
    ⚠️ **我们的 R 用批内自参照**（把同批另一组当 q）⇒ **只读"同批内相对中庸"，
       不能读"相对人类"**（我们没有人类目标分布）。
    ⚠️ 预印本，**无同行评审** ⇒ 引用时写 "preprint"。
    """
    def C(ans):
        fams = [_family_of(a) for a in ans if a]
        if not fams:
            return 0.0
        cnt = {}
        for f in fams:
            cnt[f] = cnt.get(f, 0) + 1
        n = float(len(fams))
        return sum((c / n) ** 2 for c in cnt.values())

    cp = C(answers)
    out = dict(C=cp, N2=(1.0 / cp) if cp > 0 else 0.0, R=None,
               note="批内自参照；不是'相对人类'")
    if ref is not None:
        cq = C(ref)
        out["R"] = (cq / cp) if cp > 0 else None
        out["C_ref"] = cq
        out["N2_ref"] = (1.0 / cq) if cq > 0 else 0.0
    return out


# ══════════════════════════════════════════════════════════════════════
# B 组 · 过早闭合
# ══════════════════════════════════════════════════════════════════════
def ess(weights: Sequence[float]) -> float:
    """**ESS（Effective Sample Size）**（ePF, arXiv:2510.05825）。

    ```
    ESS = 1 / Σ_i (w_i)²
    最大：权重均匀 ⇒ ESS = N（完全不塌）
    最小：一个权重 1、其余 0 ⇒ ESS = 1（塌成单个粒子）
    ```
    ⚠️ **需要权重**（每轮新发现族数），不能只用"是/否新发现"的布尔。
    """
    ws = [float(w) for w in weights if w is not None]
    if not ws:
        return 0.0
    tot = sum(ws)
    if tot <= 0:
        return 0.0
    # ★ ePF 原文：ESS = 1/Σ(w_i)²，且「权重均匀 (w=1/N) ⇒ ESS = N」
    #   ⇒ **权重必须先归一化成概率**，否则均匀权重会算成 1/N 而不是 N
    ps = [w / tot for w in ws]
    return 1.0 / sum(p * p for p in ps)


def marginal_util(rounds: Sequence[Sequence[str]]) -> List[float]:
    """**保留我们的逐轮曲线**（给形状），并与 ESS（给单值）**同时报**。

    ⚠️ 先例审计建议：曲线给形状、ESS 给可跨臂比较的单值 ⇒ 两个都报。
    """
    out: List[float] = []
    seen: set = set()
    for k, rs in enumerate(rounds):
        cur = set()
        for a in rs:
            cur |= set(a)
        if k > 0:
            total = len(cur) or 1
            out.append(len(cur - seen) / total)
        seen |= cur
    return out


def ess_from_rounds(rounds: Sequence[Sequence[str]]) -> float:
    """由逐轮**新发现族数**当权重 ⇒ 算 ESS（先例要求的口径）。"""
    ws, seen = [], set()
    for rs in rounds:
        cur = set()
        for a in rs:
            cur |= set(a)
        ws.append(float(len(cur - seen)))
        seen |= cur
    return ess(ws)


def dbs_diversity_stats(texts: Sequence[str], n: int = 2) -> Dict[str, float]:
    """**Diverse Beam Search 的 diversity statistics**（AAAI 2018, arXiv:1610.02424）。

    逐字："数出生成列表中出现的**不同 n-gram** 数；类似 Li et al. 2015，我们把这些计数
    **除以生成的总词数**以抑制长句偏置。"
    ⇒ ⇒ **跨论文可比**的 n-gram 版多样性。
    """
    allg = set()
    total = 0
    for t in texts:
        s = _PUNCT.sub("", (t or ""))
        total += max(1, len(s))
        for i in range(max(0, len(s) - n + 1)):
            allg.add(s[i:i + n])
    return dict(distinct_n=len(allg), total_chars=total,
                distinct_n_per_char=(len(allg) / total) if total else 0.0)


# ══════════════════════════════════════════════════════════════════════
# C 组 · 覆盖（保留 + 改名对齐）
# ══════════════════════════════════════════════════════════════════════
def coverage_over_preregistered(found_families: Iterable[str], ct_size: int) -> Dict[str, Any]:
    """**coverage over a pre-registered conclusion space**。

    ★ 改名对齐 OvertonScore (ICLR'26, arXiv:2512.01351) 的形式，
      但**分母不同**（我们 = 预注册结论空间 \|C_t\|，他们 = 人类观点集 \|W(x)\|）
      ⇒ 论文必须写"形式同 OvertonScore，分母不同"。
    ★ \|C_t\| 是**绝对分母**，必须写出来。
    """
    fams = set(found_families or [])
    den = int(ct_size or 0)
    return dict(n_found=len(fams), ct_size=den,
                coverage=(len(fams) / den) if den else 0.0,
                saturated=bool(den and len(fams) >= den))


# ══════════════════════════════════════════════════════════════════════
# 辅助：族（等价类）
# ══════════════════════════════════════════════════════════════════════
def _family_of(answer: Sequence[str]) -> str:
    """一个答案的**族键**（= 它支撑的结论集合，排序后连接）。

    ★ 与生产读数同口径（`family_key`）⇒ 与 `dims_from_cards` 一致。
    """
    return "|".join(sorted(answer or []))


# ══════════════════════════════════════════════════════════════════════
# ★ 二元目标 + Pareto 档案（EoT / MOAE / SetPO 的形态）
# ══════════════════════════════════════════════════════════════════════
def dominates(a: Tuple[float, float], b: Tuple[float, float]) -> bool:
    """a 支配 b：质量与多样性**同时**不劣，且至少一项严格更优（EoT 的 A_i ≺ A_j）。"""
    return (a[0] >= b[0] and a[1] >= b[1]) and (a[0] > b[0] or a[1] > b[1])


def nondominated_sort(pop: Sequence[Tuple[Tuple[float, float], Any]]) -> List[List[int]]:
    """**非支配排序**（NSGA-II 的第一步）⇒ 返回前沿列表（front 0 = Pareto 前沿）。

    ★ 这替代了**标量 argmax** ⇒ 标量目标必然收敛到一点（＝中庸），
      而 Pareto 前沿会**同时保留多个不可比的解**。
    """
    n = len(pop)
    S = [set() for _ in range(n)]     # S[i] = **支配 i** 的点集合
    D = [set() for _ in range(n)]     # D[i] = **i 支配** 的点集合（剥层要用这个！）
    cnt = [0] * n                     # cnt[i] = 支配 i 的点数
    fronts: List[List[int]] = []
    f0: List[int] = []
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if dominates(pop[j][0], pop[i][0]):
                S[i].add(j)          # j 支配 i
                cnt[i] += 1
            elif dominates(pop[i][0], pop[j][0]):
                D[i].add(j)          # i 支配 j
        if cnt[i] == 0:
            f0.append(i)            # ★ 全部前沿点放进**同一个** front-0 列表
    if f0:
        fronts.append(f0)
    # 迭代剥层：前沿里的 i 被移出后，**它所支配的**那些点的支配计数减 1
    k = 0
    while True:
        if not fronts:
            break
        nxt = []
        for i in fronts[k]:
            for j in D[i]:           # ★ 用 D（i 支配的），不是 S
                cnt[j] -= 1
                if cnt[j] == 0:
                    nxt.append(j)
        k += 1
        if not nxt:
            break
        fronts.append(nxt)
    return fronts


def pareto_front(points: Sequence[Tuple[float, float]]) -> List[int]:
    """只取 Pareto 前沿的下标（便捷封装）。"""
    pop = [(p, None) for p in points]
    fronts = nondominated_sort(pop)
    return fronts[0] if fronts else []


# ══════════════════════════════════════════════════════════════════════
# ★ 策略档案：同一份代码、同一批样本，**只改选择规则** ⇒ 最干净的对照
# ══════════════════════════════════════════════════════════════════════
class StrategyArchive:
    """**策略档案**（EoT / MOAE 的形态）。

    ★★ **这个类承载了全文最锐利的一个对照**：

    | 选择规则 | 档案里留下什么 | 档案规模 | 策略间 Self-Sim | 含义 |
    |---|---|---|---|---|
    | `scalar` | **只留分数最高的 1 个** | **必然 = 1** | **= 1.0**（完全同质）| **中庸** |
    | `pareto` | 留**全部非支配解** | >= 1（通常 > 1）| < 1.0 | **不中庸** |

    => => **"答案不再中庸"在策略层面就等于「档案规模 > 1」。**
    => => 而且这**不是修辞**：标量 argmax 的档案规模在数学上**必然是 1**。

    ★ 档案级多样性用**有出处的度量**报：Self-Sim（Lake et al. NAACL'25）
      + #distinct + 碰撞比（Skobelev et al.，批内自参照）。
    """

    def __init__(self, mode: str = "pareto", max_size: int = 64):
        if mode not in ("scalar", "pareto"):
            raise ValueError("mode 必须是 scalar / pareto（收到 %r）" % mode)
        self.mode = mode
        self.max_size = max_size
        self.items: List[Dict[str, Any]] = []

    def _score(self, it: Dict[str, Any]) -> Tuple[float, float]:
        return (float(it.get("quality") or 0.0), float(it.get("diversity") or 0.0))

    def _scalar(self, it: Dict[str, Any]) -> float:
        return float(it.get("scalar") or 0.0)

    def offer(self, item: Dict[str, Any]) -> bool:
        """提交一个策略样本。返回 True = 它**留在了档案里**。"""
        if self.mode == "scalar":
            if not self.items:
                self.items.append(item)
                return True
            best = max(self.items, key=self._scalar)
            if self._scalar(item) > self._scalar(best):
                self.items = [it for it in self.items if it is not best] + [item]
                return True
            return False
        # ── pareto：非支配 => 留下；被支配 => 剔掉
        self.items.append(item)
        pts = [self._score(x) for x in self.items]
        fronts = nondominated_sort([(p, None) for p in pts])
        keep = set(fronts[0])
        # ★ 前沿内部**全留**（互不可比 => 都要）=> 这正是标量 argmax 做不到的
        self.items = [x for i, x in enumerate(self.items) if i in keep]
        if len(self.items) > self.max_size:
            self.items = self.items[:self.max_size]
        return True

    def stats(self) -> Dict[str, Any]:
        n = len(self.items)
        answers = [it.get("claims") or [] for it in self.items]
        out: Dict[str, Any] = dict(mode=self.mode, n_items=n,
                                   specs=[list(it.get("spec") or []) for it in self.items])
        if n == 0:
            return out
        out["distinct_families"] = distinct_families(answers)
        if n >= 2:
            out["self_sim"] = self_sim(answers, mode="bigram")
            out["self_sim_decision"] = self_sim(answers, mode="decision")
            out["collision"] = collision_ratio(answers)
        else:
            out["self_sim"] = None
            out["self_sim_decision"] = None
            out["collision"] = None
        out["mean_quality"] = sum(self._score(it)[0] for it in self.items) / n
        out["mean_diversity"] = sum(self._score(it)[1] for it in self.items) / n
        return out
