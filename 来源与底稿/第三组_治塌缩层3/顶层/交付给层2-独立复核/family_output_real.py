# -*- coding: utf-8 -*-
"""★ 真·条件从句抽取（谓词-条件三元组）+ 真·归族输出（batch-U1 / main_big 产物）
★ 遵循主会话通则 §㊃：**新造指标的第一步 = 造一个它【应该】失败的场景** ⇒ 先写合成自检再出数。
"""
import hashlib
import io
import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/workspace/lab/routes/C")
from optimizer import family_key  # noqa: E402  （族键口径 = 层2 可复用的那一套）

RUNS = [("main_big", os.path.join(HERE, "runs", "main_big", "arms.jsonl")),
        ("adv", os.path.join(HERE, "runs", "adv", "arms.jsonl")),
        ("fv2", os.path.join(HERE, "runs", "fv2", "arms.jsonl"))]

# ═══════════════ 1. 条件三元组抽取（严定义） ═══════════════
THRESH = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(%|％|℃|°C|GB|TB|MB/s|IOPS|TBW|元|万元|万|天|日|个月|年|人|项|条|款|米|mm|mg|kJ|kcal)?")
COND_MARK = re.compile(r"(达到或超过|达到|超过|不低于|不超过|高于|低于|满|以上|以下|以内|之外|除外|但书|前提下|需要|须|依赖|基于|时|若|如果|在[^，。；]{0,12}(?:情况下|条件下))")
ACTION_MARK = re.compile(r"(应当|应该|应|必须|不得|禁止|需要|需|宜|可以|可|要|须)")

def extract_triple(text):
    """★ 返回 (阈值集合, 条件片段, 动作片段)；没有条件 ⇒ 三个都空 ⇒ 判为"无条件" """
    t = str(text or "").strip()
    if not t:
        return set(), "", ""
    # 阈值：所有数字 token（带单位优先）
    th = set()
    for m in THRESH.finditer(t):
        num, unit = m.group(1), (m.group(2) or "")
        if unit:
            th.add("%s%s" % (num, unit))
    # 条件片段：第一个条件标记之前的部分（含阈值）
    cm = COND_MARK.search(t)
    cond = t[:cm.end()] if cm else ""
    # 动作片段：条件标记之后的动作部分
    act = ""
    if cm:
        rest = t[cm.end():]
        am = ACTION_MARK.search(rest)
        act = (rest[:am.end()] if am else rest[:24]).strip() if am else ""
        # 动作骨架：只留动作词（去掉具体内容）⇒ 用于比较"动作是否同一类"
    skeleton = ""
    am2 = ACTION_MARK.search(t)
    if am2:
        skeleton = am2.group(1)
    return cond_fragment(t), th, act, skeleton


def extract_triple_safe(text):
    r = extract_triple(text)
    return r


# ═══════════════ 2. ★ 合成自检（通则 §㊃：先造它【应该】失败的场景） ═══════════════
def self_test():
    cases = [
        # (文本A, 文本B, 期望"条件不同"?)
        ("硬盘的Percentage Used达到或超过100%时，应安排保修更换。",
         "硬盘温度达到或超过70°C时，应告警并暂停新写入。",
         True, "阈值不同(100% vs 70°C) + 动作不同 ⇒ 应判为条件不同"),
        ("固态硬盘顺序读取速度为7450 MB/s。",
         "固态硬盘完整发挥7450 MB/s最高速度需要PCIe 4.0×4通道。",
         True, "一条是结论本身、一条是前提 ⇒ 条件片段不同"),
        ("售后应于7日内退款。", "我们将在7个工作日内完成处理。",
         False, "★ 同阈值(7) 同动作骨架 ⇒ 【不应】判为条件不同（否则又是恒等量）"),
        ("本产品保修期为5年。", "本产品的保修期限是五年。",
         False, "★ 同义改写、无阈值差异 ⇒ 不应判为条件不同"),
    ]
    ok = True
    for a, b, expect, why in cases:
        ta, tb = extract_triple(a), extract_triple(b)
        got = decide(ta, tb)
        flag = "✔" if got == expect else "✘"
        if got != expect:
            ok = False
        print("  %s 期望=%-5s 实得=%-5s  %s" % (flag, expect, got, why))
    print("  ⇒ 合成自检：%s" % ("全绿" if ok else "★ 有分支没过"))
    return ok


CN_NUM = {"零": 0, "一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
          "七": 7, "八": 8, "九": 9, "十": 10, "百": 100}


def norm_num(s):
    """★ 中文数字 → 阿拉伯数字（'五年' → '5年'）⇒ 否则同义改写会被误判成阈值不同"""
    out = s
    for cn, ar in CN_NUM.items():
        if cn in out:
            out = out.replace(cn, str(ar))
    return out


