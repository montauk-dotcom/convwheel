"""Самопроверка собранного приложения: `ConvWheel --selftest`.

Запускается в CI после сборки: если в .app не попала какая-то библиотека или ffmpeg,
сборка упадёт сразу, а не у пользователя.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path


def _report(text: str) -> None:
    """В оконной сборке Windows нет консоли (sys.stdout = None) — пишем ещё и в файл."""
    import os
    log = os.environ.get("CONVWHEEL_SELFTEST_LOG")
    if log:
        with open(log, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    if sys.stdout is not None:
        try:
            print(text)
        except Exception:
            pass


def main() -> int:
    errors = []
    for mod in ("PySide6.QtWidgets", "pymupdf", "pdf2docx", "docx", "openpyxl",
                "PIL.Image", "markdown", "py7zr", "convwheel.app", "convwheel.settings_window",
                "convwheel.trigger"):
        try:
            __import__(mod)
        except Exception as e:
            errors.append(f"import {mod}: {e}")
    platform_mods = {"darwin": ("AppKit", "Quartz", "ApplicationServices", "Foundation", "objc",
                                "convwheel.trigger.macos", "convwheel.mac_permissions"),
                     "win32": ("win32com.client", "pythoncom", "comtypes.client",
                               "comtypes.gen.UIAutomationClient", "convwheel.trigger.windows")
                     }.get(sys.platform, ())
    if platform_mods:
        for mod in platform_mods:
            try:
                __import__(mod)
            except Exception as e:
                errors.append(f"import {mod}: {e}")

    from .platform_utils import find_ffmpeg
    if not find_ffmpeg():
        errors.append("ffmpeg не найден в сборке")

    # реальные мини-конвертации: картинка → JPG и PDF, PDF → TXT, TXT → DOCX
    try:
        from PIL import Image
        from .engine import run_job
        from .formats import targets_for
        with tempfile.TemporaryDirectory() as d:
            png = Path(d) / "t.png"
            Image.new("RGBA", (40, 30), (0, 128, 255, 128)).save(png)
            pick = {t.key: t for t in targets_for(png)}
            run_job([png], pick["jpg"])
            pdf = run_job([png], pick["pdf"])[0]
            txt = Path(d) / "t.txt"
            txt.write_text("Привет, проверка", encoding="utf-8")
            run_job([txt], {t.key: t for t in targets_for(txt)}["docx"])
            import pymupdf
            assert pymupdf.open(pdf).page_count == 1
            # папка → 7Z → распаковка
            folder = Path(d) / "папка"
            folder.mkdir()
            (folder / "a.txt").write_text("x", encoding="utf-8")
            arch = run_job([folder], {t.key: t for t in targets_for(folder)}["7z"])[0]
            back = run_job([arch], {t.key: t for t in targets_for(arch)}["extract"])[0]
            assert (back / "a.txt").exists()
    except Exception as e:
        errors.append(f"конвертация: {e}")

    # перехват мыши: нужные функции ОС на месте
    try:
        if sys.platform == "darwin":
            import Quartz as Q
            for name in ("CGEventTapCreate", "CGEventTapEnable", "CGEventTapIsEnabled", "CGEventMaskBit",
                         "CFMachPortCreateRunLoopSource", "CFRunLoopRunInMode", "kCGEventTapDisabledByTimeout"):
                getattr(Q, name)
        elif sys.platform == "win32":
            from .trigger.windows import MouseHook, _u
            _u.SetWindowsHookExW, _u.CallNextHookEx
    except Exception as e:
        errors.append(f"перехват мыши: {e}")

    # отдельный процесс-исполнитель: именно так конвертирует установленное приложение
    try:
        import json
        import subprocess
        from .worker import command
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "w.txt"
            src.write_text("Проверка исполнителя", encoding="utf-8")
            job = {"files": [str(src)], "target": "docx",
                   "progress": str(Path(d) / "p.json"), "result": str(Path(d) / "r.json")}
            jp = Path(d) / "job.json"
            jp.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
            subprocess.run(command(str(jp)), timeout=180, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            res = json.loads((Path(d) / "r.json").read_text(encoding="utf-8"))
            if not res.get("ok") or not Path(res["outputs"][0]).exists():
                errors.append(f"исполнитель: {res}")
    except Exception as e:
        errors.append(f"исполнитель: {e}")

    # окно выбора вида собирается (все 8 превью рисуются)
    try:
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen" if sys.platform.startswith("linux") else "")
        if not os.environ["QT_QPA_PLATFORM"]:
            del os.environ["QT_QPA_PLATFORM"]
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from .settings_window import SettingsWindow
        from . import themes
        w = SettingsWindow()
        assert len(w.cards) == len(themes.THEMES) >= 8
        w.deleteLater()
    except Exception as e:
        errors.append(f"окно видов: {e}")

    if errors:
        _report("SELFTEST FAILED:\n  " + "\n  ".join(errors))
        return 1
    _report("SELFTEST OK")
    return 0
