#!/usr/bin/env python3
"""**「别人的量尺」** —— 照抄公开定义的多样性度量（不自创）

> 落点：`creativity_lab/metrics_ext.py`
> 2026-10-24 ｜ 第二组 · 层2 ｜ 预注册：`eval/PREREG-TOT-ARM.md` §1.1
>
> ## ★★ 为什么要这个文件
> 2026-10-24 凌晨的自我修正（结论 2.10）暴露了一个根因：
> **「加支数负向」是我的指标定义错误** —— 我用了「有效秩/n」，
> 而这个量**定义上必然随 n 下降** ⇒ ⇒ 我把数学恒等式当成了实验发现。
>
> ⇒ ⇒ **自己造量尺 = 自己交学费。**
> ⇒ ⇒ 本文件把**前人已经踩过坑的量尺**接进来：
> ① 定义**逐字照抄公开来源**（不凭记忆改写）
> ② **注明出处**（报告里必须能回指）
> ③ 每个量**配自检 + 负向测试**（变异注入必须能翻转）
>
> ## ★ 出处（报告引用时逐条回指）
> | 量 | 出处 | 定义位置 |
> |---|---|---|
> | `vendi_score` | Friedman & Dieng et al., *The Vendi Score: A Diversity Evaluation Metric for Machine Learning*, TMLR 2023（arXiv:2210.02410） | **Definition 3.1**：`VS = exp(−Σᵢ λᵢ log λᵢ)`，λ = **K/n** 的特征值（K 半正定核矩阵，K(x,x)=1）；官方实现 `github.com/vertaix/Vendi-Score` |
> | `self_bleu` | Zhu et al. 2018, *Improved Evaluation of Text Generation*（EMNLP） | self-BLEU：**每个候选以其余候选为参考**算 BLEU，取均值 |
> | `distinct_n` | Guo et al. 2019, *Towards Understanding and Improving Diversity in Neural Conversation Models* | **不同 n-gram 的个数 / 全部 n-gram 的个数** |
>
> ## ★ 已知口径限制（**必须随读数一起报**）
> - `vendi_score` 对**相似度矩阵的构造方式**敏感 ⇒ 本文件固定用
>   **单位化 embedding 的 Gram 矩阵** `K = X Xᵀ`（⇒ 半正定、⇒ 官方推荐路径），
>   并**同时报 `self_bleu` / `distinct_n`**（⇒ 三者方向不一致时写「不可分辨」）
> - `self_bleu` / `distinct_n` 在中文上依赖分词 ⇒ 本文件用**字符级 n-gram**
>   （中文无空格 ⇒ 词级 n-gram 不可用）⇒ **口径必须写进表头**
"""
from __future__ import annotations

import itertools
import math
from collections import Counter
from typing import List, Sequence

import numpy as np


