# 表T1 · 通道健康（★ 独立重算，见 `fix_calllog_fields.py`）


| 项 | 值 |
|---|---:|
| n_groups | 9 |
| n_arms | 5 |
| n_calls_total | 254 |
| n_calls_failed | 0 |
| n_calls_empty | 143 |
| n_branch_deficit | 36 |
| channel_health | 0.437 |
| effort | medium |
| model | MiniMax-M3 |

> ⚠️ **本次跑批的 `channel_health` 用的是修正后的判据**（`has_content` + `finish_reason=='exception'` + `content_len==0`）
