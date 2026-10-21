"""Изображения через Pillow (+ HEIC через pillow-heif, если установлен)."""
from __future__ import annotations

from pathlib import Path

from .common import ConversionError, Ctx, ensure_output

try:  # HEIC/HEIF с iPhone
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:
    pass

PIL_FORMAT = {"png": "PNG", "jpg": "JPEG", "webp": "WEBP", "bmp": "BMP", "gif": "GIF",
              "tiff": "TIFF", "ico": "ICO", "pdf": "PDF"}


def _flatten(im, bg=(255, 255, 255)):
    """Убирает прозрачность (для JPG/PDF/BMP) — прозрачное станет белым, а не чёрным."""
    from PIL import Image
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        base = Image.new("RGB", im.size, bg)
        base.paste(im, mask=im.getchannel("A"))
        return base
    return im.convert("RGB") if im.mode != "RGB" else im


def _load(src: Path):
    try:
        from PIL import Image, ImageOps
    except ImportError as e:
        raise ConversionError("Нужен пакет Pillow") from e
    try:
        im = Image.open(str(src))
        im.load()
    except Exception as e:
        hint = " (для HEIC установите pillow-heif)" if src.suffix.lower() in (".heic", ".heif") else ""
        raise ConversionError(f"Не удалось открыть изображение{hint}: {e}") from e
    return im, ImageOps


def convert_image(src: Path, ctx: Ctx, fmt: str) -> list[Path]:
    from PIL import Image, ImageSequence

    im, ImageOps = _load(src)
    out = ctx.out(src, fmt)
    animated = getattr(im, "is_animated", False) and getattr(im, "n_frames", 1) > 1
    exif = im.info.get("exif")

    if animated and fmt in ("gif", "webp"):
        frames = [f.convert("RGBA") for f in ImageSequence.Iterator(im)]
        durations = [f.info.get("duration", im.info.get("duration", 100)) for f in ImageSequence.Iterator(im)]
        frames[0].save(str(out), format=PIL_FORMAT[fmt], save_all=True, append_images=frames[1:],
                       duration=durations, loop=im.info.get("loop", 0),
                       **({"disposal": 2} if fmt == "gif" else {"lossless": False, "quality": 90}))
        return ensure_output([out])

    if animated:
        im.seek(0)
    im = ImageOps.exif_transpose(im)  # фото с телефона не будут повёрнуты

    if fmt == "jpg":
        _flatten(im).save(str(out), "JPEG", quality=ctx.config.jpeg_quality, optimize=True,
                          subsampling=0 if ctx.config.jpeg_quality >= 90 else 2,
                          **({"exif": exif} if exif else {}))
    elif fmt == "png":
        if im.mode not in ("RGB", "RGBA", "L", "LA", "P", "I;16"):
            im = im.convert("RGBA")
        im.save(str(out), "PNG", optimize=True)
    elif fmt == "webp":
        im = im if im.mode in ("RGB", "RGBA") else im.convert("RGBA")
        im.save(str(out), "WEBP", quality=90, method=6)
    elif fmt == "bmp":
        _flatten(im).save(str(out), "BMP")
    elif fmt == "gif":
        im.convert("RGBA").save(str(out), "GIF")
    elif fmt == "tiff":
        im.save(str(out), "TIFF", compression="tiff_lzw")
    elif fmt == "pdf":
        _flatten(im).save(str(out), "PDF", resolution=float(im.info.get("dpi", (150, 150))[0] or 150))
    elif fmt == "ico":
        im = im.convert("RGBA")
        side = max(im.size)
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        square.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
        sizes = [s for s in (16, 24, 32, 48, 64, 128, 256) if s <= max(side, 16)]
        square.save(str(out), "ICO", sizes=[(s, s) for s in sizes])
    else:
        raise ConversionError(f"Формат {fmt} не поддерживается")
    return ensure_output([out])


def images_to_single_pdf(srcs: list[Path], ctx: Ctx) -> list[Path]:
    """Несколько картинок → один многостраничный PDF (в порядке имён)."""
    pages = []
    for i, s in enumerate(sorted(srcs, key=lambda p: p.name.lower())):
        im, ImageOps = _load(s)
        pages.append(_flatten(ImageOps.exif_transpose(im)))
        ctx.progress((i + 1) / len(srcs) * 0.9)
    out = ctx.out_dir / f"{sorted(srcs, key=lambda p: p.name.lower())[0].stem} (объединено).pdf"
    pages[0].save(str(out), "PDF", save_all=True, append_images=pages[1:], resolution=150.0)
    return ensure_output([out])
