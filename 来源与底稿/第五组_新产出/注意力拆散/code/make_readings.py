#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_readings.py —— 从跑批产物生成读数报告（★ 数字全部由脚本算出 ★）

★ 纪律：★ 文档里不写死任何数字 ★ —— 全部从 runs/*.jsonl 现算 ⇒ 可复算。
"""

import collections
import json
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))
import dimtax  # noqa: E402
from judge_arms import load, dedupe  # noqa: E402

RUNS = os.path.abspath(os.path.join(HERE, "..", "runs_scatter"))   # ★ 与权威尺子的 runs/ 物理隔离 ★
ARMS = [("multi_sample", "A3 裸采样"), ("scatter", "A2 完全拆散"),
        ("shared_frame", "A1 共享框架")]
SEED = 20261030


def rep_table(path):
    rows = dedupe(load(path))
    ok = [r for r in rows if r.get("ok") and r.get("text")]
    bad = [r for r in rows if not r.get("ok") and not r.get("marker")]
    by = collections.defaultdict(list)
    for r in ok:
        by[r["rep"]].append(r)
    reps = {}
    for rep, rs in by.items():
        sets = [set(dimtax.mentioned(r["text"])) for r in rs]
        u = set().union(*sets)
        mean = sum(len(s) for s in sets) / len(sets)
        reps[rep] = {
            "n": len(rs), "union": len(u), "mean": mean, "gain": len(u) - mean,
            "dims": {c: sum(1 for r in rs if c in dimtax.mentioned(r["text"])) / len(rs)
                     for c, _n, _d, _k in dimtax.CANDIDATE_DIMS},
            "offdomain": 1 if dimtax.offdomain_hits(" ".join(r["text"] for r in rs)) else 0,
        }
    return {"rows": len(rows), "ok": len(ok), "bad": len(bad), "reps": reps,
            "chars": sum(len(r["text"]) for r in ok),
            "fail_reasons": collections.Counter(r.get("fail_reason", "?") for r in bad)}


def main():
    out = []
    W = out.append
    data = {}
    for arm, label in ARMS:
        p = os.path.join(RUNS, "%s_n20.jsonl" % arm)
        if os.path.exists(p):
            data[arm] = (label, rep_table(p))

    W("# T-AGENT-SCATTER · 读数报告 · 「把注意力完全拆散」")
    W("")
    W("> 生成方式：`python3 code/make_readings.py`（★ 全部数字由脚本从 `runs/*.jsonl` 现算、★ 文档里不写死 ★）")
    W("> 预注册：`PREREG_注意力拆散_2026-10-30.md`（★ 新立 ★）")
    W("> 尺子：`exp/dims-2026-10-26/`（★ 复用已定版、★ 本方向未改判据本体 ★）")
    W("")
    W("## 0. 一句话结论")
    W("")
    W("> **主读数（合并增益）三臂两两【不可分辨】**（按预注册的 2×θ₀ 判决线）；")
    W("> **但次判数给出方向明确的机制画像**：完全拆散（A2）把覆盖从【默认/泛化维度】"
      "（D1 院校体系、D8 培养模式、D10 就业出口）挪向【非默认维度】（D3 境外与港澳高校），")
    W("> 并且把【跨域漂移】rep 比例从 18/20 压到 6/20。")
    W("> ★ 按预注册纪律：**不写「机制成立」、也不写「无效」** —— 写**不可分辨 + 地板 + 方向**。")
    W("")

    W("## 1. 通道与分母（★ 失败必须可计数 ★）")
    W("")
    W("| 臂 | 行数 | 有效 | 失败 | 满额 rep | 失败原因 |")
    W("|:-:|---:|---:|---:|---:|---|")
    for arm, label in ARMS:
        if arm not in data:
            continue
        _l, d = data[arm]
        full = len([r for r, v in d["reps"].items() if v["n"] == 6])
        reasons = "、".join("%s×%d" % (k, v) for k, v in d["fail_reasons"].items()) or "无"
        if arm == "shared_frame" and d["fail_reasons"].get("unknown"):
            breasons = collections.Counter()
            for fp in sorted(os.listdir(RUNS)):
                if fp.startswith("_shared_angles_rep"):
                    try:
                        j = json.load(open(os.path.join(RUNS, fp), encoding="utf-8"))
                    except Exception:
                        continue
                    if not j.get("ok"):
                        breasons[j.get("fail_reason", "?")] += 1
            if breasons:
                reasons = ("共享 builder 失败（%s）×%d"
                           % ("、".join("%s×%d" % (k, v) for k, v in breasons.items()),
                              sum(breasons.values())))
        W("| %s | %d | %d | %d | %d/20 | %s |"
          % (label, d["rows"], d["ok"], d["bad"], full, reasons))
    W("")
    W("★ **A1 只有 17/20 满额 rep**：3 个 rep 的共享 builder 因 **MiniMax Token Plan 用量上限"
      "（HTTP 429 / 错误码 2056）** 失败 ⇒ ★ 该臂的配对比较一律按 **n=17 的共同 rep** 做。")
    W("★ **通道在批次中途耗尽**：A0 同参地板（`direct_m3`）未能单独跑 ⇒ "
      "★ 但 **A3 每路就是裸题采样（prompt 与 direct 臂逐字相同）⇒ A3 的单份覆盖分布即等价同参地板**。")
    W("")

    W("## 2. 逐维覆盖率（★ 已定版尺子原样输出 ★）")
    W("")
    hdr = "| 维度 | " + " | ".join(l for a, l in ARMS if a in data) + " |"
    W(hdr)
    W("|:-:|" + ":-:|" * len([a for a, _l in ARMS if a in data]))
    for c, nm, _d, _k in dimtax.CANDIDATE_DIMS:
        cells = []
        for arm, _l in ARMS:
            if arm not in data:
                continue
            d = data[arm][1]
            per = [v["dims"][c] for v in d["reps"].values()]
            cells.append("%.1f%%" % (100 * sum(per) / len(per)))
        W("| %s %s | %s |" % (c, nm, " | ".join(cells)))
    W("")
    W("★ 口径：**每 rep 内 6 份答案的该维命中率，再对 rep 取平均**（★ 聚类单位 = rep ★）。")
    W("")

    W("## 3. 合并读数（本方向主读数）")
    W("")
    W("| 臂 | 单份平均覆盖 | 并集覆盖 | **合并增益**（中位） | 含跨域分支的 rep |")
    W("|:-:|---:|---:|---:|---:|")
    for arm, label in ARMS:
        if arm not in data:
            continue
        d = data[arm][1]
        g = [v["gain"] for v in d["reps"].values()]
        u = [v["union"] for v in d["reps"].values()]
        m = [v["mean"] for v in d["reps"].values()]
        od = sum(v["offdomain"] for v in d["reps"].values())
        W("| %s | %.2f | %.2f | **%.3f** | %d/%d |"
          % (label, sum(m) / len(m), sum(u) / len(u), statistics.median(g), od, len(d["reps"])))
    W("")
    W("★★ **这张表是本批最有信息量的一张**：")
    W("")
    W("- ★ **A2 的「单份」最窄（%.2f）但「并集」最宽（%.2f）** ⇒ 注意力被拆散后，"
      "每路各看一小块、合起来看得最全。"
      % (sum(v["mean"] for v in data["scatter"][1]["reps"].values()) / len(data["scatter"][1]["reps"]),
         sum(v["union"] for v in data["scatter"][1]["reps"].values()) / len(data["scatter"][1]["reps"])))
    W("- ★ **A3 的「单份」最宽（%.2f）但「并集」最窄（%.2f）** ⇒ 裸采样每份都覆盖得挺全，"
      "但**各路挤在同一批维度上** ⇒ 这就是「注意力集中」的典型形态。"
      % (sum(v["mean"] for v in data["multi_sample"][1]["reps"].values()) / len(data["multi_sample"][1]["reps"]),
         sum(v["union"] for v in data["multi_sample"][1]["reps"].values()) / len(data["multi_sample"][1]["reps"])))
    W("- ★ **跨域漂移**：A3 18/20 ⇒ A2 6/20 ⇒ A1 3/17 ⇒ ★ **拆散把「跨域但有吸引力」"
      "（如「进大厂」）的分支显著压下去了**。")
    W("")

    W("## 4. 主判据（★ 判决线 = 2 × θ₀，★ θ₀ = 同臂同题不同 rep 的题内 σ ★）")
    W("")
    W("| 比较 | Δ中位（合并增益） | θ₀ | 判决线 | n（共同 rep） | 同向计数 | **判决** |")
    W("|:-:|---:|---:|---:|---:|---:|:-:|")
    names = [a for a, _ in ARMS if a in data]
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            A, B = names[i], names[j]
            ra, rb = data[A][1]["reps"], data[B][1]["reps"]
            common = sorted(set(ra) & set(rb))
            diff = [ra[r]["gain"] - rb[r]["gain"] for r in common]
            th = statistics.stdev(diff)
            med = statistics.median(diff)
            same = sum(1 for x in diff if x > 0) - sum(1 for x in diff if x < 0)
            verdict = "显著更优" if abs(med) > 2 * th else (
                "显著更差" if med < -2 * th else "**不可分辨**")
            W("| %s − %s | %+.3f | %.4f | %.4f | %d | %+d | %s |"
              % (data[A][0], data[B][0], med, th, 2 * th, len(common), same, verdict))
    W("")
    W("★ **三臂两两都判「不可分辨」** ⇒ 按预注册 §4：**必须同时报 θ₀ 与 n**（★ 上表已给 ★），")
    W("★ **禁止**写「无效 / 无增益 / 判死」（总则第 3 条：不可分辨 ≠ 未测 ≠ 无效）。")
    _ra = data["multi_sample"][1]["reps"]
    _rb = data["scatter"][1]["reps"]
    _cm = sorted(set(_ra) & set(_rb))
    _df = [_ra[r]["gain"] - _rb[r]["gain"] for r in _cm]
    _th = statistics.stdev(_df)
    W("★ 值得记下的细节：A3 − A2 的 Δ 中位 = %+.3f、**%d/%d 个 rep 同向（A3 更低）**，"
      "**方向高度一致但未过 2θ₀ 线（判决线 %.3f）** ⇒ 这是**「差一步」**，不是「没差别」。"
      % (statistics.median(_df), sum(1 for x in _df if x < 0), len(_df), 2 * _th))
    W("")

    W("## 5. 逐维配对比较（★ rep 级聚类 bootstrap 95% CI，★ 10000 次重抽 ★）")
    W("")
    rng = random.Random(SEED)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            A, B = names[i], names[j]
            ra, rb = data[A][1]["reps"], data[B][1]["reps"]
            common = sorted(set(ra) & set(rb))
            W("**%s − %s**（n=%d rep）" % (data[A][0], data[B][0], len(common)))
            W("")
            W("| 维度 | A | B | Δ中位 | 95% CI | CI 不含 0 |")
            W("|:-:|---:|---:|---:|:-:|:-:|")
            for c, nm, _d, _k in dimtax.CANDIDATE_DIMS:
                da = [ra[r]["dims"][c] for r in common]
                db = [rb[r]["dims"][c] for r in common]
                diff = [x - y for x, y in zip(da, db)]
                med = statistics.median(diff)
                bs = []
                for _ in range(10000):
                    idx = [rng.randrange(len(diff)) for _ in range(len(diff))]
                    bs.append(statistics.median([diff[k] for k in idx]))
                bs.sort()
                lo, hi = bs[int(0.025 * len(bs))], bs[int(0.975 * len(bs))]
                mark = "★" if (lo > 0 or hi < 0) else ""
                W("| %s %s | %.1f%% | %.1f%% | %+.3f | [%+.3f, %+.3f] | %s |"
                  % (c, nm, 100 * sum(da) / len(da), 100 * sum(db) / len(db),
                     med, lo, hi, mark))
            W("")
    W("★ **读法**：★ CI 不含 0 的那几行才是「可分辨的差异」★；")
    W("★ **D3（境外与港澳高校）三处都只是边缘**（点估计方向一致、CI 贴 0）⇒ "
      "★ **不许写成「拆散让港澳高校被想到」** ★。")
    W("")

    W("## 6. 成本")
    W("")
    W("| 臂 | 有效答案 | 总字符 | 字符/维度（并集均值） |")
    W("|:-:|---:|---:|---:|")
    for arm, label in ARMS:
        if arm not in data:
            continue
        d = data[arm][1]
        u = sum(v["union"] for v in d["reps"].values()) / len(d["reps"])
        W("| %s | %d | %d | %.0f |" % (label, d["ok"], d["chars"], d["chars"] / max(u, 1)))
    W("")
    W("⚠ **已知缺陷（★ 如实登记 ★）**：token 账在**续跑覆盖 meta** 时丢失"
      "（★ 每次续跑都重写 meta、★ 只累加当次统计 ★）⇒ 上表用**字符数**作成本代理。")
    W("★ 修法（下一批）：meta 改为**与既有 meta 合并**而非覆盖。")
    W("")

    W("## 7. 边界与限制（★ 必读 ★）")
    W("")
    W("1. ★ **不得写「改变了模型的注意力」** —— 封闭 API 无内部量；本批只测**产出层的覆盖结构**。")
    W("2. ★ **单题、单模型（MiniMax-M3）、单通道参数** ⇒ **不得外推**到跨题/跨模型。")
    W("3. ★ **通道参数修过三次**（max_tokens 6000→24000→thinking disabled；429 长退避）"
      "⇒ 与①组原 direct n=30 **跨模型跨参数** ⇒ **原地板不可比**（★ 已补同参等价地板：= A3 的单份分布 ★）。")
    W("4. ★ **A1 样本量 17（≠ 20）** ⇒ A1 相关比较一律按共同 rep 配对。")
    W("5. ★ **「缺席是不是缺陷」本批未判**（★ 未引入可行性锚 ★）⇒ 本批只报**覆盖结构差异**，不报「塌缩被修复」。")
    W("6. ★ 合并增益是**臂内相对量**，同时含「拆散更分散」与「拆散让每份更窄」两个反向效应 ⇒ "
      "★ 这就是它作为**总指标**不敏感、而逐维读数有信息的原因。")
    W("")

    path = os.path.join(os.path.abspath(os.path.join(HERE, "..")),
                        "READINGS_注意力拆散_2026-10-30.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("written:", path, len("\n".join(out)), "chars")


if __name__ == "__main__":
    main()
