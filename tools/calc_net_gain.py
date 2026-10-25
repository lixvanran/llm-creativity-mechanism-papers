#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""净增益【双边】重算（零模型调用 · 事后重算）。

本脚本只做**机械集合运算**与**已有读数的代数推导**；不调用任何模型 API。

════════════════════════════════════════════════════════════════════════
一、它算什么（三个层）
════════════════════════════════════════════════════════════════════════
  L1 结论层（结论 id 级）  元素 = 单条结论编号 C1..Cn
                           来源 = 仓内既有流水线 `run_dev.py: dims_from_cards`
                                  （承重 ∧ 被依据支持 ∧ 有支撑结论 ⇒ 归族）
                           ★ 与 `judge/measure.py` 的 `conclusions_supported`
                             同集合语义（measure.py 额外多一道 `decision_changed`
                             过滤，仓内 readings 用的流水线没有这一道，见 --selftest）

  L2 结论族层              元素 = 结论族 "C1|C10"
                           ★ 这就是仓内 `dims` 字段本身（`dims_from_cards` 的输出）

  L3 断言层                元素 = 归一化后的**断言文本**（cards[].claim）
                           ★ 承重分层 = 高/低承重 × 新增/丢失（四格）
                           ★ 另给【改写感知】细分：把"新增/丢失"拆成
                             「真新增/真丢失」与「换句话说」两类

════════════════════════════════════════════════════════════════════════
二、配对与基线
════════════════════════════════════════════════════════════════════════
  基线 = **同题同重复**（同 task_id + 同 rep）的 `B0_direct`
  ★ 与 `judge/measure.py:494-508` 的既有双边实现同口径（"配对基线"：
    固定用 rep1 会把基线噪声记成被测臂的"丢失"）

  净增益 = |新增| − |丢失|，其中
    新增 = 该臂集合 \ 基线集合
    丢失 = 基线集合 \ 该臂集合
  ★ 恒等式自检：|W\B| − |B\W| ≡ |W| − |B|（脚本内断言，见 --selftest）

════════════════════════════════════════════════════════════════════════
三、失败路径不许静默归零
════════════════════════════════════════════════════════════════════════
  出现 `parsefail_rate is None` 且 `n_cards == 0` 的行 = **仪器层零**
  （答案根本没产出，不是"测出 0 收益"）⇒
    · 单独列在【失败路径表】
    · **从配对比较中剔除**（不计入净增益分母）
    · 绝不用 0 冒充读数

════════════════════════════════════════════════════════════════════════
四、复跑
════════════════════════════════════════════════════════════════════════
  python3 tools/calc_net_gain.py                 # 全量（仓内 20 条 + 944 批推导）
  python3 tools/calc_net_gain.py --selftest      # 只跑自检
  python3 tools/calc_net_gain.py --json out.json # 额外落一份机读结果
  ★ 路径全部相对脚本自身 ⇒ 放哪儿都能跑；不写被检树（sys.dont_write_bytecode）
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # ★ 不污染被检树

import argparse
import json
import os
import re
import unicodedata
from collections import Counter, OrderedDict, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

READINGS_REL = os.path.join(
    "来源与底稿", "第三组_治塌缩层3", "cmp8repo", "repro", "readings",
    "main_big_arms.jsonl",
)
REPO_SRC_REL = os.path.join(
    "来源与底稿", "第三组_治塌缩层3", "cmp8repo", "repro", "src",
)

BASELINE = "B0_direct"
WORKFLOW_ARMS = ("W_design_L2", "W_train_L3")
ALL_ARMS = ("B0_direct", "B0_bestof3", "B0_frames_vote", "W_design_L2", "W_train_L3")

# ══════════════════════════════════════════════════════════════════════
# 仓内既有原语的**逐字复刻**（保持口径与仓内一致，不自创指标）
#   · char_bigrams      ← cmp8repo/repro/src/metrics_priorart.py:53
#   · dims_from_cards   ← cmp8repo/repro/src/run_dev.py:136
#   · decision_fingerprint / _fingerprint_match ← cmp8repo/repro/src/anchor_out.py:48,67
# ══════════════════════════════════════════════════════════════════════
_PUNCT = re.compile(r"[\s，。；：、！？,.;:!?（）()【】《》“”‘’\-—/]")
# ★ 与仓内 `workflow.py:442-444` **逐字一致**（`anchor_out.py` 从 workflow 导入这两个）
_OPT_MARK = re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩]|\(\d{1,2}\)|（\d{1,2}）")
_NUM_UNIT = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|％|元|万|亿|毫秒|秒|分钟|小时|天|年|个月|次|人|台|条|个|米|公里|"
    r"kg|g|MB|GB|TB|W|V|A|MHz|GHz|℃|度)?")


def char_bigrams(text: str) -> frozenset:
    """中文版的「唯一词干集合」⇒ 字符 2-gram 集合（仓内 Self-Sim 口径）。"""
    t = _PUNCT.sub("", (text or ""))
    if len(t) < 2:
        return frozenset([t]) if t else frozenset()
    return frozenset(t[i:i + 2] for i in range(len(t) - 1))


def dims_from_cards(cards) -> list:
    """承重维度数 = 去冗余后的**不同结论族**数（仓内 `run_dev.py:136-143` 逐字复刻）。"""
    fams = set()
    for c in cards:
        if c.get("load_bearing") and c.get("verify_status") == "supported" \
                and c.get("supports_conclusions"):
            fams.add("|".join(sorted(c["supports_conclusions"])))
    return sorted(fams)


def decision_fingerprint(text: str):
    """把一段「决策描述」压成指纹：(选项标记, 数值集合, 字符 2-gram 集合)。"""
    if not text:
        return frozenset(), frozenset(), frozenset()
    opts = frozenset(m.group(0) for m in _OPT_MARK.finditer(text))
    nums = frozenset(m.group(0).strip() for m in _NUM_UNIT.finditer(text))
    t = _PUNCT.sub("", text or "")
    grams = frozenset(t[i:i + 2] for i in range(max(0, len(t) - 1)))
    return opts, nums, grams


def _fingerprint_match(a, b) -> bool:
    """两个指纹是否**指向同一个决策**（仓内 `anchor_out._fingerprint_match` 逐字复刻）。"""
    a_opts, a_nums, a_words = a
    b_opts, b_nums, b_words = b
    if a_opts and b_opts:
        if a_opts != b_opts:
            return False
        opt_ok = True
    else:
        opt_ok = False
    if a_nums and b_nums:
        if a_nums != b_nums:
            return False
        num_ok = True
    else:
        num_ok = False
    if a_words and b_words:
        inter = len(a_words & b_words)
        word_ok = inter / float(min(len(a_words), len(b_words))) >= 0.35
    else:
        word_ok = False
    return (opt_ok or num_ok) and word_ok


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 0.0
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


# ══════════════════════════════════════════════════════════════════════
# 断言文本的归一化规则（★ 归一化规则会影响绝对值 ⇒ 必须在报告里写明）
# ══════════════════════════════════════════════════════════════════════
_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
_WS = re.compile(r"\s+")
_NUM_COMMA = re.compile(r"(?<=\d),(?=\d{3})")


