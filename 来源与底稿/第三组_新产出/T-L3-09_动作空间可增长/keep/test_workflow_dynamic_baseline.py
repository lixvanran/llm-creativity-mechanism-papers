# -*- coding: utf-8 -*-
"""治塌缩工作流（W）的自检 —— **证明它真的会动，而且不会假动**。

> 2026-10-22 ｜ 配套 `workflow.py`

## 为什么要有这个文件
本项目一路吃过两次亏：
① 契约的 δ_judge 在 temp=0 下恒为 0（**定义造成的"没动静"**）；
② 自检首版报"变异全被抓住"，但失败的全是**基线本来就失败**的检查（**假阳性**）。

⇒ 所以本文件的两条纪律：
* **每个机制都要有一条"它真的动了"的检查**（不是"跑通"）；
* **变异注入前必须基线全过**（否则"被抓住"可能只是抓住了预存在的失败）。

## 变异注入清单
| # | 变异 | 必须 FAIL 的检查 |
|:-:|---|---|
| 1 | `select_frames` 去掉 seed（永远返回同一组） | `frames_seed_reproducible` / `frames_vary_by_seed` |
| 2 | `dedup` 变成空操作 | `dedup_removes_redundant` |
| 3 | `propose_new_action` 对未知失败类型也返回动作 | `action_evolve_rejects_unknown_kind` |
| 4 | 工作流**去掉"没有失败就不演化"的短路** | `no_failure_no_evolution` |
| 5 | `BehaviorArchive.offer` 总是覆盖（不留最优） | `archive_keeps_best_per_cell` |

## 纪律
* 全部用**本地 stub LLM**，**不调用任何模型 API** ⇒ 零成本、可离线跑。
* stub 的行为是**确定的**，因此"动了"可以精确断言。
"""

from __future__ import annotations

import argparse
import importlib
import os
import shutil
import sys
import tempfile
import traceback

# ⚠️ 2026-10-22：**沙箱里 .pyc 的 mtime 失效判断不可靠**
#    （实测：源码已改、但 import 拿到的还是旧模块 ⇒ 跑旧代码却以为在跑新代码）
#    ⇒ 跑之前必须清缓存 + 禁止再写。
sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import workflow as W  # noqa: E402


# ══════════════════════════════════════════════════════════════════════
# stub LLM（**确定**的 ⇒ "动了"可精确断言）
# ══════════════════════════════════════════════════════════════════════
class StubLLM:
    """按 purpose 分派的可预测 LLM。

    ★ `empty_slots` 里的帧 id 在第一次被调用时返回**空**（模拟"抽不出断言"的失败）
      ⇒ 工作流应当据此**演化出新动作**。
    """

    def __init__(self, empty_slots=(), n_calls=None, slot_content=None):
        self.empty_slots = set(empty_slots)
        self.calls = []
        self.n_calls = 0
        self.seen_slots = set()
        # 每个槽位**各自**的内容（用于制造跨槽位矛盾）
        self.slot_content = dict(slot_content or {})
        self._last = ""

    def chat(self, prompt, *, model=None, temp=None, max_tokens=None,
             budgets=None, min_ok=None, purpose=None):
        self.n_calls += 1
        self.calls.append(purpose or "")
        p = purpose or ""
        if p.startswith("W_slot"):
            fid = p.replace("W_slot_", "")
            if fid in self.empty_slots:
                # ⚠️ 必须**每次都空**：`_chat` 现在会因空输出**抬预算重试**
                #    ⇒ 若只第一次空，重试会把它掩盖掉 ⇒ 失败通道测不到
                self.seen_slots.add(fid)
                return ""
            if fid in self.slot_content:
                self._last = self.slot_content[fid]
                return self.slot_content[fid]
            self._last = ("- 依据 EV-03 写明的条件成立时，顺序读取为 7450 MB/s\n"
                           "- 若保修条款为五年，则在第 36 个月内仍然有效\n"
                           "- 当并发写入超过 1000 IOPS 时，延迟会超过 1 毫秒")
            return self._last
        if p.startswith("B0_multi"):
            # ★ 等预算臂的生成 ⇒ 也要回填 `_last`，否则抽取拿到空串
            #   ⇒ 空抽取会**触发 3 次阶梯重试** ⇒ 调用数虚高 3 倍
            self._last = ("- 依据 EV-03 写明的条件成立时，顺序读取为 7450 MB/s\n"
                           "- 若保修条款为五年，则在第 36 个月内仍然有效\n"
                           "- 当并发写入超过 1000 IOPS 时，延迟会超过 1 毫秒")
            return self._last
        if p == "W_extract":
            # ⚠️ 必须**回显本槽位的产出** ⇒ 否则所有槽位抽出的断言都一样
            #    ⇒ **跨槽位矛盾被抹平** ⇒ 矛盾检测根本测不到
            return getattr(self, "_last", "") or "" 
        if p == "W_aggregate":
            return ("- 顺序读取为 7450 MB/s\n- 保修五年在第 36 个月仍有效\n"
                    "- 并发写入超过 1000 IOPS 时延迟超过 1 毫秒")
        return "- 默认断言：条件成立时该结论为真"


