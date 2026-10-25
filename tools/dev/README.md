# tools/dev · 这一轮的一次性修稿脚本（**第三方不需要运行**）

**这些脚本会改写仓内文件**（`papers/*.md`、`support/*.md`、`tools/*.md`），
**第三方误跑会改动交付内容**，**它们留在包里，只是为了留过程史**
（记忆铁律：**过程史只有推分支才活**；沙箱重置会同时毁内容与过程）。

**它们对应的"改完后的状态"才是交付面**（`papers/` / `support/` 下的文件）。
**验收请用 `tools/` 下的只读检查器，不要跑这里的脚本。**

| 脚本 | 它改了什么 | 幂等性 |
|---|---|---|
| `_fix_f1_f2_f8.py` | 提纲的注意力红线矛盾（F1）＋「47 而非 36×36」（F2）＋ 验收器基线与失效文件引用（F8） | **锚点不匹配即退出 1**（改过之后再跑会报错，不会重复应用）|
| `_fix_bad_pointers.py` | 指针迁移留下的三处坏指针（`§6.5b` / `§1.2b` / `§§3.1`） | 同上 |
| `_fix_carriers_netgain.py` | 跨篇载体上「净增益口径未完成（未算『丢失』侧）」的过时表述 | 同上 |

**只读检查器（在 `tools/` 下，第三方应该跑这些）**：
`check_cluster_consistency.py`（簇级一致性 S1–S10）｜`verify_pointer_migration.py`（指针迁移对拍）｜
`check_docx_freshness.py`（docx↔md 指纹）｜`check_docx.py`｜`check_package.py`｜
`calc_net_gain.py`（② 篇双边净增益重算，零 API）