def normalize_claim(text: str) -> str:
    """**归一化规则 v1（默认）**

    1. NFKC 归一（全角→半角、兼容字符折叠）
    2. 去首尾空白、连续空白压成单空格
    3. **删掉汉字之间的空格**（"三星 990 PRO" → "三星990 PRO"）
    4. **删掉数字千分位逗号**（"7,450 MB/s" → "7450 MB/s"）★ 这是纯写法差异，
       不改变语义；不删的话 baseline 与工作流臂会因写法不同而互相误判成
       「新增/丢失」

    ⚠️ **不做**的事：不同义改写、繁简、术语同义替换**一律不合并** ⇒
       同义改写造成的虚假"新增/丢失"由【改写感知】细分单独量化，不混进主口径。
    """
    t = unicodedata.normalize("NFKC", text or "")
    t = _NUM_COMMA.sub("", t)
    t = _WS.sub(" ", t).strip()
    # 汉字之间的空格删掉（中文排版常在汉字与拉丁/数字之间插空格）
    t = re.sub(r"(?<=[㐀-䶿一-鿿豈-﫿])\s+(?=[㐀-䶿一-鿿豈-﫿])", "", t)
    t = re.sub(r"\s+(?=[㐀-䶿一-鿿豈-﫿])", "", t)
    t = re.sub(r"(?<=[㐀-䶿一-鿿豈-﫿])\s+", "", t)
    return t


def load_bearing_variants(text: str) -> str:
    """归一化规则 v2：再叠加【去标点 + 数字单位归一】，用于敏感性分析。"""
    t = normalize_claim(text)
    t = re.sub(r"(?<=\d)\s*(?=[%A-Za-z])", "", t)   # "7,450 MB/s" 的空格已被上一步处理
    t = re.sub(r"[\s，。；：、！？,.;:!?（）()【】《》“”‘’\-—/]", "", t)
    return t


# ══════════════════════════════════════════════════════════════════════
# 数据装载
# ══════════════════════════════════════════════════════════════════════
def load_readings(path: str):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def row_instrument_zero(r) -> bool:
    """仪器层零：卡片没出来 + 解析失败率是 None（不是 0）。"""
    pf = r.get("parsefail_rate")
    return (r.get("n_cards") or 0) == 0 and pf is None


def row_facts(r) -> dict:
    """逐行的绝对分母与事实计数。"""
    cards = r.get("cards") or []
    claims = r.get("claims") or []
    vs = Counter(c.get("verify_status") for c in cards)
    lb_rows = sum(1 for c in cards if c.get("load_bearing"))
    aset = assertion_set(r)
    return {
        "task_id": r.get("task_id"),
        "rep": r.get("rep"),
        "arm": r.get("arm"),
        "n_answer_chars": r.get("n_chars"),
        "n_candidate_claims": len(claims),          # 候选池（抽取出的原始条目）
        "n_card_rows": len(cards),                   # 卡片行数（含跨帧重复）
        "n_assertions_dedup": len(aset),            # 归一化去重后的断言数
        "n_assertions_dedup_lb": sum(1 for v in aset.values() if v["lb"]),
        "n_cards_field": r.get("n_cards"),
        "n_load_bearing_rows": lb_rows,
        "n_load_bearing_field": r.get("n_load_bearing"),
        "n_supported": vs.get("supported", 0),
        "n_contradicted": vs.get("contradicted", 0),
        "n_unmentioned": vs.get("unmentioned", 0),
        "n_nonclaim": vs.get("unverifiable", 0),
        "n_dims": r.get("n_dims"),
        "n_dims_recomputed": len(dims_from_cards(cards)),
        "parsefail_rate": r.get("parsefail_rate"),
        "parsefail_is_none": r.get("parsefail_rate") is None,
        "calls": r.get("calls"),
        "n_frames": len(r.get("frames") or []),
        "instrument_zero": row_instrument_zero(r),
    }


def assertion_set(r, normalizer=normalize_claim):
    """断言层元素集：归一化后的**去重**断言文本。

    ★ 去重规则：同一臂内 **归一化后完全相同**的断言文本算同一条
      （跨帧重复：工作流臂 3 帧 × 4 卡片 ⇒ 12 行里只有 8 条不同断言）
    ★ 承重聚合：同一断言的多个卡片行可能给出不同的 load_bearing
      ⇒ 主口径取 **OR**（任一行承重 ⇒ 该断言承重），另给 AND 作敏感性
    """
    agg = OrderedDict()   # norm_text -> dict
    for c in (r.get("cards") or []):
        txt = normalizer(c.get("claim") or "")
        if not txt:
            continue
        d = agg.setdefault(txt, {"text": txt, "lb": False, "rows": 0,
                                  "supported": False, "contradicted": False})
        d["rows"] += 1
        d["lb"] = d["lb"] or bool(c.get("load_bearing"))
        d["supported"] = d["supported"] or (c.get("verify_status") == "supported")
        d["contradicted"] = d["contradicted"] or (c.get("verify_status") == "contradicted")
    return agg


def conclusion_id_set_raw(r) -> set:
    """★ **口径 A（预注册算法，逐字照抄 ②A 稿 §5.2.4 ③）**：

        新增(臂, task, rep) = ⋃(该臂 cards[].supports_conclusions)
                              \\ ⋃(基线臂 cards[].supports_conclusions)
        丢失(臂, task, rep) = ⋃(基线臂 cards[].supports_conclusions)
                              \\ ⋃(该臂 cards[].supports_conclusions)
        净增益 = |新增| − |丢失|

    ★ **不做任何过滤**（不筛 load_bearing、不筛 verify_status）⇒ 这是
      「照抄现成实现，不要另发明」的原文口径 ⇒ **本口径为主口径**。

    ⚠️ 注意：`judge/measure.py:447` 的 `conclusions_supported` **多两道过滤**
      （`is_claim` ∧ `decision_changed`）⇒ 它与本函数**不是同一个集合**；
      本报告把两个变体都算出来（见 L0 / L1），不混用。
    """
    out = set()
    for c in (r.get("cards") or []):
        for cid in (c.get("supports_conclusions") or []):
            cid = str(cid).strip()
            if cid:
                out.add(cid)
    return out


def conclusion_id_set(r) -> set:
    """口径 A′：从 `dims`（= `run_dev.py: dims_from_cards` 的输出，已滤
    load_bearing ∧ verify_status=supported）拆开求并
    ⇒ 与 `judge/measure.py` 的 `conclusions_supported` 同集合语义
    （measure.py 额外多一道 `decision_changed` 过滤，仓内 readings 的流水线没有）。"""
    out = set()
    for fam in (r.get("dims") or []):
        for cid in str(fam).split("|"):
            if cid.strip():
                out.add(cid.strip())
    return out


def family_set(r) -> set:
    """L2：结论族集合（= `dims` 本身）。"""
    return set(r.get("dims") or [])


