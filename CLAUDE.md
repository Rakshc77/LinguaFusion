# LinguaFusion — project context for Claude Code

Offline-first Windows app: speech transcription, translation, OCR, and TTS.
PySide6 desktop app (`desktop/main.py`) + FastAPI backend (`backend/server.py`),
running locally, no cloud dependency by design.

Dev machine: AMD Ryzen 5 5600X, 32GB RAM, RTX 2080 Ti (11GB VRAM), Windows 11.

## Starting the app

```powershell
.\scripts\start_backend.ps1   # sets LF_WHISPER_MODEL, starts uvicorn
.\scripts\start_desktop.ps1   # launches the PySide6 app
```

**Before starting anything GPU-related**, confirm MSI Afterburner has a
**-500MHz memory clock underclock** applied (see GPU section below) — without
it, GPU inference silently corrupts output or hangs forever with no error.

## GPU: known VRAM instability (already fixed, don't re-diagnose from scratch)

This RTX 2080 Ti produces corrupted output under sustained compute load
(garbled multilingual text from Ollama, silent hangs from faster-whisper)
due to marginal VRAM. Root-caused via testing across model sizes and
confirmed with a driver reinstall (DDU) that did NOT fix it, ruling out
driver corruption. **Fix: -500MHz memory clock offset in MSI Afterburner.**
This must be active (ideally "apply at Windows startup" checked in
Afterburner settings) before running Ollama or faster-whisper on GPU. If
GPU output ever looks corrupted/garbled again, check the underclock first
before re-diagnosing — don't assume it's a new bug.

`LF_WHISPER_DEVICE=cpu` env var forces CPU mode as a safe fallback if GPU
issues recur.

## Speech: faster-whisper (not whisper.cpp)

`backend/services/whisper_service.py` — switched from whisper.cpp subprocess
calls to `faster-whisper` (loads model once, stays in memory, single-pass
language detection). Config via env vars: `LF_WHISPER_MODEL` (tiny/base/
small/medium/large-v3, default small), `LF_WHISPER_DEVICE` (cuda/cpu/auto).

