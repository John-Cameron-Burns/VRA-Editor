; Inno Setup script for the VRA Core 4 XML Editor's Windows installer.
;
; Build (from the repo root, after pyinstaller has produced
; dist\VRA Editor\ -- see VRA_Editor.spec):
;   "C:\Program Files\Inno Setup 7\ISCC.exe" packaging\VRA_Editor.iss
;
; Produces installer_output\VRA_Editor_Setup_<version>.exe. AppId's GUID is
; fixed and must never change across releases -- it's how Windows/Inno
; Setup recognizes "this is the same app" for upgrades and uninstall, not
; the version number.

#define MyAppName "VRA Core 4 XML Editor"
#define MyAppExeName "VRA Editor.exe"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "John Burns and Impact Data Metrics Limited"

[Setup]
AppId={{26CB7F35-0A3A-4ADE-8298-1E09DE23B13E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\VRA Editor
DefaultGroupName=VRA Editor
LicenseFile=..\LICENSE
OutputDir=..\installer_output
OutputBaseFilename=VRA_Editor_Setup_{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; The PyInstaller build itself is unsigned (see VRA_Editor.spec's own
; comments on this) -- SmartScreen will still flag it on first run,
; same as running the raw .exe directly. Nothing this script controls.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
; The whole PyInstaller COLLECT output, recursively -- VRA Editor.exe
; can't run without everything under _internal\ sitting next to it.
Source: "..\dist\VRA Editor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
