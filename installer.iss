; Telegram Username Scanner 2.0 — установщик с обновлением без потери сессий
; Компилятор: Inno Setup 6.x (https://jrsoftware.org/isinfo.php)
; Что делает:
;  1. По умолчанию предлагает ТУ ЖЕ папку, куда ставили в прошлый раз (запоминает в реестре).
;  2. Пользователь может выбрать ЛЮБУЮ папку — например, ту, где уже лежат sessions/ и accounts.json.
;  3. При обновлении меняет ТОЛЬКО exe, сессии/настройки/найденные ники НЕ трогает и НЕ удаляет при деинсталляции.
;  4. Не требует прав админа (PrivilegesRequired=lowest) — иначе Windows не даст писать sessions рядом с exe.

#define MyAppName "Telegram Username Scanner"
#define MyAppVersion "2.0"
#define MyAppExe "TelegramUsernameScanner.exe"

[Setup]
AppId={{8E2A3F1B-4C7D-4E5A-9B11-7A2B9C4D5E6F1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Valterkr
DefaultDirName={autopf}\{#MyAppName}
; ^ стартовое предложение. При обновлении подставится папка из прошлого раза (UsePreviousAppDir).
UsePreviousAppDir=yes
DirExistsWarning=no
; Разрешить выбрать папку с уже лежащими сессиями:
Uninstallable=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputBaseFilename=TelegramUsernameScanner-Setup-2.0
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Dirs]
; Папка сессий создаётся, при удалении программы НЕ трогается:
Name: "{app}\\sessions"; Flags: uninsneveruninstall

[Files]
; Главный exe — всегда заменяется на новый:
Source: "{#MyAppExe}"; DestDir: "{app}"; Flags: ignoreversion
; Настройки и результаты — копируются ТОЛЬКО если их ещё нет (обновление их не затрёт):
Source: "accounts.json"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall skipifsourcedoesntexist
Source: "available.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall skipifsourcedoesntexist
Source: "fragment.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall skipifsourcedoesntexist

[Icons]
Name: "{autoprograms}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExe}"
Name: "{autodesktop}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Никогда не удаляем сессии при обновлении — секции нет специально.

[UninstallDelete]
; При деинсталляции exe удалится, а это — НЕТ (сессии и находки остаются):
; sessions/, accounts.json, available.txt, fragment.txt — остаются.

[Registry]
; Запоминаем папку установки, чтобы следующий Setup-2.1 сам предложил её же:
Root: HKCU; Subkey: "Software\\TelegramUsernameScanner"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekeyifempty
Root: HKCU; Subkey: "Software\\TelegramUsernameScanner"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"

[Code]
function InitializeSetup(): Boolean;
var
  PrevPath: String;
begin
  { Если программа уже ставилась — сразу предлагаем её папку, даже если DefaultDirName другая }
  if RegQueryStringValue(HKCU, 'Software\TelegramUsernameScanner', 'InstallPath', PrevPath) then
    if DirExists(PrevPath) then
      WizardForm.DirEdit.Text := PrevPath;
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Backup: String;
begin
  { Перед заменой exe — бэкап настроек на всякий случай }
  if CurStep = ssInstall then
  begin
    if FileExists(ExpandConstant('{app}\accounts.json')) then
    begin
      Backup := ExpandConstant('{app}\accounts.json.bak');
      FileCopy(ExpandConstant('{app}\accounts.json'), Backup, False);
    end;
  end;
end;
