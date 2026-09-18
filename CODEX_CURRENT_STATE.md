# LinguaFusion — current Codex handover

## Streamlined interface and cohesive motion — September 18, 2026

Branch `codex/streamlined-motion` starts from published `main` commit `c67b966`
(Online `2026.09.16.3`, Android 1.21/versionCode 22). It prepares Online
`2026.09.18.1`, Android 1.22/versionCode 23 and Windows desktop
`1.0-rc2.17-streamlined-motion`.

The Online and bundled Android Offline interfaces now use concise page headings,
shorter guidance, compact result actions and collapsible technical/owner detail.
The Online landing page shows iPhone visitors a clear instruction to scroll down
and create an account. Per-action paid-use checkboxes were removed because this
private app is not commercial. Each deliberate signed-in action still sends
`paid_consent=true` for API compatibility; Firebase approval, owner policy,
monthly budgets, provider allowlists and request limits remain server-enforced.

Motion is independent of Studio/Minimal and day/night. **Lively** is the default;
the Settings **Reduce motion** switch selects the quieter **Balanced** profile.
Operating-system reduced-motion always takes precedence. Views and successful
results enter once, buttons have restrained tactile feedback, processing uses a
contained sweep, recording pulses and bottom navigation has a compact active
indicator. The Windows desktop retains its established internal preference IDs
for compatibility but presents them as Lively, Balanced and Off.

Validation in this workspace: all 73 browser tests pass; all 51 cloud
route tests pass; 34 of 37 combined Android/static desktop contracts pass. The
three remaining checks are environment-only here: the private Android signing
keystore is intentionally absent and PySide6 is unavailable for the two headless
desktop runtime tests. Re-run the complete Android contract and desktop smoke
suite on the owner PC before publishing. Do not replace the signing key. The APK
asset and `android-app.json` remain at published Android 1.21 until that rebuild.

Release state: source-only. Merge, deploy Online `2026.09.18.1`, build/publish
Android 1.22 from the owner PC, and rebuild the Windows EXE. No Cloud Run, APK or
desktop binary was published from this branch.

### Remaining to-do checklist

1. Review and merge `codex/streamlined-motion` into `main`.
2. In Cloud Shell, pull `main`, build Online `2026.09.18.1`, wait for `SUCCESS`,
   promote it and verify the new Cloud Run revision is ready.
3. On the owner PC, pull merged `main` and run the complete Android contract with
   the private `debug.keystore` present. Build Android 1.22/versionCode 23 with
   the existing key; never generate a replacement.
4. Run `scripts\publish_android_apk.py`, verify `android-app.json` reports 1.22,
   commit the regenerated APK and metadata, push them, then deploy that commit so
   **Check for updates** offers Android 1.22.
5. On the owner PC, run the two PySide6 desktop smoke/usability tests and rebuild
   the clickable Windows EXE from merged `main`.
6. Physical-device checks: iPhone landing advisory and account creation; Android
   Online/Offline Lively default; Reduce motion → Balanced; operating-system
   reduced motion; recording pulse; result reveals; Read Aloud; owner requests.
7. Verify the live UI no longer shows per-action paid-use consent checkboxes and
   that server-side account approval, budgets and request limits still reject an
   unauthorized or over-limit request.

---

## Android Read Aloud voice fallback — September 16, 2026

Android 1.21/versionCode 22 fixes a physical-device failure where Android
advertised a high-quality German network voice, accepted it, then failed after
playback began. Native Read Aloud now prefers an installed local voice in both
modes, retries Online once using the phone's preferred system voice, and opens
Android voice settings with an actionable message only if both attempts fail.
Offline remains strictly local. Source is not published until the owner-PC APK
is rebuilt with the existing signing key and the updated APK asset is deployed.

---

## Desktop phone shell and owner account — September 16, 2026

Branch `codex/desktop-phone-owner` starts from published `main` commit
`fde835a` (Online `2026.09.16.2`, Android 1.20/versionCode 21). It prepares
Online `2026.09.16.3` and Windows desktop
`1.0-rc2.16-phone-shell-owner`; Android source and APK are unchanged.

