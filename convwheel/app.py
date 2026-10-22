"""Основная часть ConvWheel: значок в строке меню / трее, меню, перехват мыши, колесо.

Запускается:
  • Windows/Linux — сторожем (supervisor.py) как процесс `--agent`;
  • macOS — прямо в процессе приложения (run_mac_main), а от падений страхует watchdog.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QCursor, QGuiApplication
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import APP_NAME, __version__, autostart, ipc, themes
from .config import CONFIG
from .crashlog import install as install_crashlog
from .crashlog import install_qt
from .crashlog import write as log
from .formats import targets_for_many
from .icons import app_icon, tray_icon, windows_taskbar_is_light
from .jobs import WheelManager
from .platform_utils import IS_MAC, IS_WIN, find_ffmpeg, find_soffice, has_ms_office

EXIT_RESTART = 75
_controller: "Controller | None" = None      # сильная ссылка: иначе сборщик мусора удалит значок
_reopen_handler = None

BUTTON_NAMES = {"left": "Shift + левая кнопка", "middle": "Shift + колёсико", "right": "Shift + правая кнопка"}


class Bridge(QObject):
    """Переносит события из фоновых потоков в главный (Qt) поток."""
    files = Signal(list)
    press = Signal()
    command = Signal(str)


class Controller(QObject):
    def __init__(self, app: QApplication, supervisor_pid: int = 0):
        super().__init__()
        self.app = app
        self.supervisor_pid = supervisor_pid
        self.settings = None
        self.perm = None
        self._in_dock = False
        self._light_taskbar = windows_taskbar_is_light()
        self.office_ok = bool(find_soffice()) or (IS_WIN and has_ms_office())

        self.manager = WheelManager(self)
        self.bridge = Bridge(self)
        self.bridge.files.connect(self.on_files)
        self.bridge.press.connect(self.manager.outside_click)
        self.bridge.command.connect(self.on_command)

        self.tray = QSystemTrayIcon(tray_icon(), self)
        self.tray.setToolTip(f"{APP_NAME} — Shift + клик по файлу")
        self.menu = self._build_menu()
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        from .trigger import Trigger
        self.trigger = Trigger(on_files=self.bridge.files.emit, on_press=self.bridge.press.emit)
        try:
            self.trigger.start()
        except Exception as e:
            log(f"Не удалось включить перехват мыши: {e}")

        self.ipc = ipc.Server(self.bridge.command.emit)
        self.ipc.start()

        self.health = QTimer(self)
        self.health.timeout.connect(self._health)
        self.health.start(3000)
        QTimer.singleShot(800, self._health)

        if IS_MAC:
            QTimer.singleShot(500, self._install_reopen_handler)
            from . import mac_permissions
            if not mac_permissions.all_required_ok():
                QTimer.singleShot(400, self.show_permissions)
        QTimer.singleShot(2500, self._prebuild_window)   # окно собираем заранее — откроется мгновенно
        if not CONFIG.extra.get("welcomed"):
            CONFIG.extra["welcomed"] = True
            CONFIG.save()
            QTimer.singleShot(600, lambda: self.show_settings(welcome=True))
        elif not self.office_ok and IS_WIN:
            QTimer.singleShot(1500, lambda: self.tray.showMessage(
                APP_NAME, "LibreOffice не найден — офисные форматы (DOCX→PDF и т.п.) работать не будут. "
                "Картинки, PDF, видео, аудио и архивы — работают.", QSystemTrayIcon.Warning, 8000))

    # ------------------------------------------------------------ меню значка
    def _build_menu(self) -> QMenu:
        """Короткое меню, как у AmneziaVPN: Показать / быстрые переключатели / Закрыть.
        Остальные настройки — в окне ConvWheel."""
        m = QMenu()
        m.addAction(f"Показать {APP_NAME}", self.show_settings)
        self.act_status = QAction("", m)
        self.act_status.setVisible(False)
        self.act_status.triggered.connect(self._fix_problem)
        m.addAction(self.act_status)
        m.addSeparator()

        self.act_enabled = QAction("Колесо включено", m, checkable=True, checked=CONFIG.enabled)
        self.act_enabled.toggled.connect(self._set_enabled)
        m.addAction(self.act_enabled)

        look = m.addMenu("Вид колеса")
        self.theme_group = QActionGroup(look)
        self.theme_actions: dict[str, QAction] = {}
        current = themes.normalize(CONFIG.theme)
        for key, t in themes.THEMES.items():
            a = QAction(t.name, look, checkable=True, checked=key == current)
            a.triggered.connect(lambda _=False, k=key: self.set_theme(k, preview=True))
            self.theme_group.addAction(a)
            look.addAction(a)
            self.theme_actions[key] = a
        look.addSeparator()
        look.addAction("Посмотреть вживую", lambda: self.demo(themes.normalize(CONFIG.theme)))

        if IS_WIN:
            eng = m.addMenu("Офисный движок")
            g2 = QActionGroup(eng)
            for key, label in (("auto", "Авто (MS Office, если есть)"), ("msoffice", "Microsoft Office"),
                               ("libreoffice", "LibreOffice")):
                a = QAction(label, eng, checkable=True, checked=CONFIG.office_engine == key)
                a.triggered.connect(lambda _=False, k=key: self._set_engine(k))
                g2.addAction(a)
                eng.addAction(a)
        m.addAction("Проверить компоненты", self._diagnostics)
        m.addSeparator()
        m.addAction(f"Закрыть {APP_NAME}", self.quit)
        return m

    def _fix_problem(self):
        if IS_MAC:
            self.show_permissions()
        else:
            self.show_settings()

    def _on_tray_activated(self, reason):
        # Windows: клик по значку открывает окно с видами (меню — правой кнопкой).
        # macOS: клик сам открывает меню.
        if not IS_MAC and reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_settings()

    # ------------------------------------------------------------ действия
    def on_files(self, paths: list):
        files = [Path(p) for p in paths]
        self.manager.show(files, targets_for_many(files))

    def on_command(self, cmd: str):
        if cmd == "show":
            self.show_settings()

    def set_theme(self, key: str, preview: bool = False):
        CONFIG.theme = themes.normalize(key)
        CONFIG.save()
        a = self.theme_actions.get(CONFIG.theme)
        if a and not a.isChecked():
            a.setChecked(True)
        if self.settings:
            self.settings.sync()
        if preview:
            self.demo(CONFIG.theme)

    def demo(self, key: str | None = None):
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        pos = QCursor.pos() if self.settings and self.settings.isVisible() else screen.availableGeometry().center()
        self.manager.show_demo(theme=key, pos=pos)

    def _set_enabled(self, on: bool):
        CONFIG.enabled = on
        CONFIG.save()
        if self.settings:
            self.settings.sync()

    def _set_engine(self, key: str):
        CONFIG.office_engine = key
        CONFIG.save()

    def _sync_menu(self):
        self.act_enabled.blockSignals(True)
        self.act_enabled.setChecked(CONFIG.enabled)
        self.act_enabled.blockSignals(False)

    # ------------------------------------------------------------ окна
    def _prebuild_window(self):
        if self.settings is None:
            self._build_window(welcome=False)

    def _build_window(self, welcome: bool):
        from .settings_window import SettingsWindow
        self.settings = SettingsWindow(welcome=welcome)
        self.settings.theme_changed.connect(lambda k: self.set_theme(k))
        self.settings.demo_requested.connect(self.demo)
        self.settings.permissions_requested.connect(self.show_permissions)
        self.settings.settings_changed.connect(self._sync_menu)
        self.settings.visibility_changed.connect(self._schedule_dock_update)

    def show_settings(self, welcome: bool = False):
        if self.settings is None:
            self._build_window(welcome)
        self._health()
        self.settings.sync()
        self._present(self.settings)

    def show_permissions(self):
        if not IS_MAC:
            return
        from .mac_permissions import PermissionsWindow
        if self.perm is None:
            self.perm = PermissionsWindow(hook_ok=lambda: self.trigger.status == "ok")
            self.perm.installEventFilter(self)
        self._present(self.perm)

    def _present(self, w):
        """Показать окно поверх остальных. На macOS сначала появляемся в Доке (как обычная программа)."""
        self._set_dock(True)
        w.show()
        w.raise_()
        w.activateWindow()
        _activate(w)

    def eventFilter(self, obj, ev):
        if ev.type() in (ev.Type.Show, ev.Type.Hide):
            self._schedule_dock_update()
        return False

    def _schedule_dock_update(self):
        QTimer.singleShot(0, self._update_dock)

    def _update_dock(self):
        visible = any(w is not None and w.isVisible() for w in (self.settings, self.perm))
        self._set_dock(visible)

    def _set_dock(self, show: bool):
        """macOS: значок в Доке только пока открыто окно; закрыли крестиком — остаётся лишь строка меню."""
        if not IS_MAC or show == self._in_dock:
            return
        self._in_dock = show
        try:
            from AppKit import NSApplication
            nsapp = NSApplication.sharedApplication()
            nsapp.setActivationPolicy_(0 if show else 1)       # 0 — обычное приложение, 1 — только меню
            if show:
                nsapp.activateIgnoringOtherApps_(True)
        except Exception as e:
            log(f"Не удалось переключить значок в Доке: {e}")

    def _diagnostics(self):
        def mark(ok):
            return "✅" if ok else "❌"
        lines = [
            f"{mark(find_soffice())} LibreOffice: {find_soffice() or 'не найден'}",
            f"{mark(find_ffmpeg())} ffmpeg: {'есть' if find_ffmpeg() else 'не найден'}",
            f"{mark(self.trigger.status == 'ok')} Перехват мыши: {self.trigger.status}",
        ]
        if IS_WIN:
            lines.append(f"{mark(has_ms_office('Word'))} Microsoft Word")
        for mod, label in (("pymupdf", "PyMuPDF (PDF)"), ("pdf2docx", "pdf2docx (PDF→DOCX)"),
                           ("docx", "python-docx"), ("PIL", "Pillow (картинки)"), ("py7zr", "py7zr (7Z)"),
                           ("pillow_heif", "pillow-heif (HEIC, необязательно)")):
            try:
                __import__(mod)
                ok = True
            except Exception:
                ok = False
            lines.append(f"{mark(ok)} {label}")
        QMessageBox.information(None, APP_NAME, "\n".join(lines))

    # ------------------------------------------------------------ здоровье
    def _health(self):
        self.trigger.health_check()
        st = self.trigger.status
        problem = ""
        if st == "no_permission":
            problem = "⚠️ Нет доступа к мыши — выдать…"
        elif st == "error":
            problem = "⚠️ Перехват мыши не работает"
        self.act_status.setText(problem)
        self.act_status.setVisible(bool(problem))
        if self.settings is not None:
            warning = ""
            if st == "no_permission":
                warning = "Нет доступа к мыши — нажмите «Разрешения macOS…» ниже."
            elif st == "error":
                warning = "Не удалось включить перехват мыши — перезапустите ConvWheel."
            elif not self.office_ok:
                warning = "LibreOffice не найден — офисные форматы (DOCX → PDF и т.п.) недоступны."
            if not CONFIG.enabled:
                text = "Колесо выключено."
            else:
                text = f"Работает в фоне • {BUTTON_NAMES[CONFIG.trigger_button]} по файлу или папке"
            self.settings.set_status(text, warning)
        if IS_WIN:                                   # тема панели задач сменилась — перекрашиваем значок
            light = windows_taskbar_is_light()
            if light != self._light_taskbar:
                self._light_taskbar = light
                self.tray.setIcon(tray_icon())
        if self.supervisor_pid:
            from .supervisor import parent_alive
            if not parent_alive(self.supervisor_pid):
                log("Сторож завершился — выходим вместе с ним.")
                self._shutdown()
                self.app.exit(0)

    def _install_reopen_handler(self):
        """macOS: «Открыть ConvWheel» ещё раз (Finder, Launchpad, Spotlight) → окно настроек."""
        global _reopen_handler
        if _reopen_handler is not None:
            return
        try:
            import objc
            from Foundation import NSAppleEventManager, NSObject
            bridge = self.bridge

            class ConvWheelReopenHandler(NSObject):
                @objc.typedSelector(b"v@:@@")
                def handleReopen_withReply_(self, _event, _reply):
                    bridge.command.emit("show")

            _reopen_handler = ConvWheelReopenHandler.alloc().init()
            NSAppleEventManager.sharedAppleEventManager() \
                .setEventHandler_andSelector_forEventClass_andEventID_(
                    _reopen_handler, b"handleReopen:withReply:", 0x61657674, 0x72617070)  # 'aevt' 'rapp'
        except Exception as e:
            log(f"Не удалось подключить обработчик повторного открытия: {e}")

    # ------------------------------------------------------------ выход
    def _shutdown(self):
        try:
            self.health.stop()
            self.trigger.stop()
            self.ipc.close()
            self.manager.shutdown()
            self.tray.hide()
        except Exception:
            pass

    def on_about_to_quit(self):
        if IS_MAC:
            from .watchdog import set_exit_reason
            set_exit_reason("quit")
        self._shutdown()

    def quit(self):
        if IS_MAC:
            from .watchdog import set_exit_reason
            set_exit_reason("quit")
        self._shutdown()
        self.app.exit(0)

    def restart(self):
        if IS_MAC:
            from .watchdog import set_exit_reason
            set_exit_reason("restart")
        self._shutdown()
        self.app.exit(EXIT_RESTART)


def request_restart():
    if _controller is not None:
        _controller.restart()


# ================================================================ запуск
def _make_app(argv: list[str]) -> QApplication:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())
    install_qt()
    if IS_MAC:  # без значка в Dock — только в строке меню
        try:
            from AppKit import NSApplication
            NSApplication.sharedApplication().setActivationPolicy_(1)  # Accessory
        except Exception:
            pass
    return app


def _activate(w):
    try:
        if IS_MAC:
            from AppKit import NSApplication
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        elif IS_WIN:
            from .wheel import _force_foreground
            _force_foreground(w)
    except Exception:
        pass


def _arg_int(argv: list[str], name: str) -> int:
    try:
        return int(argv[argv.index(name) + 1])
    except (ValueError, IndexError):
        return 0


def run(argv: list[str]) -> int:
    """--agent (под сторожем), --file путь… (отладка), --demo (пример колеса)."""
    global _controller
    install_crashlog("agent" if "--agent" in argv else "debug")
    app = _make_app(argv)

    if "--file" in argv or "--demo" in argv:
        mgr = WheelManager()
        if "--file" in argv:
            files = [Path(a) for a in argv[argv.index("--file") + 1:] if not a.startswith("--")]
            if not mgr.show(files, targets_for_many(files)):
                print("Неподдерживаемый формат")
                return 1
        else:
            mgr.show_demo()
        mgr.wheel.closed.connect(lambda *_: QTimer.singleShot(50, app.quit))
        return app.exec()

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, APP_NAME, "Системный трей недоступен")
        return 1
    _controller = Controller(app, supervisor_pid=_arg_int(argv, "--supervisor-pid"))
    app._cw_controller = _controller
    return app.exec()


def run_mac_main(argv: list[str]) -> int:
    """macOS: процесс приложения сам является агентом; от падений страхует watchdog."""
    global _controller
    from .supervisor import acquire_single_instance
    from .watchdog import set_exit_reason, spawn_for
    install_crashlog("app")
    if not acquire_single_instance():
        ipc.send("show")                   # уже работает — показываем окно настроек
        return 0
    spawn_for(os.getpid())
    app = _make_app(argv)
    _controller = Controller(app)
    app._cw_controller = _controller
    app.aboutToQuit.connect(_controller.on_about_to_quit)
    code = app.exec()
    set_exit_reason("restart" if code == EXIT_RESTART else "quit")
    return 0
