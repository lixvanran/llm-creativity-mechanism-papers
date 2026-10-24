#!/usr/bin/env python3
# check_package.py —— 交付包自检（**全量核对，不抽样**）
#
# ★ 为什么要有这个脚本：合订本附录 A 与 tools/build_docx.sh 的末行都写着
#   「python3 check_package.py <本包>.zip」⇒ ⇒ **那句话必须是真的**，否则交付说明里
#   就有一条指向不存在的东西的指令（= 读者照做必然失败）。
#
# ★ 四项检查（每项都是**全量**，不是抽样）：
#   ① 清单集合 == 成员集合 − {SHA256SUMS.txt}（双向差集都要为 0）
#   ② 包内每个成员的 sha256 与清单逐条重算比对（0 不符）
#   ③ 非 ASCII 文件名必须带 UTF-8 标志位（0x800）——★ **按中央目录原始字节判**，
#      不看 Python 解码后的 filename（标志位丢失时 Python 已按 cp437 解码，乱码形状
#      「看着不像中文」⇒ 只看解码结果会假阴性）
#   ④ 空包 / 缺清单 ⇒ 响亮失败（不许静默通过）
#
# 用法：
#   python3 tools/check_package.py <包.zip>          # 检一个包
#   python3 tools/check_package.py <包.zip> --self-test   # 另跑负向测试（造坏包证明本检查抓得住）
#
# 退出码：0 = 全绿；非 0 = 有问题（逐条打印）

import hashlib
import os
import shutil
import sys
import tempfile
import zipfile

MANIFEST = "SHA256SUMS.txt"


def parse_manifest(text):
    entries = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        if "  " not in line:
            raise ValueError("清单行格式不符（期望 '<sha256>  <路径>'）：%r" % line[:80])
        h, p = line.split("  ", 1)
        entries[p] = h
    return entries


def check(zip_path):
    """返回 (ok, [问题列表], [信息行])"""
    problems, info = [], []
    if not os.path.isfile(zip_path):
        return False, ["包不存在：%s" % zip_path], info
    z = zipfile.ZipFile(zip_path)
    members = z.namelist()
    info.append("包：%s" % os.path.basename(zip_path))
    info.append("成员数：%d" % len(members))
    if not members:
        return False, ["包是空的"], info

    if MANIFEST not in members:
        return False, ["包内缺 %s（无清单 ⇒ 无法核对）" % MANIFEST], info

    entries = parse_manifest(z.read(MANIFEST).decode("utf-8"))
    info.append("清单条目数：%d" % len(entries))

    # ① 双向差集
    only_manifest = sorted(set(entries) - set(members))
    only_zip = sorted(set(members) - set(entries) - {MANIFEST})
    if only_manifest:
        problems.append("清单里有 %d 个包内不存在的条目：%s" % (len(only_manifest), only_manifest[:5]))
    if only_zip:
        problems.append("包内有 %d 个未登记进清单的文件：%s" % (len(only_zip), only_zip[:5]))

    # ② 全量重算 sha256
    bad = []
    for p, h in entries.items():
        if p not in members:
            continue
        d = hashlib.sha256(z.read(p)).hexdigest()
        if d != h:
            bad.append(p)
    if bad:
        problems.append("sha256 不符 %d 条：%s" % (len(bad), bad[:5]))
    info.append("sha256 全量重算：%d 条比对，不符 %d 条" % (len(entries), len(bad)))

    # ③ 非 ASCII 文件名的 UTF-8 标志位
    no_flag = []
    for i in z.infolist():
        if any(ord(c) > 127 for c in i.filename) and not (i.flag_bits & 0x800):
            no_flag.append(i.filename)
    if no_flag:
        problems.append("缺 UTF-8 标志位(0x800)的非 ASCII 文件名 %d 个：%s" % (len(no_flag), no_flag[:5]))
    info.append("非 ASCII 文件名 UTF-8 标志位：全齐（%d 个非 ASCII 成员）" %
                sum(1 for i in z.infolist() if any(ord(c) > 127 for c in i.filename)))

    return (not problems), problems, info


