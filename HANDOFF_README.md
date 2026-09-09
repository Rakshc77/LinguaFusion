# LinguaFusion — Historical Windows Project Handoff

For the current cloud/Android project, read [CODEX_CURRENT_STATE.md](CODEX_CURRENT_STATE.md).
The August desktop checkpoint below is historical and is not the current cloud roadmap.

## September 8: hosting approved; durable pilot controls prepared

User approved hosting and explicitly postponed Superdesign. Do not retry the
previous elevated npm rejection. Proposed Frankfurt + US$5/month hosting alert
in an asynchronous question; no answer received yet. API testing allowance stays
a separate US$5 lifetime allowance, NOT renewed by hosting.

Added cloud_api/firestore_policy.py: bounded small-pilot transactional approval,
monthly usage/budgets, shared lifetime cap, prior-spend carry-forward, retained
holds, and idempotent settlement. app.py selects via LF_CLOUD_POLICY_BACKEND;
Cloud Run now rejects local/missing controls and emulator configuration. Updated
Docker allowlist and review-only YAML. No automatic ledger bootstrap.

50 Python tests passed (nine new offline policy/Cloud Run guard tests). No real
Firestore tests yet. Read-only scripts/check_cloud_hosting.py confirmed hosting
APIs disabled (run/firestore/cloudbuild/artifactregistry/secretmanager); Vision
enabled. Runtime account only unconditional Service Usage Consumer. Inventory
of databases HTTP403, so database existence/location unknown.

No hosting resources created and no paid AI requests made this turn. Providers
still isolated smoke-test adapters; UI pronunciation pane still pending. See
cloud_api/HOSTING_READINESS.md for explicit gates, especially preserving existing
test holds and preventing a second independent US$5 ledger at cloud cutover.

## Latest: pronunciation / transliteration requested, partial prototype

User asks Latin pronunciation pane for non-Latin languages, notably Odia/Arabic.
Discovered existing backend transliteration helper explicitly disables Hindi
romanization for prior quality reasons; do not blindly restore unidecode.
Added PilotProviders.romanize optional paid Gemma3-27B call with .20 USD/M price
ceiling, DeepInfra only, no fallback, same .01 hold. Preserves native text,
flags approximate, rejects native-script letters and incomplete output.
translate now permits explicit Gemma test model (Nemo still default).
Live -ReadingGuide run made four requests: Arabic guide failed validation;
Odia native+Latin guide returned, needs native-speaker quality review. Report:
cloud_api/local-data/synthetic-tests/reading-guides.json. Total expected holds .16.
Nine focused adapter/budget tests pass. Interface pane NOT implemented yet.
Superdesign skill preflight failed npm EACCES/network; reported UI workflow paused.
Need implement actual pane (source/translation links, toggle/copy, LTR, clear stale
result on edit/switch/logout, explicit cloud consent), verify Arabic guide and
Hindi/Odia quality, desktop/mobile scope. Keep exports native unless opted in.

## Latest September8: OCR works; Nemo multilingual quality NOT approved

After user billing update, final OCR retry SUCCEEDED with text 'LinguaFusion test:
Train 14:30'. Uses developer ADC; runtime service account not tested. Holds .06
before multilingual sweep. Translation PS now accepts -AllLanguages; six live
synthetic samples ran: en/de/es/hi produced plausible complete text, ar produced
mixed English 'bring' and poor phrasing, or returned429 (no output). Do NOT label
all languages passed based on number/script smoke checks. Added fixture-specific
untranslated-word check for future runs (no repeat paid run after patch).
Report cloud_api/local-data/synthetic-tests/translation-languages.json records
original outputs. Holds expected .12 total; actual provider charge unreconciled.
TestBudget.summary now separates held/recorded/remaining; added unit test.
No UI activation, hosting, retries or model upgrades. Need choose/test better
Arabic/Odia translation route before enabling cloud translation universally.

## September 8 live media checks — Google billing blocks OCR

