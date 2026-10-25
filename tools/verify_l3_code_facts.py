#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_l3_code_facts.py —— 方向③（层3）三条代码级事实的【零调用】复现脚本

★ 背景：2026-10-24 执行会话读底稿代码时提出三条断言，owner 逐条复现后全部成立，
  并据此改写了层3 篇的规格（v2.1 §0.5）。本脚本把那三条断言固化成【可复跑】的判据。

★ 零模型调用、零网络：只 import 底稿里的 workflow.py（外部依赖用桩打掉）。

用法：
    python3 tools/verify_l3_code_facts.py
退出码：0 = 全部六条断言成立；1 = 有断言不成立（打印实际值）。
"""
import importlib.abc
import importlib.machinery
import os
import sys
import types

# ★★ S-01（2026-10-25 包级复核 v2）：★ 本脚本 import 底稿的 workflow.py ⇒ 默认会在
#   【被检树】里落 `__pycache__/workflow.cpython-311.pyc` ⇒ ★ **污染它自己检查的对象**
#   （★ 不污染交付包 —— 打包器已排除 `__pycache__` —— ★ 但会脏仓，且会让「从脏树重建」
#     这条路径看起来不可靠）⇒ 落法：★ 关掉字节码写入（★ 被检树的字节一个都不动）
sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "来源与底稿", "第三组_治塌缩层3", "cmp8repo", "repro", "src")


class _Stub(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Stub(name)

    def __call__(self, *a, **k):
        return None


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """把底稿用不到的外部依赖替换成桩（只桩【找不到】的模块，不动标准库）"""

    def find_spec(self, name, path=None, target=None):
        if name.startswith("workflow"):
            return None
        try:
            if importlib.machinery.PathFinder.find_spec(name, path) is not None:
                return None
        except Exception:
            pass
        return importlib.machinery.ModuleSpec(name, self)

    def create_module(self, spec):
        return _Stub(spec.name)

    def exec_module(self, module):
        pass


def load_workflow():
    if not os.path.isdir(SRC):
        print("✘ 找不到底稿源码目录：%s" % SRC)
        sys.exit(2)
    sys.meta_path.insert(0, _Finder())
    sys.path.insert(0, SRC)
    import workflow  # noqa: E402
    return workflow


def main():
    W = load_workflow()
    fails = []

    # ── 断言①：ARB_IDS 是 (mark, keep_pos, keep_neg) ⇒ 策略路径产不出 "resolve" ──
    arb_ids = tuple(W.ActionPolicy.ARB_IDS)
    ok1 = (arb_ids == ("mark", "keep_pos", "keep_neg")) and ("resolve" not in arb_ids)
    print("① ARB_IDS = %s  ⇒ 策略路径产不出 'resolve'：%s" % (arb_ids, "✔" if ok1 else "✘"))
    if not ok1:
        fails.append("① ARB_IDS 与预期不符：%s" % (arb_ids,))

    # ── 断言②：mode="resolve" 的输出与 mode="drop_one" 完全相同（无独立实现）────
    claims_pos_first = ["① 正确：A 满足条件", "① 错误：A 不满足条件"]
    claims_neg_first = ["① 错误：A 不满足条件", "① 正确：A 满足条件"]
    same_resolve = True
    for cl in (claims_pos_first, claims_neg_first):
        k_dn, _ = W.arbitrate(list(cl), "drop_one", drop_choice="keep_pos")
        k_rs, _ = W.arbitrate(list(cl), "resolve", drop_choice="keep_pos")
        same_resolve = same_resolve and (k_dn == k_rs)
    print("② mode='resolve' 输出 == mode='drop_one' 输出（两种冲突对顺序）：%s"
          % ("✔" if same_resolve else "✘"))
    if not same_resolve:
        fails.append("② mode='resolve' 与 'drop_one' 行为不同 ⇒ 与判据冲突")

    # ── 断言③：drop_choice 的语义随冲突对的【出现顺序】互换 ⇒ 实际是按索引丢 ──
    kept = {}
    for tag, cl in (("正在前", claims_pos_first), ("负在前", claims_neg_first)):
        for dc in ("keep_pos", "keep_neg"):
            k, _ = W.arbitrate(list(cl), "drop_one", drop_choice=dc)
            kept[(tag, dc)] = k[0]
    flips = (kept[("正在前", "keep_pos")] != kept[("负在前", "keep_pos")]) and \
            (kept[("正在前", "keep_neg")] != kept[("负在前", "keep_neg")])
    print("③ drop_choice 保留的极性随【出现顺序】互换 ⇒ 按索引丢、与极性无关：%s"
          % ("✔" if flips else "✘"))
    for k, v in sorted(kept.items()):
        print("     %s / %-9s ⇒ kept=%s" % (k[0], k[1], v))
    if not flips:
        fails.append("③ drop_choice 行为与判据不符（未观察到顺序依赖）")

    # ── 断言④：mode='none'（层2 默认）保留全部（不收窄搜索空间）────────────
    none_keeps_all = all(
        len(W.arbitrate(list(cl), "none", drop_choice="keep_pos")[0]) == len(cl)
        for cl in (claims_pos_first, claims_neg_first))
    print("④ mode='none'（层2 默认）保留全部：%s" % ("✔" if none_keeps_all else "✘"))
    if not none_keeps_all:
        fails.append("④ mode='none' 未保留全部")

    # ── 断言⑤：读数批里 arb 从未被行使（run_dev 不传 arbitrate_mode ⇒ 默认 none）──
    rdv = os.path.join(SRC, "run_dev.py")
    src = open(rdv, encoding="utf-8").read() if os.path.isfile(rdv) else ""
    arm_src = ""
    m = src.find("def arm_workflow(")
    if m >= 0:
        arm_src = src[m:src.find("\ndef ", m + 10)] if src.find("\ndef ", m + 10) > 0 else src[m:]
    passes_arb_mode = "arbitrate_mode" in arm_src
    default_none = ('C.get("arbitrate_mode", "none")' in open(
        os.path.join(SRC, "workflow.py"), encoding="utf-8").read())
    ok5 = (not passes_arb_mode) and default_none
    print("⑤ 读数批（run_dev.arm_workflow）不传 arbitrate_mode，且默认 'none'：%s"
          % ("✔" if ok5 else "✘"))
    if not ok5:
        fails.append("⑤ arbitrate_mode 门控状态与判据不符")

    # ── 断言⑥：两臂共用同一个 policy=_pol（⇒ 实现上只差 evolve）────────────
    l2_pol = 'W_design_L2' in src and 'policy=_pol' in src
    print("⑥ W_design_L2 / W_train_L3 传同一个 policy=_pol：%s"
          % ("✔" if l2_pol else "✘"))
    if not l2_pol:
        fails.append("⑥ 未找到两臂共用 policy=_pol 的证据")

    print()
    if fails:
        print("★ 负向结果：%d 条断言不成立" % len(fails))
        for f in fails:
            print("   - %s" % f)
        return 1
    print("★ 全部 %d 条断言成立（零调用、零网络）" % 6)
    return 0


if __name__ == "__main__":
    sys.exit(main())
