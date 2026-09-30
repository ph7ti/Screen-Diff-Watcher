; Instalador Windows do Screen Diff Watcher (Inno Setup 6).
;
; Build: ISCC.exe /DVersion=0.2.0 /O<dist>\installers screen-diff-watcher.iss
; (quem chama e o scripts/build_release.py --windows)

#ifndef Version
  #define Version "0.0.0"
#endif

#define AppName "Screen Diff Watcher"
#define AppPublisher "ph7ti"
#define AppURL "https://github.com/ph7ti/Screen-Diff-Watcher"

[Setup]
AppId=ph7ti.screendiffwatcher
AppName={#AppName}
AppVersion={#Version}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
DefaultDirName={autopf}\Screen Diff Watcher
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\screen-watch-gui.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Per-machine por causa do Tesseract instalado por maquina.
PrivilegesRequired=admin
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
SetupIconFile=..\icons\ScreenDiffWatcher.ico
OutputDir=..\..\dist\installers
OutputBaseFilename=screen-diff-watcher_{#Version}_windows_x64_setup

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Iniciar com o Windows"; GroupDescription: "Opcoes:"; Flags: unchecked

[Files]
Source: "..\..\dist\screen-watch\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "install-tesseract.ps1"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "tesseract.json"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "..\icons\ScreenDiffWatcher.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\screen-watch-gui.exe"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\screen-watch-gui.exe"; Tasks: desktopicon
Name: "{commonstartup}\{#AppName}"; Filename: "{app}\screen-watch-gui.exe"; Tasks: autostart

[Run]
; `runasoriginaluser` evita abrir a GUI elevada (o app-data seria o do admin).
Filename: "{app}\screen-watch-gui.exe"; Description: "Abrir o {#AppName}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[Code]
function TesseractPresent(): Boolean;
var
  Candidates: array[0..2] of String;
  I: Integer;
begin
  Candidates[0] := ExpandConstant('{commonpf}\Tesseract-OCR\tesseract.exe');
  Candidates[1] := ExpandConstant('{commonpf32}\Tesseract-OCR\tesseract.exe');
  Candidates[2] := ExpandConstant('{localappdata}\Programs\Tesseract-OCR\tesseract.exe');
  for I := 0 to 2 do
  begin
    if FileExists(Candidates[I]) then
    begin
      Result := True;
      Exit;
    end;
  end;
  Result := False;
end;

function RunTesseractHelper(): Integer;
var
  Params: String;
  ResultCode: Integer;
begin
  Params :=
    '-ExecutionPolicy Bypass -NoProfile -File "' +
    ExpandConstant('{app}\tools\install-tesseract.ps1') +
    '" -ConfigPath "' +
    ExpandConstant('{app}\tools\tesseract.json') + '"';
  if not Exec('powershell.exe', Params, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    ResultCode := 1;
  end;
  Result := ResultCode;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
  Message: String;
begin
  if CurStep <> ssPostInstall then
  begin
    Exit;
  end;
  if TesseractPresent() then
  begin
    Exit;
  end;
  Code := RunTesseractHelper();
  if Code = 0 then
  begin
    Exit;
  end;
  case Code of
    2: Message := 'Nao foi possivel baixar o Tesseract (verifique a conexao).';
    3: Message := 'O download do Tesseract falhou na verificacao de integridade (SHA256).';
  else
    Message := 'A instalacao automatica do Tesseract falhou.';
  end;
  MsgBox(
    Message + #13#10#13#10 +
    'O app funciona nos modos light/default. O modo advanced (OCR) exige o Tesseract: ' +
    'instale manualmente de https://github.com/UB-Mannheim/tesseract/wiki ' +
    '(com os traineddata por e eng).',
    mbInformation, MB_OK);
end;