# ══════════════════════════════════════════════════════════════════════
# 检查框架
# ══════════════════════════════════════════════════════════════════════
class Check:
    def __init__(self, name):
        self.name = name
        self.ok = False
        self.detail = ""
        self.error = None


def run_checks():
    checks = []

    def add(name, fn):
        c = Check(name)
        try:
            c.ok, c.detail = fn()
        except Exception as e:
            c.ok = False
            c.error = "%s: %s" % (type(e).__name__, e)
        checks.append(c)
        return c

    # ── 1. 选帧：可复现 / 随 seed 变 / 互不重复 / 必含 wild
    def c1():
        a = W.select_frames(4, seed=7)
        b = W.select_frames(4, seed=7)
        if a != b:
            return False, "同 seed 结果不同：%r vs %r" % (a, b)
        if len(set(a)) != len(a):
            return False, "抽到重复帧：%r" % (a,)
        if not any(W._FRAME_BY_ID[i]["wild"] for i in a):
            return False, "没有 wild 帧：%r" % (a,)
        return True, "seed=7 → %s（可复现、唯一、含 wild）" % (a,)

    def c2():
        a = W.select_frames(4, seed=1)
        b = W.select_frames(4, seed=2)
        if a == b:
            return False, "不同 seed 给出同一组 ⇒ seed 没起作用"
        return True, "seed=1 → %s ／ seed=2 → %s" % (a, b)

    # ── 3. 去冗余真的去
    def c3():
        items = [
            "顺序读取速度为 7450 MB/s，接口是 PCIe Gen4",
            "顺序读取速度为 7450 MB/s，接口是 PCIe Gen4",   # 几乎同句
            "保修期限是 5 年",                              # 独立
        ]
        kept = W.dedup(items)
        if len(kept) != 2:
            return False, "去冗余后剩 %d 条（应 2）：%r" % (len(kept), kept)
        if "保修期限是 5 年" not in kept:
            return False, "把独立条目误删了：%r" % (kept,)
        return True, "3 条 → %d 条" % len(kept)

    # ── 4. 动作演化：只对已知失败类型提案
    def c4():
        arc = W.ActionArchive()
        nm = W.propose_new_action("empty", "s0", arc)
        if not nm or nm not in arc.actions:
            return False, "未产出新动作：%r" % nm
        again = W.propose_new_action("empty", "s1", arc)
        if again != nm:
            return False, "同一失败类型应复用同一动作名：%r vs %r" % (nm, again)
        if len(arc.actions) != 1:
            return False, "动作数应为 1，实际 %d" % len(arc.actions)
        bad = W.propose_new_action("not_a_kind", "s0", arc)
        if bad is not None:
            return False, "未知失败类型竟产出了动作：%r" % bad
        return True, "动作 %s 出生，动作集=1" % nm

    # ── 5. 行为档案：每格留最优
    def c5():
        arc = W.BehaviorArchive()
        arc.offer("k1", payload="a", score=3)
        arc.offer("k1", payload="b", score=7)
        arc.offer("k1", payload="c", score=5)
        arc.offer("k2", payload="d", score=1)
        st = arc.stats()
        if st["n_cells"] != 2:
            return False, "格子数 %d（应 2）" % st["n_cells"]
        if arc.cells["k1"]["score"] != 7:
            return False, "k1 未留最优（%r）" % arc.cells["k1"]["score"]
        return True, "2 格，k1 留 7"

    # ── 6. 中庸度四指标
    def c6():
        arms = [["a", "b", "c"], ["a", "b"], ["a", "b", "d"]]
        cr = W.common_rate(arms)
        if not (0.3 <= cr <= 0.7):
            return False, "交集率 %r 不在合理区间" % cr
        rounds = [[["a", "b"]], [["a", "b", "c"], ["a", "b", "c"]]]
        mu = W.marginal_util(rounds)
        if len(mu) != 1:
            return False, "边际利用率长度 %d（应 1）" % len(mu)
        if mu[0] <= 0:
            return False, "第二轮有新增却算出边际利用率 %r" % mu[0]
        dm = W.dist_to_modal(["a", "b"], arms)
        if dm < 0:
            return False, "中庸距离为负 %r" % dm
        cs = W.coverage_saturation(rounds, universe=4)
        if len(cs) != 2 or cs[-1] < cs[0]:
            return False, "覆盖饱和度不单调：%r" % cs
        return True, "交集率=%.3f 边际=%.3f 距离=%.3f 饱和=%r" % (cr, mu[0], dm, cs)

    # ── 7. ★ 工作流端到端：**真的演化出动作了**
    def c7():
        # ★ 必须**制造一次真实失败**（某个槽位第一次抽不出断言）⇒ 才有东西可演化
        frames = W.select_frames(3, seed=5)
        llm = StubLLM(empty_slots={frames[0]})
        wf = W.CollapseFixWorkflow(llm, n_slots=3, seed=5, model="stub",
                                   judge_model="stub", max_rounds=2)
        r = wf.run("990 PRO 1TB 的哪些参数成立？")
        if not r["claims"]:
            return False, "没有产出任何断言"
        if not r["frames"]:
            return False, "没有选帧"
        if r["archive"]["n_actions"] < 1:
            return False, ("★ 动作档案没长出新动作（failures=%r）⇒ 演化没发生"
                           % (r["failures"],))
        if not r["failures"].get("empty"):
            return False, "失败通道没记到 empty（failures=%r）" % (r["failures"],)
        if not any(o.startswith("EVOLVE") for o in r["ops"]):
            return False, "操作序列里没有 EVOLVE 标记：%r" % (r["ops"],)
        if r["illum"]["n_cells"] < 1:
            return False, "行为档案为空"
        return True, ("断言 %d 条 ／ 动作集 %d（%s）／ 失败 %r ／ 格 %d"
                      % (len(r["claims"]), r["archive"]["n_actions"],
                         r["archive"]["names"], r["failures"], r["illum"]["n_cells"]))

    # ── 8. ★ 没有失败 ⇒ **一轮生成就够**（不演化、不白跑第二轮）
    # ⚠️ 2026-10-22 修正：原先只看「动作档案大小」⇒ **盯错了可观测量**
    #   （变异「去掉短路」后动作档案**也是 0** —— 它只是让第二轮白跑 ⇒ 抓不住）。
    #   真正的差异 = **生成轮数 / LLM 调用数** ⇒ 改盯这个。
    def c8():
        llm = StubLLM()          # 不制造任何空槽位
        wf = W.CollapseFixWorkflow(llm, n_slots=3, seed=5, model="stub",
                                   judge_model="stub", max_rounds=3)
        r = wf.run("990 PRO 1TB 的哪些参数成立？")
        n_slot_calls = sum(1 for p in llm.calls if str(p).startswith("W_slot"))
        if r["archive"]["n_actions"] != 0:
            return False, ("★ 没有失败却演化了 %d 个动作 ⇒ 动作空间在无节制增长"
                           % r["archive"]["n_actions"])
        if n_slot_calls != 3:
            return False, ("★ 没有失败却生成了 %d 次（应 3 = 一轮 × 3 槽位）"
                           "⇒ 白跑了一轮" % n_slot_calls)
        if any(o.startswith("EVOLVE") for o in r["ops"]):
            return False, "没有失败却出现了 EVOLVE 标记：%r" % (r["ops"],)
        return True, "无失败 ⇒ 动作集 0、生成 1 轮（3 次）"

    # ── 9. 槽位互不可见：★ 第二个槽位的提示里**不能有别人的稿**
    def c9():
        llm = StubLLM()
        wf = W.CollapseFixWorkflow(llm, n_slots=3, seed=5, model="stub",
                                   judge_model="stub", max_rounds=1)
        wf.run("990 PRO 1TB 的哪些参数成立？")
        slot_prompts = []
        orig = llm.chat

        def spy(prompt, **kw):
            if str(kw.get("purpose", "")).startswith("W_slot"):
                slot_prompts.append(prompt)
            return orig(prompt, **kw)
        llm.chat = spy
        wf2 = W.CollapseFixWorkflow(llm, n_slots=3, seed=5, model="stub",
                                    judge_model="stub", max_rounds=1)
        wf2.run("990 PRO 1TB 的哪些参数成立？")
        if len(slot_prompts) < 3:
            return False, "只抓到 %d 个槽位提示" % len(slot_prompts)
        # 各槽位提示应**互不相同**（认知帧不同）且**不含对方的草稿**
        if len(set(slot_prompts)) != len(slot_prompts):
            return False, "不同槽位拿到了完全相同的提示 ⇒ 认知位置没解耦"
        return True, "%d 个槽位提示互不相同" % len(slot_prompts)

    # ── 10. ★ 机械汇总**不许丢东西**（2026-10-22 实测 bug 的正面防线）
    #    实测：模型汇总在 adaptive thinking 下预算被吃光 ⇒ 汇总为空
    #         ⇒ 整条答案承重维度 0（D01：W 臂 dims=0 vs B0 dims=3）
    def c10():
        llm = StubLLM()
        wf = W.CollapseFixWorkflow(llm, n_slots=3, seed=5, model="stub",
                                   judge_model="stub", max_rounds=1,
                                   merge_mode="mechanical", learn_architecture=False)
        r = wf.run("990 PRO 1TB 的哪些参数成立？")
        if "AGGREGATE(mechanical)" not in r["ops"]:
            return False, "默认没走机械汇总：ops=%r" % (r["ops"],)
        if not r["claims"]:
            return False, "机械汇总后一条断言都没有"
        # 答案正文里的条目数 == 装配出的断言数（**不多不少**）
        n_lines = len([l for l in (r["answer"] or "").splitlines() if l.strip()])
        if n_lines != len(r["claims"]):
            return False, ("★ 装配 %d 条但答案只有 %d 行 ⇒ 汇总在丢东西"
                           % (len(r["claims"]), n_lines))
        # 机械汇总**不该**多花一次"装配后二次抽取"的调用
        n_extract = sum(1 for p in llm.calls if p == "W_extract")
        n_slot = sum(1 for p in llm.calls if str(p).startswith("W_slot"))
        if n_extract != n_slot:
            return False, ("抽取次数 %d ≠ 槽位数 %d ⇒ 存在多余的二次抽取"
                           % (n_extract, n_slot))
        return True, "机械汇总：%d 条断言 / %d 行 / 无二次抽取" % (
            len(r["claims"]), n_lines)

    # ── 11. ★★ 层2 / 层3 分离：关掉"演化"这一个自由度，其余不变
    #     层2「用设计的手段」：架构先验设计好、**运行时不自修改**（但**仍记失败**）
    #     层3「用训练/自迭代的手段」：从失败**构造新动作**
    def c11():
        frames = W.select_frames(3, seed=5)
        # 层2
        llm2 = StubLLM(empty_slots={frames[0]})
        wf2 = W.CollapseFixWorkflow(llm2, n_slots=3, seed=5, model="stub",
                                    judge_model="stub", max_rounds=2,
                                    evolve=False, layer="L2")
        r2 = wf2.run("990 PRO 1TB 的哪些参数成立？")
        # 层3
        llm3 = StubLLM(empty_slots={frames[0]})
        wf3 = W.CollapseFixWorkflow(llm3, n_slots=3, seed=5, model="stub",
                                    judge_model="stub", max_rounds=2,
                                    evolve=True, layer="L3")
        r3 = wf3.run("990 PRO 1TB 的哪些参数成立？")
        if r2["archive"]["n_actions"] != 0:
            return False, ("★ 层2（evolve=False）却长了 %d 个动作 ⇒ 分离失效"
                           % r2["archive"]["n_actions"])
        if r3["archive"]["n_actions"] < 1:
            return False, ("★ 层3（evolve=True）没长出新动作（failures=%r）"
                           % (r3["failures"],))
        if not r2["failures"]:
            return False, "★ 层2 应当**照样记录失败**（那是层3 的学习信号）"
        if r2.get("evolve") is not False or r3.get("evolve") is not True:
            return False, "读数里没有记 evolve 开关 ⇒ 无法归档时区分层"
        return True, ("层2：动作 0、失败 %r；层3：动作 %d"
                      % (r2["failures"], r3["archive"]["n_actions"]))

    # ── 12. ★ 矛盾检测：**零判官成本**，且能抓住 D01 的真实观测
    def c12():
        # ★ D01 真实案例：层2 写「①③④正确，②错误」，直调写「②正确」
        real = ["①③④正确，②错误", "②正确"]
        cf = W.detect_conflicts(real)
        if not cf:
            return False, "★ D01 的真实矛盾没被抓住"
        kinds = {c["kind"] for c in cf}
        if "option_verdict" not in kinds:
            return False, "没识别成选项判定冲突：%r" % (kinds,)
        # 一致的内容不该误报
        ok = ["①正确：顺序读取 7450 MB/s", "②正确：保修 5 年"]
        if W.detect_conflicts(ok):
            return False, "★ 一致的断言被误报成冲突：%r" % (W.detect_conflicts(ok),)
        return True, "D01 案例抓到（%s），一致内容不误报" % (sorted(kinds),)

    # ── 13. ★ 矛盾能**驱动演化**（层3 的第一个真实学习信号）
    def c13():
        frames = W.select_frames(3, seed=5)
        llm = StubLLM(slot_content={
            frames[0]: "- ①③④正确，②错误\n- 顺序读取为 7450 MB/s",
            frames[1]: "- ②正确：随机读 140 万 IOPS",
        })
        wf = W.CollapseFixWorkflow(llm, n_slots=3, seed=5, model="stub",
                                   judge_model="stub", max_rounds=2)
        r = wf.run("990 PRO 1TB：①顺序读7450MB/s ②随机读140万IOPS ③保修5年 ④耐久600TBW。哪些正确？")
        if not r.get("n_conflicts"):
            return False, "★ 没检测到矛盾（failures=%r）" % (r["failures"],)
        if "act_conflict" not in (r["archive"].get("names") or []):
            return False, ("★ 矛盾没驱动出新动作（archive=%r failures=%r）"
                           % (r["archive"].get("names"), r["failures"]))
        if "conflict" not in (r["failures"] or {}):
            return False, "失败通道没记 conflict：%r" % (r["failures"],)
        return True, "矛盾 %d 处 → 演化出 %s" % (r["n_conflicts"],
                                                r["archive"].get("names"))

    # ── 14. ★ 动作空间是**可组合的一族**（不是 6 个查表模板）
    def c14():
        specs = W.all_action_specs()
        # ★★★ 动态期望（★ 不写死 36/57 ⇒ 动作空间可增长时断言自动跟着变）
        exp_n = len(W.REPAIR_TYPES) * len(W.SCOPES) * len(W.STRICTNESS)
        if len(specs) != exp_n:
            return False, "动作数 %d（应 %d = %d 修复型 × %d 范围 × %d 强度）" % (
                len(specs), exp_n, len(W.REPAIR_TYPES), len(W.SCOPES),
                len(W.STRICTNESS))
        if len(set(specs)) != len(specs):
            return False, "有重复动作"
        # 不同 spec ⇒ 不同提示词（否则"可组合"是假的）
        ps = {W.action_prompt(sp, "F") for sp in specs}
        if len(ps) != len(specs):
            return False, "不同动作生成了相同提示词（%d/%d）" % (len(ps), len(specs))
        # 每个 spec 都必须真的改变提示词的某一部分
        a = W.action_prompt(("none", "slot", 0), "F")
        b = W.action_prompt(("drop_conflicting", "cross_slot", 2), "F")
        if a == b:
            return False, "两端动作生成相同提示"
        return True, "%d 个可组合动作，提示词全不同" % len(specs)

    # ── 15. ★ 策略：可学、且查表策略是它的特例
    def c15():
        p0 = W.ActionPolicy()
        # 6 修复型 + 2 范围 + 3 强度 + 36 交互 + 3 仲裁 + 4 发散度 + 3 合并方式 = 57
        # ★ 动态期望：u + v + t + m(行×列) + 仲裁 + 发散度 + 合并方式
        exp_p = (len(p0.u) + len(p0.v) + len(p0.t)
                 + len(p0.m) * len(p0.m[0]) + len(p0.arb)
                 + len(p0.nf) + len(p0.mm))
        if p0.param_count() != exp_p:
            return False, "参数量 %d（应 %d = %d+%+d+%d+%d×%d+%d+%d+%d）" % (
                p0.param_count(), exp_p, len(p0.u), len(p0.v), len(p0.t),
                len(p0.m), len(p0.m[0]), len(p0.arb), len(p0.nf), len(p0.mm))
        probs = p0.probs("conflict")
        if abs(sum(probs) - 1.0) > 1e-6:
            return False, "概率没归一：%r" % sum(probs)
        if max(probs) - min(probs) > 1e-9:
            return False, "w=0 时应当均匀（未训练基线）"
        # 查表策略 ⇒ 每个失败类型都指向映射的修复型
        pl = W.ActionPolicy.from_lookup()
        import random as _r
        for fk, want in (("conflict", "drop_conflicting"),
                         ("empty", "ground_in_evidence"),
                         ("truncated", "compress")):
            sp = pl.choose(fk, _r.Random(0))
            if sp[0] != want:
                return False, "查表策略在 %s 上选了 %s（应 %s）" % (fk, sp[0], want)
        return True, "47 参数；w=0 均匀；查表策略命中映射"

    # ── 16. ★ policy 模式真能产出**组合动作**
    def c16():
        frames = W.select_frames(3, seed=5)
        llm = StubLLM(empty_slots={frames[0]})
        wf = W.CollapseFixWorkflow(llm, n_slots=3, seed=5, model="stub",
                                   judge_model="stub", max_rounds=2,
                                   action_mode="policy")
        r = wf.run("990 PRO 1TB 的哪些参数成立？")
        names = r["archive"].get("names") or []
        # 合法组合动作名 = "act_<rt>_<sc>_<st>"（因子名本身可能含下划线 ⇒ 不用 count 判断）
        legal = {"act_%s_%s_%d" % sp for sp in W.ACTION_SPECS}
        if not (set(names) & legal):
            return False, "policy 模式没产出组合动作名：%r（合法集合大小 %d）" % (names, len(legal))
        if r.get("action_mode") != "policy":
            return False, "读数里没记 action_mode"
        return True, "组合动作 %s（参数 %d 个）" % (names, r.get("policy_param_count"))

    # ── 17. ★ 锚外判定：机械、零 embedding，且**必须**区分锚内/锚外/写不出岔口
    def c17():
        import anchor_out as AO
        ct = [{"id": "C1", "text": "①成立：官方标称顺序读取 7450 MB/s"},
              {"id": "C2", "text": "②成立：官方标称随机读取 140 万 IOPS"}]
        cards = [
            {"claim": "①正确", "verdict": "支持", "load_bearing": True,
             "decision_changed": "确认①成立，顺序读取为 7450 MB/s"},
            {"claim": "运维监控", "verdict": "支持", "load_bearing": True,
             "decision_changed": "建议每 5 分钟采集 SMART，异常即摘盘"},
            {"claim": "免责", "verdict": "支持", "load_bearing": False,
             "decision_changed": None},
            {"claim": "说不清", "verdict": "支持", "load_bearing": True,
             "decision_changed": None},
        ]
        d = AO.decide_anchor_out(cards, ct)
        if d["n_anchored"] != 1 or d["n_anchor_out"] != 1 or d["n_unknown"] != 1:
            return False, "判定错：%r" % d
        if AO.decide_anchor_out(cards[:1], ct)["n_anchor_out"] != 0:
            return False, "锚内条目被误判成锚外"
        return True, "锚内1 锚外1 写不出岔口1；锚内不误判"

    # ── 18. ★ 等预算对照臂：调用数与 W 同量（否则"增益"可能只是"多花了钱"）
    def c18():
        import anchor_out as AO
        llm = StubLLM()
        task = {"ask": "990 PRO 1TB 的哪些参数成立？", "evidence": []}
        r = AO.best_of_n_direct(llm, task, "stub", n=3)
        n_gen = sum(1 for p in llm.calls if str(p).startswith("B0_multi"))
        n_ex = sum(1 for p in llm.calls if p == "W_extract")
        if n_gen != 3:
            return False, "生成调用 %d（应 3）" % n_gen
        if n_ex != 3:
            return False, "抽取调用 %d（应 3 = 每路一次）" % n_ex
        if not r["claims"]:
            return False, "没抽出断言"
        return True, "3 次生成 + 3 次抽取（与 W 的 6 次同量）"

    # ── 19. ★ 跨槽位冲突的**检测 + 仲裁三档**（架构侧，不是度量侧）
    def c19():
        claims = ["①正确：顺序读取 7450 MB/s", "②正确：保修 5 年",
                  "①错误：顺序读取不是 7450", "③正确：耐久 600 TBW"]
        ps = W.detect_opposite_pairs(claims)
        if len(ps) != 1:
            return False, "应检出 1 对冲突，实得 %d" % len(ps)
        if ps[0]["marks"] != ["①"]:
            return False, "标记应含 ①，实得 %r" % ps[0]["marks"]
        # ★ "none" = 冲突容忍 ⇒ **一条都不许丢**（不收窄搜索空间）
        kept, log = W.arbitrate(claims, "none")
        if len(kept) != len(claims):
            return False, "★ 'none' 丢了断言（%d→%d）⇒ 收窄了搜索空间" % (len(claims), len(kept))
        if log["n_pairs"] != 1:
            return False, "日志没记冲突对数"
        # ★ "drop_one" = 收窄 ⇒ 恰好丢一条，且丢的是被指定的那一侧
        kept2, _ = W.arbitrate(claims, "drop_one", drop_choice="keep_pos")
        if len(kept2) != len(claims) - 1:
            return False, "'drop_one' 应丢 1 条，实丢 %d" % (len(claims) - len(kept2))
        kept3, _ = W.arbitrate(claims, "drop_one", drop_choice="keep_neg")
        if kept2 == kept3:
            return False, "★ keep_pos 与 keep_neg 结果相同 ⇒ 仲裁没起作用"
        # 一致的内容不该误报
        if W.detect_opposite_pairs(["①正确：7450 MB/s", "②正确：保修 5 年"]):
            return False, "一致内容被误报成冲突"
        return True, "检出 1 对；none 容忍(丢0) drop_one 丢1 且两向不同"

    # ── 20. ★★ 架构自由度（发散程度 + 合并方式）**由策略决定**，且真的被用上
    def c20():
        import random as _r
        # ① 策略能采样出 (n_frames, merge_mode)
        pol = W.ActionPolicy()
        nf, mm = pol.choose_architecture("conflict", _r.Random(0))
        if nf not in W.ActionPolicy.NF_IDS or mm not in W.ActionPolicy.MM_IDS:
            return False, "采样出非法架构决策：(%r, %r)" % (nf, mm)
        # ② 推高某个发散度 ⇒ 采样应偏向它
        pol.nf[W.ActionPolicy.NF_IDS.index(2)] = 8.0
        picks = [pol.choose_architecture("conflict", _r.Random(i))[0] for i in range(20)]
        if picks.count(2) < 15:
            return False, "推高发散度=2 后，采样仍不集中：%r" % picks
        # ③ run() 里策略的选择**真的生效**（arch_pick 落进读数 + ops 里有 ARCH 标记）
        llm = StubLLM()
        wf = W.CollapseFixWorkflow(llm, n_slots=3, seed=5, model="stub",
                                   judge_model="stub", max_rounds=1,
                                   policy=pol, learn_architecture=True)
        r = wf.run("990 PRO 1TB 的哪些参数成立？")
        if not r.get("arch_pick"):
            return False, "读数里没有 arch_pick ⇒ 策略的选择没落地"
        if r.get("merge_mode") not in W.ActionPolicy.MM_IDS:
            return False, "merge_mode 非法：%r" % r.get("merge_mode")
        if not any(o.startswith("ARCH[") for o in r.get("ops") or []):
            return False, "ops 里没有 ARCH 标记：%r" % (r.get("ops"),)
        # ④ 三种合并方式都能跑
        for m in W.ActionPolicy.MM_IDS:
            mg = W.merge_claims(["①正确：7450 MB/s", "①错误：7450 MB/s", "②正确：保修5年"], m)
            if not mg.get("claims"):
                return False, "合并方式 %s 没产出断言" % m
        return True, ("策略选的架构生效：nf=%s mm=%s；三种合并都可用"
                      % (r.get("arch_pick"), r.get("merge_mode")))

    add("frames_seed_reproducible", c1)
    add("frames_vary_by_seed", c2)
    add("dedup_removes_redundant", c3)
    add("action_evolve_rejects_unknown_kind", c4)
    add("archive_keeps_best_per_cell", c5)
    add("medianity_metrics_behave", c6)
    add("workflow_evolves_action_on_failure", c7)
    add("no_failure_no_evolution", c8)
    add("slots_are_decoupled", c9)
    add("mechanical_aggregate_is_lossless", c10)
    add("layer2_layer3_separated", c11)
    add("conflict_detected_zero_judge_cost", c12)
    add("conflict_drives_evolution", c13)
    add("action_space_is_composable", c14)
    add("policy_is_learnable", c15)
    add("policy_mode_produces_composed_action", c16)
    add("anchor_out_decision_is_mechanical", c17)
    add("equal_budget_control_arm", c18)
    add("conflict_arbitration_modes", c19)
    add("architecture_freedom_is_learned", c20)
    return checks


