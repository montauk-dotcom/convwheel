"""Видео и аудио через ffmpeg, с реальным прогрессом."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ..platform_utils import NO_WINDOW, find_ffmpeg
from .common import ConversionError, Ctx, ensure_output

AUDIO_ARGS = {
    "mp3": ["-vn", "-c:a", "libmp3lame", "-q:a", "2"],
    "wav": ["-vn", "-c:a", "pcm_s16le"],
    "ogg": ["-vn", "-c:a", "libvorbis", "-q:a", "5"],
    "flac": ["-vn", "-c:a", "flac"],
    "m4a": ["-vn", "-c:a", "aac", "-b:a", "192k"],
}
EVEN = "scale=trunc(iw/2)*2:trunc(ih/2)*2"   # x264 требует чётные размеры
VIDEO_ARGS = {
    "mp4": ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-vf", EVEN, "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart"],
    "mov": ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-vf", EVEN, "-c:a", "aac", "-b:a", "160k"],
    "webm": ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-row-mt", "1",
             "-c:a", "libopus", "-b:a", "128k"],
    "gif": ["-an", "-vf",
            "fps=12,scale='min(720,iw)':-2:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];"
            "[b][p]paletteuse=dither=bayer:bayer_scale=4", "-loop", "0"],
}

_DUR = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def _duration(ffmpeg: str, src: Path) -> float:
    try:
        r = subprocess.run([ffmpeg, "-hide_banner", "-i", str(src)], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=30, creationflags=NO_WINDOW)
        m = _DUR.search(r.stderr.decode(errors="replace"))
        if m:
            h, mi, s = m.groups()
            return int(h) * 3600 + int(mi) * 60 + float(s)
    except Exception:
        pass
    return 0.0


def convert_media(src: Path, ctx: Ctx, fmt: str) -> list[Path]:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise ConversionError("Не найден ffmpeg (pip install imageio-ffmpeg или установите ffmpeg)")
    args = AUDIO_ARGS.get(fmt) or VIDEO_ARGS.get(fmt)
    if args is None:
        raise ConversionError(f"Формат {fmt} не поддерживается")
    out = ctx.out(src, fmt)
    total = _duration(ffmpeg, src)
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-i", str(src), *args,
           "-progress", "pipe:1", "-nostats", str(out)]
    ctx.progress(0 if total else -1)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=NO_WINDOW, text=True, errors="replace")
    import threading
    err_tail: list[str] = []

    def _drain():  # stderr нужно вычитывать, иначе ffmpeg может зависнуть на заполненном буфере
        for line in proc.stderr:
            err_tail.append(line)
            del err_tail[:-30]
    t = threading.Thread(target=_drain, daemon=True)
    t.start()
    for line in proc.stdout:
        if total and line.startswith("out_time_us="):
            try:
                ctx.progress(min(int(line.split("=", 1)[1]) / 1e6 / total, 0.99))
            except ValueError:
                pass
    proc.wait()
    t.join(timeout=2)
    if proc.returncode != 0:
        msg = "".join(err_tail).strip().splitlines()
        raise ConversionError("ffmpeg: " + (msg[-1] if msg else f"код {proc.returncode}"))
    return ensure_output([out])
