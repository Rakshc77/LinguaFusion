# LinguaFusion — current Codex handover

Updated: September 9, 2026.

## Read this first

The owner approved the Studio and Minimal preview designs and requested
implementation and an up-to-date Codex handover. Source work is on
`codex/studio-minimal-appearance`, based on cloud checkpoint `4947729`, now merged with Claude’s GitHub
checkpoint `4afa66a` (owner monthly pricing reminder and provider diagnostics).
First appearance commit: `172c426`; subsequent UI polish and this handover are
recorded in the branch’s latest commit. Check `git log -3 --oneline`.

**Publication status:** the owner explicitly authorized publishing
`codex/studio-minimal-appearance` to the public GitHub repository in this
conversation. The subsequent push reached GitHub but failed with missing
username/authentication (`terminal prompts disabled`). The GitHub plugin was
suggested for connection; no successful connection or push is verified yet.
No further publication permission is needed for this prepared branch. Connect
GitHub with repository access, push, and verify the remote commit hash before
claiming another Codex environment can retrieve it.

**Deployment status:** this session has not deployed these changes. The live
Cloud Run revision has not been inspected. Automatic review blocked Google
credential discovery as outside implementation/handover scope. Deployment
identity remains unverified; do not scan for credentials or copy private keys.
Use the approved deployment flow when separately authorized and authenticated.

## Current product

- Cloud Run: service `linguafusion-cloud-pilot`, project `linguafusion-f24fe`,
  region `europe-west3`.
- App: https://linguafusion-cloud-pilot-jl77ipbeua-ey.a.run.app/pilot/
- Firebase sign-in and owner-approved access; Firestore policies/spending ledger.
- OpenRouter via DeepInfra: translation and pronunciation. Groq: transcription.
  Google Vision: image OCR. No PC or tunnel required for the cloud app.
- Current cloud translation choices: English, German, Spanish, Hindi, Arabic,
  Odia. French is not yet added. Transcription uses multilingual
  `whisper-large-v3-turbo` with automatic language detection.
- Android 1.5 / version code 6 uses native AudioRecord to bypass the S26 Ultra
  WebView microphone failure. The owner explicitly confirmed smooth recording
  and transcription. Broader hardware/language coverage is still unverified.
- No APK binary or signing identity was changed in this UI update.

## Implemented in this branch

Only Studio and Minimal remain in the CLOUD UI registry and stylesheet.
Day/Night and font selections are independent. Studio day is Warm Editorial
parchment/brown/terracotta; Studio night is Sunset rose/plum; Minimal is neutral
in both modes. See DESIGN.md for exact tokens.

Settings > Appearance offers theme and typography. The redundant Day/Night
selector has been removed; the header pill remains the single mode control.
Added legacy preference migration,
blocked-storage tolerance and theme-color metadata updates. Added “Match the
look” typography: Studio has editorial headings/results, Minimal sans-serif.
Existing chosen fonts are preserved. Replaced navigation emoji with inline line
icons, refined headings/result surfaces and spacing, retained all feature,
authorization, consent, recording and export controls. Updated manifest colors
and static cache version. The historical desktop/PC-paired themes were not changed.

## Online update control

Settings now contains App updates, showing Online interface version
`2026.09.09.2`. Check for updates fetches public uncached metadata with a timeout.
A different release offers an explicit Reload and update action; checking alone
does not reload. Active recording or processing blocks reload, and the UI warns
that unsaved text/results must be copied or downloaded first. Service-worker
activation completes before reload where supported. Errors leave the page open.
This updates the hosted interface, not the signed Android APK or offline models.
For each interface release, bump `APP_VERSION` in `updates.mjs`,
`app-version.json`, and the cache version in `sw.js` together.

User-facing native Android Cloud labels now say Online in source. Native labels
require a signed APK rebuild; the current APK was not rebuilt or replaced.

## Validation in this workspace

- 146 Python cloud tests pass; 8 invite-image tests skip because optional qrcode
  and Pillow dependencies are absent.
- 54 Node tests pass, including three appearance behavior tests and existing
  recording/auth/client tests.
- Browser-rendered all four palettes at 412px width using the shipped HTML/CSS
  with synthetic transcript content; no horizontal overflow. This is visual
  verification of the static UI, not an authenticated production test.
- Provider calls were not made and no AI budget was consumed by these tests.
- CPU-only Python 3.12 and Node 24 used locally; CI specifies Python 3.11/Node 22.
- APK hardware validation of the new appearance and live deployment checks remain.

Commands (root pytest defaults otherwise select legacy tests):

```sh
python -m pip install -r cloud_api/requirements.txt 'pytest>=8,<10'
python -m pytest cloud_api -o python_files=test_*.py -q
node --test cloud_api/web/*.test.mjs
```

## Offline Android plan — not implemented

Approved initial language scope: English, German, Arabic, Spanish, French.
No Hindi or Odia in the initial OFFLINE release; this does not authorize removing
those languages from the existing cloud app.

Proposed: ML Kit downloadable translation packs plus a multilingual
whisper.cpp model on the phone. Benchmark Base versus Small/quantized variants
on the S26 Ultra; validate Arabic dialects, noise, latency, heat and battery.
Start with record -> stop -> transcribe -> translate, not live streaming.

Required work: maintainable Android dependency/NDK build, packaged offline UI
that does not require cloud sign-in, explicit Online/Offline selection, resumable
verified model downloads/removal, storage display, local inference lifecycle
and cancellation, and airplane-mode cold-start tests. Additional supported
translation languages can use downloaded packs; Whisper-supported languages
usually share one multilingual model. No offline inference is currently shipped.
Storage estimates discussed with the owner were approximate, not measured builds.

## Spending, privacy and operations

Preserve existing model/provider allowlists, provider price/token caps,
`data_collection: deny`, no fallback routing, authorization and paid-consent gates.
No OpenRouter dashboard settings were changed by this session.

Last known handoff snapshot (September 8, NOT a live balance): shared lifetime
ceiling USD 27, committed/held USD 0.46, remaining USD 26.54. This is an application
ledger, not a provider invoice. Do not reset it. Google hosting charges are separate.
Claude’s `4afa66a` removes the October 8 hard stop. The owner now gets a monthly
pricing-review reminder and can acknowledge review; provider limits remain.
Owner-only failure diagnostics are preserved.

## Next steps

1. Complete the GitHub connection, publish the already-authorized branch, and confirm the remote hash.
2. Deploy through the existing image-only Cloud Build/Run tooling after deployment
   authorization and identity are established. GitHub Actions tests do not deploy.
3. Verify new appearance on the actual phone, all six views, consent and downloads.
4. Start the offline Android work above as a separate implementation task.

Never replace the published APK with a different signing key. The existing
owner key is not in this checkout. See CLOUD_HANDOFF.md for the build allowlist,
known image digests and rollback constraints. Historical desktop work is in
HANDOFF_README.md and README_OFFLINE_DESKTOP.md; it is not the cloud baseline.
