# LinguaFusion — current state

**Written:** 2026-09-08 · **Author:** Claude (session handover)
**Scope:** the cloud service (`cloud_api/`) and the Android wrapper. The offline
Windows app, PC backend and PC pairing flow are **unchanged** by this work.

---

## 1. What exists now, in one paragraph

There is a live, owner-approved cloud service at
**https://linguafusion-cloud-pilot-jl77ipbeua-ey.a.run.app** offering
translation, pronunciation guides, speech-to-text and reading text from
pictures. People sign in with Firebase, confirm their email, request access, and
the owner approves each one by hand. All paid AI is metered against a per-user
monthly budget and a shared lifetime ceiling. An Android wrapper and a printable
QR invite point at the same service.

---

## 2. Live state as of writing

| Thing | Value |
|---|---|
| Service | `linguafusion-cloud-pilot`, Cloud Run, europe-west3 |
| Image | `europe-west3-docker.pkg.dev/linguafusion-f24fe/linguafusion/cloud-pilot@sha256:032a00d6…` |
| Scaling | min 0, max 1, concurrency 8, 60s timeout, 1 vCPU / 512Mi |
| Firestore | `(default)`, europe-west3, Native, delete protection ON, PITR off |
| Ledger | committed **$0.46** of **$27.00** ceiling |
| People with access | owner `kLqjJka0cH…`, plus `bZTv4DH0sT…` (Rajarshi Chakraborty) |
| Per-user limits | 540 requests / **$5.40** per month |
| Owner | the owner's Google account = UID `kLqjJka0cHXTCZX0TQxA2QMlzKi1` |
| Alerts | Cloud Monitoring → the owner's address (verified) + a second address |
| Tests | 141 cloud Python · 8 invite · 36 Node · 85 backend (+18 skipped `live_api`) |

**Everything is deployed.** Nothing is waiting on a build.

---

## 3. How to operate it

```bash
# See spending and the ceiling (read-only)
.venv-cloud/Scripts/python.exe scripts/set_spending_ceiling.py

# Raise the ceiling (real money, needs --confirm)
.venv-cloud/Scripts/python.exe scripts/set_spending_ceiling.py --usd 40 --confirm

# Check what is provisioned in Google Cloud (read-only)
.venv-cloud/Scripts/python.exe scripts/check_deploy_readiness.py

# Rotate a provider key (reads YOUR file, never prints the key)
.venv-cloud/Scripts/python.exe scripts/add_provider_secret.py --provider openrouter --file "C:/path/to/your/keys.txt" --line 1 --add-version

# Rebuild the printable / shareable invite
.venv/Scripts/python.exe scripts/generate_cloud_invite_qr.py

# Publish a freshly built APK for download from the app
.venv-cloud/Scripts/python.exe scripts/publish_android_apk.py
```

**Approving people** happens in the app: sign in as owner → **Account** →
**Access requests** → Approve → confirm in the row. No command needed.

**Two Python environments.** `.venv-cloud` has firebase/firestore/httpx and runs
everything cloud. `.venv` is the main app environment and additionally has
`qrcode`, `Pillow` and `reportlab` for the invite. Some tests only run in one:
`cloud_api/test_invite_qr.py` needs `.venv`; the rest use `.venv-cloud`.

---

## 4. What was built today

### Backend (`cloud_api/`)
- **`pilot_capabilities.py`** — the gateway every paid capability goes through.
  Reserves from the per-user policy, then dispatches. Never retries.
- **`ocr_layout.py`** — rebuilds page layout from Google Vision word geometry.
- **`access_requests.py`** — access requests in their own Firestore collection.
- Routes `/api/translate`, `/api/pronounce`, `/api/transcribe`, `/api/ocr`,
  `/access/request`, `/owner/requests`, `/owner/users`.
- Per-path body limits in `backend/request_limits.py` (4 MB for audio/images,
  64 KB everywhere else).

### Web app (`cloud_api/web/`)
Sign-up, email confirmation, access request, then a five-view app shell with a
bottom bar: **Speak · Translate · Read · Say it · Model · Account**. Installable
(manifest + service worker). Nine phone looks and six typefaces, shared with the
existing mobile client. Client-side export (txt/md, csv for tables).
`wav.mjs` encodes microphone audio into the mono 16-bit PCM WAV the backend
requires — `MediaRecorder` produces WebM, which the adapter rejects.

