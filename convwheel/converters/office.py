"""Офисные документы: Microsoft Office (COM, только Windows) или LibreOffice (везде).

Почему так: для DOCX/XLSX/PPTX → PDF самое точное отображение даёт сам MS Office.
Если его нет (или это macOS), используется LibreOffice в headless-режиме с отдельным
профилем, чтобы не конфликтовать с уже открытым LibreOffice пользователя.
"""
from __future__ import annotations

import shutil
import tempfile
import threading
from pathlib import Path

from ..platform_utils import IS_WIN, config_dir, find_soffice, has_ms_office, run
from .common import ConversionError, Ctx, ensure_output, read_text_smart

WRITER = {"docx", "doc", "odt", "rtf", "txt", "md", "html", "htm", "wps", "dotx"}
CALC = {"xlsx", "xls", "ods", "csv", "xlsm"}
IMPRESS = {"pptx", "ppt", "odp", "pps", "ppsx"}

# Фильтры экспорта LibreOffice: (семейство, целевое расширение) -> строка для --convert-to
LO_FILTERS = {
    ("writer", "pdf"): "pdf:writer_pdf_Export",
    ("writer", "docx"): 'docx:MS Word 2007 XML',
    ("writer", "doc"): "doc:MS Word 97",
    ("writer", "odt"): "odt:writer8",
    ("writer", "rtf"): "rtf:Rich Text Format",
    ("writer", "html"): "html:HTML (StarWriter)",
    ("writer", "txt"): "txt:Text (encoded):UTF8",
    ("calc", "pdf"): "pdf:calc_pdf_Export",
    ("calc", "xlsx"): "xlsx:Calc MS Excel 2007 XML",
    ("calc", "ods"): "ods:calc8",
    # 44=',', 34='"', 76=UTF-8, 1=первая строка; последний -1 = все листы (LO ≥ 7.2)
    ("calc", "csv"): "csv:Text - txt - csv (StarCalc):44,34,76,1,,0,false,true,false,false,false,-1",
    ("impress", "pdf"): "pdf:impress_pdf_Export",
    ("impress", "pptx"): "pptx:Impress MS PowerPoint 2007 XML",
    ("impress", "odp"): "odp:impress8",
}

# LibreOffice не любит параллельные запуски с одним профилем
_lo_lock = threading.Lock()


def family(ext: str) -> str:
    if ext in CALC:
        return "calc"
    if ext in IMPRESS:
        return "impress"
    return "writer"


# ---------------------------------------------------------------- LibreOffice
def libreoffice_convert(src: Path, target: str, ctx: Ctx) -> list[Path]:
    soffice = find_soffice()
    if not soffice:
        raise ConversionError(
            "Не найден LibreOffice. Установите его (libreoffice.org) — он нужен для офисных форматов.")
    src_ext = src.suffix.lower().lstrip(".")
    fam = family(src_ext)
    flt = LO_FILTERS.get((fam, target))
    if not flt:
        raise ConversionError(f"LibreOffice не умеет {src_ext.upper()} → {target.upper()}")

    work_src = src
    tmp_in = None
    infilter = None
    if src_ext in {"txt", "md", "csv"}:
        # Нормализуем кодировку в UTF-8, иначе кириллица в CP1251 превратится в кракозябры
        tmp_in = Path(tempfile.mkdtemp(prefix="cw_in_"))
        if src_ext == "md":
            from .text import markdown_to_html
            work_src = tmp_in / f"{src.stem}.html"
            work_src.write_text(markdown_to_html(read_text_smart(src), src.stem), encoding="utf-8")
            infilter = "HTML (StarWriter)"
        else:
            work_src = tmp_in / src.name
            content = read_text_smart(src)
            work_src.write_text(content, encoding="utf-8")
            if src_ext == "csv":
                import csv
                try:  # в русской локали Excel пишет CSV через «;» — определяем разделитель
                    delim = csv.Sniffer().sniff(content[:4096], delimiters=",;\t|").delimiter
                except csv.Error:
                    delim = ","
                infilter = f"Text - txt - csv (StarCalc):{ord(delim)},34,76,1"
            else:
                infilter = "Text (encoded):UTF8"
    elif src_ext in {"html", "htm"}:
        infilter = "HTML (StarWriter)"

    profile = (config_dir() / "lo_profile").resolve()
    cmd = [
        soffice,
        f"-env:UserInstallation={profile.as_uri()}",
        "--headless", "--invisible", "--norestore", "--nologo", "--nodefault", "--nolockcheck",
    ]
    if infilter:
        cmd.append(f"--infilter={infilter}")
    cmd += ["--convert-to", flt, "--outdir", str(ctx.out_dir), str(work_src)]

    ctx.progress(-1)
    try:
        with _lo_lock:
            res = run(cmd, timeout=300)
    except Exception as e:  # timeout и т.п.
        raise ConversionError(f"LibreOffice не ответил: {e}") from e
    finally:
        if tmp_in:
            shutil.rmtree(tmp_in, ignore_errors=True)

    outs = sorted(ctx.out_dir.glob(f"{work_src.stem}*.{target}"))
    if not outs:
        err = (res.stderr or b"").decode(errors="replace").strip()
        raise ConversionError("LibreOffice не смог сконвертировать файл" + (f": {err[-300:]}" if err else ""))
    # имя результата должно совпадать с исходником (а не с временной копией)
    return ensure_output(outs)


