; Установщик ConvWheel для Windows (Inno Setup 6).
; Собирается автоматически из build_windows.ps1; версия приходит из переменной CW_VERSION.
; Ставится в профиль пользователя — права администратора не нужны.

#define MyAppVersion GetEnv("CW_VERSION")
#if MyAppVersion == ""
  #define MyAppVersion "1.0.0"
#endif

[Setup]
AppId={{8C1B6F2E-5D3A-4B8E-9F4C-2A7E1D0B3C55}
AppName=ConvWheel
AppVersion={#MyAppVersion}
AppVerName=ConvWheel {#MyAppVersion}
AppPublisher=ConvWheel
DefaultDirName={localappdata}\Programs\ConvWheel
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=ConvWheel-Setup-{#MyAppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\ConvWheel.exe
UninstallDisplayName=ConvWheel
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "Запускать ConvWheel при входе в Windows"; GroupDescription: "Дополнительно:"
Name: "desktopicon"; Description: "Значок на рабочем столе"; GroupDescription: "Дополнительно:"; Flags: unchecked

[Files]
Source: "..\dist\ConvWheel\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\ConvWheel"; Filename: "{app}\ConvWheel.exe"
Name: "{userdesktop}\ConvWheel"; Filename: "{app}\ConvWheel.exe"; Tasks: desktopicon

[Registry]
; То же значение, что переключает пункт «Запускать при входе» в меню приложения
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "ConvWheel"; ValueData: """{app}\ConvWheel.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\ConvWheel.exe"; Description: "Запустить ConvWheel"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM ConvWheel.exe"; Flags: runhidden; RunOnceId: "StopConvWheel"
