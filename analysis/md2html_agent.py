#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把《家庭网络智能体协同的承载边界》markdown 初稿转为自包含 HTML。

特性：内嵌图片 base64；MathJax（SVG）离线渲染；<sup> 引用上标透传；
多行 $$ 公式；表题；草稿状态注记框；按锚点文本插图并生成目次。
"""
import base64
import html
import os
import re

MD = r"D:\工作区\家庭网络智能体协同承载边界论文\04_论文初稿_v1.md"
FIGDIR = r"D:\工作区\家庭网络智能体协同承载边界论文\figs"
OUT = r"D:\工作区\家庭网络智能体协同承载边界论文\04_论文初稿_v1.html"
MJ = r"D:\工作区\ns3_work\mathjax-tex-svg.js"

md = open(MD, encoding="utf-8").read().replace("\r\n", "\n")
lines = md.split("\n")

# ---------------- 块解析 ----------------
blocks = []          # (kind, payload)
title = ""
i = 0
while i < len(lines):
    s = lines[i].strip()
    if not s or s == "---":
        i += 1
        continue
    if s.startswith("# ") and not title:
        title = s[2:].strip()
        i += 1
        continue
    if s.startswith("```"):                       # 参考文献围栏
        i += 1
        while i < len(lines) and not lines[i].strip().startswith("```"):
            t = lines[i].strip()
            if t:
                blocks.append(("ref", t))
            i += 1
        i += 1
        continue
    if s.startswith(">"):                         # 草稿注记
        note = []
        while i < len(lines) and lines[i].strip().startswith(">"):
            note.append(lines[i].strip().lstrip(">").strip())
            i += 1
        blocks.append(("note", " ".join(x for x in note if x)))
        continue
    if s == "## 摘要":
        i += 1
        abs_text = []
        while i < len(lines):
            t = lines[i].strip()
            if t.startswith("**关键词**"):
                break
            if t and t != "---":
                abs_text.append(t)
            i += 1
        blocks.append(("abstract", " ".join(abs_text)))
        continue
    if s.startswith("### "):
        blocks.append(("h3", s[4:].strip()))
        i += 1
        continue
    if s.startswith("## "):
        blocks.append(("h2", s[3:].strip()))
        i += 1
        continue
    if s.startswith("|"):
        rows = []
        while i < len(lines) and lines[i].strip().startswith("|"):
            rows.append(lines[i].strip())
            i += 1
        blocks.append(("table", rows))
        continue
    if s.startswith("$$"):                        # 公式（可跨行）
        if s.endswith("$$") and len(s) > 4:
            blocks.append(("eq", s[2:-2].strip()))
            i += 1
            continue
        buf = [s[2:]] if len(s) > 2 else []
        i += 1
        while i < len(lines):
            t = lines[i].strip()
            if t.endswith("$$"):
                if len(t) > 2:
                    buf.append(t[:-2])
                break
            buf.append(t)
            i += 1
        i += 1
        blocks.append(("eq", " ".join(x for x in buf if x)))
        continue
    if re.match(r"^\*\*表 \d", s):
        blocks.append(("tabcap", s))
        i += 1
        continue
    if s.startswith("- "):
        items = []
        while i < len(lines) and lines[i].strip().startswith("- "):
            items.append(lines[i].strip()[2:])
            i += 1
        blocks.append(("ul", items))
        continue
    if re.match(r"^\d+\.\s", s):
        items = []
        while i < len(lines) and re.match(r"^\d+\.\s", lines[i].strip()):
            items.append(re.sub(r"^\d+\.\s+", "", lines[i].strip()))
            i += 1
        blocks.append(("ol", items))
        continue
    if s.startswith("**关键词**"):
        blocks.append(("keywords", s))
        i += 1
        continue
    para = [s]
    i += 1
    while i < len(lines):
        t = lines[i].strip()
        if (not t or t == "---" or t.startswith(("#", "|", "- ", ">", "```", "$$"))
                or re.match(r"^\d+\.\s", t) or re.match(r"^\*\*表 \d", t)):
            break
        para.append(t)
        i += 1
    blocks.append(("p", " ".join(para)))


def inline2(t):
    """转义 HTML，但透传 <sup>；处理 **粗体**、`代码`、\\_。"""
    t = t.replace("<sup>", "«sup»").replace("</sup>", "«/sup»")
    t = html.escape(t, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = t.replace("\\_", "_")
    t = t.replace("«sup»", "<sup>").replace("«/sup»", "</sup>")
    return t


# ---------------- 图表定义 ----------------
FIGS = {
    "fig01_arch.png": ("图 1",
        "三层参考架构与两个独立开销项：① 多播发现的空口竞争（$N$ 依赖）；"
        "② 子任务在端／家庭主机／云三层的仿射执行代价（$g$ 依赖，云侧 "
        "$\\gamma_2$ 含 $C/B_u$ 上下文税）"),
    "fig02_overhead.png": ("图 2",
        "发现—执行二元开销分解（解析，参数按 §4.1 标定）：三条仿射代价线的下包络"
        "给出“端→家庭→云”门限带；点线为修订 2a 的等效家庭代价 $T_1^{\\rm eff}$"
        "（$m{=}3$），使 $g_2^*$ 由 19 KB 左移至 8.6 KB"),
    "fig1_discovery_law.png": ("图 3",
        "发现开销两段律（命题 1）：(a) 双对数下两模型在 N≤96 重合，N=112 呈种子间"
        "双峰相变，N=128 删失（$N^*$ 临界带为阴影）；(b) 发现阶段真实空口占用随 N 分化"),
    "fig2_threshold_band.png": ("图 4",
        "执行位置门限带（命题 2）：(a) 四策略的时延—粒度曲线与解析门限 "
        "$g_1^*/g_2^*$；(b) $g{=}$16 KB 处门限的比较静态（斜纹＝实际落点转为云）"),
    "fig05_g2star.png": ("图 5",
        "门限 $g_2^*$ 的比较静态（推论 2.1）：解析曲线（实线）与 E2 实测落点"
        "（○，标注实测 P50 与实际执行位置），三向单调性全部成立"),
    "fig06_lambda.png": ("图 6",
        "承载放大系数（命题 3）：(a) $\\Lambda(C)$ 实测与解析一致（应用层口径，偏差 ≤0.5%），缓存 "
        "$\\psi{=}1$ 使上下文项降为 $C/m$；(b) $C{=}$64 KB 处缓存增益的实测比值 2.8 ≈ $m{=}3$"),
    "fig07_mixed.png": ("图 7",
        "混合背景负载（E4）：(a) $B_u{=}$30 Mbps 设计点上危害由上行占用决定——视频（下行 20 Mbps）"
        "零影响、云备份（上行 24 Mbps）+81%；(b) $B_u{=}$10 Mbps 时效应转入长尾（备份 P95 +110%）"
        "而中位数几乎不动；(c) 有效上行 $B_u^{\\rm eff}$ 越小门限 $g_2^*$ 越大（右移）"),
    "fig08_oracle.png": ("图 8",
        "放置质量（E5）：本文判据 vs ORACLE（$3^m$ 批级穷举）vs 全云。16 KB 处批内混排可回收 41% 时延；"
        "8 KB 处判据反超解析参照 5%，度量其不含 WAN 批内排队的乐观度"),
    "fig09_mix.png": ("图 9",
        "批内混排（E6）：(a) 逐点判据／$O(m\\log m)$ 混排贪心／ORACLE／全云的完成时延——16 KB 处"
        "判据未计批内排队（+68%），混排回收 ≈38%；(b) 上云子任务份额：混排贪心与 $3^m$ 穷举的指派"
        "逐位相同（1/8/16 KB 处 1/3、32/64 KB 处 2/3）"),
    "fig10_thread_disc.png": ("图 10",
        "跨介质普适性（T1）：Thread/802.15.4 星型 PAN 的发现扫描。"
        "BEB 把中位时延压在约 60 ms 平台（N=8→224，P50 38→58 ms），而单次查询成功率从"
        "70.2% 单调崩塌至 3.5%——失败模态与 Wi-Fi 固定窗口的“时延爆炸”互补，"
        "共同指向共享介质多播发现的承载容量悬崖"),
    "fig11_thread_place.png": ("图 11",
        "跨地址族执行放置（T2）：Thread 叶→border 实测单向传输代价 $\\tau_{lb}(g)$"
        "（g≤16 KB 干净区间）对 Wi-Fi 端→家庭参照（50 Mbps），相差约三个数量级；"
        "右上 × 为 ns-3 模型级失败（32 KB 重装停滞、64 KB 发送失败）；"
        "真实 Linux 栈硬件级复测经两级分片可承载至 65507 B UDP 上限（§5.11 发现 2）"),
}

# 锚点文本 → 图（插入到匹配块之后）
ANCHORS = [
    ("关键结构差异：", ["fig01_arch.png"]),
    ("默认参数下 $m{=}3$ 时 $g_2^*$ 由 19 KB 左移", ["fig02_overhead.png"]),
    ("完整 10 档数据见实验记录", ["fig1_discovery_law.png"]),
    ("（图 4a；成功率全部", ["fig2_threshold_band.png"]),
    ("二者须分开治理。", ["fig05_g2star.png"]),
    ("（图 6）", ["fig06_lambda.png"]),
    ("（图 7；全本地对照", ["fig07_mixed.png"]),
    ("（图 8）", ["fig08_oracle.png"]),
    ("（图 9）", ["fig09_mix.png"]),
    ("（图 10）", ["fig10_thread_disc.png"]),
    ("（图 11）", ["fig11_thread_place.png"]),
]

ins = {}
for k, (kind, payload) in enumerate(blocks):
    text = payload if isinstance(payload, str) else " ".join(payload)
    for anchor, fl in ANCHORS:
        if anchor in text:
            ins.setdefault(k, []).extend(fl)


def fig_html(fname):
    no, cap = FIGS[fname]
    data = base64.b64encode(open(os.path.join(FIGDIR, fname), "rb").read()).decode()
    return ('<figure class="fig" id="fig%s">'
            '<img src="data:image/png;base64,%s" alt="%s">'
            '<figcaption><span class="figno">%s</span>　%s</figcaption></figure>'
            % (re.sub(r"\D", "", no), data, no, no, inline2(cap)))


def make_table(rows):
    def cells(r):
        r = r.strip().strip("|")
        return [c.strip() for c in r.split("|")]

    head = cells(rows[0])
    body = [cells(r) for r in rows[2:] if not set(r) <= set("|-: ")]
    out = ['<table class="data"><thead><tr>']
    for c in head:
        out.append("<th>%s</th>" % inline2(c))
    out.append("</tr></thead><tbody>")
    for row in body:
        out.append("<tr>")
        for j, c in enumerate(row):
            out.append('<td class="%s">%s</td>' % ("l" if j == 0 else "c", inline2(c)))
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def make_eq(content):
    m = re.search(r"\\tag\{(\d+)\}", content)
    no = m.group(1) if m else ""
    body_eq = re.sub(r"\s*\\tag\{\d+\}", "", content)
    return ('<div class="eq"><div class="eq-m">\\[%s\\]</div>'
            '<span class="eq-no">%s</span></div>' % (body_eq, no))


def sec_id(text):
    m = re.match(r"^([\d.]+)", text)
    return ("sec-" + m.group(1).rstrip(".")) if m else "sec-" + re.sub(r"\W", "-", text)[:12]


toc = []
body = []
abs_kw_html = ""

for k, (kind, payload) in enumerate(blocks):
    if kind == "h2":
        m = re.match(r"^([\d.]+)\s+(.*)$", payload)
        if m:
            no, t = m.group(1), m.group(2)
            body.append('<h2 id="%s"><span class="secno">%s</span>　%s</h2>'
                        % (sec_id(payload), no, t))
            toc.append((2, no, t, sec_id(payload)))
        else:
            body.append('<h2 id="%s">%s</h2>' % (sec_id(payload), inline2(payload)))
            toc.append((2, "", payload, sec_id(payload)))
    elif kind == "h3":
        m = re.match(r"^([\d.]+)\s+(.*)$", payload)
        if m:
            no, t = m.group(1), m.group(2)
            body.append('<h3 id="%s"><span class="secno">%s</span>　%s</h3>'
                        % (sec_id(payload), no, t))
            toc.append((3, no, t, sec_id(payload)))
        else:
            body.append("<h3>%s</h3>" % inline2(payload))
    elif kind == "p":
        cls = "noindent" if payload.startswith("**") else ""
        body.append('<p class="%s">%s</p>' % (cls, inline2(payload)))
    elif kind == "abstract":
        abs_kw_html += ('<div class="abstract"><span class="abs-label">摘要</span>%s</div>'
                        % inline2(payload))
    elif kind == "keywords":
        t = re.sub(r"^\*\*关键词\*\*[:：]?\s*", "", payload)
        abs_kw_html += ('<div class="keywords"><span class="abs-label">关键词</span>%s</div>'
                        % inline2(t))
    elif kind == "note":
        body.append('<div class="draftnote">%s</div>' % inline2(payload))
    elif kind == "tabcap":
        t = re.sub(r"^\*\*(.*)\*\*$", r"\1", payload)
        body.append('<div class="tabcap">%s</div>' % inline2(t))
    elif kind == "table":
        body.append(make_table(payload))
    elif kind == "eq":
        body.append(make_eq(payload))
    elif kind == "ul":
        body.append("<ul>%s</ul>" % "".join("<li>%s</li>" % inline2(x) for x in payload))
    elif kind == "ol":
        body.append("<ol>%s</ol>" % "".join("<li>%s</li>" % inline2(x) for x in payload))
    elif kind == "ref":
        body.append('<p class="ref">%s</p>' % inline2(payload))
    if k in ins:
        for f in ins[k]:
            body.append(fig_html(f))

toc_html = "".join(
    '<div class="toc-l%d"><span class="tocno">%s</span><a href="#%s">%s</a></div>'
    % (lv, no, sid, t) for lv, no, t, sid in toc)

CSS = """
:root { --ink:#1c1c1c; --rule:#2b2b2b; --soft:#777; --bg:#ffffff; --panel:#f7f6f2; }
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin:0; background:var(--bg); color:var(--ink);
  font-family: Georgia, "Times New Roman", "Source Han Serif SC", "Songti SC", SimSun, serif;
  font-size:15.5px; line-height:1.9; }
