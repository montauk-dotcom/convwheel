"""PDF: в DOCX (pdf2docx), TXT и картинки (PyMuPDF)."""
from __future__ import annotations

from pathlib import Path

from .common import ConversionError, Ctx, ensure_output


def _open(src: Path):
    try:
        import pymupdf
    except ImportError as e:
        raise ConversionError("Нужен пакет PyMuPDF") from e
    try:
        doc = pymupdf.open(str(src))
    except Exception as e:
        raise ConversionError(f"Не удалось открыть PDF: {e}") from e
    if doc.needs_pass:
        raise ConversionError("PDF защищён паролем")
    return doc


def pdf_to_txt(src: Path, ctx: Ctx) -> list[Path]:
    doc = _open(src)
    parts = []
    n = doc.page_count
    for i, page in enumerate(doc):
        parts.append(page.get_text("text", sort=True).rstrip())
        ctx.progress((i + 1) / n)
    doc.close()
    text = "\n\n".join(parts).strip()
    if not text:
        raise ConversionError("В PDF нет текстового слоя (это скан) — для него нужен OCR")
    out = ctx.out(src, "txt")
    out.write_text(text + "\n", encoding="utf-8")
    return ensure_output([out])


def pdf_to_images(src: Path, ctx: Ctx, fmt: str) -> list[Path]:
    """Каждая страница — отдельный файл. Одна страница → файл, несколько → папка."""
    doc = _open(src)
    dpi = ctx.config.pdf_image_dpi
    n = doc.page_count
    if n == 0:
        raise ConversionError("PDF без страниц")
    if n == 1:
        targets = [ctx.out(src, fmt)]
    else:
        folder = ctx.out_dir / f"{src.stem} ({fmt.upper()})"
        folder.mkdir()
        width = len(str(n))
        targets = [folder / f"{src.stem}_{str(i + 1).zfill(width)}.{fmt}" for i in range(n)]
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        if fmt == "jpg":
            pix.save(str(targets[i]), output="jpeg", jpg_quality=ctx.config.jpeg_quality)
        else:
            pix.save(str(targets[i]))
        ctx.progress((i + 1) / n)
    doc.close()
    return ensure_output([targets[0]] if n == 1 else [targets[0].parent])


def pdf_to_docx(src: Path, ctx: Ctx) -> list[Path]:
    try:
        from pdf2docx import Converter
    except ImportError as e:
        raise ConversionError("Нужен пакет pdf2docx") from e
    doc = _open(src)  # проверка пароля/битого файла до долгой конвертации
    scanned = all(not p.get_text().strip() for p in doc)
    doc.close()
    if scanned:
        raise ConversionError("В PDF нет текстового слоя (это скан) — DOCX получится из картинок, нужен OCR")
    out = ctx.out(src, "docx")
    ctx.progress(-1)
    try:
        cv = Converter(str(src))
        cv.convert(str(out), multi_processing=False)
        cv.close()
    except Exception as e:
        raise ConversionError(f"Ошибка PDF → DOCX: {e}") from e
    return ensure_output([out])
