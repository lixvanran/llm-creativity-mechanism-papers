# -*- coding: utf-8 -*-
"""治塌缩工作流（W）· **真实跑批**（DEV 集上）

> 2026-10-22 ｜ 配套 `workflow.py` ｜ **这是第一次把 W 接到真模型上跑**

## 跑什么
两条臂，同题、同模型、同测量：

| 臂 | 是什么 | 作用 |
|---|---|---|
| `B0_direct` | **直调**：题面 + 输出规格，一次调用 | 参照基线（= "不知道该考虑哪些维度"的状态）|
| `W_collapse` | **治塌缩工作流**：认知帧解耦 → 去冗余 → **动作演化** → 汇总 → 机械装配 | 我们的架构 |

⇒ 读数：**承重维度数**（`load_bearing` 且 `supports_conclusions` 非空且去冗余后）
＋ **中庸度四指标**（交集率 / 边际利用率 / 中庸距离 / 覆盖饱和度）
＋ **动作演化读数**（动作档案从 0 长到几个、失败类型分布）
＋ **行为格数**（探索了几种东西）

## 成本
被测与测量**都用 MiniMax 订阅（$0）**。被测 `MiniMax-M3.1-Flash-Preview`。
⇒ ⚠️ 判官与被测**同厂商** ⇒ `judge_same_vendor=true` ⇒ 读数**只能用于内部对照**，
   **不能**作为对外结论（协议 §4.3 的跨厂商要求）。

## 纪律
* **失败不许静默变 0**：每臂的 `parsefail_rate`、`n_load_bearing`、调用数全部落盘。
* **不重跑到好看**：跑几次就是几次，invalid 也如实报。
* **密钥只从环境读**，不写进任何文件。
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
import shutil
import sys
import time

# ⚠️ 2026-10-22：**沙箱里 .pyc 的 mtime 失效判断不可靠**
#    （实测：源码已改、import 拿到的还是旧模块 ⇒ 跑旧代码却以为在跑新代码）
#    ⇒ **跑之前必须清缓存**。这直接关系到读数归因。
sys.dont_write_bytecode = True
_here = os.path.dirname(os.path.abspath(__file__))
shutil.rmtree(os.path.join(_here, '__pycache__'), ignore_errors=True)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# 复用既有的真实客户端与测量流水线（**不重写**）
BATCH_U1 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "judge")
sys.path.insert(0, BATCH_U1)

import u1_lib as U            # noqa: E402
import measure as M           # noqa: E402
import workflow as W          # noqa: E402
import anchor_out as AO       # noqa: E402
import premature_closure as PC  # noqa: E402

DEV = os.environ.get("DEV_DIR") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "devset")
OUT = os.path.join(HERE, "runs")


# ══════════════════════════════════════════════════════════════════════
# 工具
# ══════════════════════════════════════════════════════════════════════
def load_tasks(n=None, devset=None):
    """devset 可指定题集文件（默认 DEV/devset.json；对抗题集用 DEV-ADV-*.json）。"""
    path = devset or os.path.join(DEV, "devset.json")
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    tasks = d["tasks"] if isinstance(d, dict) and "tasks" in d else d
    return tasks[:n] if n else tasks


def ev_items(task):
    return [{"id": e["id"], "text": e["text"]} for e in task.get("evidence") or []]


def ct_text(task):
    """结论空间给判官的文本（**编号即结论编号**）。"""
    cs = task.get("conclusion_space") or []
    return "\n".join("%d. [%s] %s" % (i + 1, c.get("id", ""), c.get("text", ""))
                     for i, c in enumerate(cs))


def measure_one(llm, task, answer, answer_id, judge_model=None, anchor_out=True):
    """两份判官同跑一份答案：

    ① **普通判官**（拿 `C_t`）⇒ 承重维度数、矛盾、净增益
    ② **锚外判官**（**不给 `C_t`**）⇒ 它自己说"改变了哪个决策"
       ⇒ 再由我们比这个岔口在不在 `C_t` 里 ⇒ `VD_anchor_out`
    ★ 两者**共用同一批抽取出的断言** ⇒ 省一次抽取调用
    ⚠️ 锚外的解析失败率**单独计数**，不许混进主判据的读数。
    """
    # ★ 抽取的模型名必须**跟着判官走**（否则换厂商 ⇒ 400 ⇒ 静默空串 ⇒ 读数 0）
    claims = M.extract_claims(llm, answer, model=judge_model)
    res = M.measure_answer(llm, task["ask"], ev_items(task), ct_text(task),
                           answer, answer_id, claims=claims,
                           judge_model=judge_model)
    # ── 锚外：换一个**不知道 C_t** 的判官
    anchor = dict(n_anchor_out=0, n_anchored=0, n_unknown=0,
                   anchor_out_claims=[], anchored_claims=[],
                   parsefail_rate=None, n_cards=0)
    if anchor_out:
        try:
            aor = M.measure_anchor_out(llm, task["ask"], ev_items(task),
                                        answer, answer_id + "/ao", claims=claims,
                                        judge_model=judge_model)
            ao_cards = aor.get("cards") or []
            dec = AO.decide_anchor_out(ao_cards, task.get("conclusion_space") or [])
            dec["parsefail_rate"] = aor.get("parsefail_rate")
            dec["n_cards"] = len(ao_cards)
            anchor = dec
        except Exception as e:
            anchor["error"] = "%s: %s" % (type(e).__name__, e)

    cards = []
    for i, c in enumerate(res.get("cards_all") or []):
        v = c.get("verdict")
        st = {"支持": "supported", "矛盾": "contradicted",
              "未提及": "unmentioned", "非主张": "unverifiable"}.get(v, "unverifiable")
        cards.append(dict(
            card_id="%s#%d" % (answer_id, i),
            claim=c.get("claim"),
            verify_status=st,
            verdict=v,
            load_bearing=bool(c.get("load_bearing")),
            # ⚠️ int → 结论 id（`family_key` 要字符串，否则 join 报 TypeError）
            supports_conclusions=["C%d" % int(x) for x in (c.get("supports_conclusions") or [])],
            stage="final",
        ))
    return res, cards, anchor


def dims_from_cards(cards):
    """承重维度数 = 去冗余后的**不同结论族**数（与生产读数同口径：`family_key`）。"""
    fams = set()
    for c in cards:
        if c.get("load_bearing") and c.get("verify_status") == "supported" \
                and c.get("supports_conclusions"):
            fams.add("|".join(sorted(c["supports_conclusions"])))
    return fams


def claims_text(cards):
    return [c.get("claim") or "" for c in cards]


# ══════════════════════════════════════════════════════════════════════
# 两条臂
# ══════════════════════════════════════════════════════════════════════
def arm_direct(llm, task, model):
    """直调基线：一次调用。**没有帧、没有演化、没有汇总。**"""
    prompt = "问题：%s\n\n%s" % (task["ask"], W._OUT_SPEC)
    direct_stats = {"calls": []}
    print("      [B0] 生成…", flush=True)
    out, _bi = W._chat(llm, prompt, purpose="B0_direct", model=model, temp=0.7,
                       max_tokens=0, min_ok=20, stats=direct_stats)
    print("      [B0] 抽取…", flush=True)
    _cl = W._extract_claims(llm, out, model=model) if out else []
    print("      [B0] 抽到 %d 条" % len(_cl), flush=True)
    return dict(answer=out or "", claims=_cl,
                ops=["GEN[direct]"], frames=[], archive={}, failures={}, illum={},
                chat_stats=direct_stats)


def arm_frames_vote(llm, task, model, slots=3, seed=0, frame_seed=None):
    """★ 对照臂 `B0_frames_vote`：**每个认知帧各跑一遍独立答案，再投票**。

    ★ 为什么必须有（Self-Discover arXiv:2402.03620 逐字）：
      "superior performance against … CoT + Self-Consistency and **majority voting of
       every module** while requiring 10-40x fewer inference compute"
    ⇒ ⇒ 没有这个臂，"多帧 ⇒ 多维度"站不住。
    ⇒ ⇒ **用与 W 臂完全相同的帧**（同 seed ⇒ 同帧集合）⇒ 公平比较。
    """
    frames = W.select_frames(slots, seed=seed, frame_seed=frame_seed)
    print("      [B0fv] %d 帧各跑一遍 + plurality 投票：%s"
          % (len(frames), frames), flush=True)
    r = AO.frames_vote_baseline(llm, task, model, frames, seed=seed)
    print("      [B0fv] 抽到 %d 条" % len(r["claims"]), flush=True)
    return dict(answer=r["answer"], claims=r["claims"], ops=r["ops"],
                paths=r.get("paths"), frames=r.get("frames") or [],
                archive={}, failures={}, illum={}, rounds=[])


def arm_bestof(llm, task, model, n=3, seed=0):
    """★ 等预算对照臂：N 次独立直调 + 机械去冗余（调用数与 W 相同）。"""
    print("      [B0bestof%d] N 次独立直调…" % n, flush=True)
    r = AO.best_of_n_direct(llm, task, model, n=n, seed=seed)
    print("      [B0bestof%d] 抽到 %d 条" % (n, len(r["claims"])), flush=True)
    # ★ paths 必须透传（否则等预算臂的"路径间多样性"算不出来 ⇒ 与 W 不可比）
    return dict(answer=r["answer"], claims=r["claims"], ops=r["ops"],
                paths=r.get("paths"), frames=r.get("frames") or [],
                archive=r.get("archive") or {}, failures=r.get("failures") or {},
                illum=r.get("illum") or {}, rounds=r.get("rounds") or [])


def arm_workflow(llm, task, model, seed=0, n_slots=4, max_rounds=2, frame_seed=None,
                 evolve=True, layer="L3", action_mode="lookup", policy=None):
    wf = W.CollapseFixWorkflow(llm, n_slots=n_slots, seed=seed, frame_seed=frame_seed,
                                model=model, judge_model=model,
                                max_rounds=max_rounds, evolve=evolve, layer=layer,
                                action_mode=action_mode, policy=policy)
    print("      [W ] 跑工作流（%s）…" % layer, flush=True)
    r = wf.run(task["ask"])
    print("      [W ] 演化=%s 失败=%s" % (r["archive"].get("names"), r["failures"]), flush=True)
    return dict(answer=r["answer"], claims=r["claims"], ops=r["ops"],
                frames=r["frames"], archive=r["archive"], failures=r["failures"],
                illum=r["illum"], rounds=r["rounds"],
                paths=r.get("paths"),          # ★ 供"路径间多样性/思维跳跃"用
                layer=r.get("layer"), evolve=r.get("evolve"))


# ══════════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", type=int, default=3, help="跑前 N 道 DEV 题")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--slots", type=int, default=4)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--dry", action="store_true", help="只跑不落盘")
    ap.add_argument("--frame-seed", type=int, default=None,
                    help="★ 帧组合的独立 seed（与 run seed 解耦）；不传 ⇒ 与旧版逐字节一致")
    ap.add_argument("--resume", action="store_true",
                    help="★ 断点续跑：跳过 arms.jsonl 里已完成的 (题,臂,rep)")
    ap.add_argument("--action-mode", default="lookup", choices=["lookup", "policy"],
                    help="lookup=6 个手写模板（层2 的设计）；policy=36 个可组合动作+策略（层3）")
    ap.add_argument("--policy-file", default="",
                    help="学出来的策略 JSON（runs/policy_train/policy.json）")
    ap.add_argument("--arms", default="B0,W_design_L2,W_train_L3",
                    help="逗号分隔的臂名")
    ap.add_argument("--judge", default="minimax", choices=["minimax", "openrouter"],
                    help="判官厂商（★ 跨厂商交叉用 openrouter ⇒ judge_same_vendor=false）")
    ap.add_argument("--devset", default="",
                    help="题集 json（默认 DEV/devset.json；对抗题集用 DEV-ADV-*.json）")
    ap.add_argument("--judge-model", default="",
                    help="判官模型（openrouter 时默认 u1_lib.OR_MODEL）")
    args = ap.parse_args()

    tasks = load_tasks(args.tasks, args.devset)
    _adv = {t["task_id"]: t for t in tasks if t.get("trap_fingerprints")}
    if _adv:
        print("★ 诱导钻牛角尖题集：%d 题（带陷阱指纹，钻牛角尖率可机械判定）" % len(_adv))
    model = os.environ.get("MM_MODEL", "MiniMax-M3.1-Flash-Preview")
    # ★ 断点续跑：沙箱会杀长跑后台进程 ⇒ 每次重启都要能接着跑
    _done = set()
    _jl = os.path.join(args.out, "arms.jsonl")
    if args.resume and os.path.exists(_jl):
        for _ln in open(_jl, encoding="utf-8"):
            try:
                _d = json.loads(_ln)
                _done.add((_d.get("task_id"), _d.get("arm"), _d.get("rep")))
            except Exception:
                pass
        print("断点续跑：已完成 %d 个臂，跳过它们" % len(_done))
    _pol = None
    if args.policy_file and os.path.exists(args.policy_file):
        with open(args.policy_file, encoding="utf-8") as f:
            _pol = W.ActionPolicy.load(json.load(f))
        print("载入策略：%s（%d 参数）" % (args.policy_file, _pol.param_count()))
    elif args.action_mode == "policy":
        _pol = W.ActionPolicy()          # w=0 ⇒ 均匀 ⇒ **未训练基线**
        print("★ 未载入策略 ⇒ 用 w=0 均匀策略（未训练基线）")
    want_arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    # ★ 判官客户端：**生成侧始终 MiniMax**，只有**测量侧**可换厂商
    #   ⇒ 跨厂商交叉 = 同一批答案、**同一份判官提示词**、只换判官模型（ToT 的做法）
    #   ⇒ 生成侧不动 ⇒ 唯一变化就是"谁在判" ⇒ 读数差异就归因到判官
    if args.judge == "openrouter":
        jm = args.judge_model or U.OR_MODEL
        judge_llm = U.OpenRouterLLM()
        judge_same_vendor = False
        print("判官：%s（★ 跨厂商 ⇒ judge_same_vendor=false）" % jm)
    else:
        jm = args.judge_model or U.MM_MODEL
        judge_llm = U.MiniMaxLLM()
        judge_same_vendor = True
        print("判官：%s" % jm)
    llm = U.MiniMaxLLM()
    print("模型：%s ｜ 题数：%d ｜ rep：%d" % (model, len(tasks), args.reps))
    print("=" * 74)

    all_rows = []
    t0 = time.time()
    for ti, task in enumerate(tasks):
        for rep in range(1, args.reps + 1):
            row = dict(task_id=task["task_id"], rep=rep, arms={})
            _ARMS = {
                "B0_direct": lambda: arm_direct(llm, task, model),
                # ★ 等预算对照臂：N 次独立直调 + 机械去冗余 ⇒ **调用数与 W 相同**
                #   ⇒ 差集恰好是 {认知帧解耦 + 机械汇总 + 动作演化}
                #   ⇒ 同时实现 ToT 的「同预算 best-of-k」（轴＝调用数，不是节点数）
                "B0_bestof3": lambda: arm_bestof(llm, task, model, 3, rep),
                # ★ Self-Discover 的对照：每帧各跑一遍 + 投票（plurality）
                "B0_frames_vote": lambda: arm_frames_vote(llm, task, model,
                                                          args.slots, rep),
                # ★ 层2「用设计的手段」：架构先验设计好、**运行时不自修改**
                "W_design_L2": lambda: arm_workflow(
                    llm, task, model, seed=rep, n_slots=args.slots, frame_seed=args.frame_seed,
                    max_rounds=args.rounds, evolve=False, layer="L2",
                    action_mode=args.action_mode, policy=_pol),
                # ★ 层3「用训练/自迭代的手段」：从失败**构造新动作**、档案累积
                "W_train_L3": lambda: arm_workflow(
                    llm, task, model, seed=rep, n_slots=args.slots,
                    max_rounds=args.rounds, evolve=True, layer="L3",
                    action_mode=args.action_mode, policy=_pol),
            }
            for arm_name, fn in ((k, _ARMS[k]) for k in want_arms if k in _ARMS):
                if (task["task_id"], arm_name, rep) in _done:
                    print("  %-4s %-13s rep%s ★ 已完成，跳过"
                          % (task["task_id"], arm_name, rep), flush=True)
                    continue
                c0 = llm.n_api_calls
                try:
                    a = fn()
                    print("      [%s] 测量（判官）…" % arm_name, flush=True)
                    res, cards, anchor = measure_one(judge_llm, task, a["answer"],
                                                     "%s/%s/rep%d" % (arm_name, task["task_id"], rep),
                                                     judge_model=jm)
                    fams = dims_from_cards(cards)
                    row["arms"][arm_name] = dict(
                        answer=a["answer"], n_chars=len(a["answer"]),
                        claims=a["claims"],
                        n_cards=len(cards),
                        n_load_bearing=sum(1 for c in cards if c["load_bearing"]),
                        n_dims=len(fams),
                        dims=sorted(fams),
                        parsefail_rate=res.get("parsefail_rate"),
                        cards=cards,
                        anchor_out=anchor,
                        vd_anchor_out=(anchor or {}).get("n_anchor_out", 0),
                        ops=a.get("ops"), frames=a.get("frames"),
                        archive=a.get("archive"), failures=a.get("failures"),
                        illum=a.get("illum"),
                        chat_stats=a.get("chat_stats"),
                        rounds=a.get("rounds"),
                        paths=a.get("paths"),
                        # ★ 钻牛角尖判定（零判官、纯文本正则）
                        pc=(PC.premature_closure(_adv[task["task_id"]], a.get("answer") or "")
                            if task["task_id"] in _adv else None),
                        # ★ **代码版本标记**：⇒ 任何时候都能一眼看出"这批读数是哪份代码产的"
                        #   （我们已经栽过好几次"跑的是旧代码却以为在跑新代码"）
                        code_version="paths+arb+framesvote@2026-10-24",
                        calls=llm.n_api_calls - c0,
                    )
                except Exception as e:
                    row["arms"][arm_name] = dict(error="%s: %s" % (type(e).__name__, e))
                print("  %-4s %-11s dims=%-3s lb=%-3s calls=%-3s %s"
                      % (task["task_id"], arm_name,
                         row["arms"][arm_name].get("n_dims", "-"),
                         row["arms"][arm_name].get("n_load_bearing", "-"),
                         row["arms"][arm_name].get("calls", "-"),
                         row["arms"][arm_name].get("error", "")))
                # ★★ **逐臂增量落盘**（2026-10-22 实测教训：批次**静默**死掉时，
                #   只在末尾汇总的 JSON 会**全丢** ⇒ 日志里的数字救不回来）
                os.makedirs(args.out, exist_ok=True)
                with open(os.path.join(args.out, "arms.jsonl"), "a", encoding="utf-8") as _f:
                    _f.write(json.dumps(dict(
                        task_id=task["task_id"], rep=rep, arm=arm_name,
                        judge_model=jm, judge_same_vendor=judge_same_vendor,
                        **row["arms"][arm_name]), ensure_ascii=False) + "\n")
            all_rows.append(row)
            print("  " + "-" * 70)

    # ★ 从**增量落盘**重建 rows ⇒ 即使进程被杀，已完成的臂也**不会丢**
    _jl = os.path.join(args.out, "arms.jsonl")
    if os.path.exists(_jl):
        _rows = defaultdict(dict)
        for _ln in open(_jl, encoding="utf-8"):
            try:
                _d = json.loads(_ln)
            except Exception:
                continue
            _rows[(_d.get("task_id"), _d.get("rep"))][_d.get("arm")] = _d
        all_rows = [dict(task_id=k[0], rep=k[1], arms=v)
                    for k, v in _rows.items()]
        print("  ★ 从 arms.jsonl 重建 %d 行（%d 个臂）"
              % (len(all_rows), sum(len(v) for v in _rows.values())))

    # ── 汇总读数
    summary = dict(
        model=model, judge_model=jm, judge_same_vendor=judge_same_vendor,
        judge_vendor=args.judge,
        note=("判官与被测**同厂商**（MiniMax）⇒ 内部对照用；"
              "**不能**作为对外结论（协议 §4.3 要求跨厂商判官）"),
        n_tasks=len(tasks), reps=args.reps, slots=args.slots, rounds=args.rounds,
        secs=round(time.time() - t0, 1), total_calls=llm.n_api_calls,
        arms={}, rows=all_rows,
    )
    for arm in want_arms:
        dims, lbs, pf = [], [], []
        for row in all_rows:
            a = row["arms"].get(arm) or {}
            if "error" in a:
                continue
            dims.append(a.get("n_dims") or 0)
            lbs.append(a.get("n_load_bearing") or 0)
            pf.append(a.get("parsefail_rate") or 0.0)
        summary["arms"][arm] = dict(
            n=len(dims), dims=dims, mean_dims=(sum(dims) / len(dims)) if dims else 0,
            mean_load_bearing=(sum(lbs) / len(lbs)) if lbs else 0,
            mean_parsefail=(sum(pf) / len(pf)) if pf else 0,
        )

    # ── 中庸度（跨臂，按题）
    common_rates = []
    for row in all_rows:
        arms = row["arms"]
        # ★ 按**实际存在且无错误**的臂动态计算
        #   （原先硬编码 ("B0_direct","W_design_L2","W_train_L3") ⇒ 臂集合一变就 KeyError
        #     ⇒ **整批静默崩掉** ⇒ 这就是之前那几次"进程莫名消失"的真凶）
        _have = [a for a in arms
                 if isinstance(arms.get(a), dict) and "error" not in arms[a]
                 and arms[a].get("cards") is not None]
        if len(_have) < 2:
            continue
        common_rates.append(W.common_rate([
            [c.get("claim") or "" for c in (arms[a].get("cards") or [])]
            for a in _have
        ]))
    summary["medianity"] = dict(
        common_rate_across_arms=common_rates,
        mean_common_rate=(sum(common_rates) / len(common_rates)) if common_rates else 0.0,
    )

    # ── 动作演化读数
    evo = []
    for row in all_rows:
        a = row["arms"].get("W_train_L3") or row["arms"].get("W_design_L2") or {}
        if "error" in a:
            continue
        evo.append(dict(task_id=row["task_id"],
                        n_actions=(a.get("archive") or {}).get("n_actions", 0),
                        actions=(a.get("archive") or {}).get("names", []),
                        failures=a.get("failures") or {},
                        n_cells=(a.get("illum") or {}).get("n_cells", 0)))
    summary["evolution"] = evo

    print("=" * 74)
    for arm, s in summary["arms"].items():
        print("  %-11s n=%d  平均维度数=%.2f  平均承重卡=%.2f  平均解析失败率=%.3f"
              % (arm, s["n"], s["mean_dims"], s["mean_load_bearing"], s["mean_parsefail"]))
    print("  跨臂交集率均值=%.3f" % summary["medianity"]["mean_common_rate"])
    print("  动作演化：%s" % json.dumps(evo, ensure_ascii=False))
    print("  总调用 %d 次 ／ %.1f 秒" % (summary["total_calls"], summary["secs"]))
    print("=" * 74)

    if not args.dry:
        os.makedirs(args.out, exist_ok=True)
        path = os.path.join(args.out, "w_dev_run.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, sort_keys=True)
        print("  落盘：%s" % path)


if __name__ == "__main__":
    main()