scripts/test_cloud_media.ps1 creates synthetic System.Speech WAV and System.Drawing
PNG, loads Groq DPAPI credential privately, runs test_cloud_media.py. Live Groq
Turbo passed: Hello/train2.30/ticket correctly transcribed. Read-only Google IAM
confirmed backend service account unconditional Service Usage Consumer role.
Vision is ENABLED but OCR failed403; one OCR-only diagnostic retry confirmed
BILLING_DISABLED. No billing settings changed. Uses developer ADC, not deployment
service-account impersonation. cloudbilling billingInfo read also403 SERVICE_DISABLED
(billing API unavailable); this is distinct from Vision response BILLING_DISABLED.
Adapters now expose only allowlisted Google error reasons, never raw error bodies.
Total holds now USD .04 (translation .01, speech .01, two OCR attempts .02), NOT
actual invoiced spend. Samples in ignored cloud_api/local-data/synthetic-tests.
User must link billing before OCR can succeed. No more retries until changed.

## September 8 bounded adapters and FIRST LIVE translation success

cloud_api/pilot_providers.py provides isolated smoke-test adapters for fixed
OpenRouter Nemo (DeepInfra only, fallback false, .05 USD/M input/output ceiling),
Groq Turbo (validated mono PCM WAV <=60s/4MB), Vision single PNG/JPEG <=4MB.
All reserve .01 USD BEFORE network against same lifetime TestBudget. Holds remain
even on success until reconciliation; do not display as actual billed spend.
Prices expire October8. No public UI/routes wired, no production startup changes.
39 Python tests passed, including 3 adapter mocks. Google IAM and live OCR/Groq
tests still outstanding. PNG/JPEG validation currently signature/size only.

scripts/test_cloud_translation.ps1 decrypts saved DPAPI OpenRouter credential in
actual Windows user context, passes only to child process environment, cleans up.
Ran authorized synthetic Hello/train14:30 -> German successfully (exit0), using
scripts/test_cloud_translation.py. Ledger cloud_api/local-data/combined-test-budget.sqlite3
now has .01 USD held against USD5; actual charge not yet reconciled. Console
encoding replaced umlaut in tool output, not yet established as provider issue.
No credential printed. No hosting/billing changes. Next continue live bounded
speech and OCR tests after Google IAM verification, then integrate UI adapters.

## September 8 private setup and approved combined test budget

User chose OpenRouter translation, Groq speech and Google Vision OCR; explicitly
approved USD 5 TOTAL initial testing, excluding hosting. OpenRouter dedicated
key screenshot showed USD5 limit. Groq key reportedly ready. Vision enabled;
service account supplied: linguafusion-be@linguafusion-f24fe.iam.gserviceaccount.com.
Its IAM permissions still need verification; do not assume runtime attachment.

scripts/configure_cloud_keys.ps1 now prompts privately for OpenRouter/Groq keys,
saves Windows user/machine-bound DPAPI SecureStrings in ignored local-data;
skips existing files, no network/inference. User must run it interactively.
No secrets entered/read by agent. Syntax checked, not run with real keys.
cloud_api/test_budget.py is a separate lifetime combined USD5 reservation ledger
(not monthly/per-user); restart/concurrency/unknown-charge tests pass.
36 Python tests passed. IMPORTANT: ledger is NOT YET wired to paid adapters;
paid AI remains OFF. Need implement OpenRouter/Groq/Vision adapters, trusted
maximum-charge reservations + key loader, IAM read-only check, and mock tests
BEFORE real calls. Avoid claiming account-wide cost guarantee. No deployment.

## September 7 Cheaper Inference identified — discovery foundation only

User supplied https://platform.cheaperinference.com/dashboard/keys, identifying
Cheaper Inference rather than an assumed OmniRoute localhost gateway. Official
https://api.cheaperinference.com/api-reference and /docs confirm fixed
https://api.cheaperinference.com/v1, key-filtered GET /models, is_free and
cheaper_inference.billed_cost_usd (six-decimal string). Discount ceiling accepts
0–99.99, NOT a strict zero-price ceiling. Do not promise a free-labelled key
cannot bill without verifying provider-side restrictions. No key supplied.

