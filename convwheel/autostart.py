"""Автозапуск при входе в систему: реестр Run (Windows) или LaunchAgent (macOS)."""
from __future__ import annotations

import plistlib
import sys
from pathlib import Path

from . import APP_ID, APP_NAME
from .platform_utils import IS_MAC, IS_WIN

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{APP_ID}.plist"


def _command() -> list[str]:
    if getattr(sys, "frozen", False):          # собранное приложение (PyInstaller)
        exe = sys.executable
        if IS_MAC and ".app/Contents/MacOS/" in exe:
            return [exe]
        return [exe]
    main = Path(__file__).resolve().parent.parent / "main.py"
    py = sys.executable
    if IS_WIN and py.lower().endswith("python.exe"):
        py = py[:-10] + "pythonw.exe"          # без консольного окна
    return [py, str(main)]


def is_enabled() -> bool:
    if IS_WIN:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.QueryValueEx(k, APP_NAME)
                return True
        except OSError:
            return False
    if IS_MAC:
        return PLIST.exists()
    return False


def set_enabled(on: bool) -> None:
    if IS_WIN:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                cmd = " ".join(f'"{c}"' for c in _command())
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except OSError:
                    pass
    elif IS_MAC:
        if on:
            PLIST.parent.mkdir(parents=True, exist_ok=True)
            with open(PLIST, "wb") as f:
                plistlib.dump({"Label": APP_ID, "ProgramArguments": _command(),
                               "RunAtLoad": True, "KeepAlive": False,
                               "ProcessType": "Interactive"}, f)
        else:
            PLIST.unlink(missing_ok=True)
