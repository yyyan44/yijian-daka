# -*- coding: utf-8 -*-
"""校验生成的 docx：zip / XML / 图片 / 表格，并让 WPS 打开读回排版数据。
用法：python 安卓版/tools/check_docx.py <文件.docx>
"""
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def check(path: Path) -> int:
    print(f"\n--- 结构校验：{path.name}（{path.stat().st_size/1024:.0f} KB）---")
    z = zipfile.ZipFile(path)
    bad_zip = z.testzip()
    parts = z.namelist()
    media = [n for n in parts if n.startswith("word/media/")]

    bad_xml = []
    for n in parts:
        if n.endswith(".xml") or n.endswith(".rels"):
            try:
                ET.fromstring(z.read(n))
            except Exception as e:
                bad_xml.append((n, str(e)[:70]))

    doc = z.read("word/document.xml").decode("utf-8")
    rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
    embeds = set(re.findall(r'r:embed="([^"]+)"', doc))
    relids = set(re.findall(r'Id="([^"]+)"', rels))

    root = ET.fromstring(z.read("word/document.xml"))
    tbl = root.find(f"{{{W}}}body").find(f"{{{W}}}tbl")
    rows = tbl.findall(f"{{{W}}}tr")
    text = "".join(t.text or "" for t in root.iter(f"{{{W}}}t"))
    ext = re.findall(r'<wp:extent cx="(\d+)" cy="(\d+)"', doc)
    dims = [(round(int(a) / 360000, 2), round(int(b) / 360000, 2)) for a, b in ext]

    print(f"  zip 完整性      : {'OK' if bad_zip is None else '损坏 ' + str(bad_zip)}")
    print(f"  部件 / 图片      : {len(parts)} / {len(media)}")
    print(f"  XML 解析失败     : {len(bad_xml)}" + ("" if not bad_xml else f"  {bad_xml[:2]}"))
    print(f"  图片引用对得上   : {embeds <= relids}（{len(embeds)} 个）")
    print(f"  表格行数         : {len(rows)}")
    print(f"  占位符已替换     : {'填自己' not in text}")
    print(f"  图片尺寸(cm)     : {dims}")

    # WPS 排版引擎读回
    try:
        import win32com.client as w
        app = w.Dispatch("KWPS.Application")
        try:
            app.Visible = False
            app.DisplayAlerts = 0
        except Exception:
            pass
        d = app.Documents.Open(str(path), ReadOnly=True)
        pdf = path.with_name(path.stem + "_WPS.pdf")
        try:
            d.ExportAsFixedFormat(str(pdf), 17)
            pdfinfo = f"，导出 PDF {pdf.stat().st_size/1024:.0f} KB"
        except Exception:
            pdfinfo = ""
        print(f"  WPS 打开         : OK｜页数 {d.ComputeStatistics(2)}｜表格 {d.Tables.Count}｜"
              f"内嵌图片 {d.InlineShapes.Count}{pdfinfo}")
        d.Close(0)
        app.Quit()
    except Exception as e:
        print(f"  WPS 打开         : 失败 {e}")

    ok = (bad_zip is None) and not bad_xml and (embeds <= relids) and len(rows) >= 19
    print(f"  → 结论           : {'通过 ✅' if ok else '有问题 ❌'}")
    return 0 if ok else 1


if __name__ == "__main__":
    code = 0
    for a in sys.argv[1:]:
        p = Path(a)
        if not p.is_file():
            print("找不到文件:", p)
            code = 1
            continue
        code |= check(p)
    sys.exit(code)