# ══════════════════════════════════════════════════════════════════════
# 变异注入
# ══════════════════════════════════════════════════════════════════════
MUTATIONS = [
    ("选帧去掉 seed（永远同一组）", "workflow.py",
     "    rng = random.Random(seed)",
     "    rng = random.Random(0)"),

    ("dedup 变成空操作", "workflow.py",
     """    kept: List[str] = []
    for it in items:
        if not (it or "").strip():
            continue
        if any(is_redundant(it, k, **kw) for k in kept):
            continue
        kept.append(it.strip())
    return kept""",
     "    return [i.strip() for i in items if (i or '').strip()]"),

    ("未知失败类型也被提案（把未知当成 empty）", "workflow.py",
     """    if failure_kind not in FAILURE_KINDS:
        return None""",
     '''    if failure_kind not in FAILURE_KINDS:
        failure_kind = "empty"'''),

    ("去掉「没有失败就不演化」的短路", "workflow.py",
     """            if not new_actions:
                break                       # 没有失败 ⇒ 不演化（★ 不无节制扩动作空间）""",
     "            if not new_actions:\n                new_actions = {fid: 'base' for fid in frames}"),

    ("矛盾检测变成空操作", "workflow.py",
     "def detect_conflicts(claims: Sequence[str]) -> List[Dict[str, Any]]:",
     "def detect_conflicts(claims: Sequence[str]) -> List[Dict[str, Any]]:\n    return []\n    # ---"),

    ("矛盾不再优先于其它失败", "workflow.py",
     "        if has_conflict:\n            return \"conflict\"",
     "        if False:\n            return \"conflict\""),

    ("交互项被去掉（失败类型不再影响选择）", "workflow.py",
     """        if failure_kind and failure_kind in FAILURE_IDS:
            fi = FAILURE_IDS.index(failure_kind)
            s += self.m[fi][REPAIR_IDS.index(rt)]""",
     "        pass"),

    ("动作空间塌成 6 个（丢掉组合维度）", "workflow.py",
     """    for rt in REPAIR_TYPES:
        for sc in SCOPES:
            for st in (0, 1, 2):
                out.append((rt, sc, st))""",
     """    for rt in REPAIR_TYPES:
        out.append((rt, "slot", 0))"""),

    ("行为档案总是覆盖（不留最优）", "workflow.py",
     """        cell = self.cells.get(key)
        if cell is None or score > cell["score"]:""",
     """        cell = self.cells.get(key)
        if True:"""),
]


