# -*- coding: utf-8 -*-
"""批次 U1-2026-10-21 · **测量侧**（MiniMax，与被测侧 OpenRouter 完全独立）。

按 `/workspace/lab/routes/PROTOCOL.md` §2–§4 执行，核心判据：

  D(S) = |S 能支撑的**结论空间元素**集合|
  去冗余：Δ(A→B) = D(A∪B) − D(A) = 0 ⇒ A、B 冗余（支撑同一批结论 ⇒ 合并）
  净维度增益 = |新增结论| − |丢失结论|   （相对基线臂 B0_direct，双边）

⇒ **模型只做三件事**（抽断言 / 分类与承重 / 判支持关系），
  **去冗余与净增益全是机械计算**（不依赖模型自评）。
⇒ 判官提示词**必须拿到题面 + 依据条目 + 结论空间 `C_t`**（协议 §4.6 强制句逐字包含）。
"""
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, "/workspace/lab/batch-U1")
import u1_lib as U

BATCH = U.BATCH
RUNS = os.path.join(BATCH, "runs")
MEAS_VERSION = "U1-measure-v1-2026-10-21+card8k+extract8k"  # 2026-10-22：判官阶梯 8k 起、批 8、断言上限 12、**抽取也 8k 起**

EXTRACT_Q = """从下面这段回答里，逐条列出其中**可判真假的陈述**。
一行一条，最多 20 条。

要求：
- 一条一个可独立核验的事实性陈述。
- **每条必须自足**：写出主体名称与具体数值/条件/规则，不要用「它」「该」「此项」「上述」代替主语。
- 不要观点、不要建议、不要寒暄。

文本：
{t}
"""

CARD_Q = """下面是一份「依据条目 / 结论空间」清单（**同一份事实，编号即结论编号**）、一个问题，
以及若干条候选陈述。请对**每条**候选陈述逐条判断。

问题：
{ask}

依据条目与结论空间（编号即结论编号）：
{ev}

候选陈述：
{claims}

对每条候选陈述，输出**一行 JSON**，字段如下（不要输出别的任何内容）：

{{"i": <候选编号>,
 "is_claim": true/false,          ← 只复述了问题里给出的情形 ⇒ false
 "verdict": "支持"/"矛盾"/"未提及"/"非主张",
 "evidence_ref": "EV-07",          ← verdict 为 支持/矛盾 时必填（依据条目编号）；否则填 null
 "evidence_class": "事实"/"推论"/"价值判断"/"建议",
 "load_bearing": true/false,       ← 见下方承重检验
 "decision_changed": "<它改变了哪个决策/结论；写不出来就填空字符串>",
 "supports_conclusions": [<结论编号>...],   ← 该陈述支撑清单里哪几条结论；支撑不了就填 []
 "maps_to_question": true/false}}  ← 与原题相关吗

**判据一 · 是不是断言**：只要陈述里含有**超出问题本身**的信息（数字/阈值/名称/规则/主体关系/比较/归类），
就当它是断言；**由问题里的数值加上依据规则推导出的结论，是断言，不是复述**。只复述情形的，is_claim=false。

**判据二 · 关系**：依据条目明确认可或蕴含该条 ⇒「支持」（改写、简称、换词但含义相同也算支持）；
依据条目明确讲了相反的内容（数字对不上、阈值不同、方向相反）⇒「矛盾」；
依据没讲到或讲的是别的事 ⇒「未提及」。**不确定时一律答「未提及」。**

**判据三 · 承重检验（最重要）**：这条陈述**改变了一个决策或结论**吗？
- 它必须能指向上面清单里的**某一条具体结论编号**，并说明「没有它，结论就不成立/就不同」；
- **写不出「改变了哪个决策/结论」⇒ load_bearing=false**（哪怕它是真的、哪怕依据支持它）。
- 复述、铺陈、寒暄、免责、延伸感想 ⇒ load_bearing=false。

**判据四 · 证据类别**：陈述本身是「事实」（可核验的既有信息）/「推论」（由事实推出）/「价值判断」（好坏取舍）/「建议」（行动提议）。

一行一条 JSON，顺序对应，不要解释，不要补充。
"""


def parse_cards(raw, n):
    out = []
    for i, ln in enumerate((raw or "").splitlines()):
        ln = ln.strip()
        if not ln.startswith("{"):
            continue
        try:
            d = json.loads(ln)
        except Exception:
            continue
        d["i"] = int(d.get("i", i + 1))
        d["supports_conclusions"] = [int(x) for x in (d.get("supports_conclusions") or [])
                                    if str(x).strip().isdigit()]
        out.append(d)
    return out