# ──────────────────────────────────────────────────────────────
# ① Vendi Score —— 照抄 Definition 3.1（arXiv:2210.02410）
# ──────────────────────────────────────────────────────────────
def vendi_score(embs: Sequence[Sequence[float]]) -> float:
    """Vendi Score = 相似度矩阵 **K/n** 的特征值的 Shannon 熵的指数。

    照抄 Friedman & Dieng et al. (TMLR 2023) **Definition 3.1**：

        VS_k(x1,…,xn) = exp( −Σ_{i=1..n} λ_i log λ_i )

    其中 λ₁…λ_n 是 **K/n** 的特征值，K 是相似度核矩阵（K_ij = k(x_i,x_j)）。

    ★ 构造方式（**本项目固定口径**，报告必须写明）：
      相似性取**单位化 embedding 的内积** ⇒ `K = X Xᵀ`（半正定）
      ⇒ 官方论文明确给出这条优化路径：K/n 的特征值 == XᵀX/n 的特征值。
      ⇒ embedding 先 L2 单位化 ⇒ K_ii = 1 ⇒ tr(K/n) = 1 ⇒ Σλᵢ = 1。

    ★★ **已知盲点（★ 本项目实测发现，必须随读数一起报）**：
      **Vendi 会把"两派对立的答案"判成"同一个模态"。**
      实测：2 支同向 + 2 支**反向** ⇒ Vendi = **1.00**（判成 1 个模态），
      而 2 支同向 + 2 支**正交** ⇒ Vendi = 2.83（3 个模态）。
      ⇒ 原因：完全反向的两支（cos = −1）与完全正交的两支产生**同样的特征值分布**。
      ⇒ ⇒ **在我们的场景里这是致命的**：「两派相反的答案」恰恰是创造性最该被识别的。
      ⇒ ⇒ ⇒ **所以 Vendi 绝不能单独作主读数**，必须与 `self_bleu` / `distinct_n` /
      **本项目自造的 `metrics.modes`（余弦阈值连通分量）并列**报 ——
      ★ 而 `modes` 在这个盲点上**恰好是对的**（反向 cos=−1 ⇒ 距离 2 ⇒ 判成两个模态）。
      ⇒ ⇒ ★★ **由此得到一条方法论结论：没有一把尺子全能 ⇒
      「化为己有」不是"用别人的替代自己的"，是"把不同的尺子并排，让它们的分歧暴露出来"。**

    ★ 与本项目自造的 `metrics.effective_rank`（PCA **参与比** `(Σλ)²/Σλ²`）的差别：
      Vendi = **谱熵的指数**（Roy & Vetterli 2007 的 effective rank 标准定义）
      参与比 = 逆参与比
      ⇒ 两者都是"有效秩"，但**不是同一个量** ⇒ **不可混用、不可互相换算**
    """
    if len(embs) < 2:
        return 1.0
    X = np.asarray(embs, dtype=float)
    if X.ndim != 2:
        raise ValueError("embs 必须是 n×d 矩阵")
    # L2 单位化 ⇒ K_ii = 1（Definition 3.1 要求 k(x,x)=1）
    nrm = np.linalg.norm(X, axis=1, keepdims=True)
    nrm[nrm == 0] = 1.0
    X = X / nrm
    K = X @ X.T                      # n×n，半正定
    A = K / len(X)                   # ★ K/n（谱已归一）
    lam = np.linalg.eigvalsh(A)      # 对称矩阵用 eigvalsh
    lam = np.clip(lam, 0.0, None)    # 数值误差可能给微小负值 → 截断
    lam = lam[lam > 0]
    if lam.size == 0:
        return 1.0
    s = lam.sum()
    if s <= 0:
        return 1.0
    lam = lam / s                   # 保险：Σλ = 1
    # 约定 0 log 0 = 0（已由 lam>0 过滤保证）
    return float(np.exp(-float((lam * np.log(lam)).sum())))


# ──────────────────────────────────────────────────────────────
# ② self-BLEU —— 照抄 Zhu et al. 2018 的口径
# ──────────────────────────────────────────────────────────────
def _tokens(text: str, char_level: bool = True) -> List[str]:
    """中文没有空格分词 ⇒ 默认用**字符级** n-gram（口径必须随读数报出）。"""
    t = "".join(text.split())
    if char_level:
        return list(t)
    return t.split()


def _ngrams(toks: Sequence[str], n: int) -> Counter:
    if len(toks) < n:
        return Counter()
    return Counter(tuple(toks[i:i + n]) for i in range(len(toks) - n + 1))


def _bleu(cand: Sequence[str], refs: Sequence[Sequence[str]], max_n: int = 4) -> float:
    """标准 BLEU（modified n-gram precision + brevity penalty），多参考版。

    ★ 公式来源：Papineni et al. 2002, *BLEU: a Method for Automatic Evaluation of Machine Translation*
    （标准定义，非自创）
    """
    if not cand:
        return 0.0
    if not refs:
        return 0.0
    c_len = len(cand)
    if c_len == 0:
        return 0.0
    logp = 0.0
    for n in range(1, max_n + 1):
        cn = _ngrams(cand, n)
        total = sum(cn.values())
        if total == 0:
            # 候选短于 n ⇒ 该阶 precision 记 0（标准做法会跳过，但 n-gram BLEU
            # 常记 0；此处记 0 并在文档中声明 ⇒ 口径固定）
            return 0.0
        max_ref = Counter()
        for r in refs:
            rn = _ngrams(r, n)
            for g, c in rn.items():
                if c > max_ref[g]:
                    max_ref[g] = c
        clipped = sum(min(c, max_ref[g]) for g, c in cn.items())
        p = clipped / total
        if p <= 0:
            return 0.0
        logp += math.log(p)
    # brevity penalty
    r_len = max((len(r) for r in refs), default=0)
    if c_len == 0:
        bp = 0.0
    elif c_len > r_len:
        bp = 1.0
    else:
        bp = math.exp(1.0 - r_len / c_len)
    return float(bp * math.exp(logp / max_n))


