"""Действия над папкой: пакетная конвертация содержимого и список файлов."""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from ..platform_utils import human_size
from .common import ConversionError, Ctx, ensure_output

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".heic", ".heif"}
DOC_EXT = {".docx", ".doc", ".odt", ".rtf", ".xlsx", ".xls", ".ods", ".pptx", ".ppt", ".odp", ".txt", ".md"}


def natural_key(p: Path):
    """«фото 2» раньше «фото 10»."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def top_files(folder: Path, exts: set[str]) -> list[Path]:
    try:
        return sorted((f for f in folder.iterdir()
                       if f.is_file() and f.suffix.lower() in exts and not f.name.startswith(("~$", "."))),
                      key=natural_key)
    except OSError:
        return []


def _subfolder(ctx: Ctx, src: Path, label: str) -> Path:
    d = ctx.out_dir / f"{src.name} ({label})"
    d.mkdir()
    return d


def images_to_pdf(src: Path, ctx: Ctx) -> list[Path]:
    from PIL import ImageOps
    from .image import _flatten, _load
    files = top_files(src, IMAGE_EXT)
    if not files:
        raise ConversionError("В папке нет картинок")
    out = ctx.out_dir / f"{src.name}.pdf"
    pages = []
    for i, f in enumerate(files):
        im, _ = _load(f)
        pages.append(_flatten(ImageOps.exif_transpose(im)))
        ctx.progress((i + 1) / len(files) * 0.9)
    pages[0].save(str(out), "PDF", save_all=True, append_images=pages[1:], resolution=150.0)
    return ensure_output([out])


def _batch(src: Path, ctx: Ctx, files: list[Path], label: str, fn) -> list[Path]:
    """Конвертирует каждый файл в подпапку; ошибки отдельных файлов не роняют весь пакет."""
    if not files:
        raise ConversionError("В папке нет подходящих файлов")
    dest = _subfolder(ctx, src, label)
    errors = []
    for i, f in enumerate(files):
        try:
            sub = Ctx(dest, lambda p, i=i: ctx.progress(-1 if p < 0 else (i + p) / len(files)), ctx.config)
            fn(f, sub)
        except ConversionError as e:
            errors.append(f"{f.name}: {e}")
        ctx.progress((i + 1) / len(files))
    if not any(dest.iterdir()):
        raise ConversionError("Ни один файл не сконвертировался:\n" + "\n".join(errors[:5]))
    if errors:
        (dest / "_ошибки.txt").write_text("\n".join(errors), encoding="utf-8")
    return [dest]


def docs_to_pdf(src: Path, ctx: Ctx) -> list[Path]:
    from .office import office_convert
    return _batch(src, ctx, top_files(src, DOC_EXT), "PDF", lambda f, c: office_convert(f, "pdf", c))


def photos_to_jpg(src: Path, ctx: Ctx) -> list[Path]:
    from .image import convert_image
    files = [f for f in top_files(src, IMAGE_EXT) if f.suffix.lower() not in (".jpg", ".jpeg")]
    if not files:
        raise ConversionError("Все картинки в папке уже JPG")
    return _batch(src, ctx, files, "JPG", lambda f, c: convert_image(f, c, "jpg"))


def compress_photos(src: Path, ctx: Ctx, max_side: int = 2560, quality: int = 82) -> list[Path]:
    """Уменьшает фото до 2560 px по длинной стороне и пережимает в JPG — для отправки."""
    from PIL import Image, ImageOps
    from .image import _flatten, _load

    def one(f: Path, c: Ctx):
        im, _ = _load(f)
        im = _flatten(ImageOps.exif_transpose(im))
        im.thumbnail((max_side, max_side), Image.LANCZOS)
        im.save(c.out(f, "jpg"), "JPEG", quality=quality, optimize=True, progressive=True)

    return _batch(src, ctx, top_files(src, IMAGE_EXT), "сжато", one)


def file_list(src: Path, ctx: Ctx) -> list[Path]:
    """Дерево папки с размерами — удобно отправить или распечатать."""
    lines = [f"{src}", f"Создано: {datetime.now():%d.%m.%Y %H:%M}", ""]
    total_files, total_size, limit = 0, 0, 50000
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames.sort(key=str.lower)
        rel = Path(dirpath).relative_to(src)
        depth = 0 if str(rel) == "." else len(rel.parts)
        if depth:
            lines.append("    " * (depth - 1) + f"📁 {rel.name}/")
        for f in sorted(filenames, key=str.lower):
            if f in (".DS_Store", "Thumbs.db", "desktop.ini"):
                continue
            try:
                size = (Path(dirpath) / f).stat().st_size
            except OSError:
                size = 0
            total_files += 1
            total_size += size
            if total_files <= limit:
                lines.append("    " * depth + f"{f}  —  {human_size(size)}")
    if total_files > limit:
        lines.append(f"… и ещё {total_files - limit} файлов")
    lines += ["", f"Всего файлов: {total_files}, общий размер: {human_size(total_size)}"]
    out = ctx.out_dir / f"{src.name} — список файлов.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ensure_output([out])


def folder_summary(folder: Path, cap: int = 20000) -> tuple[int, int, bool]:
    """(кол-во файлов, размер, обрезано_ли) — с ограничением, чтобы не тормозить на огромных папках."""
    n = size = 0
    for dirpath, _dirs, files in os.walk(folder):
        for f in files:
            n += 1
            try:
                size += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
            if n >= cap:
                return n, size, True
    return n, size, False
