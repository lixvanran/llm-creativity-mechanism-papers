# repro · 治塌缩工作流（论文「搜索空间塌缩与过早闭合」的复现包）

> 本目录是**论文的复现入口**。论文正文在 `docs/cmp8/PAPER-2026-10-25.md`。
> 判定规则（写于读数产出之前）在 `prereg/PREREG-DECISION-RULES-2026-10-22.md`。

## 0. 这份包要支撑的三个结论

1. **搜索空间确实被拓宽了**（零判官指标）：3 次独立直调的分支彼此重叠 **0.41–0.61**；
   任何"用认知位置"的臂彼此重叠 **0.10–0.13** ⇒ "独立采样"并不独立（shared prior）。
2. **代价发生在「合并」这一步**：逐帧各跑一遍＋投票的臂**同样宽、且信息量最高**；
   我们的机械汇总臂**同样宽、但信息量最低** ⇒ 下一步该动的是**合并方式**。
3. **评测层会吞掉架构层效应**：同一批设计、同一批题，**换判官结论就反号**；
   判官读数的中位波动 = 1，而维度数只有 1–5 ⇒ 判官读数**不能**支撑架构级结论。

## 1. 依赖

* **Python 3.9+**，**仅标准库**（`urllib` / `json` / `re` / `statistics`）—— **无第三方包**
* 两个密钥（**从环境变量读，绝不写进代码/日志**）：
  * `MINIMAX_SUBSCRIPTION_KEY` —— 生成侧 + 判官侧（默认）
  * `OPENROUTER_API_KEY` —— 可选，跨厂商判官（`x-ai/grok-4.3`）

## 2. 数据（已随包提供，**不需联网**）

```
devset/devset.json     9 道 DEV 题（题面 + 依据包 + 结论空间）
devset/evidence/       逐题依据（107 条，全部带可逐字引用的原文 + URL + 日期）
devset/gold/           金标卡（由结论空间机械派生）
devset/MANIFEST.json   冻结清单（devset_hash = sha256:41bbb538a454d9b0）
```
⚠️ **DEV 集已冻结** —— 改动它会让全部历史读数不可比。

## 3. 复现命令（从 `repro/` 目录执行）

```bash
cd repro

# ① 自检（零成本、零 API）
python3 src/test_workflow.py            # 期望 19/19
python3 src/test_metrics_priorart.py    # 期望 10/10

# ② 主批次：5 臂 × 2 题 × R=2（判官 MiniMax-M2.5；约 2–3 小时、约 120 次调用）
python3 src/run_dev.py --tasks 2 --reps 2 --slots 3 --rounds 2 \
  --arms B0_direct,B0_bestof3,B0_frames_vote,W_design_L2,W_train_L3 \
  --judge minimax --judge-model MiniMax-M2.5 --out runs/main

# ③ 零判官空间指标（本文主指标）
python3 src/space_report_final.py       # 逐臂表 + 关键对照

# ④ 判读（判读规则已预注册写死）
python3 src/analyze_batch.py --run runs/main/arms.jsonl

# ⑤ 跨厂商判官交叉（可选；**限 8 份**控成本）
python3 src/remeasure.py --run runs/main/arms.jsonl --judge openrouter --limit 8
```
★ **可复现的关键**：`runs/arms.jsonl` **逐臂增量落盘** ⇒ 中途被中断也不丢已完成的臂；
下次用 `--resume` 接着跑。读数里带 `code_version` 字段 ⇒ 能一眼看出是哪份代码产的。

## 4. 五个臂是什么

| 臂 | 含义 | 作用 |
|---|---|---|
| `B0_direct` | 1 次直调 | 基线（**单分支** ⇒ 无路径间多样性可言）|
| `B0_bestof3` | 3 次独立直调 + 机械去冗余 | ★ **等预算对照**（调用数与 W 相同）|
| `B0_frames_vote` | 每个认知帧各跑一遍 + plurality 投票 | ★ **Self-Discover 的对照**（"组合结构 vs 逐模块投票"）|
| `W_design_L2` | 认知帧解耦 + 机械汇总 | 层2「用设计的手段」|
| `W_train_L3` | 层2 + 失败驱动的动作演化 + 学出来的仲裁 | 层3「用训练/自迭代的手段」|

## 5. 判官纪律（**必读**）

* 判官必须**实测**其可复现性，不能假设 `temperature=0` 就够
  （实测 `MiniMax-M3.1-Flash-Preview`（强制 thinking）波动 **3**、`MiniMax-M2.5`（non-thinking）波动 **1**）
* **必须区分"两种 0"**：仪器层（卡片没出来）与内容层（卡片在、判定翻转）—— 在主指标上**完全一样**
* **跨判官一致**是任何架构级结论的前提
* 解析失败**必须单独计数**（`parsefail_rate`），不许混进主读数

## 6. 成本

* 生成侧与判官侧默认都用 **MiniMax 订阅（$0）**
* 跨厂商判官（OpenRouter）另计 ⇒ 建议 `--limit 8`（约 $0.3–0.6）

## 7. 已知不可用的部分（如实交代）

* **`VD_anchor_out`（锚外新增维度数）的自动判定当前不可用**：
  指纹匹配松紧两端都错（假阳性来自"锚内的也认不出来"）⇒ 论文 §3.6 与 §8 给了失效模式与正确做法
  （把语义判断交回模型：判官 A 不给 `C_t` 出岔口，判官 B 给 `C_t` + 岔口 判是否等同），**但尚未实现**
* **层 1（注意力机制层面的原因分析）**不在本包内（另一组交付）
* `remeasure.py` 的 `--reps` 需配合 `--append` 才能跨次续跑
