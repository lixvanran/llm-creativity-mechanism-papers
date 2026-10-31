#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_tokens.py —— T-AGENT-TOKENS 跑批器（★ 单一 Agent 反复聚焦于每一个 token ★）

★ 预注册：来源与底稿/第五组_新产出/注意力拆散/PREREG_TOKENS_逐token聚焦_2026-10-31.md
★ 五臂（★ 全部单 agent ★）：
  B0 direct         层3 arm_direct 逐字（★ 跨批基准 ★）
  T1 token_tag      逐 token 角色标注 → 汇总作答
  T2 token_probe    逐 token 角色标注 → 逐 token 追问 → 汇总作答（★ 主臂 ★）
  T3 token_shuffle  ★ 与 T2 同流程、★ 只把清单里的 token 顺序打乱 ★（★ 归因闸门 ★）
  T4 sentence_tag   ★ 切分单元换成句子 ★（★ 粒度对照 ★）

★★ 纪律 ★★：
· 依据包 / 结论空间 / 金标 **一律不进提示词**（★ devset 规格 §3.5 ★）
· token 切分是**纯函数**（★ 只吃题面字符串、★ 不得用 gold ★）
· 打乱用固定种子 20261031 ＋ Fisher–Yates（★ 只打乱清单、★ 不打乱原题面 ★）
· 跑批顺序 ＝ rep 外层、臂内层、题内层（★ 额度中断时各臂完成度均衡 ★）
"""

import argparse
import hashlib
import json
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm2 import LLM2, QuotaExhausted, atomic_write_jsonl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), "runs_tokens")
DEVSET_DEFAULT = "/workspace/work/devset/devset.json"

SHUFFLE_SEED = 20261031

# ★ 层3 的 _OUT_SPEC（★ 逐字抄自 repro/src/workflow.py:848-852 ★）
_OUT_SPEC = ("【输出规格】\n"
             "- 只输出 3–6 条，每条一行，行首用「- 」\n"
             "- 每条必须**具体**：带一个数字 / 一个明确条件 / 一个可核查的判断\n"
             "- 不写开场白、不写总结、不写免责说明\n"
             "- 不超过 400 字")

# ★ 层3 `arm_direct` 的逐字拼法（run_dev.py:155）
P_DIRECT = "问题：{ask}\n\n" + _OUT_SPEC

P_SUM = ("问题：{ask}\n\n"
         "【你已逐个检查过的清单】\n{checklist}\n\n"
         + _OUT_SPEC)

P_TAG = """【题面】
{ask}

【切分序列】★ 顺序即下面给出的顺序、★ 不许增删、★ 不许合并 ★
{units}

请**逐个**给出标注，★ 不许跳过任何一项、★ 输出顺序必须与上面一致 ★
- role：该项的角色（主体/数值/单位/条件/动作/修饰/连接/标点/其他）
- decisive：该项是否携带"可判定的要素"（★ 数值、阈值、适用条件、主体关系、量词 ★）
- gloss：它在这道题里的作用（一句话、★ 不超过 20 字 ★）

★ 只输出 JSON：{"ann": [{"i": 1, "role": "...", "decisive": true, "gloss": "..."}, ...]} ★"""

P_PROBE = """【题面】
{ask}

【逐项标注】
{ann}

请**逐个**回答（★ 只针对 decisive=true 的项 ★）：
- what：这一项规定的到底是什么（数值/条件/主体/量词…）
- trap：这一处最容易被读错或搞混的地方（★ 没有就写"无" ★）

