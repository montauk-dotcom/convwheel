"""Архивы: упаковка папок/файлов в ZIP, 7Z, TAR.GZ и безопасная распаковка."""
from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path

from .common import ConversionError, Ctx, ensure_output

SKIP = {".DS_Store", "Thumbs.db", "desktop.ini"}
ARCHIVE_SUFFIXES = (".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".tar", ".zip", ".7z")


def archive_kind(p: Path) -> str | None:
    n = p.name.lower()
    for s in ARCHIVE_SUFFIXES:
        if n.endswith(s):
            return s
    return None


def archive_stem(p: Path) -> str:
    """«фото.tar.gz» → «фото»."""
    k = archive_kind(p)
    return p.name[: -len(k)] if k else p.stem


def _walk(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        for f in filenames:
            if f not in SKIP:
                files.append(Path(dirpath) / f)
    return files


def _total(files: list[Path]) -> int:
    t = 0
    for f in files:
        try:
            t += f.stat().st_size
        except OSError:
            pass
    return t or 1


# ------------------------------------------------------------------ упаковка
def to_zip(src: Path, ctx: Ctx, name: str | None = None) -> list[Path]:
    out = ctx.out_dir / f"{name or (src.name if src.is_dir() else src.stem)}.zip"
    files = _walk(src)
    total, done = _total(files), 0
    base = src.parent
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        if src.is_dir() and not files:
            z.writestr(src.name + "/", "")
        for f in files:
            z.write(f, f.relative_to(base).as_posix())
            done += f.stat().st_size
            ctx.progress(done / total)
    return ensure_output([out])


def to_7z(src: Path, ctx: Ctx, name: str | None = None) -> list[Path]:
    try:
        import py7zr
    except ImportError as e:
        raise ConversionError("Для 7Z нужен пакет py7zr") from e
    out = ctx.out_dir / f"{name or (src.name if src.is_dir() else src.stem)}.7z"
    ctx.progress(-1)
    files = _walk(src)
    total, done = _total(files), 0
    with py7zr.SevenZipFile(out, "w") as z:
        for f in files:   # по одному файлу — чтобы пропустить служебные .DS_Store/Thumbs.db
            z.write(f, arcname=f.relative_to(src.parent).as_posix())
            done += f.stat().st_size
            ctx.progress(done / total)
        if src.is_dir() and not files:
            z.mkdir(src.name)
    return ensure_output([out])


def to_targz(src: Path, ctx: Ctx, name: str | None = None) -> list[Path]:
    out = ctx.out_dir / f"{name or (src.name if src.is_dir() else src.stem)}.tar.gz"
    files = _walk(src)
    total, done = _total(files), 0

    def skip(ti: tarfile.TarInfo):
        return None if Path(ti.name).name in SKIP else ti

    with tarfile.open(out, "w:gz", compresslevel=6) as t:
        if src.is_dir():
            t.add(src, arcname=src.name, recursive=False)
        for f in files:
            t.add(f, arcname=f.relative_to(src.parent).as_posix(), filter=skip)
            done += f.stat().st_size
            ctx.progress(done / total)
    return ensure_output([out])


# ------------------------------------------------------------------ распаковка
def _safe_target(dest: Path, member: str) -> Path:
    """Защита от «zip slip»: путь внутри архива не должен выходить за папку назначения."""
    target = (dest / member).resolve()
    if dest.resolve() not in target.parents and target != dest.resolve():
        raise ConversionError(f"Небезопасный путь в архиве: {member}")
    return target


def _extract_to(src: Path, dest: Path, ctx: Ctx) -> None:
    kind = archive_kind(src)
    dest.mkdir(parents=True, exist_ok=True)
    try:
        if kind == ".zip":
            with zipfile.ZipFile(src) as z:
                infos = z.infolist()
                for i, info in enumerate(infos):
                    name = info.filename
                    if not (info.flag_bits & 0x800):   # не UTF-8 → имена из Windows (CP866)
                        try:
                            name = name.encode("cp437").decode("cp866")
                        except (UnicodeEncodeError, UnicodeDecodeError):
                            pass
                    target = _safe_target(dest, name)
                    if info.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with z.open(info) as s, open(target, "wb") as d:
                            shutil.copyfileobj(s, d)
                    ctx.progress((i + 1) / len(infos))
        elif kind == ".7z":
            import py7zr
            with py7zr.SevenZipFile(src, "r") as z:
                for n in z.getnames():
                    _safe_target(dest, n)
                ctx.progress(-1)
                z.extractall(path=dest)
        else:
            with tarfile.open(src, "r:*") as t:
                members = t.getmembers()
                for m in members:
                    _safe_target(dest, m.name)
                    if m.issym() or m.islnk():
                        _safe_target(dest, os.path.join(os.path.dirname(m.name), m.linkname))
                try:
                    t.extractall(dest, filter="data")
                except TypeError:   # Python < 3.12
                    t.extractall(dest)
    except zipfile.BadZipFile as e:
        raise ConversionError("Архив повреждён или это не ZIP") from e
    except RuntimeError as e:      # зашифрованный zip
        raise ConversionError(f"Архив защищён паролем: {e}") from e
    except ConversionError:
        raise
    except Exception as e:
        if "password" in str(e).lower():
            raise ConversionError("Архив защищён паролем") from e
        raise ConversionError(f"Не удалось распаковать: {e}") from e


def extract(src: Path, ctx: Ctx) -> list[Path]:
    """Распаковывает в папку с именем архива. Если внутри одна папка — без лишней вложенности."""
    stem = archive_stem(src)
    dest = ctx.out_dir / stem
    _extract_to(src, dest, ctx)
    items = [p for p in dest.iterdir() if p.name not in SKIP and p.name != "__MACOSX"]
    if len(items) == 1 and items[0].is_dir():
        inner = items[0]
        final = ctx.out_dir / f"__{inner.name}"
        inner.rename(final)
        shutil.rmtree(dest)
        dest = final.rename(ctx.out_dir / inner.name)
    else:
        mac = dest / "__MACOSX"
        if mac.exists():
            shutil.rmtree(mac, ignore_errors=True)
    return ensure_output([dest])


def repack(src: Path, ctx: Ctx, fmt: str) -> list[Path]:
    """Архив → другой формат архива (через временную распаковку)."""
    tmp = Path(tempfile.mkdtemp(prefix="cw_repack_"))
    try:
        sub = Ctx(tmp, lambda p: ctx.progress(-1 if p < 0 else p * 0.5), ctx.config)
        folder = extract(src, sub)[0]
        pack = Ctx(ctx.out_dir, lambda p: ctx.progress(-1 if p < 0 else 0.5 + p * 0.5), ctx.config)
        fn = {"zip": to_zip, "7z": to_7z, "tar.gz": to_targz}[fmt]
        return fn(folder, pack, name=archive_stem(src))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
