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

## Current appearance

Only Studio and Minimal are offered by the cloud app. Both have Day and Night
modes. Studio day uses Warm Editorial parchment and terracotta; Studio night
uses Sunset rose on plum. Minimal is monochrome. Typeface selection is
independent; “Match the look” uses editorial headings for Studio and sans-serif
for Minimal. Previously selected typefaces are preserved.

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
- [Historical offline Windows README](README_OFFLINE_DESKTOP.md)
- [Historical Windows handoff](HANDOFF_README.md)

Android provides phone-only Offline translation and transcription for English,
German, Arabic, Spanish and French. Version 1.16 adds a native selected-text
translation surface for WhatsApp and other Android apps; see the Android README.
