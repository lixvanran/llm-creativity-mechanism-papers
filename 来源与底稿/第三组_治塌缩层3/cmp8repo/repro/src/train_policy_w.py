# -*- coding: utf-8 -*-
"""层3 · 动作策略的**自迭代训练**（on-policy REINFORCE）

> 2026-10-22 ｜ 配套 `workflow.py`（36 个可组合动作 + 因子化 softmax 策略）
> 目标：让**架构由训练产生**，而不是人写死的映射（这是负责人四层结构的第 3 层）。

## 为什么用**代理奖励**训练

完整的判官评估一次要 **~228 秒**（实测：抽取 1 次 + 卡片 1–2 次）。
⇒ 用完整评估做内循环 ⇒ 30 个样本 ≈ 2.5 小时，**且样本量根本不够学**。
⇒ ⇒ **两段式**：
1. **内循环（训练）**：用**零判官成本**的代理奖励
   （矛盾数 / 空产出 / 兜底 / 去重后覆盖 / 调用成本）——全部是**本地可算**的
2. **外循环（验证）**：用**完整判官**评估"学出来的策略 vs 查表策略 vs 均匀策略"
   ⇒ ★ **代理奖励是否迁移到真实判据，本身就是一个要报告的发现**（不迁移 ⇒ 如实写）

## 奖励（代理，零判官成本）

```
r = -λ_conflict · n_conflicts          # 发散的代价（矛盾）
    -λ_empty    · n_empty_slots         # 仪器/生成失败
    -λ_fallback · n_fallback_slots
    +λ_cover    · n_distinct_families   # 去冗余后的覆盖（不是字数）
    -λ_cost     · n_calls               # 成本
```

★ `n_distinct_families` 用**数字指纹 + 内容词**去重 ⇒ 不是一个"字数"指标。

## 更新（on-policy REINFORCE，因子化）

动作 `a = (type, scope, strict)`，失败类型 `f`：
```
score(a) = u[type] + v[scope] + t[strict] + m[f][type]
∇ = (r − baseline) · (onehot(type) + onehot(scope) + onehot(strict) + onehot(f,type))
```
⇒ ★ **交互项 `m` 是唯一让"当前失败类型"影响动作选择的通道**
（我们实测过：与 op 无关的状态特征对选择**零作用**）。

## 纪律

* **baseline** 用同批次的移动平均（不是零）⇒ 减方差
* **种子可复现**：base seed + rng 按 (轮, 题) 派生 ⇒ 断点续跑一致
* **不重跑到好看**：跑几次就是几次
* **不宣称学到了**：训练完必须与 `from_lookup()`（查表策略）和**均匀策略**在同一批题上比
* ⚠️ **代理奖励 ≠ 真实判据** ⇒ 验证不通过就如实写"代理奖励未迁移"

## 用法

```bash
python3 -B train_policy_w.py --tasks 3 --rounds 8 --out runs/policy_train
```
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import statistics
import sys
import time
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "judge"))

# ⚠️ 沙箱：`.pyc` 失效不可靠 ⇒ 跑前清缓存 + 禁止写
sys.dont_write_bytecode = True
shutil.rmtree(os.path.join(HERE, "__pycache__"), ignore_errors=True)

import workflow as W          # noqa: E402
import u1_lib as U            # noqa: E402
import metrics_priorart as MP  # noqa: E402

DEV = os.environ.get("DEV_DIR") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "devset")
OUT_DEFAULT = os.path.join(HERE, "runs", "policy_train")

# 代理奖励权重（**事前写死**，不调）
# ★★ 奖励权重（事前写死）：★ trap 与 width 是**新加的两项**
#    —— 对齐负责人的两个目标："局部不钻牛角尖" + "整体思维面更宽"
LAMBDA = dict(conflict=1.0, empty=0.5, fallback=0.5, cover=0.30, cost=0.02,
              conflict_pairs=0.8,
              trap=6.0,      # ★ 踩一次陷阱的代价（很大 ⇒ 策略会避开）
              width=4.0)     # ★ 分支分散度的收益（⇒ 策略会想要更宽）


# ══════════════════════════════════════════════════════════════════════
# 强制指定动作的策略（用于"试这个动作，看收益如何"）
# ══════════════════════════════════════════════════════════════════════
class ForcedPolicy(W.ActionPolicy):
    """始终返回指定动作（其余参数照常打分，只是不参与选择）。"""

    def __init__(self, spec, base: Optional[W.ActionPolicy] = None,
                 forced_arb: Optional[int] = None,
                 forced_arch: Optional[tuple] = None):
        super().__init__(base.export() if base else None)
        self._forced = spec
        self._forced_arch = forced_arch
        self.used_arch = None
        # ★ 固定仲裁选择（层3 的第二件事：训练时试某个仲裁档，看收益）
        self._forced_arb = forced_arb
        self.used_arb = None

    def choose(self, failure_kind, rng):        # noqa: D102
        return self._forced

    def choose_arbitration(self, failure_kind, rng):
        if self._forced_arb is not None:
            self.used_arb = self._forced_arb
            return self._forced_arb
        v = super().choose_arbitration(failure_kind, rng)
        self.used_arb = v
        return v

    def choose_architecture(self, failure_kind, rng):
        """★ 固定架构决策（发散度 + 合并方式）⇒ 训练时能"试某种架构、看收益"。"""
        if self._forced_arch is not None:
            self.used_arch = self._forced_arch
            return self._forced_arch
        v = super().choose_architecture(failure_kind, rng)
        self.used_arch = v
        return v


# ══════════════════════════════════════════════════════════════════════
# 代理奖励
# ══════════════════════════════════════════════════════════════════════
def population_diversity(claims: Sequence[str], history: Sequence[Sequence[str]]) -> float:
    """★ **种群级**多样性：与"历史中其它样本"的平均差异度 = 1 − 平均 Self-Sim。

    ★★ 为什么必须改成种群级（2026-10-22 实测教训）：
      先前用**样本内**的"去冗余覆盖量"当多样性分量，而它与质量分量里的
      **矛盾数强负相关**（矛盾多 ⇒ 内容被削减 ⇒ 覆盖少）⇒ **两个分量共线**
      ⇒ **二元目标退化成标量** ⇒ Pareto 前沿只剩 1 个点（实测 9 样本仍是 1）。
      ⇒ ⇒ 而 EoT / MOAE 的多样性是**种群层面**的（候选集之间的差异），
      不是单个候选的属性 ⇒ 这里改成"与历史的差异"。
    """
    if not history:
        return 0.0
    sims = [MP.self_sim([list(claims), list(h)], mode="decision") for h in history]
    if not sims:
        return 0.0
    return 1.0 - (sum(sims) / len(sims))


def proxy_reward(res: Dict[str, Any], task: Optional[Dict[str, Any]] = None
                 ) -> Dict[str, Any]:
    """从一次运行的读数里算**代理奖励**（零判官成本）。

    ★★ 2026-10-24 重写奖励项以**对齐负责人给的两个目标**：
      ① **局部不钻牛角尖** ⇒ `−λ_trap × 陷阱命中数`
         （★ 这一项**之前完全没有** ⇒ 上一轮训练"没学出偏好"的根因就在这）
      ② **整体思维面更宽** ⇒ `+λ_width × 分支分散度`（**集合级**，在训练循环里算）
      ③ 闭合的代价 ⇒ `−λ_conflict_pairs × 跨槽位冲突对数`
      ④ 成本 ⇒ `−λ_cost × 调用数`
    """
    conflicts = int(res.get("n_conflicts") or 0)
    failures = res.get("failures") or {}
    n_empty = int(failures.get("empty") or 0)
    n_fb = int(failures.get("fallback") or 0)
    claims = res.get("claims") or []
    fams = set()
    for c in claims:
        fams.add((tuple(sorted(W._fingerprint(c))), tuple(sorted(W._CN_CONTENT.findall(c)))))
    cover = len(fams)
    calls = len(res.get("ops") or [])
    r = (-LAMBDA["conflict"] * conflicts
         - LAMBDA["empty"] * n_empty
         - LAMBDA["fallback"] * n_fb
         + LAMBDA["cover"] * cover
         - LAMBDA["cost"] * calls)
    # ★ 二元目标：质量（越高越好）= −(矛盾 + 空 + 兜底 + 成本)；多样性（越高越好）= 覆盖族数
    # ★★ 冲突项（**本地检测 ⇒ 零判官成本**）：跨槽位矛盾的对数
    #   ⇒ 层3 的目标函数里**必须有"闭合的代价"**，否则策略只会一味发散
    n_conf = len(W.detect_opposite_pairs(res.get("claims") or []))
    # ★★ 陷阱命中（**钻牛角尖的直接代价**）：只在带 trap_fingerprints 的题上可测
    n_trap = 0
    if task and task.get("trap_fingerprints"):
        try:
            import premature_closure as _PC
            _pc = _PC.premature_closure(task, res.get("answer") or "")
            n_trap = 1 if _pc.get("hit") else 0
        except Exception:
            n_trap = 0
    quality = -(LAMBDA["conflict"] * conflicts + LAMBDA["empty"] * n_empty
                + LAMBDA["fallback"] * n_fb + LAMBDA["cost"] * calls
                + LAMBDA["conflict_pairs"] * n_conf
                + LAMBDA["trap"] * n_trap)
    # ★★ **思维面宽度**（样本内：各分支彼此有多分散）⇒ 越高越宽
    #    零 embedding、纯文本（Self-Sim 原口径，Lake et al. NAACL'25）
    _paths = [p for p in (res.get("paths") or []) if p.get("claims")]
    if len(_paths) >= 2:
        _cl = [list(p["claims"]) for p in _paths]
        _sim = MP.self_sim(_cl, mode="bigram") or 0.0
        width = max(0.0, 1.0 - _sim)
    else:
        width = 0.0
    r = (quality + LAMBDA["width"] * width)      # ★ 奖励 = 质量代价 + 宽度收益
    diversity = float(cover)
    return dict(r=r, quality=quality, diversity=diversity, width=width,
                conflicts=conflicts, n_empty=n_empty, n_fallback=n_fb,
                n_conflict_pairs=n_conf, n_trap_hits=n_trap,
                cover=cover, calls=calls, claims=claims)


# ══════════════════════════════════════════════════════════════════════
# 更新（因子化 REINFORCE）
# ══════════════════════════════════════════════════════════════════════
def reinforce(pol: W.ActionPolicy, spec: W.ActionSpec, failure_kind: str,
              r: float, baseline: float, lr: float = 0.5,
              adv_override: Optional[float] = None) -> Dict[str, Any]:
    """一次 on-policy 更新。返回本次的梯度分量（便于审计）。

    ★ `adv_override`：★ **两种目标共用同一套更新规则**，唯一差别是
      「这个样本能不能留在档案里」⇒ 留在档案（精英）adv=+1，被淘汰 adv=−1。
      ⇒ 于是**唯一变量 = 选择规则** ⇒ 干净的受控对照。
    """
    rt, sc, st = spec
    adv = (r - baseline) if adv_override is None else float(adv_override)
    g = dict(u=0.0, v=0.0, t=0.0, m=0.0)
    pol.u[W.REPAIR_IDS.index(rt)] += lr * adv
    g["u"] = lr * adv
    pol.v[W.SCOPE_IDS.index(sc)] += lr * adv
    g["v"] = lr * adv
    pol.t[W.STRICT_IDS.index(st)] += lr * adv
    g["t"] = lr * adv
    if failure_kind in W.FAILURE_IDS:
        fi = W.FAILURE_IDS.index(failure_kind)
        pol.m[fi][W.REPAIR_IDS.index(rt)] += lr * adv
        g["m"] = lr * adv
    return dict(adv=adv, grad=g, spec=spec, failure_kind=failure_kind)


# ══════════════════════════════════════════════════════════════════════
# 主循环
# ══════════════════════════════════════════════════════════════════════
def load_tasks(n=None, mixed=True, exclude=None):
    """训练题集：**DEV 9 题 + 诱导钻牛角尖 6 题**（混合）。

    ★ 必须混合：陷阱命中（钻牛角尖的代价）**只在带 trap_fingerprints 的题上可测**
    ⇒ ⇒ 只用原来的 9 道核对型题 ⇒ **"局部不钻牛角尖"这一项永远测不到** ⇒ 策略学不到。
    """
    with open(os.path.join(DEV, "devset.json"), encoding="utf-8") as f:
        d = json.load(f)
    tasks = list(d["tasks"] if isinstance(d, dict) and "tasks" in d else d)
    adv_path = os.path.join(DEV, "DEV-ADV-2026-10-24.json")
    if mixed and os.path.exists(adv_path):
        with open(adv_path, encoding="utf-8") as f:
            ad = json.load(f)
        tasks = tasks + list(ad["tasks"] if isinstance(ad, dict) and "tasks" in ad else ad)
    # ★ 2026-10-24 留出集协议：把留出题从训练题集里**排除**（默认空 ⇒ 行为不变）
    if exclude:
        ex = set(exclude)
        before = len(tasks)
        tasks = [t for t in tasks if t.get("task_id") not in ex]
        print("  [exclude] 训练题集排除 %s ⇒ %d 题（原 %d 题）" % (sorted(ex), len(tasks), before))

    return tasks[:n] if n else tasks


def run_one(llm, task, spec, seed, slots=3, rounds=2, forced_arb=None,
            forced_arch=None):
    """用**指定动作 + 指定仲裁档**跑一遍，返回读数（★ 不做判官评估 ⇒ 便宜）。"""
    pol = ForcedPolicy(spec, forced_arb=forced_arb, forced_arch=forced_arch)
    wf = W.CollapseFixWorkflow(
        llm, n_slots=slots, seed=seed, model=os.environ.get("MM_MODEL",
                                                            "MiniMax-M3.1-Flash-Preview"),
        judge_model="", max_rounds=rounds, evolve=True, action_mode="policy",
        policy=pol, policy_seed=seed, arbitrate_mode="learned")
    r = wf.run(task["ask"])
    r["_arb_used"] = pol.used_arb
    r["_arch_used"] = pol.used_arch
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", type=int, default=3)
    ap.add_argument("--exclude", default="", help="★ 逗号分隔的 task_id，从训练题集排除（留出集用）；默认空=全部保留")
    ap.add_argument("--rounds", type=int, default=8, help="训练轮数")
    ap.add_argument("--samples", type=int, default=4, help="每轮样本数")
    ap.add_argument("--slots", type=int, default=3)
    ap.add_argument("--rounds-per-run", type=int, default=2)
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--seed", type=int, default=20261022)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--objective", default="scalar",
                    choices=["scalar", "scalar_r", "pareto"],
                    help="★ 选择规则：scalar=只留最优（档案必然=1 ⇒ 中庸）；"
                         "pareto=留全部非支配解；scalar_r=最早的标量 REINFORCE（第三臂）")
    ap.add_argument("--stub", action="store_true",
                    help="用本地 stub LLM（零 API 成本）跑冒烟；★ 读数不代表真实效果")
    args = ap.parse_args()

    excl = [x.strip() for x in (args.exclude or "").split(",") if x.strip()]
    tasks = load_tasks(args.tasks, exclude=excl)
    model = os.environ.get("MM_MODEL", "MiniMax-M3.1-Flash-Preview")
    if args.stub:
        from test_workflow import StubLLM
        llm = StubLLM()
    else:
        llm = U.MiniMaxLLM()
    os.makedirs(args.out, exist_ok=True)
    ckpt = os.path.join(args.out, "policy.json")

    pol = W.ActionPolicy()
    start_round = 0
    hist: List[Dict[str, Any]] = []
    if args.resume and os.path.exists(ckpt):
        with open(ckpt, encoding="utf-8") as f:
            st = json.load(f)
        pol = W.ActionPolicy.load(st["policy"])
        start_round = int(st.get("round", 0))
        hist = st.get("hist", [])
        print("  断点续跑：从第 %d 轮开始" % start_round, flush=True)

    base = 0.0
    # ★ 策略档案：两种目标**只差选择规则** ⇒ 档案规模/策略间多样性就是对照读数
    archive = MP.StrategyArchive(mode=("scalar" if args.objective == "scalar_r"
                                    else args.objective))
    # ★ 全部样本历史（用于种群级多样性）；**与档案不同** ⇒ 档案会淘汰，history 不淘汰
    all_items: List[Dict[str, Any]] = []
    t_all = time.time()
    for rnd in range(start_round, args.rounds):
        rnd_hist = []
        for si in range(args.samples):
            task = tasks[(rnd * args.samples + si) % len(tasks)]
            seed = args.seed + 1000 * rnd + si          # ★ rng 按 (轮, 题) 派生 ⇒ 可复现
            rng = random.Random(seed)
            # ① 采样一个动作（从当前策略）
            spec = pol.choose("conflict", rng)
            # ★ 同时抽一个**仲裁档**（mark / keep_pos / keep_neg）⇒ 一起学
            _arb = pol.choose_arbitration("conflict", rng)
            # ★ 同时抽**架构决策**（发散度 + 合并方式）⇒ 一起学
            _nf, _mm = pol.choose_architecture("conflict", rng)
            _arch = (int(_nf), str(_mm))
            # ② 用它跑一遍（观测实际失败类型）
            try:
                res = run_one(llm, task, spec, seed, args.slots, args.rounds_per_run,
                              forced_arb=_arb, forced_arch=_arch)
            except Exception as e:
                print("  ⚠️ 样本失败（计入，不重试）：%s: %s" % (type(e).__name__, e), flush=True)
                continue
            pr = proxy_reward(res, task)
            # ③ 实际发生的失败类型（用于交互项）
            fk = None
            for k in ("conflict", "empty", "all_unmentioned", "zero_load_bearing",
                      "fallback", "truncated"):
                if (res.get("failures") or {}).get(k):
                    fk = k
                    break
            if fk is None:
                fk = "conflict"
            # ④ 入档案（★ 两种目标唯一的差别就在这里）
            # ★ 多样性用**种群级**（与历史的差异），不是样本内覆盖量
            _pop_div = population_diversity(pr.get("claims") or [],
                                            [it.get("claims") or [] for it in all_items])
            pr["diversity_population"] = _pop_div
            item = dict(quality=pr["quality"], diversity=_pop_div,
                        scalar=pr["r"], spec=list(spec), failure_kind=fk,
                        claims=pr.get("claims") or [], task=task.get("task_id"))
            kept = archive.offer(item)
            all_items.append(dict(quality=pr["quality"], diversity=_pop_div,
                                  scalar=pr["r"], spec=list(spec),
                                  claims=pr.get("claims") or [],
                                  task=task.get("task_id")))
            # ⑤ 更新
            # ★ 优势：**留在档案里 = 精英（adv=+1），被淘汰 = −1**
            #   ⇒ 两种目标**同一套更新规则** ⇒ 唯一变量是"谁能留在档案里"
            # ⚠️ baseline **跨轮连续**（不能每轮重置 ⇒ 否则每轮第一个样本 adv=0 ⇒ 白学）
            if not hist:
                base = pr["r"]
            else:
                base = 0.7 * base + 0.3 * pr["r"]
            adv_scalar = (pr["r"] - base) if args.objective == "scalar_r" else (1.0 if kept else -1.0)
            g = reinforce(pol, spec, fk, pr["r"], base, adv_override=adv_scalar)
            # ★ 更新**仲裁权重**（层3 的第二件事）
            if _arb is not None:
                pol.arb[_arb] += 0.5 * adv_scalar
            # ★ 更新**架构权重**（发散度 + 合并方式）⇒ 让"该不该发散/怎么合并"被学出来
            if _arch is not None:
                _nfi = W.ActionPolicy.NF_IDS.index(_arch[0]) if _arch[0] in W.ActionPolicy.NF_IDS else None
                _mmi = W.ActionPolicy.MM_IDS.index(_arch[1]) if _arch[1] in W.ActionPolicy.MM_IDS else None
                if _nfi is not None:
                    pol.nf[_nfi] += 0.5 * adv_scalar
                if _mmi is not None:
                    pol.mm[_mmi] += 0.5 * adv_scalar
            rec = dict(round=rnd, sample=si, task=task.get("task_id"),
                       spec=list(spec), failure_kind=fk, r=pr["r"], base=base,
                       kept=kept, archive_n=len(archive.items),
                       arb=_arb, arch=_arch,
                       # ★ 只把标量化的分量进日志（claims 太长，另存档案）
                       **{k: v for k, v in pr.items() if k not in ("r", "claims")},
                       grad=g["grad"])
            rnd_hist.append(rec)
            hist.append(rec)
            print("  轮%-2d 样本%-2d %s  动作=%s  失败=%-14s r=%+.2f (base %+.2f) 矛盾=%d 覆盖=%d"
                  % (rnd, si, task.get("task_id"), spec, fk, pr["r"], base,
                     pr["conflicts"], pr["cover"]), flush=True)
        # 每轮落盘（断点续跑）
        with open(ckpt, "w", encoding="utf-8") as f:
            json.dump(dict(policy=pol.export(), round=rnd + 1, hist=hist,
                           lam=LAMBDA, seed=args.seed,
                           objective=args.objective,
                           archive=archive.stats(),
                           history_n=len(all_items),
                           history_specs=[it.get("spec") for it in all_items]),
                      f, ensure_ascii=False, indent=2)
        print("  ── 轮 %d 完成（累计 %.1f 分钟）──" % (rnd, (time.time() - t_all) / 60), flush=True)

    print("=" * 72)
    print("训练结束：%d 轮，%d 样本，%.1f 分钟" % (args.rounds, len(hist),
                                          (time.time() - t_all) / 60))
    print("策略：%s" % json.dumps(pol.export(), ensure_ascii=False)[:400])
    print("落盘：%s" % ckpt)
    st = archive.stats()
    print("★ 策略档案（%s）：规模=%d  策略间 Self-Sim=%s  #distinct=%s  碰撞C=%s"
          % (args.objective, st.get("n_items", 0), st.get("self_sim"),
             st.get("distinct_families"),
             (st.get("collision") or {}).get("C")))
    print("=" * 72)
    print("★ 提醒：**代理奖励 ≠ 真实判据** ⇒ 必须再用完整判官比一次"
          "（学出来的 vs 查表 vs 均匀），否则不算数。")


if __name__ == "__main__":
    main()
