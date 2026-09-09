# LinguaFusion — Historical Windows Project Handoff

For the current cloud/Android project, read [CODEX_CURRENT_STATE.md](CODEX_CURRENT_STATE.md).
The August desktop checkpoint below is historical and is not the current cloud roadmap.

**Last updated:** August 7, 2026  
**Application version:** `1.0-rc2.14-agentic-phase-a`  
**Handoff revision:** `permissioned-background-task-foundation`  
**Architecture:** PySide6 Windows desktop app + FastAPI PC backend + mobile PWA used by Android and iPhone wrappers.

## August 7 low-usage continuation checkpoint

The installed release at `dist\LinguaFusion` remains the verified Phase A
build. Do not replace it until the Phase B source checkpoint below completes
packaged GPU validation.

Phase B source work now present but **not yet packaged**:

- `backend/services/agent_planner_service.py` adds a preview-only local Ollama
  planner using JSON-schema structured output, temperature 0, the GPU
  coordinator, one validation repair attempt, and `OLLAMA_PLANNER_MODEL`
  configuration (falling back to the normal Ollama model).
- `POST /agent/plan` and `GET /agent/planner/status` are authenticated. The
  model can propose only Phase A's typed allowlist. The server validates every
  tool and input before preview; execution still requires UI confirmation and
  is validated again by `/agent/tasks`.
- Desktop and phone Task Centers have natural-language request, preview,
  confirm, and discard controls. Note creation still needs separate PC-owner
  `local_write` approval. Unsafe and external tools remain disabled.
- A real GPU call with `llama3.1:8b` returned a valid translation + note plan
  in 49 seconds at the confirmed 6498 MHz memory clock. It exposed a quality
  issue where the model used translated content as the note title; validation
  now rejects referenced note titles and triggers the one repair attempt. That
  exact live request must be rerun next.
- The desktop-theme regression is repaired in source. A late Signal Deck QSS
  block hard-coded one cyan/dark palette and Consolas across the whole app,
  overriding all nine theme and font choices. It now resolves through the
  active palette, corner metrics, and independently selected font.
- 20 focused planner, policy/API, desktop theme/usability, and phone tests pass.
  Python and JavaScript syntax checks pass. The broader suite reached 65 passes
  before 13 obsolete tests failed only because they hard-coded an older version;
  those assertions now accept any `1.0-rc2.*` release.

Resume in this order:

1. Rerun `Translate Good morning to Odia and save it as a note called Greeting`
   and confirm the repaired plan keeps `Greeting` as the literal note title.
2. Add reference-output-field validation and a test, so each `$step.N.field`
   must name a real output of that earlier tool.
3. Make failures during the second/repair Ollama call return the same friendly
   HTTP 503 response as failures during the first call.
4. Change the desktop Task Center safety-strip copy from `PHASE A` to `PHASE B`.
5. Rerun the full deterministic suite and a source live preview -> confirm ->
   owner approval -> completion workflow.
6. Capture Broadsheet, Gallery, Glass Dark, and Zen from the native desktop app
   to verify visibly distinct rendering.
7. Bump to `1.0-rc2.15-agentic-phase-b`, bump the phone cache beyond v26,
   update roadmap/counts, package, run the full CUDA suite, preserve rc2.14 as
   rollback, then install and launch rc2.15.

## Current state

LinguaFusion is an offline-first speech transcription, translation, OCR, document reader, and TTS application. The PC performs the inference work. Phones can connect over the local network or through the owner-controlled HTTPS tunnel and one-time pairing flow.

Agentic Phase A is implemented. Desktop and phone Task Centers can queue
validated translation and audio-transcription workflows, monitor persistent
progress, pause/resume/cancel/retry work, and request owner approval before a
task creates a note. The execution engine exposes no shell, Python, arbitrary
filesystem, unrestricted database, or unrestricted network tool.

- **Universal Color Inversion (`◐`)**: Both the native PC desktop app (`desktop/main.py`) and Mobile PWA (`backend/mobile_web/linguafusion-themes.css`) feature universal color mode inversion. Toggling color mode (`◐`) cleanly inverts backgrounds, panels, text, and surfaces between Light $\leftrightarrow$ Dark without altering the selected theme structure or leaving the active page.
- **Independent Font Separation**: Typography choices (`Modern Sans`, `Friendly Rounded`, `Accessibility Sans`, `Editorial Serif`, `Classic Serif`, `Technical Mono`) are strictly decoupled from theme looks across both PC and Phone interfaces.
- The native Windows desktop app offers the 9 PC themes (`broadsheet`, `editorial-split`, `reading-room`, `gallery`, `editorial-luxe`, `glass-dark`, `aurora-glass`, `blueprint`, `zen`), with `broadsheet` as default.
- The mobile PWA and native Android/iPhone wrappers offer the 9 mobile themes (`soft-ui`, `sunset`, `brutalist`, `warm-editorial`, `glass-dark`, `neon-arcade`, `warm-minimal`, `bold-mono`, `nature-calm`), with full CSS custom property tokens, structural rules, and color mode inversion enabled.
- Theme, color mode, and font choices persist separately between sessions.
- Fonts use local/system families only; the offline app does not depend on Google Fonts.
- Speech uses a shared four-stage interaction model: **Listening → Processing → Translating → Complete**.
- Motion can be set independently to Full, Reduced, or Off on desktop; phones additionally offer a System setting.

## Appearance choices

### Windows desktop — 9 PC looks

| ID | Display name | Mode |
| --- | --- | --- |
| `broadsheet` | Broadsheet (Default) | Light |
| `editorial-split` | Editorial Split | Light |
| `reading-room` | Reading Room | Light |
| `gallery` | Gallery | Dark |
| `editorial-luxe` | Editorial Luxe | Light |
| `glass-dark` | Glass Dark | Dark |
| `aurora-glass` | Aurora Glass | Dark |
| `blueprint` | Technical Blueprint | Dark |
| `zen` | Zen Focus | Dark |

