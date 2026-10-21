from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..config import CONFIG, Config


class ConversionError(Exception):
    """Понятная пользователю ошибка конвертации."""


@dataclass
class Ctx:
    """Контекст одной конвертации: куда писать, как сообщать прогресс."""
    out_dir: Path                      # временная папка для результата
    progress: Callable[[float], None] = lambda p: None   # 0..1, или -1 = неизвестно
    config: Config = field(default_factory=lambda: CONFIG)

    def out(self, src: Path, ext: str, suffix: str = "") -> Path:
        return self.out_dir / f"{src.stem}{suffix}.{ext}"


def read_text_smart(path: Path) -> str:
    """Читает текстовый файл, угадывая кодировку (UTF-8/UTF-16/CP1251)."""
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace")
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("cp1251")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


def ensure_output(paths: list[Path]) -> list[Path]:
    """Проверяет, что результат действительно создан и не пустой."""
    good = [p for p in paths if p.exists() and (p.is_dir() or p.stat().st_size > 0)]
    if not good:
        raise ConversionError("Конвертер не создал файл результата")
    return good
