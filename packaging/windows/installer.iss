#ifndef AppVersion
  #error AppVersion must be supplied by the build script
#endif
#ifndef BundleDir
  #error BundleDir must be supplied by the build script
#endif
#ifndef OutputDir
  #error OutputDir must be supplied by the build script
#endif
[Setup]
AppId={{22D5F89B-1F42-4D31-9A95-11752830ECF0}
AppName=Antibody Research Workbench
AppVersion={#AppVersion}
AppVerName=Antibody Research Workbench {#AppVersion} (Release Candidate)
AppPublisher=Antibody Risk Assessment contributors
AppPublisherURL=https://github.com/jie4578/antibody-risk-assessment
DefaultDirName={localappdata}\Programs\AntibodyResearchWorkbench
DefaultGroupName=Antibody Research Workbench
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=AntibodyResearchWorkbench-{#AppVersion}-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\AntibodyResearchWorkbench.exe
LicenseFile={#BundleDir}\_internal\LICENSE
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\抗体科研工作台（候选版）"; Filename: "{app}\AntibodyResearchWorkbench.exe"; WorkingDir: "{app}"
Name: "{group}\卸载抗体科研工作台"; Filename: "{uninstallexe}"
Name: "{autodesktop}\抗体科研工作台（候选版）"; Filename: "{app}\AntibodyResearchWorkbench.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\AntibodyResearchWorkbench.exe"; Description: "启动抗体科研工作台"; Flags: nowait postinstall skipifsilent

; User configuration/cache/model directories are intentionally never deleted.
