#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T-L1-01 · 注意力层内部探针 · 跑批器（每进程跑一批 = 1 题 × 2 臂 × 3 rep = 6 单元）

★ 预注册固定的采样参数（PREREG_T-L1-01.md §1）：
  9 题（DEV 全集，不抽样）× 2 臂 × 3 rep = 54 单元
  temperature=0.7 / top_p=0.95 / max_new_tokens=64
★ 停止规则（§3）：失败最多重试 1 次且不换 seed；失败单元必须落盘并报数。
★ 断点续跑：已存在于输出 JSONL 的 (task_id, arm, rep) 不重跑。

用法：  python 03_probe_run.py --batch 0        # 第 0 题（0-based）
"""
import os, sys, json, time, argparse, hashlib

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

import probe_lib as PL

MODEL_DIR = "/workspace/hf_cache/Qwen3-0.6B"
DEVSET = "/workspace/repo_source/devset.json"
OUT_DIR = "/workspace/run/units"
SEED_BASE = 20261026
REVISIONS = 3


def unit_seed(qi, ai, ri):
    """seed 事前定版：base + 题*100 + 臂*10 + rep（失败重试不换 seed ⇒ 同 seed 重试）。"""
    return SEED_BASE + qi * 100 + ai * 10 + ri


def load_devset():
    d = json.load(open(DEVSET, encoding="utf-8"))
    return d["tasks"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, required=True, help="0-based 题号；每批 = 1 题 × 2 臂 × 3 rep")
    a = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "units_batch%02d.jsonl" % a.batch)

    tasks = load_devset()
    qi = a.batch
    task = tasks[qi]
    tid = task["task_id"]
    ask = task["ask"]
    concls = [(c["id"], c["text"]) for c in task["conclusion_space"]]

    done = set()
    if os.path.exists(out_path):
        for line in open(out_path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("status") == "ok":
                done.add((r["task_id"], r["arm"], r["rep"]))

    torch.set_num_threads(2)
    tok = AutoTokenizer.from_pretrained(MODEL_DIR)
    t0 = time.time()
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_DIR, dtype=torch.bfloat16, attn_implementation="eager")
    model.eval()
    load_s = time.time() - t0
    print("[b%02d] 模型加载 %.1fs" % (qi, load_s), flush=True)

    fh = open(out_path, "a", encoding="utf-8")

    for ai, arm in enumerate(["A_bare", "A_list"]):
        pr = PL.build_prompt(tok, ask, concls, arm)
        print("[b%02d] %s %s prompt_len=%d head=%d think=%d ref_ids_equal=%s ref_text_equal=%s budget=%d"
              % (qi, tid, arm, pr["n_prompt"], pr["head_len"], pr["think_len"],
                 pr["ref_ids_equal"], pr["ref_text_equal"], pr["trunc_budget_tokens"]), flush=True)
        for ri in range(REVISIONS):
            key = (tid, arm, ri)
            if key in done:
                print("   跳过已完成 %s" % (key,), flush=True)
                continue
            seed = unit_seed(qi, ai, ri)
            rec = run_one(model, tok, pr, task, arm, ri, seed, qi, ai)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
            if rec["status"] == "ok":
                print("   ok  %s rep%d  gen=%d tok  %.1fs" % (arm, ri, rec["n_generated"], rec["elapsed_s"]), flush=True)
            else:
                print("   FAIL %s rep%d : %s" % (arm, ri, rec.get("error", "")[:120]), flush=True)
                # ★ 失败最多重试 1 次、且不换 seed
                rec2 = run_one(model, tok, pr, task, arm, ri, seed, qi, ai)
                rec2["retry_of"] = rec.get("attempt")
                rec2["attempt"] = 2
                fh.write(json.dumps(rec2, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
                print("   重试后: %s" % rec2["status"], flush=True)
    fh.close()
    print("[b%02d] 完成 → %s" % (qi, out_path), flush=True)
    return 0


def run_one(model, tok, pr, task, arm, ri, seed, qi, ai):
    t0 = time.time()
    ids = torch.tensor([pr["input_ids"]], dtype=torch.long)
    P = pr["n_prompt"]
    try:
        torch.manual_seed(seed)
        with torch.no_grad():
            out = model.generate(
                input_ids=ids,
                attention_mask=torch.ones_like(ids),
                do_sample=True, temperature=PL.TEMPERATURE, top_p=PL.TOP_P,
                max_new_tokens=PL.MAX_NEW_TOKENS,
                output_attentions=True, output_hidden_states=True, output_scores=True,
                return_dict_in_generate=True,
                pad_token_id=tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id,
            )
        gen_ids = out.sequences[0][P:].tolist()
        K = len(gen_ids)
        raw_text = tok.decode(gen_ids, skip_special_tokens=True)
        clean_text, n_strip = PL.strip_think(raw_text)
        has_think = ("<think>" in raw_text) or ("</think>" in raw_text)

        # ---- 逐步抽内部量
        steps = []
        attn = out.attentions
        hss = out.hidden_states
        n_layer = len(attn[0])
        hs_prompt_end = None
        hs_prev = None
        for k in range(K):
            hs_last = hss[k][-1][0, -1].detach().float().numpy() if hss is not None else None
            if k == 0 and hs_last is not None:
                hs_prompt_end = hss[0][-1][0, -1].detach().float().numpy()
            st = PL.extract_step_stats(
                attn[k], P, n_gen=k, spans=pr["spans"],
                hs_last=hs_last, hs_prev=hs_prev, hs_prompt_end=hs_prompt_end)
            st["n_gen_in_ctx"] = k
            steps.append(st)
            hs_prev = hs_last

        # ---- logit 熵：★ 用 lm_head(hidden_states[-1]) 反解 raw logits（自证：raw ≈ temperature × scores）
        logit_check = {}
        if hss is not None and out.scores is not None:
            lents, lents_s, top1 = [], [], []
            ratio_ok = 0
            for k in range(K):
                # ★ hidden 必须【转成 lm_head 权重的 dtype】——transformers 5.x 的 output_hidden_states
                #   末层可能是 float32，而 lm_head 权重是 bf16 ⇒ 直接喂 float32 会 dtype 不匹配
                #   （2026-10-26 首跑的崩溃点；下方一行 .to(weight.dtype) 是稳健写法，两种 dtype 都成立）★
                h = hss[k][-1][0, -1].detach().to(model.lm_head.weight.dtype)
                raw = model.lm_head(h.unsqueeze(0)).squeeze(0).float().numpy()
                pr_ = np.exp(raw - raw.max())
                pr_ = pr_ / pr_.sum()
                lents.append(float(-(pr_[pr_ > 0] * np.log(pr_[pr_ > 0])).sum()))
                top1.append(float(pr_.max()))
                sc = out.scores[k][0].detach().float().numpy()
                sp = np.exp(sc - sc.max()); sp = sp / sp.sum()
                lents_s.append(float(-(sp[sp > 0] * np.log(sp[sp > 0])).sum()))
                if abs(raw.max() - sc.max() * PL.TEMPERATURE) < 0.5:
                    ratio_ok += 1
            logit_check = {"logit_entropy_raw": lents, "logit_entropy_sampled": lents_s,
                           "logit_top1_raw": top1, "raw_vs_scaled_max_ok": ratio_ok, "K": K}
        else:
            logit_check = {}

        rec = {
            "run_id": "T-L1-01-2026-10-26",
            "task_id": task["task_id"], "arm": arm, "rep": ri, "seed": seed,
            "batch": qi, "status": "ok", "attempt": 1,
            "n_prompt": P, "n_generated": K,
            "prompt_text": pr["text"], "user_content": pr["user_content"],
            "prompt_head_len": pr["head_len"], "prompt_think_len": pr["think_len"],
            "prompt_think_ids": pr["think_ids"],
            "prompt_ref_ids_equal": pr["ref_ids_equal"], "prompt_ref_text_equal": pr["ref_text_equal"],
            "trunc_budget_tokens": pr["trunc_budget_tokens"],
            "spans": pr["spans"],
            "gen_ids": gen_ids, "gen_text_raw": raw_text, "gen_text": clean_text,
            "n_think_stripped": n_strip, "gen_contains_think_tag": bool(has_think),
            "steps": steps,
            "logit": logit_check,
            "sampling": {"temperature": PL.TEMPERATURE, "top_p": PL.TOP_P,
                         "max_new_tokens": PL.MAX_NEW_TOKENS},
            "elapsed_s": round(time.time() - t0, 2),
        }
        return rec
    except Exception as e:
        import traceback
        return {"run_id": "T-L1-01-2026-10-26", "task_id": task["task_id"], "arm": arm,
                "rep": ri, "seed": seed, "batch": qi, "status": "fail",
                "error": "%s: %s" % (type(e).__name__, str(e)[:300]),
                "traceback": traceback.format_exc()[-1500:],
                "elapsed_s": round(time.time() - t0, 2)}


if __name__ == "__main__":
    sys.exit(main())