def setdiff_report(w_set, b_set, lb_of=None, normalizer=normalize_claim):
    """双边差集 + 承重分层 + 改写感知细分。

    ★ 承重分层用**两张表**（这一点极易写错）：
        · 新增项的承重标记取**该臂（工作流臂）**的卡片
        · 丢失项的承重标记取**基线臂**的卡片
      ⇒ 丢失项在基线里可能是承重的 ⇒ 丢失项若拿工作流臂的表去查，
        必然全部落进"低承重丢失"（**静默失真**）⇒ 脚本内两种口径都算，
        并在结果里分别给出。

    lb_of: {"w": {text->bool}, "b": {text->bool}} 或 None（仅结论层用不到）
    """
    added = [x for x in w_set if x not in b_set]
    lost = [x for x in b_set if x not in w_set]
    common = [x for x in w_set if x in b_set]
    out = {
        "n_added": len(added),
        "n_lost": len(lost),
        "n_common": len(common),
        "n_workflow": len(w_set),
        "n_baseline": len(b_set),
        "net_gain": len(added) - len(lost),
        "identity_holds": (len(added) - len(lost)) == (len(w_set) - len(b_set)),
        "added": added,
        "lost": lost,
    }
    if lb_of is not None:
        lb_w = lb_of.get("w") or {}
        lb_b = lb_of.get("b") or {}
        out["added_lb"] = sum(1 for x in added if lb_w.get(x))
        out["added_nonlb"] = sum(1 for x in added if not lb_w.get(x))
        out["lost_lb"] = sum(1 for x in lost if lb_b.get(x))
        out["lost_nonlb"] = sum(1 for x in lost if not lb_b.get(x))
    # 改写感知：逐条对另一侧求"是否同一件事"（仓内指纹判定 + 2-gram Jaccard）
    for key, mine, other in (("added", added, b_set), ("lost", lost, w_set)):
        same_decision, high_overlap = [], []
        for x in mine:
            fx = decision_fingerprint(x)
            best_fp = any(_fingerprint_match(fx, decision_fingerprint(y)) for y in other)
            gx = char_bigrams(x)
            best_j = max([jaccard(gx, char_bigrams(y)) for y in other], default=0.0)
            if best_fp:
                same_decision.append(x)
            elif best_j >= 0.35:
                high_overlap.append(x)
        out[key + "_paraphrase_same_decision"] = len(same_decision)
        out[key + "_paraphrase_high_overlap"] = len(high_overlap)
        out[key + "_truly_new_or_lost"] = len(mine) - len(same_decision) - len(high_overlap)
    return out


# ══════════════════════════════════════════════════════════════════════
# 任务 1：仓内 20 条
# ══════════════════════════════════════════════════════════════════════
def run_task1(path: str) -> dict:
    rows = load_readings(path)
    idx = {(r["task_id"], r["rep"], r["arm"]): r for r in rows}
    tasks = sorted({r["task_id"] for r in rows})
    reps = sorted({r["rep"] for r in rows})

    facts = {("%s#r%s" % (r["task_id"], r["rep"]), r["arm"]): row_facts(r) for r in rows}
    failures = []
    for k, f in facts.items():
        if f["instrument_zero"]:
            failures.append(f)

    results = {"n_rows": len(rows), "tasks": tasks, "reps": reps,
               "arms": sorted({r["arm"] for r in rows}),
               "facts": facts, "failures": failures, "pairs": []}

    # ── 逐 (题, rep) 配对：工作流臂 vs 同 rep 的 B0_direct ──────────────
    for t in tasks:
        for rep in reps:
            b = idx.get((t, rep, BASELINE))
            if b is None:
                continue
            for arm in ALL_ARMS:
                if arm == BASELINE:
                    continue
                w = idx.get((t, rep, arm))
                if w is None:
                    continue
                if row_instrument_zero(w) or row_instrument_zero(b):
                    results["pairs"].append({
                        "task_id": t, "rep": rep, "arm": arm,
                        "status": "SKIPPED_INSTRUMENT_ZERO",
                        "reason": "该臂/基线在本题本 rep 仪器层零（答案未产出）⇒ "
                                  "从配对比较剔除，不以 0 冒充读数",
                    })
                    continue

                # 口径 A（预注册算法 §5.2.4 ③，逐字照抄）：⋃ cards[].supports_conclusions
                l0 = setdiff_report(conclusion_id_set_raw(w), conclusion_id_set_raw(b))
                # 口径 A′（dims 过滤版 = measure.py 语义）
                l1 = setdiff_report(conclusion_id_set(w), conclusion_id_set(b))
                # L2 结论族层
                l2 = setdiff_report(family_set(w), family_set(b))
                # 口径 B（断言层，含承重分层：新增取工作流臂、丢失取基线臂）
                wa = assertion_set(w)
                ba = assertion_set(b)
                lb_w = {k: v["lb"] for k, v in wa.items()}
                lb_b = {k: v["lb"] for k, v in ba.items()}
                l3 = setdiff_report(set(wa), set(ba), lb_of={"w": lb_w, "b": lb_b})
                # L3 承重聚合敏感性：AND 口径（同一断言的所有卡片行都承重才算承重）
                wa_and = {k: all_rows_lb(w, k) for k in wa}
                ba_and = {k: all_rows_lb(b, k) for k in ba}
                l3_and = setdiff_report(set(wa), set(ba),
                                        lb_of={"w": wa_and, "b": ba_and})
                # L3 归一化敏感性：v2（去标点）
                wa2 = assertion_set(w, normalizer=load_bearing_variants)
                ba2 = assertion_set(b, normalizer=load_bearing_variants)
                l3_v2 = setdiff_report(set(wa2), set(ba2))

                results["pairs"].append({
                    "task_id": t, "rep": rep, "arm": arm,
                    "status": "OK",
                    "L0_conclusion_id_raw": l0,
                    "L1_conclusion_id": l1,
                    "L2_conclusion_family": l2,
                    "L3_assertion": l3,
                    "L3_assertion_lb_AND": l3_and,
                    "L3_assertion_norm_v2": l3_v2,
                    "denominators": {
                        "arm_card_rows": len(w.get("cards") or []),
                        "arm_assertions_dedup": len(wa),
                        "arm_lb_rows": facts[("%s#r%s" % (t, rep), arm)]["n_load_bearing_rows"],
                        "arm_candidate_claims": facts[("%s#r%s" % (t, rep), arm)]["n_candidate_claims"],
                        "base_card_rows": len(b.get("cards") or []),
                        "base_assertions_dedup": len(ba),
                        "base_lb_rows": facts[("%s#r%s" % (t, rep), BASELINE)]["n_load_bearing_rows"],
                        "base_candidate_claims": facts[("%s#r%s" % (t, rep), BASELINE)]["n_candidate_claims"],
                    },
                })

    # ── 汇总（按臂）─────────────────────────────────────────────────
    agg = defaultdict(lambda: {
        "n_pairs": 0, "n_skipped": 0,
        "L0_net": 0, "L0_added": 0, "L0_lost": 0,
        "L0_per_pair": [],
        "L1_net": 0, "L1_added": 0, "L1_lost": 0,
        "L1_per_pair": [],
        "L2_net": 0, "L2_added": 0, "L2_lost": 0,
        "L3_net": 0, "L3_added": 0, "L3_lost": 0,
        "L3_added_lb": 0, "L3_lost_lb": 0,
        "L3_added_nonlb": 0, "L3_lost_nonlb": 0,
        "L3_added_true": 0, "L3_lost_true": 0,
        "L3_added_para": 0, "L3_lost_para": 0,
        "L3_net_AND": 0, "L3_net_v2": 0,
        # ★ 明确命名的承重子层键（★ 别抽 L3_net_AND，★ 那个是断言层总净）
        "L3_lb_OR_added": 0, "L3_lb_OR_lost": 0,
        "L3_lb_AND_added": 0, "L3_lb_AND_lost": 0,
    })
    for p in results["pairs"]:
        a = agg[p["arm"]]
        if p["status"] != "OK":
            a["n_skipped"] += 1
            continue
        a["n_pairs"] += 1
        for pre in ("L0", "L1", "L2", "L3"):
            d = p[pre + ("_conclusion_id_raw" if pre == "L0" else
                         "_conclusion_id" if pre == "L1" else
                         "_conclusion_family" if pre == "L2" else "_assertion")]
            a[pre + "_net"] += d["net_gain"]
            a[pre + "_added"] += d["n_added"]
            a[pre + "_lost"] += d["n_lost"]
            if pre in ("L0", "L1"):
                a[pre + "_per_pair"].append(d["net_gain"])
        d3 = p["L3_assertion"]
        a["L3_added_lb"] += d3["added_lb"]
        a["L3_lost_lb"] += d3["lost_lb"]
        a["L3_added_nonlb"] += d3["added_nonlb"]
        a["L3_lost_nonlb"] += d3["lost_nonlb"]
        a["L3_added_para"] += d3["added_paraphrase_same_decision"]
        a["L3_lost_para"] += d3["lost_paraphrase_same_decision"]
        a["L3_added_true"] += d3["added_truly_new_or_lost"]
        a["L3_lost_true"] += d3["lost_truly_new_or_lost"]
        # ★★★ 【明确命名的承重子层键】（★ 2026-10-25 · 审稿人指出"抽键陷阱"）
        #   ★★★ 陷阱：`L3_net_AND` 这个键名有误导性 ⇒ ★ 它装的是【断言层的总净增益】
        #     （★ 在 AND 口径下分类 added/lost），★ **不是**【承重子层的净】
        #     ⇒ ★ 第三方直抽它 ⇒ 会得出"承重子层 = +14 ⇒ 为正 ⇒ ②篇结论不成立"的【完全错误】结论
        #   ⇒ ★ 落法：★ 承重两个口径各给一对【明确命名】的 added/lost/net 键
        a["L3_net_AND"] += p["L3_assertion_lb_AND"]["net_gain"]
        a["L3_net_v2"] += p["L3_assertion_norm_v2"]["net_gain"]
        # ★ 承重 OR（主口径）：高承重新增 − 高承重丢失
        a["L3_lb_OR_added"] += d3["added_lb"]
        a["L3_lb_OR_lost"] += d3["lost_lb"]
        # ★ 承重 AND（敏感性变体）
        a["L3_lb_AND_added"] += p["L3_assertion_lb_AND"]["added_lb"]
        a["L3_lb_AND_lost"] += p["L3_assertion_lb_AND"]["lost_lb"]
    results["aggregate"] = {k: dict(v) for k, v in agg.items()}

    # ── 工作流臂两两直接对比（W_design_L2 vs W_train_L3，同题同 rep）──
    direct_cmp = []
    for t in tasks:
        for rep in reps:
            a = idx.get((t, rep, "W_design_L2"))
            b = idx.get((t, rep, "W_train_L3"))
            if a is None or b is None or row_instrument_zero(a) or row_instrument_zero(b):
                continue
            aa, bb = assertion_set(a), assertion_set(b)
            d3 = setdiff_report(set(aa), set(bb),
                                lb_of={"w": {k: v["lb"] for k, v in aa.items()},
                                       "b": {k: v["lb"] for k, v in bb.items()}})
            direct_cmp.append({
                "task_id": t, "rep": rep,
                "L0": setdiff_report(conclusion_id_set_raw(a), conclusion_id_set_raw(b)),
                "L1": setdiff_report(conclusion_id_set(a), conclusion_id_set(b)),
                "L2": setdiff_report(family_set(a), family_set(b)),
                "L3_assertion": d3,
            })
    results["W_design_L2_vs_W_train_L3"] = direct_cmp
    results["null_calibration"] = run_null_calibration(idx, tasks, reps)
    return results


