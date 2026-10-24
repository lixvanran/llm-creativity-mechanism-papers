#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 净增益键名自检（★ 独立于 calc_net_gain.py 的写入路径 ⇒ 写入器不当检查器）

★ **它防的是【抽键陷阱】**：★ `L3_net_AND` 这个键名有误导性 ⇒ ★ 它装的是【断言层的总净增益】
（★ 在 AND 口径下分类 added/lost），★ **不是**【承重子层的净】⇒ ★ 第三方直抽它
⇒ 会得出"承重子层 = +14 ⇒ 为正 ⇒ ②篇结论不成立"的【完全错误】结论。

★ **判据**：★ 四个【明确命名】的承重键必须与【登记台账】逐位一致（★ 台账 = 三个独立来源的共识值）。
★ **负向测试**：★ 若把 `L3_net_AND` 当承重净 ⇒ 本自检必须【红】。
"""
import sys, os, json, subprocess
sys.dont_write_bytecode = True
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = "/tmp/_ng_selftest.json"

# ★ 登记台账（★ 来源：三个独立来源逐位一致 —— owner / ②篇 / 审稿人 / 交付包内第四来源）
LEDGER = {
    "W_design_L2": {"OR": (+20, +14, +6), "AND": (+7, +14, -7)},
    "W_train_L3": {"OR": (+21, +14, +7), "AND": (+12, +14, -2)},
}

r = subprocess.run([sys.executable, os.path.join(REPO, "tools/calc_net_gain.py"), "--json", OUT],
                   capture_output=True, text=True, cwd=REPO)
if r.returncode != 0:
    print("⛔ calc_net_gain.py 退出码 %d：%s" % (r.returncode, r.stderr[-400:])); sys.exit(2)
d = json.load(open(OUT, encoding="utf-8"))
agg = d["task1"]["aggregate"]

ok = True
print("★ 承重子层四序列（★ 目标：与登记台账逐位一致）")
for arm, spec in LEDGER.items():
    a = agg[arm]
    for cname, (ea, el, en) in spec.items():
        ga, gl = (a["L3_lb_OR_added"], a["L3_lb_OR_lost"]) if cname == "OR" else \
                 (a["L3_lb_AND_added"], a["L3_lb_AND_lost"])
        gn = ga - gl
        good = (ga, gl, gn) == (ea, el, en)
        ok &= good
        print("  %-14s %-3s 新增%3d 丢失%3d ⇒ 净 %+d  ｜ 台账 %+d/%+d/%+d  %s"
              % (arm, cname, ga, gl, gn, ea, el, en, "✅" if good else "❌"))

print()
print("★ 【抽键陷阱】负向测试：★ 旧误导键 L3_net_AND 不得被当成承重净")
for arm, spec in LEDGER.items():
    a = agg[arm]
    trap = a["L3_net_AND"]
    truth = a["L3_lb_OR_added"] - a["L3_lb_OR_lost"]
    bad = (trap == truth)          # ★ 若两者相等 ⇒ 说明键没被区分 ⇒ 陷阱仍在
    print("  %-14s L3_net_AND=%+d  vs  承重 OR 净=%+d  ⇒ %s"
          % (arm, trap, truth, "❌ 撞上了（陷阱未封）" if bad else "✅ 不同（已封）"))
    ok &= not bad

print()
print("★ 总体：%s" % ("✅ 全部通过" if ok else "❌ 有失败"))
sys.exit(0 if ok else 1)
