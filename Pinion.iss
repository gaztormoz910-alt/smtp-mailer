#ifndef AppVersion
  #define AppVersion Trim(FileRead(FileOpen("VERSION")))
#endif
#ifndef SrcDir
  #define SrcDir "dist\Pinion"
#endif
#ifndef OutDir
  #define OutDir "installer"
#endif

[Setup]
AppId={{B907B747-47DE-45F2-BDBE-693E613071A2}
AppName=Pinion
AppVersion={#AppVersion}
AppPublisher=Pinion
DefaultDirName={localappdata}\Programs\Pinion
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\Pinion.exe
UninstallDisplayName=Pinion
OutputDir={#OutDir}
OutputBaseFilename=Pinion-setup
SetupIconFile=assets\Pinion.ico
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"

[Files]
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Pinion"; Filename: "{app}\Pinion.exe"
Name: "{autodesktop}\Pinion"; Filename: "{app}\Pinion.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Pinion.exe"; Description: "Запустить Pinion"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\data"
