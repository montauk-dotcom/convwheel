"""Заглушка для Linux (для разработки): глобальный перехват не поддерживается,
используйте `python main.py --file путь`."""
import threading


class MouseHook(threading.Thread):
    def __init__(self, callback):
        super().__init__(daemon=True)
        self.status = "unsupported"

    def run(self):
        pass

    def stop(self):
        pass


def shift_down() -> bool:
    return False


def files_under_click(x, y) -> list[str]:
    return []
