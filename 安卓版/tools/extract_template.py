# -*- coding: utf-8 -*-
"""把 打卡表模板.docx 抽成 assets/template.js（JS 直接可用的部件包）。

做的事和电脑版 build() 里的预处理一模一样：
  · 去掉模板自带的示例图片和对应的 image 关系
  · 每个表格行加 cantSplit（一行不被拆到两页）
  · 日期标签行加 keepNext（标签跟着它的图走）
之后 JS 只负责：填日期、填班级姓名、往格子里插图片、备用格加行。
"""
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent          # 安卓版/
TPL = next((p for p in [ROOT.parent / "打卡表模板.docx",            # 安卓版/ 就在仓库根下
                         ROOT.parent / "打卡工具" / "打卡表模板.docx",  # 旧布局
                         ROOT.parent / ".." / "打卡工具" / "打卡表模板.docx"] if p.is_file()), None)
OUT = ROOT / "app" / "src" / "main" / "assets" / "template.js"

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
LABEL_ROWS = [2, 4, 6, 8, 10, 12, 14]

print("模板:", TPL)
z = zipfile.ZipFile(TPL)
parts: dict[str, bytes] = {}
for info in z.infolist():
    n = info.filename
    if n.endswith("/"):
        continue
    if n.startswith("word/media/"):
        continue                                    # 示例图丢掉
    parts[n] = z.read(n)
z.close()

# 1) 关系表里去掉所有 image 关系（图片部件已经不要了）
rels = parts["word/_rels/document.xml.rels"].decode("utf-8")
before = len(re.findall(r'Type="[^"]*/image"', rels))
rels = re.sub(r'<Relationship\b[^>]*Type="[^"]*/image"[^>]*/>', "", rels)
parts["word/_rels/document.xml.rels"] = rels.encode("utf-8")
print(f"去掉 image 关系 {before} 条")

# 2) 处理 document.xml
doc = parts["word/document.xml"]
head = doc[:4000].decode("utf-8", "replace")
for pfx, uri in re.findall(r'xmlns:([A-Za-z0-9_]+)="([^"]+)"', re.search(r"<w:document\b[^>]*>", head).group(0)):
    try:
        ET.register_namespace(pfx, uri)
    except Exception:
        pass

root = ET.fromstring(doc)
tbl = root.find(f"{{{W}}}body").find(f"{{{W}}}tbl")
rows = tbl.findall(f"{{{W}}}tr")
removed = 0
for tr in rows:
    trPr = tr.find(f"{{{W}}}trPr")
    if trPr is None:
        trPr = ET.Element(f"{{{W}}}trPr")
        tr.insert(0, trPr)
    if trPr.find(f"{{{W}}}cantSplit") is None:
        ET.SubElement(trPr, f"{{{W}}}cantSplit")
    for tc in tr.findall(f"{{{W}}}tc"):
        for p in list(tc.findall(f"{{{W}}}p")):
            if p.find(f".//{{{W}}}drawing") is not None:
                tc.remove(p)
                removed += 1
for i in LABEL_ROWS:
    for p in rows[i].iter(f"{{{W}}}p"):
        pPr = p.find(f"{{{W}}}pPr")
        if pPr is None:
            pPr = ET.Element(f"{{{W}}}pPr")
            p.insert(0, pPr)
        if pPr.find(f"{{{W}}}keepNext") is None:
            at = 1 if pPr.find(f"{{{W}}}pStyle") is not None else 0
            pPr.insert(at, ET.Element(f"{{{W}}}keepNext"))
print(f"清掉 {removed} 个示例图片段落，19 行都加了 cantSplit")

parts["word/document.xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
ET.fromstring(parts["word/document.xml"])          # 自检

# 3) 输出成 JS
data = {n: parts[n].decode("utf-8") for n in parts}
js = "// 自动生成：打卡表模板的各个部件（已去掉示例图和图片关系）\n"
js += "// 生成命令：python 安卓版/tools/extract_template.py\n"
js += "window.TEMPLATE = " + json.dumps(data, ensure_ascii=False) + ";\n"
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(js, encoding="utf-8")
print(f"\n写入 {OUT}")
print(f"  部件 {len(data)} 个，文件 {OUT.stat().st_size/1024:.0f} KB")
print("  含:", ", ".join(sorted(data)[:6]), "…")
