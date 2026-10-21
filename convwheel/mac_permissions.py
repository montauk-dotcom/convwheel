"""macOS: окно первого запуска, которое проводит через системные разрешения.

Apple требует их от любой программы, которая видит клики во всей системе, поэтому
обойти их нельзя — но можно сделать так, чтобы человеку не пришлось ничего искать:
кнопки сразу открывают нужный раздел настроек, статус обновляется сам, а когда всё
выдано — приложение само перезапускается.
"""
from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget)

from .config import CONFIG
from .platform_utils import IS_MAC

PANE = "x-apple.systempreferences:com.apple.preference.security?"
URL_ACCESSIBILITY = PANE + "Privacy_Accessibility"
URL_INPUT = PANE + "Privacy_ListenEvent"
URL_AUTOMATION = PANE + "Privacy_Automation"


# ------------------------------------------------------------------ проверки
def accessibility_ok() -> bool:
    if not IS_MAC:
        return False
    try:
        from ApplicationServices import AXIsProcessTrusted
        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def input_monitoring_ok() -> bool:
    if not IS_MAC:
        return False
    try:
        import Quartz
        return bool(Quartz.CGPreflightListenEventAccess())
    except Exception:
        return True   # старые macOS (до 10.15) — такого разрешения нет


def finder_ok() -> bool:
    return bool(CONFIG.extra.get("finder_ok"))


def all_required_ok() -> bool:
    return accessibility_ok() and input_monitoring_ok()


def request_accessibility():
    """Системный запрос + сразу добавляет ConvWheel в список «Универсальный доступ»."""
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
        AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
    except Exception:
        pass
    open_url(URL_ACCESSIBILITY)


def request_input_monitoring():
    try:
        import Quartz
        Quartz.CGRequestListenEventAccess()   # добавляет приложение в список
    except Exception:
        pass
    open_url(URL_INPUT)


def request_finder() -> bool:
    """Безобидный запрос к Finder вызывает системное окно «Разрешить управлять Finder»."""
    try:
        r = subprocess.run(["osascript", "-e", 'tell application "Finder" to get name of startup disk'],
                           capture_output=True, text=True, timeout=60)
        ok = r.returncode == 0
    except Exception:
        ok = False
    if not ok:
        open_url(URL_AUTOMATION)
    CONFIG.extra["finder_ok"] = ok
    CONFIG.save()
    return ok


def open_url(url: str):
    try:
        subprocess.Popen(["open", url])
    except Exception:
        pass


def relaunch():
    """Перезапуск: разрешения на перехват ввода применяются только к новому процессу."""
    if getattr(sys, "frozen", False):
        exe = sys.executable
        app = exe[: exe.index(".app/") + 4] if ".app/" in exe else exe
        cmd = f'sleep 1; open -n "{app}"'
    else:
        args = " ".join(f'"{a}"' for a in [sys.executable, *sys.argv])
        cmd = f"sleep 1; {args} &"
    subprocess.Popen(["/bin/sh", "-c", cmd], start_new_session=True)
    os._exit(0)


# ------------------------------------------------------------------ окно
STYLE = """
QWidget#root { background: #12161F; }
QLabel { color: #E8EEF7; }
QLabel#title { font-size: 22px; font-weight: 700; }
QLabel#subtitle { color: #9AA6B8; font-size: 13px; }
QFrame.row { background: #1A202B; border: 1px solid #263042; border-radius: 12px; }
QFrame.row[done="true"] { border-color: #2F6F55; background: #162420; }
QLabel.badge { border-radius: 14px; min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px;
               font-weight: 700; font-size: 14px; qproperty-alignment: AlignCenter;
               background: #263042; color: #C9D3E2; }
QLabel.badge[done="true"] { background: #34D399; color: #0B1A13; }
QLabel.rowtitle { font-size: 14px; font-weight: 600; }
QLabel.rowdesc { color: #8E9AAD; font-size: 12px; }
QPushButton { background: #2A3446; color: #E8EEF7; border: none; border-radius: 8px;
              padding: 7px 14px; font-size: 13px; }
QPushButton:hover { background: #34405A; }
QPushButton#primary { background: #2F80ED; font-weight: 600; padding: 10px 18px; }
QPushButton#primary:hover { background: #3B8CFA; }
QPushButton#primary:disabled { background: #233047; color: #6F7C92; }
QPushButton#link { background: transparent; color: #7FB3FF; padding: 4px; }
"""


