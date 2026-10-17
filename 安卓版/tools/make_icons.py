# -*- coding: utf-8 -*-
"""把用户给的 .ico 生成安卓各尺寸图标（含自适应图标）。
用法：python 安卓版/tools/make_icons.py "<ico 路径>"
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent          # 安卓版/
RES = ROOT / "app" / "src" / "main" / "res"

ICO = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if not ICO or not ICO.is_file():
    print("找不到 ico：", ICO)
    sys.exit(1)

src = Image.open(ICO).convert("RGBA")
src.load()
if src.size != (256, 256):
    src = src.resize((256, 256), Image.LANCZOS)

# 背景色：取不透明像素的平均色，向白色混 85%，做成柔和的浅色底
px = src.load()
rs = gs = bs = n = 0
for y in range(0, 256, 4):
    for x in range(0, 256, 4):
        r, g, b, a = px[x, y]
        if a > 200:
            rs += r; gs += g; bs += b; n += 1
avg = (rs // max(1, n), gs // max(1, n), bs // max(1, n))
bg = tuple(int(c + (255 - c) * 0.86) for c in avg)
print("图标平均色:", avg, "→ 底色:", bg, "#%02X%02X%02X" % bg)

LEGACY = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
ADAPT = {"mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432}


def fit(img, box, scale):
    """把图按 scale 比例放进 box 画布，居中，保持透明"""
    side = int(box * scale)
    im = img.resize((side, side), Image.LANCZOS)
    canvas = Image.new("RGBA", (box, box), (0, 0, 0, 0))
    off = (box - side) // 2
    canvas.paste(im, (off, off), im)
    return canvas


def circle_mask(img):
    box = img.size[0]
    mask = Image.new("L", (box, box), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, box - 1, box - 1), fill=255)
    out = Image.new("RGBA", (box, box), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


for d, size in LEGACY.items():
    folder = RES / f"mipmap-{d}"
    folder.mkdir(parents=True, exist_ok=True)
    square = fit(src, size, 0.98)                     # 普通图标：留一点边距
    square.save(folder / "ic_launcher.png")
    circle_mask(square).save(folder / "ic_launcher_round.png")

for d, size in ADAPT.items():
    folder = RES / f"mipmap-{d}"
    # 自适应图标：前景占中间约 82%，四周留给系统裁切
    fg = fit(src, size, 0.70)
    fg.save(folder / "ic_launcher_fg.png")

anydpi = RES / "mipmap-anydpi-v26"
anydpi.mkdir(parents=True, exist_ok=True)
xml = ('<?xml version="1.0" encoding="utf-8"?>\n'
       '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
       '    <background android:drawable="@color/ic_launcher_background"/>\n'
       '    <foreground android:drawable="@mipmap/ic_launcher_fg"/>\n'
       '</adaptive-icon>\n')
(anydpi / "ic_launcher.xml").write_text(xml, encoding="utf-8")
(anydpi / "ic_launcher_round.xml").write_text(xml, encoding="utf-8")

values = RES / "values"
values.mkdir(parents=True, exist_ok=True)
(values / "colors.xml").write_text(
    '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
    f'    <color name="ic_launcher_background">#{"%02X%02X%02X" % bg}</color>\n'
    '</resources>\n', encoding="utf-8")

print("\n生成完毕：")
for d in LEGACY:
    f = RES / f"mipmap-{d}"
    print(f"  mipmap-{d}: " + ", ".join(f"{p.name}({Image.open(p).size[0]}px)"
                                       for p in sorted(f.glob("*.png"))))
print("  mipmap-anydpi-v26: ic_launcher.xml, ic_launcher_round.xml")
print("  values/colors.xml:", "#%02X%02X%02X" % bg)


