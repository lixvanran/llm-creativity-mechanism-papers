#!/usr/bin/env python3
"""交付前自检：md → docx 双向校验 + 「表格前缺空行」检测。
用法：python3 check_docx.py [目录]
退出码 0 = 全绿；非 0 = 有问题（可直接进 CI/pre-commit）"""
import zipfile,re,io,os,sys,html
D=sys.argv[1] if len(sys.argv)>1 else '.'
def dparts(p):
    x=zipfile.ZipFile(p).read('word/document.xml').decode('utf-8')
    return x, html.unescape(re.sub(r'<[^>]+>','',re.sub(r'</w:p>','\n',x)))
def norm(s):
    s=re.sub(r'~~|</?br\s*/?>|\\\|','',s); s=re.sub(r'[*`]','',s)
    s=s.replace('“','"').replace('”','"').replace('‘',"'").replace('’',"'")
    return re.sub(r'\s+','',s)
def is_sep(row): return set(row.replace('|','').replace(':','').replace('-','').strip())==set()
def split_tables(md):
    lines=md.split('\n'); tabs=[]; cur=None
    for i,l in enumerate(lines,1):
        s=l.strip()
        if s.startswith('|') and s.endswith('|') and len(s)>1:
            if cur is None: cur=[]
            cur.append((i,s))
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
def angle_swallow(md):
    """★ 表格单元格里出现**裸尖括号** `<xxx>` ⇒ pandoc 当成 HTML 标签 ⇒ 内容在 docx 里被吞掉。

    （2026-10-25 实际踩到：`"supports_conclusions": [<结论编号>...]` ⇒ 整段从 docx 消失。）
    ★ 注意：「表格数 md==docx」**抓不到**这一类（表格数仍然相等）⇒ 只有"单元格零丢失"能抓到。
    ⇒ 修法：把 `<` `>` 换成全角〈〉，或用反斜杠转义。
    """
    out=[]
    for t in split_tables(md):
        for (li,l) in t:
            for c in l.strip().strip('|').split('|'):
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
    x,dt=dparts(dp); ndt=norm(dt)
    tabs=split_tables(md); bad=[]; n=0
    for t in tabs:
        sep=len(t)>1 and is_sep(t[1][1])
        for (li,l) in (t[2:] if sep else t[1:]):
            for c in l.strip().strip('|').split('|'):
                nc=norm(c)
                if len(nc)>=3:
                    n+=1; tot+=1
                    if nc not in ndt: bad.append((li,nc[:34]))
    mm=len(re.findall(r'【待完成】',md)); mx=dt.count('【待完成】')
    mb=missing_blank(md)
    orph=orphan_table(md)
    cb=code_block_table(md)
    ang=angle_swallow(md)
    if ang:
        allok=False
        print("     ⛔ 尖括号吞字 L%d：%s（pandoc 当 HTML 标签 ⇒ 单元格内容在 docx 里消失 ⇒ 改成全角〈〉）"%(ang[0][0],ang[0][1]))
    ok=(len(tabs)==x.count('<w:tbl>')) and not bad and mm==mx and not mb and not orph and not cb and not ang
    allok&=ok
    if cb:
        allok=False
        print("     ⛔ 代码块表格 L%d（缩进 %d 空格，pandoc 会当代码块 ⇒ 表消失）"%(cb[0][0],cb[0][1]))
    print("  %-40s 表 %2d/%-2d ｜ 单元格 %3d 丢失 %d ｜ 待完成 %d/%d ｜ 缺空行 %d ｜ 无表头碎片 %d ｜ 代码块表 %d ｜ %s"%(
        f[:38],len(tabs),x.count('<w:tbl>'),n,len(bad),mm,mx,len(mb),len(orph),len(cb),'✅' if ok else '❌'))
    for li,c in bad[:3]: print("        L%-4d %r"%(li,c))
    for li,pv,txt in mb[:3]: print("        ⛔ L%-4d 前一行 L%-4d 非空: %r"%(li,pv,txt))
    for li,txt in orph[:3]: print("        ⛔ L%-4d 无表头的表格碎片: %r"%(li,txt))
print()
print("★ 交付自检：%s（表格单元格合计 %d）"%("✅ 全绿" if allok else "❌ 有问题", tot))
sys.exit(0 if allok else 1)
