"""Регрессия падения 1.1: колесо не должно удаляться, пока идёт конвертация.

Сценарий из отчётов macOS: клик по самому краю колеса — глобальный перехват считает его
«мимо» (dismiss), а колесо — выбором сектора (start). Старый код удалял колесо вместе с
потоком конвертации → «QThread: Destroyed while thread is still running» → abort.
"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path
from PySide6.QtCore import QTimer, QPointF
from PySide6.QtWidgets import QApplication

app = QApplication([])
from convwheel.jobs import WheelManager
from convwheel.wheel import R_OUT
from convwheel.formats import targets_for

work = Path(__file__).parent / "out_lifecycle"; work.mkdir(exist_ok=True)
src = work / "заметка.txt"; src.write_text("Привет", encoding="utf-8")
mgr = WheelManager()
mgr.job_extra = {"test_sleep": 2.0}
results = {}

def step1():                                   # клик по краю: dismiss + start одновременно
    w = mgr.wheel
    rim = w.mapToGlobal(QPointF(w.width() / 2, w.height() / 2 - (R_OUT + 25)).toPoint())
    mgr.outside_click(rim)
    w.start([t.key for t in w.targets].index("docx"))
    results["busy_after_click"] = w.busy

def step2():                                   # во время конвертации: новый Shift+клик, Esc, Alt+F4
    w = mgr.wheel
    results["still_same_wheel"] = w is not None and w.busy
    results["new_wheel_refused"] = not mgr.show([src], targets_for(src))
    w.dismiss(); w.close()
    results["survived_close"] = mgr.wheel is w and w.isVisible()

def step3():
    w = mgr.wheel
    results["state"] = w.state if w else None
    results["status"] = w.status_text if w else None
    w.dismiss()

def step4():
    results["wheel_released"] = mgr.wheel is None
    app.quit()

mgr.show([src], targets_for(src))
QTimer.singleShot(300, step1)
QTimer.singleShot(1000, step2)
QTimer.singleShot(4300, step3)
QTimer.singleShot(5000, step4)
app.exec()
print(results)
ok = (results["busy_after_click"] and results["still_same_wheel"] and results["new_wheel_refused"]
      and results["survived_close"] and results["state"] == 2 and results["wheel_released"]
      and (work / "заметка.docx").exists())
print("LIFECYCLE OK" if ok else "LIFECYCLE FAILED")
sys.exit(0 if ok else 1)
