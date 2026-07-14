# LinguaFusion

LinguaFusion is an offline-first desktop language assistant for speech transcription, translation, document reading, OCR, and text-to-speech workflows.

The project is designed for local use on Windows. Core processing runs through a local FastAPI backend and a desktop client, with local models and runtime data kept outside the repository.

## Main features

- Speech-to-text for recorded or imported audio
- Text translation for supported language pairs
- Text-to-speech playback for imported or typed text
- Reader mode for text and document workflows
- OCR support for images and scanned PDFs
- Format-aware export for TXT, Markdown, DOCX, CSV, and PDF workflows where supported
- User correction memory for recurring transcription or spelling fixes
- Local-first architecture with optional extension points for external services

## Supported languages

The current build focuses on:

| Language | Code |
|---|---:|
| English | `en` |
| German | `de` |
| Spanish | `es` |
| Hindi | `hi` |

Support depends on the installed local speech, translation, and TTS models.

## Repository structure

```text
backend/              FastAPI backend and service modules
desktop/              Desktop application entry point and UI code
scripts/              Windows helper scripts
tools/                Local tool integrations or build instructions
Readme.md             Main project overview
DESIGN.md             Architecture overview
README_RUN_WINDOWS.md Windows run guide
requirements.txt      Python dependency list
VERSION               Current project version
```

The following folders are intentionally not tracked in Git because they contain local runtime data, generated outputs, virtual environments, or large model files:

```text
.venv/
models/
downloads/
storage/
temp/
debug/
__pycache__/
```

## Quick start on Windows

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

Install Python dependencies:

```powershell
pip install -r requirements.txt
```

Start the backend:

```powershell
python -m uvicorn backend.server:app --reload --host 0.0.0.0 --port 8000
```

In a second terminal, start the desktop app:

```powershell
python .\desktop\main.py
```

Health check:

```text
http://localhost:8000/health
```

See `README_RUN_WINDOWS.md` for a more detailed Windows run guide.

## Privacy and local files

LinguaFusion is intended to run locally. Local models, generated audio, user correction data, runtime databases, logs, and temporary files should remain outside the public repository. Keep them excluded through `.gitignore`.

## Status

Current public version: `1.0.0-beta.5`

This is an active development project. Some workflows, especially OCR table reconstruction, document layout preservation, and speech alignment, are best-effort and may vary by input quality and installed local models.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