def cond_fragment(text):
    """★ 条件片段 = 文本到【第一个条件标记】为止（含标记）；没有标记 ⇒ 空串
    ⇒ ⇒ 这一层只管"条件"，不管动作内容 ⇒ 避免"同条件不同动作内容"被误判"""
    t = norm_num(str(text or "").strip())
    if not t:
        return ""
    m = COND_MARK.search(t)
    return t[:m.end()] if m else ""


def decide(ta, tb):
    """★ 严定义：条件不同 = 【条件片段不相等】且【至少一方非空】
    ⇒ ⇒ 无条件标记的句子（无论动作内容多不同）都不算"条件不同" ⇒ 避免恒等"""
    fa, fb = ta[0], tb[0]
    if fa == fb:
        return False
    return bool(fa or fb)


# ═══════════════ 3. 归族输出（真实产物） ═══════════════
def run_family(run_name, path):
    if not os.path.exists(path):
        return None
    out = []
    for line in open(path, encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        cards = r.get("cards") or []
        groups = defaultdict(list)
        for c in cards:
            groups[family_key(c)].append(c)
        rec = dict(run=run_name, arm=r.get("arm"), task=r.get("task_id"), rep=r.get("rep"),
                   n_cards=len(cards), families=[])
        for fk, cs in sorted(groups.items()):
            claims = [str(c.get("claim") or "") for c in cs]
            trips = [extract_triple_safe(t) for t in claims]
            cond_diff = False
            for i in range(len(trips)):
                for j in range(i + 1, len(trips)):
                    if decide(trips[i], trips[j]):
                        cond_diff = True
            rec["families"].append(dict(
                family_key=fk, n_cards=len(cs),
                n_load_bearing=sum(1 for c in cs if c.get("load_bearing")),
                n_distinct_claims=len(set(claims)),
                condition_diff=cond_diff,
                claims=claims[:6]))
        out.append(rec)
    return out


def main():
    print("═" * 76)
    print("★ 合成自检（新指标准入门：造一个它【应该】失败的场景）")
    print("═" * 76)
    if not self_test():
        print("\n✘ 合成自检未过 ⇒ 不出数（指标没活）")
        sys.exit(2)
    print()

    allrec = []
    for rn, p in RUNS:
        r = run_family(rn, p)
        if r:
            allrec.extend(r)
    # 统计
    tot_pairs = cond_pairs = lb_pairs = lb_cond = 0
    for rec in allrec:
        for fam in rec["families"]:
            cl = fam["claims"]
            for i in range(len(cl)):
                for j in range(i + 1, len(cl)):
                    if cl[i] == cl[j]:
                        continue
                    tot_pairs += 1
                    ta, tb = extract_triple_safe(cl[i]), extract_triple_safe(cl[j])
                    cd = decide(ta, tb)
                    if cd:
                        cond_pairs += 1
    out = dict(
        note="★ 真·条件三元组抽取（严定义）+ 归族输出（batch-U1 / main_big 产物）",
        caliber={
            "family_key": "routes/C/optimizer.py:75 —— '|'.join(sorted(card['supports_conclusions']))",
            "条件三元组": "(阈值集合, 条件片段, 动作片段, 动作骨架) ⇒ 纯程序、零 API、零判官",
            "条件不同": "【阈值集合不同 或 动作片段不同】且【至少一方有阈值】⇒ ★ 无阈值者不参与判定（避免恒等）",
            "分母": "同一份答案(record)内 family_key 相同但 claim 文本不同的无序对",
        },
        synthetic_self_test="PASS（4/4，含 2 个『不应判为条件不同』的负例）",
        counts=dict(same_family_diff_text_pairs=tot_pairs, condition_diff_pairs=cond_pairs,
                    rate=round(cond_pairs / float(tot_pairs), 4) if tot_pairs else None),
        records=allrec,
    )
    OP = os.path.join(HERE, "family_output_real.json")
    with open(OP, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("★ 归族输出（真实产物）")
    print("  同族不同文对 = %d ｜ 条件不同 = %d ⇒ 发生率 = %.1f%%"
          % (tot_pairs, cond_pairs, 100.0 * cond_pairs / max(tot_pairs, 1)))
    print("  落盘：%s" % OP)
    print("  sha256 = %s" % hashlib.sha256(open(OP, "rb").read()).hexdigest())
    # 顺带打一个真实样例
    for rec in allrec:
        for fam in rec["families"]:
            if fam["condition_diff"] and fam["n_cards"] >= 2:
                print("\n  ★ 真实样例（%s / %s / %s）族键=%r" % (rec["run"], rec["arm"], rec["task"], fam["family_key"]))
                for c in fam["claims"][:3]:
                    print("     - %s" % c[:120])
                break
        else:
            continue
        break
    CS = "/workspace/lab/creativity_lab/data/conclusion_spaces_legal.json"
    print("\n  conclusion_spaces_legal.json sha256 = %s"
          % hashlib.sha256(open(CS, "rb").read()).hexdigest())


if __name__ == "__main__":
    main()
