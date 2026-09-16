# LinguaFusion

PC-independent cloud translation, transcription, pronunciation guides and OCR,
with an Android app and browser interface. The original offline Windows app
remains a separate client.

## Continue in Codex

Read **[CODEX_CURRENT_STATE.md](CODEX_CURRENT_STATE.md)** first, then
[CLOUD_HANDOFF.md](CLOUD_HANDOFF.md) for deployment and signing constraints.
`main` is the current integrated baseline. Check the handover and Git history
for any active feature branch before changing it.

Cloud app: https://linguafusion-cloud-pilot-jl77ipbeua-ey.a.run.app/pilot/

## Current release

- Online interface: `2026.09.13.3`
- Android: `1.17` / versionCode `18`
- Android provides phone-only Offline translation and transcription for English,
  German, Arabic, Spanish and French.
- Android selected-text translation works from WhatsApp and other apps through
  **Translate with LinguaFusion**.
- Owner controls provide single-use join links and QR codes, request badges and
  native Android request notifications.

The existing private Android signing key must be preserved. Never generate a
replacement key: a differently signed APK cannot update existing installations.

Current source prepares Online `2026.09.14.1` and Android `1.18` / versionCode
`19`. They are not live until the cloud interface is deployed and the Android
APK is rebuilt and published with the existing owner key.

## Current appearance

Only Studio and Minimal are offered by the cloud app. Both have Day and Night
modes. Studio day uses Warm Editorial parchment and terracotta; Studio night
uses Sunset rose on plum. Minimal is monochrome. Typeface selection is
independent; “Match the look” uses editorial headings for Studio and sans-serif
for Minimal. Previously selected typefaces are preserved.

## Read Aloud

Read Aloud is implemented in the current source as an accessibility and
language-learning output action. It requires the release steps above before it
appears in installed/live copies.

The action will appear on Translation, Transcription and OCR result cards:

- Translation speaks the target language.
- Transcription speaks the selected or detected source language.
- OCR speaks the selected source language.
- Only one result speaks at a time. The first release has **Read aloud**,
  **Stop** and 0.75× / 1× / 1.25× speed controls.
- Speech is synthesized on the device. Result text and generated audio are not
  uploaded for speech, stored by LinguaFusion or sent to an AI provider.
- The initial guaranteed language scope is English, German, Arabic, Spanish and
  French. Availability still depends on an installed device voice.
- Existing pronunciation guidance (**Say it**) remains separate.

Platform behavior:

1. Browser/iPhone PWA speech uses the Web Speech synthesis API, with a clear
   unavailable-voice fallback.
2. Android uses native `TextToSpeech` for reliable installed-app and Offline
   behavior. Offline mode selects only a voice that does not require a network.
3. The hosted Online page connects to Android through an origin-restricted
   AndroidX WebKit message listener. The native layer validates language,
   text and rate, chunks long utterances, and stops speech on logout, account
   switch or content removal.
4. Physical-device testing is still required for all five languages on Android
   and iPhone Safari/Home Screen. A full voice chooser remains future polish.

Voice data remains OS-managed rather than bundled in the APK, so the source/APK
increase should be small; a phone may separately offer a voice-pack download.

## Candidate feature queue

After Read Aloud, the strongest usability additions are:

1. **Conversation mode** — large alternating controls for two speakers, quick
   language swap and explicit confirmation before paid online processing.
2. **Private history and phrasebook** — opt-in, searchable, device-local,
   exportable and fully deletable, with favorite phrases available Offline.
3. **Offline download manager** — show model/translation/voice-pack status,
   storage size, Wi-Fi-only downloads and safe removal.
4. **Camera reading workflow** — crop, rotate and select a sentence from OCR,
   then translate or read just that selection aloud.
5. **Accessibility controls** — larger text, higher contrast, reduced motion,
   haptics and better one-handed result actions.
6. **Privacy-safe owner analytics** — request counts, active-user totals and
   spend thresholds without retaining translation or transcription content.

A broad screen-reading overlay remains intentionally deferred because it would
require much wider Android accessibility/screen-capture permissions.

## Development checks

Use the cloud dependencies, not the Windows/GPU requirements:

```sh
python -m pip install -r cloud_api/requirements.txt 'pytest>=8,<10'
python -m pytest cloud_api -o python_files=test_*.py -q
node --test cloud_api/web/*.test.mjs
```

GitHub Actions runs tests only; pushing does not deploy the app.

The Android source also has its own compile/JVM workflow. A release APK still
has to be built with the existing private signing material on the owner PC.

## Documentation

- [Current Codex state and next steps](CODEX_CURRENT_STATE.md)
- [Cloud handoff and deployment](CLOUD_HANDOFF.md)
- [Cloud API setup](cloud_api/README.md)
- [Current UI design](DESIGN.md)
- [Android app and build notes](android/LinguaFusionMobile/README.md)
- [Historical offline Windows README](README_OFFLINE_DESKTOP.md)
- [Historical Windows handoff](HANDOFF_README.md)
