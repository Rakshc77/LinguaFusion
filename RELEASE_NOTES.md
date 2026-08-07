# Release Notes

## 1.0-rc2.12-ui-consumer-polish

Phase 5 workflow-fit refinement. This build tightens the medium-width layout across workflow pages, improves OCR spacing, applies native media icons to playback-related buttons, and adds multiple taskbar-safe LinguaFusion icon concepts.

Changes:

- Translate/Reader/Speech waveform cards now stay inside the same proportional content band as the main workflow controls.
- Horizontal page scrolling remains disabled.
- Playback buttons use native media icons so compact controls do not render as empty boxes.
- OCR controls were reorganized into a compact row to remove excessive empty space.
- The scroll cue is only shown on pages where lower playback controls may require vertical scrolling.
- New icon options are included in `desktop/assets/icon_options/`; Option A is applied as the default app and taskbar icon.

Known limitation: ultra-compact/mobile-style layout remains deferred.


## 1.0-rc2.13-ui-consumer-polish-lock

- Uses icon option B as the app/taskbar icon.
- Applies the Windows AppUserModelID before QApplication startup for more reliable taskbar branding.
- Restores visible blue/white playback glyphs without native black Qt media icons.
- Tightens the OCR empty-state layout and removes the grey control cutout behind the Extract action.
