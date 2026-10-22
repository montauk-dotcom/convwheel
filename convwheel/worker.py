"""Процесс-исполнитель конвертации: `ConvWheel --worker задание.json`.

Каждая конвертация идёт в отдельном процессе. Если библиотека (PDF, картинки, видео)
упадёт на «плохом» файле, погибнет только этот процесс — колесо покажет ошибку, а сам
ConvWheel продолжит работать.

Обмен — через файлы, а не stdout: у оконной сборки Windows консоли нет.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path


def _write_atomic(path: str, data: dict) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def main(job_path: str) -> int:
    from .crashlog import install as install_crashlog
    install_crashlog("worker")
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    progress_path, result_path = job["progress"], job["result"]
    last = [0.0]

    def progress(p: float, name: str):
        now = time.monotonic()
        if now - last[0] >= 0.08 or p >= 1 or p < 0:     # не чаще ~12 раз в секунду
            last[0] = now
            try:
                _write_atomic(progress_path, {"p": p, "name": name})
            except OSError:
                pass

    try:
        if job.get("selftest_crash"):      # для проверки защиты от падений
            os.abort()
        if job.get("test_sleep"):          # для тестов: «долгая» конвертация
            time.sleep(float(job["test_sleep"]))
        from .converters.common import ConversionError
        from .engine import run_job
        from .formats import targets_for_many
        files = [Path(f) for f in job["files"]]
        target = next((t for t in targets_for_many(files) if t.key == job["target"]), None)
        if target is None:
            raise ConversionError(f"Действие «{job['target']}» недоступно для этого файла")
        outs = run_job(files, target, progress)
        _write_atomic(result_path, {"ok": True, "outputs": [str(o) for o in outs]})
        return 0
    except Exception as e:
        from .converters.common import ConversionError
        if not isinstance(e, ConversionError):
            from .engine import _log
            _log(traceback.format_exc())
            msg = f"Неожиданная ошибка: {e}"
        else:
            msg = str(e)
        try:
            _write_atomic(result_path, {"ok": False, "error": msg})
        except OSError:
            pass
        return 1


def command(job_path: str) -> list[str]:
    """Как запустить исполнителя: та же программа с ключом --worker."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--worker", job_path]
    main_py = str(Path(__file__).resolve().parent.parent / "main.py")
    py = sys.executable
    if sys.platform.startswith("win") and py.lower().endswith("python.exe"):
        cand = py[:-10] + "pythonw.exe"           # без чёрного окна консоли
        if os.path.exists(cand):
            py = cand
    return [py, main_py, "--worker", job_path]
