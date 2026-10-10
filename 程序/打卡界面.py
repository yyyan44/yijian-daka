# -*- coding: utf-8 -*-
r"""「宣传委员打卡表」图形界面版。

双击本文件（或桌面上的「一键打卡」）就打开这个窗口，整张表长什么样一目了然：

    上面   周次 / 班级 / 姓名 / 模板
    中间   周六 … 周五 七个格子 + 备用格 + 未归位
    下面   日志和「生成 Word 打卡表」

操作就三件事：
    1. 把截图从资源管理器拖进对应的格子（拖错了再拖到别的格子，或按 Delete 删掉）；
       也可以点格子里的「＋」选文件，或者 Ctrl+V 直接粘贴刚截的图。
    2. 周次会自动认，认错了用 ◀ ▶ 或旁边的按钮改。
    3. 点「生成 Word 打卡表」，完成后可以一键打开。

纯界面，所有实际工作都在 打卡核心.py 里，跟命令行版结果完全一致。

文件怎么放的：程序（.py / .ico / 打卡配置.json）都在「程序」文件夹里，
模板、截图文件夹、生成的 Word 放在它的上一层（也就是「宣传委员打卡」文件夹），
程序会自动认出来 —— 见 打卡核心.data_root()。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

try:
    from PySide6.QtCore import (Qt, QSize, QMimeData, QUrl, QThread, Signal,
                                QTimer, QPoint, QEvent)
    from PySide6.QtGui import (QAction, QDrag, QImageReader, QKeySequence,
                               QPainter, QPixmap, QColor, QFont, QIcon)
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
        QToolButton, QListWidget, QListWidgetItem, QListView, QAbstractItemView,
        QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QSpinBox, QDialog,
        QPlainTextEdit, QFileDialog, QMessageBox, QScrollArea,
        QSizePolicy, QMenu, QStatusBar)
except ImportError as exc:      # 没装 PySide6 时给一句人话
    print("需要 PySide6：pip install PySide6\n" + str(exc))
    raise

sys.path.insert(0, str(Path(__file__).resolve().parent))
import 打卡核心 as core       # noqa: E402

APP_DIR = Path(__file__).resolve().parent   # 程序（界面/核心/图标）在哪
HERE = core.data_root()                     # 模板、截图、生成的 Word 在哪
THUMB = 84                     # 缩略图边长（像素）
CARDS_PER_ROW = 4
_THUMB_CACHE: dict[str, QPixmap] = {}
# 一次拖动里被目标格子真正收下的文件；拖完据此把源格子的项目删掉，避免一图两格
_ACCEPTED_DRAG: set[str] = set()

QSS = """
QWidget { font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif; font-size: 13px; }
QMainWindow, QDialog { background: #f4f6f9; }
QFrame#card { background: #ffffff; border: 1px solid #d8dde5; border-radius: 8px; }
QFrame#card[state="full"] { border: 1px solid #57a05f; }
QFrame#card[state="empty"] { border: 1px dashed #d9a441; background: #fffdf6; }
QLabel#cardTitle { font-size: 14px; font-weight: 600; color: #23303f; }
QLabel#chipFull { color: #2f7d3a; background: #eaf6ec; border-radius: 9px; padding: 1px 8px; }
QLabel#chipEmpty { color: #a5680e; background: #fdf3e0; border-radius: 9px; padding: 1px 8px; }
QLabel#hint { color: #6b7684; }
QLabel#big { font-size: 15px; font-weight: 600; color: #1b2734; }
QListWidget { background: #fbfcfe; border: 1px solid #e3e7ee; border-radius: 6px; }
QListWidget::item { color: #4a5563; }
QListWidget::item:selected { background: #e8f0fe; color: #10365e; border-radius: 4px; }
QPushButton { background: #ffffff; border: 1px solid #ccd3dd; border-radius: 6px; padding: 5px 12px; }
QPushButton:hover { background: #f0f4fa; border-color: #a9b6c7; }
QPushButton:disabled { color: #a8b0ba; background: #f2f3f5; }
QPushButton#primary { background: #2f6fd0; border: 1px solid #2f6fd0; color: #ffffff; font-weight: 600; padding: 8px 22px; }
QPushButton#primary:hover { background: #3a7fe0; }
QPushButton#primary:disabled { background: #a8bcd8; border-color: #a8bcd8; color: #eef2f7; }
QToolButton { border: none; color: #4a5563; padding: 2px 6px; }
QToolButton:hover { background: #eef2f8; border-radius: 4px; }
QLineEdit, QSpinBox { background: #ffffff; border: 1px solid #ccd3dd; border-radius: 6px; padding: 4px 8px; }
QPlainTextEdit { background: #ffffff; border: 1px solid #e3e7ee; border-radius: 6px; }
QScrollArea { border: none; background: transparent; }
"""


# ───────────────────────── 小工具 ─────────────────────────

def thumb_for(path: Path) -> QPixmap:
    key = str(path)
    pm = _THUMB_CACHE.get(key)
    if pm is not None:
        return pm
    pm = QPixmap()
    try:
        r = QImageReader(str(path))
        r.setAutoTransform(True)
        sz = r.size()
        if sz.isValid() and max(sz.width(), sz.height()) > THUMB * 2:
            r.setScaledSize(sz.scaled(THUMB * 2, THUMB * 2, Qt.AspectRatioMode.KeepAspectRatio))
        img = r.read()
        if not img.isNull():
            pm = QPixmap.fromImage(img)
    except Exception:
        pass
    _THUMB_CACHE[key] = pm
    return pm


def short_name(path: Path) -> str:
    """缩略图下面那行字：去掉截图软件的前缀，太长就截断。"""
    s = Path(path).stem
    for pre in ("Screenshot ", "screenshot ", "微信截图", "微信图片", "QQ图片",
                "QQ截图", "截图", "image", "IMG_", "IMG"):
        if s.startswith(pre):
            s = s[len(pre):].strip(" -_")
            break
    return s[:13] or Path(path).stem[:13]


def open_in_explorer(path: Path) -> None:
    p = Path(path)
    try:
        if p.is_dir():
            os.startfile(str(p))                                    # noqa: S606
        elif p.exists():
            subprocess.Popen(["explorer", "/select,", str(p)])
        else:
            os.startfile(str(p.parent))
    except Exception:
        pass


def open_file(path: Path) -> None:
    try:
        os.startfile(str(path))                                     # noqa: S606
    except Exception as exc:
        QMessageBox.warning(None, "打不开", f"没能打开文件：\n{path}\n{exc}")


# ───────────────────────── 图片列表（可拖进拖出） ─────────────────────────

class ImageList(QListWidget):
    """缩略图列表：接受从资源管理器拖进来的图片，也能把图拖到别的格子。"""

    changed = Signal()

    def __init__(self, parent=None, placeholder: str = "拖图片到这里\n或点「＋ 添加」"):
        super().__init__(parent)
        self.placeholder = placeholder
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setIconSize(QSize(THUMB, THUMB))
        self.setGridSize(QSize(THUMB + 22, THUMB + 26))
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.setUniformItemSizes(True)
        self.setMovement(QListView.Movement.Static)
        self.setSpacing(4)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.viewport().setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    # —— 内容 ——
    def paths(self) -> list[Path]:
        out = []
        for i in range(self.count()):
            p = self.item(i).data(Qt.ItemDataRole.UserRole)
            if p:
                out.append(Path(p))
        return out

    def has_path(self, path: Path) -> bool:
        key = str(Path(path))
        return any(str(p) == key for p in self.paths())

    def add_paths(self, paths, quiet: bool = False) -> int:
        added = 0
        for p in paths:
            p = Path(p)
            if not core.is_image(p) or self.has_path(p):
                continue
            try:
                shot = core.make_shot(p, core.load_config())
                tip = shot.tip
            except Exception:
                tip = str(p)
            it = QListWidgetItem(QIcon(thumb_for(p)), short_name(p))
            it.setData(Qt.ItemDataRole.UserRole, str(p))
            it.setToolTip(tip)
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.addItem(it)
            added += 1
        if added:
            self.changed.emit()
        return added

    def remove_selected(self) -> None:
        rows = sorted((self.row(i) for i in self.selectedItems()), reverse=True)
        for r in rows:
            self.takeItem(r)
        if rows:
            self.changed.emit()

    def remove_row(self, row: int) -> None:
        if 0 <= row < self.count():
            self.takeItem(row)
            self.changed.emit()

    def clear_all(self) -> None:
        if self.count():
            self.clear()
            self.changed.emit()

    # —— 拖放 ——
    def startDrag(self, actions):
        items = self.selectedItems()
        if not items:
            return
        paths = [Path(i.data(Qt.ItemDataRole.UserRole)) for i in items]
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
        drag = QDrag(self)
        drag.setMimeData(mime)
        pm = items[0].icon().pixmap(THUMB, THUMB)
        if not pm.isNull():
            drag.setPixmap(pm)
            drag.setHotSpot(QPoint(pm.width() // 2, pm.height() // 2))
        _ACCEPTED_DRAG.clear()
        drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction,
                  Qt.DropAction.MoveAction)
        if all(str(p) in _ACCEPTED_DRAG for p in paths):
            # 目标格子确实收下了 → 把源格子里的这几个删掉（一图只留一格）
            for it in items:
                self.remove_row(self.row(it))
        _ACCEPTED_DRAG.clear()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count() == 0 and self.placeholder:
            p = QPainter(self.viewport())
            p.setPen(QColor("#aab2bd"))
            p.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter, self.placeholder)

    def _local_paths(self, mime: QMimeData) -> list[Path]:
        if not mime.hasUrls():
            return []
        return [Path(u.toLocalFile()) for u in mime.urls()
                if u.isLocalFile() and core.is_image(Path(u.toLocalFile()))]

    def dragEnterEvent(self, event):
        if self._local_paths(event.mimeData()):
            event.setDropAction(Qt.DropAction.MoveAction
                                if event.source() is not None else Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._local_paths(event.mimeData()):
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.source() is self:          # 自己拖自己：不动，免得顺序乱
            event.ignore()
            return
        paths = self._local_paths(event.mimeData())
        if not paths:
            event.ignore()
            return
        self.add_paths(paths)
        if event.source() is not None:
            # 来自另一个格子：记下来，让源格子知道可以把原件删了
            _ACCEPTED_DRAG.update(str(p) for p in paths)
            event.setDropAction(Qt.DropAction.MoveAction)
        else:
            event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

    # —— 键盘 / 右键 ——
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.remove_selected()
            return
        super().keyPressEvent(event)

    def _menu(self, pos):
        item = self.itemAt(pos)
        menu = QMenu(self)
        if item is not None:
            p = Path(item.data(Qt.ItemDataRole.UserRole))
            row = self.row(item)
            menu.addAction("看大图", lambda: self.window().preview(self, row))
            menu.addAction("用系统看图打开", lambda: open_file(p))
            menu.addAction("在文件夹中显示", lambda: open_in_explorer(p))
            menu.addSeparator()
            menu.addAction("移除这张", lambda: self.remove_row(row))
        menu.addAction("添加图片…", lambda: self.window().pick_files(self))
        menu.addAction("粘贴剪贴板图片", lambda: self.window().paste_image(self))
        menu.addSeparator()
        menu.addAction("清空本格", lambda: self.clear_all())
        menu.exec(self.viewport().mapToGlobal(pos))


# ───────────────────────── 一张卡片 ─────────────────────────

class ImageCard(QFrame):
    """一个格子：标题 + 状态 + 缩略图 + 几个小按钮。"""

    def __init__(self, title: str, subtitle: str = "", height: int = 112,
                 empty_text: str = "缺", placeholder: str = "拖图片到这里\n或点「＋ 添加」",
                 parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setProperty("state", "empty")
        self.empty_text = empty_text
        self.title_label = QLabel(title)
        self.title_label.setObjectName("cardTitle")
        self.sub_label = QLabel(subtitle)
        self.sub_label.setObjectName("hint")
        self.chip = QLabel(empty_text)
        self.chip.setObjectName("chipEmpty")
        self.list = ImageList(self, placeholder)

        head = QHBoxLayout()
        head.setSpacing(6)
        head.addWidget(self.title_label)
        head.addWidget(self.sub_label)
        head.addStretch(1)
        head.addWidget(self.chip)

        self.btn_add = QToolButton(); self.btn_add.setText("＋ 添加")
        self.btn_paste = QToolButton(); self.btn_paste.setText("粘贴")
        self.btn_clear = QToolButton(); self.btn_clear.setText("清空")
        for b in (self.btn_add, self.btn_paste, self.btn_clear):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        tools = QHBoxLayout()
        tools.setSpacing(2)
        tools.addWidget(self.btn_add)
        tools.addWidget(self.btn_paste)
        tools.addWidget(self.btn_clear)
        tools.addStretch(1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)
        lay.addLayout(head)
        lay.addWidget(self.list, 1)
        lay.addLayout(tools)
        self.list.setMinimumHeight(height)

        self.btn_add.clicked.connect(lambda: self.window().pick_files(self.list))
        self.btn_paste.clicked.connect(lambda: self.window().paste_image(self.list))
        self.btn_clear.clicked.connect(self.list.clear_all)
        self.list.changed.connect(self.refresh)
        # 焦点落到列表上时，记住这是「当前格」，给 Ctrl+V / Ctrl+O 用
        self.list.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.list and event.type() == QEvent.Type.FocusIn:
            win = self.window()
            if hasattr(win, "last_list"):
                win.last_list = self.list
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        win = self.window()
        if hasattr(win, "last_list"):
            win.last_list = self.list
        super().mousePressEvent(event)

    def refresh(self):
        n = self.list.count()
        self.chip.setText(self.empty_text if n == 0 else f"{n} 张")
        self.chip.setObjectName("chipEmpty" if n == 0 else "chipFull")
        self.setProperty("state", "empty" if n == 0 else "full")
        for w in (self.chip, self):
            w.style().unpolish(w)
            w.style().polish(w)

    def set_subtitle(self, text: str):
        self.sub_label.setText(text)


# ───────────────────────── 大图预览 ─────────────────────────

class PreviewDialog(QDialog):
    def __init__(self, parent, paths: list[Path], index: int = 0):
        super().__init__(parent)
        self.setWindowTitle("看大图")
        self.resize(900, 720)
        self.paths = list(paths)
        self.i = max(0, min(index, len(self.paths) - 1))
        self.zoom = 1.0
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setMinimumSize(400, 300)
        self.tip = QLabel("← → 换同格里的图　滚轮缩放　Esc 关闭")
        self.tip.setObjectName("hint")
        lay = QVBoxLayout(self)
        lay.addWidget(self.label, 1)
        lay.addWidget(self.tip)
        self.show_current()

    def show_current(self):
        if not self.paths:
            self.label.setText("没有图片")
            return
        p = self.paths[self.i]
        self.setWindowTitle(f"{p.name}　({self.i + 1}/{len(self.paths)})")
        pm = QPixmap(str(p))
        self.raw = pm
        self.render()

    def render(self):
        if getattr(self, "raw", QPixmap()).isNull():
            self.label.setText("读不出这张图")
            return
        avail = self.label.size() * self.zoom
        self.label.setPixmap(self.raw.scaled(
            avail, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.render()

    def wheelEvent(self, event):
        self.zoom = min(6.0, max(0.2, self.zoom * (1.15 if event.angleDelta().y() > 0 else 0.87)))
        self.render()

    def keyPressEvent(self, event):
        k = event.key()
        if k == Qt.Key.Key_Escape:
            self.close()
        elif k in (Qt.Key.Key_Right, Qt.Key.Key_Down) and self.i + 1 < len(self.paths):
            self.i += 1; self.show_current()
        elif k in (Qt.Key.Key_Left, Qt.Key.Key_Up) and self.i > 0:
            self.i -= 1; self.show_current()
        else:
            super().keyPressEvent(event)


# ───────────────────────── 生成线程 ─────────────────────────

class BuildWorker(QThread):
    msg = Signal(str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, week, out, cfg, chat, dates, parent=None):
        super().__init__(parent)
        self.args = (week, out, cfg, chat, dates)

    def run(self):
        week, out, cfg, chat, dates = self.args
        try:
            res = core.build_from_plan(week, out, HERE, cfg, chat, dates,
                                       log=lambda m: self.msg.emit(m))
            self.done.emit(res)
        except Exception:
            self.failed.emit(traceback.format_exc())


# ───────────────────────── 主窗口 ─────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("宣传委员打卡 · 打卡表生成器")
        self.resize(1180, 900)
        self.setMinimumSize(940, 600)
        self.cfg = core.load_config()
        self.cards: dict[str, ImageCard] = {}
        self.last_list: ImageList | None = None
        self.last_out: Path | None = None
        self.worker: BuildWorker | None = None
        self.pool: list[core.Shot] = []
        self._build_ui()
        # 第一次运行时把两个截图文件夹建出来，省得自己新建
        for key in ("chat_dir", "date_dir"):
            try:
                (HERE / str(self.cfg.get(key) or core.DEFAULTS[key])).mkdir(exist_ok=True)
            except Exception:
                pass
        self._load_state_or_scan()
        # 文件夹被搬走以后，快捷方式里的绝对路径会失效 —— 启动时顺手修一下
        try:
            core.ensure_shortcut(HERE, APP_DIR / "打卡界面.py", APP_DIR / "打卡图标.ico")
        except Exception:
            pass

    # ── 界面 ────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(14, 12, 14, 10)
        outer.setSpacing(10)
        outer.addWidget(self._top_bar())

        body = QWidget()
        grid = QVBoxLayout(body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)

        days = QGridLayout()
        days.setSpacing(10)
        for i, wd in enumerate(core.DAYS):
            card = ImageCard(f"周{wd}", "", height=112)
            self.cards[wd] = card
            days.addWidget(card, i // CARDS_PER_ROW, i % CARDS_PER_ROW)
        for c in range(CARDS_PER_ROW):
            days.setColumnStretch(c, 1)
        grid.addLayout(days)

        trays = QHBoxLayout()
        trays.setSpacing(10)
        self.card_spare = ImageCard("备用格", "日期截图放这里，每行 3 张", height=112,
                                    empty_text="0 张", placeholder="日期截图拖到这里")
        self.card_left = ImageCard("未归位", "不属于本周的图，可拖到上面的格子", height=112,
                                   empty_text="0 张", placeholder="没有多余的图")
        trays.addWidget(self.card_spare, 1)
        trays.addWidget(self.card_left, 1)
        grid.addLayout(trays)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        outer.addWidget(self._bottom_bar())

        # 菜单
        m_file = self.menuBar().addMenu("文件(&F)")
        self._act(m_file, "重新扫描截图文件夹", "Ctrl+R", self.rescan_with_confirm)
        self._act(m_file, "添加图片到当前格…", "Ctrl+O", lambda: self.pick_files(self.current_list()))
        self._act(m_file, "打开聊天记录截图文件夹", None, lambda: open_in_explorer(HERE / str(self.cfg["chat_dir"])))
        self._act(m_file, "打开日期截图文件夹", None, lambda: open_in_explorer(HERE / str(self.cfg["date_dir"])))
        m_file.addSeparator()
        self._act(m_file, "打开输出文件夹", None, lambda: open_in_explorer(HERE))
        m_file.addSeparator()
        self._act(m_file, "退出", "Ctrl+Q", self.close)

        m_edit = self.menuBar().addMenu("编辑(&E)")
        self._act(m_edit, "粘贴剪贴板图片到当前格", "Ctrl+V", self.paste_current)
        self._act(m_edit, "删除当前格选中的图", "Delete", self.remove_current)
        self._act(m_edit, "清空当前格", None, lambda: self.current_list().clear_all())
        m_edit.addSeparator()
        self._act(m_edit, "重新归位（按截图日期重排）", None, lambda: self.rescan(force=True))
        self._act(m_edit, "全部清空", None, self.clear_all)

        m_help = self.menuBar().addMenu("帮助(&H)")
        self._act(m_help, "使用说明", "F1", self.show_help)
        self._act(m_help, "关于", None, lambda: QMessageBox.information(
            self, "关于",
            "宣传委员打卡 · 打卡表生成器\n\n"
            "界面版 打卡界面.py　核心逻辑 打卡核心.py\n"
            "命令行版 打卡表.py（用法不变，可加 --week N）\n\n"
            f"程序文件夹：{APP_DIR}\n"
            f"图片 / 模板 / 生成的 Word：{HERE}"))

        self.setStatusBar(QStatusBar())
        for wd in core.DAYS:
            self.cards[wd].list.changed.connect(self.update_summary)
        self.card_spare.list.changed.connect(self.update_summary)
        self.card_left.list.changed.connect(self.update_summary)

    def _act(self, menu, text, shortcut, slot):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.triggered.connect(slot)
        menu.addAction(a)
        return a

    def _top_bar(self) -> QWidget:
        box = QFrame()
        box.setObjectName("card")
        lay = QGridLayout(box)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setHorizontalSpacing(8)
        lay.setVerticalSpacing(8)

        # 第一行：周次
        self.btn_prev = QToolButton(); self.btn_prev.setText("◀")
        self.btn_next = QToolButton(); self.btn_next.setText("▶")
        self.spin_week = QSpinBox(); self.spin_week.setRange(1, 30)
        self.spin_week.setSuffix(" 周")
        self.spin_week.setFixedWidth(84)
        self.lbl_range = QLabel("")
        self.lbl_range.setObjectName("big")
        self.btn_auto = QPushButton("按截图定周次")
        self.btn_rescan = QPushButton("重新扫描文件夹")
        self.btn_help = QPushButton("使用说明")

        w1 = QHBoxLayout(); w1.setSpacing(6)
        w1.addWidget(QLabel("周次"))
        w1.addWidget(self.btn_prev)
        w1.addWidget(self.spin_week)
        w1.addWidget(self.btn_next)
        w1.addSpacing(8)
        w1.addWidget(self.lbl_range)
        w1.addStretch(1)
        w1.addWidget(self.btn_auto)
        w1.addWidget(self.btn_rescan)
        w1.addWidget(self.btn_help)

        # 第二行：班级 / 姓名 / 模板
        self.ed_class = QLineEdit(str(self.cfg.get("class_name", "")))
        self.ed_class.setFixedWidth(150)
        self.ed_name = QLineEdit(str(self.cfg.get("student_name", "")))
        self.ed_name.setFixedWidth(110)
        self.lbl_tpl = QLabel("")
        self.lbl_tpl.setObjectName("hint")
        btn_tpl = QPushButton("换模板…")

        w2 = QHBoxLayout(); w2.setSpacing(6)
        w2.addWidget(QLabel("班级"))
        w2.addWidget(self.ed_class)
        w2.addWidget(QLabel("姓名"))
        w2.addWidget(self.ed_name)
        w2.addSpacing(10)
        w2.addWidget(QLabel("模板"))
        w2.addWidget(self.lbl_tpl, 1)
        w2.addWidget(btn_tpl)

        lay.addLayout(w1, 0, 0)
        lay.addLayout(w2, 1, 0)

        self.spin_week.valueChanged.connect(self.on_week_changed)
        self.btn_prev.clicked.connect(lambda: self.spin_week.setValue(self.spin_week.value() - 1))
        self.btn_next.clicked.connect(lambda: self.spin_week.setValue(self.spin_week.value() + 1))
        self.btn_auto.clicked.connect(self.auto_week)
        self.btn_rescan.clicked.connect(self.rescan_with_confirm)
        self.btn_help.clicked.connect(self.show_help)
        btn_tpl.clicked.connect(self.pick_template)
        self.ed_class.editingFinished.connect(self.save_config_from_ui)
        self.ed_name.editingFinished.connect(self.save_config_from_ui)
        return box

    def _bottom_bar(self) -> QWidget:
        box = QFrame()
        box.setObjectName("card")
        lay = QHBoxLayout(box)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(800)
        self.log.setFixedHeight(132)
        self.log.setPlaceholderText("这里会显示归位情况和生成结果…")

        right = QVBoxLayout()
        right.setSpacing(8)
        self.btn_gen = QPushButton("生成 Word 打卡表")
        self.btn_gen.setObjectName("primary")
        self.btn_gen.setMinimumHeight(38)
        self.btn_open_out = QPushButton("打开刚生成的文档")
        self.btn_open_dir = QPushButton("打开输出文件夹")
        self.btn_open_out.setEnabled(False)
        right.addWidget(self.btn_gen)
        right.addWidget(self.btn_open_out)
        right.addWidget(self.btn_open_dir)
        right.addStretch(1)

        lay.addWidget(self.log, 1)
        lay.addLayout(right)

        self.btn_gen.clicked.connect(self.generate)
        self.btn_open_out.clicked.connect(lambda: open_file(self.last_out) if self.last_out else None)
        self.btn_open_dir.clicked.connect(lambda: open_in_explorer(HERE))
        return box

    # ── 小操作 ──────────────────────────────────────────
    def current_list(self) -> ImageList:
        if self.last_list is not None:
            return self.last_list
        return self.cards["六"].list

    def log_line(self, text: str):
        self.log.appendPlainText(text)

    def status(self, text: str):
        self.statusBar().showMessage(text)

    def refresh_titles(self):
        week = self.spin_week.value()
        try:
            start, end = core.week_range(week, self.cfg)
        except Exception:
            return
        self.lbl_range.setText(f"第{core.cn_num(week)}周　{start:%m/%d}（周六）　→　{end:%m/%d}（周五）")
        for i, wd in enumerate(core.DAYS):
            d = start + timedelta(days=i)
            self.cards[wd].set_subtitle(f"{d.month}/{d.day}")
        self.lbl_tpl.setText(str(self.cfg.get("template_file", "")))
        self.update_summary()

    def update_summary(self):
        filled = sum(1 for wd in core.DAYS if self.cards[wd].list.count())
        spare = self.card_spare.list.count()
        left = self.card_left.list.count()
        missing = [core.WD_CN[wd] for wd in core.DAYS if not self.cards[wd].list.count()]
        txt = f"已归位 {filled}/7 天　·　备用 {spare} 张　·　未归位 {left} 张"
        if missing:
            txt += "　·　缺：" + "、".join(missing)
        self.status(txt)
        for wd in core.DAYS:
            self.cards[wd].refresh()
        self.card_spare.refresh()
        self.card_left.refresh()

    # ── 配置 ────────────────────────────────────────────
    def save_config_from_ui(self):
        self.cfg["class_name"] = self.ed_class.text().strip() or core.DEFAULTS["class_name"]
        self.cfg["student_name"] = self.ed_name.text().strip() or core.DEFAULTS["student_name"]
        core.save_config(self.cfg)

    def pick_template(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择打卡表模板", str(HERE), "Word 文档 (*.docx)")
        if f:
            self.cfg["template_file"] = Path(f).name
            if Path(f).parent != HERE:
                self.log_line(f"[提示] 模板换成了 {f}；程序只会读这个名字，请把模板放到 {HERE} 里。")
            core.save_config(self.cfg)
            self.refresh_titles()

    # ── 选文件 / 粘贴 ───────────────────────────────────
    def pick_files(self, target: ImageList | None = None):
        target = target or self.current_list()
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择截图", str(HERE), "图片 (*.png *.jpg *.jpeg *.webp *.bmp *.gif)")
        if files:
            n = target.add_paths([Path(f) for f in files])
            self.log_line(f"加入 {n} 张图。")
            self.update_summary()

    def paste_image(self, target: ImageList | None = None):
        target = target or self.current_list()
        cb = QApplication.clipboard()
        img = cb.image()
        if img.isNull() and cb.mimeData().hasUrls():
            paths = [Path(u.toLocalFile()) for u in cb.mimeData().urls() if u.isLocalFile()]
            n = target.add_paths(paths)
            if n:
                self.log_line(f"从剪贴板加入了 {n} 个文件。")
                self.update_summary()
            return
        if img.isNull():
            self.log_line("[提示] 剪贴板里没有图片。用 Win+Shift+S 或微信截图后再按 Ctrl+V。")
            return
        folder = HERE / str(self.cfg.get("clip_dir") or core.DEFAULTS["clip_dir"])
        folder.mkdir(exist_ok=True)
        p = folder / f"粘贴_{datetime.now():%Y%m%d_%H%M%S}.png"
        if img.save(str(p)):
            target.add_paths([p])
            self.log_line(f"剪贴板图片已存为 {p.name} 并放进当前格。")
            self.update_summary()
        else:
            self.log_line("[!] 剪贴板图片保存失败。")

    def remove_current(self):
        self.current_list().remove_selected()
        self.update_summary()

    def paste_current(self):
        self.paste_image(self.current_list())

    def clear_all(self):
        if QMessageBox.question(self, "确认", "清空所有格子里的图片？") != QMessageBox.StandardButton.Yes:
            return
        for wd in core.DAYS:
            self.cards[wd].list.clear_all()
        self.card_spare.list.clear_all()
        self.card_left.list.clear_all()
        self.update_summary()

    def preview(self, source: ImageList, row: int):
        paths = source.paths()
        if paths:
            PreviewDialog(self, paths, row).exec()

    # ── 周次 ────────────────────────────────────────────
    def on_week_changed(self, _v):
        self.refresh_titles()
        if self.pool:
            off = [s for s in self.pool if s.kind == "chat" and s.week != self.spin_week.value()]
            if off:
                self.log_line(f"[注意] 有 {len(off)} 张截图不属于第{core.cn_num(self.spin_week.value())}周，"
                              f"要重新归位请点「重新扫描文件夹」。")

    def auto_week(self):
        shots = self.pool or core.collect(HERE, self.cfg)
        if not shots:
            self.log_line("[提示] 两个截图文件夹都是空的，周次按今天算。")
            self.spin_week.setValue(max(1, core.today_week(self.cfg)))
            return
        week, tally = core.guess_week(shots, self.cfg)
        detail = "、".join(f"第{core.cn_num(k)}周 {v} 张" for k, v in sorted(tally.items()))
        self.log_line(f"按截图日期统计：{detail} → 定为第{core.cn_num(week)}周")
        self.spin_week.setValue(week)

    # ── 扫描归位 ────────────────────────────────────────
    def scan_into_slots(self, week: int | None = None):
        self.pool = core.collect(HERE, self.cfg)
        shots = self.pool
        if week is None:
            week = core.guess_week(shots, self.cfg)[0] if shots else max(1, core.today_week(self.cfg))
            self.spin_week.blockSignals(True)
            self.spin_week.setValue(week)
            self.spin_week.blockSignals(False)
        else:
            self.spin_week.blockSignals(True)
            self.spin_week.setValue(week)
            self.spin_week.blockSignals(False)

        for wd in core.DAYS:
            self.cards[wd].list.clear_all()
        self.card_spare.list.clear_all()
        self.card_left.list.clear_all()

        chat, leftover = core.split(shots, week)
        for wd in core.DAYS:
            self.cards[wd].list.add_paths([s.path for s in chat[wd]], quiet=True)
        self.card_spare.list.add_paths([s.path for s in shots if s.kind == "date"], quiet=True)
        self.card_left.list.add_paths([s.path for s in leftover if s.kind == "chat"], quiet=True)

        self.log_line(f"—— 扫描完成：第{core.cn_num(week)}周 ——")
        for wd in core.DAYS:
            names = "、".join(short_name(p) for p in self.cards[wd].list.paths())
            if names:
                self.log_line(f"  周{wd}（{core.WD_CN[wd]}）：{names}")
        missing = [f"周{wd}" for wd in core.DAYS if not self.cards[wd].list.count()]
        if missing:
            self.log_line("  还缺：" + "、".join(missing))
        dates = self.card_spare.list.paths()
        self.log_line(f"  备用格：{'、'.join(short_name(p) for p in dates) if dates else '缺'}")
        other = [s for s in leftover if s.kind == "chat"]
        if other:
            self.log_line("  这些不属于本周，放在「未归位」里，要收就拖上去：")
            for s in other:
                self.log_line(f"      {short_name(s.path)}（第{core.cn_num(s.week)}周）")
        self.refresh_titles()

    def rescan_with_confirm(self):
        self.rescan(force=True)

    def rescan(self, force: bool = False):
        has_any = any(self.cards[wd].list.count() for wd in core.DAYS) or self.card_spare.list.count()
        if force and has_any:
            r = QMessageBox.question(
                self, "重新扫描",
                "会按两个截图文件夹里的图重新归位，当前格子里的安排会被覆盖（拖进去的图不影响原文件）。\n继续？")
            if r != QMessageBox.StandardButton.Yes:
                return
        self.scan_into_slots()

    # ── 生成 ────────────────────────────────────────────
    def gather(self):
        week = self.spin_week.value()
        chat = {wd: self.cards[wd].list.paths() for wd in core.DAYS}
        dates = self.card_spare.list.paths()
        return week, chat, dates

    def generate(self):
        self.save_config_from_ui()
        week, chat, dates = self.gather()
        missing = [core.WD_CN[wd] for wd in core.DAYS if not chat[wd]]
        if missing:
            r = QMessageBox.question(
                self, "还没凑齐",
                f"还缺 {len(missing)} 天：{'、'.join(missing)}\n"
                "仍然生成的话，那几天的格子会是空的（以后可以补上再生成）。\n\n现在生成吗？")
            if r != QMessageBox.StandardButton.Yes:
                return
        if not dates:
            self.log_line("[提示] 备用格是空的，表格里那几格会留白。")
        out = core.out_path(week, self.cfg.get("class_name", ""), HERE)
        if out.exists():
            r = QMessageBox.question(self, "已存在", f"{out.name} 已经存在，覆盖它吗？")
            if r != QMessageBox.StandardButton.Yes:
                return
        self.btn_gen.setEnabled(False)
        self.btn_gen.setText("正在生成…")
        self.log_line(f"—— 开始生成 {out.name} ——")
        self.worker = BuildWorker(week, out, dict(self.cfg), chat, dates, self)
        self.worker.msg.connect(self.log_line)
        self.worker.done.connect(self.on_built)
        self.worker.failed.connect(self.on_build_failed)
        self.worker.start()

    def on_built(self, res: core.BuildResult):
        self.btn_gen.setEnabled(True)
        self.btn_gen.setText("生成 Word 打卡表")
        self.last_out = res.out
        self.btn_open_out.setEnabled(True)
        self.log_line(f"✅ 完成：{res.out.name}（{res.size_kb:.0f} KB，{res.used} 张图）")
        if res.missing:
            self.log_line(f"   还缺：{'、'.join(res.missing)}")
        self.save_state()
        r = QMessageBox.information(
            self, "生成好了",
            f"{res.out.name}\n共 {res.used} 张图，{res.size_kb:.0f} KB。\n\n现在打开看看吗？",
            QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Close)
        if r == QMessageBox.StandardButton.Open:
            open_file(res.out)

    def on_build_failed(self, text: str):
        self.btn_gen.setEnabled(True)
        self.btn_gen.setText("生成 Word 打卡表")
        self.log_line("❌ 生成失败：\n" + text)
        QMessageBox.critical(self, "生成失败", text.strip().splitlines()[-1] if text.strip() else "未知错误")

    # ── 状态存取 ────────────────────────────────────────
    def save_state(self):
        week, chat, dates = self.gather()
        data = {
            "week": week,
            "class_name": self.ed_class.text(),
            "student_name": self.ed_name.text(),
            "chat": {wd: [str(p) for p in chat[wd]] for wd in core.DAYS},
            "dates": [str(p) for p in dates],
            "leftover": [str(p) for p in self.card_left.list.paths()],
        }
        try:
            (HERE / core.STATE_FILE).write_text(
                json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        except Exception:
            pass

    def _load_state_or_scan(self):
        p = HERE / core.STATE_FILE
        if p.is_file():
            try:
                data = json.loads(p.read_text("utf-8"))
                week = int(data.get("week") or core.today_week(self.cfg))
                self.ed_class.setText(str(data.get("class_name") or self.cfg.get("class_name", "")))
                self.ed_name.setText(str(data.get("student_name") or self.cfg.get("student_name", "")))
                keep = 0
                self.spin_week.blockSignals(True)
                self.spin_week.setValue(max(1, week))
                self.spin_week.blockSignals(False)
                for wd in core.DAYS:
                    ps = [Path(x) for x in (data.get("chat", {}).get(wd) or []) if Path(x).is_file()]
                    keep += self.cards[wd].list.add_paths(ps, quiet=True)
                ds = [Path(x) for x in (data.get("dates") or []) if Path(x).is_file()]
                keep += self.card_spare.list.add_paths(ds, quiet=True)
                ls = [Path(x) for x in (data.get("leftover") or []) if Path(x).is_file()]
                keep += self.card_left.list.add_paths(ls, quiet=True)
                if keep:
                    self.log_line(f"已恢复上次的安排（{keep} 张图）。文件名有变化请点「重新扫描文件夹」。")
                    self.refresh_titles()
                    return
            except Exception:
                self.log_line("[提示] 上次的安排读不出来，改成扫描文件夹。")
        self.scan_into_slots()
        self.log_line("用法：把截图拖进对应的星期格子 → 看下周次对不对 → 点右下角「生成 Word 打卡表」。")

    def show_help(self):
        QMessageBox.information(self, "使用说明", (
            "三步做完一张打卡表：\n\n"
            "1）把截图放进格子\n"
            "     · 从资源管理器直接拖到对应的星期格子里；\n"
            "     · 或点格子里的「＋ 添加」选文件；\n"
            "     · 或者截图后直接按 Ctrl+V 粘到当前格；\n"
            "     · 拖错了：再拖到别的格子，或选中后按 Delete。\n\n"
            "2）看一眼周次对不对\n"
            "     周次默认按截图日期自动算，用 ◀ ▶ 改；\n"
            "     「按截图定周次」= 按现有截图的日期重新投票决定。\n\n"
            "3）点「生成 Word 打卡表」\n"
            "     生成的文件就在本文件夹里，可以直接打开检查。\n\n"
            "其它：\n"
            "     · 「备用格」= 日期截图，每行 3 张，多了自动加行；\n"
            "     · 「未归位」= 不属于本周的图，不会写进表格；\n"
            "     · 双击缩略图看大图（← → 翻页，滚轮缩放）；\n"
            "     · 班级、姓名、模板改了会自动记住。\n\n"
            "命令行版依然可用：python 打卡表.py --week 6"
        ))

    def closeEvent(self, event):
        self.save_config_from_ui()
        self.save_state()
        if self.worker and self.worker.isRunning():
            self.worker.wait(3000)
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("宣传委员打卡")
    app.setStyleSheet(QSS)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
