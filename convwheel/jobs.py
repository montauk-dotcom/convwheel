"""Показ колёс и запуск конвертаций.

WheelManager — единственный владелец колёс и задач:
  • колесо удаляется только через deleteLater(), и только когда оно закрылось само;
  • пока колесо занято конвертацией, его нельзя закрыть или заменить новым;
  • конвертация идёт в отдельном процессе (ConversionProcess), а не потоком внутри колеса.
Так исключено падение «QThread: Destroyed while thread is still running» из версии 1.1.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal
from PySide6.QtGui import QCursor

from . import worker
from .crashlog import write as log
from .formats import Target
from .wheel import ConvertWheel


class ConversionProcess(QObject):
    progressed = Signal(float, str)
    succeeded = Signal(list)
    failed = Signal(str)
    done = Signal(object)

    def __init__(self, files: list[Path], target_key: str, parent: QObject | None = None,
                 extra: dict | None = None):
        super().__init__(parent)
        self.tmp = Path(tempfile.mkdtemp(prefix="cw_job_"))
        self.progress_file = self.tmp / "progress.json"
        self.result_file = self.tmp / "result.json"
        job = {"files": [str(f) for f in files], "target": target_key,
               "progress": str(self.progress_file), "result": str(self.result_file), **(extra or {})}
        self.job_file = self.tmp / "job.json"
        self.job_file.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        self._finished = False

        cmd = worker.command(str(self.job_file))
        self.proc = QProcess(self)
        self.proc.setProgram(cmd[0])
        self.proc.setArguments(cmd[1:])
        env = QProcessEnvironment.systemEnvironment()
        env.insert("CONVWHEEL_WORKER", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        self.proc.setProcessEnvironment(env)
        self.proc.setStandardOutputFile(QProcess.nullDevice())
        self.proc.setStandardErrorFile(QProcess.nullDevice())
        self.proc.finished.connect(self._on_finished)
        self.proc.errorOccurred.connect(self._on_error)
        self.poll = QTimer(self)
        self.poll.setInterval(100)
        self.poll.timeout.connect(self._read_progress)

    def start(self):
        self.progressed.emit(-1.0, "")
        self.proc.start()
        self.poll.start()

    def kill(self):
        if self.proc.state() != QProcess.NotRunning:
            self.proc.kill()

    def _read_progress(self):
        try:
            d = json.loads(self.progress_file.read_text(encoding="utf-8"))
            self.progressed.emit(float(d.get("p", -1)), str(d.get("name", "")))
        except (OSError, ValueError):
            pass

    def _on_error(self, err):
        if err == QProcess.FailedToStart:
            log(f"Не удалось запустить исполнителя: {self.proc.program()} {self.proc.errorString()}")
            self._finish(False, "Не удалось запустить конвертер")

    def _on_finished(self, code: int, status):
        try:
            res = json.loads(self.result_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            res = None
        if res and res.get("ok"):
            self._finish(True, res.get("outputs", []))
        elif res:
            self._finish(False, res.get("error") or "Ошибка конвертации")
        else:
            log(f"Исполнитель завершился аварийно (код {code}, статус {status})")
            self._finish(False, "Конвертер аварийно завершился на этом файле. "
                                "Исходный файл не изменён, ConvWheel продолжает работать.")

    def _finish(self, ok: bool, payload):
        if self._finished:
            return
        self._finished = True
        self.poll.stop()
        if ok:
            self.succeeded.emit(list(payload))
        else:
            self.failed.emit(str(payload))
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.done.emit(self)


class WheelManager(QObject):
    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.wheel: ConvertWheel | None = None
        self._retired: dict[int, ConvertWheel] = {}
        self._jobs: set[ConversionProcess] = set()
        self.job_extra: dict = {}           # для тестов (например, test_sleep)

    @property
    def busy(self) -> bool:
        return self.wheel is not None and self.wheel.busy

    def show(self, files: list[Path], targets: list[Target], *, demo: bool = False,
             theme: str | None = None, pos=None) -> bool:
        if not targets:
            return False
        if self.wheel is not None:
            if self.wheel.busy:
                return False                 # идёт конвертация — новое колесо не открываем
            old, self.wheel = self.wheel, None
            self._retire(old)
        w = ConvertWheel(files, targets, theme=theme, demo=demo)
        w.closed.connect(self._on_closed)
        w.convert_requested.connect(self._on_convert)
        self.wheel = w
        w.popup_at(pos)
        return True

    def show_demo(self, theme: str | None = None, pos=None) -> bool:
        from .wheel import SAMPLE_FILE, sample_targets
        return self.show([SAMPLE_FILE], sample_targets(), demo=True, theme=theme, pos=pos)

    def outside_click(self, pos=None):
        """Нажатие мыши где-то в системе: если мимо колеса — плавно закрыть его."""
        w = self.wheel
        if w is None or w.busy or not w.isVisible():
            return
        if not w.contains_global(pos if pos is not None else QCursor.pos()):
            w.dismiss()

    outside_click_at = outside_click

    def _on_closed(self, w: ConvertWheel):
        if self.wheel is w:
            self.wheel = None
        self._retire(w)

    def _retire(self, w: ConvertWheel):
        """Удаление — только отложенное, через цикл событий (никогда из обработчика самого колеса)."""
        key = id(w)
        if key in self._retired:
            return
        if w.busy:                     # на всякий случай: занятое колесо не трогаем
            return
        w.timer.stop()
        w.autoclose.stop()
        w.hide()
        self._retired[key] = w
        w.destroyed.connect(lambda *_a, k=key: QTimer.singleShot(0, lambda: self._retired.pop(k, None)))
        w.deleteLater()

    def _on_convert(self, w: ConvertWheel, target: Target):
        job = ConversionProcess(w.files, target.key, self, self.job_extra)
        job.progressed.connect(w.set_progress)
        job.succeeded.connect(w.finish_ok)
        job.failed.connect(w.finish_fail)
        job.done.connect(self._job_done)
        self._jobs.add(job)
        job.start()

    def _job_done(self, job: ConversionProcess):
        self._jobs.discard(job)
        job.deleteLater()

    def shutdown(self):
        for j in list(self._jobs):
            j.kill()
