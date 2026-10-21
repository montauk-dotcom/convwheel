@echo off
chcp 65001 >nul
REM Сборка ConvWheel для Windows. Двойной клик или запуск из папки проекта.
where pwsh >nul 2>nul && (pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1") || (powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1")
pause
