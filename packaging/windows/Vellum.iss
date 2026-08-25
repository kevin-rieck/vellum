; Inno Setup definition for the per-user Vellum distribution.
; The release workflow supplies /DMyAppVersion from the project version.
#ifndef MyAppVersion
#define MyAppVersion "0.1.0"
#endif

#define MyAppName "Vellum"
#define MyAppPublisher "Vellum contributors"
#define MyAppExeName "vellum.exe"

[Setup]
AppId={{C5BDF2E1-3CE8-47A1-91C6-9D0E6421BB9D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Vellum\app
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist\installer
OutputBaseFilename=Vellum-{#MyAppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=..\..\LICENSE

[Files]
Source: "..\..\dist\vellum\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Vellum"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Vellum"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Vellum"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Settings, verified engines, and local diagnostics under %LOCALAPPDATA%\Vellum
; are intentionally retained so uninstall does not destroy user data.
Type: filesandordirs; Name: "{app}"
