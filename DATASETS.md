# 数据集索引

> 本文件由 `tools/build_data_package.py` 自动生成， 不要手改。
> 重新生成：`python3 tools/build_data_package.py`　｜　校验：`python3 tools/check_data_package.py --negative`

**生成命令**：`python3 tools/build_data_package.py`　**校验命令**：`python3 tools/check_data_package.py`

## 一览

| 数据集 | 文件 | 格式 | 行数 | 字节 | sha256（前 16） |
|---|---|:-:|--:|--:|---|
| `audit_objects` | `data/audit_objects.jsonl` | jsonl | 23 | 11005 | `97955780faeb6b3f` |
| `audit_verdicts` | `data/audit_verdicts.jsonl` | jsonl | 108 | 53626 | `be3859557d831220` |
| `negative_results` | `data/negative_results.jsonl` | jsonl | 475 | 298359 | `84db49c62e57fa22` |
| `open_tasks` | `data/open_tasks.jsonl` | jsonl | 45 | 26924 | `c5519e1d45f71a6a` |
| `pointer_migrations` | `data/pointer_migrations.json` | json | 1 | 124 | `edb15e71a7f72501` |
| `readings` | `data/readings.jsonl` | jsonl | 1678 | 1149330 | `7afe815faf742b4a` |

## 字段说明

### `audit_objects`

- **粒度**：一次「被审的是哪一版」的记录
- **字段**：
  - `sha` —— 16 位前缀或 40 位全量
  - `sha_len` —— 16 或 40
  - `file` —— 复核链文件
  - `line` —— 行号
  - `cells` —— 该行各格原文
- **注意**： 判定的效力锚； 对象一改、 判定不自动继承

### `audit_verdicts`

- **粒度**：一条审稿判定（ 首列是条目号）
- **字段**：
  - `item_id` —— 条目号
  - `file` —— 复核链文件
  - `line` —— 行号
  - `cells` —— 该行各格原文（ 判定/复验/证据）
- **注意**： 只覆盖复核链目录； 具体哪一版被绑、 看 audit_objects

### `negative_results`

- **粒度**：正文里的一行
- **字段**：
  - `paper` —— 篇号
  - `file` —— 相对路径
  - `line` —— 行号
  - `section` —— 最近的上级标题
  - `markers` —— 命中的阴性/未定标记
  - `numbers` —— 该行出现的数字
  - `text` —— 该行原文（截断 600 字）
- **注意**：这是阴性结果的索引； 不代表该行每个数字都已独立核过

### `open_tasks`

- **粒度**：一条待取证任务
- **字段**：
  - `task_id` —— T-A-02 式编号
  - `file` —— 定义所在文件
  - `line` —— 行号
  - `columns` —— 表头
  - `fields` —— 该行各格原文
- **注意**：columns 与 fields 按位置对应； 有些表的列名不同， 用 fields[0] 当编号

### `pointer_migrations`

- **粒度**：一条指针迁移记录
- **字段**：
  - `（原样保留）` —— tools/.pointer_migration_state.json 的内容
- **注意**：活文档改指针、 历史留痕不改内容、 只在入口文档声明

### `readings`

- **粒度**：一个数字 token × 一篇正文
- **字段**：
  - `token` —— 数字字面量
  - `paper` —— 篇号 L1/A/C/D/L3
  - `source_class` —— 出处等级（一手材料/审稿留痕/复算底稿/改稿规格/前作基线）
  - `sources` —— 出处列表（文件 + 行号 + 等级）
- **注意**：只收录【在仓内找得到出处】的 token；无出处的由 verify_new_readings.py 单独报

## 怎么取这些文件

| 情形 | 怎么取 |
|---|---|
| 正常网络 | `git clone https://github.com/lixvanran/llm-creativity-mechanism-papers.git` 后直接读 |
| 只想拿一个小于 1 MB 的文件 | `GET /repos/lixvanran/llm-creativity-mechanism-papers/contents/<路径>?ref=main` |
| 拿大于 1 MB 的文件（ `readings.jsonl` 约 1.1 MB） | contents API 不内联； 用 `GET /git/blobs/<blob sha>` 并带 `Accept: application/vnd.github.raw`， 或直接 clone |
| 沙箱 / 受限网络 | `raw.githubusercontent.com` 可能被掐； 走 API 或 clone |

## 怎么用

```python
import json

# 例 1： 找出所有「不可分辨」的读数行（ 阴性结果）
neg = [json.loads(l) for l in open('data/negative_results.jsonl', encoding='utf-8')]
undet = [r for r in neg if '不可分辨' in r['markers'] and r['numbers']]

# 例 2： 查某个读数的出处（ 第三方可自己核）
rd = [json.loads(l) for l in open('data/readings.jsonl', encoding='utf-8')]
hit = [r for r in rd if r['token'] == '0.886']

# 例 3： 列出待取证任务
tasks = [json.loads(l) for l in open('data/open_tasks.jsonl', encoding='utf-8')]
```

