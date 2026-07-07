# LinguaFusion Release Notes

## Current public version

`1.0.0-beta.5`

## Current capabilities

- Local speech transcription for recorded or imported audio
- Translation for supported language pairs
- Reader mode with text-to-speech playback
- OCR support for images and scanned PDFs
- Format-aware document export where supported
- Correction memory for recurring transcription or spelling issues
- Backend diagnostics through a local health endpoint

## Speech workflow

- Audio can be routed into the speech workflow for transcription.
- Long audio can be processed in chunks and merged into one transcript.
- Local correction memory can normalize recurring recognition errors.
- Speech output can be reused for translation, reading, notes, or export.

## Translation workflow

- Imported text is segmented for more stable translation.
- Paragraph and line structure are preserved where practical.
- Mixed-language text can be routed per segment when automatic source detection is enabled.
- Helper views are displayed only when relevant to the selected target language.

## Reader workflow

- Reader mode imports text and document content.
- TTS can route supported language segments to suitable local voices.
- Cursor-based reading and highlighting are approximate and depend on generated audio duration.

## OCR and document workflow

- OCR supports images and scanned PDFs as a best-effort workflow.
- CSV, pipe-table text, and table-like document content can be exported in a more structured form where practical.
- PDF and DOCX layout preservation is best-effort and depends on the source document.

## Known limitations

- Offline translation quality depends on the installed local models.
- OCR table reconstruction is not guaranteed to be exact.
- Complex PDF layout preservation remains limited.
- Reader highlighting is approximate because exact word-level TTS timestamps are not available.
