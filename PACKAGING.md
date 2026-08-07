# Building LinguaFusion-Setup.exe

Run all of this on the Windows machine, inside the activated venv, from the
project root. Each step depends on the one before it.

## 1. Install the packaging tool

```powershell
pip install pyinstaller
```

## 2. Freeze the desktop app

```powershell
pyinstaller pyinstaller_desktop.spec
```

Output: `dist\LinguaFusion\LinguaFusion.exe` plus its supporting files.
Test it runs (it'll fail to reach the backend since that's not running yet
-- that's expected at this stage, just confirm the window opens).

## 3. Freeze the backend

```powershell
pyinstaller pyinstaller_server.spec
```

Output: `dist\LinguaFusionServer\LinguaFusionServer.exe`.

**This is the step most likely to need a fix.** Run it directly and watch
for errors:

```powershell
.\dist\LinguaFusionServer\LinguaFusionServer.exe
```

If it crashes on a missing CUDA DLL (cublas64_12.dll, cudnn64_9.dll, etc.)
-- this is the exact same class of problem solved earlier for the
source-run case (see Windows DLL resolution docs, "Windows DLL gotcha"). PyInstaller's
`collect_all()` in the .spec file *should* bundle these automatically
since they're real files in site-packages, but frozen-app DLL loading has
its own quirks separate from the namespace-package issue we fixed before.
If it happens, the fix is to explicitly add the missing DLL's full path to
the `binaries` list in `pyinstaller_server.spec` and rebuild.

Test it responds:
```powershell
curl http://localhost:8000/health
```

## 4. Test both together

Copy `dist\LinguaFusionServer\*` into `dist\LinguaFusion\` (merging the
folders -- this is what the installer does later, but worth testing now
before wrapping it in an installer):

```powershell
Copy-Item -Path "dist\LinguaFusionServer\*" -Destination "dist\LinguaFusion\" -Recurse -Force
.\dist\LinguaFusion\LinguaFusion.exe
```

The desktop app should spawn the backend automatically now (see
`ensure_backend_running()` in `desktop/main.py`) and the window should
show live data instead of "Backend Offline."

## 5. Install Inno Setup

Free download: https://jrsoftware.org/isinfo.php

## 6. Compile the installer

Open `LinguaFusion.iss` in the Inno Setup Compiler (or run `iscc
LinguaFusion.iss` from a terminal with Inno Setup on PATH) and compile.

Output: `dist_installer\LinguaFusion-Setup.exe` -- this is the file you'd
actually hand to someone else. Running it installs the app with a normal
Windows wizard, Start Menu entry, and optional desktop shortcut, using the
icon we built.

## What's NOT automated in the installer itself

- **Whisper model download** -- happens automatically the first time
  someone actually transcribes something (faster-whisper downloads it on
  first use). No action needed, just slower on the very first run.
- **Tesseract, ffmpeg, Ollama** -- these are separate programs, not Python
  packages, so they can't be frozen into the exes. The installer's
  "Optional components" page mentions them; `install.ps1` (already in the
  project) still works standalone for anyone who wants the full guided
  setup including these via winget.
- **NLLB-200** -- needs `ct2-transformers-converter`, which needs a live
  Python environment to run the one-time model conversion. Not something
  we've packaged as a frozen tool. If someone wants NLLB on a machine with
  no Python, that's a gap for now -- Argos (bundled) remains the working
  default either way.
