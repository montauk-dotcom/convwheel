"""Журнал ошибок: необработанные исключения, сообщения Qt и аварийные падения (faulthandler).

Всё пишется в convwheel.log в папке настроек — его можно прислать для разбора.
"""
from __future__ import annotations

import faulthandler
import os
import sys
import threading
import time
import traceback

from .platform_utils import config_dir

_fh = None
_role = "app"
MAX_LOG = 2 * 1024 * 1024


def log_path():
    return config_dir() / "convwheel.log"


def write(text: str) -> None:
    try:
        p = log_path()
        if p.exists() and p.stat().st_size > MAX_LOG:      # не даём журналу разрастись
            p.replace(p.with_suffix(".old.log"))
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{_role} {os.getpid()}] {text.rstrip()}\n")
    except Exception:
        pass


def install(role: str) -> None:
    global _fh, _role
    _role = role
    try:   # сбой в C-коде (segfault/abort): Python-стек всех потоков попадёт в журнал
        _fh = open(config_dir() / "crash.log", "a", encoding="utf-8")
        _fh.write(f"\n--- {role} {os.getpid()} запущен {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        _fh.flush()
        faulthandler.enable(file=_fh, all_threads=True)
    except Exception:
        pass

    def hook(et, ev, tb):
        write("Необработанное исключение:\n" + "".join(traceback.format_exception(et, ev, tb)))

    sys.excepthook = hook
    threading.excepthook = lambda a: hook(a.exc_type, a.exc_value, a.exc_traceback)


def install_qt() -> None:
    """Сообщения Qt (включая фатальные) — в журнал."""
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler

        def handler(mode, ctx, msg):
            if mode in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
                if "propagateSizeHints" in msg or "QFont::" in msg:
                    return
                write(f"Qt: {msg}")

        qInstallMessageHandler(handler)
    except Exception:
        pass
