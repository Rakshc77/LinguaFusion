# LinguaFusion Windows Run Guide

This guide explains how to run LinguaFusion locally on Windows from VS Code or PowerShell.

## 1. Open the project

Open the project folder in VS Code:

```powershell
cd <LinguaFusion project folder>
code .
```

## 2. Create a virtual environment

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\activate
```

## 3. Install dependencies

```powershell
pip install -r requirements.txt
```

## 4. Add local runtime assets

Large runtime assets are intentionally not included in the repository. Depending on which features you use, place local models and tools in the expected project folders, for example:

```text
models/whisper/
models/piper/
tools/whispercpp/
```

Generated files and local runtime data should stay untracked.

## 5. Start the backend

```powershell
python -m uvicorn backend.server:app --reload --host 0.0.0.0 --port 8000
```

Open this URL to check the backend:

```text
http://localhost:8000/health
```

The response should show a JSON health or diagnostics payload.

## 6. Start the desktop app

Open a second terminal, activate the same virtual environment, and run:

```powershell
.\.venv\Scripts\activate
python .\desktop\main.py
```

## 7. Optional helper scripts

The repository may include helper scripts for common startup commands:

```powershell
.\scripts\start_backend.ps1
.\scripts\start_desktop.ps1
```

## 8. Files that should remain local

Keep these out of public Git commits:

```text
.venv/
models/
downloads/
storage/
temp/
debug/
__pycache__/
*.wav
*.mp3
*.mp4
*.log
```

## Troubleshooting

### `git` is not recognized

Install Git for Windows and restart VS Code. GitHub Desktop can still publish the repository even if the Git CLI is not available in the terminal.

### Backend does not start

Check that the virtual environment is activated and that dependencies were installed with:

```powershell
pip install -r requirements.txt
```

### Desktop opens but backend features fail

Confirm the backend is running and that `http://localhost:8000/health` returns a valid response.

### Speech, TTS, or OCR features fail

Check that the required local models and tools are installed in the expected folders and available to the backend.