### Android (`android/LinguaFusionMobile/`)
Cloud mode beside PC pairing, no pairing key needed. Shares the microphone and
file-picker plumbing with PC mode. Handles `data:` downloads via MediaStore.
Built and signed; published for download at `/pilot/linguafusion-android.apk`
with its SHA-256 shown in the app.

### Operational scripts
`cutover_to_managed_ledger.py`, `set_spending_ceiling.py`,
`add_provider_secret.py`, `setup_request_alerts.py`, `publish_android_apk.py`,
`generate_cloud_invite_qr.py`, `check_firestore_access.py`,
`check_deploy_readiness.py`.

---

## 5. Problems hit, and how they were solved

These are the ones worth remembering. Most cost real time to find.

### The Firestore 403 was not a permissions problem
Listing databases returned 403 for days. The cause was `SERVICE_DISABLED` — the
API was simply off. The identity already held every permission needed. **Lesson:
read the structured `reason` in the error body before assuming access.**

### Cloud Run would have re-granted the $5 allowance on every cold start
The lifetime ledger was a SQLite file. Cloud Run's filesystem is ephemeral, so
each cold start would have recreated it with a fresh $5. Now `create_app`
refuses that combination outright, and `FirestorePolicy` is the lifetime ledger
in the cloud.

### The container would have crashed on boot
`app.py` imported three modules the Dockerfile never copied. **A successful
build proves nothing.** Fixed, and a test now asserts the build context covers
every first-party import — verified by deleting a `COPY` line and watching it
fail.

### Approvals silently did nothing
`window.confirm()` returns **false without displaying anything** in installed
PWAs, Android WebViews, and pages where dialogs are suppressed. The handler
returned early with no message. Replaced with an in-page confirmation; a test
fails if `confirm`/`alert`/`prompt` reappear.

### The whole translate section was wired to a dead route
The model chooser and Translate button drove the legacy OpenAI route, which
needs `OPENAI_API_KEY` — not set, never will be. It advertised GPT pricing for
something that could never run. Now routes to `/api/translate`.

### Themes were silently inert on dark-mode phones
`prefers-color-scheme: dark` assigned literal colours later in the cascade at
equal specificity, so the attribute changed and nothing moved. Those tokens now
defer to the chosen look.

### The nav bar leaked the page through it
It used `--panel` → `--lf-surface-bg`, which several looks define as a
translucent overlay for a blurred backdrop (one is literally `transparent`).
**`--lf-surface-bg` is unsafe for anything that must occlude scrolling content.**
Now uses `--lf-app-bg`, opaque in every look.

### "Microphone unavailable" was told to someone who had already granted it
One `try/catch` wrapped both `getUserMedia` and the audio-graph setup, so every
cause collapsed into one misleading sentence. Now reports the actual error name.
Two further real causes were fixed: Android creates `AudioContext` **suspended**
(the graph connects, the mic goes live, and `onaudioprocess` never fires), and a
stream still held from an earlier attempt makes Android refuse the next one with
`NotReadableError` — which reads as "another app is using it" when the page
itself is the culprit. It now releases first and retries with plain constraints.

### Raising the translation limit would have broken long translations
`max_tokens: 2048` caps the **output**. Indic scripts tokenise near one token per
character, so a full A4 page would truncate and fail as a provider error. Output
ceilings are now 8192 / 4096.

### The QR code did not work
`reportlab` silently discarded a group transform, so the code rendered unscaled
and unscannable while the script exited successfully — and the HTML invite had
no code at all. Modules are now drawn at absolute coordinates, and tests read
every artifact back and compare it to the encoder's matrix pixel by pixel.

### Mistral Nemo was mistranslating Hindi
In a spot check it rendered "the contract is void" as "कॉन्ट्रैक्ट कोल्हू" —
कोल्हू is an **oil press**. The default moved to Mistral Small 24B, which got it
right for a fraction of a cent more.

---

## 6. Unresolved problems

