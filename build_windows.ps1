# Сборка ConvWheel для Windows: папка с .exe, portable-архив и установщик.
# Обычно запускается GitHub Actions; локально — двойным кликом по build_windows.bat.
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
Set-Location $PSScriptRoot

function Check($what) { if ($LASTEXITCODE -ne 0) { throw "$what завершилось с ошибкой ($LASTEXITCODE)" } }

if (-not $env:CI) {
    python -m venv .venv; Check "venv"
    . .\.venv\Scripts\Activate.ps1
}
python -m pip install --upgrade pip; Check "pip"
python -m pip install -r requirements.txt pyinstaller; Check "pip install"

# comtypes генерирует обёртку UI Automation при первом использовании — делаем заранее
python -c "import comtypes.client; comtypes.client.GetModule('UIAutomationCore.dll')"; Check "comtypes"

$version = (python -c "import convwheel; print(convwheel.__version__)").Trim()
python tools/make_icon.py packaging/icon.png; Check "icon"
python -c "from PIL import Image; Image.open('packaging/icon.png').save('packaging/icon.ico', sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])"; Check "ico"

foreach ($d in "build", "dist") { if (Test-Path $d) { Remove-Item $d -Recurse -Force } }

pyinstaller --noconfirm --windowed --name ConvWheel `
  --icon packaging/icon.ico `
  --collect-all pdf2docx --collect-all pymupdf --collect-all imageio_ffmpeg --collect-all py7zr `
  --hidden-import comtypes.gen.UIAutomationClient `
  --hidden-import win32timezone `
  main.py
Check "pyinstaller"

# Самопроверка собранного .exe (окно без консоли — результат пишется в файл)
$log = Join-Path $env:TEMP "convwheel_selftest.txt"
$env:CONVWHEEL_SELFTEST_LOG = $log
$p = Start-Process -FilePath "dist\ConvWheel\ConvWheel.exe" -ArgumentList "--selftest" -Wait -PassThru
if (Test-Path $log) { Get-Content $log -Encoding UTF8 }
if ($p.ExitCode -ne 0) { throw "Самопроверка не прошла (код $($p.ExitCode))" }

# Portable-версия: распаковал и запустил
Compress-Archive -Path "dist\ConvWheel" -DestinationPath "dist\ConvWheel-$version-windows-portable.zip" -Force

# Установщик
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
        Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    Write-Host "Inno Setup не найден — устанавливаю"
    choco install innosetup -y --no-progress; Check "choco"
    $iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
            Where-Object { Test-Path $_ } | Select-Object -First 1
}
$env:CW_VERSION = $version
& $iscc "packaging\convwheel.iss"; Check "Inno Setup"

Write-Host "Готово:"
Get-ChildItem dist -File | ForEach-Object { Write-Host "  $($_.Name)  ($([math]::Round($_.Length / 1MB, 1)) МБ)" }
