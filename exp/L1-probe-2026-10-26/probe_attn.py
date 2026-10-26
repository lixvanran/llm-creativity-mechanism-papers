# -*- coding: utf-8 -*-
"""probe_attn.py —— 层1 注意力探针（★ 第 1 章「源于注意力机制」的唯一内部量仪器 ★）

★★★ 为什么必须做这个 ★★★
「§1.3 其源于 transformer 的注意力机制」在【应用层不可测】⇒
只有内部量能判它 ⇒ 探针不是可选的尺子、★ 是该主张的【唯一】仪器。
★ 前作已判决：★ 层1 归因因【无 attention/logits 数据】而被判「不成立」
   ⇒ 本脚本就是去把那批数据【造出来】★

★★★ 测什么（★ 三个量 + 一条曲线 ★）★★★
1. 注意力熵 per head       ⇒ 高=未聚焦 / 低=已聚焦
2. 头间冗余（两两余弦）    ⇒ ★ 多个头坍缩成同一个 ⇒ 「注意力塌缩」的直接指标 ★
3. 有效秩（谱）            ⇒ 注意力矩阵降秩 ⇒ 闭合
4. 生成步上的闭合曲线       ⇒ 闭合【发生得多早】★ 塌缩的时间维度 ★

★★★ 对照臂（★ 用户方法论①的三个干预 ★）★★★
  direct   : 裸问题
  scatter : ★ 强行分散注意力（要求同时考虑多个互不相同角度）★
  token   : ★ 强制逐 token 聚焦（要求逐词分析提示词每个词的作用）★
  assoc   : ★ 联想（要求先列联想词再作答）★
★ 注意：★ 干预提示词【不给维度】⇒ 不构成金标泄漏 ★
"""
import json, math, os, sys, time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_DIR = os.environ.get("PROBE_MODEL", "Qwen/Qwen3-0.6B")
OUT = os.environ.get("PROBE_OUT", "runs/attn_probe.jsonl")
DEVICE = "cpu"
# ★ 实测：★ float32 加载 1.5GB 权重 ⇒ 内存峰值翻倍 ⇒ 退出码 137（OOM 被 cgroup 杀）★★
#   ⇒ 改 bfloat16 + low_cpu_mem_usage（★ 避免双份拷贝 ★）
DTYPE = torch.bfloat16


# ---------- 注意力度量 ----------
def attn_entropy(att):
    """★ att: [heads, q, k] ⇒ 每头注意力分布的熵（★ 自然对数 ★）⇒ 均值 """
    p = att.float().softmax(-1)
    h = -(p * (p + 1e-12).log()).sum(-1)     # [heads, q]
    return h.mean(-1).tolist()               # per head


def head_redundancy(att):
    """★ 头间冗余：★ 同层内各头注意力模式（对 k 维平均后归一）的平均两两余弦 ★"""
    m = att.float().mean(1)                 # [q, k] 头平均
    m = m / (m.norm(dim=-1, keepdim=True) + 1e-9)
    sim = m @ m.t()
    n = sim.shape[0]
    off = sim[~torch.eye(n, dtype=torch.bool)]
    return float(off.mean()) if off.numel() else float("nan")


def eff_rank(att):
    """★ 头平均注意力矩阵的【有效秩】（★ 谱熵的指数 ★）⇒ 降秩=闭合 ★"""
    m = att.float().mean(1)                 # [q, k]
    s = torch.linalg.svdvals(m)
    p = s / (s.sum() + 1e-12)
    p = p[p > 1e-12]
    return float(torch.exp(-(p * p.log()).sum()))


# ---------- 提示词 ----------
# ★★★ ★★ 混淆变量警告 ★★ ★★★
#   ★ 首版实测：★ direct 的 prompt 只有 16 token、干预臂 35 token ⇒
#   ★ 熵与有效秩都【随序列长度变化】⇒ 那个 2.74 vs 3.54 的差距
#   ★ 【极可能是长度效应、而不是干预效应】⇒ 首版读数【作废】★★
#   ⇒ 落法：★ 四臂【补齐到同一 token 数】、★ 且【用同一个填充串】★★
#   ⇒ 补齐串放在【末尾】（★ 因果注意力 ⇒ 末尾 token 对前面 query 的影响最小 ★）

FILLER = "请结合以上信息作答，并说明理由。"


def build_prompts():
    q = "湖北物理类620分，想学AI，怎么选择大学？"
    return {
        "direct": q,
        "scatter": q + "\n请同时从多个互不相同的方面考虑，先列出这些方面再逐个展开。",
        "token": q + "\n请先逐词分析本问题中每个词分别起什么作用，再基于分析作答。",
        "assoc": q + "\n请先列出与本问题相关的联想词与联想方向，再从这些联想出发作答。",
    }