★ 只输出 JSON：{"probe": [{"i": 3, "what": "...", "trap": "..."}, ...]} ★"""

ARMS = ["B0", "T1", "T2", "T3", "T4"]
# ★ 每臂的阶段序列（★ 阶段名 → 函数 ★）
ARM_STAGES = {
    "B0": ["direct"],
    "T1": ["tag", "sum"],
    "T2": ["tag", "probe", "sum"],
    "T3": ["tag_shuf", "probe", "sum"],
    "T4": ["tag_sent", "sum"],
}

_lock = threading.Lock()
_rows = []


def sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()[:16]


def cut_tokens(s):
    """★ 字符/词级切分（★ 纯函数、★ 只吃题面 ★）★★
    ★ 连续 ASCII 字母数字与 `%.%/-` 合成一个 token、★ 其余每字符一个 ★
    """
    out = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch.isascii() and (ch.isalnum() or ch in "%.%/-"):
            j = i
            while j < len(s) and s[j].isascii() and (s[j].isalnum() or s[j] in "%.%/-"):
                j += 1
            out.append(s[i:j])
            i = j
        else:
            out.append(ch)
            i += 1
    return out


def cut_sentences(s):
    """★ 句子级切分（★ 粒度对照用 ★）★"""
    parts, cur = [], ""
    for ch in s:
        cur += ch
        if ch in "。？！；\n":
            if cur.strip():
                parts.append(cur.strip())
            cur = ""
    if cur.strip():
        parts.append(cur.strip())
    return parts


def shuffle_units(units, seed=SHUFFLE_SEED):
    """★ Fisher–Yates ＋ 固定种子（★ 只打乱清单、★ 集合不变 ★）★"""
    arr = list(units)
    rnd = random.Random(seed)
    for i in range(len(arr) - 1, 0, -1):
        j = rnd.randint(0, i)
        arr[i], arr[j] = arr[j], arr[i]
    return arr


def units_block(units):
    return "\n".join("%d. %s" % (i + 1, u) for i, u in enumerate(units))


def parse_json_obj(text):
    """★ 宽容 JSON 解析（★ 实测踩坑：★ 模型输出常带前言/尾注/代码围栏 ★）

    ★ 依次尝试：① 整段 json.loads ② 第一个 `{` 到最后一个 `}` 的切片
      ③ 从每个 `{` 起、到其后第一个 `}` 结束的候选
    ★ 返回 (obj, err)；★ obj 可能是 dict、也可能是 list（★ 裸数组也接受 ★）
    """
    if not text:
        return None, "empty_text"
    tries = []
    t = text.strip()
    tries.append(t)
    a = t.find("{")
    b = t.rfind("}")
    if a != -1 and b > a:
        tries.append(t[a:b + 1])
    a2 = t.find("[")
    b2 = t.rfind("]")
    if a2 != -1 and b2 > a2:
        tries.append(t[a2:b2 + 1])
    for cand in tries:
        try:
            obj = json.loads(cand)
        except Exception:                        # noqa: BLE001
            continue
        if isinstance(obj, (dict, list)):
            return obj, None
    return None, "json_parse_error"


def pick_items(obj, key):
    """★ 从解析结果里取条目数组（★ 兼容 {"ann":[...]} 与 裸 [...] ★）"""
    if isinstance(obj, dict):
        v = obj.get(key)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
        # ★ 兜底：找第一个 list 类型的值
        for vv in obj.values():
            if isinstance(vv, list) and vv and isinstance(vv[0], dict):
                return [x for x in vv if isinstance(x, dict)]
        return []
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    return []


def fmt_checklist(units, ann, probe, mode):
    """★ 把逐 token 标注/追问压成给汇总阶段的清单（★ 短、★ 只留判读相关 ★）★"""
    lines = []
    pm = {int(p.get("i", -1)): p for p in (probe or []) if isinstance(p, dict)}
    for a in (ann or []):
        if not isinstance(a, dict):
            continue
        i = int(a.get("i", -1))
        u = units[i - 1] if 0 < i <= len(units) else "?"
        seg = "%d. %s ｜ %s" % (i, u, a.get("role", "?"))
        if a.get("decisive"):
            seg += " ★可判定★"
        if a.get("gloss"):
            seg += " ｜ %s" % a["gloss"]
        if mode in ("probe",) and i in pm:
            p = pm[i]
            seg += "\n     规定：%s" % p.get("what", "")
            if p.get("trap") and p.get("trap") != "无":
                seg += " ｜ 易错：%s" % p["trap"]
        lines.append(seg)
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--devset", default=DEVSET_DEFAULT)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--tasks", default="")
    ap.add_argument("--run-id", default="tk-v1")
    ap.add_argument("--out-dir", default=OUT_DIR)
    ap.add_argument("--max-workers", type=int, default=3)
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()

    os.makedirs(a.out_dir, exist_ok=True)
    for sub in ("ann", "probe"):
        os.makedirs(os.path.join(a.out_dir, sub), exist_ok=True)
    ans_path = os.path.join(a.out_dir, "answers_%s.jsonl" % a.run_id)
    meta_path = os.path.join(a.out_dir, "meta_%s.json" % a.run_id)

    dev = json.load(open(a.devset, encoding="utf-8"))
    tasks = dev["tasks"]
    if a.tasks:
        keep = set(a.tasks.split(","))
        tasks = [t for t in tasks if t["task_id"] in keep]
    if a.smoke:
        tasks = tasks[:1]
        a.reps = 1
    arms = [x for x in a.arms.split(",") if x]
    dev_sha = hashlib.sha256(open(a.devset, "rb").read()).hexdigest()[:16]

    _rows.clear()
    if os.path.exists(ans_path):
        for line in open(ans_path, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    _rows.append(json.loads(line))
                except Exception:                # noqa: BLE001
                    pass
    seen = {(r["arm"], r["task_id"], r["rep"]): r for r in _rows}
    _rows[:] = list(seen.values())

    llm = LLM2(model="MiniMax-M3", temperature=1.0, max_tokens=12000)
    t0 = time.time()
    print("[run] %s dev_sha=%s tasks=%d reps=%d arms=%s" %
          (a.run_id, dev_sha, len(tasks), a.reps, arms), flush=True)

    def flush():
        atomic_write_jsonl(ans_path, _rows)

    def call(prompt, tag):
        txt, ok = llm.chat(prompt)
        return txt, ok

    # ★ 阶段1：★ 正常顺序（T1/T2/T4 共用）＋ 打乱顺序（T3）★ 落盘供复核与 R7 ★
    def stage_tag(tid, ask, rep, kind):
        """kind ∈ {tok, tok_shuf, sent}"""
        fp = os.path.join(a.out_dir, "ann", "%s_%s_rep%d.json" % (tid, kind, rep))
        if os.path.exists(fp):
            return json.load(open(fp, encoding="utf-8"))
        units = cut_tokens(ask) if kind.startswith("tok") else cut_sentences(ask)
        units = [u for u in units if u.strip()]
        if kind == "tok_shuf":
            units = shuffle_units(units)
        p = P_TAG.replace("{ask}", ask).replace("{units}", units_block(units))
        txt, ok = call(p, "tag")
        obj, err = (parse_json_obj(txt) if ok else (None, "call_failed"))
        ann = pick_items(obj, "ann") if obj is not None else []
        rec = {"task_id": tid, "rep": rep, "kind": kind, "units": units,
               "ann": ann, "ok": bool(ok and ann), "err": err, "raw": (txt or "")[:4000],
               "n_units": len(units), "n_ann": len(ann),
               "prompt_sha": sha(p), "ts": time.time()}
        tmp = fp + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=1)
        os.replace(tmp, fp)
        return rec

    def stage_probe(tid, ask, rep, kind):
        fp = os.path.join(a.out_dir, "probe", "%s_%s_rep%d.json" % (tid, kind, rep))
        if os.path.exists(fp):
            return json.load(open(fp, encoding="utf-8"))
        arec = stage_tag(tid, ask, rep, kind)
        ann = arec.get("ann") or []
        p = P_PROBE.replace("{ask}", ask).replace("{ann}", units_block(
            ["%d. %s ｜ %s ｜ decisive=%s" % (int(x.get("i", 0)), (arec["units"][int(x.get("i", 1)) - 1]
             if 0 < int(x.get("i", 0)) <= len(arec["units"]) else "?"), x.get("role", "?"),
             x.get("decisive")) for x in ann]))
        txt, ok = call(p, "probe")
        obj, err = (parse_json_obj(txt) if ok else (None, "call_failed"))
        probe = pick_items(obj, "probe") if obj is not None else []
        rec = {"task_id": tid, "rep": rep, "kind": kind, "probe": probe,
               "ok": bool(ok and probe), "err": err, "n_probe": len(probe),
               "raw": (txt or "")[:4000],
               "prompt_sha": sha(p), "ts": time.time()}
        tmp = fp + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=1)
        os.replace(tmp, fp)
        return rec

    def run_arm_unit(arm, task, rep):
        tid, ask = task["task_id"], task["ask"]
        stages = ARM_STAGES[arm]
        text = ""
        prompt = ""
        err = None
        units, ann, probe = [], [], []
        if "direct" in stages:
            prompt = P_DIRECT.replace("{ask}", ask)
            text, ok = call(prompt, "direct")
            if not ok:
                err = "call_failed_or_truncated"
        else:
            kind = {"tag": "tok", "tag_shuf": "tok_shuf", "tag_sent": "sent"}[stages[0]]
            arec = stage_tag(tid, ask, rep, kind)
            units, ann = arec.get("units", []), arec.get("ann", [])
            if not arec.get("ok"):
                err = "stage1_failed:%s" % arec.get("err")
            if "probe" in stages:
                prec = stage_probe(tid, ask, rep, kind)
                probe = prec.get("probe", [])
                if not prec.get("ok") and not err:
                    err = "stage2_failed:%s" % prec.get("err")
            mode = "probe" if "probe" in stages else "tag"
            checklist = fmt_checklist(units, ann, probe, mode)
            prompt = P_SUM.replace("{ask}", ask).replace("{checklist}", checklist)
            text, ok = call(prompt, "sum")
            if not ok and not err:
                err = "call_failed_or_truncated"
        bullets = [ln.strip() for ln in (text or "").splitlines() if ln.strip().startswith("-")]
        row = {"run_id": a.run_id, "arm": arm, "task_id": tid, "rep": rep, "route": 0,
               "model": "MiniMax-M3", "prompt_sha": sha(prompt), "prompt_len": len(prompt),
               "text": text or "", "n_chars": len(text or ""), "n_bullets": len(bullets),
               "ok": bool(text) and bool(bullets), "fail_reason": err, "ts": time.time()}
        with _lock:
            _rows.append(row)
            seen[(arm, tid, rep)] = row
        return row

    stop = {"flag": False}
    for rep in range(1, a.reps + 1):
        if stop["flag"]:
            break
        for arm in arms:
            if stop["flag"]:
                break
            for task in tasks:
                if stop["flag"]:
                    break
                tid = task["task_id"]
                if (arm, tid, rep) in seen:
                    continue
                try:
                    run_arm_unit(arm, task, rep)
                except QuotaExhausted:
                    print("[QUOTA] 2056 用量上限 ⇒ 立即停", flush=True)
                    stop["flag"] = True
                    break
                flush()
                print("[%6.1fs] %s %s rep%d | rows=%d fails=%d" %
                      (time.time() - t0, arm, tid, rep, len(_rows), llm.failures), flush=True)
        flush()
        st = llm.stats()
        meta = {"run_id": a.run_id, "dev_sha": dev_sha, "reps": a.reps, "arms": arms,
                "n_tasks": len(tasks), "shuffle_seed": SHUFFLE_SEED,
                "arm_stages": ARM_STAGES,
                "channel": {"model": "MiniMax-M3", "thinking": "disabled",
                            "max_tokens": 12000, "temperature": 1.0},
                "stats": st, "ts": time.time()}
        tmp = meta_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
        os.replace(tmp, meta_path)
        print("[rep %d] 完成 | calls=%d fails=%d usage=%s" %
              (rep, st["calls"], st["failures"], json.dumps(st["usage"], ensure_ascii=False)), flush=True)

    flush()
    print("[done] rows=%d elapsed=%.1fs" % (len(_rows), time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
