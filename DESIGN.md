# LinguaFusion Design Notes

Current version: 1.0-rc2.12-ui-consumer-polish

Phase 5 uses a stable desktop UI with a supported medium-width floor. The application avoids horizontal workflow scrolling in normal pages. At medium width, right-side info panels collapse, controls use a shared proportional content band, and only vertical scrolling is used when lower playback controls require additional space.

## Medium-width layout policy

- Keep the desktop Source/Target arrangement instead of forcing an ultra-compact mobile layout.
- Compress source/target boxes, input/output fields, action buttons, export buttons, and playback cards into the same visual content band.
- Avoid horizontal page scrolling.
- Use vertical scrolling for lower playback sections when necessary.
- Show a clear scroll cue only on pages with playback controls.

## Workflow adjustments in this build

- Translate: tighter input/output and playback bands, export buttons remain visible, native media icons are applied to playback controls.
- Reader: same proportional playback and export behavior as Translate.
- OCR: controls are grouped into a compact row and the result area is brought up to reduce dead space.
- Speech: media/control buttons use native icons in compact mode and stay inside the common content band.

## Application icon

The desktop shell includes PNG and ICO icon assets under `desktop/assets/`. Multiple candidate icon concepts are included under `desktop/assets/icon_options/`. The default app/taskbar icon in this build is Option A, which combines speech, waveform/audio, translation, and document handling into a single simple mark.

Ultra-compact/mobile-style layout remains deferred until it can be redesigned cleanly.
