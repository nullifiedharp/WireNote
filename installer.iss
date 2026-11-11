; WireNote — Inno Setup script
; Built automatically by build.bat (Inno Setup 6.3+)

#define AppName "WireNote"
#define AppVersion "1.0.0"
#define AppExe "WireNote.exe"
#define Verb "WireNote.Annotate"

[Setup]
AppId={{8F3C2A51-6E4B-4D7A-9C21-5B0E7A3D9F14}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=NullHarp
AppPublisherURL=https://github.com/nullifiedharp/WireNote
AppSupportURL=https://github.com/nullifiedharp/WireNote/issues
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=installer
OutputBaseFilename=WireNote-Setup-{#AppVersion}
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
LicenseFile=LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Tasks]
Name: "contextmenu"; Description: "Add ""Annotate"" to the right-click menu for images"; GroupDescription: "Integration:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "dist\WireNote\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Right-click > Annotate on every image type Windows knows (png, jpg, bmp, gif, tif, webp...)
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\image\shell\{#Verb}"; ValueType: string; ValueName: ""; ValueData: "Annotate"; Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\image\shell\{#Verb}"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExe}"",0"; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\image\shell\{#Verb}\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: contextmenu
; "Open with" entry
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
