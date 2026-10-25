#!/usr/bin/env python3
# check_docx_freshness.py —— ★ 只读：核 docx 内嵌的源 md 指纹 vs 当前 md 指纹
#
# ★ 为什么需要它（★ 来自 ④D 篇的一次真实踩坑）：
#   `tools/embed_src_sha.py` 是【写入器】：它把【当前 md 的 sha256】盖进 docx 的
#   docProps/core.xml ⇒ ⇒ ★★★ **对着一份过期的 docx 跑它，会把"可检出的不同步"
#   变成"查不出的不同步"** ⇒ 指纹变绿，内容还是旧的 ⇒ ★ 比不做指纹更危险。
#   ⇒ ⇒ **正确顺序永远是：① 先用 md 重建 docx → ② 再 embed 指纹 → ③ 再跑本检查器**
#   ⇒ ⇒ 本脚本只做第 ③ 步，★ **不写任何文件**。
#
# 用法：
#   python3 check_docx_freshness.py            # 扫全仓 papers/*.docx
#   python3 check_docx_freshness.py <目录>      # 扫指定目录
# 退出码：0 = 全一致；1 = 有不一致或缺指纹
import hashlib
import os
import re
import sys
import zipfile

CORE = "docProps/core.xml"
TAG_RE = re.compile(r"src-sha256:([0-9a-f]{64})")


def embedded_sha(docx):
    """返回 (内嵌指纹 or None, 读到的 core.xml or None)"""
    try:
        with zipfile.ZipFile(docx) as z:
            if CORE not in z.namelist():
                return None, None
            core = z.read(CORE).decode("utf-8", errors="replace")
    except Exception as e:                      # 坏 zip / 缺 core
        return None, "ERR:%s" % e
    m = TAG_RE.search(core)
    return (m.group(1) if m else None), core


def main(target):
    rows, bad = [], []
    docxs = []
    for dirpath, _dirs, files in os.walk(target):
        for f in files:
            if f.endswith(".docx"):
                docxs.append(os.path.join(dirpath, f))
    for docx in sorted(docxs):
        md = docx[:-5] + ".md"
        name = os.path.basename(docx)
        if not os.path.isfile(md):
            rows.append((name, "★ 无同名 md", "", ""))
            bad.append(name)
            continue
        emb, err = embedded_sha(docx)
        cur = hashlib.sha256(open(md, "rb").read()).hexdigest()
        if emb is None:
            rows.append((name, "★ 无指纹（未 embed）", "", cur))
            bad.append(name)
        elif emb != cur:
            rows.append((name, "★ 不一致 ⇒ docx 落后于 md", emb, cur))
            bad.append(name)
        else:
            rows.append((name, "✔ 一致", emb, cur))

    w = max((len(r[0]) for r in rows), default=10) + 2
    print("=== docx 源指纹 vs 当前 md 指纹（只读检查）===")
    for name, st, emb, cur in rows:
        print("  %-*s %s" % (w, name, st))
        if st.startswith("★") and emb:
            print("      内嵌 %s… / 当前 md %s…" % (emb[:16], cur[:16]))
    print("\n合计 %d 个 docx；%d 个需要重建或重新 embed。" % (len(rows), len(bad)))
    if bad:
        print("  ⇒ ★ **重建 docx 之后**再跑 `embed_src_sha.py`，★ **不要对旧 docx 直接 embed**"
              "（那会让指纹变绿而内容仍旧）。")
    return 1 if bad else 0


if __name__ == "__main__":
    tgt = sys.argv[1] if len(sys.argv) > 1 else "papers"
    sys.exit(main(tgt))
