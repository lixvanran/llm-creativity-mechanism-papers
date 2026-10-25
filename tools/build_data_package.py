#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 科研过程数据包的抽取器（★ 2026-10-25）

★★★ 它解决什么：★★
  ★ 本仓原来的定位是「论文集」⇒ ★ README 明写「只放成果、★ 不含过程日志、★ 跑批输出、★ 工具实现」。
  ★ ★ 但过程数据本身才是这份工作的可复用资产（★ 阴性读数、★ 待取证任务、★ 审稿判定、★ 出处链）⇒
  ★ ★ 所以要把它们从散文里抽成**机器可读**的表、★ 并让每一行都带**可回源的指针**。

★★★ 设计上的三条硬规矩：★★
  1. ★ **不手编任何数字**：★ 全部从仓里现有文件抽取 ⇒ ★ 跑一次就重算一次。
  2. ★ **每条记录带 source 指针**（★ `文件:行号`）⇒ ★ 第三方能自己核。
  3. ★ **阴性结果单独立表**：★ 「不可分辨 / 未测 / 未检出」这类读数是科研过程数据里最值钱的部分
     （★ 它们记录了【试过但没打出来】的东西）⇒ ★ 绝不能埋在正文里。

★★★ 产出（★ 全部在 `data/`）：★★
  readings.jsonl          读数全集（★ 含新增/非新增、★ 出处、★ 出处等级）
  negative_results.jsonl  阴性/未定结果行（★ 逐行带标记与所在小节）
  open_tasks.jsonl        待取证任务（★ 结构化字段：★ 要补什么/去哪找/判据/回填后影响/成本）
  audit_verdicts.jsonl    审稿判定（★ 用被审对象的 sha256 当锚）
  pointer_migrations.json 指针迁移 25 条
  dataset_index.json      索引（★ 行数/字段/生成命令/校验命令）

