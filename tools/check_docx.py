#!/usr/bin/env python3
"""交付前自检：md → docx 双向校验 + 「表格前缺空行」检测。
用法：python3 check_docx.py [目录]
退出码 0 = 全绿；非 0 = 有问题（可直接进 CI/pre-commit）"""
import zipfile,re,io,os,sys,html,hashlib

def src_sha(p):
    """读出 docx 内嵌的【源 md sha256】；没有则返回 ''。
    ★ 指纹写在 docProps/core.xml 的 <cp:keywords>（OPC 已有部件 ⇒ Word 正常）。"""
    try:
        t=zipfile.ZipFile(p).read('docProps/core.xml').decode('utf-8')
    except Exception:
        return ''
    m=re.search(r'src-sha256:([0-9a-f]{64})',t)
    return m.group(1) if m else ''
D=sys.argv[1] if len(sys.argv)>1 else '.'
def dparts(p):
    x=zipfile.ZipFile(p).read('word/document.xml').decode('utf-8')
    return x, html.unescape(re.sub(r'<[^>]+>','',re.sub(r'</w:p>','\n',x)))
def norm(s):
    # ★ pandoc 会把「反斜杠 + ASCII 标点」里的反斜杠吃掉（`B\*` ⇒ 渲染成 `B*`）
    #   ⇒ 归一化时必须做同一条规则，否则「单元格零丢失」会【假报】（2026-10-24 06_L3 实测）
    s=re.sub(r'\\([!\"#\$%&\'()*+,\-./:;<=>?@\[\\\]\^_`{|}~])',r'\1',s)
    s=re.sub(r'~~|</?br\s*/?>|\\\|','',s); s=re.sub(r'[*`]','',s)
    s=s.replace('“','"').replace('”','"').replace('‘',"'").replace('’',"'")
    return re.sub(r'\s+','',s)
def split_cells(row):
    """★ 切表格单元格，**解析规则必须与 pandoc 对齐**（2026-10-24 06_L3 实踩）。

    ⇒ ① **code span 内的竖线不是分隔符**（`\`| a | b \`|` 是【一个】单元格）
    ⇒ ② **转义竖线 `\|` 不是分隔符**（它是内容的一部分）
    ⇒ ★ 旧实现直接 `split('|')` ⇒ 把「单元格里嵌表」的行数成 7/15 列 ⇒ **假阳性**。
    """
    spans=[]
    def _keep(m):
        spans.append(m.group(0)); return "\x00SPAN%d\x00" % (len(spans)-1)
    # ★ pandoc 的 code span 规则：N 个反引号开、N 个反引号闭（**双反引号要当成一个 span**）
    #   ⇒ 旧正则 `` `[^`]*` `` 会先吃掉双反引号之间的空串 ⇒ 后面的 | 被误当列分隔符 ⇒ 假阳性
    r = re.sub(r'(`+)(.*?)\1', _keep, row, flags=re.S)
    r = r.replace('\\|', '\x01')
    cells = r.strip().strip('|').split('|')
    out=[]
    for c in cells:
        c = c.replace('\x01','|')
        c = re.sub(r'\x00SPAN(\d+)\x00', lambda m: spans[int(m.group(1))], c)
        out.append(c)
    return out
def is_sep(row): return set(row.replace('|','').replace(':','').replace('-','').strip())==set()
def _trow(l):
    """★ 把一行还原成「表格行本体」⇒ **支持引用块里的表**。

    （2026-10-25 实踩：终审报告的版本台账表整张在 `> ` 引用块里 ⇒ pandoc 照渲染（docx 9 张）
      ⇒ 而旧实现只数顶层表（md 8 张）⇒ ⇒ **假报「表数不一致 md≠docx」** ⇒ 任何人写带引用块的表都会中招。）
    ⇒ 返回 None 表示「不是表格行」。
    """
    s=l.strip()
    while s.startswith('>'):
        s=s[1:].strip()
    if s.startswith('|') and s.endswith('|') and len(s)>1:
        return s
    return None
def split_tables(md):
    lines=md.split('\n'); tabs=[]; cur=None
    for i,l in enumerate(lines,1):
        row=_trow(l)
        if row is not None:
            if cur is None: cur=[]
            cur.append((i,row))
        else:
            if cur: tabs.append(cur); cur=None
    if cur: tabs.append(cur)
    return tabs
def orphan_table(md):
    """没有表头的表格碎片（块内第 2 行不是分隔行）⇒ pandoc 不认它是表，整块会掉成段落"""
    out=[]
    for t in split_tables(md):
        if len(t)<2 or not is_sep(t[1][1]):
            out.append((t[0][0], t[0][1][:60]))
    return out
