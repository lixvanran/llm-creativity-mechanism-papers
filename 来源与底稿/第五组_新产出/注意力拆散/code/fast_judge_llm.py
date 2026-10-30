#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fast_judge_llm.py —— 判官**传输层**替换（★ 判据本体一字未动 ★）

★ 为什么需要（★ 2026-10-30 实测 ★）：
  层3 的 `u1_lib._BaseLLM.chat` **不发** `thinking:{"type":"disabled"}`
  ⇒ MiniMax 的 adaptive thinking 会吃光预算 ⇒ 它自己注释里就记着
  「8000 才出正文（309 字符 / 109 秒）」⇒ ★ 单次判官调用几十秒 ★
  ⇒ 918 次判官调用 ⇒ 批要跑一个多小时。

★ 本类只做三件事（★ 全在【传输层】、★ 判据本体不动 ★）：
  1. ★ 加 `thinking:{"type":"disabled"}`（★ 本项目已验证的配方：reasoning=0、finish=stop ★）
  2. ★ 保留层3 的【预算阶梯】语义（★ `max_tokens` 后接 `budgets`、★ 截断/未闭合 think ⇒ 换下一档 ★）
  3. ★ 保留层3 的【不许把失败吞成空串】纪律（★ 全部失败 ⇒ 抛错 ★）

★ 接口与 `u1_lib._BaseLLM.chat` **同签名** ⇒ `measure.py` 的调用点**一个字都不用改** ★
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm2 import LLM2, QuotaExhausted   # noqa: E402


class FastJudgeLLM:
    """★ 判官传输层（★ 只换传输、★ 不换判据 ★）"""

    def __init__(self, model="MiniMax-M3.1-Flash-Preview"):
        self.MODEL = model
        self._llm = LLM2(model=model, temperature=0.7, max_tokens=8000, retries=0)
        self.usage = []
        self.errors = []
        self.rec = []

    def chat(self, prompt, *, model=None, temp=0.7, max_tokens=8000, budgets=(),
             min_ok=20, purpose=""):
        last = ""
        last_error = ""
        for mt in (max_tokens,) + tuple(budgets):
            try:
                txt, ok = self._llm.chat(prompt, model=model or self.MODEL,
                                         max_tokens=mt, temperature=temp)
                if not ok:
                    last_error = "call_failed_or_truncated"
                    continue
                if len(txt) < min_ok:
                    last = txt
                    last_error = "too_short(%d<%d)" % (len(txt), min_ok)
                    continue
                self.usage.append({"model": model or self.MODEL, "purpose": purpose,
                                   "max_tokens": mt, "chars": len(txt)})
                return txt
            except QuotaExhausted:
                raise
            except Exception as e:                # noqa: BLE001
                last_error = "%s: %s" % (type(e).__name__, str(e)[:160])
        if last_error:
            raise RuntimeError("LLM 调用全部失败（%s）：%s" % (purpose, last_error))
        return last

    @property
    def n_api_calls(self):
        return len(self.usage)

    @property
    def n_tokens(self):
        return sum(u.get("chars", 0) for u in self.usage)
