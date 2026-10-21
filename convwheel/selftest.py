"""Самопроверка собранного приложения: `ConvWheel --selftest`.

Запускается в CI после сборки: если в .app не попала какая-то библиотека или ffmpeg,
сборка упадёт сразу, а не у пользователя.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path


def main() -> int:
    errors = []
    mods = ("pynput.mouse",) if sys.platform in ("darwin", "win32") else ()  # на Linux нужен X-сервер
    for mod in (*mods, "PySide6.QtWidgets", "pymupdf", "pdf2docx", "docx", "openpyxl",
                "PIL.Image", "markdown"):
        try:
            __import__(mod)
        except Exception as e:
            errors.append(f"import {mod}: {e}")
    if sys.platform == "darwin":
        for mod in ("AppKit", "Quartz", "ApplicationServices"):
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
    except Exception as e:
        errors.append(f"конвертация: {e}")

    if errors:
        print("SELFTEST FAILED:\n  " + "\n  ".join(errors))
        return 1
    print("SELFTEST OK")
    return 0
