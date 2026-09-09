# LinguaFusion

PC-independent cloud translation, transcription, pronunciation guides and OCR,
with an Android app and browser interface. The original offline Windows app
remains a separate client.

## Continue in Codex

Read **[CODEX_CURRENT_STATE.md](CODEX_CURRENT_STATE.md)** first, then
[CLOUD_HANDOFF.md](CLOUD_HANDOFF.md) for deployment and signing constraints.
Current source branch: `codex/studio-minimal-appearance`.
Do not start from `main`: it lacks the newer cloud implementation.

Cloud app: https://linguafusion-cloud-pilot-jl77ipbeua-ey.a.run.app/pilot/
The latest appearance work is source-only; it has not been deployed by this session.

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

## Documentation

- [Current Codex state and next steps](CODEX_CURRENT_STATE.md)
- [Cloud handoff and deployment](CLOUD_HANDOFF.md)
- [Cloud API setup](cloud_api/README.md)
- [Current UI design](DESIGN.md)
- [Historical offline Windows README](README_OFFLINE_DESKTOP.md)
- [Historical Windows handoff](HANDOFF_README.md)

Offline Android translation and transcription are planned, not implemented.
The first planned languages are English, German, Arabic, Spanish and French.
