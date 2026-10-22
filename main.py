"""ConvWheel — запуск.

    ConvWheel                      обычный запуск (двойной клик, автозапуск)
    ConvWheel --file a.docx        сразу показать колесо для файла (отладка)
    ConvWheel --demo               показать колесо-пример текущего вида
    ConvWheel --selftest           проверить, что все компоненты на месте

Служебные режимы (запускаются самой программой):
    --agent        основная часть: значок, перехват мыши, колесо
    --worker JOB   одна конвертация в отдельном процессе
    --watchdog PID (macOS) перезапуск после аварийного падения
"""
import sys


def _arg(name: str) -> str | None:
    if name in sys.argv:
        i = sys.argv.index(name)
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else None
    return None


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        from convwheel.selftest import main as selftest
        sys.exit(selftest())
    if "--worker" in sys.argv:
        from convwheel.worker import main as worker_main
        sys.exit(worker_main(_arg("--worker")))
    if "--watchdog" in sys.argv:
        from convwheel.watchdog import main as watchdog_main
        sys.exit(watchdog_main(int(_arg("--watchdog") or 0)))
    if "--agent" in sys.argv or "--file" in sys.argv or "--demo" in sys.argv:
        from convwheel.app import run
        sys.exit(run(sys.argv))
    from convwheel.platform_utils import IS_MAC
    if IS_MAC:
        # На macOS основная часть — это сам процесс приложения (так работают «Открыть ещё раз»
        # и значок в строке меню), а от падений страхует отдельный watchdog.
        from convwheel.app import run_mac_main
        sys.exit(run_mac_main(sys.argv))
    from convwheel.supervisor import main as supervisor_main
    sys.exit(supervisor_main())
