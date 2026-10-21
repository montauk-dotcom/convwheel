"""Мелкие кроссплатформенные утилиты: пути, поиск программ, открытие папок."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

# На Windows не показываем чёрное окно консоли у дочерних процессов
NO_WINDOW = 0x08000000 if IS_WIN else 0


def config_dir() -> Path:
    if IS_WIN:
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif IS_MAC:
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / "ConvWheel"
    d.mkdir(parents=True, exist_ok=True)
    return d


def run(cmd: list[str], timeout: float | None = None, **kw) -> subprocess.CompletedProcess:
    """subprocess.run без всплывающей консоли на Windows."""
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        creationflags=NO_WINDOW,
        **kw,
    )


def find_soffice() -> str | None:
    """Ищет LibreOffice (soffice) в стандартных местах."""
    candidates: list[str] = []
    env = os.environ.get("CONVWHEEL_SOFFICE")
    if env:
        candidates.append(env)
    if IS_WIN:
        for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                     r"C:\Program Files", r"C:\Program Files (x86)"):
            if root:
                candidates.append(os.path.join(root, "LibreOffice", "program", "soffice.exe"))
    elif IS_MAC:
        candidates += [
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
            str(Path.home() / "Applications/LibreOffice.app/Contents/MacOS/soffice"),
        ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    return None


def find_ffmpeg() -> str | None:
    env = os.environ.get("CONVWHEEL_FFMPEG")
    if env and os.path.isfile(env):
        return env
    try:  # бинарник ffmpeg, поставляемый вместе с imageio-ffmpeg
        import imageio_ffmpeg
        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and os.path.isfile(p):
            return p
    except Exception:
        pass
    p = shutil.which("ffmpeg")
    if p:
        return p
    if IS_MAC:
        for c in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
            if os.path.isfile(c):
                return c
    return None


def has_ms_office(app: str = "Word") -> bool:
    """Есть ли установленный Microsoft Office (только Windows, через реестр COM)."""
    if not IS_WIN:
        return False
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"{app}.Application\\CLSID"))
        return True
    except OSError:
        return False


def reveal_in_file_manager(path: str | Path) -> None:
    path = str(path)
    try:
        if IS_WIN:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)], creationflags=NO_WINDOW)
        elif IS_MAC:
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])
    except Exception:
        pass


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if size < 1024 or unit == "ГБ":
            return f"{size:.0f} {unit}" if unit == "Б" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} Б"
