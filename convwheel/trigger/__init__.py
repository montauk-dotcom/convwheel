"""Глобальный перехват Shift+клика и определение файла под курсором.

  1. Системный перехват мыши (свой для каждой ОС, см. MouseHook в windows.py/macos.py) только
     складывает события в очередь — он должен отвечать системе мгновенно, иначе та его отключит.
  2. Отдельный поток разбирает очередь: любое нажатие — повод закрыть колесо, если клик мимо;
     отпускание нужной кнопки при зажатом Shift — через ~140 мс (Проводник/Finder успевают
     обновить выделение) спрашиваем у файлового менеджера, по чему кликнули.
  3. Если перехват умер или отключён системой — health_check() его поднимает заново.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Callable

from ..config import CONFIG
from ..platform_utils import IS_MAC, IS_WIN


class Trigger:
    def __init__(self, on_files: Callable[[list[str]], None], on_press: Callable[[], None]):
        self.on_files = on_files
        self.on_press = on_press
        self._events: queue.SimpleQueue = queue.SimpleQueue()
        self._busy = threading.Lock()
        self._stop = threading.Event()
        if IS_WIN:
            from . import windows as backend
        elif IS_MAC:
            from . import macos as backend
        else:
            from . import linux_stub as backend
        self.backend = backend
        self.hook = None
        self._worker = threading.Thread(target=self._process, name="cw-trigger", daemon=True)

    # ------------------------------------------------------------ жизненный цикл
    def start(self):
        self._worker.start()
        self._start_hook()

    def _start_hook(self):
        self.hook = self.backend.MouseHook(self._event)
        self.hook.start()

    def stop(self):
        self._stop.set()
        self._events.put(None)
        if self.hook:
            self.hook.stop()

    @property
    def status(self) -> str:
        """ok | no_permission | starting | error | unsupported"""
        return self.hook.status if self.hook else "starting"

    def health_check(self) -> None:
        """Вызывается по таймеру: если поток перехвата умер — запускаем новый."""
        if self._stop.is_set() or self.hook is None:
            return
        if not self.hook.is_alive() and self.hook.status != "unsupported":
            from ..crashlog import write
            write(f"Перехват мыши остановился (status={self.hook.status}) — перезапускаю")
            self._start_hook()
        if not self._worker.is_alive():
            self._worker = threading.Thread(target=self._process, name="cw-trigger", daemon=True)
            self._worker.start()

    # ------------------------------------------------------------ события
    def _event(self, button: str, pressed: bool, x: float, y: float, shift: bool | None):
        """Вызывается из системного перехвата — только кладём в очередь."""
        self._events.put((button, pressed, x, y, shift))

    def _process(self):
        while not self._stop.is_set():
            ev = self._events.get()
            if ev is None:
                return
            try:
                button, pressed, x, y, shift = ev
                if pressed:
                    self.on_press()
                    continue
                if not CONFIG.enabled or button != CONFIG.trigger_button:
                    continue
                if shift is None:
                    shift = self.backend.shift_down()
                if not shift or not self._busy.acquire(blocking=False):
                    continue
                threading.Thread(target=self._resolve, args=(x, y), daemon=True).start()
            except Exception:
                import traceback
                from ..crashlog import write
                write(traceback.format_exc())

    def _resolve(self, x, y):
        try:
            time.sleep(CONFIG.selection_delay_ms / 1000)
            paths = self.backend.files_under_click(x, y)
            if paths:
                self.on_files(paths)
        except Exception:
            import traceback
            from ..crashlog import write
            write(traceback.format_exc())
        finally:
            self._busy.release()
