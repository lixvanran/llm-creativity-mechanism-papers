# -*- coding: utf-8 -*-
"""批次 U1-2026-10-21 的共用件：事实切分 / C_t / OpenRouter 侧 LLM / MiniMax 侧判官。

⚠️ **两侧厂商隔离**（协议 R-8）：
   - 被测侧（工作流）⇒ **OpenRouter**（`x-ai/grok-4.3`）
   - 测量侧（判官 / 维度抽取）⇒ **MiniMax 订阅**（`MiniMax-M3.1-Flash-Preview`）
   ⇒ `judge_same_vendor = false`
"""
import hashlib
import json
import os
import re
import time
import urllib.request

REPO = "/workspace/lab/cmp8repo"
ROUTES = "/workspace/lab/routes"
BATCH = "/workspace/lab/batch-U1"

OR_BASE = os.environ.get("OR_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
OR_KEY = os.environ.get("OPENROUTER_API_KEY", "")
MM_BASE = os.environ.get("MM_BASE_URL", "https://api.minimaxi.com/v1").rstrip("/")
MM_KEY = os.environ.get("MINIMAX_SUBSCRIPTION_KEY", "")
OR_MODEL = os.environ.get("OR_MODEL", "x-ai/grok-4.3")
MM_MODEL = os.environ.get("MM_MODEL", "MiniMax-M3.1-Flash-Preview")

U1_PACK = os.path.join(REPO, "cmp8/creativity_lab/data/user4_q1.json")

# ── 人肉标准关键词（★ **只允许出现在测量侧**；生成侧出现即污染，见 PREREG R5）──
HUMAN_KEYS = {
    "港校": 0.5,
    "香港城大": 0.5,
    "城市理工": 0.5,
    "香港理工": 0.5,
}
HUMAN_MAX = 1.0


def sha(obj):
    return "sha256:" + hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()[:16]


# ══════════════════ 事实切分（确定性，零模型） ══════════════════
def load_u1():
    return json.load(open(U1_PACK, encoding="utf-8"))


def split_facts(evidence_text: str):
    """按中文句末标点切分 ⇒ 原子事实列表。**确定性，无模型参与。**"""
    parts = re.split(r"(?<=[。！？；])", evidence_text or "")
    out = []
    for p in parts:
        p = (p or "").strip()
        if p:
            out.append(p)
    return out


def evidence_items(pack=None):
    pack = pack or load_u1()
    facts = split_facts(pack["evidence"])
    return [{"id": "EV-%02d" % (i + 1), "text": f} for i, f in enumerate(facts)]


def conclusion_space(pack=None):
    """`C_t`（结论空间）= **依据包 16 条原子事实各自的命题化文本**。

    机械构造：事实原文去掉句末标点 ⇒ 不含任何模型判断、不含任何"正确答案"暗示。
    """
    return [{"id": it["id"], "text": it["text"].rstrip("。！？；")}
            for it in evidence_items(pack)]


# ══════════════════ 两个厂商的 LLM（同一接口） ══════════════════
class _Call:
    def __init__(self, model, purpose, max_tokens, finish_reason, content_len, ok, secs):
        self.model = model
        self.purpose = purpose
        self.max_tokens = max_tokens
        self.finish_reason = finish_reason
        self.content_len = content_len
        self.ok = ok
        self.secs = secs


class _BaseLLM:
    """共同接口：`chat(prompt, *, model, temp, max_tokens, budgets, min_ok, purpose)`，
    外加 `n_api_calls` / `n_tokens` / `rec`（路线 A/C 的执行器依赖这三个）。"""

    def __init__(self):
        self.rec = []
        self.errors = []
        self.usage = []
        self._cache = {}

    # 子类覆盖
    def _post(self, url, payload, timeout=240):
        raise NotImplementedError

    def chat(self, prompt: str, *, model=None, temp: float = 0.7,
             max_tokens: int = 8000, budgets=(), min_ok: int = 20,
             purpose: str = "") -> str:
        last = ""
        last_error = ""
        t0 = time.time()
        for mt in (max_tokens,) + tuple(budgets):
            try:
                d = self._post("%s/chat/completions" % self.BASE, {
                    "model": model or self.MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temp, "max_tokens": mt,
                })
                if "choices" not in d:
                    # ★ 供应商可能用 **HTTP 200 + 错误体** 返回（无 choices）
                    #   ⇒ 旧代码在这里抛 KeyError ⇒ 错误体被吞 ⇒ 只剩 "KeyError: choices"
                    #   ⇒ 无法诊断（2026-10-23 实测：锚外判官恒 0 就是这么来的）
                    raise RuntimeError("响应无 choices：%s"
                                       % json.dumps(d, ensure_ascii=False)[:300])
                ch = d["choices"][0]
                raw = ch["message"].get("content") or ""
                last = self._strip(raw)
                fr = ch.get("finish_reason", "")
                u = d.get("usage") or {}
                self.usage.append(dict(
                    model=model or self.MODEL, purpose=purpose, max_tokens=mt,
                    finish_reason=fr, prompt_tokens=int(u.get("prompt_tokens") or 0),
                    completion_tokens=int(u.get("completion_tokens") or 0),
                    total_tokens=int(u.get("total_tokens") or 0),
                    secs=round(time.time() - t0, 2)))
                self.rec.append(_Call(model or self.MODEL, purpose, mt, fr,
                                       len(last), False, time.time() - t0))
                if fr == "length":
                    continue
                if last.count("<think>") > last.count("</think>"):
                    continue
                if len(last) >= min_ok:
                    self.rec[-1].ok = True
                    return last
            except Exception as e:
                # ★ 2026-10-23：**不许把失败吞成空串**
                #   旧写法：只记 "error:HTTPError" ⇒ 状态码/响应体全丢 ⇒ 事后查不出原因
                #   ⇒ 且返回空串 ⇒ 上层把"调用失败"读成"这条臂没有承重信息"（dims=0）
                detail = "%s: %s" % (type(e).__name__, e)
                try:
                    _body = getattr(e, "read", lambda: b"")()[:300]
                    if _body:
                        detail += " | body=" + _body.decode("utf-8", "ignore")
                except Exception:
                    pass
                self.errors.append(dict(purpose=purpose, model=model or self.MODEL,
                                         max_tokens=mt, error=detail))
                self.rec.append(_Call(model or self.MODEL, purpose, max_tokens,
                                       "error:%s" % type(e).__name__, 0, False,
                                       time.time() - t0))
                last_error = detail
                time.sleep(2.0)
        # ★ 全部尝试都失败 ⇒ **抛错**（带原因）⇒ 不许返回空串冒充成功
        if last_error:
            raise RuntimeError("LLM 调用全部失败（%s）：%s" % (purpose, last_error))
        return last

    @staticmethod
    def _strip(raw):
        raw = raw or ""
        raw = re.sub(r"^.*?</think>", "", raw, flags=re.S)
        return raw.strip()

    @property
    def n_api_calls(self):
        return len(self.usage)

    @property
    def n_tokens(self):
        return sum(u["total_tokens"] or (u["prompt_tokens"] + u["completion_tokens"])
                   for u in self.usage)


class OpenRouterLLM(_BaseLLM):
    """被测侧（工作流）⇒ OpenRouter。"""

    BASE = OR_BASE
    MODEL = OR_MODEL

    def _post(self, url, payload, timeout=240):
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + OR_KEY,
                     "content-type": "application/json",
                     "HTTP-Referer": "https://github.com/lixvanran/agent-creativity-mechanism-study",
                     "X-Title": "u1-batch-2026-10-21"})
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())


