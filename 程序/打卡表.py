# -*- coding: utf-8 -*-
r"""命令行版：把「聊天记录截图」「日期截图」两个文件夹里的图填进打卡表模板。

想更省事就用图形界面版 —— 双击「打卡界面.py」或「一键打卡」。

用法
----
    python 打卡表.py                 # 按截图日期自动定周次，直接生成
    python 打卡表.py --week 6        # 指定第 6 周
    python 打卡表.py --check         # 只看会怎么归位，不生成 Word
    python 打卡表.py --out 别的名字.docx

周次不用你算：脚本按「第1周周一」＋「周期从周六起算」自动推算今天属于第几周，
所以隔一周、隔两周轮流做也不会错。表格里的日期也自动跟着变。

需要：Python 3.9+ 和 Pillow（pip install pillow）。模板要和本文件放在一起。
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import 打卡核心 as core

APP_DIR = Path(__file__).resolve().parent    # 程序在哪
HERE = core.data_root()                      # 模板、截图、生成的 Word 在哪


def main() -> int:
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    cfg = core.load_config()
    template = HERE / str(cfg["template_file"])
    if not template.is_file():
        print(f"找不到模板：{template}\n模板要放在 {HERE} （和「程序」文件夹平级）。")
        return 1

    chat_dir = HERE / str(cfg["chat_dir"])
    date_dir = HERE / str(cfg["date_dir"])
    chat_dir.mkdir(exist_ok=True)
    date_dir.mkdir(exist_ok=True)

    argv = sys.argv[1:]
    check_only = "--check" in argv

    def arg_value(flag: str) -> str | None:
        if flag in argv:
            i = argv.index(flag)
            if i + 1 < len(argv):
                return argv[i + 1]
        return None

    shots = core.collect(HERE, cfg)
    imgs = [s.path for s in shots]

    # ── 定周次 ─────────────────────────────────────────────
    week_arg = arg_value("--week")
    if week_arg:
        week = int(week_arg)
        print(f"（手动指定）第{core.cn_num(week)}周")
    elif shots:
        print("=== 按截图时间戳定周次 ===")
        week, tally = core.guess_week(shots, cfg)
        for s in shots:
            print(f"  {s.path.name:<32} {s.day:%Y-%m-%d}（{s.how}）→ 第{core.cn_num(s.week)}周")
        odd = [s for s in shots if s.week != week and s.kind == "chat"]
        if odd:
            print(f"  [!] 有 {len(odd)} 张不属于第{core.cn_num(week)}周，本表不收："
                  + "、".join(s.path.name for s in odd))
        print(f"→ 本表定为：第{core.cn_num(week)}周\n")
    else:
        week = core.today_week(cfg)
        print(f"（两个截图文件夹都是空的，先按今天算：第{core.cn_num(week)}周）\n")

    if week < 1:
        print(f"按截图时间算落在了第 {week} 周（还没开学？）。请用 --week N 指定。")
        return 1

    chat_shots, leftover = core.split(shots, week)
    date_shots = [s for s in shots if s.kind == "date"]
    if leftover and any(s.kind == "chat" for s in leftover):
        pass  # 上面已经提示过

    # ── 打印归位结果 ───────────────────────────────────────
    print("=== 聊天记录截图 ===")
    for wd in core.DAYS:
        names = "、".join(s.path.name for s in chat_shots[wd]) or "（缺）"
        print(f"  {core.WD_CN[wd]:<5} {names}")
        for s in chat_shots[wd]:
            if not s.from_name:
                print(f"        （文件名没写星期几，按截图日期归到这里：{s.path.name}）")
    print("=== 日期截图（备用格） ===")
    print("  " + ("、".join(s.path.name for s in date_shots) if date_shots else "（缺）"))
    for s in leftover:
        if s.kind == "chat":
            print(f"  [!] 不属于本周（第{core.cn_num(s.week)}周），没放：{s.path.name}")
    print()

    if check_only:
        print("（--check：只看归位结果，没有生成 Word）")
        return 0

    start, end = core.week_range(week, cfg)
    out = Path(arg_value("--out") or core.out_path(week, str(cfg["class_name"]), HERE))
    if not out.is_absolute():
        out = HERE / out
    print(f"本次周期：{start:%m/%d}（周六） ~ {end:%m/%d}（周五）")
    print(f"聊天记录截图目录：{chat_dir}")
    print(f"日期截图目录：    {date_dir}")
    print()

    res = core.build_from_plan(
        week, out, HERE, cfg,
        chat={wd: [s.path for s in chat_shots[wd]] for wd in core.DAYS},
        dates=[s.path for s in date_shots],
        log=print)

    print(f"\n已生成：{res.out}  （{res.size_kb:.0f} KB）")
    if res.missing:
        print(f"有 {len(res.missing)} 天没图，补进「{cfg['chat_dir']}」再跑一次就能补上。")
        global PAUSE_AT_END
        PAUSE_AT_END = True   # 有缺图：把窗口留住，方便看清缺哪几天
    return 0


PAUSE_AT_END = False


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    except Exception:
        import traceback
        traceback.print_exc()
    if (code or PAUSE_AT_END) and sys.stdin and sys.stdin.isatty():
        try:
            input("\n按回车关闭 . . .")
        except Exception:
            pass
    sys.exit(code)