def run_null_calibration(idx, tasks, reps) -> dict:
    """★ **零假设标定（噪声地板）**：同臂、同题、**rep1 vs rep2** 的净增益。

    为什么这是正确的零分布：**同臂的两次重复之间没有任何架构差异**，
    只差采样 ⇒ 「把 rep2 当成被测臂、把 rep1 当成基线」算出来的净增益
    **就是这个统计量在纯噪声下的取值** ⇒ ⇒ 用来判断工作流臂的净增益
    是否落进噪声带（②A 稿 §5.2.3 的「不可分辨」档需要它，不是靠断言）。

    ★ 零 API（纯集合运算）｜ ★ 只用仓内已有产出。
    """
    samples = {"A": [], "B": []}
    detail = []
    for t in tasks:
        for arm in ALL_ARMS:
            r1 = idx.get((t, 1, arm))
            r2 = idx.get((t, 2, arm))
            if r1 is None or r2 is None:
                continue
            if row_instrument_zero(r1) or row_instrument_zero(r2):
                continue
            a_net = setdiff_report(conclusion_id_set_raw(r1),
                                   conclusion_id_set_raw(r2))["net_gain"]
            a2 = assertion_set(r1)
            a3 = assertion_set(r2)
            b_net = setdiff_report(set(a2), set(a3))["net_gain"]
            samples["A"].append(a_net)
            samples["B"].append(b_net)
            detail.append({"task_id": t, "arm": arm, "A_net_rep1_vs_rep2": a_net,
                           "B_net_rep1_vs_rep2": b_net})
    out = {"samples": detail, "n": len(samples["A"])}
    for k in ("A", "B"):
        v = samples[k]
        if v:
            out[k + "_values"] = v
            out[k + "_abs_max"] = max(abs(x) for x in v)
            out[k + "_abs_mean"] = sum(abs(x) for x in v) / float(len(v))
            out[k + "_sign_consistent"] = (all(x > 0 for x in v) or
                                           all(x < 0 for x in v))
    return out


def all_rows_lb(r, norm_text) -> bool:
    """AND 口径：该断言的所有卡片行都承重才算承重。"""
    rows = [c for c in (r.get("cards") or [])
            if normalize_claim(c.get("claim") or "") == norm_text]
    return bool(rows) and all(bool(c.get("load_bearing")) for c in rows)


# ══════════════════════════════════════════════════════════════════════
# 任务 2：944 批（R2）双边重算
#   ★ 原始产出（claims/verdicts）**未能捞到**（见报告"未捞到"节）
#   ⇒ 这里做的是【仓内一手文档读数的代数推导】，不是重新抽断言
# ══════════════════════════════════════════════════════════════════════
# 一手读数（全部来自仓内文档，逐条在报告里给出出处）：
#   来源 A：来源与底稿/第二组_源文件/REPORT-DRILL-2026-10-18.md §4.1
#           （同一批亦见 docs/CORRECTION-2026-10-18-breadth.md 与 ②A 稿 §5 R2）
#   来源 B：docs/CORRECTION-2026-10-18-breadth.md §三轴实测（宽度/支持率/矛盾率）
#   来源 C：docs/CORRECTION-2026-10-18-breadth.md §「多报出来」
DRILL_944 = {
    # 臂: (断言数, 支持, 矛盾, 非主张, 总分, 每份均值, 矛盾率, 支持率)
    "direct":      dict(n_assert=324, sup=117, con=1, non=39, score=95.5, per=2.65,
                        con_rate=0.4, sup_rate=41.1),
    "dual_select": dict(n_assert=302, sup=109, con=4, non=51, score=75.5, per=2.10,
                        con_rate=1.6, sup_rate=43.4),
    "dual_fuse":   dict(n_assert=318, sup=90, con=12, non=34, score=49.0, per=1.36,
                        con_rate=4.2, sup_rate=31.7),
}
# 去重并集/题（来源 B）：宽度 = 每题每臂的【去重并集断言数】均值
BREADTH = {"direct": 5.2, "dual_fuse": 5.8, "dual_select": 5.4}
# 来源 C：相对直调「多报出来」条数（跨 18 题）及其去向
MULTI_REPORTED = {"dual_select": dict(total=9, sup=0, con=0, unmentioned=5, nonclaim=4)}
N_TASKS = 18
N_PER_ARM = 36          # 份/臂（18 题 × 2 重复）
BRANCH_NOMINAL = 5      # 名义支数
BRANCH_ACTUAL = 4       # 实测支数（第 5 支命中下架型号 ⇒ 空串 ⇒ 被 if o 过滤）