class MiniMaxLLM(_BaseLLM):
    """测量侧（判官 / 维度抽取）⇒ MiniMax 订阅。"""

    BASE = MM_BASE
    MODEL = MM_MODEL

    def _post(self, url, payload, timeout=240):
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + MM_KEY,
                     "content-type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())


# ══════════════════ 人肉标准（纯字符串匹配，零模型） ══════════════════
def human_score(answer: str):
    """负责人的人肉标准（**主口径 = 分级**）：提到港校 +0.5；点名列名（香港城大/香港理工）
    再 +0.5 ⇒ 封顶 1.0。

    实现：**纯子串匹配**（确定性、可复现、零歧义）。
    ⚠️ 「城市理工」单独命中也计（指 CityU）；「香港理工」与「香港理工大学」都计。

    �� 原始措辞「提到港校 +0.5，提到香港城大、香港理工这两所学校的具体名字再 +0.5」
       有两种读法，本函数**两种都算**，主口径取「分级」（泛指 0.5 / 点名 1.0）：
         score       = 分级读法（主口径）
         score_pername = 每校名各 +0.5 的读法（封顶同 1.0）
       ⇒ 两者**只在「两个校名都点、但没提港校」这一种情形下不同**，其余完全一致。
    """
    a = answer or ""
    generic = "港校" in a
    cityu = ("香港城大" in a) or ("城市理工" in a)
    polyu = ("香港理工" in a)
    named = cityu or polyu
    per_name = 0.0
    hits = {}
    if generic:
        hits["港校"] = 0.5
        per_name += 0.5
    if cityu:
        hits["香港城大|城市理工"] = 0.5
        per_name += 0.5
    if polyu:
        hits["香港理工"] = 0.5
        per_name += 0.5
    graded = (0.5 if generic else 0.0) + (0.5 if named else 0.0)
    return dict(score=round(min(graded, HUMAN_MAX), 3),
                 score_pername=round(min(per_name, HUMAN_MAX), 3),
                 generic_mentioned=generic,
                 specific_named=named,
                 hits=hits, matched=sorted(hits.keys()))


# ══════════════════ 生成侧污染自检（R5）══════════════════
def generation_prompt_contamination(prompts):
    """生成侧提示词里是否出现了人肉标准的关键词 ⇒ 命中即污染（R5 ⇒ 该臂作废）。"""
    bad = []
    for i, p in enumerate(prompts or []):
        for kw in HUMAN_KEYS:
            if kw in (p or ""):
                bad.append(dict(prompt_index=i, keyword=kw))
    return bad
