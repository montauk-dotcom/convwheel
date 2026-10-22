"""macOS: выделенные файлы в Finder (включая рабочий стол — это тоже Finder).

Требуются разрешения (система спросит при первом запуске):
  • Универсальный доступ (Accessibility) и Мониторинг ввода — для глобального клика;
  • Автоматизация → Finder — чтобы спросить у Finder выделение.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time


class MouseHook(threading.Thread):
    """Слушающий (ничего не блокирующий) перехват кнопок мыши через Quartz event tap.

    macOS отключает перехват, если программа хоть раз ответила медленно, — тогда приходит
    событие kCGEventTapDisabledByTimeout. Мы сразу включаем его обратно и дополнительно
    раз в секунду проверяем CGEventTapIsEnabled. Если доступа нет (не выданы разрешения),
    пробуем снова каждые 3 секунды — после выдачи разрешения всё заработает само.
    """

    def __init__(self, callback):
        super().__init__(name="cw-mousehook", daemon=True)
        self.cb = callback
        self.status = "starting"
        self.reenabled = 0
        self._stop = threading.Event()
        self._tap = None
        self._loop = None

    def stop(self):
        self._stop.set()
        try:
            import Quartz
            if self._loop is not None:
                Quartz.CFRunLoopStop(self._loop)
        except Exception:
            pass

    def run(self):
        import Quartz as Q
        mask = 0
        for t in (Q.kCGEventLeftMouseDown, Q.kCGEventLeftMouseUp, Q.kCGEventRightMouseDown,
                  Q.kCGEventRightMouseUp, Q.kCGEventOtherMouseDown, Q.kCGEventOtherMouseUp):
            mask |= Q.CGEventMaskBit(t)
        self._types = {
            Q.kCGEventLeftMouseDown: ("left", True), Q.kCGEventLeftMouseUp: ("left", False),
            Q.kCGEventRightMouseDown: ("right", True), Q.kCGEventRightMouseUp: ("right", False),
            Q.kCGEventOtherMouseDown: ("other", True), Q.kCGEventOtherMouseUp: ("other", False),
        }
        while not self._stop.is_set():
            tap = Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap,
                                     Q.kCGEventTapOptionListenOnly, mask, self._handler, None)
            if not tap:
                self.status = "no_permission"
                self._stop.wait(3)
                continue
            self._tap = tap
            src = Q.CFMachPortCreateRunLoopSource(None, tap, 0)
            self._loop = Q.CFRunLoopGetCurrent()
            Q.CFRunLoopAddSource(self._loop, src, Q.kCFRunLoopCommonModes)
            Q.CGEventTapEnable(tap, True)
            self.status = "ok"
            while not self._stop.is_set():
                Q.CFRunLoopRunInMode(Q.kCFRunLoopDefaultMode, 1.0, False)
                if not Q.CGEventTapIsEnabled(tap):
                    Q.CGEventTapEnable(tap, True)
                    self.reenabled += 1
                    if not Q.CGEventTapIsEnabled(tap):    # не включается — пересоздаём
                        break
            Q.CFRunLoopRemoveSource(self._loop, src, Q.kCFRunLoopCommonModes)
            Q.CFMachPortInvalidate(tap)
            self._tap = None
            time.sleep(0.2)

    def _handler(self, proxy, etype, event, refcon):
        try:
            import Quartz as Q
            if etype in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
                if self._tap is not None:
                    Q.CGEventTapEnable(self._tap, True)
                    self.reenabled += 1
                return event
            kind = self._types.get(etype)
            if kind is None:
                return event
            button, pressed = kind
            if button == "other":
                num = Q.CGEventGetIntegerValueField(event, Q.kCGMouseEventButtonNumber)
                if num != 2:
                    return event
                button = "middle"
            shift = bool(Q.CGEventGetFlags(event) & Q.kCGEventFlagMaskShift)
            loc = Q.CGEventGetLocation(event)
            self.cb(button, pressed, loc.x, loc.y, shift)
        except Exception:
            pass
        return event

SCRIPT = '''
tell application "Finder"
    set out to ""
    repeat with i in (get selection)
        try
            set out to out & POSIX path of (i as alias) & linefeed
        end try
    end repeat
    return out
end tell
'''


def shift_down() -> bool:
    try:
        import Quartz
        flags = Quartz.CGEventSourceFlagsState(Quartz.kCGEventSourceStateCombinedSessionState)
        return bool(flags & Quartz.kCGEventFlagMaskShift)
    except Exception:
        return False


def _finder_frontmost() -> bool:
    try:
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return app is not None and app.bundleIdentifier() == "com.apple.finder"
    except Exception:
        r = subprocess.run(["osascript", "-e",
                            'tell application "System Events" to get bundle identifier of first process whose frontmost is true'],
                           capture_output=True, text=True, timeout=3)
        return r.stdout.strip() == "com.apple.finder"


def files_under_click(x, y) -> list[str]:
    if not _finder_frontmost():
        return []
    r = subprocess.run(["osascript", "-e", SCRIPT], capture_output=True, text=True, timeout=5)
    paths = [p.rstrip("/") or "/" for p in r.stdout.splitlines() if p]
    # файлы и папки (кроме корня и дисков в /Volumes)
    return [p for p in paths
            if os.path.isfile(p) or (os.path.isdir(p) and p != "/" and os.path.dirname(p) != "/Volumes")]
