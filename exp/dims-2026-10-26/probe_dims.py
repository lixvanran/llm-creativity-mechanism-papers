# -*- coding: utf-8 -*-
"""probe_dims.py —— 测「裸模型第一步想到哪个有效维度」

★ 纪律：★ 【金标不进提示词】★ 只发原问题、★ 不给任何维度提示、★ 不加 system ⇒ 测的是【裸模型】
★ 通道参数全部显式记录（★ 模型/温度/思考档位/上限/用量 ★）
★ 失败可计数、★ 不静默归零
"""
import json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "l0")))
from llm import LLM, atomic_write_jsonl   # noqa: E402

QUESTION = "湖北物理类620分，想学AI，怎么选择大学？"
N = int(os.environ.get("N", "30"))
OUT = os.path.join(HERE, "runs", "direct_n%d.jsonl" % N)

def main():
    llm = LLM(model=os.environ.get("MODEL", "MiniMax-M2.5"),
              temperature=float(os.environ.get("TEMP", "1.0")),
              max_tokens=int(os.environ.get("MAXTOK", "6000")),
              reasoning_effort=os.environ.get("EFFORT", "medium"))
    rows = []
    for i in range(N):
        t0 = time.time()
        text, ok = llm.chat(QUESTION)
        rows.append({"i": i, "ok": ok, "text": text, "chars": len(text),
                     "sec": round(time.time() - t0, 1)})
        print("  [%2d/%d] ok=%s chars=%5d %.1fs" % (i + 1, N, ok, len(text), time.time() - t0), flush=True)
        atomic_write_jsonl(OUT, rows)          # ★ 增量落盘（★ 沙箱会杀长跑 ★）
    st = llm.stats()
    meta = {"question": QUESTION, "n": N, "model": llm.model,
            "temperature": llm.temperature, "max_tokens": llm.max_tokens,
            "reasoning_effort": llm.reasoning_effort, "stats": st}
    with open(os.path.join(HERE, "runs", "direct_n%d.meta.json" % N), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("通道统计:", json.dumps(st["usage"], ensure_ascii=False), "失败:", st["failures"])

if __name__ == "__main__":
    main()
