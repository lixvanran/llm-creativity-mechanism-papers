#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_scatter2.py —— T-AGENT-SCATTER-2 · 答题阶段（★ 五臂、★ N=4 路 ★）

★ 预注册：来源与底稿/第五组_新产出/注意力拆散/PREREG_拆散方式对照_2026-10-30.md（★ 含 v2 修订 ★）
★ 本文件实现预注册 §2 的五臂、§5 的样本量、§6 的失败口径、§8 的反自证清单 ★

★★ 底座提示词 P0 = 层3 `arm_direct` 的**逐字**拼法（★ `repro/src/run_dev.py:155` ＋ `repro/src/workflow.py:848` 的 `_OUT_SPEC` ★）
★★ ⇒ **判官（层3 的 measure.py）能直接解析这批输出**（★ 层3 自己的 B0_direct 就因为格式不合而 parsefail=1.0 ★）

★★ 五臂（★ 每臂之间只差一个变量 ★）：
  B0 single         1 份、prompt 逐字＝P0                      ★ 路径唯一版（T-L1-06 对照格）
  S1 parallel_sample 4 份、prompt 逐字＝P0                      ★ 唯一差别＝份数
  S2 self_angle     4 份、prompt ＝ P0 ＋ 各自 builder 造的角度   ★ 唯一差别＝角度来源（自选）
  S3 assigned_view  4 份、prompt ＝ P0 ＋ 指派的固定视角           ★ 唯一差别＝角度来源（指派）
  S4 hetero_model   4 份、prompt 逐字＝P0、★ 换模型身份 ★

★★ 纪律 ★★：
· 依据包 / 结论空间 / 金标 **一律不进提示词**（★ devset 规格 §3.5 ★）
· 落盘按 (arm, task, rep, route) 去重保留最后一行；★ 失败逐行带原因
· 额度上限（2056）⇒ 立即停、★ 不许换模型凑数
· 跑批顺序 ＝ rep 外层、arm 次层、★ ⇒ 任何时刻中断各臂完成度均衡
"""

import argparse
import hashlib
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm2 import LLM2, QuotaExhausted, atomic_write_jsonl  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), "runs_scatter2")
DEVSET_DEFAULT = "/workspace/work/devset/devset.json"

N_ROUTES = 4
VIEWS = ["事实与参数核对", "数值与量级计算", "条件、例外与时序", "主体资格与适用范围"]
MODELS_S4 = ["MiniMax-M3", "MiniMax-M2.7", "MiniMax-M2.5-highspeed", "MiniMax-M1"]

# ★★★ 层3 的 _OUT_SPEC（★ 逐字抄自 repro/src/workflow.py:848-852 ★）
_OUT_SPEC = ("【输出规格】\n"
             "- 只输出 3–6 条，每条一行，行首用「- 」\n"
             "- 每条必须**具体**：带一个数字 / 一个明确条件 / 一个可核查的判断\n"
             "- 不写开场白、不写总结、不写免责说明\n"
             "- 不超过 400 字")

# ★ 层3 `arm_direct` 的逐字拼法（run_dev.py:155）："问题：%s\n\n%s"
P0 = "问题：{ask}\n\n" + _OUT_SPEC

S2_TMPL = P0 + """

你负责的角度：{angle}
★ 只从这一个角度作答 ★。"""

S3_TMPL = P0 + """

你负责的检查视角：{view}
★ 只从这一个视角作答、★ 不要覆盖其它视角 ★。"""

BUILDER_TMPL = """问题：{ask}