def run_task2() -> dict:
    out = {"provenance": [], "identity": {}, "arms": {}, "rounding_band": {}}

    # ── 恒等式：|W\B| − |B\W| ≡ |W| − |B| ──────────────────────────
    ident_ok = True
    for _ in range(200):
        b = set(range(int(_ % 7)))
        w = set(range(int((_ * 3) % 9)))
        if (len(w - b) - len(b - w)) != (len(w) - len(b)):
            ident_ok = False
            break
    out["identity"] = {"statement": "|W\\B| - |B\\W| == |W| - |B|",
                       "random_check_passed": ident_ok}

    # ── 总分核对：总分 = 支持 − 2·矛盾 − 0.5·非主张（巡练打分函数）──
    for arm, d in DRILL_944.items():
        s = d["sup"] - 2 * d["con"] - 0.5 * d["non"]
        d["score_recomputed"] = s
        d["score_formula_matches"] = abs(s - d["score"]) < 1e-9
        d["legal_denominator"] = d["n_assert"] - d["non"]          # 合法主张数
        d["con_rate_recomputed"] = 100.0 * d["con"] / d["legal_denominator"]
        d["sup_rate_recomputed"] = 100.0 * d["sup"] / d["legal_denominator"]
        d["per_answer_check"] = d["score"] / N_PER_ARM
        d["assert_per_answer"] = d["n_assert"] / N_PER_ARM
        # 去重并集总量（|U|）：宽度/题 × 题数（= 18 题的逐题并集之和）
        d["width_per_task"] = BREADTH[arm]
        d["union_total"] = BREADTH[arm] * N_TASKS
        out["arms"][arm] = d

    base = out["arms"]["direct"]["union_total"]
    out["net_gain"] = {}
    for arm in ("dual_select", "dual_fuse"):
        w = out["arms"][arm]["union_total"]
        # 舍入带：宽度保留 1 位小数 ⇒ |U| 的不确定度 = 0.05 × 18 = 0.9
        band = 0.05 * N_TASKS
        net = w - base
        out["net_gain"][arm] = {
            "n_baseline_union": base,
            "n_workflow_union": w,
            "added": None,      # 见下：若来源 C 有"多报"数则为下界
            "lost": None,
            "net_gain": net,
            "rounding_band": band,
            "net_gain_min": net - 2 * band,
            "net_gain_max": net + 2 * band,
            "sign_robust_to_rounding": (net - 2 * band) > 0 or (net + 2 * band) < 0,
        }

    # ── 用来源 C（多报 9 条）做【第二条独立通路】交叉验证 ──────────
    for arm, mr in MULTI_REPORTED.items():
        ng = out["net_gain"][arm]
        # |W| = |W∩B| + |W\B|  ⇒  |W\B| ≥ 多报数（多报还额外剔了"换句话说"）
        # |B\W| = |W\B| − 净增益  ⇒  丢失 ≥ 多报数 − 净增益
        ng["added_lower_bound_published_multireported"] = mr["total"]
        ng["lost_lower_bound"] = mr["total"] - ng["net_gain"]
        ng["cross_check"] = {
            "published_multireported": mr["total"],
            "implied_intersection": ng["n_workflow_union"] - mr["total"],
            "implied_baseline_union": ng["n_baseline_union"],
            "note": "多报数是【再滤过同义改写后】的下界 ⇒ 真实新增 ≥ 该数、"
                    "真实丢失 ≥ 该数 − 净增益；净增益本身不受此滤器影响",
        }

    out["provenance"] = [
        "A｜来源与底稿/第二组_源文件/REPORT-DRILL-2026-10-18.md §4.1（944 断言全量重判表）",
        "B｜docs/CORRECTION-2026-10-18-breadth.md §三轴实测（宽度=去重并集/题、支持率、矛盾率）",
        "C｜docs/CORRECTION-2026-10-18-breadth.md §「多报出来」（dual_select 多报 9 条）",
        "D｜②A 篇 §5 R2 / §7 局限 11 / §8.1 第 5 项与第 7 项 / 附录 D.1（口径与待办）",
        "E｜cmp8/net_gain.py（既有双边实现：基线=同题同重复直调、元素=依据包原子事实、"
        "四档匹配器按「跨题误匹配≈0 且召回最高」选档）",
    ]
    out["raw_recovered"] = False
    out["raw_search_log"] = [
        "仓内 /workspace/work/llm-creativity-mechanism-papers：来源与底稿/第二组_源文件/runs/ "
        "只有 n-baseline-2026-10-24 与 nested-calibration-2026-10-24 ⇒ 无 944 批原始产出",
        "drive（source=AgentDeliverable，按 session_id 过滤第二组 455174667473626）："
        "取到 第二组交付包_2026-10-24.zip 与 _2026-10-26.zip（9.3MB 各）⇒ "
        "内含 cmp8/net_gain.py、cmp8/analysis_net_gain.md、REPORT-DRILL-2026-10-18.md、"
        "docs/CORRECTION-2026-10-18-breadth.md、data/historical-runs/** ⇒ "
        "**但不含 runs/drill/ 与 runs/train2/**（claims.json / texts.json / verdicts_v4_full.json）",
        "GitHub api lixvanran/agent-creativity-mechanism-study @ cmp8-handover-2026-10-20 "
        "(sha 6307ca8daba13b15d80c35279c4542ec48e517f4，1532 条 tree)："
        "runs/ 已被 gitignore ⇒ 无 drill/train2 产物",
        "结论：944 批的【原始断言文本与逐条判决】在本环境不可达 ⇒ "
        "本节数字是【仓内一手文档读数的代数推导】，不是重新抽断言的结果",
    ]
    out["branch_basis"] = {
        "nominal_branches": BRANCH_NOMINAL,
        "actual_branches": BRANCH_ACTUAL,
        "note": "净增益的三个分母（|U|、题数 18、份/臂 36）**不含支数** ⇒ "
                "支数漂移不进入净增益的分母；dual 臂的产出本身就是 4 支产物 ⇒ "
                "本节读数已按【4 支产出】计算。★ 4 支口径重算（②A §8.1 第 7 项）"
                "是另一项独立待办：它要重跑/重算的是 R2/R3/R4 的绝对读数与分母，"
                "方向未知（②A §7 局限 25），本节读数继承该限定",
    }
    return out


