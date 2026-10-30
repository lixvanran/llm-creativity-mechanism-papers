#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l0/llm.py —— L0 Agent 的 LLM 通道

★ 三条纪律（★ 全部来自本项目既有教训 ★）：
1. **必须剥 `<think>`** —— MiniMax 把推理内联在 `content` 里（实测 `<think>We need…</think>\n\nPONG`）
   ⇒ 不剥 ⇒ 事实抽取会把推理文字当正文 ⇒ 整批作废。
2. **失败必须可计数** —— 失败不许静默归零：每次调用记 ok/fail 与失败原因。
3. **凭据只从 env 读** —— 不落盘、不进日志、不进任何会进 git 的文件。
"""

import json
import os
import re
import time
import urllib.request

ENDPOINT = "https://api.minimaxi.com/v1"
MODEL = "MiniMax-M2.5"   # ★ Agent 场景默认：★ 实测 think 707 vs M3 的 2090（★ 省 3 倍、★ 不撞上限 ★）
THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def strip_think(text):
    """★ 剥 `<think>`（★ 含未闭合的情况 ★）"""
    if not text:
        return ""
    if "</think>" in text:
        return text.rsplit("</think>", 1)[-1].strip()
    if "<think>" in text:
        # ★ 未闭合 ⇒ 思考被截断、★ 正文根本没写出来 ⇒ ★ 判失败、★ 不许把 think 当正文 ★
        return ""
    return text.strip()


class LLM:
    """★ ★★ 通道参数必须【显式固定】★★

    ★ 实测（★ 2026-10-26 冒烟 ★）：★ MiniMax 省略 `reasoning_effort` ⇒ **默认 max** ⇒
    ★ 思考块吃光 `max_tokens` ⇒ 正文为空 ⇒ 剥完 `<think>` 是空串 ⇒
    ★ **表现为「empty_after_strip_think」、★ 而内容本身没问题** ⇒
    ★ ★ 这是第二组早就踩过的坑（★ 「通道坏掉的『全 0』是关于【仪器】不是【世界】的证据」★）★★
    ★ ⇒ 本类**默认 medium**、★ 并把 effort 写进读数元数据（★ 复现必须知道档位 ★）
    """

    def __init__(self, model=MODEL, temperature=0.7, max_tokens=6000, retries=2,
                 reasoning_effort="medium", thinking_disabled=False):
        self.key = os.environ.get("MINIMAX_SUBSCRIPTION_KEY", "")
        if not self.key:
            raise RuntimeError("MINIMAX_SUBSCRIPTION_KEY 不在 env 里（★ 不落盘 ★）")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.retries = retries
        self.reasoning_effort = reasoning_effort
        self.thinking_disabled = thinking_disabled
        self.calls = 0
        self.failures = 0
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0}
        self.failure_log = []

    def chat(self, prompt, system=None, max_tokens=None, temperature=None,
             reasoning_effort=None):
        """★ 返回 (text, ok) —— ★ 失败不抛、★ 但计入 failures ★"""
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        body = {
            "model": self.model,
            "messages": msgs,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": self.temperature if temperature is None else temperature,
            # ★ 显式固定档位：★ 省略 = 默认 max = 吃光 token ★
            "reasoning_effort": reasoning_effort or self.reasoning_effort,
        }
        # ★★ 关思考：★ M2.5/M3 的推理 token 会【随机暴涨】⇒ 正文被截断 ★★
        # （★ 实测：thinking disabled ⇒ reasoning=0、finish_reason=stop、12s/次 ★）
        if self.thinking_disabled:
            body["thinking"] = {"type": "disabled"}
        last = ""
        for attempt in range(self.retries + 1):
            self.calls += 1
            try:
                req = urllib.request.Request(
                    ENDPOINT + "/chat/completions",
                    data=json.dumps(body).encode("utf-8"),
                    headers={"Authorization": "Bearer " + self.key,
                             "Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=120) as r:
                    d = json.loads(r.read().decode("utf-8"))
                u = d.get("usage") or {}
                self.usage["prompt_tokens"] += u.get("prompt_tokens", 0) or 0
                self.usage["completion_tokens"] += u.get("completion_tokens", 0) or 0
                self.usage["reasoning_tokens"] += (u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0) or 0
                ch = d["choices"][0]
                raw = ch["message"]["content"]
                text = strip_think(raw)
                if not text:
                    last = "empty_after_strip_think"
                    self._fail(last, attempt)
                    time.sleep(1.5 * (attempt + 1))
                    continue
                if ch.get("finish_reason") == "length":
                    last = "truncated"
                    self._fail(last, attempt)
                    return text, False          # ★ 截断不算成功 ★
                return text, True
            except Exception as e:                # noqa: BLE001
                last = "%s: %s" % (type(e).__name__, str(e)[:80])
                self._fail(last, attempt)
                time.sleep(1.5 * (attempt + 1))
        return "", False

    def _fail(self, reason, attempt):
        self.failures += 1
        self.failure_log.append({"call_no": self.calls, "attempt": attempt, "reason": reason})

    def stats(self):
        return {"calls": self.calls, "failures": self.failures,
                "usage": dict(self.usage), "failure_log": self.failure_log[:50]}


def atomic_write_jsonl(path, rows):
    """★ 原子写（★ 临时文件 + os.replace ★）⇒ 写失败不会把原文件截断成 0 ★"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
