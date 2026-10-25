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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "judge"))
import u1_lib as U

BATCH = U.BATCH
RUNS = os.path.join(BATCH, "runs")
MEAS_VERSION = "U1-measure-v2-2026-10-22+singleattempt+par"  # ★ 阶梯不嵌套（每档一次）+ 卡片批次并行 + 8k 起 + 批 8 + 断言上限 12

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


def _json_blocks(text):
    """从一段文本里**配平括号**地抽出所有顶层 JSON 对象（不管它们前面有没有别的东西）。

    ★ 2026-10-22 实测教训：MiniMax 的卡片输出**不是稳定的"一行一个 JSON"**：
      实测出现过 ```` ```json ```` 包裹、行内有前导文字、一行多个对象
      ⇒ 旧解析器（只认"行首是 {"）会 **100% 解析失败** ⇒ 而 `parsefail_rate` 只在
      "卡片条数不够"时才体现 ⇒ ⇒ **静默变成 dims=0**，看起来像"这条臂没有承重信息"。
      ⇒ 这就是"失败不许静默变 0"的第四例，且是**我自己早就踩过**的坑（U1 的 R2）。
    """
    out, i, n = [], 0, len(text or "")
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth, j, in_str, esc = 0, i, False, False
        while j < n:
            ch = text[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        out.append(text[i:j + 1])
                        i = j + 1
                        break
            j += 1
        else:
            break
    return out


def parse_cards(raw, n, loose=True):
    """解析判官返回的卡片 JSON。

    ★ 两级：
      ① **strict**：行首就是 `{` 的行（快、严）
      ② **loose**：配平括号抽块 + 剥 code fence + 容忍尾逗号（慢、宽）
    ⇒ 返回 (cards, mode)；mode ∈ {"strict","loose","none"} ⇒ **解析路径本身可诊断**
    """
    def _norm(block):
        b = block.strip()
        b = re.sub(r"^```(?:json)?\s*", "", b)
        b = re.sub(r"\s*```$", "", b)
        b = re.sub(r",\s*([}\]])", r"\1", b)          # 容忍尾逗号
        return b

    def _mk(block, idx):
        try:
            d = json.loads(_norm(block))
        except Exception:
            return None
        if not isinstance(d, dict):
            return None
        d["i"] = int(d.get("i", idx + 1))
        d["supports_conclusions"] = [int(x) for x in (d.get("supports_conclusions") or [])
                                    if str(x).strip().isdigit()]
        return d

    raw = raw or ""
    out = []
    for i, ln in enumerate(raw.splitlines()):
        ln = ln.strip()
        if not ln.startswith("{"):
            continue
        d = _mk(ln, i)
        if d is not None:
            out.append(d)
    if out or not loose:
        return out, ("strict" if out else "none")
    # ── loose
    out = []
    for k, blk in enumerate(_json_blocks(raw)):
        d = _mk(blk, k)
        if d is not None:
            out.append(d)
    return out, ("loose" if out else "none")


def _chat_ladder(llm, prompt, *, model, temp, budgets, min_ok, purpose):
    """★ 2026-10-22：**一次尝试 = 一次调用**（不把阶梯交给客户端再套一层）。

    旧写法 `llm.chat(..., max_tokens=8000, budgets=(12000,16000))`
    ⇒ 客户端内部按 (8000, 12000, 16000) 试 **3 次**；再叠加外层阶梯
    ⇒ 一次逻辑调用最多 6 次尝试 ⇒ 实测把一个批次拖成 40 分钟。
    ⇒ 现在阶梯由本函数独占控制，**每档只试一次**。
    """
    last = ""
    fr = ""
    for mt in budgets:
        last = llm.chat(prompt, model=model, temp=temp, max_tokens=mt,
                        budgets=(), min_ok=min_ok, purpose=purpose) or ""
        rec = getattr(llm, "rec", None)
        fr = getattr(rec[-1], "finish_reason", "") if rec else ""
        if last.strip() and fr != "length":
            break
    return last, dict(attempts=len(budgets), finish_reason=fr,
                       empty=not bool(last.strip()))


# ══════════════════════════════════════════════════════════════════════
# ★ 锚外判官（2026-10-22 新增）：**故意不给结论空间 C_t**
# ══════════════════════════════════════════════════════════════════════
# 为什么必须有它：普通判官**拿着 C_t 打分** ⇒ 它只能标"支撑 C_t 第几条"
# ⇒ ⇒ **锚外维度在普通判据下永远不可见** ⇒ VD_anchor_out 恒为 0
#    —— 那是**判据设计的必然**，不是"我们没发现"。
# ⇒ ⇒ 锚外必须**换一个不知道 C_t 的判官**：只给依据，让它自己说
#    「这句话改变了哪个决策」+「它依赖哪几条依据」；然后**由我们**去比
#    这个岔口在不在 C_t 里 ⇒ 这就是 Curiosity Search 的 leave-one-out
#    精神（**不需要事前白名单**）。
ANCHOR_OUT_Q = """下面是一份「依据条目」清单、一个问题，以及若干条候选陈述。
请对**每条**候选陈述逐条判断。**注意：这里没有给你任何预定的结论清单**
——请你自己判断每条陈述**改变了哪个决策**。

问题：
{ask}

依据条目：
{ev}

候选陈述：
{claims}

对每条候选陈述，输出**一行 JSON**，字段如下（不要输出别的任何内容）：
{{"i": <编号>,
  "is_claim": true/false,
  "verdict": "支持"/"矛盾"/"未提及"/"非主张",
  "evidence_ref": "EV-07",
  "load_bearing": true/false,
  "decision_changed": "如果这条信息为假，答案的哪一句/哪一个决策会变？（写具体；写不出就填 null）",
  "uses_evidence": ["EV-03", "EV-07"]}}

判据：
- 「支持」= 依据条目明确认可或蕴含该条；「矛盾」= 依据讲了相反的内容；「未提及」= 依据没讲到
- **load_bearing**：写得出「改变了哪个决策」才为 true；复述、铺陈、寒暄、免责 ⇒ false
- **uses_evidence**：列出这条陈述**实际依赖**的依据条目编号（可为空数组）
"""


def extract_claims(llm, answer, *, cap=12, model=None):
    """抽断言（**两个判官共用同一批** ⇒ 省一次调用）。

    ★ `model` 必须**跟着判官走** —— 否则换厂商时抽取会拿着上一个厂商的模型名去打
      ⇒ 400（"X is not a valid model ID"）⇒ **静默返回空串** ⇒ 读数变 0
      ⇒ 而那会被误读成"这条臂没有承重信息"。2026-10-23 实测踩到。
    """
    raw, _i = _chat_ladder(llm, EXTRACT_Q.format(t=(answer or "")[:3000]),
                           model=model or U.MM_MODEL, temp=0.0,
                           budgets=(8000, 12000, 16000), min_ok=10, purpose="extract")
    claims = []
    for ln in (raw or "").splitlines():
        ln = re.sub(r"^\s*[-*\d.、)）]+\s*", "", ln).strip()
        if 8 <= len(ln) <= 120:
            claims.append(ln)
    return list(dict.fromkeys(claims))[:cap]


def measure_anchor_out(llm, ask, ev_items, answer, answer_id, claims=None,
                        judge_model=None):
    """锚外测量：**不给 C_t** 的判官 ⇒ 只看「依据 + 陈述」⇒ 它自己说改变了哪个决策。

    ★ `judge_model` 必须**跟着判官走**（抽取与卡片两处都要）——
      否则换厂商时仍拿着上一个厂商的模型名去打 ⇒ 400 ⇒ 静默空串
      ⇒ **锚外数恒为 0**，而那会被误读成"主命题不成立"（2026-10-23 实测踩到）。
    """
    _jm = judge_model or U.MM_MODEL
    """锚外测量：**不给 C_t** 的判官 ⇒ 只看「依据 + 陈述」⇒ 它自己说改变了哪个决策。

    返回 dict：cards（带 decision_changed / uses_evidence）+ 统计
    ⚠️ 与普通判官**分开计数**：锚外的解析失败率必须单独报，不许混进主判据的读数。
    """
    res = dict(answer_id=answer_id, mode="anchor_out", n_chars=len(answer or ""))
    if not (answer or "").strip():
        res.update(valid=0, reason="empty_answer", n_cards=0, n_parsefail=0)
        return res
    if claims is None:
        claims = extract_claims(llm, answer, model=_jm)
    res["n_claims_extracted"] = len(claims)
    if not claims:
        res.update(valid=1, n_cards=0, n_parsefail=0)
        return res
    evs = "\n".join("%d. %s" % (i + 1, e["text"]) for i, e in enumerate(ev_items))
    cards, n_parsefail = [], 0
    B = 8
    batches = [claims[i:i + B] for i in range(0, len(claims), B)]
    def _one(bb):
        def _call(chunk):
            lst = "\n".join("%d. %s" % (k + 1, chunk[k]) for k in range(len(chunk)))
            r, _inf = _chat_ladder(llm, ANCHOR_OUT_Q.format(ask=ask, ev=evs, claims=lst),
                                   model=_jm, temp=0.0,
                                   budgets=(8000, 12000, 16000),
                                   min_ok=len(chunk) * 15, purpose="anchor_out")
            return parse_cards(r, len(chunk))
        got, mode = _call(bb)
        if len(got) < len(bb) and len(bb) > 1:
            half = len(bb) // 2
            got, mode = [], mode
            for part in (bb[:half], bb[half:]):
                if not part:
                    continue
                g2, m2 = _call(part)
                got.extend(g2)
                if m2 != "none":
                    mode = m2
        for g in got:
            g["claim"] = bb[g["i"] - 1] if 1 <= g["i"] <= len(bb) else ""
            g["uses_evidence"] = list(g.get("uses_evidence") or [])
        return got, max(0, len(bb) - len(got)), mode
    if len(batches) > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(len(batches), 4)) as _ex:
            rs = list(_ex.map(_one, batches))
    else:
        rs = [_one(batches[0])]
    parse_modes = {}
    for got, pf, _mode in rs:
        n_parsefail += pf
        parse_modes[_mode] = parse_modes.get(_mode, 0) + 1
        cards.extend(got)
    res["parse_modes"] = parse_modes
    res["n_cards"] = len(cards)
    res["n_parsefail"] = n_parsefail
    res["parsefail_rate"] = n_parsefail / max(len(claims), 1)
    res["cards"] = cards
    return res