Windows primary navigation now matches the phone exactly: Speak, Translate,
Read, Say it, Model and Settings. Speak, Translate and Read map to the native
Speech, Translate and OCR workspaces. Say it embeds the phone's authenticated
Online pronunciation guide; Model contains local language readiness, installer
access, GPU safety and Ollama status. Notes, Tasks, document Reader, Remote Access,
global search, recents and the right inspector remain in legacy source where
needed for data compatibility but are no longer built into primary navigation.

Settings has two explicit sections. **Account & owner** embeds the fixed
`/pilot/?embed=desktop&view=account` cloud route in Qt WebEngine, retaining the
phone app's Firebase sign-in, password reset, approval request, owner-only
policy checks, one-time invite links/QR codes, people/limits, usage and provider
diagnostics. Authentication tokens stay inside the existing web client and are
not copied into Python. **Desktop preferences** contains Studio/Minimal,
typeface, motion, startup and system-tray behavior. The embedded route hides
only the redundant phone bottom navigation; unapproved users still see the
normal request-access flow, and non-owner accounts never receive owner data.

Validation in this Linux workspace: Python syntax and static desktop-embed
contracts pass; all 72 browser tests pass. PySide6 is unavailable here, so the
headless desktop smoke/usability tests require the Windows owner environment or
CI. Superdesign generation was not run because its CLI's separate analytics
telemetry was blocked by the execution policy; implementation used the approved
existing Studio/Minimal system directly.

Release state: source-only. Merge the branch, deploy Online `2026.09.16.3`, then
rebuild the clickable Windows EXE from current `main`. No Android rebuild is
needed for this desktop/account change.

---

## Unified languages and desktop Studio — September 16, 2026

Branch `codex/unified-languages-desktop` starts from published `main` commit
`3eb4b3d` (Online `2026.09.16.1`, Android 1.19/versionCode 20). It prepares
Online `2026.09.16.2`, Android 1.20/versionCode 21 and Windows desktop
`1.0-rc2.15-unified-languages`.

One canonical ordered catalogue now covers English, German, French, Spanish,
Hindi, Arabic and Odia. French was added to desktop translation, transcription,
OCR, Piper voice configuration, diagnostics and the one-time model installer;
the Online and legacy connected interfaces now expose the same seven choices.
The Windows installer also checks/downloads the other missing Piper, MMS and
Tesseract assets. Desktop Settings reports Voice, Speech, OCR and Translation
readiness for every language.

Android phone-only Offline remains intentionally limited to English, German,
French, Spanish and Arabic for speech/translation; Hindi and Odia were not
misrepresented as Offline core support. Android Offline OCR remains Latin-only
(English/German/French/Spanish), while Online and desktop OCR cover all seven.
Read Aloud accepts all seven Online and opens Android's trusted voice-data
installer/settings after a user-initiated attempt when a device voice is absent.

The Windows UI now uses the same approved Studio/Minimal system as the phone:
Studio Day is warm editorial, Studio Night is sunset rose on plum, Minimal is
monochrome, and the top-bar Day/Night pill is the only color-mode selector.
The core page names/order and copy are aligned without removing desktop-only
Reader, Notes, Tasks or Access capabilities.

Release state: source changes are not deployed or published yet. Before release,
run the Python/browser/Android contracts, push/merge this branch, deploy Online,
then build and publish Android 1.20 on the owner PC with the existing signing key.
Do not replace or regenerate that key. Desktop users can install all local packs
with `scripts\install_language_models.ps1`.

---

## Five-minute cloud transcription — September 16, 2026

Branch `codex/cloud-transcription-5min` starts from published `main` commit
`8ea60ad` (Online `2026.09.14.1`, Android 1.18/versionCode 19). It raises the
paid Online recording and saved-audio limit from 60 seconds to five minutes.
The browser and Android native recorder both stop at 300 seconds; the strict
mono 16 kHz/16-bit WAV remains device-created and is now capped at 10 MB.

The cloud request middleware allows the multipart framing margin only on the
transcription route, extends the upload deadline, and preserves OCR's existing
limit. The Groq adapter independently verifies duration, format and exact data
length before dispatch. Browser, provider and Cloud Run request deadlines are
extended so a valid five-minute upload is not cut off by the former one-minute
deadline. The deployment helper now sets the existing Cloud Run service request
timeout to 150 seconds while preserving its identity, secrets and other limits.

