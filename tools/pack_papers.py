#!/usr/bin/env python3
"""pack_papers.py —— 交付包打包器（★ 单一代码路径 ⇒ 打包与自检不可能分叉）

★ 五条硬要求（每条都来自一次真实事故）：
  ① 非 ASCII 文件名必须带 UTF-8 标志位（0x800）⇒ 用 Python zipfile
     （系统 `zip` 不设、`zip -UN=UTF8` 也不管用 ⇒ 中文名在解压端乱码 ⇒ 清单核对直接断链）
  ② 清单必须【全量】核对，不能抽样 ⇒ 自建 SHA256SUMS.txt 并全量重算
  ③ 期望值不能来自被检查对象自己 ⇒ 内容集合取自【版本管理】的受管集（git ls-files）
  ④ ★ **可复现**：成员时间戳固定（1980-01-01 = ZIP 格式下限）⇒ ★ 清单文件的 mtime 不会随打包时刻漂移
     ⇒ **同一批文件字节 ⇒ 同包 ⇒ 同 sha256** ⇒ ★ 包 sha256 稳定标识【这一份包字节】
     （★ 边界：★ **重建 docx 会改 `dcterms:created` ⇒ 包 sha 必变**；★ **跨 zlib 实现不保证
       压缩字节相同** ⇒ 跨实现请用 `SHA256SUMS.txt` 做【内容级】核验）（附带：不泄漏打包时刻）
  ⑤ ★ **权限位由内容决定**（带 shebang ⇒ 0o755，其余 0o644）⇒ 不依赖本地 FS 权限
     ⇒ ⇒ **解包后原地重建能产出逐字节相同的包**

★ ★ 为什么打包与自检必须【同一份代码】：
  2026-10-25 实踩 —— 上一版把「打包」和「--repro 连打两次」写成两段内嵌 python：
  第二段忘了定义 `src` ⇒ `NameError` ⇒ ★ 且第二段没有 git 回退 ⇒ 无 git 环境下第二个包内容为空
  ⇒ ⇒ **同一条纪律在第一个执行点落实了、第二个没落实** ⇒ ⇒ 修法不是补那一行，是【合并成一条路径】。

★ 内容集合来源：优先 `git ls-files`（★ 期望值不来自被检查对象自己）；
  ★ 若不在 git 仓内（★ 例如从交付包解包后原地重建）⇒ 回退为【目录遍历】
  ⇒ ⇒ **交付包自带打包器 ⇒ 第三方无需 git 也能重建出逐字节相同的包**

★ 清单【自身不入清单】；清单同时回写仓内 `SHA256SUMS.txt` ⇒ **仓内与包内同一份**

用法：
  python3 tools/pack_papers.py <输出zip路径> [--repro] [--no-verify-extracted]
    --repro              连打两次到临时文件并比对 sha256 ⇒ 打印「可复现」证据
    --no-verify-extracted  跳过【交付态验收】（默认会做）
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

STAMP = (1980, 1, 1, 0, 0, 0)          # ★ 固定时间戳（ZIP 格式下限）⇒ 可复现
MANIFEST = "SHA256SUMS.txt"
EXCLUDE_DIRS = {".git", "dist", "__pycache__", ".tmp", ".mavis", ".idea"}
EXCLUDE_SUFFIX = (".part", ".pyc", ".zip")
# ★ 显式附加（即使不在受管集也要进包：★ 交付说明与验收工具是交付物的一部分）
EXTRAS = ["交付说明_四篇改稿_2026-10-24.md", "交付总览_人肉审版_2026-10-25.md",
          "tools/check_package.py"]


def repo_root():
    """★ 路径探测【不依赖 git】：★ 沙箱里 `git rev-parse --show-toplevel` 返回的是 NFS 挂载路径
    （/run/csi/mount-root/nas/…）⇒ 与 /workspace/work/… 是同一目录但【字符串不同】⇒ 不可用它定位"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _skip(name):
    if name == MANIFEST:
        return True
    if any(p in EXCLUDE_DIRS for p in name.split("/")):
        return True
    return name.endswith(EXCLUDE_SUFFIX)