# ══════════════════════════════════════════════════════════════════════
# 自检（--selftest）：把本脚本的口径钉在仓内既有实现上
# ══════════════════════════════════════════════════════════════════════
def run_selftest(path: str) -> dict:
    res = {}
    rows = load_readings(path)

    # ① 结论族重算 == 仓内 readings 的 dims 字段（20/20）
    ok, detail = 0, []
    for r in rows:
        rec = dims_from_cards(r.get("cards") or [])
        if rec == sorted(r.get("dims") or []):
            ok += 1
        else:
            detail.append({"key": "%s#r%s#%s" % (r["task_id"], r["rep"], r["arm"]),
                           "recomputed": rec, "in_file": sorted(r.get("dims") or [])})
    res["dims_from_cards_reproduces_readings_dims"] = {
        "n_rows": len(rows), "n_match": ok, "mismatches": detail}

    # ② 恒等式
    ident_ok = True
    for i in range(500):
        b = set(range(i % 11))
        w = set(range((i * 7) % 13))
        if (len(w - b) - len(b - w)) != (len(w) - len(b)):
            ident_ok = False
            break
    res["setdiff_identity"] = {"passed": ident_ok}

    # ③ 归一化规则的自洽：v1 归一化后，同一臂内的跨帧重复应被合并
    rows_by = defaultdict(list)
    for r in rows:
        rows_by[(r["task_id"], r["rep"], r["arm"])].append(r)
    dup = []
    for k, rs in rows_by.items():
        for r in rs:
            a = assertion_set(r)
            if len(a) < len(r.get("cards") or []):
                dup.append({"key": "/".join(map(str, k)),
                            "card_rows": len(r.get("cards") or []),
                            "unique_normalized": len(a)})
    res["intra_arm_dedup"] = {
        "n_rows_with_duplicates": len(dup),
        "note": "工作流臂 3 帧 × 4 卡片 ⇒ 12 行只有 8 条不同断言（跨帧重复）",
        "detail": dup}

    # ④ 仪器层零必须被标出（失败路径不许静默归零）
    zeros = [{"key": "%s#r%s#%s" % (r["task_id"], r["rep"], r["arm"]),
              "n_cards": r.get("n_cards"), "parsefail_rate": r.get("parsefail_rate"),
              "n_chars": r.get("n_chars")}
             for r in rows if row_instrument_zero(r)]
    res["instrument_zeros"] = {"n": len(zeros), "detail": zeros}

    # ⑤ 与仓内既有实现对拍（同一份源码 ⇒ 证明本脚本的复刻没有走样）
    res["repo_cross_check"] = _cross_check_repo(rows, res)

    # ⑥ ★ 回归断言：承重分层必须是新增/丢失的**完整划分**
    #    （本脚本第一版把「丢失」项也去查工作流臂的承重表 ⇒ 丢失项全部落进
    #      「低承重丢失」⇒ 静默失真；此断言专门钉死这类错误）
    res["lb_partition"] = _assert_lb_partition(rows)
    return res


def _assert_lb_partition(rows) -> dict:
    """断言：承重分层不丢项、不重叠；且丢失项的承重标记来自**基线臂**。"""
    bad_partition, bad_source = [], []
    by = {(r["task_id"], r["rep"], r["arm"]): r for r in rows}
    for (t, rep, arm), r in by.items():
        if arm == BASELINE:
            continue
        b = by.get((t, rep, BASELINE))
        if b is None or row_instrument_zero(r) or row_instrument_zero(b):
            continue
        wa, ba = assertion_set(r), assertion_set(b)
        d = setdiff_report(set(wa), set(ba),
                           lb_of={"w": {k: v["lb"] for k, v in wa.items()},
                                  "b": {k: v["lb"] for k, v in ba.items()}})
        if d["added_lb"] + d["added_nonlb"] != d["n_added"]:
            bad_partition.append({"key": "%s#r%s#%s" % (t, rep, arm), "side": "added"})
        if d["lost_lb"] + d["lost_nonlb"] != d["n_lost"]:
            bad_partition.append({"key": "%s#r%s#%s" % (t, rep, arm), "side": "lost"})
        # 变异注入：若把「丢失项」的承重表错换成工作流臂的表，结果会变
        mut = setdiff_report(set(wa), set(ba),
                             lb_of={"w": {k: v["lb"] for k, v in wa.items()},
                                    "b": {k: v["lb"] for k, v in wa.items()}})
        if mut["lost_lb"] == d["lost_lb"] and d["n_lost"] > 0 and d["lost_lb"] > 0:
            bad_source.append({"key": "%s#r%s#%s" % (t, rep, arm),
                               "why": "错换承重表后结果未变 ⇒ 本用例检不出该错误"})
    return {
        "partition_complete": not bad_partition,
        "n_bad_partition": len(bad_partition),
        "bad_partition": bad_partition,
        "mutation_detectable": not bad_source,
        "n_mutation_undetectable": len(bad_source),
        "mutation_undetectable": bad_source,
    }


def _extract_func(src_path: str, fname: str):
    """从源码里**只取**一个函数的源码并执行（避开模块的重量级 import）。"""
    import ast
    with open(src_path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=src_path)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == fname:
            mod = ast.Module(body=[node], type_ignores=[])
            ns = {}
            exec(compile(ast.fix_missing_locations(mod), src_path, "exec"), ns)
            return ns[fname]
    return None


def _cross_check_repo(rows, res) -> dict:
    src = os.path.join(ROOT, REPO_SRC_REL)
    out = {"status": "SKIPPED", "why": "仓内 src 目录不在预期位置", "checks": []}
    if not os.path.isdir(src):
        return out
    checks, total_mism = [], 0

    # ⑤a char_bigrams ← metrics_priorart.py（可直接 import）
    try:
        if src not in sys.path:
            sys.path.insert(0, src)
        import metrics_priorart as MP  # type: ignore
        n = mism = 0
        for r in rows:
            for c in (r.get("cards") or []):
                t = c.get("claim") or ""
                if MP.char_bigrams(t) != char_bigrams(t):
                    mism += 1
                n += 1
        checks.append({"what": "char_bigrams（metrics_priorart.py:53）",
                       "n_cases": n, "n_mismatch": mism})
        total_mism += mism
    except Exception as e:  # pragma: no cover
        checks.append({"what": "char_bigrams", "status": "SKIPPED",
                       "why": "%s: %s" % (type(e).__name__, e)})

    # ⑤b decision_fingerprint ← anchor_out.py
    try:
        import anchor_out as AO  # type: ignore
        n = mism = 0
        for r in rows:
            for c in (r.get("cards") or []):
                t = c.get("claim") or ""
                if AO.decision_fingerprint(t) != decision_fingerprint(t):
                    mism += 1
                n += 1
        checks.append({"what": "decision_fingerprint（anchor_out.py:48）",
                       "n_cases": n, "n_mismatch": mism})
        total_mism += mism
    except Exception as e:  # pragma: no cover
        checks.append({"what": "decision_fingerprint", "status": "SKIPPED",
                       "why": "%s: %s" % (type(e).__name__, e)})

    # ⑤c dims_from_cards ← run_dev.py（只取该函数源码，避开模块重量级 import）
    try:
        fn = _extract_func(os.path.join(src, "run_dev.py"), "dims_from_cards")
        if fn is None:
            checks.append({"what": "dims_from_cards", "status": "SKIPPED",
                           "why": "run_dev.py 里找不到该函数"})
        else:
            n = mism = 0
            for r in rows:
                if sorted(fn(r.get("cards") or [])) != sorted(r.get("dims") or []):
                    mism += 1
                if sorted(fn(r.get("cards") or [])) != dims_from_cards(r.get("cards") or []):
                    mism += 1
                n += 1
            checks.append({"what": "dims_from_cards（run_dev.py:136）",
                           "n_cases": n, "n_mismatch": mism})
            total_mism += mism
    except Exception as e:  # pragma: no cover
        checks.append({"what": "dims_from_cards", "status": "SKIPPED",
                       "why": "%s: %s" % (type(e).__name__, e)})

    out["checks"] = checks
    out["n_mismatch"] = total_mism
    out["status"] = "PASS" if total_mism == 0 else "FAIL"
    if total_mism == 0:
        out.pop("why", None)
    return out