# ---------------------------------------------------------------- MS Office (COM)
WORD_FORMATS = {"pdf": 17, "docx": 16, "doc": 0, "rtf": 6, "odt": 23, "html": 10, "txt": 7}
EXCEL_FORMATS = {"xlsx": 51, "ods": 60}
PPT_FORMATS = {"pdf": 32, "pptx": 24, "odp": 35}


def _com_init():
    import pythoncom
    pythoncom.CoInitialize()
    return pythoncom


def msoffice_convert(src: Path, target: str, ctx: Ctx) -> list[Path]:
    import win32com.client  # noqa: F401  (pywin32)
    pythoncom = _com_init()
    ext = src.suffix.lower().lstrip(".")
    fam = family(ext)
    out = ctx.out(src, target)
    ctx.progress(-1)
    try:
        if fam == "writer":
            app = win32com.client.DispatchEx("Word.Application")
            app.Visible = False
            app.DisplayAlerts = 0
            try:
                doc = app.Documents.Open(str(src), ConfirmConversions=False, ReadOnly=True,
                                         AddToRecentFiles=False, Visible=False)
                if target == "txt":
                    doc.SaveAs2(str(out), FileFormat=7, Encoding=65001)  # UTF-8
                else:
                    doc.SaveAs2(str(out), FileFormat=WORD_FORMATS[target])
                doc.Close(False)
            finally:
                app.Quit()
        elif fam == "calc":
            app = win32com.client.DispatchEx("Excel.Application")
            app.Visible = False
            app.DisplayAlerts = False
            try:
                wb = app.Workbooks.Open(str(src), ReadOnly=True, UpdateLinks=0)
                if target == "pdf":
                    wb.ExportAsFixedFormat(0, str(out))
                else:
                    wb.SaveAs(str(out), FileFormat=EXCEL_FORMATS[target])
                wb.Close(False)
            finally:
                app.Quit()
        else:
            app = win32com.client.DispatchEx("PowerPoint.Application")
            try:
                pres = app.Presentations.Open(str(src), ReadOnly=True, WithWindow=False)
                pres.SaveAs(str(out), PPT_FORMATS[target])
                pres.Close()
            finally:
                app.Quit()
    except ConversionError:
        raise
    except Exception as e:
        raise ConversionError(f"Microsoft Office: {e}") from e
    finally:
        pythoncom.CoUninitialize()
    return ensure_output([out])


def _ms_supports(fam: str, target: str) -> bool:
    table = {"writer": WORD_FORMATS, "calc": {**EXCEL_FORMATS, "pdf": 0}, "impress": PPT_FORMATS}[fam]
    app = {"writer": "Word", "calc": "Excel", "impress": "PowerPoint"}[fam]
    return target in table and has_ms_office(app)


def office_convert(src: Path, target: str, ctx: Ctx) -> list[Path]:
    """Выбирает лучший доступный движок и конвертирует."""
    ext = src.suffix.lower().lstrip(".")
    fam = family(ext)
    engine = ctx.config.office_engine
    want_ms = IS_WIN and engine in ("auto", "msoffice") and ext not in {"md", "txt", "csv"}
    if want_ms and _ms_supports(fam, target):
        try:
            return msoffice_convert(src, target, ctx)
        except ConversionError:
            if engine == "msoffice" or not find_soffice():
                raise
            # иначе пробуем LibreOffice как запасной вариант
    return libreoffice_convert(src, target, ctx)
