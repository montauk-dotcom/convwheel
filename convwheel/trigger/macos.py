"""macOS: выделенные файлы в Finder (включая рабочий стол — это тоже Finder).

Требуются разрешения (система спросит при первом запуске):
  • Универсальный доступ (Accessibility) и Мониторинг ввода — для глобального клика;
  • Автоматизация → Finder — чтобы спросить у Finder выделение.
"""
from __future__ import annotations

import os
import subprocess

SCRIPT = '''
tell application "Finder"
    set out to ""
    repeat with i in (get selection)
        try
            set out to out & POSIX path of (i as alias) & linefeed
        end try
    end repeat
    return out
end tell
'''


def shift_down() -> bool:
    try:
        import Quartz
        flags = Quartz.CGEventSourceFlagsState(Quartz.kCGEventSourceStateCombinedSessionState)
        return bool(flags & Quartz.kCGEventFlagMaskShift)
    except Exception:
        return False


def cursor_pos(x, y):
    return x, y


def _finder_frontmost() -> bool:
    try:
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return app is not None and app.bundleIdentifier() == "com.apple.finder"
    except Exception:
        r = subprocess.run(["osascript", "-e",
                            'tell application "System Events" to get bundle identifier of first process whose frontmost is true'],
                           capture_output=True, text=True, timeout=3)
        return r.stdout.strip() == "com.apple.finder"


def files_under_click(x, y) -> list[str]:
    if not _finder_frontmost():
        return []
    r = subprocess.run(["osascript", "-e", SCRIPT], capture_output=True, text=True, timeout=5)
    paths = [p.rstrip("/") or "/" for p in r.stdout.splitlines() if p]
    # файлы и папки (кроме корня и дисков в /Volumes)
    return [p for p in paths
            if os.path.isfile(p) or (os.path.isdir(p) and p != "/" and os.path.dirname(p) != "/Volumes")]