Source versions are Online `2026.09.16.1` and Android 1.19/versionCode 20. They
remain source-only until tests pass, the cloud image is promoted, and Android
1.19 is rebuilt/published on the owner PC with the existing signing key.

---

## Read Aloud implementation — September 14, 2026

Branch `codex/read-aloud` starts from `main` commit `02dbc32`. It implements the
roadmap immediately below and supersedes its “planned, not implemented” wording.
Online source is `2026.09.14.1`; Android source is 1.18/versionCode 19. The live
service and published APK remain Online `2026.09.13.3` and Android 1.17 until
the normal Cloud Run promotion and owner-PC signed APK publication are completed.

Translation, transcription and OCR result cards now have Read Aloud/Stop and
0.75×, 1× and 1.25× speed controls. Translation uses the returned target
language; Online Transcript and OCR expose a small manual **Read as** selector
because those provider responses do not include a reliable language code.
Browser/iPhone uses Web Speech synthesis. Playback makes no LinguaFusion paid
provider request. Only one utterance can run, and speech stops before recording,
on hidden/page exit, logout/account cleanup or result replacement.

Android uses native `TextToSpeech`, chunks below the engine input ceiling and
tracks completion/error. The hosted page receives only an origin-restricted
AndroidX WebMessage object, with native validation of id, text, language and
rate; it still receives no broad `addJavascriptInterface`. Offline uses the
existing bundled-page bridge and accepts only voices that report no network
requirement. The compact selected-text/WhatsApp translation surface also reads
its result aloud. Initial Offline scope remains English, German, Arabic,
Spanish and French.

Validation so far: all 72 browser tests pass; the relevant cloud/static Android
set passes 82 tests with only the intentionally unavailable private-keystore
test excluded. The full cloud suite additionally needs the normal qrcode test
dependency in CI; this environment lacks it. Android Gradle compilation must be
confirmed by GitHub Actions because this workspace cannot download Gradle. No
provider calls, deployment, APK build or signing operation has been made.

Before release: confirm both GitHub workflows; physically test each of the five
Offline voices and at least one Online result on the owner's Samsung; check
iPhone Safari and Home Screen playback; deploy Online; then build/publish signed
Android 1.18 on the owner PC without changing the key.

---

## End-of-night handover — September 13, 2026

This section supersedes any older deployment, APK-version or next-step wording
below. The work is concluded for tonight with no active build or promotion.

### Verified live baseline

- GitHub `main` contained Android publication commit `40e20d3` before
  tonight's documentation-only commits.
- Live Online interface: `2026.09.13.3`.
- Live Android metadata: `1.17` / versionCode `18`, 22,450,547 bytes,
  SHA-256
  `65d1373ab0178a4f0554817d1aef23af589fb6674cefeec4f6f4282f94e2d71c`.
- Cloud build `b40174e4-105b-42ec-a263-10ceda001439` succeeded and its
  different image digest was promoted.
- Owner one-use invitation links/QR codes and the repaired secure route
  allowlist are live. Android 1.17 contains the native access-request
  notification channel and permission flow.
- No source, APK, provider configuration, secrets, spend limits or signing
  material were changed in tonight's final documentation pass.

### Next feature: Read Aloud (planned, not implemented)

Build Read Aloud as a device-synthesized output action for Translation,
Transcription and OCR results. It must not make an OpenRouter, Groq or other AI
request; LinguaFusion must not upload or retain synthesized audio.

Behavior contract:

1. A Translation result speaks its target language; a Transcript or OCR result
   speaks its selected/detected source language.
2. Each card exposes **Read aloud** and **Stop**, plus 0.75× / 1× / 1.25× speed.
   Only one utterance may be active app-wide.
3. Stop speech when another result starts, the result is removed, the account
   changes or the user logs out. Do not add background playback in the first
   release.
4. Keep **Say it** as the separate pronunciation-guide feature.
5. Guarantee English, German, Arabic, Spanish and French only when a matching
   device voice is installed. Missing voices need an honest, actionable message.
6. Store voice/rate preferences locally only. Never log spoken text.
7. Voice packs remain OS-managed instead of being bundled, keeping APK growth
   small. A separate OS voice download may still be needed.