def align_length(tok, prompts, target=None):
    """★ 把各臂补齐到【同一 token 数】⇒ 消除长度混淆 ★
    ★ 补齐用【同一个填充串】⇒ 四臂的背景完全相同、★ 只有指令不同 ★"""
    encs = {k: tok(v, add_special_tokens=False)["input_ids"] for k, v in prompts.items()}
    L = target or max(len(v) for v in encs.values())
    fill = tok(FILLER, add_special_tokens=False)["input_ids"]
    out = {}
    for k, ids in encs.items():
        if len(ids) < L:
            need = L - len(ids)
            i = 0
            while need > 0:
                take = min(need, len(fill))
                ids = ids + fill[:take]
                need -= take
                i += 1
        out[k] = ids[:L]
    assert len({len(v) for v in out.values()}) == 1, "补齐失败：长度不齐"
    return out


def main():
    os.makedirs("runs", exist_ok=True)
    tok = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_DIR, dtype=DTYPE, attn_implementation="eager",
        low_cpu_mem_usage=True).to(DEVICE).eval()
    print("模型加载完成:", MODEL_DIR, "| 层数:", model.config.num_hidden_layers,
          "| 头数:", model.config.num_attention_heads, flush=True)

    QUESTIONS = [
        "湖北物理类620分，想学AI，怎么选择大学？",
        "一个研究生想找导师做LLM推理加速，应该怎么筛？",
        "给高中生做AI通识课，第一课应该讲什么？",
    ]
    rows = []
    for qi, qtext in enumerate(QUESTIONS):
      prompts = build_prompts()
      prompts = {k: v.replace(QUESTIONS[0], qtext) for k, v in prompts.items()}
      aligned = align_length(tok, prompts)
      for arm in prompts:
        t0 = time.time()
        # ★ tokenizer 5.x 不接受 token-id 列表 ⇒ 直接造 tensors（★ 四臂同样处理 ★）
        ids = aligned[arm]
        enc = {"input_ids": torch.tensor([ids], dtype=torch.long),
               "attention_mask": torch.ones(1, len(ids), dtype=torch.long)}
        with torch.no_grad():
            out = model(**enc, output_attentions=True, use_cache=False)
        atts = out.attentions                     # tuple[layer] = [1, heads, q, k]
        n_layers = len(atts)
        per_layer = []
        for li, a in enumerate(atts):
            a = a[0]                              # [heads, q, k]
            per_layer.append({
                "layer": li,
                "entropy_per_head": [round(x, 4) for x in attn_entropy(a)],
                "entropy_mean": round(sum(attn_entropy(a)) / len(attn_entropy(a)), 4),
                "head_redundancy": round(head_redundancy(a), 4),
                "eff_rank": round(eff_rank(a), 4),
            })
        n_tok = int(enc["input_ids"].shape[1])
        row = {"arm": arm, "n_prompt_tokens": n_tok,
               "n_layers": n_layers,
               "sec": round(time.time() - t0, 1),
               "per_layer": per_layer}
        row["q_idx"] = qi
        rows.append(row)
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print("  q%d arm=%-8s tok=%4d  %.1fs  L0熵=%.3f 冗余=%.3f 秩=%.1f" % (
            qi, arm, n_tok, row["sec"],
            per_layer[0]["entropy_mean"], per_layer[0]["head_redundancy"],
            per_layer[0]["eff_rank"]), flush=True)

    # ★ 摘要表
    print("\n═══ 摘要：★ 逐层 三量（★ arm 对比、★ 按题平均 ★）═══")
    print("  %-8s %-6s %-8s %-10s %-8s" % ("arm", "layer", "熵", "头间冗余", "有效秩"))
    import collections
    agg = collections.defaultdict(list)
    for r in rows:
        for pl in r["per_layer"]:
            agg[(r["arm"], pl["layer"])].append(
                (pl["entropy_mean"], pl["head_redundancy"], pl["eff_rank"]))
    for arm in ("direct", "scatter", "token", "assoc"):
        for L in (0, 2, 5, 9, 13, 20, 27):
            v = agg.get((arm, L))
            if not v:
                continue
            n = len(v)
            print("  %-8s L%-5d %-8.3f %-10.3f %-8.1f   (n=%d 题)"
                  % (arm, L, sum(x[0] for x in v) / n,
                     sum(x[1] for x in v) / n, sum(x[2] for x in v) / n, n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
