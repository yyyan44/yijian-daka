# -*- coding: utf-8 -*-
r"""一键打卡 —— 放哪都能双击的入口。

这个文件（和它旁边的「程序」文件夹、模板、截图文件夹）可以整个搬去任何地方：
双击它就能打开打卡表生成器，顺手还会把旁边的「一键打卡.lnk」修到新的位置。

注意：它靠 .pyw 的文件关联（也就是装了 Python）来运行，没有黑窗口。
如果哪天双击没反应，改用「程序\打卡界面.py」或者见「使用说明.txt」。
"""

import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # 本文件所在文件夹 = 整个工具的家
PROG = HERE / "程序"

sys.path.insert(0, str(PROG))

try:
    import 打卡核心 as core

    # 搬过家以后快捷方式会失效，这里按当前位置重建一个
    try:
        core.ensure_shortcut(HERE, PROG / "打卡界面.py", PROG / "打卡图标.ico")
    except Exception:
        pass

    runpy.run_path(str(PROG / "打卡界面.py"), run_name="__main__")
except Exception:
    import traceback
    import tkinter.messagebox as mb

    try:
        mb.showerror("打卡表生成器启动失败",
                     "启动时出错了，把下面这段发给帮你做这个工具的人：\n\n"
                     + traceback.format_exc())
    except Exception:
        pass
    raise