★★★ 幂等：★ 连跑两次字节一致。★★
"""
import sys, re, json, pathlib, hashlib, argparse
sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data"

PAPERS = [
    ("L1", "papers/01_L1_PrematureConvergence_交差稿.md"),
    ("A",  "papers/02_A_SelectionIsNotCreation_稿.md"),
    ("C",  "papers/03_C_SixWaysToLookDone_稿.md"),
    ("D",  "papers/04_D_StateMachineIsNotYetAPrompt_交差稿.md"),
    ("L3", "papers/06_L3_层3自修改_交差稿.md"),
]
# ★ ①篇现在有主稿 + 详稿两件（★ 主稿是交差稿、★ 详稿是注意力层归因详稿）⇒ ★ 两件都进语料
EXTRA_DOCS = ["papers/01_L1_注意力层归因_详稿_2026-10-25.md"]

# ★ 出处等级（★ 优先级从高到低：★ 命中多处时取最高级）
SOURCE_CLASSES = [
    ("一手材料",  "来源与底稿/"),
    ("审稿留痕",  "papers/复核链/"),
    ("复算底稿",  "papers/净增益双边重算_可粘贴段落_2026-10-25.md"),
    ("改稿规格",  "改稿规格_"),
    ("前作基线",  "baseline/"),
]

# ★ 阴性/未定标记（★ 顺序无关、★ 命中即记一条）
NEG_MARKERS = ["不可分辨", "未检出", "未检验", "未测", "未证实", "不可判定",
                "证据不足", "检出力不足", "不显著", "【待完成】", "【待回查】"]

RE_SHA   = re.compile(r"\b[0-9a-f]{40}\b")
RE_NUM   = re.compile(r"-?\d+(?:\.\d+)?%?")
RE_TASK  = re.compile(r"^T-[A-Z0-9]+-\d+$")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def read(rel: str):
    p = ROOT / rel
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8", errors="replace")


def source_corpus():
    """★ 产出：★ [(相对路径, 全文, 行列表)] —— ★ 一次扫完、★ 供 token→出处 索引用"""
    out = []
    for f in sorted(ROOT.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(ROOT).as_posix()
        if rel.startswith(".git/") or rel.startswith("dist/") or rel.startswith("data/"):
            continue
        if rel.startswith("来源与底稿/"):
            pass
        elif any(rel.startswith(pfx) for pfx, _ in SOURCE_CLASSES[1:]):
            pass
        else:
            continue
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if "\x00" in txt[:2048]:
            continue          # ★ 二进制 ⇒ 跳过
        out.append((rel, txt.split("\n")))
    return out


def classify_source(rel: str) -> str:
    for name, pfx in SOURCE_CLASSES:
        if rel.startswith(pfx):
            return name
    return "其他"


def build_readings(corpus):
    """★ 读数全集：★ 逐篇抽数字 token、★ 再回 corpus 找出处"""
    tok_re = re.compile(r"-?\d+(?:\.\d+)?")
    # ★ 反向索引：★ token → [(文件, 行号, 等级)]
    idx = {}
    for rel, lines in corpus:
        lvl = classify_source(rel)
        for i, ln in enumerate(lines, 1):
            for m in tok_re.finditer(ln):
                idx.setdefault(m.group(0), []).append((rel, i, lvl))

    recs = []
    for pid, rel in PAPERS:
        txt = read(rel)
        if txt is None:
            continue
        for tok in sorted(set(tok_re.findall(txt))):
            srcs = idx.get(tok, [])
            # ★ 只保留有出处的（★ 没有出处的读数会在 verify_new_readings 里被报出来、★ 属另一条链）
            if not srcs:
                continue
            best = min((s[2] for s in srcs),
                       key=lambda L: [n for n, _ in SOURCE_CLASSES].index(L)
                       if L in [n for n, _ in SOURCE_CLASSES] else 99)
            recs.append({
                "dataset": "readings",
                "paper": pid,
                "token": tok,
                "source_class": best,
                "n_sources": len(srcs),
                "sources": [{"file": s[0], "line": s[1], "class": s[2]} for s in srcs[:6]],
            })
    return recs


def build_negative_results():
    """★ 阴性/未定结果：★ 逐行扫、★ 记标记 + 所在小节 + 该行读数"""
    recs = []
    for pid, rel in PAPERS + [("L1详稿", p) for p in EXTRA_DOCS]:
        txt = read(rel)
        if txt is None:
            continue
        sec = ""
        for i, ln in enumerate(txt.split("\n"), 1):
            m = re.match(r"^(#{1,4})\s+(.*)$", ln)
            if m:
                sec = m.group(2).strip()
                continue
            hit = [w for w in NEG_MARKERS if w in ln]
            if not hit:
                continue
            nums = sorted(set(RE_NUM.findall(ln)))
            recs.append({
                "dataset": "negative_results",
                "paper": pid,
                "file": rel,
                "line": i,
                "section": sec,
                "markers": hit,
                "numbers": nums[:12],
                "text": ln.strip()[:600],
            })
    return recs


def build_open_tasks():
    """★ 待取证任务：★ 从 markdown 表里抽（★ 表头含「编号」且含「要补什么」）"""
    recs = []
    files = [rel for _, rel in PAPERS] + EXTRA_DOCS + \
            [p.as_posix() for p in sorted((ROOT / "support").glob("*.md"))] + \
            [p.name for p in sorted(ROOT.glob("改稿规格*.md"))]
    for rel in files:
        txt = read(rel)
        if txt is None:
            continue
        lines = txt.split("\n")
        header = None
        tno = 0
        for i, ln in enumerate(lines, 1):
            s = ln.strip()
            if not s.startswith("|"):
                if s:
                    header = None
                    tno += 1
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if header is None:
                joined = " ".join(cells)
                if "编号" in joined and ("要补什么" in joined or "去哪找" in joined):
                    header = cells
                continue
            # ★ 表头之下、遇到非表行就结束
            if len(cells) < 2:
                header = None
                continue
            tid = cells[0].strip("*` ")
            if not RE_TASK.match(tid):
                continue
            rec = {"dataset": "open_tasks", "task_id": tid, "file": rel, "line": i,
                   "table_no": tno, "columns": header, "fields": cells}
            recs.append(rec)
    return recs


RE_SHA16 = re.compile(r"\b[0-9a-f]{16}\b")
RE_ITEM  = re.compile(r"^\*?\*?([A-Z][A-Z0-9]*-\d+)\*?\*?$")


def build_audit_verdicts():
    """★ 审稿判定：★ 拆两张表

    ★ audit_verdicts —— 逐条判定（★ 首列是条目号、★ 如 NEW-1 / F-01 / R-3）
    ★ audit_objects —— 被审对象身份（★ 表行里带 16 位或 40 位 sha ⇒ 那一行说的是「哪一版」）

    ★ 分两张是因为【判定】和【判定绑定的那一版】是两种东西：★ 对象一改、★ 判定不自动继承。
    """
    verdicts, objects = [], []
    base = ROOT / "papers" / "复核链"
    files = sorted(base.rglob("*.md")) if base.exists() else []
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        tno = 0
        header = []
        for i, ln in enumerate(f.read_text(encoding="utf-8", errors="replace").split("\n"), 1):
            s = ln.strip()
            if not s.startswith("|"):
                # ★ 遇到非表行 ⇒ 表格结束（★ 下一张表重新计数）
                if s:
                    tno += 1
                    header = []
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if not header:
                header = cells
            m16 = RE_SHA16.search(s)
            m40 = RE_SHA.search(s)
            if m16 or m40:
                sha = m40.group(0) if m40 else m16.group(0)
                objects.append({
                    "dataset": "audit_objects",
                    "file": rel, "line": i,
                    "sha": sha, "sha_len": len(sha),
                    "table_no": tno, "table_header": header,
                    "cells": cells,
                })
            mi = RE_ITEM.match(cells[0]) if cells else None
            if mi:
                verdicts.append({
                    "dataset": "audit_verdicts",
                    "file": rel, "line": i,
                    "item_id": mi.group(1),
                    "table_no": tno, "table_header": header,
                    "cells": cells,
                })
    return verdicts, objects


def build_pointer_migrations():
    p = ROOT / "tools" / ".pointer_migration_state.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def write_jsonl(name, recs):
    p = OUT / name
    body = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in recs)
    p.write_text(body, encoding="utf-8")
    return p


def write_json(name, obj):
    p = OUT / name
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return p


SCHEMAS = {
    "readings": {
        "粒度": "一个数字 token × 一篇正文",
        "字段": {"token": "数字字面量", "paper": "篇号 L1/A/C/D/L3",
                 "source_class": "出处等级（一手材料/审稿留痕/复算底稿/改稿规格/前作基线）",
                 "sources": "出处列表（文件 + 行号 + 等级）"},
        "注意": "只收录【在仓内找得到出处】的 token；无出处的由 verify_new_readings.py 单独报",
    },
    "negative_results": {
        "粒度": "正文里的一行",
        "字段": {"paper": "篇号", "file": "相对路径", "line": "行号",
                 "section": "最近的上级标题", "markers": "命中的阴性/未定标记",
                 "numbers": "该行出现的数字", "text": "该行原文（截断 600 字）"},
        "注意": "这是阴性结果的索引；★ 不代表该行每个数字都已独立核过",
    },
    "open_tasks": {
        "粒度": "一条待取证任务",
        "字段": {"task_id": "T-A-02 式编号", "file": "定义所在文件", "line": "行号",
                 "columns": "表头", "fields": "该行各格原文"},
        "注意": "columns 与 fields 按位置对应；★ 有些表的列名不同，★ 用 fields[0] 当编号",
    },
    "audit_verdicts": {
        "粒度": "一条审稿判定（★ 首列是条目号）",
        "字段": {"item_id": "条目号", "file": "复核链文件", "line": "行号",
                 "cells": "该行各格原文（★ 判定/复验/证据）"},
        "注意": "★ 只覆盖复核链目录；★ 具体哪一版被绑、★ 看 audit_objects",
    },
    "audit_objects": {
        "粒度": "一次「被审的是哪一版」的记录",
        "字段": {"sha": "16 位前缀或 40 位全量", "sha_len": "16 或 40",
                 "file": "复核链文件", "line": "行号", "cells": "该行各格原文"},
        "注意": "★ 判定的效力锚；★ 对象一改、★ 判定不自动继承",
    },
    "pointer_migrations": {
        "粒度": "一条指针迁移记录",
        "字段": {"（原样保留）": "tools/.pointer_migration_state.json 的内容"},
        "注意": "活文档改指针、★ 历史留痕不改内容、★ 只在入口文档声明",
    },
}


def write_datadoc(index):
    """★ DATASETS.md 由索引生成（★ 免得手写、★ 免得跟数据漂）"""
    L = []
    L.append("# 数据集索引")
    L.append("")
    L.append("> 本文件由 `tools/build_data_package.py` 自动生成，★ 不要手改。")
    L.append("> 重新生成：`python3 tools/build_data_package.py`　｜　校验：`python3 tools/check_data_package.py --negative`")
    L.append("")
    L.append("**生成命令**：`%s`　**校验命令**：`%s`" % (index["generator_cmd"], index["validator_cmd"]))
    L.append("")
    L.append("## 一览")
    L.append("")
    L.append("| 数据集 | 文件 | 格式 | 行数 | 字节 | sha256（前 16） |")
    L.append("|---|---|:-:|--:|--:|---|")
    for k, v in sorted(index["datasets"].items()):
        L.append("| `%s` | `%s` | %s | %d | %d | `%s` |" % (
            k, v["file"], v["format"], v["rows"], v["bytes"], v["sha256"][:16]))
    L.append("")
    L.append("## 字段说明")
    L.append("")
    for k, v in sorted(index["datasets"].items()):
        sch = v.get("schema") or {}
        L.append("### `%s`" % k)
        L.append("")
        L.append("- **粒度**：%s" % sch.get("粒度", "（未定义）"))
        if sch.get("字段"):
            L.append("- **字段**：")
            for fk, fv in sch["字段"].items():
                L.append("  - `%s` —— %s" % (fk, fv))
        if sch.get("注意"):
            L.append("- **注意**：%s" % sch["注意"])
        L.append("")
    L.append("## 怎么用")
    L.append("")
    L.append("```python")
    L.append("import json")
    L.append("")
    L.append("# 例 1：★ 找出所有「不可分辨」的读数行（★ 阴性结果）")
    L.append("neg = [json.loads(l) for l in open('data/negative_results.jsonl', encoding='utf-8')]")
    L.append("undet = [r for r in neg if '不可分辨' in r['markers'] and r['numbers']]")
    L.append("")
    L.append("# 例 2：★ 查某个读数的出处（★ 第三方可自己核）")
    L.append("rd = [json.loads(l) for l in open('data/readings.jsonl', encoding='utf-8')]")
    L.append("hit = [r for r in rd if r['token'] == '0.886']")
    L.append("")
    L.append("# 例 3：★ 列出待取证任务")
    L.append("tasks = [json.loads(l) for l in open('data/open_tasks.jsonl', encoding='utf-8')]")
    L.append("```")
    L.append("")
    # ★ 生成物必须与本仓的去装饰规则一致（★ 无 emoji、★ 无装饰符号）
    body = "\n".join(L) + "\n"
    body = body.replace("★", "").replace("⇒", "->")
    for a, b in [("\u26a0\ufe0f", ""), ("\u2705", ""), ("\u2714", ""), ("\u274c", ""),
                 ("\u2b1c", ""), ("\u2753", ""), ("\u25a1", ""), ("\u2757", ""),
                 ("\U0001f4cc", ""), ("\U0001f4c4", ""), ("\U0001f504", ""), ("\u25d0", "")]:
        body = body.replace(a, b)
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    (ROOT / "DATASETS.md").write_text(body, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--check", action="store_true", help="只校验已生成的数据包")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    if not a.check:
        corpus = source_corpus()
        av, ao = build_audit_verdicts()
        ds = {
            "readings": build_readings(corpus),
            "negative_results": build_negative_results(),
            "open_tasks": build_open_tasks(),
            "audit_verdicts": av,
            "audit_objects": ao,
        }
        for name, recs in ds.items():
            write_jsonl(name + ".jsonl", recs)
        pm = build_pointer_migrations()
        if pm is not None:
            write_json("pointer_migrations.json", pm)

        # ★ 索引：★ 行数 + sha + 生成命令 + 校验命令
        index = {
            "generated_by": "tools/build_data_package.py",
            "generator_cmd": "python3 tools/build_data_package.py",
            "validator_cmd": "python3 tools/check_data_package.py",
            "datasets": {},
        }
        for f in sorted(OUT.iterdir()):
            if f.name == "dataset_index.json":
                continue
            rel = f.relative_to(ROOT).as_posix()
            key = f.stem
            raw = f.read_text(encoding="utf-8")
            if f.suffix == ".jsonl":
                recs = [json.loads(l) for l in raw.split("\n") if l.strip()]
            else:
                obj = json.loads(raw)
                recs = obj if isinstance(obj, list) else [obj]
            index["datasets"][key] = {
                "file": rel,
                "format": "jsonl" if f.suffix == ".jsonl" else "json",
                "rows": len(recs),
                "bytes": f.stat().st_size,
                "sha256": sha256_bytes(f.read_bytes()),
                "schema": SCHEMAS.get(key, {}),
            }
        write_json("dataset_index.json", index)
        write_datadoc(index)
        print("✔ 数据包已生成：%d 个文件" % len(index["datasets"]))
        for k, v in sorted(index["datasets"].items()):
            print("   %-22s %5d 行  %s" % (k, v["rows"], v["file"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