def missing_blank(md):
    """pandoc 不会把「前面无空行」的表格渲染成表 ⇒ 检出它们"""
    lines=md.split('\n'); bad=[]; i=0
    while i<len(lines):
        s=lines[i].strip()
        if s.startswith('|') and s.endswith('|') and len(s)>1:
            j=i-1
            while j>=0 and lines[j].strip().startswith('|') and lines[j].strip().endswith('|'): j-=1
            if j>=0 and lines[j].strip()!='' and not lines[j].strip().startswith('#'):
                bad.append((i+1,j+1,lines[j][:60]))
            while i<len(lines) and lines[i].strip().startswith('|') and lines[i].strip().endswith('|'): i+=1
        else: i+=1
    return bad
def col_mismatch(md):
    """★ 表头 / 分隔行 / 表体 的【列数必须一致】⇒ 否则 pandoc 会按其中一种截列。

    （2026-10-24 06_L3 实踩：表头 7 列、分隔行 6 列 ⇒ pandoc 渲染出 6 列
      ⇒ 第 ⑥ 列的 7 格内容**整列消失**，而「表格数 md==docx」**照样相等**。
      ⇒ 只有「单元格零丢失」抓得到 ⇒ ★ 但那是在渲染之后；本项能在【改稿阶段】直接抓到。）
    """
    out=[]
    for t in split_tables(md):
        if len(t)<2 or not is_sep(t[1][1]):
            continue
        n_head=len(split_cells(t[0][1]))
        n_sep =len(split_cells(t[1][1]))
        if n_head!=n_sep:
            out.append((t[1][0], n_head, n_sep, '表头 %d 列 vs 分隔行 %d 列'%(n_head,n_sep)))
        for (li,l) in t[2:]:
            n_row=len(split_cells(l))
            if n_row!=n_sep:
                out.append((li, n_sep, n_row, '分隔行 %d 列 vs 该行 %d 列'%(n_sep,n_row)))
    return out
def angle_swallow(md):
    """★ 表格单元格里出现**裸尖括号** `<xxx>` ⇒ pandoc 当成 HTML 标签 ⇒ 内容在 docx 里被吞掉。

    （2026-10-25 实际踩到：`"supports_conclusions": [<结论编号>...]` ⇒ 整段从 docx 消失。）
    ★ 注意：「表格数 md==docx」**抓不到**这一类（表格数仍然相等）⇒ 只有"单元格零丢失"能抓到。
    ⇒ 修法：把 `<` `>` 换成全角〈〉，或用反斜杠转义。
    """
    out=[]
    for t in split_tables(md):
        for (li,l) in t:
            for c in split_cells(l):
                # ★ 去掉 code span（反引号内不是 HTML，pandoc 原样保留）
                c2=re.sub(r'`[^`]*`','',c)
                for m in re.finditer(r'<[A-Za-z\u4e00-\u9fff][^>]{0,40}>', c2):
                    if m.group(0).lower() in ('<br>','<br/>','<br />'):
                        continue          # ★ 表格里的合法换行
                    out.append((li, m.group(0)[:40]))
    return out
def code_block_table(md):
    """★ 缩进 ≥4 空格的表格行会被 pandoc 当成【代码块】⇒ 整张表从 docx 里消失。

    （2026-10-25 实际踩到：把表格放进列表项时按 4/5 空格缩进 ⇒ docx 里表不见了，
      而 md 侧的表格数仍是对的 ⇒ 「表格数 md==docx」这项能抓到，但成因难定位。）

    允许的例外：所在列表项的序号是两位以上（`10. ` 这类，其内容列本来就缩进 4 空格）。
    """
    lines=md.split('\n'); bad=[]
    for i,l in enumerate(lines):
        m=re.match(r'^( +)\|', l)
        if not m or len(m.group(1))<4:
            continue
        # 往上找最近的列表项
        allow=False
        for j in range(i-1, max(-1,i-12), -1):
            mm=re.match(r'^\s*(\d{2,})[.)]\s', lines[j])
            if mm: allow=True; break
            if re.match(r'^\s*[-*+]\s', lines[j]): break
        if not allow:
            bad.append((i+1, len(m.group(1)), lines[i].strip()[:60]))
    return bad