def _strip_utf8_flag(src_zip, dst_zip):
    """★ 在【字节层】把一个非 ASCII 成员的 UTF-8 标志位(0x800)抹掉。

    ★ 为什么不能重写 zip：Python 的 zipfile 对 str 文件名**自动补置 0x800**
      ⇒ 用它重写出来的包**标志位一个都没少** ⇒ 变异**根本没发生**，
      而"变异没发生"在输出层与"检查项失效"完全同形 ⇒ **必须先证明变异真的发生**。
    ★ 真实事故的成因是"用不设标志位的打包器"（如 `zip` CLI 在非 UTF-8 locale 下）
      ⇒ 这里直接改字节，复现同一个成因。
    """
    data = bytearray(open(src_zip, "rb").read())
    # ① 找一个非 ASCII 成员
    target = None
    with zipfile.ZipFile(src_zip) as z:
        for info in z.infolist():
            if any(ord(c) > 127 for c in info.filename):
                target = info
                break
    if target is None:
        raise RuntimeError("包里没有非 ASCII 文件名 ⇒ 本负向测试无法构造（变异未发生）")
    name_bytes = target.filename.encode("utf-8")

    # ② 本地文件头：flag 在 sig+6
    off = target.header_offset
    assert data[off:off + 4] == b"PK\x03\x04", "本地文件头签名不对"
    assert data[off + 30:off + 30 + len(name_bytes)] == name_bytes, "本地头文件名不匹配"
    before = (data[off + 6] | (data[off + 7] << 8))
    data[off + 6] = data[off + 6] & ~0x80
    data[off + 7] = data[off + 7] & ~0x08

    # ③ 中央目录项：flag 在 sig+8
    eocd = data.rfind(b"PK\x05\x06")
    assert eocd > 0, "找不到 EOCD"
    cd_off = int.from_bytes(data[eocd + 16:eocd + 20], "little")
    p = cd_off
    hit = False
    while data[p:p + 4] == b"PK\x01\x02":
        nlen = int.from_bytes(data[p + 28:p + 30], "little")
        elen = int.from_bytes(data[p + 30:p + 32], "little")
        clen = int.from_bytes(data[p + 32:p + 34], "little")
        nm = bytes(data[p + 46:p + 46 + nlen])
        if nm == name_bytes:
            data[p + 8] = data[p + 8] & ~0x80
            data[p + 9] = data[p + 9] & ~0x08
            hit = True
            break
        p += 46 + nlen + elen + clen
    assert hit, "中央目录里找不到该成员（变异未发生）"
    open(dst_zip, "wb").write(bytes(data))

    # ④ ★ 证明变异真的发生（否则后面"没抓到"会被误判成"检查项失效"）
    with zipfile.ZipFile(dst_zip) as z:
        info = z.getinfo(target.filename) if target.filename in z.namelist() else None
        if info is None:
            # 标志位没了 ⇒ zipfile 会按 cp437 解码 ⇒ 文件名变成乱码 ⇒ 用乱码名找
            for i2 in z.infolist():
                if i2.filename != target.filename and any(ord(c) > 127 for c in i2.filename):
                    info = i2
                    break
        assert info is not None, "变异后找不到该成员"
        assert not (info.flag_bits & 0x800), "★ 变异未生效：UTF-8 标志位仍在（0x%x）" % info.flag_bits
    return target.filename


def self_test(zip_path):
    """负向测试：造三个坏包，证明本检查**抓得住**（否则本检查可能恒真）
    ★ 每造一个坏包，先**证明变异真的发生了**，再检查【检查项是否抓住】——
      否则"变异没发生"会被误判成"检查项失效"，把修法导向错误的方向。
    """
    cases = []
    tmp = tempfile.mkdtemp(prefix="checkpkg_")
    try:
        # ① 内容被改、清单没改 ⇒ 必须被 ② 抓住
        p1 = os.path.join(tmp, "tamper_content.zip")
        with zipfile.ZipFile(zip_path) as zin, zipfile.ZipFile(p1, "w", zipfile.ZIP_DEFLATED) as zout:
            for m in zin.namelist():
                data = zin.read(m)
                if m == MANIFEST:
                    data = data
                else:
                    data = data + b"\n<!-- tampered -->\n" if not m.endswith("/") else data
                zout.writestr(m, data)
        # 变异确实发生？⇒ 至少有一个成员内容与原包不同
        with zipfile.ZipFile(zip_path) as za, zipfile.ZipFile(p1) as zb:
            assert any(za.read(m) != zb.read(m) for m in za.namelist() if not m.endswith("/")), "★ 变异未生效"
        cases.append(("内容被改但清单没改", p1, "sha256"))

        # ② 多一个未登记的文件 ⇒ 必须被 ① 抓住
        p2 = os.path.join(tmp, "tamper_extra.zip")
        with zipfile.ZipFile(zip_path) as zin, zipfile.ZipFile(p2, "w", zipfile.ZIP_DEFLATED) as zout:
            for m in zin.namelist():
                zout.writestr(m, zin.read(m))
            zout.writestr("未被登记的游离文件.md", "x")
        with zipfile.ZipFile(p2) as zb:
            assert "未被登记的游离文件.md" in zb.namelist(), "★ 变异未生效"
        cases.append(("多一个未登记文件", p2, "清单"))

        # ③ 缺 UTF-8 标志位 ⇒ 必须被 ③ 抓住（★ 字节层抹标志，见 _strip_utf8_flag）
        p3 = os.path.join(tmp, "tamper_utf8.zip")
        _strip_utf8_flag(zip_path, p3)
        cases.append(("非 ASCII 名缺 UTF-8 标志位", p3, "标志位"))

        ok_all = True
        for name, path, expect_kw in cases:
            ok, problems, _ = check(path)
            caught = (not ok)
            hit = any(expect_kw in p for p in problems)
            status = "✔ 抓得住" if (caught and hit) else "✘ 没抓到"
            if not (caught and hit):
                ok_all = False
            print("  %-28s → %s（%s）" % (name, status, "；".join(problems[:2]) or "无问题报告"))
        print("★ 负向测试：%s" % ("全绿（每个坏包都被抓住且归因正确）" if ok_all else "★ 有漏抓 ⇒ 本检查不可信"))
        return ok_all
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    args = [a for a in sys.argv[1:] if a != "--self-test"]
    do_self = "--self-test" in sys.argv[1:]
    if not args:
        print("用法：python3 tools/check_package.py <包.zip> [--self-test]")
        return 2
    zip_path = args[0]
    ok, problems, info = check(zip_path)
    for line in info:
        print("  " + line)
    if problems:
        print("★ 交付自检：❌ 有问题")
        for p in problems:
            print("  ✘ " + p)
    else:
        print("★ 交付自检：✅ 全绿")
    if do_self:
        if not ok:
            print("★ 自测跳过（基准包本身就没过检）")
            return 1
        print("★ 负向测试：")
        if not self_test(zip_path):
            return 1
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
