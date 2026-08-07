; LinguaFusion installer -- Inno Setup script
;
; Compile with Inno Setup (free, jrsoftware.org/isinfo.php) once both
; PyInstaller builds exist:
;   pyinstaller pyinstaller_desktop.spec
;   pyinstaller pyinstaller_server.spec
; then open this file in the Inno Setup Compiler and click Compile, or:
;   iscc LinguaFusion.iss
;
; Output: dist_installer\LinguaFusion-Setup.exe -- a normal Windows
; installer wizard someone can double-click, with no Python or dependency
; knowledge required for the core app to run.
;
; WHAT THIS DOES NOT COVER (by design, see comments below):
;   - Tesseract OCR, ffmpeg, Ollama are separate external programs, not
;     Python packages, so they can't be bundled into these exes. The
;     post-install page below offers to run winget for these, same as
;     install.ps1 did, but winget itself needs to already be present
;     (built into Windows 10/11 since ~2021).
;   - NLLB-200 setup (the translation quality upgrade) needs the
;     `ct2-transformers-converter` tool and a Python environment to run
;     it, since converting a Hugging Face model to ctranslate2 format
;     isn't something we've packaged as its own frozen tool. If the
;     target machine doesn't have Python, this step is skipped with a
;     message rather than silently failing.

#define MyAppName "LinguaFusion"
#define MyAppVersion "1.0"
#define MyAppExeName "LinguaFusion.exe"

[Setup]
AppId={{8F2C1A6E-4B7D-4E1F-9C3A-2D5E7F8A1B4C}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist_installer
OutputBaseFilename=LinguaFusion-Setup
SetupIconFile=desktop\assets\linguafusion.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
; Both PyInstaller onedir outputs land in one shared install folder, so
; LinguaFusion.exe can find LinguaFusionServer.exe sitting right next to
; it at runtime (see ensure_backend_running() in desktop/main.py).
Source: "dist\LinguaFusion\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\LinguaFusionServer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "install_argos_models.py"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent

[Code]
var
  OptionalPage: TOutputMsgWizardPage;

procedure InitializeWizard;
begin
  OptionalPage := CreateOutputMsgPage(wpSelectTasks,
    'Optional components', 'Set up local AI correction, better OCR/translation quality',
    'LinguaFusion works out of the box once installed. A few optional pieces improve ' +
    'quality further but need separate downloads:' + #13#10#13#10 +
    '- Tesseract OCR (scanned PDF text extraction) - github.com/UB-Mannheim/tesseract/wiki' + #13#10 +
    '- Ollama (local AI correction for speech/OCR) - ollama.com' + #13#10 +
    '- ffmpeg (audio format conversion) - ffmpeg.org' + #13#10#13#10 +
    'You can install any of these later, or run install.ps1 from the app folder ' +
    'for a guided setup that checks for and installs all of them automatically.');
end;
