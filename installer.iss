; iFlow 中转管理工具 - Inno Setup 安装脚本
; 兼容 Windows 7 SP1 及以上系统
; 每次安装清理旧数据，需重新登录 iFlow

#define MyAppName "iFlow 中转工具"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "iFlow"
#define MyAppExeName "iFlow中转工具.exe"

[Setup]
AppId={{A3F8B2C1-7D4E-4A5F-9B6C-1E2D3F4A5B6C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\iFlow中转工具
DefaultGroupName={#MyAppName}
OutputDir=installer_output
OutputBaseFilename=iFlow中转工具_Setup_{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
; Windows 7 SP1 最低版本要求 (6.1.7601)
MinVersion=6.1sp1
SetupIconFile=iflow.ico
UninstallDisplayIcon={app}\iFlow中转工具.exe
UninstallDisplayName={#MyAppName}
PrivilegesRequired=admin
; 允许用户选择安装目录
AllowNoIcons=yes
; 安装时显示许可协议（可选）
; LicenseFile=LICENSE.txt
; 现代化安装界面
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create Desktop Shortcut"; GroupDescription: "Additional icons:"

[Files]
; 主程序（PyInstaller 打包产物）
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; 内置 CLIProxyAPI 引擎
Source: "engine\cli-proxy-api.exe"; DestDir: "{app}\engine"; Flags: ignoreversion
Source: "engine\config.yaml"; DestDir: "{app}\engine"; Flags: ignoreversion
Source: "engine\static\*"; DestDir: "{app}\engine\static"; Flags: ignoreversion recursesubdirs createallsubdirs

; 应用图标
Source: "iflow.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\iflow.ico"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\iflow.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 iFlow 中转工具"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 卸载时清理运行时生成的文件
Type: filesandordirs; Name: "{app}\engine\auth"
Type: filesandordirs; Name: "{app}\engine\logs"
Type: filesandordirs; Name: "{app}\engine\*.log"

[Code]
// 安装前清理旧的认证数据，确保每次安装都需要重新登录
procedure CurStepChanged(CurStep: TSetupStep);
var
  AuthDir: String;
  HomeAuthDir: String;
  EngineAuthDir: String;
begin
  if CurStep = ssInstall then
  begin
    // 清理安装目录下的旧认证数据
    EngineAuthDir := ExpandConstant('{app}\engine\auth');
    if DirExists(EngineAuthDir) then
      DelTree(EngineAuthDir, True, True, True);

    // 清理用户目录下的认证数据
    HomeAuthDir := ExpandConstant('{userappdata}\..\..\.cli-proxy-api');
    if DirExists(HomeAuthDir) then
      DelTree(HomeAuthDir, True, True, True);

    // 也清理 %USERPROFILE%\.cli-proxy-api
    AuthDir := GetEnv('USERPROFILE') + '\.cli-proxy-api';
    if DirExists(AuthDir) then
      DelTree(AuthDir, True, True, True);
  end;
end;

// 卸载时也清理所有认证数据
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AuthDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    AuthDir := GetEnv('USERPROFILE') + '\.cli-proxy-api';
    if DirExists(AuthDir) then
      DelTree(AuthDir, True, True, True);
  end;
end;