def collect(root):
    """★ 受管文件集合（★ 期望值不来自被检查对象自己）"""
    names, seen = [], set()

    def add(n):
        if n and not _skip(n) and n not in seen and os.path.isfile(os.path.join(root, n)):
            seen.add(n)
            names.append(n)

    try:                                    # 优先：版本管理的受管集
        raw = subprocess.check_output(["git", "-C", root, "ls-files", "-z"])
        for b in raw.split(b"\0"):
            if b:
                add(b.decode("utf-8"))
    except Exception:
        pass
    if not names:                           # 回退：不在 git 仓内 ⇒ 目录遍历
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
            for fn in filenames:
                add(os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/"))
    for e in EXTRAS:
        add(e)
    names.sort()
    return names


def build(root, out, workdir):
    """★ 唯一的一条打包路径（★ 打包与 --repro 复用它 ⇒ 不可能分叉）"""
    names = collect(root)
    missing = [n for n in names if not os.path.isfile(os.path.join(root, n))]
    if missing:
        raise SystemExit("!! 清单里有不存在的文件：\n" + "\n".join("   - " + m for m in missing[:20]))

    # 暂存副本（zip 从副本取 ⇒ zip 与清单同源，且不含 .git）
    tree = os.path.join(workdir, "tree")
    if os.path.isdir(tree):
        shutil.rmtree(tree)
    for n in names:
        dst = os.path.join(tree, n)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(root, n), dst)

    # 清单（arcname 路径；自身不入清单）⇒ 同时回写仓内
    sums = []
    for n in names:
        h = hashlib.sha256(open(os.path.join(tree, n), "rb").read()).hexdigest()
        sums.append("%s  %s" % (h, n))
    manifest_text = "\n".join(sums) + "\n"
    with open(os.path.join(tree, MANIFEST), "w", encoding="utf-8") as f:
        f.write(manifest_text)
    try:
        with open(os.path.join(root, MANIFEST), "w", encoding="utf-8") as f:
            f.write(manifest_text)          # ★ 仓内与包内同一份
    except OSError:
        pass                               # ★ 解包后原地重建时可能只读 ⇒ 不致命

    allnames = names + [MANIFEST]
    assert len(set(allnames)) == len(allnames), "重复成员名"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n in allnames:
            src = os.path.join(tree, n)
            info = zipfile.ZipInfo(filename=n, date_time=STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            # ★★ 权限位【由内容决定】★★ ★ 不能取本地 st_mode：★ 解包时权限会丢
            #   ⇒ ⇒ 「同一内容、不同环境」重建出的字节不同 ⇒ ⇒ sha 不可复现
            with open(src, "rb") as fh:
                head = fh.read(2)
            info.external_attr = (0o755 if head == b"#!" else 0o644) << 16
            z.writestr(info, open(src, "rb").read())
    return names


def assert_zip(out):
    """★★ 产物级回读断言（★ 写完之后重新打开读字节；★ 不读中间态）★★"""
    import struct
    z = zipfile.ZipFile(out)
    assert z.testzip() is None, "zip 损坏"
    names = z.namelist()
    assert len(names) == len(set(names)), "有重复成员名"
    bad_c = bad_l = n = 0
    with open(out, "rb") as f:
        for i in z.infolist():
            if not any(ord(c) > 127 for c in i.filename):
                continue
            n += 1
            if not (i.flag_bits & 0x800):                       # 中央目录
                bad_c += 1
                print("  ✘ 中央目录缺 UTF-8 标志位：%s" % i.filename)
            f.seek(i.header_offset)
            _sig, _ver, flags = struct.unpack("<IHH", f.read(8))  # 本地文件头
            if not (flags & 0x800):
                bad_l += 1
                print("  ✘ 本地头缺 UTF-8 标志位：%s" % i.filename)
    assert bad_c == 0 and bad_l == 0, "非 ASCII 成员标志位缺失（中央 %d / 本地 %d）" % (bad_c, bad_l)
    # ★ 清单与包内成员逐条对账（★ 全量，不抽样）
    man = z.read(MANIFEST).decode("utf-8").split("\n")
    entries = 0
    for line in man:
        if not line.strip():
            continue
        h, _, p = line.partition("  ")
        entries += 1
        try:
            d = z.read(p)
        except KeyError:
            raise SystemExit("✘ 清单条目不在包内：%s" % p)
        if hashlib.sha256(d).hexdigest() != h:
            raise SystemExit("✘ 清单 sha 不符：%s" % p)
    assert entries == len(names) - 1, "清单条目数 %d ≠ 成员数 %d - 1" % (entries, len(names))
    print("★ 回读断言：非 ASCII 成员 %d 个 ⇒ 中央目录 + 本地头 的 UTF-8 标志位（0x800）全齐 ✔ ｜ 清单 %d 条逐条对账 ✔"
          % (n, entries))
    return names


def verify_extracted(out, workdir):
    """★★ 交付态验收（★ 断言必须在【交付态】读，不是在【生产态】读）★★
    ★ 解包到临时目录 ⇒ 在【解包后的那棵树】上跑：清单核对 / docx↔md 双向自检 / 原仪器
    ⇒ ★ 这一步专门抓「在仓里绿、在交付态红」的那类问题（★ 2026-10-25 实踩：
    ★   可复现打包 + extractall 不还原 mtime ⇒ 「docx 比 md 旧」在交付态假红 11 个）"""
    root = os.path.join(workdir, "extracted")
    if os.path.isdir(root):
        shutil.rmtree(root)
    os.makedirs(root)
    with zipfile.ZipFile(out) as z:
        z.extractall(root)
    steps = []
    steps.append(("清单全量核对", ["sha256sum", "-c", MANIFEST], root))
    if os.path.isdir(os.path.join(root, "papers")):
        steps.append(("docx↔md 双向自检", [sys.executable, "tools/check_docx.py", "papers"], root))
    l3 = "papers/06_L3_层3自修改_交差稿.md"
    if os.path.isfile(os.path.join(root, l3)):
        steps.append(("原仪器 check_l3", [sys.executable, "tools/check_l3.py", l3], root))
    bad = 0
    for name, cmd, cwd in steps:
        r = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        tail = r.stdout.decode("utf-8", "replace").strip().split("\n")
        ok = (r.returncode == 0)
        print("  %s 【交付态】%s（exit=%d）%s" % ("✔" if ok else "⛔", name, r.returncode,
                                                ("｜ " + tail[-1][:70]) if tail else ""))
        if not ok:
            bad += 1
            for l in tail[-8:]:
                print("      %s" % l[:110])
    if bad:
        raise SystemExit("⛔ 交付态验收失败：%d 项不通过 ⇒ 不要交付" % bad)
    print("★ 交付态验收：%d 项全绿 ✔" % len(steps))
    return root


def main(argv):
    out = argv[0] if argv else "交付包.zip"
    repro = "--repro" in argv
    verify = "--no-verify-extracted" not in argv
    root = repo_root()
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="pack_") as wd:
        names = build(root, out, wd)
        print("★ 包已写出：%s  成员 %d（清单条目 %d）" % (out, len(names) + 1, len(names)))
        assert_zip(out)

        if repro:
            print("★ 可复现性自检：★ 同一份 build() 连打两次比对 sha256 …")
            out2 = os.path.join(wd, "second.zip")
            build(root, out2, wd)
            a = hashlib.sha256(open(out, "rb").read()).hexdigest()
            b = hashlib.sha256(open(out2, "rb").read()).hexdigest()
            if a != b:
                raise SystemExit("✘ 不可复现：%s vs %s" % (a[:16], b[:16]))
            print("★ ✔ 可复现：两次打包 sha256 一致（%s…）⇒ ★ **同一批文件字节 ⇒ 同一份包 sha**"
                  "（★ 边界见 交付总览 §1：重建 docx 会改包 sha；跨 zlib 实现不保证压缩字节相同）"
                  % a[:16])

        if verify:
            print("★ 交付态验收：解包到临时目录后，在【交付态那棵树】上复跑 …")
            verify_extracted(out, wd)

    print("★ sha256: %s" % hashlib.sha256(open(out, "rb").read()).hexdigest())
    print("★ 大小: %d B" % os.path.getsize(out))
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(args + flags))
