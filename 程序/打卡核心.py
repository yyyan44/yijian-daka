# -*- coding: utf-8 -*-
r"""「宣传委员打卡表」核心逻辑。

周次推算 → 截图归位 → 填进 Word 模板，全在这里。
命令行版（打卡表.py）和界面版（打卡界面.py）都调用这个模块，
所以两种用法的结果完全一样。

单独双击本文件不会做任何事；改设置请用界面上的输入框，
也可以直接编辑同目录的「打卡配置.json」。
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable, Sequence
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
PROGRAM_DIR = HERE               # 程序（.py / .ico / 设置）在哪个文件夹
CONFIG_FILE = "打卡配置.json"
STATE_FILE = "打卡安排.json"

# ═══════════════════════════════════════════════════════════
#  默认设置（界面上改了会写进 打卡配置.json，这里只是初值）
# ═══════════════════════════════════════════════════════════
DEFAULTS: dict = {
    "first_week_monday": "2026-08-31",   # 第 1 周里的那个周一（第1周 = 8/29 周六 ~ 9/4 周五）
    "cycle_start_weekday": 6,            # 一个周期从星期几起算：1=周一 … 6=周六 … 7=周日
    "class_name": "XX班",                 # 班级（第一次用请在界面上填自己的，会记住）
    "student_name": "张三",               # 姓名（同上）
    "template_file": "打卡表模板.docx",    # 模板文件名
    "chat_dir": "聊天记录截图",            # 按星期几归位的那批
    "date_dir": "日期截图",               # 塞进「备用格」的那批
    "clip_dir": "剪贴板截图",              # 界面里 Ctrl+V 粘贴的图存这里
    "out_dir": "生成的打卡表",              # 生成好的 Word 放哪个子文件夹
}
# ═══════════════════════════════════════════════════════════

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}

# ───────────────────────── 程序在哪、数据在哪 ─────────────────────────
# 程序文件（.py / .ico / 打卡配置.json）和在用的东西（模板、截图、生成的 Word、
# 打卡安排.json）可以分开放：程序塞进「程序」子文件夹时，自动往上一层找数据目录。
_SUBDIR_NAMES = {"程序", "程序文件", "打卡工具", "工具", "tools", "app", "bin"}


def _looks_like_data(d: Path) -> bool:
    return any((d / n).exists() for n in
               ("打卡表模板.docx", "聊天记录截图", "日期截图", STATE_FILE))


def data_root() -> Path:
    """截图、模板、生成的 Word 放哪个文件夹。"""
    seen = []
    d = PROGRAM_DIR
    for _ in range(4):                     # 自己 + 往上三层
        seen.append(d)
        if _looks_like_data(d):
            return d
        if d.parent == d:
            break
        d = d.parent
    if PROGRAM_DIR.name.lower() in _SUBDIR_NAMES and PROGRAM_DIR.parent.is_dir():
        return PROGRAM_DIR.parent          # 程序在「程序」之类的子文件夹里，数据放外面
    return PROGRAM_DIR


DATA = data_root()                         # 界面/命令行都用它当「当前文件夹」

DAYS = ["六", "日", "一", "二", "三", "四", "五"]
WD_CN = {"六": "上周六", "日": "上周日", "一": "本周一", "二": "本周二",
         "三": "本周三", "四": "本周四", "五": "本周五"}
WD_RANK = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7,
           "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7}
RANK_WD = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "日"}
CN_NUM = "零一二三四五六七八九"

WD_RE = re.compile(r"(?:周|星期|礼拜)\s*([一二三四五六日天1-7])")
TS_RE = re.compile(r"(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])"
                   r"(?:[-_.\sT]?([01]\d|2[0-3])[-_.:]?([0-5]\d)[-_.:]?([0-5]\d))?")


# ───────────────────────── 配置 ─────────────────────────

def load_config(here: Path | None = None) -> dict:
    """读 打卡配置.json（跟着程序走），缺的字段用默认值补上。"""
    cfg = dict(DEFAULTS)
    p = Path(here or PROGRAM_DIR) / CONFIG_FILE
    if p.is_file():
        try:
            data = json.loads(p.read_text("utf-8"))
            if isinstance(data, dict):
                for k, v in data.items():
                    if k in DEFAULTS and v not in (None, ""):
                        cfg[k] = v
        except Exception:
            pass
    return cfg


def save_config(cfg: dict, here: Path | None = None) -> None:
    p = Path(here or PROGRAM_DIR) / CONFIG_FILE
    try:
        p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
    except Exception:
        pass


def ensure_shortcut(here: Path | None = None, script: Path | None = None,
                    icon: Path | None = None) -> bool:
    """把「一键打卡.lnk」修到当前所在位置。

    Windows 快捷方式里存的是绝对路径，整个文件夹搬走以后就会失效。
    所以每次启动都检查一下：指对了不动，指错了（或根本没有）就按当前位置重建。
    修不好也没关系 —— 同一个文件夹里的「一键打卡.pyw」放哪都能双击。
    """
    here = Path(here or DATA)
    script = Path(script or (PROGRAM_DIR / "打卡界面.py"))
    icon = Path(icon or (PROGRAM_DIR / "打卡图标.ico"))
    lnk = here / "一键打卡.lnk"
    if not script.is_file():
        return False
    try:
        if lnk.is_file():
            raw = lnk.read_bytes().decode("utf-16-le", "ignore").lower()
            if str(script).lower() in raw and str(here).lower() in raw:
                return True                       # 已经指对了
    except Exception:
        pass

    exe = Path(sys.executable)
    target = exe.with_name("pythonw.exe")
    if not target.is_file():
        target = exe                               # 没有 pythonw 就用 python

    def q(s) -> str:
        return str(s).replace("'", "''")

    ps = ("$ws = New-Object -ComObject WScript.Shell; "
          f"$l = $ws.CreateShortcut('{q(lnk)}'); "
          f"$l.TargetPath = '{q(target)}'; "
          f"$l.Arguments = '\"{q(script)}\"'; "
          f"$l.WorkingDirectory = '{q(here)}'; "
          + (f"$l.IconLocation = '{q(icon)},0'; " if Path(icon).is_file() else "")
          + "$l.Description = '宣传委员打卡 · 打开打卡表生成器界面'; $l.Save()")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, timeout=25,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode == 0 and lnk.is_file()
    except Exception:
        return False


# ───────────────────────── 周次推算 ─────────────────────────

def cn_num(n: int) -> str:
    if n < 10:
        return CN_NUM[n]
    if n == 10:
        return "十"
    if n < 20:
        return "十" + CN_NUM[n % 10]
    return CN_NUM[n // 10] + "十" + (CN_NUM[n % 10] if n % 10 else "")


def anchor_monday(cfg: dict) -> date:
    s = str(cfg.get("first_week_monday") or DEFAULTS["first_week_monday"])
    try:
        y, m, d = (int(x) for x in re.split(r"[-/.]", s)[:3])
        return date(y, m, d)
    except Exception:
        return date(2026, 8, 31)


def week1_start(cfg: dict) -> date:
    """第 1 周的起点：从锚点周一往前推到那一周期的起始星期。"""
    a = anchor_monday(cfg)
    start_wd = int(cfg.get("cycle_start_weekday") or 6)
    delta = (a.weekday() + 1 - start_wd) % 7
    return a - timedelta(days=delta)


def cycle_start(week: int, cfg: dict) -> date:
    return week1_start(cfg) + timedelta(days=7 * (week - 1))


def week_range(week: int, cfg: dict) -> tuple[date, date]:
    s = cycle_start(week, cfg)
    return s, s + timedelta(days=6)


def week_of(day: date, cfg: dict) -> int:
    return (day - week1_start(cfg)).days // 7 + 1


def today_week(cfg: dict) -> int:
    return week_of(date.today(), cfg)


def describe_week(week: int, cfg: dict) -> str:
    s, e = week_range(week, cfg)
    return f"第{cn_num(week)}周　{s:%m/%d}（周六）~ {e:%m/%d}（周五）"


# ───────────────────────── 认图片是哪天的 ─────────────────────────

def weekday_of(path: Path) -> str | None:
    """文件名里写了「周三 / 星期三 / 礼拜3」就认出来。"""
    m = WD_RE.search(Path(path).stem)
    if not m:
        return None
    rank = WD_RANK.get(m.group(1))
    return RANK_WD.get(rank) if rank else None


def shot_date(path: Path) -> tuple[date, str]:
    """截图是哪天的：先认文件名里的时间戳（微信截图一般带），认不出就用文件修改时间。"""
    p = Path(path)
    m = TS_RE.search(p.stem)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), "文件名"
        except ValueError:
            pass
    try:
        return date.fromtimestamp(p.stat().st_mtime), "文件时间"
    except Exception:
        return date.today(), "系统日期"


def is_image(path: Path) -> bool:
    return Path(path).is_file() and Path(path).suffix.lower() in IMG_EXT


def list_images(folder: Path) -> list[Path]:
    if not Path(folder).is_dir():
        return []
    return [p for p in sorted(Path(folder).iterdir()) if is_image(p)]


@dataclass
class Shot:
    """一张截图 + 它属于哪一天、第几周。"""
    path: Path
    day: date
    how: str                 # 日期是「文件名」还是「文件时间」认出来的
    weekday: str             # 六 / 日 / 一 …
    from_name: bool          # 文件名里写了星期几
    week: int
    kind: str                # chat=聊天记录截图，date=日期截图，clip=粘贴

    @property
    def tip(self) -> str:
        src = "文件名写明" if self.from_name else f"{self.how}推得"
        return (f"{self.path.name}\n{self.day:%Y-%m-%d}（周{self.weekday}，{src}）\n"
                f"属于第{cn_num(self.week)}周")


def make_shot(path: Path, cfg: dict, kind: str = "chat") -> Shot:
    p = Path(path)
    d, how = shot_date(p)
    named = weekday_of(p)
    from_name = named is not None
    wd = named if (named and kind != "date") else RANK_WD[d.isoweekday()]
    return Shot(path=p, day=d, how=how, weekday=wd, from_name=from_name,
                week=week_of(d, cfg), kind=kind)


def collect(here: Path | None = None, cfg: dict | None = None) -> list[Shot]:
    """把两个截图文件夹里的图都收进来，附上日期/星期/周次。"""
    here = Path(here or DATA)
    cfg = cfg or load_config()
    out: list[Shot] = []
    for kind, key in (("chat", "chat_dir"), ("date", "date_dir")):
        for p in list_images(here / str(cfg.get(key) or DEFAULTS[key])):
            out.append(make_shot(p, cfg, kind))
    return out


def guess_week(shots: Sequence[Shot], cfg: dict) -> tuple[int, dict[int, int]]:
    """按截图日期投票决定是哪一周（多数票，同票取靠后的周）。"""
    tally: dict[int, int] = {}
    for s in shots:
        if s.week >= 1:
            tally[s.week] = tally.get(s.week, 0) + 1
    if not tally:
        return max(1, today_week(cfg)), tally
    return max(tally, key=lambda k: (tally[k], k)), tally


def split(shots: Iterable[Shot], week: int) -> tuple[dict[str, list[Shot]], list[Shot]]:
    """按星期几归位；不属于本周的聊天记录截图退到「未归位」。"""
    chat: dict[str, list[Shot]] = {wd: [] for wd in DAYS}
    leftover: list[Shot] = []
    for s in shots:
        if s.kind == "chat" and s.week == week:
            chat[s.weekday].append(s)
        else:
            leftover.append(s)
    return chat, leftover


# ───────────────────────── 写 Word ─────────────────────────

BOX_W_CM, BOX_H_CM = 19.5, 24.6   # 图片最大尺寸（合并后那格宽约 19.87cm，A4 高 29.7cm）
CM = 360000                       # 1 厘米 = 360000 EMU

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"

# 表格里的行号（模板固定 19 行）：标签行 / 截图行
LABEL_ROWS = {"六": 2, "日": 4, "一": 6, "二": 8, "三": 10, "四": 12, "五": 14}
SLOT_ROWS = {"六": 3, "日": 5, "一": 7, "二": 9, "三": 11, "四": 13, "五": 15}
NOTICE_ROW = 17                   # 「本周通知转发日期截图」那一行
SPARE_ROW = 18                    # 「备用格1/2/3」那一行

DRAWING_P = """<w:p xmlns:w="{W}" xmlns:r="{R}" xmlns:wp="{WP}" xmlns:a="{A}">
<w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:drawing>
<wp:inline distT="0" distB="0" distL="114300" distR="114300">
<wp:extent cx="{CX}" cy="{CY}"/><wp:effectExtent l="0" t="0" r="0" b="0"/>
<wp:docPr id="{ID}" name="图片 {ID}"/>
<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>
<a:graphic><a:graphicData uri="{PIC}"><pic:pic xmlns:pic="{PIC}">
<pic:nvPicPr><pic:cNvPr id="{ID}" name="图片 {ID}"/><pic:cNvPicPr><a:picLocks noChangeAspect="1"/></pic:cNvPicPr></pic:nvPicPr>
<pic:blipFill><a:blip r:embed="rId{RID}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{CX}" cy="{CY}"/></a:xfrm>
<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>
</pic:pic></a:graphicData></a:graphic>
</wp:inline></w:drawing></w:r></w:p>""".replace("{W}", W).replace("{R}", R_NS) \
    .replace("{WP}", WP).replace("{A}", A_NS).replace("{PIC}", PIC)


@dataclass
class BuildResult:
    out: Path
    week: int
    used: int = 0                     # 一共放了几个图
    missing: list[str] = field(default_factory=list)   # 哪几天没图（中文星期）
    sized_down: list[str] = field(default_factory=list)  # 同一天多图被缩小
    size_kb: float = 0.0

    @property
    def ok(self) -> bool:
        return self.out.is_file()


def cell_box_cm(tc) -> float:
    """按格子自身的宽度算可用宽度（厘米）—— 备用格只有 6cm 宽，不能按大格子的 19.5 缩。"""
    tcPr = tc.find(f"{{{W}}}tcPr")
    if tcPr is not None:
        wq = tcPr.find(f"{{{W}}}tcW")
        if wq is not None and wq.get(f"{{{W}}}type") == "dxa":
            return max(2.0, int(wq.get(f"{{{W}}}w")) / 567 - 0.4)   # 扣掉左右格边距
    return BOX_W_CM


def fit(iw: int, ih: int, bw_cm: float = BOX_W_CM,
        bh_cm: float = BOX_H_CM) -> tuple[int, int]:
    bw, bh = bw_cm * CM, bh_cm * CM
    if iw <= 0 or ih <= 0:
        return int(bw), int(bh)
    k = min(bw / iw, bh / ih)
    return int(iw * k), int(ih * k)


def to_jpeg(path: Path, quality: int = 85):
    from PIL import Image
    with Image.open(path) as im:
        size = im.size
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue(), size


def register_ns(xml_bytes: bytes) -> None:
    head = xml_bytes[:4000].decode("utf-8", "replace")
    m = re.search(r"<w:document\b[^>]*>", head)
    if m:
        for pfx, uri in re.findall(r'xmlns:([A-Za-z0-9_]+)="([^"]+)"', m.group(0)):
            try:
                ET.register_namespace(pfx, uri)
            except Exception:
                pass


def build(week: int, out: Path, template: Path,
          chat: dict[str, list[Path]], dates: list[Path],
          cls: str, name: str, cfg: dict | None = None,
          log: Callable[[str], None] | None = None) -> BuildResult:
    """把 chat（星期几 -> 图片）和 dates（备用格图片）写进模板，另存为 out。"""
    import copy

    say = log or (lambda _m: None)
    out = Path(out)
    template = Path(template)
    if not template.is_file():
        raise FileNotFoundError(f"找不到模板：{template}")

    z = zipfile.ZipFile(template)
    parts = {n: z.read(n) for n in z.namelist()}
    z.close()

    doc_bytes = parts["word/document.xml"]
    register_ns(doc_bytes)
    root = ET.fromstring(doc_bytes)
    tbl = root.find(f"{{{W}}}body").find(f"{{{W}}}tbl")
    rows = tbl.findall(f"{{{W}}}tr")
    rels = parts["word/_rels/document.xml.rels"].decode("utf-8")

    # 排版约束：一行不许被拆到两页（图片就不会被横切）；日期标签跟着它的图走
    for tr in rows:
        trPr = tr.find(f"{{{W}}}trPr")
        if trPr is None:
            trPr = ET.Element(f"{{{W}}}trPr")
            tr.insert(0, trPr)
        if trPr.find(f"{{{W}}}cantSplit") is None:
            ET.SubElement(trPr, f"{{{W}}}cantSplit")
    for wd in DAYS:
        for p in rows[LABEL_ROWS[wd]].iter(f"{{{W}}}p"):
            pPr = p.find(f"{{{W}}}pPr")
            if pPr is None:
                pPr = ET.Element(f"{{{W}}}pPr")
                p.insert(0, pPr)
            if pPr.find(f"{{{W}}}keepNext") is None:
                at = 1 if pPr.find(f"{{{W}}}pStyle") is not None else 0
                pPr.insert(at, ET.Element(f"{{{W}}}keepNext"))

    # 清掉模板自带的示例图
    for n in [x for x in parts if x.startswith("word/media/")]:
        del parts[n]
    rels = re.sub(r'<Relationship\b[^>]*Type="[^"]*/image"[^>]*/>', "", rels)
    for tr in rows:
        for tc in tr.findall(f"{{{W}}}tc"):
            for p in list(tc.findall(f"{{{W}}}p")):
                if p.find(f".//{{{W}}}drawing") is not None:
                    tc.remove(p)

    rid, pic_id = [100], [100]
    result = BuildResult(out=out, week=week)

    def put_image(tc, path: Path, max_h_cm: float = BOX_H_CM) -> None:
        nonlocal rels
        data, (iw, ih) = to_jpeg(path)
        rid[0] += 1
        pic_id[0] += 1
        cx, cy = fit(iw, ih, cell_box_cm(tc), max_h_cm)
        parts[f"word/media/img{pic_id[0]}.jpeg"] = data
        rels = rels.replace(
            "</Relationships>",
            f'<Relationship Id="rId{rid[0]}" Type="{R_NS}/image" '
            f'Target="media/img{pic_id[0]}.jpeg"/></Relationships>')
        tc.append(ET.fromstring(
            DRAWING_P.replace("{CX}", str(cx)).replace("{CY}", str(cy))
                     .replace("{ID}", str(rid[0])).replace("{RID}", str(rid[0]))))
        result.used += 1

    def put_cell(tc, paths: list[Path], label: str) -> None:
        """一格里的图平均分配高度：一天塞两张也不会顶穿一页。"""
        paths = [Path(p) for p in paths]
        if not paths:
            return
        if len(paths) > 1:
            result.sized_down.append(f"{label}（{len(paths)} 张）")
        per = BOX_H_CM / len(paths)
        for p in paths:
            put_image(tc, p, per)

    # 聊天记录截图 -> 按星期几进各自格子；日期标签一并改成这周的真实日期
    start = cycle_start(week, cfg or load_config(out.parent))
    for i, wd in enumerate(DAYS):
        d = start + timedelta(days=i)
        ts = rows[LABEL_ROWS[wd]].findall(f".//{{{W}}}t")
        if ts:
            ts[0].text = f"{WD_CN[wd]}（{d.day}）"
            ts[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            for t in ts[1:]:
                t.text = ""
        tc = rows[SLOT_ROWS[wd]].findall(f"{{{W}}}tc")[1]
        put_cell(tc, chat.get(wd) or [], f"周{wd}")
        if not (chat.get(wd) or []):
            result.missing.append(WD_CN[wd])

    # 日期截图 -> 备用格1/2/3；超过 3 张就照原样往下加行，每行放 3 张
    dates = [Path(p) for p in dates]
    spare_rows = [rows[SPARE_ROW]]
    for i, p in enumerate(dates):
        row_no, slot = divmod(i, 3)
        if row_no >= len(spare_rows):
            newrow = copy.deepcopy(rows[SPARE_ROW])
            tcs = newrow.findall(f"{{{W}}}tc")
            for tc in tcs:
                for pp in list(tc.findall(f"{{{W}}}p")):
                    if pp.find(f".//{{{W}}}drawing") is not None:
                        tc.remove(pp)
            for k in range(4):
                labs = tcs[k].findall(f".//{{{W}}}t")
                for t in labs:
                    t.text = ""
                if k and labs:
                    labs[0].text = f"备用格{row_no * 3 + k}"
            tbl.append(newrow)
            spare_rows.append(newrow)
        tc = spare_rows[row_no].findall(f"{{{W}}}tc")[slot + 1]
        put_cell(tc, [p], f"备用格{slot + 1}")

    # 班级 / 姓名
    for t in root.iter(f"{{{W}}}t"):
        if t.text:
            if "填自己班" in t.text:
                t.text = cls
            if "填自己名字" in t.text:
                t.text = name

    parts["word/document.xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    parts["word/_rels/document.xml.rels"] = rels.encode("utf-8")
    ET.fromstring(parts["word/document.xml"])       # 自检：解析得回来才写盘

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zo:
        for n, data in parts.items():
            zo.writestr(n, data)

    try:
        result.size_kb = out.stat().st_size / 1024
    except OSError:
        pass
    say(f"已写入 {result.used} 张图片 → {out.name}")
    if result.sized_down:
        say("同一天/同一格多张图，已自动缩小：" + "、".join(result.sized_down))
    if result.missing:
        say("还缺这些天的截图：" + "、".join(result.missing))
    return result


def build_from_plan(week: int, out: Path, here: Path | None = None, cfg: dict | None = None,
                    chat: dict[str, list[Path]] | None = None,
                    dates: list[Path] | None = None,
                    log: Callable[[str], None] | None = None) -> BuildResult:
    """build() 的省事包装：模板/班级/姓名从配置里取。"""
    here = Path(here or DATA)
    cfg = cfg or load_config()
    template = here / str(cfg.get("template_file") or DEFAULTS["template_file"])
    return build(week, out, template, chat or {}, dates or [],
                 str(cfg.get("class_name") or ""), str(cfg.get("student_name") or ""),
                 cfg, log)


def out_dir(here: Path | None = None, cfg: dict | None = None) -> Path:
    """生成的 Word 放哪个文件夹（默认数据目录下的「生成的打卡表」）。"""
    cfg = cfg or load_config()
    name = str(cfg.get("out_dir") or DEFAULTS["out_dir"]).strip() or DEFAULTS["out_dir"]
    d = Path(here or DATA) / name
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d


def out_path(week: int, cls: str, here: Path | None = None,
             cfg: dict | None = None) -> Path:
    safe = re.sub(r'[\\/:*?"<>|]', "", str(cls or "打卡表")).strip() or "打卡表"
    return out_dir(here, cfg) / f"{safe}第{cn_num(week)}周打卡.docx"


if __name__ == "__main__":
    cfg = load_config()
    print("这是核心模块，没有界面。")
    print(f"程序所在：{PROGRAM_DIR}")
    print(f"数据所在：{DATA}")
    print(f"今天是第 {cn_num(today_week(cfg))} 周，本周周期：{describe_week(today_week(cfg), cfg)}")
    print("要生成打卡表请运行 打卡界面.py（图形界面）或 打卡表.py（命令行）。")
