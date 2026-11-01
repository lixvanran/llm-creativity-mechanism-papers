#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★★ 路径解析（★ 交付包自包含的钥匙 ★）

★ ★ 纪律：★ **禁止硬编码 `/workspace/...` 绝对路径** —— 第三方拿到包第一步就跑不了、★ 复现链断在开头 ★
★★ ⇒ 落法：★ 四级查找 ① 环境变量 → ② 脚本同目录 / 包内相对位置 → ③ 上溯目录 → ④ 沙箱兜底
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _ancestors(start):
    d = start
    while True:
        yield d
        nd = os.path.dirname(d)
        if nd == d:
            return
        d = nd


def find_l3_src():
    """★ 找层3 判据源码目录（★ 含 space.py / measure.py ★）"""
    cands = []
    env = os.environ.get("T0KENS_L3_SRC")
    if env:
        cands.append(env)
    # ② 脚本同目录 / 包内相对位置
    cands += [
        os.path.join(HERE, "l3", "src"),
        os.path.join(HERE, "..", "l3", "src"),
        os.path.join(HERE, "..", "..", "l3", "src"),
        os.path.join(HERE, "..", "..", "src"),
    ]
    # ③ 上溯目录
    for base in _ancestors(HERE):
        cands.append(os.path.join(base, "l3", "src"))
        cands.append(os.path.join(base, "src"))
        cands.append(os.path.join(base, "代码", "l3", "src"))
    # ④ 沙箱兜底
    cands.append("/workspace/work/l3/src")
    for c in cands:
        c = os.path.abspath(c)
        if os.path.isfile(os.path.join(c, "space.py")):
            return c
    raise SystemExit("★ 找不到层3 源码目录（★ 含 space.py ★）★★ 请设环境变量 T0KENS_L3_SRC 指向它 ★")


def find_devset():
    """★ 找题库（★ devset.json：★ 题面 ＋ 依据池 ＋ 结论池 ★）"""
    cands = []
    env = os.environ.get("T0KENS_DEVSET")
    if env:
        cands.append(env)
    cands += [
        os.path.join(HERE, "..", "devset", "devset.json"),
        os.path.join(HERE, "..", "..", "devset", "devset.json"),
        os.path.join(HERE, "devset", "devset.json"),
        os.path.join(HERE, "..", "题库", "devset.json"),
    ]
    for base in _ancestors(HERE):
        cands.append(os.path.join(base, "devset", "devset.json"))
        cands.append(os.path.join(base, "题库", "devset.json"))
        cands.append(os.path.join(base, "data", "devset.json"))
    cands.append("/workspace/work/devset/devset.json")
    for c in cands:
        c = os.path.abspath(c)
        if os.path.isfile(c):
            return c
    raise SystemExit("★ 找不到 devset.json ★★ 请设环境变量 T0KENS_DEVSET 指向它 ★")


def ensure_l3_on_path():
    p = find_l3_src()
    if p not in sys.path:
        sys.path.insert(0, p)
    return p