Added cloud_api/cheaper_inference.py: read-only bounded model discovery, fixed
host, no redirects/retries/key fallback, conservative free/unknown labels, exact
provider-charge parser. Added scripts/check_cheaper_inference.py for private
getpass discovery (no persistence/inference). Four new mock tests; 32 Python
tests pass with two existing deprecation warnings. Nothing wired into live UI
or inference yet; no paid calls, secrets, billing activation or service restart.
Next: user runs private free-key discovery; verify free eligibility/restrictions,
then integrate catalog, credential storage, provider billing reconciliation and
explicit mode selection. Keep existing offline app unchanged.

## September 7 current: money tracking/model selection + OmniRoute request

User requested money spent, free/paid labels and model choice, then added
OmniRoute API integration. Asked asynchronously for official OmniRoute docs URL;
no reply yet. Do NOT assume OpenRouter or another similarly named service.

Implemented models.py catalog Luna/Terra/Sol with verified standard input/cache/
output rates USD/1M: .20/.02/1.20;2/.20/12;4/.40/20 (review2026-09-07,
expires2026-10-07). Local NLLB/Argos/Ollama listed PC-only, unavailable in pilot.
policy.py now has budgets/charges/budget audit tables; defaults ZERO USD.
Atomic monetary+attempt reservation, persistent unresolved holds on any uncertain
usage, idempotent usage settlement, per-user and owner aggregate spending.
Not invoice reconciliation, hosting totals or guaranteed account-wide cap.
Owner API accepts optional monthly_budget_usd; validated0–1000 /2decimals.
Client model must be server-allowlisted, explicit paid_consent required; no fallback.

UI has model picker, pricing, spending, owner policy editor (UID/enable/request
limit/USD budget). Real backend owner change only performed in isolated tests.
Local pilot restarted launcher39404, logs temp/cloud_spending_stdout.log and
cloud_spending_stderr.log. AI still forcibly OFF; no provider calls or spend.
28 Python tests +14 Node tests pass before final browser QA. OmniRoute remains
pending exact provider docs, auth/data-handling/free quota review and integration.

## September 7 persistent local pilot controls

`cloud_api/policy.py` adds local SQLite access controls, atomic per-user UTC
monthly attempt reservations, owner policy-change audit. Owner-only API list/
update routes added. Owner UID configured by local launcher; DB is
cloud_api/local-data/policy.sqlite3 (Git/Docker excluded, NOT included by old
backend/storage backup). Seeds100 attempts/month only on first insertion.
No text/password/token storage. Retries/errors consume reservations; disabled
users and restarts/reapproval cannot bypass limits. No UI toggle/list yet.
AI fails closed without policy store, SQLite errors503, Cloud Run refuses local
SQLite config. Still needs managed cloud persistence and real spending controls;
request counts are NOT a currency cap. All paid AI stays OFF.
Tests: cloud_api/test_policy.py covers concurrency, restart/revocation, owner
auth, failures consuming quota, no-store fail-closed and database failure.
Verified25 Python +14 Node tests pass. Restarted only local pilot8081 to activate
controls (launcher43968; logs temp/cloud_policy_stdout.log/cloud_policy_stderr.log).
Health returns200. Normal PC backend untouched. Real owner management requests
still need end-to-end testing once the management UI is connected.

## September 7 Google CLI installation / authorization handoff

Latest correction: owner reauthorized with project-owning Google account.
Read-only scripts/check_cloud_identity.py now confirms ADC quota project matches,
Firebase test user exists and is not disabled (with/without explicit quota).
Old pilot40128 cached prior credentials. Verified its executable/command line,
restarted only that pilot; PowerShell Stop-Process failed, taskkill succeeded.
New launcher9484, logs temp/cloud_pilot_reauth_stdout.log and
temp/cloud_pilot_reauth_stderr.log. User should click Check cloud access again.
Cloud AI remains OFF. No IAM changes or billing activation were needed.

