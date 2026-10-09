[Setup]
AppId={{829BC578-9CD2-43C1-BA87-80367759A28F}
AppName=Kotoba
AppVersion=1.0.0
AppPublisher=ppoc164
AppPublisherURL=https://github.com/ppoc164/kotoba-windows
DefaultDirName={localappdata}\Programs\Kotoba
DefaultGroupName=Kotoba
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=release
OutputBaseFilename=Kotoba-1.0.0-windows-x64-setup
SetupIconFile=assets\kotoba.ico
UninstallDisplayIcon={app}\Kotoba.exe
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "dist-v6\Kotoba\*"; DestDir: "{app}"; Excludes: "data\*"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Kotoba"; Filename: "{app}\Kotoba.exe"
Name: "{userdesktop}\Kotoba"; Filename: "{app}\Kotoba.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Kotoba.exe"; Description: "Launch Kotoba"; Flags: nowait postinstall skipifsilent
