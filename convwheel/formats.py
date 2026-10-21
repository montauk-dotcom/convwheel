"""Реестр: какие форматы можно получить из какого файла и чем конвертировать."""
from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Callable

from .converters import archive, folder, image, media, office, pdf, sheet, text
from .converters.common import ConversionError, Ctx
from .platform_utils import find_soffice

Converter = Callable[[Path, Ctx], list[Path]]


@dataclass(frozen=True)
class Target:
    key: str            # уникальный ключ варианта
    label: str          # крупная надпись на сегменте
    hint: str           # мелкая подпись
    color: str          # акцентный цвет сегмента
    convert: Converter | None = None   # конвертер одного файла
    batch: Callable[[list[Path], Ctx], list[Path]] | None = None  # для «объединить в один»


COLORS = {
    "pdf": "#FF5A5F", "docx": "#4C8DFF", "doc": "#4C8DFF", "odt": "#3FB8C9", "rtf": "#7A8CFF",
    "txt": "#B8C2CC", "html": "#FF9F43", "md": "#9AA5B1",
    "xlsx": "#2ECC71", "csv": "#7BD88F", "ods": "#3FC9A0",
    "pptx": "#FF7A45", "odp": "#FFA36C",
    "png": "#3DDC97", "jpg": "#FFB547", "webp": "#4FD1C5", "bmp": "#A0AEC0", "gif": "#D96CFF",
    "tiff": "#8FA3BF", "ico": "#F6E05E",
    "mp4": "#5B8CFF", "mov": "#6C7BFF", "webm": "#29C7AC", "mp3": "#B07CFF", "wav": "#FF6FA8",
    "ogg": "#F08A5D", "flac": "#4FC3F7", "m4a": "#C38BFF",
}
HINTS = {
    "pdf": "Документ PDF", "docx": "Word", "doc": "Word 97–2003", "odt": "OpenDocument",
    "rtf": "Rich Text", "txt": "Простой текст", "html": "Веб-страница", "xlsx": "Excel",
    "csv": "Таблица CSV", "ods": "OpenDocument", "pptx": "PowerPoint", "odp": "OpenDocument",
    "png": "Без потерь", "jpg": "Фото", "webp": "Для веба", "bmp": "Растр", "gif": "GIF",
    "tiff": "Печать", "ico": "Иконка", "mp4": "Видео H.264", "mov": "QuickTime",
    "webm": "Видео VP9", "mp3": "Аудио", "wav": "Без сжатия", "ogg": "Vorbis",
    "flac": "Без потерь", "m4a": "AAC",
}


def T(ext: str, fn: Converter, label: str | None = None, hint: str | None = None) -> Target:
    return Target(ext, label or ext.upper(), hint or HINTS.get(ext, ""), COLORS.get(ext, "#7FB3FF"), fn)


def _office(fmt: str) -> Converter:
    return lambda src, ctx: office.office_convert(src, fmt, ctx)


def _docx_txt(src: Path, ctx: Ctx) -> list[Path]:
    if src.suffix.lower() == ".docx":
        return text.docx_to_txt(src, ctx)
    return office.office_convert(src, "txt", ctx)


def _sheet_csv(src: Path, ctx: Ctx) -> list[Path]:
    if find_soffice():
        try:
            return office.libreoffice_convert(src, "csv", ctx)
        except ConversionError:
            if src.suffix.lower() not in (".xlsx", ".xlsm"):
                raise
    if src.suffix.lower() in (".xlsx", ".xlsm"):
        return sheet.xlsx_to_csv(src, ctx)
    raise ConversionError("Для этого формата таблиц нужен LibreOffice")


def _csv_xlsx(src: Path, ctx: Ctx) -> list[Path]:
    return sheet.csv_to_xlsx(src, ctx)


def _img(fmt: str) -> Converter:
    return partial(image.convert_image, fmt=fmt)


def _pdfimg(fmt: str) -> Converter:
    return partial(pdf.pdf_to_images, fmt=fmt)


def _media(fmt: str) -> Converter:
    return partial(media.convert_media, fmt=fmt)


WORD_EXT = {"docx", "doc", "odt", "rtf"}
TEXT_EXT = {"txt", "md"}
SHEET_EXT = {"xlsx", "xls", "ods", "xlsm"}
SLIDE_EXT = {"pptx", "ppt", "odp"}
IMAGE_EXT = {"png", "jpg", "jpeg", "webp", "bmp", "gif", "tif", "tiff", "heic", "heif", "ico"}
VIDEO_EXT = {"mp4", "mov", "mkv", "avi", "webm", "m4v", "wmv", "flv"}
AUDIO_EXT = {"mp3", "wav", "ogg", "flac", "m4a", "aac", "wma", "opus"}

ALIASES = {"jpeg": "jpg", "tif": "tiff", "heif": "heic", "htm": "html", "xlsm": "xlsx"}


def norm_ext(path: Path) -> str:
    e = path.suffix.lower().lstrip(".")
    return ALIASES.get(e, e)