Owner successfully signed into the pilot (account workspace screenshot), but
backend capabilities returned503. Owner authorized installing Google Cloud CLI.
Official dl.google.com installer verified Authenticode Valid / Google LLC;
single-user silent install completed with reporting and shortcuts disabled.
Verified Google Cloud SDK583.0.0 at
`C:\Users\rajar\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd`.
Installer retained under temp/GoogleCloudSDKInstaller.exe.
`scripts/authorize_cloud_pilot.ps1` prepared and PowerShell syntax checked.
USER MUST RUN it to complete private `auth application-default login` using
project linguafusion-f24fe. No Google consent approved by agent, no credentials
read, no paid services enabled. Next: user completes authorization then selects
Check cloud access; inspect status, troubleshoot ADC/IAM/quota only as needed.
Important: sandbox LOCALAPPDATA differs from actual rajar environment; prior
Test-Path on sandbox APPDATA was not proof of absence in the real user's profile.
Use actual user context for credential-presence checks, never print contents.

## September 7 cloud foundation prototype (current continuation)

User approved preparing the cloud pilot after the roadmap. A separate
`cloud_api/` now contains a lightweight FastAPI service, Firebase Admin token
verification with revocation checking and an explicit UID allowlist, a bounded
OpenAI Responses translation adapter, redacted request logs, a non-root
Dockerfile with allowlisted build context, and Cloud Run review YAML.
Recommended initial host is a CPU container on Cloud Run, not a migration of
the native GPU backend into Workers. Official sources and full rationale are
linked in `cloud_api/README.md`.

Cloud AI defaults OFF; no secrets were read/copied, no real provider calls or
paid resources were created, and production DNS/PC backend/phone apps were not
changed. There is no Firebase login UI in the existing apps yet. Cloud speech,
OCR, TTS, persistent permissions/data/jobs and hard spending quotas remain
unfinished. The prototype's per-instance rate limit is not a monthly spend cap.

Isolated `.venv-cloud` installed successfully; `pip check` clean. Run
`.venv-cloud/Scripts/python.exe -m pytest cloud_api/test_cloud_api.py -q`:
16 tests pass using injected identity/provider responses and an SDK-boundary
revocation test. Real Firebase identity and provider integration remain untested.
Docker is unavailable on this PC, so the Linux image is prepared but unbuilt.
Do not call this a deployed or phone-ready cloud service.

User created Firebase project `linguafusion-f24fe`; console showed Spark plan.
Project ID is now recorded in cloud configuration templates, not deployed.
Owner confirmed enabling Email/Password and supplied test account UID
`kLqjJka0cHXTCZX0TQxA2QMlzKi1`. It is now the sole approved UID in the cloud
configuration templates; this is not a deployed permission change. AI stays OFF.
Real Firebase sign-in has not been verified. Next register a Firebase web client
to prepare client sign-in; app login integration remains pending. Never request
passwords, ID tokens, or service-account private keys.
Review hosting/model/billing choices before deployment or paid AI calls.

Owner subsequently supplied exact public Firebase web configuration. Saved in
`cloud_api/web/firebase-config.mjs`; isolated `cloud-auth.mjs` implements lazy
Firebase SDK loading, session/remember-me sign-in, sign-out, refreshed bearer
headers and redacted errors. Seven Node injected-SDK tests pass via
`node --test cloud_api/web/cloud-auth.test.mjs`.

Follow-on: separate `/pilot/` sign-in/translation UI now wired to real Firebase
and fixed same-origin API routes. Production mobile/desktop unchanged. Static
asset allowlist and CSP added; Docker includes only selected pilot assets (image
still unbuilt). `scripts/start_cloud_pilot.ps1` starts loopback8081 with project,
approved UID, AI forcibly OFF. Launched hidden for user testing (launcher PID12292;
logs temp/cloud_pilot_stdout.log and cloud_pilot_stderr.log).
No ADC credentials configured by this work; real backend identity validation
remains pending and may return503. No paid calls or deployment.
14 Node tests and17 Python tests pass. Browser verified SDK load, required fields,
rejected synthetic login recovery and signed-out390x844 layout. Successful owner
login, signed-in visual states, persistence and real phones still unverified.
Next user signs in privately on localhost8081/pilot, then configure approved
Google ADC/hosting plan to test backend identity. Never ask for their password.
Superdesign preflight failed with npm EACCES/network restriction; used local
blue/neutral UI fallback. Browser skill used for actual browser checks.

## September 7 follow-on: upload limits and recoverable backups