### Mobile PWA, Android, and iPhone — 9 phone looks

| ID | Display name | Mode |
| --- | --- | --- |
| `soft-ui` | Soft UI | Light |
| `sunset` | Sunset | Light |
| `brutalist` | Neo-Brutalist | Light |
| `warm-editorial` | Warm Editorial | Light |
| `glass-dark` | Glass Dark | Dark |
| `neon-arcade` | Neon Arcade | Dark |
| `warm-minimal` | Warm Minimal | Light |
| `bold-mono` | Bold Mono | Light |
| `nature-calm` | Nature Calm | Light |

### Independent font choices — all interfaces

`Modern Sans`, `Friendly Rounded`, `Accessible Sans`, `Editorial Serif`, `Classic Serif`, and `Technical Mono`.

## Starting LinguaFusion

Before GPU inference, confirm the RTX 2080 Ti has the known-good **-500 MHz memory clock offset** applied in MSI Afterburner.

```powershell
cd /d W:\OfflineSpeechTranslator_dev_v1.0

# Start the PC backend.
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_backend.ps1

# In a second terminal, start the native desktop interface.
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_desktop.ps1
```

For phone access and pairing, start the mobile/remote backend flow documented by the current scripts and use the owner Access page to issue or revoke invitations.

## Theme implementation

- `desktop/main.py`
  - `DESKTOP_THEME_IDS` limits the Settings selector to nine PC looks.
  - `DESKTOP_FONT_SPECS` defines six independent font presets.
  - QSS generation combines the selected look with the selected font.
- `backend/mobile_web/linguafusion-themes.js`
  - Declares platform ownership for every concept.
  - Populates only mobile looks in the PWA.
  - Stores `lf-theme` and `lf-font` independently.
  - Synchronizes Android system bars with light/dark looks.
- `backend/mobile_web/linguafusion-themes.css`
  - Contains design tokens for all concepts and late-cascade font overrides.
- `backend/mobile_web/linguafusion-structure.css`
  - Adds the phone-specific Speech screen composition for the seven mobile concepts.
- `backend/mobile_web/app.css`
  - Maps the existing PWA components to shared design tokens.
- `backend/mobile_web/index.html` and `app.js`
  - Provide separate **Phone look** and **Font** selectors.

## Verification completed

- Option A Design Concept (`demo.html`) embedded into native PySide6 UI using `QWebEngineView` and mapped to sidebar **Demo** navigation button.
- Restored the 9 PC themes and 9 Phone themes across `desktop/main.py` and `backend/mobile_web/linguafusion-themes.js`.
- All nine desktop looks and all six fonts can be applied independently in PySide6.
- All nine phone looks verified for PWA / Android / iOS wrappers.
- The verified PyInstaller release is installed at
  `dist\LinguaFusion\LinguaFusion.exe` and is the currently running desktop
  build. The immediately previous build is preserved at
  `dist\LinguaFusion.pre-agent-phase-a-20260807` for rollback.

## August 7 regression audit

- 73 deterministic backend, desktop, mobile, accessibility, agent-policy, and packaging tests pass.
- 18 CPU-safe live API tests pass across language detection, translation, Reader,
  document export, notes, OCR, image translation, TTS, and speech round-trip.
- Piper now runs in an isolated child process by default so native runtime
  conflicts cannot terminate the long-running backend. The frozen Windows app
  uses a dedicated packaged worker, and the PyInstaller spec includes Piper's
  required espeak-ng pronunciation data.
- The windowless release bundle itself passed all 18 live API workflows after
  packaging; this includes a valid packaged TTS WAV, speech round-trip, and a
  persistent background-agent task with audit events.
- Whisper supports configurable hotwords (`LF_WHISPER_HOTWORDS`) and defaults
  to the `LinguaFusion` product name.
- Explicit CPU mode no longer preloads CUDA libraries.
- Whisper VRAM release now uses the correct model lock during exclusive GPU handover.
- Agentic Phase A is implemented in `backend/services/agent_task_service.py`
  with authenticated `/agent/*` APIs and desktop/phone Task Centers. Phase B
  should add the local Ollama JSON planner above this existing policy gate.

Primary regression commands:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\test_core_desktop_usability.py backend\test_core_mobile_clients.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Final GPU validation was completed after the Afterburner underclock became
visible: `nvidia-smi` reported 6498 MHz versus the 7000 MHz maximum. The
packaged standard app passed all 18 live workflows in CUDA mode and then passed
three consecutive TTS -> faster-whisper -> translation round trips without
corruption or hanging. The verified release is installed at
`dist\LinguaFusion`; the previous build is preserved at
`dist\LinguaFusion.pre-agent-phase-a-20260807` (with the earlier pre-audit
backup retained separately).

The normal desktop-launched backend reports CUDA for faster-whisper and NLLB,
publishes `https://linguafusion.fyi` in Access, and the public `/health` and
`/mobile/` routes both returned HTTP 200 after startup. The public mobile page
contains the Speech and Task Center views plus safe-area handling for modern
Android and iPhone screens.

## Important operational notes

- GPU corruption or hanging: verify the MSI Afterburner -500 MHz memory-clock offset first.
- `LF_WHISPER_DEVICE=cpu` remains the safe fallback.
- Ollama correction must not receive empty ASR text.
- Do not weaken the existing correction overlap guardrails.
- Music/lyrics mode intentionally skips LLM correction.
- Android and iPhone do not need separate theme implementations because both consume the mobile PWA from the PC backend.