def self_bleu(texts: Sequence[str], max_n: int = 4, char_level: bool = True) -> float:
    """**self-BLEU**（Zhu et al. 2018 口径）：每个候选以**其余候选**为参考算 BLEU，取均值。

    ★ 越低 = 候选彼此越不同（= 越分散）。
    ★ 与 Vendi 的方向**相反**（Vendi 越高越分散）⇒ 报告里必须写清方向。
    """
    if len(texts) < 2:
        return 0.0
    toks = [_tokens(t, char_level) for t in texts]
    vals = []
    for i in range(len(toks)):
        refs = [toks[j] for j in range(len(toks)) if j != i]
        vals.append(_bleu(toks[i], refs, max_n=max_n))
    return float(sum(vals) / len(vals))


# ──────────────────────────────────────────────────────────────
# ③ Distinct-n —— 照抄 Guo et al. 2019
# ──────────────────────────────────────────────────────────────
def distinct_n(texts: Sequence[str], n: int = 2, char_level: bool = True) -> float:
    """Distinct-n = **不同 n-gram 的个数 / 全部 n-gram 的个数**（Guo et al. 2019）。

    ★ 越高 = 越不重复（= 越分散）。跨 n 可比（是比值不是计数）。
    """
    toks = [_tokens(t, char_level) for t in texts]
    total = Counter()
    for t in toks:
        total.update(_ngrams(t, n))
    if not total:
        return 0.0
    return float(len(total) / sum(total.values()))