# ══════════════════════════════════════════════════════════════════════
# 打印
# ══════════════════════════════════════════════════════════════════════
def print_task1(res: dict):
    print("=" * 78)
    print("任务 1 · 仓内 20 条的双边净增益（零 API）")
    print("=" * 78)
    print("数据：%s" % READINGS_REL)
    print("题：%s ｜ 重复：%s ｜ 臂：%s" % (res["tasks"], res["reps"], res["arms"]))
    print("基线：%s（同题同重复配对）" % BASELINE)
    print()
    print("【0】绝对分母（逐行）")
    hdr = ("%-22s %5s %5s %6s %6s %6s %6s %6s %6s %6s" %
           ("arm#task#rep", "chars", "cand", "cards", "dedup", "sup", "con", "non", "dims", "pfail"))
    print(hdr)
    print("-" * len(hdr))
    for k in sorted(res["facts"]):
        f = res["facts"][k]
        pf = "None" if f["parsefail_rate"] is None else f["parsefail_rate"]
        print("%-22s %5s %5d %6d %6d %6d %6d %6d %6d %6s" % (
            k, f["n_answer_chars"], f["n_candidate_claims"], f["n_card_rows"],
            f["n_assertions_dedup"], f["n_supported"], f["n_contradicted"],
            f["n_nonclaim"], f["n_dims"], pf))
    print("  ★ cand=候选池条数（抽取出的原始条目）｜ cards=卡片行数（含跨帧重复）"
          "｜ dedup=归一化去重后的断言数（★ 集合元素就是它）")
    print("  ★ pfail=None ⇒ 该行**不是**「解析失败率 0」，而是「没测到」（见【1】失败路径）")

    print()
    print("【1】失败路径（仪器层零 ⇒ 剔除，不以 0 冒充读数）")
    if not res["failures"]:
        print("  （无）")
    for f in res["failures"]:
        print("  ★ %s#r%s#%s：n_cards=%s parsefail_rate=%s n_chars=%s ⇒ "
              "答案未产出 ⇒ **不是「测出 0 收益」**"
              % (f["task_id"], f["rep"], f["arm"], f["n_cards_field"],
                 f["parsefail_rate"], f["n_answer_chars"]))

    print()
    print("【2】逐配对双边净增益")
    print("  ★ 口径 A（结论空间）= 预注册算法 §5.2.4 ③（⋃ cards[].supports_conclusions，不加过滤）")
    print("  ★ 口径 A′（dims 过滤版，= measure.py 语义）｜ 口径 B（断言层）")
    for p in res["pairs"]:
        if p["status"] != "OK":
            print("  %-6s rep%s %-15s 【SKIPPED】仪器层零" %
                  (p["task_id"], p["rep"], p["arm"]))
            continue
        l0 = p["L0_conclusion_id_raw"]
        l1 = p["L1_conclusion_id"]
        l2 = p["L2_conclusion_family"]
        l3 = p["L3_assertion"]
        d = p["denominators"]
        print("  %-6s rep%s %-15s │ A %+3d（+%d/−%d）｜ A′ %+3d ｜ 族 %+3d │ "
              "B %+3d（+%d/−%d）承重 +%d/−%d 低 +%d/−%d"
              % (p["task_id"], p["rep"], p["arm"],
                 l0["net_gain"], l0["n_added"], l0["n_lost"],
                 l1["net_gain"], l2["net_gain"],
                 l3["net_gain"], l3["n_added"], l3["n_lost"],
                 l3["added_lb"], l3["lost_lb"],
                 l3["added_nonlb"], l3["lost_nonlb"]))
        print("        └ 分母：臂 卡片行%d 去重断言%d 候选池%d ｜ 基线 卡片行%d 去重断言%d 候选池%d"
              % (d["arm_card_rows"], d["arm_assertions_dedup"], d["arm_candidate_claims"],
                 d["base_card_rows"], d["base_assertions_dedup"], d["base_candidate_claims"]))

    print()
    print("【3】按臂汇总（净增益 = Σ(新增) − Σ(丢失)）")
    hdr2 = ("%-16s %5s %6s %6s %6s %6s %6s %6s %6s %6s %6s %6s" %
            ("臂", "n对", "A净", "A逐配对", "A′净", "族净", "B净", "B新增", "B丢失",
             "高承重新", "高承重丢", "低承重丢"))
    print(hdr2)
    print("-" * len(hdr2))
    for arm in ALL_ARMS:
        a = res["aggregate"].get(arm)
        if not a:
            continue
        pp = a.get("L0_per_pair") or []
        print("%-16s %5d %+6d %6s %+6d %+6d %+6d %6d %6d %6d %6d %6d" % (
            arm, a["n_pairs"], a["L0_net"],
            (",".join("%+d" % x for x in pp) if pp else "—"),
            a["L1_net"], a["L2_net"], a["L3_net"],
            a["L3_added"], a["L3_lost"],
            a["L3_added_lb"], a["L3_lost_lb"], a["L3_lost_nonlb"]))
    print("  ★ 「A逐配对」= 逐 (题,rep) 的净增益序列 ⇒ ★ **符号是否一致**决定"
          "「为正/为负/不可分辨」（②A 稿 §5.2.3 三行表）")
    print("  ★ 口径 A 的元素全部来自承重卡 ⇒ 承重四格：**高承重新增=|新增|、高承重丢失=|丢失|、"
          "低承重新增=0、低承重丢失=0**（下表的四格是**口径 B**的）")
    print()
    print("  改写感知（断言层）：真新增/真丢失 vs 换句话说")
    hdr3 = ("%-16s %8s %8s %8s %8s %8s %8s" %
            ("臂", "真新增", "换句话说", "真丢失", "换句话说", "净(OR)", "净(AND)"))
    print(hdr3)
    print("-" * len(hdr3))
    for arm in ALL_ARMS:
        a = res["aggregate"].get(arm)
        if not a:
            continue
        print("%-16s %8d %8d %8d %8d %+8d %+8d" % (
            arm, a["L3_added_true"], a["L3_added_para"],
            a["L3_lost_true"], a["L3_lost_para"],
            a["L3_net"], a["L3_net_AND"]))
    print("  归一化敏感性（规则 v2：再去标点）：")
    for arm in ALL_ARMS:
        a = res["aggregate"].get(arm)
        if a:
            print("    %-16s L3净(v1)=%+d  L3净(v2)=%+d" % (arm, a["L3_net"], a["L3_net_v2"]))

    print()
    print("【4】W_design_L2 vs W_train_L3（②方向 vs ③方向，同题同重复直接配对）")
    for c in res["W_design_L2_vs_W_train_L3"]:
        l0, l1, l2, l3 = c["L0"], c["L1"], c["L2"], c["L3_assertion"]
        print("  %-6s rep%s │ A 净%+3d ｜ A′ 净%+3d ｜ 族 净%+3d ｜ B 断言 新增%-2d 丢失%-2d 净%+3d"
              % (c["task_id"], c["rep"], l0["net_gain"], l1["net_gain"], l2["net_gain"],
                 l3["n_added"], l3["n_lost"], l3["net_gain"]))

    print()
    print("【5】★ 零假设标定（噪声地板）：同臂同题 rep1 vs rep2 的净增益")
    nc = res.get("null_calibration") or {}
    if not nc.get("n"):
        print("  （无可用样本）")
    else:
        print("  样本 n=%d（每对 = 同臂同题的两个重复互比 ⇒ 纯噪声）" % nc["n"])
        for d in nc["samples"]:
            print("    %-6s %-15s 口径A %+d ｜ 口径B %+d"
                  % (d["task_id"], d["arm"], d["A_net_rep1_vs_rep2"],
                     d["B_net_rep1_vs_rep2"]))
        print("  口径A：|净| 均值 %.2f、最大 %d ⇒ 噪声带 ≈ ±%d（结论 id 级）"
              % (nc["A_abs_mean"], nc["A_abs_max"], nc["A_abs_max"]))
        print("  口径B：|净| 均值 %.2f、最大 %d ⇒ 噪声带 ≈ ±%d（断言级）"
              % (nc["B_abs_mean"], nc["B_abs_max"], nc["B_abs_max"]))
        print("  ★ 判读：工作流臂的净增益若**逐配对符号不一致**且**落在噪声带内** ⇒ 判「不可分辨」")


