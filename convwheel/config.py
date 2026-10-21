"""Настройки приложения (JSON в папке конфигурации пользователя)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from .platform_utils import config_dir


@dataclass
class Config:
    enabled: bool = True
    # Кнопка мыши, которая вместе с Shift открывает колесо: "left" | "middle" | "right"
    trigger_button: str = "left"
    # Задержка (мс) после клика, прежде чем читать выделение — Проводник/Finder
    # должны успеть обновить его.
    selection_delay_ms: int = 140
    # Движок офисных документов: "auto" (MS Office на Windows, если есть, иначе LibreOffice),
    # "msoffice" или "libreoffice"
    office_engine: str = "auto"
    # Разрешение при экспорте страниц PDF в картинки
    pdf_image_dpi: int = 200
    jpeg_quality: int = 92
    # Если пусто — результат кладётся рядом с исходным файлом
    output_dir: str = ""
    extra: dict = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Config":
        p = config_dir() / "config.json"
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            return cls(**known)
        except Exception:
            return cls()

    def save(self) -> None:
        p = config_dir() / "config.json"
        p.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")


CONFIG = Config.load()