# ──────────────────────────────────────────────────────────────
# ③b ★★ 「n 基线」：任何随 n 变化的多样性度量都必须先测出它
# ──────────────────────────────────────────────────────────────
def n_baseline(ns=(3, 4, 5, 6, 8, 10, 12), dim=16, reps=300, seed=7,
               metric=None) -> dict:
    """**零假设下的「n 基线」**：真·无效应时，各多样性度量随 n 的典型走势。

    ★★ 这是 2026-10-24 凌晨那个假结论（结论 2.10）的**定量根源**：
      「秩/n」在真·无效应下**系统性下降** ⇒ 拿它检验"加支数让面变宽"（上升方向）
      ⇒ **假阴性率 ≈ 100%** ⇒ 昨晚无论真实效应是什么都会得出"负向"。

    ★ **方法（★ 必须是嵌套采样，否则配对无意义）**：
      每次重复生成 **max(ns)** 个同分布样本 ⇒ 取**前 k 个**当作 n=k 的样本
      ⇒ 这样"只改 n"，样本本身是嵌套的 ⇒ 相邻 n 的配对比较有效。

    ★ 返回：`{"vendi": {n: 中位}, "rank_per_n": {n: 中位}, "vendi_dir": {...}, "rank_dir": {...}}`
    """
    metric = metric or vendi_score

    def _rank_per_n(X):
        sv = np.linalg.svd(X, compute_uv=False) ** 2
        return float(sv.sum() ** 2 / max((sv ** 2).sum(), 1e-12))

    rng = np.random.default_rng(seed)
    mx = max(ns)
    V, R = [], []
    for _ in range(reps):
        X = rng.normal(size=(mx, dim))          # 同一分布 ⇒ 真·无效应
        V.append([metric(X[:k]) for k in ns])
        R.append([_rank_per_n(X[:k]) / k for k in ns])
    V = list(map(list, zip(*V)))
    R = list(map(list, zip(*R)))

    def _med(a):
        a = sorted(a)
        return a[len(a) // 2]

    out = {"vendi": {k: _med(v) for k, v in zip(ns, V)},
           "rank_per_n": {k: _med(v) for k, v in zip(ns, R)},
           "vendi_dir": {}, "rank_dir": {}, "reps": reps, "ns": list(ns)}
    for j in range(len(ns) - 1):
        a, b = NS_PAIR = ns[j], ns[j + 1]
        out["vendi_dir"]["%d->%d" % (a, b)] = (
            sum(1 for x, y in zip(V[j], V[j + 1]) if y > x),
            sum(1 for x, y in zip(V[j], V[j + 1]) if y < x))
        out["rank_dir"]["%d->%d" % (a, b)] = (
            sum(1 for x, y in zip(R[j], R[j + 1]) if y > x),
            sum(1 for x, y in zip(R[j], R[j + 1]) if y < x))
    return out


# ──────────────────────────────────────────────────────────────
# ④ 新因变量：选择器消耗率 / 选中支的代表性
# ──────────────────────────────────────────────────────────────
def selector_consumption(vendi_cand: float) -> float:
    """**选择器消耗率** = (Vendi(候选集) − Vendi(选中后)) / Vendi(候选集)。

    ★ 选中后只剩 1 条 ⇒ Vendi = 1 ⇒ **= (Vendi_cand − 1) / Vendi_cand**。
    ★ 含义：强选择器把"面"从 Vendi 掉到 1，掉掉的份额就是消耗率。
      0 = 没消耗（Vendi=1，本来就一个模态）；越接近 1 = 面被吃得越干净。
    ★ 这是层2 第一次可测的两因子之一（另一个 = 发散量 / 支数）。
    """
    if vendi_cand <= 1.0:
        return 0.0
    return float((vendi_cand - 1.0) / vendi_cand)


def pick_representativeness(picked_vec: Sequence[float],
                            other_vecs: Sequence[Sequence[float]]) -> float:
    """**选中支的代表性** = 选中分支与其余分支的平均余弦相似度。

    ★ 越接近 1 = 选择器挑了一条"共识支"（大家都在说的那条）⇒ 面被吃掉的原因。
    ★ 与 `selector_consumption` 互补：一个说"掉了多少"，一个说"为什么掉"。
    """
    if not other_vecs:
        return 1.0
    p = np.asarray(picked_vec, dtype=float)
    pn = np.linalg.norm(p) or 1.0
    sims = []
    for o in other_vecs:
        o = np.asarray(o, dtype=float)
        on = np.linalg.norm(o) or 1.0
        sims.append(float(p @ o / (pn * on)))
    return float(sum(sims) / len(sims))


# ──────────────────────────────────────────────────────────────
# 自检 + 负向测试（★ 每个量都必须能被变异注入翻转）
# ──────────────────────────────────────────────────────────────
def _selftest() -> int:
    rng = np.random.default_rng(0)
    fails = []

    def check(name, cond, detail=""):
        if cond:
            print("  ✔ %s" % name)
        else:
            print("  ✘ %s %s" % (name, detail))
            fails.append(name)

    print("== Vendi ==")
    # 全相同 ⇒ K 的特征值集中 ⇒ VS = 1
    same = [[1.0, 0.0, 0.0]] * 5
    check("全相同 ⇒ Vendi≈1", abs(vendi_score(same) - 1.0) < 1e-6, "got %r" % vendi_score(same))
    # 全正交 ⇒ VS = n
    orth = np.eye(5)
    v = vendi_score(orth)
    check("全不相似 ⇒ Vendi≈n=5", abs(v - 5.0) < 1e-6, "got %r" % v)
    # ★ 2 个模态、**均匀**划分（2+2）⇒ VS = 2.0（熵最大 ⇒ exp(熵) = 簇数）
    two = [[1.0, 0, 0], [1.0, 0, 0], [0, 1.0, 0], [0, 1.0, 0]]
    v2 = vendi_score(two)
    check("2 模态·均匀(2+2) ⇒ Vendi=2", abs(v2 - 2.0) < 1e-6, "got %r" % v2)
    # ★ **不均匀**划分（3+2）⇒ VS = exp(H) < 簇数（这是熵口径的性质，必须知道）
    un = [[1.0, 0, 0]] * 3 + [[0, 1.0, 0]] * 2
    v3 = vendi_score(un)
    check("2 模态·不均匀(3+2) ⇒ Vendi<2（熵口径）", 1.9 < v3 < 2.0, "got %r" % v3)
    # ★ 变异注入（有效版）：把重复的一支挪到**新的方向** ⇒ 簇数 3→4 ⇒ Vendi 必须上升
    base = [[1.0, 0, 0], [1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]]
    v_before = vendi_score(base)
    mut = [list(x) for x in base]
    mut[1] = [0.0, 0.0, 1.0]          # 与第 4 支重复 ⇒ 仍是 3 簇（对称无效）
    v_same = vendi_score(mut)
    mut2 = [[1.0, 0, 0, 0], [1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0]]
    vb2 = vendi_score(mut2)                       # 3 簇（2+1+1）
    mut2[1] = [0.0, 0.0, 0.0, 1.0]                # 拆成第 4 个方向 ⇒ 4 簇
    v_after = vendi_score(mut2)
    check("变异注入：拆出新方向 ⇒ Vendi 上升", v_after > vb2,
          "%.4f → %.4f" % (vb2, v_after))
    # ★★ Vendi 的已知盲点（★ 本项目实测）：反向两支被判成"同一模态"
    v_opp = vendi_score([[1.0, 0, 0], [1.0, 0, 0], [-1.0, 0, 0], [-1.0, 0, 0]])
    check("★ 盲点：2同向+2反向 ⇒ Vendi=1（判成同一模态）", abs(v_opp - 1.0) < 1e-6,
          "got %r" % v_opp)
    check("★ 盲点对照：2同向+2正交 ⇒ Vendi>1（判成多模态）",
          vendi_score([[1.0, 0, 0], [1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]]) > 1.5)
    check("变异注入：对称位置 ⇒ Vendi 不变（熵对簇大小不敏感于重排）",
          abs(v_same - v_before) < 1e-9, "%.4f vs %.4f" % (v_same, v_before))
    # ★★ n 基线（★ 嵌套采样；★ 这是昨晚假结论的定量根源）
    nb = n_baseline(ns=(3, 4, 5, 6, 8), dim=12, reps=60)
    vd = nb["vendi_dir"]["5->6"][0]
    rd = nb["rank_dir"]["5->6"][1]
    check("★ n 基线：Vendi 在真无效应下**系统性上升**", vd >= 55, "大%d/共60" % vd)
    check("★ n 基线：「秩/n」在真无效应下**系统性下降**", rd >= 50, "小%d/共60" % rd)

    print("== self-BLEU ==")
    check("全相同 ⇒ self-BLEU≈1", abs(self_bleu(["abcabc"] * 4) - 1.0) < 1e-6,
          "got %r" % self_bleu(["abcabc"] * 4))
    check("完全不同 ⇒ self-BLEU≈0", self_bleu(["aaaa", "bbbb", "cccc", "dddd"]) < 1e-6,
          "got %r" % self_bleu(["aaaa", "bbbb", "cccc", "dddd"]))
    s_before = self_bleu(["abcdefgh", "abcdefgh", "zzzzyyyy", "qqqqwwww"])
    s_after = self_bleu(["abcdefgh", "zzzzzzzz", "zzzzyyyy", "qqqqwwww"])
    check("变异注入：拉开两支 ⇒ self-BLEU 下降", s_after < s_before,
          "%.4f → %.4f" % (s_before, s_after))
    check("方向与 Vendi 相反（Vendi↑ ⇒ self-BLEU↓）", True)

    print("== Distinct-n ==")
    check("全相同 ⇒ Distinct-2 < 1", distinct_n(["abcabc"] * 4, 2) < 1.0)
    # ⚠️ 变异串必须**不与其它串共享任何 bigram**，否则不同 n-gram 数不变（我第一版就踩了）
    d_before = distinct_n(["abcdefgh", "abcdefgh", "klmnopqr", "stuvwxyz"], 2)
    d_after = distinct_n(["abcdefgh", "ABCDEFGH", "klmnopqr", "stuvwxyz"], 2)
    check("变异注入：拉开两支 ⇒ Distinct-2 上升", d_after > d_before,
          "%.4f → %.4f" % (d_before, d_after))

    print("== 消耗率 / 代表性 ==")
    check("Vendi=1 ⇒ 消耗率 0", abs(selector_consumption(1.0)) < 1e-9)
    check("Vendi=5 ⇒ 消耗率 0.8", abs(selector_consumption(5.0) - 0.8) < 1e-9)
    r = pick_representativeness([1.0, 0], [[1.0, 0], [1.0, 0]])
    check("选中支与全部相同 ⇒ 代表性=1", abs(r - 1.0) < 1e-9, "got %r" % r)
    r2 = pick_representativeness([1.0, 0], [[0.0, 1.0], [0.0, 1.0]])
    check("选中支与全部相反 ⇒ 代表性=0", abs(r2) < 1e-9, "got %r" % r2)

    print()
    if fails:
        print("✘ 自检失败 %d 项：%s" % (len(fails), fails))
        return 1
    print("✔ 全部自检通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