Platform implementation:

- Browser and iPhone PWA: use `speechSynthesis` and
  `SpeechSynthesisUtterance` after a real user tap; refresh the voice list on
  `voiceschanged`; fall back cleanly when speech synthesis or a matching voice
  is unavailable. Because the current iPhone product is a PWA, do not describe
  native `AVSpeechSynthesizer` support unless a native iOS wrapper is later
  built.
- Android installed app: use native `android.speech.tts.TextToSpeech`. In
  Offline mode, select only a voice whose
  `isNetworkConnectionRequired()` is false. Split long content below
  `TextToSpeech.getMaxSpeechInputLength()`, track completion/errors with
  `UtteranceProgressListener`, and call `stop()`/`shutdown()` during
  lifecycle cleanup.
- Hosted Online page to Android: use
  `WebViewCompat.addWebMessageListener` restricted to the exact trusted cloud
  origin. Do not add a broad `addJavascriptInterface`. Validate message type,
  locale allowlist, text length and rate natively; expose no unrelated native
  capability.
- Offline bundled page: extend its already trusted Offline bridge with the same
  narrow play/stop/state contract.

Recommended delivery order:

1. Result-action state machine, language routing, limits and browser tests.
2. Shared Online UI plus browser/iPhone PWA speech.
3. Android native speech bridge plus Offline UI synchronization.
4. Android 1.18/versionCode 19 owner-PC signed build, physical five-language
   Android testing, iPhone Safari/Home Screen testing, then Cloud Run promotion.

Do not bump versions or start a paid/provider test until implementation begins.
Preserve the existing Android signing key.

### Prioritized product backlog

1. Read Aloud.
2. Two-person Conversation mode with large alternating controls and explicit
   confirmation before paid Online processing.
3. Opt-in, searchable, device-local history and favorites/phrasebook with
   export and complete deletion.
4. Offline download manager for speech model, translation packs and voice packs,
   including sizes, Wi-Fi-only behavior and safe removal.
5. Camera reading improvements: crop, rotate, select a sentence, then translate
   or read that selection.
6. Accessibility: larger text, high contrast, reduced motion, haptics and
   one-handed result actions.
7. Privacy-safe owner metrics: request/user counts and spend thresholds without
   translation or transcription content.

Continue to defer a full-screen translation overlay: it requires broad
Accessibility or screen-capture access and is inconsistent with the current
least-privilege design.

### Tomorrow's clean starting point

Start from the latest remote `main`, read this section and
`CLOUD_HANDOFF.md`, then create a dedicated Read Aloud branch. First implement
and test the engine-independent result-action contract; do not begin with native
bridge code. Re-fetch `main` before branching because the owner's local
worktree may still be behind or contain unrelated changes.

---

## Owner invite phone-test repair — September 13, 2026

PR #9 was squash-merged into `main` as `2b30718`, superseding the
deployment notes immediately below. The first phone test exposed two separate
issues: the secure browser client had not allowlisted the newly added invite
routes, producing **Unsupported cloud request**, and Android WebView does not
implement the browser Notification API.

Online interface `2026.09.13.3` now permits only the exact
`/owner/invites` collection path and a revoke path ending in a 64-character
lowercase hex digest. Malformed or query-appended variants remain blocked.
HTTP 410 now explains that an invitation is expired, revoked or already used.

Android source is now 1.17 / versionCode 18. The installed app implements its
own notification channel and Android 13+ permission request. The hosted page
still receives no JavaScript interface: notification permission/show actions
use fixed custom schemes, require the genuine cloud origin, require a real tap
for permission, use fixed native text and are rate-limited. Tapping an alert
opens Online mode at Owner access requests. The shared stylesheet was synced
into Offline because this source change now requires an APK rebuild.

Validation: 66 browser tests and 200 cloud tests passed locally; 29 Android
contracts passed with only the intentionally owner-PC-only private-keystore
check unavailable. GitHub Cloud pilot and Android source/Gradle checks both
passed on PR #9. Deploy current `main` to make invite creation work. Then build,
publish and deploy the signed Android 1.17 APK on the owner PC, preserving the
existing private signing key, to make native alerts work inside the installed
Android app. Do not generate a new keystore.

## Current owner invitations and access alerts — September 13, 2026

PR #8 was squash-merged into `main` as `485d282`. Online interface version
`2026.09.13.2` adds an owner-phone invitation manager under **Settings >
Owner controls**. The owner can create one-use links and QR codes lasting 1 hour,
24 hours or 7 days, share them with the phone share sheet, see active/used/
expired/revoked status and revoke an unused link. The first verified Firebase
account that redeems a link is automatically approved with the existing standard
allowance; no second account can use it.

Invitation bearer tokens travel only in a URL fragment, are removed from the
visible address after capture, and are stored in Firestore only as SHA-256
digests. Redemption is transactional and idempotent for the winning account, so
an interrupted grant can retry without reopening the link to someone else.
Names, organisations and verified email handling keep the existing access-request
privacy boundary.

Pending ordinary requests now put a count badge on Settings. The owner may enable
a local phone notification while the owner interface is open and visible; tapping
it focuses the app and opens Access requests. This is intentionally not described
as background web push. The existing verified Cloud Monitoring owner email alert
for `access_request_submitted` remains the reliable closed-app notification.

Validation passed locally (64 browser tests; 200 cloud tests), JavaScript syntax
and whitespace checks passed, and GitHub's Cloud pilot workflow passed on PR #8.
The change is merged but needs one Cloud Run build/promotion from current `main`
before it is live. It is hosted/online-only: do not rebuild or replace Android
APK 1.16, its signing key or offline models.

## Current iPhone recording recovery — September 13, 2026

PR #7 was squash-merged into `main` as `b2fce57`. Online interface version
`2026.09.13.1` adds recovery for iPhone Home Screen microphone failures: an
explicit retry, an **Open in Safari** route, and **Choose saved recording** for
a Voice Memo saved to Files. Saved audio is decoded locally, mixed/resampled to
the existing mono PCM WAV contract and only then sent after paid-use consent.

The recorder now watches audio tracks for an ended or persistently muted state,
fully releases the failed stream and audio context, and never uploads the partial
capture. This is an online/PWA change only; Android APK 1.16 and offline assets do
not need rebuilding. Validation passed locally (64 browser tests; 183 cloud tests,
8 optional skips) and GitHub's Cloud pilot tests passed on PR #7. Cloud Run must
be rebuilt and promoted from current `main` before this version is live.

## Current Android integration — September 12, 2026

PR #6 was squash-merged into `main` as `01370a6`. This section
supersedes older source/version notes below. The source and published APK are Android 1.16 / versionCode 17. The owner-PC
signed build was committed to `main` as `a5a0741` on September 13.

Implemented a compact native **Translate with LinguaFusion** activity for
Android `ACTION_PROCESS_TEXT` and text-only `ACTION_SEND`. In an editable field,
the person can select a passage, preview an on-device translation and return it
to the caller with **Replace selected text**. Read-only or shared WhatsApp text
offers **Copy and return**. Language choices and swap are included and the pair
is remembered; only the selected text is processed and text content is never
persisted.

The translation reuses the existing Offline ML Kit engine and downloaded packs
for English, German, Arabic, Spanish and French. It requests no Accessibility,
screen-capture, overlay or background clipboard permission. This keeps the
feature phone-only and avoids reading unrelated messages. A full-screen overlay
is deliberately deferred; it requires much broader access and the current
on-device OCR cannot read Arabic script.

The activity uses Studio day colors and Sunset night colors based on Android's
day/night configuration, first-strong text direction for Arabic, an explicit
on-device/private label, progress and actionable missing-pack feedback. It
returns a replacement only when Android marks the original selection editable.

Validation: GitHub's Android source check passed on PR #6 at `d87925e`,
including all applicable build contracts, native Java compilation and JVM tests.
The cloud pilot suite also passed. The private-keystore check remains limited to
the owner PC because the signing key is intentionally absent here. Physical
WhatsApp testing on the owner's Samsung remains the final behavior gate.

The existing signed APK 1.16 must keep its current signing key. Do not generate
a replacement key: it would not install over existing copies. PR #7 changes only
the hosted Online interface, so deploy Cloud Run without rebuilding the APK.

## Previous Codex handover

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
