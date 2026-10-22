"""Надёжность: падение конвертера не роняет приложение, сторож перезапускает агента,
повторный запуск открывает настройки, контроллер (значок + меню + колесо) собирается целиком."""
import os, sys, time, json, subprocess, threading
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from pathlib import Path
results = {}

# ---------- 1. сторож: два падения, потом нормальный выход
from convwheel import supervisor
work = Path(__file__).parent / "out_robust"; work.mkdir(exist_ok=True)
counter = work / "count.txt"; counter.write_text("0")
fake = work / "fake_agent.py"
fake.write_text(f"""import sys, os
p = r"{counter}"; n = int(open(p).read()) + 1; open(p, "w").write(str(n))
if n <= 2: os.abort()          # падение как в 1.1
if n == 3: sys.exit(75)        # просьба перезапуститься
sys.exit(0)                    # «Выход» из меню
""")
code = supervisor.supervise(lambda: [sys.executable, str(fake)], backoff=0.05)
results["supervisor_restarts"] = (code, counter.read_text())   # ожидаем (0, '4')

counter.write_text("0")
fake.write_text("import os; os.abort()")
code = supervisor.supervise(lambda: [sys.executable, str(fake)], max_crashes=3, backoff=0.01)
results["supervisor_gives_up"] = code                          # ожидаем 1

# ---------- 2. IPC
from convwheel import ipc
got = []
srv = ipc.Server(got.append); srv.start(); time.sleep(0.2)
results["ipc"] = (ipc.send("show"), got)
srv.close()

# ---------- 3. Qt: падение исполнителя и контроллер
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
app = QApplication([])
from convwheel.jobs import ConversionProcess
src = work / "a.txt"; src.write_text("x")
out = {}
job = ConversionProcess([src], "docx", None, {"selftest_crash": True})
job.failed.connect(lambda m: out.setdefault("fail", m))
job.succeeded.connect(lambda o: out.setdefault("ok", o))
job.done.connect(lambda *_: app.quit())
job.start(); QTimer.singleShot(20000, app.quit); app.exec()
results["worker_crash_isolated"] = out.get("fail", "")[:60]

from convwheel import app as appmod
from convwheel.config import CONFIG
CONFIG.extra["welcomed"] = True
ctl = appmod.Controller(app)
appmod._controller = ctl
steps = []
def s1():
    ctl.on_files([str(src)])
    steps.append(("wheel_shown", ctl.manager.wheel is not None and ctl.manager.wheel.isVisible()))
    ctl.set_theme("vinyl")
    steps.append(("theme", CONFIG.theme, ctl.theme_actions["vinyl"].isChecked()))
    ctl.on_command("show")
    steps.append(("settings_visible", ctl.settings.isVisible()))
    ctl.settings._pick("orange")
    steps.append(("menu_synced", ctl.theme_actions["orange"].isChecked()))
    ctl.manager.outside_click(ctl.manager.wheel.mapToGlobal(ctl.manager.wheel.rect().topLeft()) - __import__("PySide6.QtCore", fromlist=["QPoint"]).QPoint(400, 400))
    QTimer.singleShot(600, s2)                 # от момента клика, а не от старта теста
def s2():
    steps.append(("wheel_closed_by_outside_click", ctl.manager.wheel is None))
    ctl.demo("glass")
    steps.append(("demo", ctl.manager.wheel is not None and ctl.manager.wheel.demo))
    ctl.manager.wheel.start(0)
    QTimer.singleShot(2100, s3)
def s3():
    w = ctl.manager.wheel
    steps.append(("demo_done", w is not None and w.state == w.DONE))
    # меню как у AmneziaVPN: первым «Показать», последним «Закрыть»
    acts = [a.text() for a in ctl.menu.actions() if a.text()]
    steps.append(("menu_show_first_close_last", acts[0] == "Показать ConvWheel" and acts[-1] == "Закрыть ConvWheel"))
    # Док: окно открыто → в Доке; крестик → окно спрятано, из Дока ушли, приложение работает
    dock = []
    ctl._set_dock = lambda show: dock.append(show)
    win = ctl.settings
    win.close(); app.processEvents(); ctl._update_dock()
    steps.append(("x_hides_keeps_running", (not win.isVisible()) and ctl.tray.isVisible() and dock[-1] is False))
    ctl.show_settings(); app.processEvents(); ctl._update_dock()
    steps.append(("reopen_same_window", ctl.settings is win and win.isVisible() and dock[-1] is True))
    ctl.quit()
QTimer.singleShot(200, s1)
QTimer.singleShot(8000, app.quit)
code = app.exec()
results["controller"] = steps
results["quit_code"] = code
CONFIG.theme = "citrus"; CONFIG.extra.pop("welcomed", None); CONFIG.save()
for k, v in results.items(): print(k, "→", v)

ok = (results["supervisor_restarts"] == (0, "4") and results["supervisor_gives_up"] == 1
      and results["ipc"] == (True, ["show"]) and "аварийно" in results["worker_crash_isolated"]
      and all(s[1] is True or s[0] == "theme" for s in steps) and steps[1][1:] == ("vinyl", True)
      and len(steps) == 10 and code == 0)
print("ROBUSTNESS OK" if ok else "ROBUSTNESS FAILED")
sys.exit(0 if ok else 1)
