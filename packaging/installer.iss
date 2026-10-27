; Inno Setup script for the Apex Commentator Windows installer.
; Built by CI:  ISCC /DAppVersion=1.2.3 packaging\installer.iss
; Expects the PyInstaller output in dist\ApexCommentator.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8D3B6C1E-4F2A-4E57-9C8B-5A1F0E7D2C44}
AppName=Apex Commentator
AppVersion={#AppVersion}
AppVerName=Apex Commentator {#AppVersion}
AppPublisher=ShamzOut2
AppPublisherURL=https://github.com/ShamzOut2/Apex_Commentator
AppSupportURL=https://github.com/ShamzOut2/Apex_Commentator/issues
AppUpdatesURL=https://github.com/ShamzOut2/Apex_Commentator/releases
; Per-user install (no admin prompt), so in-app updates run silently.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\Apex Commentator
DefaultGroupName=Apex Commentator
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\ApexCommentator.exe
SetupIconFile=..\assets\icon.ico
OutputDir=..\dist
OutputBaseFilename=ApexCommentator-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Replace the whole program folder on update so no stale files are left.
Source: "..\dist\ApexCommentator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\Apex Commentator"; Filename: "{app}\ApexCommentator.exe"
Name: "{group}\Apex Commentator (demo mode)"; Filename: "{app}\ApexCommentator.exe"; Parameters: "--mock"; Comment: "Try it with a simulated race, no iRacing needed"
Name: "{group}\Uninstall Apex Commentator"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Apex Commentator"; Filename: "{app}\ApexCommentator.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ApexCommentator.exe"; Description: "{cm:LaunchProgram,Apex Commentator}"; Flags: nowait postinstall skipifsilent
; In-app updates run the installer silently with /RELAUNCH: reopen the app afterwards.
Filename: "{app}\ApexCommentator.exe"; Flags: nowait; Check: ShouldRelaunch

[Code]
function ShouldRelaunch: Boolean;
begin
  Result := Pos('/RELAUNCH', UpperCase(GetCmdTail)) > 0;
end;

// An in-app update starts this installer and then quits: give the app a moment
// to close before files are replaced.
function InitializeSetup: Boolean;
var
  Waited: Integer;
begin
  Waited := 0;
  while CheckForMutexes('ApexCommentatorRunning') and (Waited < 30) do
  begin
    Sleep(500);
    Waited := Waited + 1;
  end;
  if CheckForMutexes('ApexCommentatorRunning') then
  begin
    if not WizardSilent then
      MsgBox('Please close Apex Commentator, then run the installer again.', mbError, MB_OK);
    Result := False;
  end
  else
    Result := True;
end;
