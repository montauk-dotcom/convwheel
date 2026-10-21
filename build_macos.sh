#!/usr/bin/env bash
# Сборка ConvWheel.app и ConvWheel-<версия>-<arch>.dmg (macOS).
# Обычно её запускает GitHub Actions (.github/workflows/build-macos.yml), но можно и вручную:
#   ./build_macos.sh
#
# Необязательная подпись Apple Developer ID (тогда не будет предупреждения Gatekeeper):
#   MACOS_SIGN_IDENTITY="Developer ID Application: Имя (TEAMID)"
#   MACOS_NOTARY_APPLE_ID, MACOS_NOTARY_PASSWORD (пароль приложения), MACOS_NOTARY_TEAM_ID
set -euo pipefail
cd "$(dirname "$0")"

if [[ -z "${CI:-}" ]]; then          # локально — отдельное окружение; в CI Python уже настроен
  python3 -m venv .venv
  source .venv/bin/activate
fi
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt pyinstaller

VERSION=$(python3 -c "import convwheel; print(convwheel.__version__)")
ARCH=$(uname -m)                     # arm64 (M1–M4) или x86_64 (Intel)
APP="dist/ConvWheel.app"
DMG="dist/ConvWheel-${VERSION}-${ARCH}.dmg"

python3 tools/make_icon.py packaging/icon.png

rm -rf build dist
pyinstaller --noconfirm --windowed --name ConvWheel \
  --icon packaging/icon.png \
  --osx-bundle-identifier com.convwheel.agent \
  --collect-all pdf2docx --collect-all pymupdf --collect-all imageio_ffmpeg \
  --hidden-import pynput.mouse._darwin --hidden-import pynput.keyboard._darwin \
  --hidden-import ApplicationServices --hidden-import Quartz --hidden-import AppKit \
  main.py

PLIST="$APP/Contents/Info.plist"
pb() { /usr/libexec/PlistBuddy -c "Delete :$1" "$PLIST" 2>/dev/null || true
       /usr/libexec/PlistBuddy -c "Add :$1 $2 $3" "$PLIST"; }
pb LSUIElement bool true                       # без значка в Dock — только в строке меню
pb CFBundleShortVersionString string "$VERSION"
pb CFBundleVersion string "$VERSION"
pb LSMinimumSystemVersion string "11.0"
pb NSAppleEventsUsageDescription string "ConvWheel узнаёт у Finder, по какому файлу вы кликнули, чтобы предложить варианты конвертации."

# ---- подпись
if [[ -n "${MACOS_SIGN_IDENTITY:-}" ]]; then
  echo "Подпись: $MACOS_SIGN_IDENTITY"
  codesign --force --deep --timestamp --options runtime \
    --entitlements packaging/entitlements.plist \
    --sign "$MACOS_SIGN_IDENTITY" "$APP"
else
  echo "Подпись ad-hoc (без сертификата Apple)"
  codesign --force --deep --sign - --entitlements packaging/entitlements.plist "$APP"
fi
codesign --verify --deep --strict "$APP"

# ---- DMG: окно с приложением и ярлыком «Программы» — просто перетащить
STAGE=$(mktemp -d)
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Программы"
# hdiutil на CI-машинах иногда отвечает «Resource busy» — пробуем несколько раз
for i in 1 2 3 4 5; do
  hdiutil create -volname "ConvWheel" -srcfolder "$STAGE" -fs HFS+ -format UDZO -ov "$DMG" && break
  echo "hdiutil: попытка $i не удалась, повтор…"; sleep 5
done
rm -rf "$STAGE"
[[ -f "$DMG" ]] || { echo "DMG не создан"; exit 1; }

if [[ -n "${MACOS_SIGN_IDENTITY:-}" ]]; then
  codesign --force --timestamp --sign "$MACOS_SIGN_IDENTITY" "$DMG"
  if [[ -n "${MACOS_NOTARY_APPLE_ID:-}" ]]; then
    echo "Нотаризация…"
    xcrun notarytool submit "$DMG" --wait \
      --apple-id "$MACOS_NOTARY_APPLE_ID" --password "$MACOS_NOTARY_PASSWORD" \
      --team-id "$MACOS_NOTARY_TEAM_ID"
    xcrun stapler staple "$DMG"
  fi
fi

# ---- быстрая самопроверка: приложение запускается и импортирует всё нужное
"$APP/Contents/MacOS/ConvWheel" --selftest

echo "Готово: $DMG"
