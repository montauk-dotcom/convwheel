@echo off
chcp 65001 >nul
REM Сборка ConvWheel.exe (Windows). Запускать из папки проекта.
setlocal
python -m venv .venv || goto :err
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller || goto :err

REM comtypes генерирует обёртку UI Automation при первом использовании —
REM делаем это заранее, чтобы она попала в сборку.
python -c "import comtypes.client; comtypes.client.GetModule('UIAutomationCore.dll')" || goto :err

pyinstaller --noconfirm --windowed --name ConvWheel ^
  --collect-all pdf2docx --collect-all pymupdf --collect-all imageio_ffmpeg ^
  --hidden-import comtypes.gen.UIAutomationClient ^
  --hidden-import pynput.mouse._win32 --hidden-import pynput.keyboard._win32 ^
  main.py || goto :err

echo.
echo Готово: dist\ConvWheel\ConvWheel.exe
exit /b 0
:err
echo Ошибка сборки
exit /b 1