allok=True; tot=0
for f in sorted(x[:-3] for x in os.listdir(D) if x.endswith('.md')):
    fp=os.path.join(D,f+'.md'); md=io.open(fp,encoding='utf-8').read()
    dp=os.path.join(D,f+'.docx')
    if not os.path.exists(dp): print("  ❌ %s 缺 docx"%f); allok=False; continue
    # ★★ 判据：**docx 必须与源 md 同步** ⇒ ★ **用【内容指纹】判，不用文件时间戳**
    #   ⇒ 理由（2026-10-25 包级复核实踩）：★ 可复现打包 ⇒ 成员时间戳固定 ⇒ zip 不携带真实 mtime
    #     ⇒ `zipfile.extractall()` 不还原 mtime ⇒ 落盘 mtime = 解包时刻 ⇒ 由【解包顺序】决定
    #     ⇒ 成员按名排序 ⇒ .docx 排在 .md 前 ⇒ docx 早 ~1ms ⇒ ★「docx 比 md 旧」在【交付态】假红
    #     ⇒ 而且红不红**取决于用哪个工具解压** ⇒ ⇒ 判据本身不可靠 ⇒ ⇒ 指纹判据与时间戳彻底解耦
    fsha=src_sha(dp); msha=hashlib.sha256(open(fp,'rb').read()).hexdigest()
    if fsha:
        if fsha!=msha:
            print("  ⛔ %s docx 内嵌源指纹 %s… ≠ 当前 md %s… ⇒ 需重建"%(f,fsha[:12],msha[:12])); allok=False; continue
    else:
        # ★ 旧版 docx（无指纹）⇒ 回退到时间戳判据，并提示该判据在交付态不可靠
        if os.path.getmtime(dp) < os.path.getmtime(fp):
            print("  ⛔ %s docx 比 md 旧（★ 该 docx 无源指纹 ⇒ 只能用时间戳判）⇒ 需重建"%f); allok=False; continue
        print("  ⚠ %s docx 无源指纹（★ 时间戳判据在交付态可能假红 ⇒ 建议用新版 build_docx.sh 重建）"%f)
    x,dt=dparts(dp); ndt=norm(dt)
    tabs=split_tables(md); bad=[]; n=0
    for t in tabs:
        sep=len(t)>1 and is_sep(t[1][1])
        for (li,l) in (t[2:] if sep else t[1:]):
            for c in split_cells(l):
                nc=norm(c)
                if len(nc)>=3:
                    n+=1; tot+=1
                    if nc not in ndt: bad.append((li,nc[:34]))
    mm=len(re.findall(r'【待完成】',md)); mx=dt.count('【待完成】')
    mb=missing_blank(md)
    orph=orphan_table(md)
    cb=code_block_table(md)
    ang=angle_swallow(md)
    cm=col_mismatch(md)
    if cm:
        allok=False
        print("     ⛔ 表格列数不一致 L%d：%s（pandoc 会按其中一种截列 ⇒ 整列内容消失）"%(cm[0][0],cm[0][3]))
    if ang:
        allok=False
        print("     ⛔ 尖括号吞字 L%d：%s（pandoc 当 HTML 标签 ⇒ 单元格内容在 docx 里消失 ⇒ 改成全角〈〉）"%(ang[0][0],ang[0][1]))
    ok=(len(tabs)==x.count('<w:tbl>')) and not bad and mm==mx and not mb and not orph and not cb and not ang and not cm
    allok&=ok
    if cb:
        allok=False
        print("     ⛔ 代码块表格 L%d（缩进 %d 空格，pandoc 会当代码块 ⇒ 表消失）"%(cb[0][0],cb[0][1]))
    print("  %-40s 表 %2d/%-2d ｜ 单元格 %3d 丢失 %d ｜ 待完成 %d/%d ｜ 缺空行 %d ｜ 无表头碎片 %d ｜ 代码块表 %d ｜ 列数不一致 %d ｜ %s"%(
        f[:38],len(tabs),x.count('<w:tbl>'),n,len(bad),mm,mx,len(mb),len(orph),len(cb),len(cm),'✅' if ok else '❌'))
    for li,nh,nb,why in cm[:3]: print("        ⛔ L%-4d %s"%(li,why))
    for li,c in bad[:3]: print("        L%-4d %r"%(li,c))
    for li,pv,txt in mb[:3]: print("        ⛔ L%-4d 前一行 L%-4d 非空: %r"%(li,pv,txt))
    for li,txt in orph[:3]: print("        ⛔ L%-4d 无表头的表格碎片: %r"%(li,txt))
print()
print("★ 交付自检：%s（表格单元格合计 %d）"%("✅ 全绿" if allok else "❌ 有问题", tot))
sys.exit(0 if allok else 1)
