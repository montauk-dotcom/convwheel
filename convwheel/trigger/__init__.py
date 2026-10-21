"""Глобальный перехват Shift+клика и определение файла под курсором.

Общая схема одинакова для обеих систем:
  1. pynput слушает мышь во всей системе (ничего не блокирует, клики проходят дальше).
  2. Отпускание нужной кнопки при зажатом Shift → через ~140 мс (чтобы Проводник/Finder
     успели обновить выделение) в отдельном потоке спрашиваем у файлового менеджера,
     по какому файлу кликнули.
  3. Если это поддерживаемый файл — отдаём список путей в Qt-поток через сигнал.
"""
from __future__ import annotations

import threading
import time
from typing import Callable

from ..config import CONFIG
from ..platform_utils import IS_MAC, IS_WIN


class Trigger:
    def __init__(self, on_files: Callable[[list[str]], None], on_any_click: Callable[[], None]):
        self.on_files = on_files
        self.on_any_click = on_any_click
        self._listener = None
        self._busy = threading.Lock()
        if IS_WIN:
            from . import windows as backend
        elif IS_MAC:
            from . import macos as backend
        else:
            from . import linux_stub as backend
        self.backend = backend

    def start(self):
        from pynput import mouse
        self._mouse = mouse
        self._listener = mouse.Listener(on_click=self._on_click)
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()

    def _button(self):
        m = self._mouse.Button
        return {"left": m.left, "middle": m.middle, "right": m.right}.get(CONFIG.trigger_button, m.left)

    def _on_click(self, x, y, button, pressed):
        # Любое нажатие мыши — колесо само решит, закрыться ли (клик мимо него)
        if pressed:
            self.on_any_click()
            return
        if not CONFIG.enabled or button != self._button():
            return
        if not self.backend.shift_down():
            return
        if not self._busy.acquire(blocking=False):
            return  # предыдущий запрос ещё обрабатывается
        x, y = self.backend.cursor_pos(x, y)   # координаты фиксируем в момент клика
        threading.Thread(target=self._resolve, args=(x, y), daemon=True).start()

    def _resolve(self, x, y):
        try:
            time.sleep(CONFIG.selection_delay_ms / 1000)
            paths = self.backend.files_under_click(x, y)
            if paths:
                self.on_files(paths)
        except Exception:
            import traceback
            from ..engine import _log
            _log(traceback.format_exc())
        finally:
            self._busy.release()
