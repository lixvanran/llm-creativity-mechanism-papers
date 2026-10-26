# -*- coding: utf-8 -*-
"""judge_dims.py —— 独立判定器（★ 与生成器分离 ★）

★ 判据：★ 第一维度 = 答案中【最早出现】的维度标签（★ 不是「提到没提到」★）
★ 报出：首维分布 / 非默认维度命中率 / 维度数分布 / 跨域率 / 未识别实体
"""
import collections, glob, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import dimtax   # noqa: E402

def load():
    fs = sorted(glob.glob(os.path.join(HERE, "runs", "direct_n*.jsonl")))
    rows = []
    for f in fs:
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def main():
    rows = load()
    ok = [r for r in rows if r.get("ok")]
    bad = [r for r in rows if not r.get("ok")]
    print("═══ 通道 ═══")
    mf = sorted(glob.glob(os.path.join(HERE, "runs", "*.meta.json")))
    if mf:
        m = json.load(open(mf[-1], encoding="utf-8"))
        print("  模型=%s 温度=%s 思考档=%s 上限=%s" % (
            m["model"], m["temperature"], m["reasoning_effort"], m["max_tokens"]))
        print("  用量:", json.dumps(m["stats"]["usage"], ensure_ascii=False),
              "调用失败:", m["stats"]["failures"])
    print("  样本 %d 条（有效 %d / 失败 %d）" % (len(rows), len(ok), len(bad)))
    if not ok:
        print("  ★ 无有效样本 ⇒ 读数不生效"); return 1

    first = collections.Counter(); ment = collections.Counter(); nd = collections.Counter()
    off = 0; nondefault = 0; ent_all = collections.Counter(); susp_all = collections.Counter()
    a_c = collections.Counter(); b_c = collections.Counter(); disagree = 0
    for r in ok:
        t = r["text"]
        order = dimtax.mentioned(t)
        fa, fb, same = dimtax.first_dims(t)
        a_c[fa or "D0_none"] += 1
        b_c[fb or "D0_none"] += 1
        if not same:
            disagree += 1
        fd = fa or "D0_none"
        first[fd] += 1
        ment[len(order)] += 1
        if fd not in ("D1", "D0_none"):
            nondefault += 1
        if dimtax.offdomain_hits(t):
            off += 1
        real, susp = dimtax.entities(t)
        for e in real:
            ent_all[e] += 1
        for e in susp:
            susp_all[e] += 1
    print("\n═══ 机器口径A 的「第一维度分布」"
          "（★ ⚠ 该口径一致率 70% ⇒ 【不可直接引用】★ 仅作对照 ★）═══")
    for k, v in first.most_common():
        name = next((n for c, n, _d, _k in dimtax.CANDIDATE_DIMS if c == k), "（未命中任何维度）")
        print("  %-8s %2d/%2d  %5.1f%%   %s" % (k, v, len(ok), 100.0 * v / len(ok), name))
    print("\n═══ 口径B（★ 第一个小节标题内 ★）═══")
    for k, v in b_c.most_common():
        print("  %-8s %2d/%2d  %5.1f%%" % (k, v, len(ok), 100.0 * v / len(ok)))
    print("  ★ 两口径分歧: %d/%d = %.1f%%（★ 分歧高 ⇒ 该批读数不可直接引用 ★）"
          % (disagree, len(ok), 100.0 * disagree / len(ok)))
    # ★★★ ★★ 塌缩的【主指标】：非默认维度的【缺席率】 ★★ ★★★
    # ★ 理由（★ 本轮实测逼出来的 ★）：★ 「首维集中度」测的是【答案怎么组织】、
    #   不是【想得全不全】⇒ 首维人工标注几乎三等分（D4 37/D1 33/D5 30）
    #   ⇒ 而【缺席率】直接测"非默认维度有没有进候选集"★ 且纯机械、★ 无需判首维 ★
    cov = collections.Counter(); per = []
    for r in ok:
        m = set(dimtax.mentioned(r["text"])); per.append(m); cov.update(m)
    print("\n═══ ★★★ 塌缩主指标：维度覆盖率（★ 缺席率 = 1 − 覆盖率 ★）★★★ ═══")
    print("  %-4s %-8s %-10s %-10s %s" % ("代码", "覆盖率", "缺席率", "绝对分母", "维度"))
    for c, nm, _d, _k in dimtax.CANDIDATE_DIMS:
        c1, c2 = cov[c], len(ok)
        print("  %-4s %3d/%-3d  %5.1f%%  %9.1f%%  %s"
              % (c, c1, c2, 100.0 * c1 / c2, 100.0 * (c2 - c1) / c2, nm))
    union = set().union(*per) if per else set()
    print("  ★ 30 条并集覆盖 %d/%d 个候选维度" % (len(union), len(dimtax.CANDIDATE_DIMS)))
    print("  ★ 从未出现的维度: %s"
          % ([c for c, _n, _d, _k in dimtax.CANDIDATE_DIMS if cov[c] == 0] or "无"))
    print("  ★ 单条覆盖维度数: 均值 %.1f  范围 %d–%d"
          % (sum(len(x) for x in per) / len(per), min(len(x) for x in per), max(len(x) for x in per)))

    # ★ 判据自身可靠性：★ 机器口径 vs 人工锚（★ 一致率 < 0.8 ⇒ 该口径不可用 ★）
    hp = os.path.join(HERE, "human_labels.json")
    if os.path.exists(hp):
        H = json.load(open(hp, encoding="utf-8"))["labels"]
        agree = collections.Counter(); tot = 0
        for r in ok:
            key = str(r["i"])
            if key not in H:
                continue
            tot += 1
            t = r["text"]
            for name, pred in (("A(开头400字)", dimtax.first_dim_head(t)),
                               ("C(结论段)", dimtax.first_dim_concl(t)),
                               ("B(小节标题)", dimtax.first_dim_section(t))):
                if pred == H[key]:
                    agree[name] += 1
        print("\n═══ 判据可靠性：机器口径 vs 人工锚（★ n=%d ★）═══" % tot)
        for name in ("A(开头400字)", "C(结论段)", "B(小节标题)"):
            a = agree[name]
            print("  %-14s 一致 %2d/%2d = %3.0f%%  %s"
                  % (name, a, tot, 100.0 * a / tot,
                     "★ 可用" if tot and a / tot >= 0.8 else "★ 不可用（★ < 80% ★）"))
        hc = collections.Counter(H[str(r["i"])] for r in ok if str(r["i"]) in H)
        print("  ── 人工首维分布（★ 「首维集中度」不是塌缩指标 ★）──")
        for k, v in hc.most_common():
            nm = next((n for c, n, _d, _k in dimtax.CANDIDATE_DIMS if c == k), k)
            print("     %-4s %2d/%d = %5.1f%%  %s" % (k, v, tot, 100.0 * v / tot, nm))
    print("\n═══ 关键判据 ═══")
    print("  首维=非默认(D1以外): %d/%d = %.1f%%" % (nondefault, len(ok), 100.0 * nondefault / len(ok)))
    print("  含跨域分支(去大厂等): %d/%d = %.1f%%" % (off, len(ok), 100.0 * off / len(ok)))
    print("  提到的维度数分布: " + ", ".join("%d维:%d" % (k, v) for k, v in sorted(ment.items())))
    print("\n═══ 出现最多的校名类实体（前 25）═══")
    for e, c in ent_all.most_common(25):
        print("  %3d  %s" % (c, e))
    print("\n═══ 库外「校名」片段（★ 幻觉嫌疑、★ 只作嫌疑不断言 ★）═══")
    if susp_all:
        for e, c in susp_all.most_common(20):
            print("  %3d  %s" % (c, e))
    else:
        print("  （无）★ 注意：★ 「0 命中」既可能是真无幻觉、★ 也可能是剥离过度 ⇒ 不作结论 ★")
    print("\n═══ 抽样人工核（★ 判据自证：★ 肉眼看首 120 字是否与机器判的【首维】一致 ★）═══")
    for r in ok[:6]:
        fd = dimtax.first_dim(r["text"]) or "D0_none"
        head = re.sub(r"\s+", " ", r["text"][:120])
        print("  [%2d] 机器判首维=%-8s | %s..." % (r["i"], fd, head))
    return 0

if __name__ == "__main__":
    sys.exit(main())