def apply_mutation(src, old, new):
    if old not in src:
        raise RuntimeError("变异锚点找不到（源码已变？）")
    return src.replace(old, new, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutate", action="store_true")
    args = ap.parse_args()

    print("=" * 74)
    print("治塌缩工作流（W）· 自检")
    print("=" * 74)

    if not args.mutate:
        checks = run_checks()
        npass = sum(1 for c in checks if c.ok)
        for c in checks:
            print("  %s %-42s %s" % ("✔" if c.ok else "✘", c.name, c.detail or ""))
            if c.error:
                print("      ↳ %s" % c.error)
        print("-" * 74)
        print("正常模式：%d/%d 通过" % (npass, len(checks)))
        return 0 if npass == len(checks) else 1

    # ★ 基线必须全过，否则"被抓住"可能只是抓住了预存在的失败
    baseline = run_checks()
    base_failed = [c.name for c in baseline if not c.ok]
    if base_failed:
        print("  ✘ ★★ **基线本身有失败** ⇒ 变异自检无意义（会假阳性）")
        for c in baseline:
            if not c.ok:
                print("      ↳ %s：%s %s" % (c.name, c.detail or "", c.error or ""))
        print("=" * 74)
        print("变异注入：**无效**（基线未通过）")
        print("=" * 74)
        return 1
    print("  ✔ 基线全过（%d/%d）⇒ 变异自检有效" % (len(baseline), len(baseline)))
    print("-" * 74)

    here = HERE
    with open(os.path.join(here, "workflow.py"), encoding="utf-8") as f:
        original = f.read()

    all_caught, caught_n = True, 0
    for label, fname, old, new in MUTATIONS:
        tmp = tempfile.mkdtemp(prefix="w_mut_")
        try:
            for fn in os.listdir(here):
                if fn.endswith(".py"):
                    shutil.copy2(os.path.join(here, fn), os.path.join(tmp, fn))
            with open(os.path.join(tmp, fname), "w", encoding="utf-8") as f:
                f.write(apply_mutation(original, old, new))
            for mod in list(sys.modules):
                if mod == "workflow":
                    del sys.modules[mod]
            sys.path.insert(0, tmp)
            saved = W
            try:
                globals()["W"] = importlib.import_module("workflow")
                checks = run_checks()
                failed = [c.name for c in checks if not c.ok]
            finally:
                globals()["W"] = saved
                sys.path.remove(tmp)
                if "workflow" in sys.modules:
                    del sys.modules["workflow"]
                sys.path.insert(0, here)
            if failed:
                caught_n += 1
                print("  ✔ 变异被抓住：%s" % label)
                print("      ↳ 失败检查：%s" % ", ".join(failed))
            else:
                all_caught = False
                print("  ✘ ★ 变异**未被抓住**：%s" % label)
        except Exception:
            all_caught = False
            print("  ✘ ★ 变异导致自检崩溃（等于没抓住）：%s" % label)
            traceback.print_exc()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    print("=" * 74)
    print("变异注入：%s（%d/%d 被抓住）"
          % ("全部被抓住" if all_caught else "★有未被抓住的", caught_n, len(MUTATIONS)))
    print("=" * 74)
    return 0 if all_caught else 1


if __name__ == "__main__":
    sys.exit(main())