### DeepSeek V4 Flash fails 100% of the time
Three attempts, each refused in ~0.7s — an immediate rejection, not a timeout.
DeepInfra is listed as a provider for it, so the cause is unknown. It was
**removed from the model list** rather than shipped broken. Worth investigating
if you want a reasoning-oriented option: likely the price cap, the
`data_collection: deny` constraint, or the variant not being served.

### Translate fails intermittently (~1 in 5)
`provider.only: ['deepinfra']` with `allow_fallbacks: False` and a price cap
means a momentary capacity or pricing problem fails the request outright. **This
is a deliberate cost control, not a bug** — but it is the trade-off to revisit
if reliability matters more than predictable spend.

### Provider failures are not appearing in Cloud Logging
`PilotGateway` logs `provider_failure` with the provider and HTTP status, the
logger is correctly wired, and the entries do not appear in Cloud Logging. The
502s themselves are logged. **Unexplained** — worth solving, because it is the
only way to diagnose the two problems above.

### The owner account has `email_verified: false`
Nothing breaks today: `identity()` short-circuits for the owner UID. But account
recovery depends on it, and the owner is the one account that must never be
locked out. Fix from the Firebase console.

### Hard stop on 2026-10-08
`pilot_providers._post` refuses to dispatch anything after that date pending a
price review. A deliberate tripwire from the original design — but it **will**
stop the app dead if nobody revisits it. Roughly one month from writing.

### Never verified
- The Android APK has not been installed or run on a real device.
- No off-LAN phone test with the PC stopped.
- Cloud Run revision rollback has never been exercised.
- Whether the microphone now works on the owner's phone (last report: still
  failing, before the release-and-retry fix shipped).

---

## 7. Where this could go next

**Closest to done**
- **DOCX/PDF export.** The offline app already has `document_service.py` and
  `complex_script_pdf_service.py`. Complex-script PDF needs embedded fonts — a
  naive version would mangle Hindi, Arabic and Odia, which is why it was left
  out rather than half-done.
- **A fidelity guard on cloud translation.** The desktop pipeline gates LLM
  correction behind a word-overlap check (`_valid_correction`) precisely because
  general models rewrite rather than translate. The cloud path has no equivalent.
  This is the structural reason Hindi quality is uneven — see `CLAUDE.md` on why
  NLLB was chosen over a chat LLM.
- **More models.** 45 of OpenRouter's 431 sit under the current price cap, but
  only those DeepInfra serves are usable. Adding one means checking its endpoint
  and setting its own `max_price`.

**Bigger**
- **Remove `roles/editor`-equivalent risk elsewhere**, and give Cloud Build its
  own service account rather than the Compute Engine default.
- **SMS or TOTP two-factor.** Needs an Identity Platform upgrade with its own
  pricing; SMS also bills outside the €5 allowance. Deliberately not built.
- **Bring the cloud capabilities into the PC/mobile clients** so there is one
  app with an offline and an online mode, rather than two front ends.
- **Reader and saved notes**, which the offline app has and the cloud does not.

---

## 8. Traps for whoever picks this up

- **`--lf-surface-bg` is translucent in several looks.** Never use it for
  anything that must hide what scrolls behind it.
- **A consent checkbox must never live inside the fieldset it gates** — it
  disables itself and cannot be ticked.
- **`window.confirm` is unusable here.** It returns false silently in WebViews
  and installed PWAs.
- **Blob downloads do not work in Android WebView.** Emit a `data:` URL there.
- **Writing to the public Downloads path fails on Android 10+.** Use MediaStore.
- **A successful Docker build does not mean the container starts.** Run the
  image and import the app.
- **Holds are never automatically refunded.** A hold is settled to zero only
  when the process knows for certain nothing was dispatched. Recorded charges
  survive deleting the person who spent them — money already committed cannot
  be un-spent.
- **Do not clear the cutover mark** on `combined-test-budget.sqlite3`. The cloud
  ledger exists; reopening local spending would grant a second allowance.
- **Owner configuration must point at the owner's Google account** — verified
  against Firebase as the perpetual owner.

---

## 9. Fuller detail

`cloud_api/HOSTING_READINESS.md` carries the full chronological record: every
readiness gate, what was verified and how, exact digests, and the reasoning
behind each decision. This file is the summary; that one is the evidence.
