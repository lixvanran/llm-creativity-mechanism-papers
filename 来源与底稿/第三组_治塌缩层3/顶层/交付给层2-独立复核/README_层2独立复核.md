# 交付：层2 独立复核材料（2026-10-25）
## 怎么跑（零 API）
```bash
python3 -B nested_calib_self.py /tmp/你的重算.json
# 输入：main_big_arms.jsonl / adv_arms.jsonl（本目录内，与脚本同级）
# 期望（Self-Sim 的 n 基线，k=2→12 应平坦）：
#   B0_bestof3 0.213→0.213 ｜ B0_frames_vote 0.079→0.079
#   W_design_L2 0.067→0.067 ｜ W_train_L3 0.071→0.071
# 期望（模态数 = 不同断言文本条数，k=2→12 强涨）：
#   B0_bestof3 8.0→46.0
```
## 口径警告（★ 重要）
`nested_calib_self.py::modal_count` = **「不同断言文本的条数」**，**不是结论族数**。
真正的族口径（用卡里的 supports_conclusions，零 API）见 `family_recompute.py`。
⇒ 我的论文已按此降级（§6.2b）。
## 另附
- `我的6题_结论空间模板.json` = 我 6 道对抗题的 conclusion_space 结构（你们要对齐字段名的模板）
- `conclusion_spaces_legal.json` = 法律域结论空间（按法条建、18 题跨题引用）