Source now includes pre-parser request-body limits (including chunked bodies),
120-second body receive timeout, four concurrent multipart requests, and batch
limits (20 files, 100 MB combined). Middleware returns 413/408/429 as appropriate
and releases upload slots on disconnects/errors. GET health and owner controls
remain available. Limits are per process, not a distributed quota or complete
protection against decompression bombs/inference overload.

`scripts/backup_storage.ps1` creates verified private ZIPs under `backups/`.
`scripts/storage_backup.py` uses SQLite online backups, integrity checks,
checksums, bounded verification, and recovery only to a new directory.
Existing backups/live storage are not overwritten; no schedule or retention
deletions were enabled. See README_REMOTE_ACCESS.md for operating policy.

85 deterministic tests passed. A real snapshot was created at
`backups/LinguaFusion-20260907T110105Z-c2cc3791.zip`, recovered into a scratch
directory, and all three restored SQLite databases passed quick_check.
Deployment complete: the staged release was promoted to
`dist/LinguaFusion/LinguaFusion.exe`; the packaged backend is running on
loopback port 8000. Rollback is retained at
`dist/LinguaFusion.pre-upload-limits-20260907`. The desktop UI had been closed
and was left closed; its usual shortcut points to the new executable.

All 18 live API smoke tests passed against the new executable in 22.37 seconds.
Real HTTP checks confirmed an oversized declared body and a 21-file batch
return 413; health remains 200. Public `/health` and `/mobile/` return 200,
owner access status 403 and unauthenticated diagnostics 401. Underclock was
6498 MHz before GPU validation. Logs are
`temp/upload_limits_backend_stdout.log` and `_stderr.log`.

Next infrastructure work: structured/redacted logs with rotation, credential
protection/rotation, and processing limits for decompressed documents and
non-upload inference calls. Backups are private but unencrypted and currently
on the same drive; external-copy/scheduling policy is documented, not enabled.

## September 7, 2026 infrastructure continuation (supersedes deployment notes below)

Security/CUDA fixes are present in source and in the rebuilt desktop at
`dist/LinguaFusion/LinguaFusion.exe`. September 7 packaging and validation are
complete. The updated desktop UI is open and the packaged backend is running
on `127.0.0.1:8000`; the temporary source backend has been stopped.

- Matched NVIDIA CUDA packages to Torch's CUDA 12.8 library set in
  `requirements.txt`, resolving the cuBLAS/cuBLASLt entry-point mismatch.
  Source loads the NVIDIA namespace-package DLLs; frozen desktop uses its
  bundled coherent `torch/lib` set explicitly.
- Fixed a separate packaged QtCore startup failure: PyInstaller picked up
  Poppler's ICU 78 DLL from the build-tool PATH, but Qt 6.11 expects Windows'
  unversioned ICU exports. `pyinstaller_desktop.spec` excludes that conflicting
  root `icuuc.dll`, allowing Windows to supply its system library. Verified
  desktop startup visually using the Windows computer-use skill.
- Owner keys protect all legacy `/api/access/*` routes. Public health is
  minimal; detailed diagnostics require feature authentication.
- Remote feature access fails closed when the owner API key is absent.
  Forwarded requests cannot use the direct-loopback desktop exemption.
  Forwarding headers are accepted only from configured trusted proxy peers.
  Standard source and frozen launchers preserve the socket peer by disabling
  Uvicorn's own proxy-header rewriting. Backend defaults to loopback.
- Shared single-upload handler enforces a byte limit and returns HTTP 413.
  Generated response files are cleaned up. Startup sweeping is restricted to
  API-created upload/audio UUID filenames, preserving unrelated temp files.
- Whisper retries without VAD/hotwords when a long recording produces only a
  tiny hotword echo. Existing correction-overlap and lyrics guardrails remain.
- September 7 verification: 80 deterministic tests passed; all 18 live API
  smoke tests passed against source (GPU translation/transcription, TTS, OCR,
  Reader, documents, notes, background queue). Underclock confirmed 6498 MHz
  versus maximum 7000 after the user reapplied it. Always recheck next session.
- The same 18 live API tests also passed against the final packaged backend
  in 23.14 seconds, including GPU speech/translation and frozen Piper TTS.
  `pip check` reports no broken requirements. Initial packaged tests were
  skipped due to the Qt startup failure; the final successful run supersedes
  those skips.
