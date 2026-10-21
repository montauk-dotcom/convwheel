"""ConvWheel — запуск.

    python main.py                 фоновый режим (значок в трее / строке меню)
    python main.py --file a.docx   сразу показать колесо для файла (отладка)
    python main.py --selftest      проверить, что все компоненты на месте
"""
import sys

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        from convwheel.selftest import main as selftest
        sys.exit(selftest())
    from convwheel.app import run
    sys.exit(run(sys.argv))
