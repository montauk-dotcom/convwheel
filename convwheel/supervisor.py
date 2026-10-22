"""Сторож: то, что запускается двойным кликом по ConvWheel (и при входе в систему).

Он лишь держит единственный экземпляр и запускает основную часть («агент» — значок,
перехват мыши, колесо) отдельным процессом. Если агент упадёт, сторож тут же запустит
его снова — значок пропадёт на секунду, но приложение не «закроется».

  код выхода агента 0  → пользователь нажал «Выход» → сторож тоже завершается
  код выхода агента 75 → просьба перезапуститься (после выдачи разрешений macOS)
  любой другой         → падение → перезапуск (не больше 5 раз за 2 минуты)
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import ipc
from .crashlog import install as install_crashlog
from .crashlog import write as log
from .platform_utils import IS_WIN, config_dir

EXIT_QUIT = 0
EXIT_RESTART = 75
MAX_CRASHES = 5
CRASH_WINDOW = 120.0

_lock_handle = None


def acquire_single_instance() -> bool:
    """Блокировка на уровне ОС — снимается сама, даже если процесс убит."""
    global _lock_handle
    path = config_dir() / "instance.lock"
    try:
        f = open(path, "a+")
        if IS_WIN:
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_handle = f
        return True
    except OSError:
        return False


def agent_command(extra: list[str] | None = None) -> list[str]:
    args = ["--agent", "--supervisor-pid", str(os.getpid()), *(extra or [])]
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    main_py = str(Path(__file__).resolve().parent.parent / "main.py")
    py = sys.executable
    if IS_WIN and py.lower().endswith("python.exe") and os.path.exists(py[:-10] + "pythonw.exe"):
        py = py[:-10] + "pythonw.exe"
    return [py, main_py, *args]


def supervise(make_cmd, max_crashes: int = MAX_CRASHES, window: float = CRASH_WINDOW,
              backoff: float = 0.5) -> int:
    """Запускает агента и перезапускает его после падений. Возвращает свой код выхода."""
    crashes: list[float] = []
    child: subprocess.Popen | None = None
    first = True

    def forward(signum, _frame):           # выход из системы / kill — гасим и агента
        if child and child.poll() is None:
            child.terminate()
        sys.exit(0)

    for sig in (signal.SIGTERM, getattr(signal, "SIGHUP", None), signal.SIGINT):
        if sig is not None:
            try:
                signal.signal(sig, forward)
            except (ValueError, OSError):
                pass

    while True:
        env = dict(os.environ, CONVWHEEL_SUPERVISED="1")
        if first:
            env["CONVWHEEL_FIRST_START"] = "1"
        child = subprocess.Popen(make_cmd(), env=env)
        first = False
        code = child.wait()
        if code == EXIT_QUIT:
            return 0
        if code == EXIT_RESTART:
            continue
        now = time.monotonic()
        crashes = [t for t in crashes if now - t < window] + [now]
        log(f"Агент завершился аварийно (код {code}). Перезапуск {len(crashes)}/{max_crashes}.")
        if len(crashes) >= max_crashes:
            log("Слишком много падений подряд — сторож останавливается. Подробности — в crash.log.")
            return 1
        time.sleep(backoff * len(crashes))


def main() -> int:
    install_crashlog("supervisor")
    if not acquire_single_instance():
        # Уже работает — просим показать окно настроек (значок может быть не виден)
        ipc.send("show")
        return 0
    return supervise(agent_command)


def parent_alive(pid: int) -> bool:
    """Жив ли сторож (агент закрывается вместе с ним)."""
    if pid <= 0:
        return True
    if IS_WIN:
        import ctypes
        k = ctypes.WinDLL("kernel32")
        k.OpenProcess.restype = ctypes.c_void_p
        h = k.OpenProcess(0x00100000, False, pid)           # SYNCHRONIZE
        if not h:
            return False
        try:
            return k.WaitForSingleObject(ctypes.c_void_p(h), 0) == 0x102   # WAIT_TIMEOUT = жив
        finally:
            k.CloseHandle(ctypes.c_void_p(h))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return os.getppid() == pid