- Public checks: `https://linguafusion.fyi/health` 200,
  `/api/access/status` 403, `/diagnostics` 401 without credentials.
- Packaged backend was started hidden using `LinguaFusion.exe --backend` with
  `LINGUAFUSION_PUBLIC_URL=https://linguafusion.fyi`. Logs:
  `temp/packaged_backend_stdout.log` and `temp/packaged_backend_stderr.log`.
  Standard recovery/startup remains `scripts/start_backend.ps1 -NoReload`.
  Existing Cloudflare Windows service/configuration was not changed.
- Original desktop rollback is retained at
  `dist/LinguaFusion.pre-security-hardening-20260831`.

Source, friend, and mobile launch scripts now disable Uvicorn proxy rewriting;
all three pass PowerShell syntax validation. Only the standard source and
packaged launch paths receive live checks in this continuation.

Remaining assessment work: request-body/batch/resource limits, log and backup
policy, credential protection/rotation, and live checks of alternate launch modes.
RapidOCR is absent in the current environment; live OCR passes using Tesseract
fallback. No new cloud migration or Cloudflare dashboard changes were made.
The earlier Phase B roadmap below remains separate unfinished work; do not
claim it is fully validated based on the API smoke suite.

**Last updated:** August 7, 2026
**Application version:** `1.0-rc2.14-agentic-phase-a`  
**Handoff revision:** `permissioned-background-task-foundation`  
**Architecture:** PySide6 Windows desktop app + FastAPI PC backend + mobile PWA used by Android and iPhone wrappers.

## August 7 low-usage continuation checkpoint

The installed release at `dist\LinguaFusion` remains the verified Phase A
build. Do not replace it until the Phase B source checkpoint below completes
packaged GPU validation.

Phase B source work now present but **not yet packaged**:

- `backend/services/agent_planner_service.py` adds a preview-only local Ollama
  planner using JSON-schema structured output, temperature 0, the GPU
  coordinator, one validation repair attempt, and `OLLAMA_PLANNER_MODEL`
  configuration (falling back to the normal Ollama model).
- `POST /agent/plan` and `GET /agent/planner/status` are authenticated. The
  model can propose only Phase A's typed allowlist. The server validates every
  tool and input before preview; execution still requires UI confirmation and
  is validated again by `/agent/tasks`.
- Desktop and phone Task Centers have natural-language request, preview,
  confirm, and discard controls. Note creation still needs separate PC-owner
  `local_write` approval. Unsafe and external tools remain disabled.
- A real GPU call with `llama3.1:8b` returned a valid translation + note plan
  in 49 seconds at the confirmed 6498 MHz memory clock. It exposed a quality
  issue where the model used translated content as the note title; validation
  now rejects referenced note titles and triggers the one repair attempt. That
  exact live request must be rerun next.
- The desktop-theme regression is repaired in source. A late Signal Deck QSS
  block hard-coded one cyan/dark palette and Consolas across the whole app,
  overriding all nine theme and font choices. It now resolves through the
  active palette, corner metrics, and independently selected font.
- 20 focused planner, policy/API, desktop theme/usability, and phone tests pass.
  Python and JavaScript syntax checks pass. The broader suite reached 65 passes
  before 13 obsolete tests failed only because they hard-coded an older version;
  those assertions now accept any `1.0-rc2.*` release.

Resume in this order:

1. Rerun `Translate Good morning to Odia and save it as a note called Greeting`
   and confirm the repaired plan keeps `Greeting` as the literal note title.
2. Add reference-output-field validation and a test, so each `$step.N.field`
   must name a real output of that earlier tool.
3. Make failures during the second/repair Ollama call return the same friendly
   HTTP 503 response as failures during the first call.
4. Change the desktop Task Center safety-strip copy from `PHASE A` to `PHASE B`.
5. Rerun the full deterministic suite and a source live preview -> confirm ->
   owner approval -> completion workflow.
6. Capture Broadsheet, Gallery, Glass Dark, and Zen from the native desktop app
   to verify visibly distinct rendering.
