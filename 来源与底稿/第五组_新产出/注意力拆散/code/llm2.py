#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""llm2.py —— 本批（拆散方式对照）专用通道

★ 与上一批 llm.py 的差别（★ 三条、★ 都是本批踩坑点 ★）：
1. ★ **响应体必须抓下来**：★ HTTP 429 有两种 —— 2062 速率限制（退避可过）／**2056 用量上限（退避无用）**
   ⇒ ★ 只看状态码会把"额度用完"误判成"速率慢"⇒ ★ 白等几十分钟 ★ ⇒ 本模块抛 `QuotaExhausted` 让跑批器**立即停**。
2. ★ **每调用可换模型**（S4 异构模型臂）★。
3. ★ **claims 随回答自带**：★ 本批不再单独调抽取器（★ 省一半调用 ★）⇒ 解析失败单列为【产出层失败】。
"""

import json
import os
import re
import time
import urllib.error
import urllib.request

ENDPOINT = "https://api.minimaxi.com/v1"
THINK_RE = re.compile(r"<think>.*?</think>", re.S)


class QuotaExhausted(RuntimeError):
    """★ MiniMax Token Plan 用量上限（2056）⇒ ★ 退避无用、★ 立即停 ★"""


def strip_think(text):
    """★ 剥 `<think>`（★ 含未闭合的情况：★ 未闭合 ⇒ 正文根本没写出来 ⇒ 判失败 ★）"""
    if not text:
        return ""
    if "</think>" in text:
        return text.rsplit("</think>", 1)[-1].strip()
    if "<think>" in text:
        return ""
    return text.strip()


class LLM2:
    """★ 通道参数必须【显式固定】★（★ 省略 reasoning_effort ⇒ 默认 max ⇒ 思考吃光预算 ★）"""

    def __init__(self, model="MiniMax-M3", temperature=1.0, max_tokens=12000,
                 retries=2, timeout=60):
        self.key = os.environ.get("MINIMAX_SUBSCRIPTION_KEY", "")
        if not self.key:
            raise RuntimeError("MINIMAX_SUBSCRIPTION_KEY 不在 env 里（★ 不落盘 ★）")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.retries = retries
        self.timeout = timeout
        self.calls = 0
        self.failures = 0
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0}
        self.failure_log = []
        self.quota_hit = False

    def _body(self, messages, model, max_tokens, temperature):
        body = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            # ★ ★ 必带 thinking disabled：★ M2.5/M3 的推理 token 会【随机暴涨】
            #   ⇒ 正文被截断 ⇒ 覆盖系统性偏低 ⇒ 样本被仪器削短 ★ ★
            "thinking": {"type": "disabled"},
        }
        return body

    def chat(self, prompt, system=None, model=None, max_tokens=None, temperature=None):
        """★ 返回 (text, ok) —— ★ 失败不抛（★ 但计入 failures ★）；额度上限抛 QuotaExhausted ★"""
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        body = self._body(msgs, model or self.model,
                          max_tokens or self.max_tokens,
                          self.temperature if temperature is None else temperature)
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
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
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
                    self._fail(last, attempt, model or self.model)
                    time.sleep(1.5 * (attempt + 1))
                    continue
                if ch.get("finish_reason") == "length":
                    last = "truncated"
                    self._fail(last, attempt, model or self.model)
                    return text, False          # ★ 截断不算成功 ★
                return text, True
            except urllib.error.HTTPError as e:
                b = e.read().decode("utf-8", "replace")
                last = "HTTP%d:%s" % (e.code, b[:200])
                self._fail(last, attempt, model or self.model)
                # ★ ★ 额度上限（2056）：★ 退避无用、★ 立即停 ★ ★
                if e.code == 429 and "2056" in b:
                    self.quota_hit = True
                    raise QuotaExhausted(last)
                if e.code == 429:
                    time.sleep(10 * (attempt + 1))
                else:
                    time.sleep(1.5 * (attempt + 1))
            except Exception as e:                # noqa: BLE001
                last = "%s: %s" % (type(e).__name__, str(e)[:120])
                self._fail(last, attempt, model or self.model)
                time.sleep(2.0 * (attempt + 1))
        return "", False

    def _fail(self, reason, attempt, model):
        self.failures += 1
        self.failure_log.append({"call_no": self.calls, "attempt": attempt,
                                 "model": model, "reason": reason})

    def stats(self):
        return {"calls": self.calls, "failures": self.failures,
                "usage": dict(self.usage), "failure_log": self.failure_log[:60]}


def atomic_write_jsonl(path, rows):
    """★ 原子写（★ 临时文件 + os.replace ★）⇒ 写失败不会把原文件截断成 0 ★"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def parse_claims(text):
    """★ 从回答里抽 claims（★ 回答自带的那行 JSON ★）

    ★ 返回 (claims, fail_reason) —— ★ 解析失败必须可计数（★ 产出层失败 ★）★★
    """
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
    cl = obj.get("claims")
    if not isinstance(cl, list) or not cl:
        return [], "claims_missing_or_empty"
    out = [c for c in cl if isinstance(c, str) and c.strip()]
    if not out:
        return [], "claims_all_nonstring"
    return out, None
