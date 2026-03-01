; Inno Setup script (build CPU/GPU installers from the same script)

#ifndef Variant
  #define Variant "CPU"
#endif

#define VariantLower Lowercase(Variant)

#define AppName "GIF Background Removal"
#define AppVersion "0.1.0"
#define AppExeName "gif-background-removal.exe"

; dist output produced by PyInstaller commands below:
#define SourceDir "..\..\dist\" + VariantLower + "\gif-background-removal"

[Setup]
AppId={{8B4B9E2A-3C3E-4E78-9C6C-6A8A9B7B6D11}
AppName={#AppName} ({#Variant})
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=Output
OutputBaseFilename={#AppName}-{#Variant}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName} ({#Variant})"; Filename: "{app}\{#AppExeName}"
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent