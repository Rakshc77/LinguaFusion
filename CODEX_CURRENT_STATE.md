# LinguaFusion — current Codex handover

## Current update — September 10, 2026 (supersedes history below)

Work branch `codex/usability-update` starts from `origin/main` commit `879fcaa`.
Read `CURRENT_STATE_CLAUDE.md` for the current product baseline. Android source
is now committed in `android/LinguaFusionMobile`; old missing-source notes below
are historical. Keep existing phone-only offline functionality, Studio/Minimal
and Day/Night pill. Offline must never require a PC backend.

Implemented: Firebase Forgot password with email validation, duplicate submission
protection and neutral account-existence response; Online language swap with
validated device-local pair persistence; browser recording microphone level and
Cancel that releases capture without uploading. Existing Transcript-to-Translate,
OCR-to-Translate and result-to-Say-it flows are retained. Native recording's
existing Stop/Cancel dialog is unchanged. No paid requests are made by swapping.

Online interface version: `2026.09.10.1` in updater, metadata and service worker.
No CSS, native code, APK, signing identity or offline assets changed. After Cloud
Run deployment, installed apps can receive this Online interface through Settings
> Check for updates. No new APK is needed. Future native/offline changes require
a compatible signed APK and release metadata.

Validation: JavaScript 59 passed; cloud Python 183 passed, 8 skipped (optional
QR/Pillow dependencies); Android contract 24 passed, one failed because the
existing debug.keystore is absent locally. Never generate a replacement key or
weaken that gate. Physical-device UI and real reset-email delivery remain untested.
No paid provider requests were made for validation.

Source changes are not deployed. Publication is authorized; verify remote commit
before claiming publication. Previous terminal pushes lacked authentication; the
owner also has a working PC Git-bundle import/push workflow. Use the existing
Cloud Shell `scripts/deploy_cloud_update.py --build`, then `--status BUILD_ID`,
then `--promote BUILD_ID` only after SUCCESS, preserving secrets and limits.
Do not scan for cloud credentials. This workspace is Linux, not the owner's PC.

Claude's reported baseline (not reverified live here): Android 1.14/versionCode15,
22,433,279 bytes; Cloud Run revision `00047-88c`. Firebase owner approval and
provider caps/consent remain unchanged. Offline transcription/translation runs
on the phone for English, German, Arabic, Spanish and French. Shared appearance
sync script is unnecessary for this Online-only change.

## Historical handover (superseded where inconsistent above)

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

## Offline Android implementation recovered

The owner supplied the original 22 MB Android APK on September 9. It is a real
phone-only offline app, separate from the 33 KB Online WebView wrapper that is
currently published from this repository. It contains native whisper.cpp,
ML Kit offline translation, on-device OCR and a local Offline screen with model
and language-pack downloads. The downloaded speech model serves all languages;
translation packs are managed per language.

The APK's local UI includes “Work offline on this phone” and exits back to
Online through the native `linguafusion-mode://offline` route. The hosted Online
interface now restores that handoff only when this original app marks the
WebView with `LFNativeOfflineMode`; ordinary browsers and the small Online-only
wrapper never see the control. No PC backend is involved.

The corresponding full Android source and signing material are not in this
Git repository yet. Do not replace the published small APK with this binary or
claim an APK update path until the owner provides the original source and the
signing situation is verified. Initial offline language scope remains English,
German, Arabic, Spanish and French; do not add Hindi or Odia to this phone-only
release without a new decision.

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
