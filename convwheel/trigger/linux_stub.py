"""Заглушка для Linux (для разработки): глобальный триггер не поддерживается,
используйте `python main.py --file путь`."""


def shift_down() -> bool:
    return False


def cursor_pos(x, y):
    return x, y


def files_under_click(x, y) -> list[str]:
    return []
