#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T-L1-01 · 注意力层内部探针 · 核心库（prompt 构造 + 内部量抽取）

★ 三条硬要求（来自 PREREG_T-L1-01.md §4 与 派活总则 §一.5）：
  1. Qwen3 默认 thinking 必须关掉：enable_thinking=False 的真实实现 = assistant 段后接
     `<think>\n\n</think>\n\n` ⇒ 本库**手工拼 token id**（head ids + think ids 逐段拼接），
     **段边界按构造精确**，绝不用「整串分词再切」的近似。
  2. 生成的文本必须剥 <think>（落盘前剥），并抽样肉眼核。
  3. 采样参数固定：temperature=0.7 / top_p=0.95 / max_new_tokens=64。

★ 本批要算的四类内部量（详稿 §12.1 T-L1-01）：
  注意力熵 / 注意力秩 / logit 熵 / hidden state 探针（外加头间冗余度，供 H3 留痕）。
"""
import math
import numpy as np

# ---------------------------------------------------------------- 固定常量（事前定版）
MAX_PROMPT_TOKENS = 256      # prompt 上限 ⇒ prompt+生成 ≤ 320（预注册 §4「序列上限 320」）
MAX_NEW_TOKENS = 64
TEMPERATURE = 0.7
TOP_P = 0.95
RECENT_WINDOW = 8            # 「最近生成」窗口（token）
FAR_WINDOW = 64              # 「远距离」阈值（token）
EPS = 1e-12

SYSTEM_PROMPT = "你是一个严谨的知识判断助手。只输出结论，不要输出推理过程。"

THINK_BLOCK = "<think>\n\n</think>\n\n"


# ---------------------------------------------------------------- prompt 构造
def build_user_content(ask, concls, arm, budget_tokens):
    """两臂的题面文本。concls = [(id, text), ...]

    ★ 两臂的**指令完全相同**（"请作答。"）⇒ 两臂之差**只有「结论空间清单」在不在**这一处
      （执行时定的设计选择：预注册只固定了「A_bare=仅题面 / A_list=题面+清单」，没固定指令；
       指令统一 ⇒ 臂间差异不混着「任务措辞」这一混淆项）。
    """
    if arm == "A_bare":
        return "题面：%s\n\n请作答。" % ask
    if arm == "A_list":
        lines = ["题面：%s" % ask, "", "可选结论："]
        for cid, txt in concls:
            lines.append("- %s：%s" % (cid, txt))
        lines += ["", "请作答。"]
        return "\n".join(lines)
    raise ValueError("unknown arm: %r" % arm)


def truncate_to_tokens(tok, text, n):
    """按 token 数截断（确定性）。返回截断后的文本。

    ★ 截断后**回退到最后一个句读**（。！？；，、），且只有当该句读落在预算的 ≥50% 处才回退
      —— 理由：H6 的机制前提是「输入里有一份**可枚举清单**」⇒ 清单项应当是**完整可读的条目**，
      而不是半截句子；但回退必须**只缩短、绝不超预算**，且回退与否**完全由文本决定**（确定性）★。
    """
    ids = tok(text, add_special_tokens=False)["input_ids"]
    if len(ids) <= n:
        return text
    cut = tok.decode(ids[:n], skip_special_tokens=False)
    pos = max(cut.rfind(ch) for ch in "。！？；，、")
    if pos >= 0 and pos >= int(0.5 * len(cut)):
        cut = cut[:pos + 1]
    return cut


def ids_of(enc):
    """transformers 5.x 的 apply_chat_template(tokenize=True) 返回 BatchEncoding（不是裸 id 列表）⇒ 统一取法。"""
    if hasattr(enc, "get") and "input_ids" in enc:
        x = enc["input_ids"]
        return list(x[0]) if hasattr(x[0], "__len__") else list(x)
    return list(enc)


def build_prompt(tok, ask, concls, arm, max_prompt_tokens=MAX_PROMPT_TOKENS):
    """返回 dict：input_ids / head_len / think_len / spans / text。

    spans 以 **prompt 内的 token 下标** 给出：
      ask  = 题面段（两臂都有）
      lst  = 结论清单段（仅 A_list）
    ★ spans 用 offset mapping 精确求出 ⇒ 清单区域边界可核。
    """
    n = len(concls)
    budget = 40
    for _ in range(60):
        cut = [(cid, truncate_to_tokens(tok, txt, budget)) for cid, txt in concls] if arm == "A_list" else []
        user = build_user_content(ask, cut, arm, budget)
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]
        head_text = tok.apply_chat_template(
            msgs, tokenize=False, add_generation_prompt=True, enable_thinking=True)
        full_text = head_text + THINK_BLOCK
        enc = tok(full_text, add_special_tokens=False, return_offsets_mapping=True)
        ids = enc["input_ids"]
        if len(ids) <= max_prompt_tokens or budget <= 6:
            break
        budget -= 2

    # ★ 手工拼 token id：head 段（apply_chat_template 的 tokenize=True 结果）+ think 段（逐段单独分词）
    head_ids = ids_of(tok.apply_chat_template(
        msgs, tokenize=True, add_generation_prompt=True, enable_thinking=True))
    think_ids = tok(THINK_BLOCK, add_special_tokens=False)["input_ids"]
    input_ids = list(head_ids) + list(think_ids)

    # 自证 ①：构造出来的 ids 解码后必须与 full_text 逐字相等
    dec = tok.decode(input_ids, skip_special_tokens=False)
    assert dec == full_text, "prompt 自证失败：手工拼 id 的解码结果 != 目标文本"

    # 自证 ②：与模板 enable_thinking=False 的整串分词结果对比（允许边界差 1 个 token，但要记下来）
    ref_ids = ids_of(tok.apply_chat_template(
        msgs, tokenize=True, add_generation_prompt=True, enable_thinking=False))
    ref_text = tok.decode(ref_ids, skip_special_tokens=False)
    same_ids = (list(ref_ids) == input_ids)
    same_text = (ref_text == full_text)

    # spans：字符区间 → token 下标（offset mapping）
    off = enc["offset_mapping"]
    def span_of(sub):
        i = full_text.find(sub)
        if i < 0:
            return None
        j = i + len(sub)
        idx = [k for k, (a, b) in enumerate(off) if a < j and b > i]
        return [idx[0], idx[-1] + 1] if idx else None

    ask_sub = ask
    spans = {"ask": span_of(ask_sub)}
    if arm == "A_list":
        list_sub = "\n".join("- %s：%s" % (cid, txt) for cid, txt in cut)
        spans["list"] = span_of(list_sub)

    return {
        "input_ids": input_ids,
        "text": full_text,
        "head_len": len(head_ids),
        "think_len": len(think_ids),
        "think_ids": list(think_ids),
        "n_prompt": len(input_ids),
        "spans": spans,
        "trunc_budget_tokens": budget,
        "ref_ids_equal": bool(same_ids),
        "ref_text_equal": bool(same_text),
        "ref_len": len(ref_ids),
        "user_content": user,
    }


# ---------------------------------------------------------------- 剥 <think>
def strip_think(text):
    """剥掉残留的 <think>...</think>（总则 §一.5：落盘前剥）。返回 (clean, n_stripped)"""
    n = 0
    out = text
    while "<think>" in out or "</think>" in out:
        i = out.find("<think>")
        j = out.find("</think>")
        if i >= 0 and j >= 0 and j > i:
            out = out[:i] + out[j + len("</think>"):]
            n += 1
        else:
            # 孤立标签：直接去掉标签本身
            out = out.replace("<think>", "").replace("</think>", "")
            n += 1
    return out.strip(), n


# ---------------------------------------------------------------- 内部量抽取
def _ent(p):
    p = p[p > 0]
    return float(-(p * np.log(p)).sum())


def _row_stats(A, P, n_gen, spans):
    """A: [n_layers, n_heads, kv_len]（最后一行的注意力分布）→ 标量统计量字典。"""
    L, H, K = A.shape
    A = A.astype(np.float64)
    A = np.clip(A, 0.0, None)
    A = A / np.maximum(A.sum(axis=-1, keepdims=True), EPS)

    sink = A[..., 0]                                       # [L,H] attention sink
    p_nonsink = A[..., 1:P].sum(axis=-1)                   # prompt 非 sink 质量
    gen = A[..., P:P + n_gen].sum(axis=-1) if n_gen > 0 else np.zeros((L, H))
    m_ask = A[..., spans["ask"][0]:spans["ask"][1]].sum(axis=-1) if spans.get("ask") else np.zeros((L, H))
    m_lst = (A[..., spans["list"][0]:spans["list"][1]].sum(axis=-1)
             if spans.get("list") else None)

    n_recent = min(RECENT_WINDOW, n_gen)
    if n_gen > 0 and n_recent > 0:
        rec_lo = P + n_gen - n_recent
        m_recent = A[..., rec_lo:P + n_gen].sum(axis=-1)
    else:
        m_recent = np.zeros((L, H))
    n_older = n_gen - n_recent
    m_older = (A[..., P:P + n_older].sum(axis=-1) if n_older > 0 else np.zeros((L, H)))

    P2 = P // 2
    m_pe = A[..., 1:P2].sum(axis=-1) if P2 > 1 else np.zeros((L, H))
    m_pl = A[..., P2:P].sum(axis=-1) if P < P2 else np.zeros((L, H))

    # 远距离（> FAR_WINDOW 个 token 之前）——按“每 token 平均质量”归一
    dist = np.arange(K - 1, -1, -1)                       # 到 query 的距离
    far_mask = (dist > FAR_WINDOW)
    n_far = int(far_mask.sum())
    m_far = (A[..., far_mask].sum(axis=-1) / max(n_far, 1)) if n_far > 0 else np.zeros((L, H))
    n_loc = int((dist <= FAR_WINDOW).sum())
    m_loc = (A[..., ~far_mask].sum(axis=-1) / max(n_loc, 1))

    # 注意力熵（逐行）与其有效支撑宽度
    ent = np.zeros((L, H))
    for l in range(L):
        for h in range(H):
            ent[l, h] = _ent(A[l, h])
    supp = np.exp(ent)                                    # 有效注意力支撑宽度（等效 token 数）
    pr = 1.0 / np.maximum((A * A).sum(axis=-1), EPS)      # 注意力秩（participation ratio）

    # 头间冗余：同层不同头的注意力分布两两余弦相似度均值
    head_sim = np.zeros(L)
    for l in range(L):
        X = A[l]                                          # [H, K]
        nrm = np.linalg.norm(X, axis=1, keepdims=True)
        Xn = X / np.maximum(nrm, EPS)
        C = Xn @ Xn.T
        iu = np.triu_indices(H, 1)
        head_sim[l] = float(C[iu].mean()) if len(iu[0]) else float("nan")

    def m(x):
        return float(np.mean(x))

    out = {
        "attn_entropy": m(ent),
        "attn_supp": m(supp),
        "attn_rank_pr": m(pr),
        "attn_sink": m(sink),
        "attn_prompt_nonsink": m(p_nonsink),
        "attn_gen": m(gen),
        "attn_ask": m(m_ask),
        "attn_list": (m(m_lst) if m_lst is not None else None),
        "attn_recent": m(m_recent),
        "attn_older": m(m_older),
        "attn_prompt_early": m(m_pe),
        "attn_prompt_late": m(m_pl),
        "attn_far_norm": m(m_far),
        "attn_loc_norm": m(m_loc),
        "attn_meandist": m(np.tensordot(A, dist, axes=([2], [0]))),
        "head_attn_sim": m(head_sim),
        "attn_entropy_by_layer": [float(x) for x in ent.mean(axis=1)],
        "attn_gen_by_layer": [float(x) for x in gen.mean(axis=1)],
        "attn_list_by_layer": ([float(x) for x in m_lst.mean(axis=1)] if m_lst is not None else None),
    }
    # ---- 派生比值（事前定版的读数，见 PREREG-EXEC）
    n_gen_f = max(n_gen, 1)
    n_recent_f = max(n_recent, 1)
    n_older_f = max(n_older, 1)
    p_nonsink_per_tok = out["attn_prompt_nonsink"] / max(P - 1, 1)
    gen_per_tok = out["attn_gen"] / n_gen_f
    out["gen_odds"] = gen_per_tok / max(p_nonsink_per_tok, EPS)
    out["gen_recent_per_tok"] = out["attn_recent"] / n_recent_f
    out["gen_older_per_tok"] = out["attn_older"] / n_older_f
    out["h1_recency"] = out["gen_recent_per_tok"] - out["gen_older_per_tok"]
    out["prompt_early_per_tok"] = out["attn_prompt_early"] / max(P2 - 1, 1)
    out["prompt_late_per_tok"] = out["attn_prompt_late"] / max(P - P2, 1)
    out["h4_early_late"] = out["prompt_early_per_tok"] - out["prompt_late_per_tok"]
    if m_lst is not None:
        n_list = spans["list"][1] - spans["list"][0]
        n_ask = spans["ask"][1] - spans["ask"][0]
        out["list_per_tok"] = out["attn_list"] / max(n_list, 1)
        out["ask_per_tok"] = out["attn_ask"] / max(n_ask, 1)
        out["d6_list_minus_ask"] = out["list_per_tok"] - out["ask_per_tok"]
        out["list_share_of_prompt"] = out["attn_list"] / max(out["attn_list"] + out["attn_ask"], EPS)
    else:
        out["list_per_tok"] = None
        out["ask_per_tok"] = out["attn_ask"] / max(spans["ask"][1] - spans["ask"][0], 1)
        out["d6_list_minus_ask"] = None
        out["list_share_of_prompt"] = None

    # ★ 负对照（placebo）：题面段自身的前半 vs 后半的「每 token 质量」差
    #   —— 清单在题面**之后** ⇒ 位置近因会让清单天然多拿注意力 ⇒ 必须用这个「同内容、不同位置」
    #   的对照把「位置梯度」剥掉，剩下的才是「清单本身的吸住效应」。
    a0, a1 = spans["ask"][0], spans["ask"][1]
    am = (a0 + a1) // 2
    m_ae = A[..., a0:am].sum(axis=-1) if am > a0 else np.zeros((L, H))
    m_al = A[..., am:a1].sum(axis=-1) if a1 > am else np.zeros((L, H))
    out["ask_early_per_tok"] = m(m_ae) / max(am - a0, 1)
    out["ask_late_per_tok"] = m(m_al) / max(a1 - am, 1)
    out["d6_placebo_ask_split"] = out["ask_early_per_tok"] - out["ask_late_per_tok"]
    return out


def _cos(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < EPS or nb < EPS:
        return float("nan")
    return float(np.dot(a, b) / (na * nb))


def extract_step_stats(step_attentions, P, n_gen, spans, hs_last, hs_prev, hs_prompt_end):
    """把一个生成步的内部量抽成一行。step_attentions: tuple(28) of [1,H,q_len,kv_len]"""
    A = np.stack([a[0, :, -1, :].detach().float().numpy() for a in step_attentions], axis=0)  # [L,H,K]
    st = _row_stats(A, P, n_gen, spans)
    if hs_last is not None and hs_prompt_end is not None:
        st["hs_cos_prompt_end"] = _cos(hs_last, hs_prompt_end)
    else:
        st["hs_cos_prompt_end"] = None
    if hs_last is not None and hs_prev is not None:
        st["hs_adj_cos"] = _cos(hs_last, hs_prev)
    else:
        st["hs_adj_cos"] = None
    return st
