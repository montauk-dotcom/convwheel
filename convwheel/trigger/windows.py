"""Windows: какой файл или папка под курсором в Проводнике или на рабочем столе.

Используем три источника, от точного к запасному:
  1. UI Automation — имя элемента списка под курсором (работает в любой колонке
     «Таблицы», в любом виде значков, и не зависит от того, изменилось ли выделение).
  2. Shell.Application (COM) — сопоставляем это имя с файлами открытой папки и получаем
     настоящий путь (имя на экране может быть без расширения).
  3. FocusedItem/SelectedItems — если UIA ничего не дал.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
from pathlib import Path

from ..config import CONFIG

user32 = ctypes.windll.user32
user32.WindowFromPoint.argtypes = [wt.POINT]
user32.WindowFromPoint.restype = wt.HWND
user32.GetAncestor.argtypes = [wt.HWND, ctypes.c_uint]
user32.GetAncestor.restype = wt.HWND
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]

EXPLORER = {"CabinetWClass", "ExploreWClass"}
DESKTOP = {"Progman", "WorkerW"}
GA_ROOT = 2
UIA_ListItemControlTypeId = 50007
UIA_DataItemControlTypeId = 50029


def shift_down() -> bool:
    return bool(user32.GetAsyncKeyState(0x10) & 0x8000)


def cursor_pos(x, y):
    """Физические координаты курсора в момент клика (надёжнее при масштабе 125–200%)."""
    pt = wt.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _class(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def files_under_click(x: int, y: int) -> list[str]:
    hwnd = user32.WindowFromPoint(wt.POINT(int(x), int(y)))
    if not hwnd:
        return []
    root = user32.GetAncestor(hwnd, GA_ROOT)
    cls = _class(root)
    if cls not in EXPLORER and cls not in DESKTOP:
        return []

    import pythoncom
    pythoncom.CoInitialize()
    try:
        name = _uia_item_name(x, y)
        if cls in EXPLORER:
            views = _explorer_views(int(root))
        else:
            v = _desktop_view()
            views = [v] if v is not None else []
        for doc in views:
            path = _match(doc, name)
            if path:
                return _with_selection(doc, path)
        if cls in DESKTOP and name:   # запасной путь для рабочего стола
            p = _desktop_fallback(name)
            return [p] if p else []
        return []
    finally:
        pythoncom.CoUninitialize()


# ------------------------------------------------------------------ UI Automation
def _uia_item_name(x: int, y: int) -> str | None:
    try:
        import comtypes.client
        try:
            from comtypes.gen.UIAutomationClient import CUIAutomation, IUIAutomation, tagPOINT
        except ImportError:
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen.UIAutomationClient import CUIAutomation, IUIAutomation, tagPOINT
        uia = comtypes.client.CreateObject(CUIAutomation, interface=IUIAutomation)
        el = uia.ElementFromPoint(tagPOINT(int(x), int(y)))
        walker = uia.ControlViewWalker
        for _ in range(4):          # поднимаемся от текста/ячейки к самому элементу списка
            if el is None:
                break
            if el.CurrentControlType in (UIA_ListItemControlTypeId, UIA_DataItemControlTypeId):
                return el.CurrentName or None
            el = walker.GetParentElement(el)
    except Exception:
        pass
    return None


# ------------------------------------------------------------------ Shell COM
def _explorer_views(root_hwnd: int) -> list:
    import win32com.client
    docs = []
    for w in win32com.client.Dispatch("Shell.Application").Windows():
        try:
            if int(w.HWND) == root_hwnd:
                docs.append(w.Document)      # в Windows 11 у окна может быть несколько вкладок
        except Exception:
            continue
    return docs


def _desktop_view():
    """Представление рабочего стола через IShellWindows::FindWindowSW(SWC_DESKTOP)."""
    try:
        import pythoncom
        import win32com.client
        from win32com.client import VARIANT
        sw = win32com.client.Dispatch("Shell.Application").Windows()
        hwnd = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        loc = VARIANT(pythoncom.VT_I4, 0)                 # CSIDL_DESKTOP
        empty = VARIANT(pythoncom.VT_EMPTY, None)
        disp = sw.FindWindowSW(loc, empty, 8, hwnd, 1)    # SWC_DESKTOP, SWFO_NEEDDISPATCH
        return win32com.client.Dispatch(disp).Document
    except Exception:
        return None


def _is_file(item) -> bool:
    """Настоящий файл или папка на диске (не «Этот компьютер», не корень диска).
    ZIP-архивы Проводник считает папками — os.path.isfile их всё равно отличит."""
    try:
        p = item.Path
        if os.path.isfile(p):
            return True
        return os.path.isdir(p) and Path(p).parent != Path(p)
    except Exception:
        return False


def _match(doc, name: str | None) -> str | None:
    try:
        folder = doc.Folder
    except Exception:
        return None
    if name:
        try:
            fi = doc.FocusedItem
            if fi is not None and fi.Name == name and _is_file(fi):
                return fi.Path
        except Exception:
            pass
        try:
            it = folder.ParseName(name)   # сработает, если расширения показываются
            if it is not None and _is_file(it):
                return it.Path
        except Exception:
            pass
        try:
            items = folder.Items()
            for i in range(min(items.Count, 20000)):
                it = items.Item(i)
                if it.Name == name and _is_file(it):
                    return it.Path
        except Exception:
            pass
        return None
    # UIA не сработал: левый клик всё равно делает файл «в фокусе»
    if CONFIG.trigger_button == "left":
        try:
            fi = doc.FocusedItem
            if fi is not None and _is_file(fi):
                return fi.Path
        except Exception:
            pass
    return None


def _with_selection(doc, path: str) -> list[str]:
    """Shift+средняя/правая кнопка не меняет выделение — тогда берём все выделенные файлы,
    если кликнули по одному из них. Shift+левая кнопка выделяет диапазон, поэтому там — один файл."""
    if CONFIG.trigger_button == "left":
        return [path]
    try:
        sel = [it.Path for it in doc.SelectedItems() if _is_file(it)]
        if path in sel and len(sel) > 1:
            return sel
    except Exception:
        pass
    return [path]


def _desktop_fallback(name: str) -> str | None:
    dirs = [Path.home() / "Desktop", Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop"]
    try:
        import win32com.client
        dirs.insert(0, Path(win32com.client.Dispatch("WScript.Shell").SpecialFolders("Desktop")))
    except Exception:
        pass
    exact, by_stem = [], []
    for d in dirs:
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if f.is_file() or f.is_dir():
                if f.name == name:
                    exact.append(f)
                elif f.stem == name:
                    by_stem.append(f)
    if exact:
        return str(exact[0])
    if len(by_stem) == 1:   # расширения скрыты — берём, только если совпадение однозначно
        return str(by_stem[0])
    return None
