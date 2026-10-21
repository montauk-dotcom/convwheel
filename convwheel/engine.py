"""Выполнение конвертации: временная папка → проверка → атомарный перенос рядом с исходником.

Логика без Qt (run_job) отделена от Qt-обёртки (ConvertJob), чтобы её можно было
тестировать и использовать из командной строки.
"""
from __future__ import annotations

import shutil
import tempfile
import traceback
from pathlib import Path
from typing import Callable

from .config import CONFIG
from .converters.common import ConversionError, Ctx
from .formats import Target, converter_for
from .platform_utils import config_dir


def unique_path(p: Path) -> Path:
    """report.pdf → report (1).pdf, если такой уже есть. Ничего не перезаписываем."""
    if not p.exists():
        return p
    stem, suf = (p.name, "") if p.is_dir() else (p.stem, p.suffix)
    i = 1
    while True:
        cand = p.with_name(f"{stem} ({i}){suf}")
        if not cand.exists():
            return cand
        i += 1


def _dest_dir(src: Path) -> Path:
    if CONFIG.output_dir:
        d = Path(CONFIG.output_dir).expanduser()
        d.mkdir(parents=True, exist_ok=True)
        return d
    return src.parent


def _place(results: list[Path], src: Path) -> list[Path]:
    placed = []
    for r in results:
        dest = unique_path(_dest_dir(src) / r.name)
        shutil.move(str(r), str(dest))
        placed.append(dest)
    return placed


def run_job(files: list[Path], target: Target,
            progress: Callable[[float, str], None] = lambda p, s: None) -> list[Path]:
    """Конвертирует файлы; бросает ConversionError с понятным текстом при неудаче."""
    files = [Path(f) for f in files]
    for f in files:
        if not f.is_file():
            raise ConversionError(f"Файл не найден: {f.name}")

    outputs: list[Path] = []
    errors: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="convwheel_"))
    try:
        if target.batch:  # несколько файлов → один результат
            ctx = Ctx(tmp, lambda p: progress(p, files[0].name))
            outputs += _place(target.batch(files, ctx), files[0])
        else:
            n = len(files)
            for i, f in enumerate(files):
                sub = tmp / str(i)
                sub.mkdir()

                def prog(p: float, i=i, name=f.name):
                    progress(-1 if p < 0 else (i + p) / n, name)

                try:
                    fn = converter_for(f, target.key)
                    outputs += _place(fn(f, Ctx(sub, prog)), f)
                except ConversionError as e:
                    errors.append(f"{f.name}: {e}" if n > 1 else str(e))
                except Exception as e:  # неожиданное — пишем в лог, пользователю коротко
                    _log(traceback.format_exc())
                    errors.append(f"{f.name}: {e}")
                progress((i + 1) / n, f.name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if errors and not outputs:
        raise ConversionError("\n".join(errors))
    if errors:
        _log("Частичные ошибки:\n" + "\n".join(errors))
    return outputs


def _log(text: str) -> None:
    try:
        with open(config_dir() / "convwheel.log", "a", encoding="utf-8") as fh:
            fh.write(text.rstrip() + "\n")
    except Exception:
        pass


# ------------------------------------------------------------------ Qt-обёртка
try:
    from PySide6.QtCore import QObject, QThread, Signal

    class ConvertJob(QThread):
        progressed = Signal(float, str)
        succeeded = Signal(list)
        failed = Signal(str)

        def __init__(self, files: list[Path], target: Target, parent: QObject | None = None):
            super().__init__(parent)
            self.files, self.target = files, target

        def run(self):
            try:
                outs = run_job(self.files, self.target, lambda p, s: self.progressed.emit(p, s))
                self.succeeded.emit([str(o) for o in outs])
            except ConversionError as e:
                self.failed.emit(str(e))
            except Exception as e:
                _log(traceback.format_exc())
                self.failed.emit(f"Неожиданная ошибка: {e}")
except ImportError:  # pragma: no cover — Qt не обязателен для CLI/тестов
    ConvertJob = None  # type: ignore