def print_task2(res: dict):
    print("=" * 78)
    print("任务 2 · 944 批（R2）双边重算")
    print("=" * 78)
    print("★ 原始产出**未捞到**（逐条检索记录见 JSON 的 raw_search_log）")
    print("★ 下列数字 = 【仓内一手文档读数的代数推导】（恒等式 |W\\B|−|B\\W| ≡ |W|−|B|）")
    print()
    print("【0】恒等式自检：%s（随机 200 组通过=%s）"
          % (res["identity"]["statement"], res["identity"]["random_check_passed"]))
    print()
    print("【1】一手读数核对（来源 A）")
    hdr = ("%-12s %6s %5s %5s %6s %7s %8s %10s %10s" %
           ("臂", "断言", "支持", "矛盾", "非主张", "总分", "每份均值", "合法分母", "矛盾率%"))
    print(hdr)
    print("-" * len(hdr))
    for arm, d in res["arms"].items():
        print("%-12s %6d %5d %5d %6d %7.1f %8.2f %10d %10.2f" % (
            arm, d["n_assert"], d["sup"], d["con"], d["non"], d["score"],
            d["per_answer_check"], d["legal_denominator"], d["con_rate_recomputed"]))
    print("  ★ 总分 = 支持 − 2·矛盾 − 0.5·非主张（巡练打分函数）逐臂精确命中：%s"
          % {a: res["arms"][a]["score_formula_matches"] for a in res["arms"]})
    print("  ★ 断言/份：direct %.1f（=「每份答案 9 条断言」）；份/臂 = %d（18 题 × 2 重复）"
          % (res["arms"]["direct"]["assert_per_answer"], N_PER_ARM))
    print()
    print("【2】去重并集（来源 B）与双边净增益")
    hdr2 = ("%-12s %10s %12s %12s %12s %10s %10s" %
            ("臂", "宽度/题", "|U|=宽度×18", "基线|U|", "净增益", "舍入带", "符号稳健"))
    print(hdr2)
    print("-" * len(hdr2))
    for arm, d in res["arms"].items():
        ng = res["net_gain"].get(arm)
        print("%-12s %10.1f %12.1f %12s %12s %10s %10s" % (
            arm, d["width_per_task"], d["union_total"],
            ("%.1f" % ng["n_baseline_union"]) if ng else "（基线）",
            ("%+.1f" % ng["net_gain"]) if ng else "—",
            ("±%.1f" % ng["rounding_band"]) if ng else "—",
            ("是" if ng["sign_robust_to_rounding"] else "否") if ng else "—"))
    print()
    print("【3】第二条独立通路交叉验证（来源 C：dual_select 多报 9 条）")
    for arm, ng in res["net_gain"].items():
        if "cross_check" not in ng:
            print("  %s：★ **仓内未公布「多报」条数** ⇒ 本臂无第二条独立通路 ⇒ "
                  "净增益只有单条通路支撑（诚实标注，不假装有交叉验证）" % arm)
            print("     ⇒ 真实新增 ≥ %d、真实丢失 ≥ %d（由恒等式与 |U| 差给出，"
                  "但**不是**直接观测量）"
                  % (max(0, ng["net_gain"]), 0))
            continue
        cc = ng["cross_check"]
        print("  %s：多报 %d 条（支持%d/矛盾%d/未提及%d/非主张%d）"
              % (arm, cc["published_multireported"],
                 MULTI_REPORTED[arm]["sup"], MULTI_REPORTED[arm]["con"],
                 MULTI_REPORTED[arm]["unmentioned"], MULTI_REPORTED[arm]["nonclaim"]))
        print("     ⇒ 真实新增 ≥ %d（多报还额外剔了同义改写）"
              % ng["added_lower_bound_published_multireported"])
        print("     ⇒ 真实丢失 ≥ %d（= 多报 − 净增益）" % ng["lost_lower_bound"])
        print("     ⇒ 隐含交集 |W∩B| = %.1f ｜ 隐含基线并集 = %.1f"
              % (cc["implied_intersection"], cc["implied_baseline_union"]))
    print()
    print("【4】支数口径")
    bb = res["branch_basis"]
    print("  名义 %d 支 / 实测 %d 支；%s" % (bb["nominal_branches"], bb["actual_branches"], bb["note"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description="净增益双边重算（零 API）")
    ap.add_argument("--readings", default=os.path.join(ROOT, READINGS_REL),
                    help="仓内 readings 路径（默认相对脚本自身）")
    ap.add_argument("--selftest", action="store_true", help="只跑口径自检")
    ap.add_argument("--json", dest="json_out", default=None, help="额外落一份机读结果")
    args = ap.parse_args(argv)

    if not os.path.exists(args.readings):
        print("找不到 readings：%s" % args.readings, file=sys.stderr)
        return 2

    st = run_selftest(args.readings)
    print("=" * 78)
    print("自检（口径钉在仓内既有实现上）")
    print("=" * 78)
    d = st["dims_from_cards_reproduces_readings_dims"]
    print("  ① dims_from_cards 重算 == readings.dims：%d/%d 行命中"
          % (d["n_match"], d["n_rows"]))
    if d["mismatches"]:
        for m in d["mismatches"]:
            print("     ✗ %s" % m)
    print("  ② 集合差恒等式：%s" % ("PASS" if st["setdiff_identity"]["passed"] else "FAIL"))
    print("  ③ 臂内去重：%d 行存在跨帧重复（12 卡片行 → 8 条不同断言）"
          % st["intra_arm_dedup"]["n_rows_with_duplicates"])
    print("  ④ 仪器层零（失败路径）：%d 行 ⇒ 剔除，不以 0 冒充读数"
          % st["instrument_zeros"]["n"])
    cc = st["repo_cross_check"]
    print("  ⑤ 与仓内模块对拍：%s%s"
          % (cc["status"], ("（%s）" % cc["compared"]) if cc.get("compared") else
             ("（%s）" % cc["why"] if cc.get("why") else "")))
    for ch in cc.get("checks", []):
        if ch.get("status") == "SKIPPED":
            print("       · %s：SKIPPED（%s）" % (ch["what"], ch.get("why")))
        else:
            print("       · %s：%d 例，%d 处不一致"
                  % (ch["what"], ch["n_cases"], ch["n_mismatch"]))
    lp = st["lb_partition"]
    print("  ⑥ 承重分层完整划分（回归断言）：%s（%d 处不完整）"
          % ("PASS" if lp["partition_complete"] else "FAIL", lp["n_bad_partition"]))
    print("     变异注入：把「丢失项」的承重表错换成工作流臂的表 ⇒ %s"
          % ("可检出（断言有效）" if lp["mutation_detectable"]
             else "★ 本批检不出 ⇒ 断言覆盖不足"))
    print()
    if args.selftest:
        if args.json_out:
            json.dump(st, open(args.json_out, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        return 0

    t1 = run_task1(args.readings)
    print_task1(t1)
    print()
    t2 = run_task2()
    print_task2(t2)

    if args.json_out:
        payload = {"selftest": st, "task1": t1, "task2": t2}
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(_jsonable(payload), fh, ensure_ascii=False, indent=1)
        print("\n机读结果已落：%s" % args.json_out)
    return 0


def _jsonable(o):
    """把 tuple 键等转成 JSON 可序列化的形式（不丢信息）。"""
    if isinstance(o, dict):
        return {("%s#%s" % k if isinstance(k, tuple) else str(k)): _jsonable(v)
                for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(x) for x in o]
    return o


if __name__ == "__main__":
    sys.exit(main())