**Windows DLL gotcha (already solved, don't re-solve):** `nvidia-cublas-cu12`
and `nvidia-cudnn-cu12` pip packages install real DLLs but are *namespace
packages* with no `__init__.py`, so they have no `__file__` attribute —
only `__path__`. Since Python 3.8+, Windows extension modules don't search
`PATH` for DLL dependencies at all (a security change), only
`os.add_dll_directory()` registrations. The fix (already in
`whisper_service.py`'s `_register_windows_cuda_dll_dirs()`) imports each
subpackage (`nvidia.cublas`, `nvidia.cudnn`, etc.) individually and reads
`module.__path__` to register the `bin/` folder. If a future CUDA-adjacent
pip package fails to load its DLLs, this is the pattern to reuse.

## Local LLM correction: Ollama, not Gemini/Groq/OpenRouter

`backend/services/free_online_correction_service.py` and
`ai_provider_config_service.py` — cloud providers (Gemini/Groq/OpenRouter)
were removed entirely per user preference. Only two providers remain:
**LanguageTool** (free, no-key, grammar/spelling only) and **Ollama**
(local, default model `llama3.1:8b`, configurable via `OLLAMA_URL`/
`OLLAMA_MODEL` env vars or the `ollama` section of the provider config).

**Critical guardrail — do not weaken without a good reason.** Ollama (and
any LLM correction generally) is prone to hallucinated rewrites rather than
surgical corrections: it will confidently replace a phrase with something
plausible-sounding but wrong. `_valid_correction()` enforces a word-overlap
threshold (Unicode-aware, so German/Spanish/Hindi text isn't undercounted)
before any correction is accepted — 0.55 for speech, 0.75 for OCR (OCR
carries more numbers/codes that must not drift). If a correction fails the
threshold, the original (uncorrected) text is returned instead. The
system prompt also explicitly forbids paraphrasing/rewriting, only
character/word-level fixes. This was learned from a real incident: Ollama
rewrote Johnny Cash lyrics ("ain't no grave") into fabricated, unrelated
lyrics ("Buddy Holly...") when asked to "correct" them.

**Music/lyrics mode intentionally skips LLM correction entirely** —
`linguafusion_intelligence_engine.py`'s `_online_candidates_for_music()`
always returns `[]` regardless of the smart_mode setting. The existing
chunked-transcription + whole-file-pass + dedupe pipeline outperforms LLM
"correction" on lyrics, and the overlap guardrail can't help here since it
only checks fidelity to the (possibly already-wrong) raw ASR text, not to
the actual ground truth. Do not re-enable LLM correction for music without
addressing this.

## OCR: dual-engine, routed by file type

`backend/services/ocr_service.py` — RapidOCR for plain image files (photos/
screenshots, generally messier), Tesseract for scanned PDFs (rendered as
clean flat scans via PyMuPDF, where Tesseract already does well). Automatic
fallback to Tesseract if RapidOCR isn't installed or returns nothing.

Tesseract passes were reduced from up to 6 full OCR passes per image
(unconditional) to conditional escalation — extra PSM-mode passes and the
table-detail pass only run if the primary pass scores poorly or the page
looks tabular. `--oem 1` (LSTM engine) added throughout.

`ocr_correct_text()` in `free_online_correction_service.py` is an opt-in
Ollama cleanup pass for OCR-specific errors (missing umlauts/ß, 0/O, 1/l/I
confusion) — disabled by default (`ai_cleanup=False` param on
`extract_text_from_image()`), no UI toggle wired up yet.

`file_reader_service.py`'s PDF-OCR fallback (used by Reader) delegates to
`ocr_service.py`'s pipeline rather than duplicating a weaker one — this was
a real bug (Reader's scanned-PDF OCR was noticeably worse than the OCR
tab's for identical content) fixed by having `extract_pdf_ocr_text()` call
into `extract_text_from_image()` instead of its own bare
`pytesseract.image_to_string()` call.

**Caution:** `file_reader_service.py` and `ocr_service.py` got their
contents accidentally swapped once mid-session (copy-paste mixup). If
something seems off, verify with `grep "^def " <file>` that each file has
its own distinct functions (file_reader_service.py: `read_plain_text`,
`extract_docx_text`, `extract_pdf_text`, etc. — ocr_service.py:
`_preprocess_image`, `_clean_ocr_text`, `extract_text_from_image`, etc.).

## Translation: NLLB-200 preferred, Argos automatic fallback

`backend/services/translation_service.py` — `direct_translate()` tries
`nllb_translation_service.py` first (if the model directory exists),
falling back to Argos Translate transparently on any failure. NLLB-200
runs via `ctranslate2` (already a dependency for faster-whisper), converted
model expected at `models/nllb-200-distilled-600m/` (or `NLLB_MODEL_DIR`
env var). Chosen over routing translation through Ollama specifically
because NLLB is a purpose-built translation model with no tendency to
creatively rewrite, unlike a general chat LLM.

Argos's `get_installed_languages()` and per-pair translation objects are
now cached (`_get_installed_languages_cached()`,
`_get_translation_cached()`) — this was being re-scanned on every single
line of a batch/document translation, a real performance bug now fixed.

## TTS: Piper, per-segment language switching

`backend/services/piper_service.py` — `speak_to_file()` now **always**
routes through `speak_mixed_to_file()` / `split_text_for_mixed_tts()` for
per-segment language detection, using the requested language as the
fallback for ambiguous segments. This used to only activate when the
caller passed `lang="auto"`/`"mixed"`, but every real caller (desktop
dropdowns, `/tts/speak`, `/reader/speak`) always passes a concrete code —
so the segmentation logic existed but never actually ran, and mixed-language
text was always forced through one voice with no handover.

Word-level (not just sentence-level) language switching was added for
Latin-script text via `_split_latin_by_word_evidence()` — carves out runs
of words with strong diacritic evidence (German ÄÖÜäöüß, Spanish
áéíóúñ¿¡) into their own voice segment. **Known limitation, by design:**
this only works where spelling gives unambiguous evidence. A plain-ASCII
proper noun (e.g. an English name with no umlaut) embedded in a German
sentence has no orthographic signal and will still read in the sentence's
dominant voice — reliable word-level language ID for ambiguous plain text
doesn't really exist, and guessing would likely be wrong more often than
right.

## Known remaining gaps / not yet done

- No UI toggle in the desktop app for OCR's `ai_cleanup` parameter or for
  choosing NLLB vs Argos explicitly (NLLB just auto-preferred if present).
- `/health` endpoint's runtime check still references old whisper.cpp
  paths/model files — cosmetic inaccuracy, not fixed, doesn't affect
  actual functionality since faster-whisper doesn't use those paths.
- `requirements.txt` was updated to include `faster-whisper`,
  `rapidocr-onnxruntime`, `transformers` but hasn't been fully re-verified
  against a clean install.
