#define MyAppName "Jarvis AI 2.0"
#ifndef MyAppVersion
#define MyAppVersion "20.2.0"
#endif

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppId={{C2D346A5-5E50-4D5E-9D3D-6E6579D0A255}
DefaultDirName={autopf}\Jarvis AI 2.0
DefaultGroupName=Jarvis AI 2.0
UninstallDisplayIcon={app}\jarvis_ai_2.exe
Compression=lzma2/ultra
SolidCompression=yes
OutputDir=.\dist
OutputBaseFilename=JarvisAI2_Setup
PrivilegesRequired=admin
SetupIconFile=assets\icon.ico
UsePreviousAppDir=no
UsePreviousGroup=no
DisableReadyPage=yes
DisableStartupPrompt=yes

[Files]
Source: "dist\jarvis_ai_2.exe"; DestDir: "{app}"; DestName: "jarvis_ai_2.exe"; Flags: ignoreversion
Source: "updates.json"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Jarvis AI 2.0"; Filename: "{app}\jarvis_ai_2.exe"
Name: "{commondesktop}\Jarvis AI 2.0"; Filename: "{app}\jarvis_ai_2.exe"

[Run]
Filename: "{app}\jarvis_ai_2.exe"; Description: "Launch Jarvis AI 2.0"; Flags: postinstall nowait skipifsilent

[InstallDelete]
Type: files; Name: "{app}\*.pyc"
Type: files; Name: "{app}\__pycache__\*"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := true;
  Log('Jarvis AI 2.0 Setup ' + '{#MyAppVersion}' + ' starting...');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    Log('Installation completed. App version: ' + '{#MyAppVersion}');
  end;
end;
