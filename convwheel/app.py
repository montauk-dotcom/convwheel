"""Фоновое приложение: значок в трее/строке меню, триггер и показ колеса."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QCursor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import APP_NAME, __version__, autostart
from .config import CONFIG
from .formats import targets_for_many
from .platform_utils import IS_MAC, IS_WIN, find_ffmpeg, find_soffice, has_ms_office
from .wheel import ConvertWheel


class Bridge(QObject):
    """Переносит события из потоков pynput в главный (Qt) поток."""
    files = Signal(list)
    click = Signal()


def make_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    colors = ["#FF5A5F", "#4C8DFF", "#3DDC97", "#FFB547"]
    for i, c in enumerate(colors):
        pen = QPen(QColor(c), 9)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(QRectF(8, 8, 48, 48), int((90 - i * 90 + 6) * 16), int(-78 * 16))
    p.setBrush(QColor("#E8EEF7"))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QPointF(32, 32), 9, 9)
    p.end()
    return QIcon(pm)


class ConvWheelApp(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.wheel: ConvertWheel | None = None
        self.bridge = Bridge()
        self.bridge.files.connect(self.show_wheel)
        self.bridge.click.connect(self._outside_click)

        self.tray = QSystemTrayIcon(make_icon(), self)
        self.tray.setToolTip(f"{APP_NAME} — Shift+клик по файлу")
        self.tray.setContextMenu(self._build_menu())
        self.tray.show()

        from .trigger import Trigger
        self.trigger = Trigger(on_files=self.bridge.files.emit, on_any_click=self.bridge.click.emit)
        try:
            self.trigger.start()
        except Exception as e:
            QMessageBox.warning(None, APP_NAME, f"Не удалось включить перехват мыши:\n{e}")

        if not find_soffice() and not (IS_WIN and has_ms_office()):
            QTimer.singleShot(1500, lambda: self.tray.showMessage(
                APP_NAME, "LibreOffice не найден — офисные форматы (DOCX→PDF и т.п.) работать не будут. "
                "Картинки, PDF, видео и аудио — работают.", QSystemTrayIcon.Warning, 8000))

    # ------------------------------------------------------------ меню трея
    def _build_menu(self) -> QMenu:
        m = QMenu()
        title = QAction(f"{APP_NAME} {__version__}", m)
        title.setEnabled(False)
        m.addAction(title)
        m.addSeparator()

        self.act_enabled = QAction("Включено", m, checkable=True, checked=CONFIG.enabled)
        self.act_enabled.toggled.connect(self._set_enabled)
        m.addAction(self.act_enabled)

        sub = m.addMenu("Кнопка вызова")
        grp = QActionGroup(sub)
        for key, label in (("left", "Shift + левая кнопка"), ("middle", "Shift + колёсико"),
                           ("right", "Shift + правая кнопка")):
            a = QAction(label, sub, checkable=True, checked=CONFIG.trigger_button == key)
            a.triggered.connect(lambda _=False, k=key: self._set_button(k))
            grp.addAction(a)
            sub.addAction(a)

        look = m.addMenu("Оформление")
        g3 = QActionGroup(look)
        for key, label in (("citrus", "Цитрус (серый)"), ("classic", "Классика (цветной)")):
            a = QAction(label, look, checkable=True, checked=CONFIG.theme == key)
            a.triggered.connect(lambda _=False, k=key: self._set_theme(k))
            g3.addAction(a)
            look.addAction(a)

        if IS_WIN:
            eng = m.addMenu("Офисный движок")
            g2 = QActionGroup(eng)
            for key, label in (("auto", "Авто (MS Office, если есть)"), ("msoffice", "Microsoft Office"),
                               ("libreoffice", "LibreOffice")):
                a = QAction(label, eng, checkable=True, checked=CONFIG.office_engine == key)
                a.triggered.connect(lambda _=False, k=key: self._set_engine(k))
                g2.addAction(a)
                eng.addAction(a)

        if IS_WIN or IS_MAC:
            self.act_auto = QAction("Запускать при входе", m, checkable=True, checked=autostart.is_enabled())
            self.act_auto.toggled.connect(autostart.set_enabled)
            m.addAction(self.act_auto)

        if IS_MAC:
            m.addAction("Разрешения macOS…", self._show_permissions)
        m.addAction("Проверить компоненты", self._diagnostics)
        m.addSeparator()
        m.addAction("Выход", self.quit)
        return m

    def _set_enabled(self, on: bool):
        CONFIG.enabled = on
        CONFIG.save()

    def _set_button(self, key: str):
        CONFIG.trigger_button = key
        CONFIG.save()

    def _set_theme(self, key: str):
        CONFIG.theme = key
        CONFIG.save()

    def _set_engine(self, key: str):
        CONFIG.office_engine = key
        CONFIG.save()

    def _show_permissions(self):
        from .mac_permissions import PermissionsWindow
        self._perm_win = PermissionsWindow()
        self._perm_win.show()
        self._perm_win.raise_()
        _activate_mac()

    def _diagnostics(self):
        def mark(ok):
            return "✅" if ok else "❌"
        lines = [
            f"{mark(find_soffice())} LibreOffice: {find_soffice() or 'не найден'}",
            f"{mark(find_ffmpeg())} ffmpeg: {find_ffmpeg() or 'не найден'}",
        ]
        if IS_WIN:
            lines.append(f"{mark(has_ms_office('Word'))} Microsoft Word")
        for mod, label in (("pymupdf", "PyMuPDF (PDF)"), ("pdf2docx", "pdf2docx (PDF→DOCX)"),
                           ("docx", "python-docx"), ("PIL", "Pillow (картинки)"),
                           ("pillow_heif", "pillow-heif (HEIC, необязательно)")):
            try:
                __import__(mod)
                ok = True
            except Exception:
                ok = False
            lines.append(f"{mark(ok)} {label}")
        QMessageBox.information(None, APP_NAME, "\n".join(lines))

    # ------------------------------------------------------------ колесо
    def show_wheel(self, paths: list):
        if self.wheel is not None:
            if self.wheel.state == ConvertWheel.WORKING:
                return
            self.wheel.close()
        files = [Path(p) for p in paths]
        targets = targets_for_many(files)
        if not targets:
            return  # неподдерживаемый тип — молча ничего не делаем
        self.wheel = ConvertWheel(files, targets)
        self.wheel.closed.connect(self._wheel_closed)
        self.wheel.popup_at(QCursor.pos())

    def _wheel_closed(self):
        self.wheel = None

    def _outside_click(self):
        w = self.wheel
        if w is not None and w.isVisible() and w.state != ConvertWheel.WORKING:
            if not w.contains_global(QCursor.pos()):
                w.dismiss()

    def quit(self):
        self.trigger.stop()
        self.tray.hide()
        self.app.quit()


def run(argv: list[str]) -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(make_icon())

    if IS_MAC:  # без значка в Dock — только в строке меню
        try:
            from AppKit import NSApplication
            NSApplication.sharedApplication().setActivationPolicy_(1)  # Accessory
        except Exception:
            pass

    # Ручной режим / отладка:  main.py --file путь [путь ...]
    if "--file" in argv:
        files = [Path(a) for a in argv[argv.index("--file") + 1:]]
        targets = targets_for_many(files)
        if not targets:
            print("Неподдерживаемый формат")
            return 1
        w = ConvertWheel(files, targets)
        w.closed.connect(app.quit)
        w.popup_at()
        return app.exec()

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, APP_NAME, "Системный трей недоступен")
        return 1
    _single_instance_or_exit()
    if IS_MAC:
        from . import mac_permissions
        if not mac_permissions.all_required_ok():
            # Сначала проводим через разрешения; окно само перезапустит приложение
            win = mac_permissions.PermissionsWindow()
            win.show()
            win.raise_()
            _activate_mac()
            return app.exec()
    ConvWheelApp(app)
    return app.exec()


def _activate_mac():
    try:
        from AppKit import NSApplication
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception:
        pass


_lock = None


def _single_instance_or_exit():
    """Не даём запустить вторую копию (иначе два колеса на один клик)."""
    global _lock
    from PySide6.QtCore import QLockFile
    from .platform_utils import config_dir
    _lock = QLockFile(str(config_dir() / "instance.lock"))
    _lock.setStaleLockTime(0)
    if not _lock.tryLock(100):
        sys.exit(0)