class _Row(QFrame):
    def __init__(self, num: int, title: str, desc: str, button: str, on_click):
        super().__init__()
        self.setProperty("class", "row")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(12)
        self.badge = QLabel(str(num))
        self.badge.setProperty("class", "badge")
        self.num = num
        lay.addWidget(self.badge, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title)
        t.setProperty("class", "rowtitle")
        d = QLabel(desc)
        d.setProperty("class", "rowdesc")
        d.setWordWrap(True)
        col.addWidget(t)
        col.addWidget(d)
        lay.addLayout(col, 1)
        self.btn = QPushButton(button)
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.clicked.connect(on_click)
        lay.addWidget(self.btn, 0, Qt.AlignVCenter)

    def set_done(self, done: bool):
        for w in (self, self.badge):
            if w.property("done") != done:
                w.setProperty("done", done)
                w.style().unpolish(w)
                w.style().polish(w)
        self.badge.setText("✓" if done else str(self.num))
        self.btn.setVisible(not done)


class PermissionsWindow(QWidget):
    finished = Signal()

    def __init__(self, checker=None):
        super().__init__()
        # checker позволяет подменить проверки (для предпросмотра/тестов)
        self.check = checker or (lambda: (accessibility_ok(), input_monitoring_ok(), finder_ok()))
        self.setObjectName("root")
        self.setWindowTitle("ConvWheel — настройка")
        self.setStyleSheet(STYLE)
        self.setFixedWidth(560)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 24, 26, 22)
        lay.setSpacing(10)
        title = QLabel("Почти готово")
        title.setObjectName("title")
        sub = QLabel("Чтобы колесо появлялось по Shift + клику в Finder, macOS нужно "
                     "три разрешения. В каждом разделе просто включите переключатель "
                     "у ConvWheel — эта страница обновится сама.")
        sub.setObjectName("subtitle")
        sub.setWordWrap(True)
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addSpacing(6)

        self.rows = [
            _Row(1, "Универсальный доступ", "Чтобы открывать колесо поверх Finder.",
                 "Открыть настройки", request_accessibility),
            _Row(2, "Мониторинг ввода", "Чтобы замечать Shift + клик по файлу.",
                 "Открыть настройки", request_input_monitoring),
            _Row(3, "Доступ к Finder", "Чтобы узнать, по какому файлу вы кликнули. "
                 "Нажмите и выберите «Разрешить».", "Разрешить", self._finder),
        ]
        for r in self.rows:
            lay.addWidget(r)

        lay.addSpacing(8)
        bottom = QHBoxLayout()
        self.hint = QLabel("")
        self.hint.setObjectName("subtitle")
        self.hint.setWordWrap(True)
        bottom.addWidget(self.hint, 1)
        self.go = QPushButton("Запустить ConvWheel")
        self.go.setObjectName("primary")
        self.go.setCursor(Qt.PointingHandCursor)
        self.go.clicked.connect(relaunch)
        bottom.addWidget(self.go)
        lay.addLayout(bottom)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.refresh()

    def _finder(self):
        # запрос ждёт ответа пользователя в системном окне — не блокируем интерфейс
        import threading
        btn = self.rows[2].btn
        btn.setText("Ждём ответа…")
        btn.setEnabled(False)

        def work():
            request_finder()
            QTimer.singleShot(0, self, lambda: (btn.setText("Разрешить"), btn.setEnabled(True)))
        threading.Thread(target=work, daemon=True).start()

    def refresh(self):
        acc, inp, fnd = self.check()
        for row, ok in zip(self.rows, (acc, inp, fnd)):
            row.set_done(ok)
        ready = acc and inp
        self.go.setEnabled(ready)
        if not ready:
            self.hint.setText("Не нашли ConvWheel в списке? Нажмите «+» внизу списка и выберите "
                              "его в папке «Программы».")
        elif not fnd:
            self.hint.setText("Основное готово. Доступ к Finder можно выдать и позже — "
                              "macOS спросит при первом Shift + клике.")
        else:
            self.hint.setText("Всё готово! Перезапускаем…")
            if self.timer.isActive():
                self.timer.stop()
                QTimer.singleShot(1200, relaunch)