7. Bump to `1.0-rc2.15-agentic-phase-b`, bump the phone cache beyond v26,
   update roadmap/counts, package, run the full CUDA suite, preserve rc2.14 as
   rollback, then install and launch rc2.15.

## Current state

LinguaFusion is an offline-first speech transcription, translation, OCR, document reader, and TTS application. The PC performs the inference work. Phones can connect over the local network or through the owner-controlled HTTPS tunnel and one-time pairing flow.

Agentic Phase A is implemented. Desktop and phone Task Centers can queue
validated translation and audio-transcription workflows, monitor persistent
progress, pause/resume/cancel/retry work, and request owner approval before a
task creates a note. The execution engine exposes no shell, Python, arbitrary
filesystem, unrestricted database, or unrestricted network tool.

- **Universal Color Inversion (`◐`)**: Both the native PC desktop app (`desktop/main.py`) and Mobile PWA (`backend/mobile_web/linguafusion-themes.css`) feature universal color mode inversion. Toggling color mode (`◐`) cleanly inverts backgrounds, panels, text, and surfaces between Light $\leftrightarrow$ Dark without altering the selected theme structure or leaving the active page.
- **Independent Font Separation**: Typography choices (`Modern Sans`, `Friendly Rounded`, `Accessibility Sans`, `Editorial Serif`, `Classic Serif`, `Technical Mono`) are strictly decoupled from theme looks across both PC and Phone interfaces.
- The native Windows desktop app offers the 9 PC themes (`broadsheet`, `editorial-split`, `reading-room`, `gallery`, `editorial-luxe`, `glass-dark`, `aurora-glass`, `blueprint`, `zen`), with `broadsheet` as default.
- The mobile PWA and native Android/iPhone wrappers offer the 9 mobile themes (`soft-ui`, `sunset`, `brutalist`, `warm-editorial`, `glass-dark`, `neon-arcade`, `warm-minimal`, `bold-mono`, `nature-calm`), with full CSS custom property tokens, structural rules, and color mode inversion enabled.
- Theme, color mode, and font choices persist separately between sessions.
- Fonts use local/system families only; the offline app does not depend on Google Fonts.
- Speech uses a shared four-stage interaction model: **Listening → Processing → Translating → Complete**.
- Motion can be set independently to Full, Reduced, or Off on desktop; phones additionally offer a System setting.

## Appearance choices

### Windows desktop — 9 PC looks

| ID | Display name | Mode |
| --- | --- | --- |
| `broadsheet` | Broadsheet (Default) | Light |
| `editorial-split` | Editorial Split | Light |
| `reading-room` | Reading Room | Light |
| `gallery` | Gallery | Dark |
| `editorial-luxe` | Editorial Luxe | Light |
| `glass-dark` | Glass Dark | Dark |
| `aurora-glass` | Aurora Glass | Dark |
| `blueprint` | Technical Blueprint | Dark |
| `zen` | Zen Focus | Dark |

### Mobile PWA, Android, and iPhone — 9 phone looks

| ID | Display name | Mode |
| --- | --- | --- |
| `soft-ui` | Soft UI | Light |
| `sunset` | Sunset | Light |
| `brutalist` | Neo-Brutalist | Light |
| `warm-editorial` | Warm Editorial | Light |
| `glass-dark` | Glass Dark | Dark |
| `neon-arcade` | Neon Arcade | Dark |
| `warm-minimal` | Warm Minimal | Light |
| `bold-mono` | Bold Mono | Light |
| `nature-calm` | Nature Calm | Light |

### Independent font choices — all interfaces

`Modern Sans`, `Friendly Rounded`, `Accessible Sans`, `Editorial Serif`, `Classic Serif`, and `Technical Mono`.

## Starting LinguaFusion

Before GPU inference, confirm the RTX 2080 Ti has the known-good **-500 MHz memory clock offset** applied in MSI Afterburner.

```powershell
cd /d W:\OfflineSpeechTranslator_dev_v1.0

# Start the PC backend.
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_backend.ps1

# In a second terminal, start the native desktop interface.
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_desktop.ps1
```

For phone access and pairing, start the mobile/remote backend flow documented by the current scripts and use the owner Access page to issue or revoke invitations.

## Theme implementation