def _folder_targets(path: Path) -> list[Target]:
    out = [
        Target("zip", "ZIP", "Архив", "#9AA5B1", archive.to_zip),
        Target("7z", "7Z", "Сильное сжатие", "#9AA5B1", archive.to_7z),
        Target("tar.gz", "TAR.GZ", "Архив Unix", "#9AA5B1", archive.to_targz),
    ]
    imgs = folder.top_files(path, folder.IMAGE_EXT)
    if imgs:
        out.append(Target("imgpdf", "PDF", "Картинки в один", "#FF5A5F", folder.images_to_pdf))
    if folder.top_files(path, folder.DOC_EXT):
        out.append(Target("docpdf", "PDF", "Документы → PDF", "#FF5A5F", folder.docs_to_pdf))
    if any(f.suffix.lower() not in (".jpg", ".jpeg") for f in imgs):
        out.append(Target("jpgall", "JPG", "Фото → JPG", "#FFB547", folder.photos_to_jpg))
    if imgs:
        out.append(Target("shrink", "СЖАТЬ", "Для отправки", "#3DDC97", folder.compress_photos))
    out.append(Target("list", "TXT", "Список файлов", "#B8C2CC", folder.file_list))
    return out[:8]


def _archive_targets(path: Path) -> list[Target]:
    kind = archive.archive_kind(path)
    out = [Target("extract", "ПАПКА", "Распаковать", "#3DDC97", archive.extract)]
    for key, label, hint in (("zip", "ZIP", "Перепаковать"), ("7z", "7Z", "Сильное сжатие"),
                             ("tar.gz", "TAR.GZ", "Архив Unix")):
        if kind in ((".tar.gz", ".tgz") if key == "tar.gz" else (f".{key}",)):
            continue
        out.append(Target(key, label, hint, "#9AA5B1", partial(archive.repack, fmt=key)))
    return out


def targets_for(path: Path) -> list[Target]:
    if path.is_dir():
        if path.parent == path:        # корень диска — не предлагаем архивировать весь диск
            return []
        return _folder_targets(path)
    if archive.archive_kind(path):
        return _archive_targets(path)

    e = norm_ext(path)
    raw = path.suffix.lower().lstrip(".")
    out: list[Target] = []

    if raw in WORD_EXT:
        out = [T("pdf", _office("pdf")), T("txt", _docx_txt), T("docx", _office("docx")),
               T("odt", _office("odt")), T("rtf", _office("rtf")), T("html", _office("html")),
               T("doc", _office("doc"))]
    elif raw in TEXT_EXT:
        out = [T("pdf", _office("pdf")), T("docx", text.text_to_docx), T("html", text.text_to_html),
               T("odt", _office("odt")), T("txt", text.text_to_txt, hint="Без разметки" if e == "md" else "В UTF-8")]
        if e == "txt":
            out = [t for t in out if t.key != "txt"] + [T("txt", text.text_to_txt, "UTF-8", "Перекодировать")]
    elif raw == "pdf":
        out = [T("docx", pdf.pdf_to_docx), T("txt", pdf.pdf_to_txt),
               T("png", _pdfimg("png"), hint="Страницы"), T("jpg", _pdfimg("jpg"), hint="Страницы")]
    elif raw in SHEET_EXT:
        out = [T("pdf", _office("pdf")), T("csv", _sheet_csv), T("xlsx", _office("xlsx")),
               T("ods", _office("ods"))]
    elif raw == "csv":
        out = [T("xlsx", _csv_xlsx), T("pdf", _office("pdf")), T("ods", _office("ods"))]
    elif raw in SLIDE_EXT:
        out = [T("pdf", _office("pdf")), T("pptx", _office("pptx")), T("odp", _office("odp"))]
    elif raw in IMAGE_EXT:
        out = [T(f, _img(f)) for f in ("png", "jpg", "webp", "pdf", "ico", "gif", "bmp", "tiff")]
    elif raw in VIDEO_EXT:
        out = [T(f, _media(f)) for f in ("mp4", "mp3", "gif", "webm", "mov", "wav")]
        out = [t if t.key != "mp3" else T("mp3", _media("mp3"), hint="Звук из видео") for t in out]
    elif raw in AUDIO_EXT:
        out = [T(f, _media(f)) for f in ("mp3", "wav", "flac", "ogg", "m4a")]

    # не предлагаем конвертировать в тот же формат (кроме перекодировки txt)
    out = [t for t in out if not (t.key == e and t.label == e.upper())]
    return out[:8]   # колесо рассчитано максимум на 8 секторов


MERGE_PDF = Target("merge_pdf", "PDF", "Один файл", "#FF5A5F", batch=image.images_to_single_pdf)


def targets_for_many(paths: list[Path]) -> list[Target]:
    """Для нескольких файлов — только варианты, общие для всех."""
    if not paths:
        return []
    if len(paths) == 1:
        return targets_for(paths[0])
    common: dict[str, Target] | None = None
    for p in paths:
        ts = {t.key: t for t in targets_for(p)}
        common = ts if common is None else {k: v for k, v in common.items() if k in ts}
    # Конвертер берётся под каждый файл отдельно (у DOCX и TXT разные функции «в PDF»)
    result = list(common.values()) if common else []
    if all(p.suffix.lower().lstrip(".") in IMAGE_EXT for p in paths):
        result = [MERGE_PDF] + result
    return result[:8]


def converter_for(path: Path, key: str) -> Converter:
    for t in targets_for(path):
        if t.key == key and t.convert:
            return t.convert
    raise ConversionError(f"{path.name}: нельзя сконвертировать в {key.upper()}")


def supported(path: Path) -> bool:
    return bool(targets_for(path))