def measure_answer(llm, ask, ev_items, ct, answer, answer_id,
                   judge_model=None, card_q=None, claims=None):
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
    if claims is None:
        raw, _xinfo = _chat_ladder(llm, EXTRACT_Q.format(t=(answer or "")[:3000]),
                                   model=_jm, temp=0.0,
                                   budgets=(8000, 12000, 16000), min_ok=10,
                                   purpose="extract")
    else:
        raw = "\n".join("- " + c for c in claims)
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

    def _one_batch(bb):
        """判一批。★ 阶梯**由本函数独占控制**（每档只试一次），
        且**批次之间并行** ⇒ 2 批 ⇒ 1× 等待而不是 2×。

        ★ 2026-10-22：解析不足 ⇒ **降批重试**（把这一批再对半分）
          ⇒ 实测 MiniMax 的卡片输出偶发不合规 ⇒ 旧做法直接 100% 解析失败
          ⇒ **静默变成 dims=0**（看起来像"这条臂没有承重信息"）
        ⇒ 解析路径（strict/loose）**单独记录**，不许混进读数。
        """
        def _call(chunk):
            lst = "\n".join("%d. %s" % (k + 1, chunk[k]) for k in range(len(chunk)))
            r, _info = _chat_ladder(llm, _cq.format(ask=ask, ev=evs, claims=lst),
                                     model=_jm, temp=0.0, budgets=(8000, 12000, 16000),
                                     min_ok=len(chunk) * 15, purpose="card")
            return parse_cards(r, len(chunk))

        got, mode = [], "none"
        for mt in (8000,):
            got, mode = _call(bb)
            if len(got) >= len(bb):
                break
        if len(got) < len(bb) and len(bb) > 1:
            # ★ 降批重试：对半分，各自再判一次
            half = len(bb) // 2
            got, mode = [], mode
            for part in (bb[:half], bb[half:]):
                if not part:
                    continue
                g2, m2 = _call(part)
                got.extend(g2)
                if m2 != "none":
                    mode = m2
        return got, max(0, len(bb) - len(got)), (len(got) < len(bb)), mode

    _batches = [claims[i:i + B] for i in range(0, len(claims), B)]
    if len(_batches) > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(len(_batches), 4)) as _ex:
            _results = list(_ex.map(_one_batch, _batches))
    else:
        _results = [_one_batch(_batches[0])]
    parse_modes = {}
    for got, _pf, _failed, _mode in _results:
        n_parsefail += _pf
        parse_modes[_mode] = parse_modes.get(_mode, 0) + 1
        if _failed:
            card_call_failed = True
        for g in got:
            g["claim"] = claims[g["i"] - 1] if 1 <= g["i"] <= len(claims) else ""
            cards.append(g)
    res["parse_modes"] = parse_modes
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
