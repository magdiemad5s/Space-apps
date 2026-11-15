; The single downloadable EXE installs the complete offline runtime folder.
; No administrator rights, Python, Node, npm or network install is needed.
#ifndef BundleDir
  #error BundleDir must identify the tested PyInstaller ONEDIR folder.
#endif
#ifndef OutputDir
  #error OutputDir must identify the installer output folder.
#endif
#ifndef AppVersion
  #define AppVersion "0.1.2"
#endif

[Setup]
AppId={{2B11E450-13CD-48BD-9836-108C4CBA11AB}
AppName=ASTRA-SHIELD
AppVersion={#AppVersion}
AppPublisher=ASTRA-SHIELD project team
AppPublisherURL=https://github.com/magdiemad5s/Space-apps
DefaultDirName={localappdata}\Programs\ASTRA-SHIELD
DefaultGroupName=ASTRA-SHIELD
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputDir}
OutputBaseFilename=ASTRA-SHIELD-Setup-x64
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\ASTRA-SHIELD.exe
InfoBeforeFile={#BundleDir}\BUNDLE-README.txt
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ASTRA-SHIELD Demo"; Filename: "{app}\ASTRA-SHIELD.exe"; Parameters: "--seed-demo --data-dir ""{localappdata}\ASTRA-SHIELD\demo"""; WorkingDir: "{app}"
Name: "{autodesktop}\ASTRA-SHIELD Demo"; Filename: "{app}\ASTRA-SHIELD.exe"; Parameters: "--seed-demo --data-dir ""{localappdata}\ASTRA-SHIELD\demo"""; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\ASTRA-SHIELD.exe"; Parameters: "--seed-demo --data-dir ""{localappdata}\ASTRA-SHIELD\demo"""; Description: "Open ASTRA-SHIELD in your browser"; Flags: nowait postinstall skipifsilent