- `desktop/main.py`
  - `DESKTOP_THEME_IDS` limits the Settings selector to nine PC looks.
  - `DESKTOP_FONT_SPECS` defines six independent font presets.
  - QSS generation combines the selected look with the selected font.
- `backend/mobile_web/linguafusion-themes.js`
  - Declares platform ownership for every concept.
  - Populates only mobile looks in the PWA.
  - Stores `lf-theme` and `lf-font` independently.
  - Synchronizes Android system bars with light/dark looks.
- `backend/mobile_web/linguafusion-themes.css`
  - Contains design tokens for all concepts and late-cascade font overrides.
- `backend/mobile_web/linguafusion-structure.css`
  - Adds the phone-specific Speech screen composition for the seven mobile concepts.
- `backend/mobile_web/app.css`
  - Maps the existing PWA components to shared design tokens.
- `backend/mobile_web/index.html` and `app.js`
  - Provide separate **Phone look** and **Font** selectors.

## Verification completed

- Option A Design Concept (`demo.html`) embedded into native PySide6 UI using `QWebEngineView` and mapped to sidebar **Demo** navigation button.
- Restored the 9 PC themes and 9 Phone themes across `desktop/main.py` and `backend/mobile_web/linguafusion-themes.js`.
- All nine desktop looks and all six fonts can be applied independently in PySide6.
- All nine phone looks verified for PWA / Android / iOS wrappers.
- The verified PyInstaller release is installed at
  `dist\LinguaFusion\LinguaFusion.exe` and is the currently running desktop
  build. The immediately previous build is preserved at
  `dist\LinguaFusion.pre-agent-phase-a-20260807` for rollback.

## August 7 regression audit

- 73 deterministic backend, desktop, mobile, accessibility, agent-policy, and packaging tests pass.
- 18 CPU-safe live API tests pass across language detection, translation, Reader,
  document export, notes, OCR, image translation, TTS, and speech round-trip.
- Piper now runs in an isolated child process by default so native runtime
  conflicts cannot terminate the long-running backend. The frozen Windows app
  uses a dedicated packaged worker, and the PyInstaller spec includes Piper's
  required espeak-ng pronunciation data.
- The windowless release bundle itself passed all 18 live API workflows after
  packaging; this includes a valid packaged TTS WAV, speech round-trip, and a
  persistent background-agent task with audit events.
- Whisper supports configurable hotwords (`LF_WHISPER_HOTWORDS`) and defaults
  to the `LinguaFusion` product name.
- Explicit CPU mode no longer preloads CUDA libraries.
- Whisper VRAM release now uses the correct model lock during exclusive GPU handover.
- Agentic Phase A is implemented in `backend/services/agent_task_service.py`
  with authenticated `/agent/*` APIs and desktop/phone Task Centers. Phase B
  should add the local Ollama JSON planner above this existing policy gate.

Primary regression commands:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\test_core_desktop_usability.py backend\test_core_mobile_clients.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Final GPU validation was completed after the Afterburner underclock became
visible: `nvidia-smi` reported 6498 MHz versus the 7000 MHz maximum. The
packaged standard app passed all 18 live workflows in CUDA mode and then passed
three consecutive TTS -> faster-whisper -> translation round trips without
corruption or hanging. The verified release is installed at
`dist\LinguaFusion`; the previous build is preserved at
`dist\LinguaFusion.pre-agent-phase-a-20260807` (with the earlier pre-audit
backup retained separately).

The normal desktop-launched backend reports CUDA for faster-whisper and NLLB,
publishes `https://linguafusion.fyi` in Access, and the public `/health` and
`/mobile/` routes both returned HTTP 200 after startup. The public mobile page
contains the Speech and Task Center views plus safe-area handling for modern
Android and iPhone screens.

## Important operational notes

- GPU corruption or hanging: verify the MSI Afterburner -500 MHz memory-clock offset first.
- `LF_WHISPER_DEVICE=cpu` remains the safe fallback.
- Ollama correction must not receive empty ASR text.
- Do not weaken the existing correction overlap guardrails.
- Music/lyrics mode intentionally skips LLM correction.
- Android and iPhone do not need separate theme implementations because both consume the mobile PWA from the PC backend.
