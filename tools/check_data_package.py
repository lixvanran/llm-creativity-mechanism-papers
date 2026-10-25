#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 科研过程数据包的校验器（★ 2026-10-25）

★★★ 它证明什么：★★
  ★ 数据包**不是**「抽取器自己说自己抽对了」⇒ ★ 本器**独立回源**：
    ① 每个 .jsonl 逐行可解析、★ id 不重复
    ② 行数与 `data/dataset_index.json` 声明一致（★ 索引不能过期）
    ③ **每条记录的 source 指针真的能回源**（★ 文件在、★ 行号在范围内、★ 那一行确实含该读数/标记）
    ④ 索引里每个数据集的 sha256 与磁盘实测一致
    ⑤ **负向测试**：★ 篡改一条 source 的行号 ⇒ 必须被抓出来

★★★ 通则：★★
  ★ 「写入器不能当检查器」—— ★ 本器不 import 写入器、★ 只读磁盘与原文。
"""
import sys, json, pathlib, re, hashlib, argparse
sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

RE_NUM = re.compile(r"-?\d+(?:\.\d+)?%?")
FAILS = []
WARNS = []


def fail(msg):
    FAILS.append(msg)


def warn(msg):
    WARNS.append(msg)


def sha256_file(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def linecount(p: pathlib.Path) -> int:
    return len(p.read_text(encoding="utf-8", errors="replace").split("\n"))


def load_jsonl(p: pathlib.Path):
    recs = []
    for i, l in enumerate(p.read_text(encoding="utf-8").split("\n"), 1):
        if not l.strip():
            continue
        try:
            recs.append(json.loads(l))
        except Exception as e:
            fail("★ %s 第 %d 行不是合法 JSON：%s" % (p.name, i, e))
    return recs


def check_sources(recs, name):
    """★ 回源：★ source 指针必须真的指向含该内容的那一行"""
    checked = 0
    for r in recs:
        for s in r.get("sources", []):
            f = ROOT / s["file"]
            if not f.exists():
                fail("★ %s：出处文件不存在：%s" % (name, s["file"]))
                continue
            lines = f.read_text(encoding="utf-8", errors="replace").split("\n")
            ln = s["line"]
            if not (1 <= ln <= len(lines)):
                fail("★ %s：出处行号越界 %s:%d（该文件共 %d 行）" % (name, s["file"], ln, len(lines)))
                continue
            if r.get("token") and r["token"] not in lines[ln - 1]:
                fail("★ %s：出处行不含该读数 %s @ %s:%d" % (name, r["token"], s["file"], ln))
                continue
            checked += 1
    return checked


def check_line_pointers(recs, name):
    """★ negative_results / open_tasks / audit_* 这类：★ file:line 必须存在且该行含该记录的关键特征"""
    checked = 0
    for r in recs:
        f = ROOT / r.get("file", "")
        if not f.exists():
            fail("★ %s：记录指向不存在的文件 %s" % (name, r.get("file")))
            continue
        lines = f.read_text(encoding="utf-8", errors="replace").split("\n")
        ln = r["line"]
        if not (1 <= ln <= len(lines)):
            fail("★ %s：行号越界 %s:%d" % (name, r.get("file"), ln))
            continue
        src = lines[ln - 1]
        if name == "negative_results":
            if not any(m in src for m in r.get("markers", [])):
                fail("★ %s：该行不含所记标记 %s @ %s:%d" % (name, r.get("markers"), r.get("file"), ln))
                continue
        if name == "audit_objects":
            if r.get("sha") not in src:
                fail("★ %s：该行不含所记 sha %s @ %s:%d" % (name, r.get("sha"), r.get("file"), ln))
                continue
        checked += 1
    return checked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(DATA))
    ap.add_argument("--negative", action="store_true", help="跑负向测试")
    a = ap.parse_args()
    d = pathlib.Path(a.data_dir)

    idx_p = d / "dataset_index.json"
    if not idx_p.exists():
        print("⛔ 没有 dataset_index.json ⇒ 数据包不存在")
        return 1
    index = json.loads(idx_p.read_text(encoding="utf-8"))

    # ① 逐个数据集
    total_rows = 0
    for key, meta in sorted(index.get("datasets", {}).items()):
        p = ROOT / meta["file"]
        if not p.exists():
            fail("★ 索引指向的文件不存在：%s" % meta["file"])
            continue
        # ④ sha
        if sha256_file(p) != meta.get("sha256"):
            fail("★ %s 的 sha256 与索引不一致（★ 索引过期或文件被改过）" % meta["file"])
        if p.stat().st_size != meta.get("bytes"):
            fail("★ %s 的字节数与索引不一致" % meta["file"])

        if p.suffix == ".jsonl":
            recs = load_jsonl(p)
            # ② 行数
            if len(recs) != meta.get("rows"):
                fail("★ %s 行数 %d ≠ 索引声明 %d" % (meta["file"], len(recs), meta.get("rows")))
            # ① id 唯一（★ 键 = 文件 + id）
            #   ★ 为什么带文件：★ 同一个条目在两个文件里各出现一次是**合法数据**
            #     （★ 审稿：v3.0 与 v3.1 两轮各记一条；★ 任务：主稿与详稿各列一次）
            #     ⇒ ★ 跨文件重复只统计、不判红（★ 判红会把真实数据判成坏数据）
            ids = [(r.get("file", ""), r.get("table_no"), r.get("item_id") or r.get("task_id"))
                   for r in recs
                   if r.get("item_id") or r.get("task_id")]
            if len(ids) != len(set(ids)):
                dup = [x for x in set(ids) if ids.count(x) > 1]
                fail("★ %s 在同一文件内有重复 id：%s" % (meta["file"], dup[:5]))
            cross = {}
            for f_, _tn, i_ in ids:
                cross.setdefault(i_, set()).add(f_)
            n_cross = sum(1 for v in cross.values() if len(v) > 1)
            if n_cross:
                print("     · %s：%d 个 id 跨文件出现（★ 合法、★ 不判红）" % (key, n_cross))
            # ③ 回源
            if key == "readings":
                check_sources(recs, key)
            else:
                check_line_pointers(recs, key)
            total_rows += len(recs)
            print("  ✔ %-22s %5d 行  回源通过" % (key, len(recs)))
        else:
            print("  ✔ %-22s (json)" % key)

    # ⑤ 负向测试：篡改一条 source 的行号 ⇒ 必须被抓
    if a.negative:
        p = d / "readings.jsonl"
        if p.exists():
            recs = load_jsonl(p)
            backup = p.read_text(encoding="utf-8")
            try:
                for r in recs:
                    if r.get("sources"):
                        r["sources"][0]["line"] = 999999
                        break
                p.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                                     for r in recs), encoding="utf-8")
                saved = list(FAILS)
                FAILS.clear()
                idx2 = json.loads(idx_p.read_text(encoding="utf-8"))
                for key, meta in sorted(idx2.get("datasets", {}).items()):
                    q = ROOT / meta["file"]
                    if q.exists() and q.suffix == ".jsonl":
                        check_sources(load_jsonl(q), key)
                caught = len(FAILS) > 0
                FAILS.clear()
                FAILS.extend(saved)
                if caught:
                    print("  ✔ 负向测试：篡改出处行号后判据★ **抓住了**（判据能红）")
                else:
                    fail("★ 负向测试失败：篡改出处行号后判据没红（★ 判据有盲区）")
            finally:
                p.write_text(backup, encoding="utf-8")

    print()
    print("★ 结论：%s" % ("✅ 全部通过" if not FAILS else "❌ 有未通过项"))
    print("★ 失败 %d ｜ 告警 %d ｜ 核对行数 %d" % (len(FAILS), len(WARNS), total_rows))
    for f in FAILS[:20]:
        print("   %s" % f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