article { max-width: 840px; margin:0 auto; padding:56px 28px 80px; }
h1 { font-family:"Source Han Sans SC","Noto Sans SC","PingFang SC","Microsoft YaHei",SimHei,sans-serif;
  font-size:21px; font-weight:700; text-align:center; line-height:1.6; margin:0 0 24px; }
.abs-label { display:inline-block; font-weight:700; margin-right:1em;
  font-family:"Source Han Sans SC","Microsoft YaHei",SimHei,sans-serif; }
.abstract, .keywords { background:var(--panel); border:1px solid #e6e4dc;
  padding:14px 20px; font-size:14.5px; text-align:justify; margin:0 0 12px; }
.draftnote { background:#fdf6e3; border:1px dashed #d9c98a; color:#6b5b1e;
  padding:10px 18px; font-size:13px; line-height:1.8; margin:0 0 18px; text-align:left; }
nav.toc { background:var(--panel); border:1px solid #e6e4dc; padding:16px 22px;
  font-size:13.5px; margin:26px 0 8px; line-height:2.0; }
nav.toc .toc-title { font-weight:700; margin-bottom:4px;
  font-family:"Source Han Sans SC","Microsoft YaHei",SimHei,sans-serif; }
.toc-l3 { padding-left:2.2em; color:#444; }
.toc a { color:inherit; text-decoration:none; }
.toc a:hover { color:#8a1f1f; }
.tocno { display:inline-block; min-width:3.2em; color:var(--soft); }
h2 { font-family:"Source Han Sans SC","Noto Sans SC","Microsoft YaHei",SimHei,sans-serif;
  font-size:17.5px; margin:2.4em 0 0.9em; }
h3 { font-family:"Source Han Sans SC","Noto Sans SC","Microsoft YaHei",SimHei,sans-serif;
  font-size:15.5px; margin:1.8em 0 0.6em; }
.secno { margin-right:.1em; }
p { margin:.7em 0; text-align:justify; text-indent:2em; }
p.noindent { text-indent:0; }
strong { font-family:"Source Han Sans SC","Microsoft YaHei",SimHei,sans-serif; font-weight:700; }
code { font-family:Consolas,"Courier New",monospace; font-size:.88em;
  background:#f2f1ec; border:1px solid #e2e0d8; border-radius:3px; padding:0 4px; }
.data { width:100%; border-collapse:collapse; margin:4px 0 18px; font-size:13.8px; line-height:1.6; }
.data th, .data td { border:0; padding:5px 7px; text-align:center; vertical-align:bottom; }
.data thead th { border-top:1.6px solid var(--rule); border-bottom:1px solid var(--rule); font-weight:700; }
.data tbody tr:last-child td { border-bottom:1.6px solid var(--rule); }
.data td.l { text-align:left; }
.tabcap { text-align:center; font-weight:700; margin:1.6em 0 8px;
  font-family:"Source Han Sans SC","Microsoft YaHei",SimHei,sans-serif; font-size:14.5px; }
.eq { display:flex; align-items:center; margin:.6em 0; }
.eq-m { flex:1; text-align:center; }
.eq-no { color:var(--soft); font-size:.92em; }
figure.fig { margin:1.8em auto; text-align:center; page-break-inside:avoid; }
figure.fig img { max-width:92%; height:auto; }
figcaption { font-size:13.5px; color:#333; margin-top:8px; text-align:center; line-height:1.7; }
.figno { font-weight:700; font-family:"Source Han Sans SC","Microsoft YaHei",SimHei,sans-serif; }
ul, ol { margin:.5em 0 .9em; padding-left:2.4em; }
li { margin:.35em 0; text-align:justify; }
p.ref { font-size:14px; padding-left:2.6em; margin:.45em 0; text-indent:-2.6em;
  text-align:left; }
footer.colophon { margin-top:4em; padding-top:14px; border-top:1px solid #ddd;
  color:var(--soft); font-size:12.5px; text-align:center; }
@media print {
  @page { size:A4; margin:22mm 20mm; }
  article { max-width:none; padding:0; }
  nav.toc { display:none; }
  .abstract,.keywords { background:none; border:0; padding:0; }
  figure.fig, .data { page-break-inside:avoid; }
  a { color:inherit; }
}
"""

mj = open(MJ, encoding="utf-8").read()

html_doc = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s</title>
<style>%s</style>
<script>
window.MathJax = {
  tex: { inlineMath: [['$','$']], displayMath: [['\\\\[','\\\\]']], tags: 'none' },
  svg: { fontCache: 'global' },
  options: { enableMenu: false,
    skipHtmlTags: ['script','noscript','style','textarea','pre','code'] }
};
</script>
<script>%s</script>
</head>
<body>
<article>
<h1>%s</h1>
%s
<nav class="toc"><div class="toc-title">目　次</div>%s</nav>
%s
<footer class="colophon">初稿 v1 · 基于 NS-3.35 真实转发仿真 · 数据与图源见文末附表 · 公式由 MathJax（SVG）离线渲染</footer>
</article>
</body>
</html>
""" % (html.escape(title), CSS, mj, html.escape(title),
       abs_kw_html, toc_html, "\n".join(body))

open(OUT, "w", encoding="utf-8").write(html_doc)
print("written", OUT, len(html_doc), "bytes,", len(blocks), "blocks")