def measure_answer(llm, ask, ev_items, ct, answer, answer_id,
                   judge_model=None, card_q=None):
    """对**一份**最终答案跑完整条测量流水线。返回该份的测量结果。

    ⚠️ 2026-10-22 新增两个**向后兼容**参数（默认值 ⇒ 行为完全不变）：
      * `judge_model` —— 换判官**模型**。用于测 **δ_judge_version**（跨判官版本/模型）。
      * `card_q`    —— 换判官**提示词版本**。同上。
    ⇒ 这两个参数是「判官侧漂移不可见」这个缺陷的补救入口（见 routes/C/noise_floor.py）。
    """
    _jm = judge_model or U.MM_MODEL
    _cq = card_q or CARD_Q
    res = dict(answer_id=answer_id, n_chars=len(answer or ""),
               judge_model=_jm, card_prompt_version=("custom" if card_q else "v1"))
    if not (answer or "").strip():
        res.update(valid=0, reason="empty_answer")
        return res

    # ── 1. 机械抽断言（MiniMax）
    raw = llm.chat(EXTRACT_Q.format(t=(answer or "")[:3000]),
                   model=_jm, temp=0.0, max_tokens=8000,
                   budgets=(12000, 16000), min_ok=10, purpose="extract")
    # ⚠️ 2026-10-22 实测：抽取侧原为 max_tokens=3000 ⇒ **同样在"必然失败"档**
    #   （MiniMax adaptive thinking 吃光预算 ⇒ 正文空 ⇒ 0 条断言 ⇒ 0 张卡片）
    #   ⇒ 而 `parsefail_rate` 仍是 0.0 ⇒ **静默** ⇒ 被误读成"这条臂没有承重信息"。
    #   （D01 实测：W 臂因此报 dims=0，实际答案有 1056 字符、9 条内容）
    claims = []
    for ln in (raw or "").splitlines():
        ln = re.sub(r"^\s*[-*\d.、)）]+\s*", "", ln).strip()
        if 8 <= len(ln) <= 120:
            claims.append(ln)
    claims = list(dict.fromkeys(claims))[:12]   # ⚠️ 2026-10-22：20→12（判官成本线性于条数）
    res["n_claims_extracted"] = len(claims)
    if not claims:
        res.update(valid=1, n_cards=0, n_load_bearing=0, parsefail=0)
        return res

    # ── 2. 构造成维度卡片（MiniMax，拿题面 + 依据 + C_t）
    # ⚠️ 依据与 C_t 是**同一批事实** ⇒ 只传一份（原先传两遍 ⇒ 提示词 3771 字符
    #    ⇒ MiniMax 把预算全花在思考块上、正文为空 ⇒ 卡片解析 100% 失败（R2 触发））
    evs = "\n".join("%d. %s" % (i + 1, e["text"]) for i, e in enumerate(ev_items))
    cards, n_parsefail = [], 0
    card_call_failed = False
    B = 8          # ⚠️ 2026-10-22：4→8 ⇒ 批次数减半 ⇒ 判官调用数减半
    for i in range(0, len(claims), B):
        b = claims[i:i + B]
        lst = "\n".join("%d. %s" % (n + 1, b[n]) for n in range(len(b)))
        got = []
        # ⚠️ 2026-10-22 实测：max_tokens=4000 时 MiniMax 的 adaptive thinking 会
        #    **把预算吃光、正文长度 0**（finish_reason=length, content_len=0）
        #    ⇒ 4000 这一档**必然失败并重试** ⇒ 每次判官调用成本翻倍（实测 106.5s/次）。
        #    ⇒ 阶梯直接从 8000 起。
        for mt, buds in ((8000, (12000, 16000)),):
            r = llm.chat(_cq.format(ask=ask, ev=evs, claims=lst),
                         model=_jm, temp=0.0, max_tokens=mt,
                         budgets=buds, min_ok=len(b) * 15, purpose="card")
            got = parse_cards(r, len(b))
            if len(got) >= len(b):
                break
        n_parsefail += max(0, len(b) - len(got))
        if len(got) < len(b):
            card_call_failed = True
        for g in got:
            g["claim"] = b[g["i"] - 1] if 1 <= g["i"] <= len(b) else ""
            cards.append(g)
    res["card_call_failed"] = card_call_failed
    res["n_cards"] = len(cards)
    res["parsefail"] = n_parsefail
    res["parsefail_rate"] = n_parsefail / max(len(claims), 1)

    # ── 3. 承重 + 去冗余（机械）
    lb = []
    for c in cards:
        if not c.get("is_claim"):
            continue
        if c.get("load_bearing") is not True:
            continue
        if not c.get("decision_changed"):
            continue
        if not c.get("supports_conclusions"):
            continue
        lb.append(c)
    res["n_load_bearing_cards"] = len(lb)

    # 去冗余：贪心保留"每张都新增至少一条结论"的卡片；Δ=0 ⇒ 冗余
    kept, seen = [], set()
    n_redundant = 0
    for c in lb:
        new = set(c["supports_conclusions"]) - seen
        if new:
            kept.append(c)
            seen |= new
        else:
            n_redundant += 1
    res["n_redundant_merged"] = n_redundant
    res["n_dimensions"] = len(kept)                       # 维度数（去冗余后）
    res["conclusions_supported"] = sorted(seen)          # D(S) 的元素
    res["D"] = len(seen)
    res["cards_kept"] = [dict(claim=c["claim"],
                               verdict=c.get("verdict"),
                               evidence_ref=c.get("evidence_ref"),
                               evidence_class=c.get("evidence_class"),
                               decision_changed=c.get("decision_changed"),
                               supports_conclusions=c.get("supports_conclusions"))
                          for c in kept]
    res["cards_all"] = [dict(claim=c.get("claim"), verdict=c.get("verdict"),
                              evidence_ref=c.get("evidence_ref"),
                              evidence_class=c.get("evidence_class"),
                              load_bearing=c.get("load_bearing"),
                              decision_changed=c.get("decision_changed"),
                              supports_conclusions=c.get("supports_conclusions"))
                         for c in cards]
    res["valid"] = 1
    return res


