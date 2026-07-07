# LinguaFusion Design Overview

## Product goal

LinguaFusion is a local desktop application for multilingual speech, document, and reader workflows. The design goal is to keep common language-processing tasks available from a single app while allowing the heavier speech, OCR, translation, and TTS components to run through a local backend.

## Core workflows

### Speech workflow

Audio input is recorded or imported, passed to the backend for speech recognition, optionally post-processed with correction memory, and displayed as editable text.

```text
Audio input → speech recognition → cleanup/corrections → transcript → optional translation/export
```

### Translation workflow

Typed or imported text is segmented, translated, and rendered in a readable output view. For document inputs, the application attempts to preserve paragraph and table structure where practical.

```text
Text/document input → segmentation → translation → post-processing → export
```

### Reader workflow

The Reader imports text or document content and generates speech audio for playback. Cursor-based reading, pause/resume, and basic highlighting are supported with approximate timing.

```text
Document/text input → text extraction → TTS generation → playback/highlighting
```

### OCR workflow

Images and scanned PDFs are processed with OCR. The output is cleaned and routed back into document, translation, or reader workflows.

```text
Image/scanned PDF → OCR → cleanup → editable text → translation/reader/export
```

## High-level architecture

```text
LinguaFusion
├── desktop client
│   ├── UI screens
│   ├── file import/export actions
│   ├── audio playback controls
│   └── local user interaction state
│
├── backend API
│   ├── speech service
│   ├── translation service
│   ├── TTS service
│   ├── OCR/document service
│   ├── correction memory service
│   └── diagnostics endpoints
│
└── local runtime assets
    ├── speech models
    ├── TTS models
    ├── translation packages
    ├── generated audio
    └── local user data
```

## Backend responsibilities

The backend provides HTTP endpoints for speech recognition, translation, document parsing, OCR, TTS, correction memory, and diagnostics. Expensive processing is kept out of the UI thread so the desktop client remains responsive.

## Desktop responsibilities

The desktop client handles file selection, drag-and-drop routing, display of transcripts/translations, reader controls, user corrections, and export actions. It communicates with the local backend through HTTP calls.

## Local-first design

The repository excludes virtual environments, model binaries, generated media, local databases, and runtime configuration. This keeps the source repository lightweight and avoids publishing machine-specific files.

## Known design trade-offs

- Reader highlighting is approximate because typical offline TTS engines do not return exact word timestamps.
- OCR table reconstruction is best-effort and depends strongly on scan quality.
- Document layout preservation is practical for structured text and tables, but complex PDF layout reconstruction remains limited.
- Translation quality depends on the installed local translation models and language pair.