请为这道题列出 {n} 个**互不相同**的切入面（视角），用来分工作答。
★ 每个切入面说的是"该从哪个方面检查或判断这题"，★ 例如"数值与量级是否算得通""适用条件有没有被搞错" ★
★ **不要**复述题面、★ **不要**解释术语、★ **不要**给答案 ★
★ 每个切入面一句话、★ 不超过 30 字 ★
★ 只输出 JSON：{{"angles": ["...", "...", "...", "..."]}}"""

ARMS = ["B0", "S1", "S2", "S3", "S4"]
ARM_ROUTES = {"B0": 1, "S1": N_ROUTES, "S2": N_ROUTES, "S3": N_ROUTES, "S4": N_ROUTES}

_lock = threading.Lock()
_rows = []


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def build_prompt(arm, ask, route, angles):
    if arm in ("B0", "S1", "S4"):
        p = P0.replace("{ask}", ask)
    elif arm == "S3":
        p = S3_TMPL.replace("{ask}", ask).replace("{view}", VIEWS[route])
    elif arm == "S2":
        ang = (angles or [])
        a = ang[route] if route < len(ang) else ""
        a = " ".join(str(a).split())[:120]
        p = S2_TMPL.replace("{ask}", ask).replace("{angle}", a)
    else:
        raise ValueError(arm)
    return p


def parse_angles(text):
    if not text:
        return [], "empty_text"
    blob = None
    for i in range(len(text) - 1, -1, -1):
        if text[i] == "{":
            cand = text[i:]
            if cand.rstrip().endswith("}"):
                blob = cand
                break
    if blob is None:
        return [], "no_json_block"
    try:
        obj = json.loads(blob)
    except Exception:                            # noqa: BLE001
        return [], "json_parse_error"
    if not isinstance(obj, dict):
        return [], "json_not_object"
    al = obj.get("angles")
    if not isinstance(al, list) or not al:
        return [], "angles_missing_or_empty"
    return [" ".join(str(x).split())[:120] for x in al if isinstance(x, str)], None


def model_for(arm, route):
    return MODELS_S4[route] if arm == "S4" else "MiniMax-M3"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--devset", default=DEVSET_DEFAULT)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--tasks", default="")
    ap.add_argument("--run-id", default="sc2-v1")
    ap.add_argument("--out-dir", default=OUT_DIR)
    ap.add_argument("--max-workers", type=int, default=4)
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()

    os.makedirs(a.out_dir, exist_ok=True)
    ans_path = os.path.join(a.out_dir, "answers_%s.jsonl" % a.run_id)
    ang_dir = os.path.join(a.out_dir, "angles")
    os.makedirs(ang_dir, exist_ok=True)
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
            if not line:
                continue
            try:
                _rows.append(json.loads(line))
            except Exception:                    # noqa: BLE001
                pass
    seen = {}
    for r in _rows:
        seen[(r["arm"], r["task_id"], r["rep"], r["route"])] = r
    _rows[:] = list(seen.values())

    def done(arm, tid, rep, route):
        return (arm, tid, rep, route) in seen

    llm = LLM2(model="MiniMax-M3", temperature=1.0, max_tokens=12000)
    t0 = time.time()
    print("[run] %s dev_sha=%s tasks=%d reps=%d arms=%s" %
          (a.run_id, dev_sha, len(tasks), a.reps, arms), flush=True)

    def do_builder(tid, ask, rep):
        fp = os.path.join(ang_dir, "%s_rep%d.json" % (tid, rep))
        if os.path.exists(fp):
            return json.load(open(fp, encoding="utf-8")).get("angles", [])
        p = BUILDER_TMPL.replace("{ask}", ask).replace("{n}", str(N_ROUTES))
        txt, ok = llm.chat(p)
        angles, err = parse_angles(txt) if ok else ([], "call_failed")
        rec = {"task_id": tid, "rep": rep, "angles": angles,
               "ok": bool(ok and angles), "err": err,
               "prompt_sha": sha(p), "ts": time.time()}
        tmp = fp + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=1)
        os.replace(tmp, fp)
        return angles

    def flush():
        atomic_write_jsonl(ans_path, _rows)

    def run_route(arm, task, rep, route, angles):
        tid, ask = task["task_id"], task["ask"]
        p = build_prompt(arm, ask, route, angles)
        row = {"run_id": a.run_id, "arm": arm, "task_id": tid, "rep": rep, "route": route,
               "model": model_for(arm, route), "prompt_sha": sha(p), "prompt_len": len(p),
               "text": "", "n_chars": 0, "ok": False, "fail_reason": None, "ts": time.time()}
        try:
            txt, ok = llm.chat(p, model=row["model"])
        except QuotaExhausted:
            row["fail_reason"] = "quota_exhausted_2056"
            with _lock:
                _rows.append(row)
                seen[(arm, tid, rep, route)] = row
            raise
        row["text"] = txt
        row["n_chars"] = len(txt)
        if not ok:
            row["fail_reason"] = "call_failed_or_truncated"
        else:
            # ★ 产出层健康度：条目行数（★ 层3 的判官就是从这些行抽断言 ★）
            lines = [ln.strip() for ln in txt.splitlines() if ln.strip().startswith("-")]
            row["n_bullets"] = len(lines)
            row["ok"] = bool(lines)
            row["fail_reason"] = None if lines else "no_bullet_lines"
        with _lock:
            _rows.append(row)
            seen[(arm, tid, rep, route)] = row
        return row

    stop = {"flag": False}
    for rep in range(1, a.reps + 1):
        if stop["flag"]:
            break
        if "S2" in arms:
            with ThreadPoolExecutor(max_workers=a.max_workers) as ex:
                list(ex.map(lambda t: do_builder(t["task_id"], t["ask"], rep), tasks))
        for arm in arms:
            if stop["flag"]:
                break
            for task in tasks:
                if stop["flag"]:
                    break
                tid = task["task_id"]
                need = [r for r in range(ARM_ROUTES[arm]) if not done(arm, tid, rep, r)]
                if not need:
                    continue
                angles = []
                if arm == "S2":
                    fp = os.path.join(ang_dir, "%s_rep%d.json" % (tid, rep))
                    if os.path.exists(fp):
                        angles = json.load(open(fp, encoding="utf-8")).get("angles", [])
                try:
                    if len(need) == 1:
                        run_route(arm, task, rep, need[0], angles)
                    else:
                        with ThreadPoolExecutor(max_workers=min(a.max_workers, len(need))) as ex:
                            list(ex.map(lambda r: run_route(arm, task, rep, r, angles), need))
                except QuotaExhausted:
                    print("[QUOTA] 2056 用量上限 ⇒ 立即停", flush=True)
                    stop["flag"] = True
                    break
                flush()
                print("[%6.1fs] %s %s rep%d | rows=%d fails=%d" %
                      (time.time() - t0, arm, tid, rep, len(_rows), llm.failures), flush=True)
        flush()
        st = llm.stats()
        meta = {"run_id": a.run_id, "dev_sha": dev_sha, "devset": a.devset,
                "reps": a.reps, "arms": arms, "n_tasks": len(tasks),
                "n_routes": N_ROUTES, "views": VIEWS, "models_s4": MODELS_S4,
                "prompt_p0_sha": sha(P0),
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