def main():
    pack = U.load_u1()
    ask = pack["ask"]
    ev_items = U.evidence_items(pack)
    ct = U.conclusion_space(pack)

    arms = ["B0_direct", "B1_eq_calls", "A_fixed", "C_T2"]
    llm = U.MiniMaxLLM()
    out = {}
    for arm in arms:
        d = os.path.join(RUNS, arm)
        if not os.path.isdir(d):
            continue
        for rep in range(1, 4):
            ap = os.path.join(d, "rep%d.answer.md" % rep)
            if not os.path.exists(ap):
                continue
            ans = open(ap, encoding="utf-8").read()
            m = measure_answer(llm, ask, ev_items, ct, ans, "%s#rep%d" % (arm, rep))
            m["arm"] = arm
            m["rep"] = rep
            m["human"] = U.human_score(ans)
            out["%s#rep%d" % (arm, rep)] = m
            print("%-12s rep%d: 断言%2d 卡片%2d 承重%2d 维度%2d D=%2d ｜ 人肉 %.1f %s"
                  % (arm, rep, m.get("n_claims_extracted", 0), m.get("n_cards", 0),
                     m.get("n_load_bearing_cards", 0), m.get("n_dimensions", 0),
                     m.get("D", 0), m["human"]["score"], m["human"]["matched"]))
    # ── 净维度增益（相对 B0 基线，双边）────────────────────────
    # ★ **配对基线**：净增益的基线是**同 rep** 的 B0（固定用 rep1 会把基线噪声
    #   记成被测臂的"丢失"）⇒ 同 rep 配对。
    for k, v in out.items():
        rep = v.get("rep", 1)
        base = out.get("B0_direct#rep%d" % rep)
        base_set = set(base.get("conclusions_supported", [])) if base else set()
        cur = set(v.get("conclusions_supported", []))
        added = sorted(cur - base_set)
        lost = sorted(base_set - cur)
        v["added_conclusions"] = added
        v["lost_conclusions"] = lost
        v["net_dimension_gain"] = len(added) - len(lost)
        v["baseline_conclusions"] = sorted(base_set)
        v["baseline_key"] = "B0_direct#rep%d" % rep
    with open(os.path.join(BATCH, "measurement.json"), "w", encoding="utf-8") as f:
        json.dump(dict(measure_version=MEAS_VERSION, judge_model=U.MM_MODEL,
                       judge_vendor="minimax", tested_vendor="openrouter",
                       judge_same_vendor=False, ct_len=len(ct),
                       facts=len(ev_items),
                       evidence_hash=U.sha([e["text"] for e in ev_items]),
                       results=out), f, ensure_ascii=False, indent=2)
    print("\n✓ 测量结果落盘 measurement.json（判官 %s / 被测 %s）"
          % (U.MM_MODEL, U.OR_MODEL))


if __name__ == "__main__":
    main()
