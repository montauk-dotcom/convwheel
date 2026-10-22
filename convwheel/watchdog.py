"""macOS: сторож, который поднимает ConvWheel после аварийного падения.

На macOS основная часть работает прямо в процессе приложения (иначе не работают «Открыть
ещё раз» и значок в строке меню), поэтому страхует её маленький процесс-наблюдатель:

  • агент закрылся сам («Выход», выход из системы) — он заранее пишет exit_reason=quit;
  • просит перезапуск (после выдачи разрешений) — exit_reason=restart;
  • упал (abort / segfault) — faulthandler дописывает стек в crash.log, причины нет.
    Тогда сторож запускает приложение снова (не больше 5 раз за 2 минуты).
  • «Завершить принудительно» из Мониторинга системы — ни причины, ни записи в crash.log:
    это осознанное действие, и мы его уважаем — не перезапускаем.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from .crashlog import install as install_crashlog
from .crashlog import write as log
from .platform_utils import config_dir

MAX_CRASHES = 5
WINDOW = 120.0


def reason_file() -> Path:
    return config_dir() / "exit_reason"


def set_exit_reason(reason: str) -> None:
    try:
        reason_file().write_text(reason, encoding="utf-8")
    except OSError:
        pass


def crash_log_size() -> int:
    try:
        return (config_dir() / "crash.log").stat().st_size
    except OSError:
        return 0


def spawn_for(pid: int) -> None:
    """Запускается агентом при старте."""
    try:
        reason_file().unlink()
    except OSError:
        pass
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--watchdog", str(pid)]
    else:
        cmd = [sys.executable, str(Path(__file__).resolve().parent.parent / "main.py"), "--watchdog", str(pid)]
    env = dict(os.environ, CONVWHEEL_CRASHLOG_SIZE=str(crash_log_size()))
    subprocess.Popen(cmd, env=env, start_new_session=True, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _relaunch() -> None:
    exe = sys.executable
    if getattr(sys, "frozen", False) and ".app/Contents/MacOS/" in exe:
        app = exe[: exe.index(".app/") + 4]
        subprocess.Popen(["open", "-n", app])
    elif getattr(sys, "frozen", False):
        subprocess.Popen([exe], start_new_session=True)
    else:
        subprocess.Popen([exe, str(Path(__file__).resolve().parent.parent / "main.py")],
                         start_new_session=True)


def _crash_allowed() -> bool:
    hist = config_dir() / "crash_history.json"
    now = time.time()
    try:
        times = [t for t in json.loads(hist.read_text()) if now - t < WINDOW]
    except (OSError, ValueError):
        times = []
    times.append(now)
    try:
        hist.write_text(json.dumps(times))
    except OSError:
        pass
    return len(times) <= MAX_CRASHES


def main(pid: int) -> int:
    install_crashlog("watchdog")
    start_size = int(os.environ.get("CONVWHEEL_CRASHLOG_SIZE", "0") or 0)
    while _alive(pid):
        time.sleep(1.0)
    time.sleep(0.3)
    try:
        reason = reason_file().read_text(encoding="utf-8").strip()
    except OSError:
        reason = ""
    if reason == "quit":
        return 0
    if reason == "restart":
        _relaunch()
        return 0
    if crash_log_size() <= start_size:
        log("ConvWheel был завершён принудительно — не перезапускаю.")
        return 0
    if not _crash_allowed():
        log("Слишком много падений подряд — сторож не перезапускает. Подробности — в crash.log.")
        return 1
    log("ConvWheel упал — перезапускаю.")
    _relaunch()
    return 0
