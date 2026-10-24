#!/usr/bin/env python3
# embed_src_sha.py —— 把【源 md 的 sha256】写进 docx 的 docProps/core.xml
#
# ★ 为什么需要它（★ 来自一次包级复核的实踩）：
#   原本「docx 是否比 md 新」用**文件时间戳**判 ⇒ ★ 在【可复现打包】的交付态里会**必然假红**：
#     ① 可复现打包 ⇒ zip 成员时间戳固定为 1980-01-01 ⇒ **zip 不携带真实 mtime**
#     ② `zipfile.extractall()` **不还原 mtime**（`unzip` 才还原）⇒ 落盘 mtime = 解包时刻
#     ③ 成员按名排序 ⇒ `.docx` 排在 `.md` 之前 ⇒ docx 早 ~1ms ⇒ ⇒ 「docx 比 md 旧」
#   ⇒ ★ 而且红不红**取决于用哪个工具解压** ⇒ ⇒ 判据本身不可靠
#   ⇒ ⇒ 修法：★ **指纹判据**——把源 md 的 sha256 写进 docx ⇒ 新鲜度按**内容**判 ⇒ 与时间戳彻底解耦
#
# ★ 落在哪儿：docProps/core.xml 的 `<cp:keywords>`（★ OPC 已有部件 ⇒ Word 正常、不报损坏）
#   ⇒ ★ 第三方核验一行就够：
#       unzip -p x.docx docProps/core.xml | grep -o 'src-sha256:[0-9a-f]\{64\}'
#       sha256sum x.md
#
# 用法：python3 embed_src_sha.py <源.md> <目标.docx>
import hashlib
import os
import re
import sys
import zipfile

CORE = "docProps/core.xml"
TAG_RE = re.compile(r"src-sha256:([0-9a-f]{64})")


def main(md, docx):
    if not os.path.isfile(md) or not os.path.isfile(docx):
        print("  ⛔ 缺文件：%s / %s" % (md, docx))
        return 2
    sha = hashlib.sha256(open(md, "rb").read()).hexdigest()
    tag = "src-sha256:%s" % sha

    with zipfile.ZipFile(docx) as z:
        infos = z.infolist()
        data = {i.filename: z.read(i.filename) for i in infos}

    if CORE not in data:
        print("  ⛔ %s 缺 %s（不是 pandoc 产出的 docx？）" % (docx, CORE))
        return 2

    txt = data[CORE].decode("utf-8")
    if "<cp:keywords>" in txt:
        new = re.sub(r"<cp:keywords>.*?</cp:keywords>",
                     "<cp:keywords>%s</cp:keywords>" % tag, txt, count=1, flags=re.S)
    elif "<cp:keywords/>" in txt:
        new = txt.replace("<cp:keywords/>", "<cp:keywords>%s</cp:keywords>" % tag, 1)
    else:
        new = txt.replace("</cp:coreProperties>",
                          "<cp:keywords>%s</cp:keywords></cp:coreProperties>" % tag, 1)
    if new == txt and tag not in txt:
        print("  ⛔ 未能写入指纹（core.xml 结构异常）")
        return 3
    data[CORE] = new.encode("utf-8")

    # ★ 写盘（原子）
    tmp = docx + ".part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for i in infos:
            zi = zipfile.ZipInfo(filename=i.filename, date_time=i.date_time)
            zi.compress_type = i.compress_type
            zi.create_system = i.create_system
            zi.external_attr = i.external_attr
            zi.comment = i.comment
            z.writestr(zi, data[i.filename])
    os.replace(tmp, docx)

    # ★★ 产物级回读断言（★ 写完之后重新打开读字节；★ 不读中间态）
    with zipfile.ZipFile(docx) as z:
        assert z.testzip() is None, "zip 损坏"
        assert z.namelist() == [i.filename for i in infos], "成员列表/顺序变了"
        for i in infos:
            if i.filename == CORE:
                continue
            assert z.read(i.filename) == data[i.filename], "非 core 成员被改动：%s" % i.filename
        got = TAG_RE.search(z.read(CORE).decode("utf-8"))
        assert got and got.group(1) == sha, "回读指纹不符"
    print("  ✔ %s  内嵌源指纹 %s…" % (os.path.basename(docx), sha[:16]))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
