# baseline · 本轮改稿前的快照

★ **基线 commit = `8649661`**（★ 本轮改稿开始前的仓内状态）
★ **这些文件是原样拷贝，★ 一个字未改**（★ 用来给 `tools/check_cluster_consistency.py` 提供**不依赖 git** 的基线）

★ **为什么需要**：★ 验收器的 **S1「数字零改动」** 与 **S2「标记不减」** 都是「逐篇 vs 基线」的判据 ⇒ ★ **基线来自 `git show`，★ 而交付包里没有 `.git`** ⇒ ★ **收件人拿到包，S1 这条最重的判据直接跑不起来** ⇒ ★ **有了这个目录，`--baseline-dir baseline` 就能在交付态核**。

★ **核验**：
```bash
python3 tools/check_cluster_consistency.py --baseline-dir baseline
```

★ ★ **对照表见 `baseline/BASELINE_SHA256.txt`**（★ 每个文件一个 sha256）
