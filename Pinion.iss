; Установщик Pinion (Inno Setup 6). Ставит собранную onedir-сборку в профиль
; пользователя — без прав администратора и без UAC.
;
; Почему так (обосновано паспортом проекта):
;  - Приложение ПИШЕТ рядом с .exe: logs\, data\ (пресеты, queue-state.json). В
;    Program Files без админ-прав запись запрещена и всё ломается МОЛЧА, поэтому
;    ставим в {localappdata}\Programs\Pinion (туда писать можно).
;  - Имя файла установщика БЕЗ версии: иначе постоянная ссылка releases/latest
;    ломалась бы у всех при каждом релизе.
;  - Ни одного абсолютного пути: скрипт собирается и локально, и на GitHub CI.
;    Значения приходят через ISCC /D..., иначе — дефолты ниже.

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
; AppId менять НЕЛЬЗЯ: по нему обновление находит прошлую установку.
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
; Вся onedir-сборка: exe + _internal со всеми библиотеками и ресурсами.
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Pinion"; Filename: "{app}\Pinion.exe"
Name: "{autodesktop}\Pinion"; Filename: "{app}\Pinion.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Pinion.exe"; Description: "Запустить Pinion"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Файлы, которые приложение создаёт УЖЕ ПОСЛЕ установки, инсталлятору неизвестны —
; удаляем их явно, иначе после деинсталляции останется мусор в профиле.
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\data"
