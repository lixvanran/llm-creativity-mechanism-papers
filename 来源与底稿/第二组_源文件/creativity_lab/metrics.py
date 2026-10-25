"""度量。**全部只吃数据，不吃作者先验。**

关键约束（对应复盘错误 2）：参照系必须由调用方从**真实产出**构造。
本模块不含任何题目专有的关键词。
"""
from __future__ import annotations
import itertools, math
import numpy as np
from creativity_lab.client import cosine


def _mat(emb):
    M = np.array(emb, dtype=float)
    return M / np.maximum(np.linalg.norm(M, axis=1, keepdims=True), 1e-12)


def escape(cand_vecs: list, ref_vecs: list) -> float:
    """候选离参照系质心有多远。参照系通常是同题的直接采样。"""
    if not cand_vecs or not ref_vecs: return 0.0
    r = _mat(ref_vecs)
    c = _mat([cand_vecs]).mean(axis=0)
    c = c / max(float(np.linalg.norm(c)), 1e-12)
    return float(1.0 - np.mean([cosine(v, c) for v in r]))


def spread(cand_vecs: list) -> float:
    """批内两两距离中位数。"""
    if len(cand_vecs) < 2: return 0.0
    ds = [1.0 - cosine(a, b) for a, b in itertools.combinations(cand_vecs, 2)]
    ds.sort()
    return ds[len(ds) // 2]


def effective_rank(cand_vecs: list) -> float:
    """PCA 谱的参与比 (Σλ)²/Σλ²。一个模态≈1，K 个互异模态≈K。"""
    if len(cand_vecs) < 2: return 1.0
    s = np.linalg.svd(_mat(cand_vecs), compute_uv=False)
    s2 = s ** 2
    return float(s2.sum() ** 2 / max((s2 ** 2).sum(), 1e-12))


def modes(cand_vecs: list, r: float = 0.05) -> int:
    """余弦距离阈值 r 下的连通分量数 —— 字面意义的「分成了几块」。"""
    n = len(cand_vecs)
    if n == 0: return 0
    par = list(range(n))
    def f(x):
        while par[x] != x: par[x] = par[par[x]]; x = par[x]
        return x
    for i, j in itertools.combinations(range(n), 2):
        if 1.0 - cosine(cand_vecs[i], cand_vecs[j]) < r:
            a, b = f(i), f(j)
            if a != b: par[a] = b
    return len({f(i) for i in range(n)})


def dispersion(emb_list: list) -> float:
    """同臂多次重复之间的两两相似度均值（越低=越不重复）。"""
    if len(emb_list) < 2: return float("nan")
    return float(np.mean([cosine(a, b) for a, b in itertools.combinations(emb_list, 2)]))


# ──────────────────────────────────────────────────────────────
# 层2 · 末步对照用的**零判官**指标（可复算、可离线复算）
# ──────────────────────────────────────────────────────────────
# ★ 为什么不用 embedding：判官/指标同源会污染，且 embedding 距离的量级由题目内容主导
#   ⇒ 这里一律用**词块集合统计** ⇒ 零成本、零判官、逐字节可复算。
# ★ 为什么不用「措辞级 n-gram Jaccard 判同一性」：本项目实测它在中文上**恒为 0**
#   （语义同、措辞异 ⇒ 记 0）⇒ 只能当**下界**用。
#   ⇒ 本模块只用**集合覆盖**（内容还在不在），不做相似度判定。

_CJK_STOP = set("的了和是在有与及或而对于个我们你们他们这那不也就都要会可以因为所以但是如果那么什么怎么这样那样以及并且以及将把被让使可能应该这些那些自己没有一些非常还也很")


def keywords(text: str) -> set:
    """中文 2-gram 词块（去高频虚词单字）⇒ 对措辞变化稳健。

    ★ 只用于**集合覆盖**（内容是否还在），不用于相似度/同一性判定。
    """
    import re as _re
    t = _re.sub(r"[^一-鿿A-Za-z0-9]+", "", text or "")
    out = set()
    for i in range(len(t) - 1):
        w = t[i:i + 2]
        if w in _CJK_STOP:
            continue
        out.add(w)
    return out


def survival_rate(arts: list, final: str) -> float:
    """**探索存活率**：末步输出保留了多少分支的内容（按分支取平均）。

    定义：survival_i = |K_i ∩ K_final| / |K_i|；survival = mean_i(survival_i)
    （K = 词块集合）

    ★ 零判官、零 embedding、纯集合运算 ⇒ 可复算、可离线复算。
    ⚠️ **输出量越大覆盖率天然越高** ⇒ 必须与**输出量/篇数**并列报，
       否则这个指标就是在奖励"多写"（不是"思维面宽"）。
    ★ 自校准：若某臂是"原样输出其中一支"（如只选不融），它的存活率应 ≈ 1.0
       ⇒ 偏离 ⇒ **指标坏了**，不是臂坏了。
    """
    if not arts:
        return 0.0
    kf = keywords(final)
    vals = []
    for a in arts:
        ka = keywords(a)
        if not ka:
            continue
        vals.append(len(ka & kf) / len(ka))
    return float(sum(vals) / len(vals)) if vals else 0.0


def branch_diversity(arts: list) -> float:
    """分支两两**词块 Jaccard 距离**的中位数（越大 = 分支越不同 = 面越宽）。

    ⚠️ 这是**差异度的下界**：措辞改写会低估重叠 ⇒ 报"下界"，不报"真差异"。
    """
    if len(arts) < 2:
        return 0.0
    ks = [keywords(a) for a in arts]
    ds = []
    for i in range(len(ks)):
        for j in range(i + 1, len(ks)):
            u = len(ks[i] | ks[j])
            ds.append(1.0 - (len(ks[i] & ks[j]) / u) if u else 0.0)
    ds.sort()
    return float(ds[len(ds) // 2])


def distinctness_scores(arts: list) -> list:
    """每支的**独特度** = 它到其余各支的**最小**成对距离（越大越独特）。

    ★ 用于纯函数选择器：选独特度最高的一支 = **保住面的边缘**
      （而不是选最典型/中间的一支）⇒ 这是"扩展思维面"的选择口径。
    ★ 纯词块统计 ⇒ 零 embedding、零判官、可复算。
    """
    n = len(arts)
    if n == 0:
        return []
    if n == 1:
        return [0.0]
    ks = [keywords(a) for a in arts]
    out = []
    for i in range(n):
        ds = []
        for j in range(n):
            if i == j:
                continue
            u = len(ks[i] | ks[j])
            ds.append(1.0 - (len(ks[i] & ks[j]) / u) if u else 0.0)
        out.append(float(min(ds)))
    return out


def covered_branches(arts: list, final: str, thr: float = 0.30) -> int:
    """**面保留数**：末步输出里**同时**还留着多少支的内容（0..N）。

    定义：支 i 被"覆盖" ⇔ |K_i ∩ K_final| / |K_i| ≥ thr
    ⇒ 这是"思维面"的**直接**度量（宽），而 `survival_rate` 是**深度**（平均比例）。

    ★ 为什么必须和 `survival_rate` / 输出量**并排**报：
      - 只看存活率：选一臂构造性 = 1.0（它只输出那一支）⇒ 会被"深"掩盖"窄"
      - 只看面保留数：不写就多 ⇒ 会被"多写"奖励
      ⇒ 三元组 = **面宽（covered）× 面深（survival）× 输出量（chars）** 才有解释力。

    ⚠️ `thr` 是**事前登记**的参数（默认 0.30）；读数必须给**整条阈值曲线**，
       不许只报一个点（点估计 = 装饰性数字）。
    """
    if not arts:
        return 0
    kf = keywords(final)
    n = 0
    for a in arts:
        ka = keywords(a)
        if not ka:
            continue
        if len(ka & kf) / len(ka) >= thr:
            n += 1
    return n


def coverage_curve(arts: list, final: str,
                   thrs=(0.10, 0.20, 0.30, 0.40, 0.50, 0.60)) -> dict:
    """整条阈值曲线（面保留数 vs 阈值）⇒ 报范围，不报单点。"""
    return {("%.2f" % t): covered_branches(arts, final, t) for t in thrs}


# ──────────────────────────────────────────────────────────────
# 层2 · 语义层覆盖（**归一化** ⇒ 绝对阈值无意义，只用同批内相对量）
# ──────────────────────────────────────────────────────────────
# ★ 为什么必须加这一层：词块覆盖对「**改写式综合**」系统性有偏 ——
#   融合臂的输出是重新推导的，天然不复用原词 ⇒ 词块覆盖必然低
#   ⇒ 只看词块会把「改写能力强」误判成「面塌缩」。
# ★ 为什么用**归一化**：embedding 绝对余弦的量级由**题目内容**主导
#   （跨题差 10×）⇒ 绝对阈值无意义 ⇒ 只用同批内相对排序。
#   cov_i = cos(branch_i, final) / max_j cos(branch_j, final)  ∈ (0,1]

def emb_coverage(arts: list, final: str, embed_fn) -> dict:
    """语义层覆盖：**增量**判据（2026-10-23 修）。

    ★ 踩过的坑：先用「组内归一化 cos」判宽度 ⇒ **选一臂的输出（= 某支原文）
      竟然报 width=4** ⇒ 因为「支j 与被选中的支k 本来就相似(0.86)」
      被误读成「输出保留了支j」⇒ **度量与机制错配**。
    ⇒ 正确判据：**输出对支j的偏好，必须超过「分支池里最像支j的那个分支」**：
        base_j = max_{k!=j} cos(branch_j, branch_k)
        inc_j  = cos(branch_j, output) - base_j
        覆盖 <=> inc_j > 0（**严格**：零增量 = 输出没带来任何额外偏好）
    ⇒ 自检：输出=支k ⇒ inc_k>0 且 inc_j<=0 ⇒ width=1（与词面层一致）
    """
    if not arts or not final.strip():
        return {"cos": [], "inc": [], "mean": 0.0, "width": 0, "width_naive": 0, "n": 0}
    vecs = embed_fn(list(arts) + [final])
    bv = vecs[:len(arts)]
    fv = vecs[-1]
    cos = [float(max(0.0, min(1.0, cosine(v, fv)))) for v in bv]
    n = len(bv)
    base = []
    for i in range(n):
        others = [cosine(bv[i], bv[j]) for j in range(n) if j != i]
        base.append(max(others) if others else 0.0)
    inc = [cos[i] - base[i] for i in range(n)]
    mx = max(cos) if cos else 0.0
    norm = [(c / mx if mx > 1e-9 else 0.0) for c in cos]
    return {"cos": [round(c, 4) for c in cos],
            "base": [round(b, 4) for b in base],
            "inc": [round(x, 4) for x in inc],
            "norm": [round(x, 4) for x in norm],
            "mean_inc": round(sum(inc) / len(inc), 4) if inc else 0.0,
            "mean": round(sum(norm) / len(norm), 4) if norm else 0.0,
            "width": sum(1 for x in inc if x > 1e-6),   # ★ 严格 > 0（零增量不算覆盖）
            "width_naive": sum(1 for x in norm if x >= 0.70),
            "n": n}


def fixed_len_coverage(arts: list, final: str, L: int = 400) -> dict:
    """**定长对照**：把输出截到固定字数 L 再算覆盖 ⇒ 消除"多写"的混淆。

    ★ 为什么必须做：末步各臂的输出量天然不同（融合 ~400 字 vs 不做末步 ~1600 字）
      ⇒ 不控长度，覆盖率天然被输出量拉高 ⇒ 测的是"谁写得多"不是"谁留得下"。
    ★ L 事前登记（默认 400）；另给多档 L 报曲线。
    """
    t = (final or "")[:L]
    return {"L": L, "chars": len(t),
            "covered": covered_branches(arts, t, 0.30),
            "survival": round(survival_rate(arts, t), 4),
            "curve": coverage_curve(arts, t)}


def self_coverage(arts: list, final: str) -> float:
    """**自覆盖率** = 输出与**最像它的那一支**的覆盖率（max over 支）。

    ★ 为什么要有它：`survival_rate` 是**跨分支均值** ⇒ 一个只复制了其中一支的输出
      只能拿到 ≈1/n（n=5 ⇒ 0.2）⇒ **不能**用它做"原样输出"的自校准锚。
      ⇒ `self_coverage` 才是那个锚：**若输出原样复制了某一支 ⇒ �� ≈ 1.0**。
    ★ 用法：臂4（只选不融）是"原样输出其中一支" ⇒ 它的 self_coverage 应 ≈ 1.0
      ⇒ 偏离 ⇒ **臂的语义变了**（或数据错配），而不是"指标坏了"。
    """
    if not arts:
        return 0.0
    kf = keywords(final)
    best = 0.0
    for a in arts:
        ka = keywords(a)
        if not ka:
            continue
        best = max(best, len(ka & kf) / len(ka))
    return float(best)
