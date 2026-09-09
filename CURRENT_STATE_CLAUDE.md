# LinguaFusion — current state

**Written:** 2026-09-08 · **Updated:** 2026-09-09 (twice) · **Author:** Claude
**Scope:** the cloud service (`cloud_api/`) and the Android app, which now has
an offline mode of its own. The Windows desktop app, PC backend and PC pairing
flow are **unchanged** by this work.

---

## 1. What exists now, in one paragraph

There is a live, owner-approved cloud service at
**https://linguafusion-cloud-pilot-jl77ipbeua-ey.a.run.app** offering
translation, pronunciation guides, speech-to-text and reading text from
pictures. People sign in with Firebase, confirm their email, request access, and
the owner approves each one by hand. All paid AI is metered against a per-user
monthly budget and a shared lifetime ceiling. A printable QR invite points at
the same service.

The Android app is no longer only a wrapper around it. It now carries a second,
**entirely offline mode**: speech, translation, reading pictures and romanising
scripts all running on the phone, for English, German, Arabic, Spanish and
French. It needs no account, no signal and costs nothing per use. A pill in the
app header switches between the two. The app also updates itself now, rather
than expecting someone to find the APK in a browser.

---

## 2. Live state as of writing

| Thing | Value |
|---|---|
| Service | `linguafusion-cloud-pilot`, Cloud Run, europe-west3 |
| Image | `…/linguafusion/cloud-pilot@sha256:21781329c797…` (revision `00047-88c`) |
| Scaling | min 0, max 1, concurrency 8, 60s timeout, 1 vCPU / 512Mi |
| Firestore | `(default)`, europe-west3, Native, delete protection ON, PITR off |
| Ledger | committed **$0.46** of **$27.00** ceiling |
| People with access | owner `kLqjJka0cH…`, plus `bZTv4DH0sT…` (Rajarshi Chakraborty) |
| Per-user limits | 540 requests / **$5.40** per month |
| Owner | the owner's Google account = UID `kLqjJka0cHXTCZX0TQxA2QMlzKi1` |
| Alerts | Cloud Monitoring → the owner's address (verified) + a second address |
| Interface | `2026.09.09.17` — bump `updates.mjs`, `app-version.json` and `sw.js` together |
| Android app | versionCode **15**, versionName **1.14**, 21.4 MiB, arm64-v8a only |
| Android flavours | `sideload` (self-updating) and `play` (no updater, no install permission) |
| APK signer | `2cdb1969…514e` — unchanged since the first build, so it installs over |
| Offline engines | whisper.cpp b4938 (speech) · ML Kit (translate, OCR) · ICU (romanise) |
| Tests | 188 cloud Python (+8 skipped, +20 env) · 28 Android build guards · 29 Android JVM · 54 Node · 85 backend |

**Everything is deployed.** Nothing is waiting on a build.

The 20 cloud tests marked "env" fail only on this machine, on
`import google.cloud.firestore` and `firebase_admin` — optional packages the
build interpreter does not have. They are not a code problem, but they do mean
the Firestore-backed paths are not being exercised locally.

**The offline app now works on the owner's phone**, confirmed 9 September on
app 1.13 (versionCode 14): speech, translation, reading pictures and
romanisation all running with no network. Quality is below the online path,
which is expected and has three separate causes -- see "Why offline is worse"
below.

It still cannot be tested from the build machine: no device is attached, no
emulator image is installed, and the arm64-only ABI list means the usual x86
emulator could not run it. Everything here was verified by the owner, not by
this workspace.

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

# Build the Android app. ALWAYS clean: incremental packaging leaves stale
# data in the APK and has produced a 38 MiB file from a 21 MiB build.
.\gradlew.bat clean stageApk      # from android/LinguaFusionMobile

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

## 4. What was built — session 1 (8 September)

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
(manifest + service worker). Two looks -- Studio and Minimal -- each with a day
and a night mode, and six typefaces; look, mode and typeface are independent.
Client-side export (txt/md, csv for tables).
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

## 4b. What was built — session 2 (9 September)

### Appearance: two looks, not nine
The picker offered nine fixed-brightness looks copied from the phone client. It
now offers **Studio** (parchment and terracotta by day, sunset rose and plum at
night) and **Minimal** (monochrome in both), each with a **Day/Night mode** that
is independent of the look. Both are in the shared theme sheet; the older looks
stay in that file because the desktop and phone clients read it too, and the
cloud picker simply does not list them. A `◐` pill in the header switches mode
from any view.

### The Android build moved to Gradle
`build_apk.ps1` drove aapt2, javac and d8 by hand, which cannot resolve Maven
dependencies or compile native code — both needed for what follows. It is now
AGP 8.13.2 on Gradle 8.14.5, with `src/` and `res/` left where they were so the
migration changed the build and nothing else. `build_apk.ps1` survives as a thin
wrapper because the publish script points people at it.

The NDK and CMake were not installed and there are no `cmdline-tools`. They were
fetched straight from the same repository index the SDK Manager reads, with
checksums verified. `ndkVersion` is pinned: left unset, AGP silently downloaded
its own NDK 27 and built against that.

### An offline mode in the Android app
A third option on the connection screen, and a pill in the cloud app's header,
lead to a mode that talks to nothing:

- **Speech** — whisper.cpp b4938, vendored and compiled for arm64-v8a. Only what
  a CPU build compiles is vendored (6.3 MB, not 30 MB). The JNI binding is ours:
  upstream's targets Kotlin and hardcodes `language = "en"`.
- **Translation** — ML Kit, packs downloaded and removable from within the app.
- **Reading pictures** — ML Kit's Latin model. **Arabic is not one of ML Kit's
  scripts**, so those pictures still need the cloud, and the page says which
  languages it can read rather than returning an empty box.
- **Romanising** — ICU, which Android carries in the platform: no dependency,
  nothing downloaded. Arabic, Hindi and Odia, including the two the phone cannot
  transcribe or translate at all. Android 10+; below that it is hidden, not
  broken.

The interface is bundled in the APK, and that is what makes it possible: the
cloud WebView deliberately has **no** JavaScript bridge, because a remotely
served page has no business driving the microphone. A local page can hold one
safely, so the offline WebView gets a bridge and in exchange refuses to navigate
anywhere but its own assets. Recorded audio and chosen pictures never enter
JavaScript — the whole pipeline runs in Java and only text comes back.

Models are chosen, downloaded, resumed and removed in-app, each verified against
its published SHA-256. Quantised builds changed the size story Codex estimated:
Small q5_1 is 190 MB against 488 MB, so a full install is about **300 MB**, not
650–750 MB.

### The app updates itself
It checks the published `versionCode` on each launch and offers the newer build.
Android still shows its own install confirmation and always will; what is gone
is noticing an update exists, opening a browser, finding the file and checking a
fingerprint by eye. The download is checksummed **before** the installer sees
it, and a mismatch deletes it.

---

## 4c. What was built — session 3 (9 September, afternoon)

Codex worked the hosted page in parallel and merged to `main` while my Android
work sat unpushed. **The first job was reconciling the two**, which is recorded
under "Two sessions collided" below.

### The app can go to a store, if it ever should
`Play` and `sideload` are now separate build flavours. Play forbids an app it
distributes from replacing itself, so the downloader is **absent from that
flavour**, not merely disabled: the Play APK contains no `AppUpdate` class and
its manifest removes `REQUEST_INSTALL_PACKAGES`. A real 4096-bit release key
lives outside the checkout; the sideload build keeps the debug key so copies
already installed still upgrade in place.

### A proverb engine
45 idioms across the seven languages the two products translate between, each
an idea rather than a phrase. Online it becomes a **note to the model** -- this
is an idiom meaning X, conventionally said as Y -- and the model still writes
the sentence. Nothing is substituted, so a wrong match costs a misleading note
rather than a corrupted translation.

Matching folds case, punctuation, spacing, and for Arabic the optional
diacritics and interchangeable letter forms. Coverage is pinned per language;
Odia has one entry and is deliberately unfloored.

### The iPhone route
iOS has no sideloading worth the name, so the hosted page is the answer: it was
already a PWA and now has the PNG icon Safari needs (it ignores SVG) and the
Apple meta tags. Recording in a Home Screen web app fails after the first
launch -- a WebKit bug -- so that is named when it happens with the workaround.

### The ledger became true
See "The ledger was wrong by 55x" below. It now settles every capability
against measured cost, and **Settings > Owner > Check provider spend** puts
OpenRouter's actual bill beside the estimate. Groq and Vision publish no usable
API, so both are shown as unavailable with project-scoped console links rather
than quietly omitted.

### Commercialisation was started, then dropped
Release signing and the Play split were built. Then the arithmetic came in: see
"What it actually costs" below. Ads and subscriptions were dropped, the Play
submission shelved. The build work is not wasted -- the store is a submission
away rather than a rewrite -- but nothing is being sold.

---

## 4d. What it actually costs

Calibrated against the owner's real OpenRouter dashboard, not estimated:

- Measured: **31 requests, 4,000 tokens, $0.06/M blended**. So a real request is
  about **129 tokens**, and my first model was **8x high** (2.5x on price, 3.4x
  on volume).
- Three people cost **$0.22 a month, $2.60 a year**.
- A genuinely heavy user -- 1,000 translations, 5 hours of speech, 400 pictures
  -- costs **$0.81 a month**.
- **Reading pictures is 52% of spend.** Translation, the headline feature, is
  12%. One photo costs about as much as twenty translations.

The binding cost is not usage at all. Apple's $99/year is **ten times one heavy
user**, so break-even is about fixed costs and would need roughly **four
subscribers at EUR 2.99**. Ads would need ~250 users to earn what four
subscribers do, while costing the `data_collection: deny` posture.

The 540-request monthly cap is not an economic control at these numbers. A
subscriber would have to read **1,829 pictures** -- the most expensive thing
the app does -- before costing more than a EUR 2.99 fee.

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

### The APK was too large for Cloud Run to serve
At 33.3 MiB every download failed with an **HTTP 500 from Google's frontend** —
Cloud Run refuses any response over **32 MiB**. Nothing appeared in the app's
logs because the app was never reached. Dropping `armeabi-v7a` (11.6 MB, for
32-bit phones that could not run a 190 MB speech model anyway) took it to 21.0
MiB. Bundling ML Kit's OCR model would have crossed the line again at 33.2 MiB,
which is why the unbundled variant is used. A test pins the published APK under
the limit; the only symptom otherwise is that nobody can install.

### A 21 MiB build measured 38 MiB
Gradle's incremental packaging left a **16 MiB unreferenced copy** of
`libtranslate_jni.so` inside the APK. The file still installed, so the only
symptom was size — which is what breaks downloading. I read it as the cost of
the bundled OCR model and switched dependencies on the strength of it; the
switch was right, the reasoning was not. **Always compare clean builds.** A test
now fails if more than 2 MiB of the published APK is not entry data.

### Offline mode was reachable only when the network was down
Once `mode` was saved as `cloud`, the app launched straight into the cloud
WebView, and the only path back to the connection screen was the "cloud is
unreachable" error screen. So the offline app could only be reached when the
network had already failed — exactly when its 190 MB model cannot be
downloaded. It now has a header pill, reached through the same custom-scheme
interception the recording flow uses, so the cloud page gets a link rather than
a native handle.

### A refused microphone looked like a successful recording
`startNativeAudioRecording` answers `"OK"`, `"ERROR: …"` **or**
`"PERMISSION_REQUIRED"`. The offline path treated the last as success, so
refusing the permission showed "speak now" over a microphone that was never
opened, with an empty recording as the only clue. This is the same class of bug
as the earlier microphone failures: one branch collapsing several outcomes.

### Minimal's night mode had an invisible button label
The primary button hardcoded `color:white`. Fine for nine always-dark accents;
invisible on Minimal's near-white night accent. It reads through
`--lf-on-accent` now, and a test checks every offered look defines it.

### A cached shell hid the update from everyone who had installed
The service worker serves the cached shell first, so shipping edited assets
without bumping `VERSION` leaves every installed copy — home-screen PWAs and the
Android app included — running the old code indefinitely, with no error
anywhere. `sw.js` now records a fingerprint of its own shell and a test fails if
it changes without a version bump. It has caught this three times since.

---

## 5b. Why offline is worse, and by how much

Not one cause but three, and they are worth telling apart before anyone tries
to close the gap:

| | Online | Offline |
|---|---|---|
| Speech | `whisper-large-v3-turbo` (Groq) | Whisper Small, quantised q5_1, ~190 MB |
| Translation | Mistral Small 24B | ML Kit, **pivots through English** |
| Romanisation | a language model | ICU, script to script only |

The translation gap is the sharpest and the least obvious. ML Kit has no direct
model for most pairs, so German to Spanish is really German to English to
Spanish: it loses twice, and on exactly the pairs where the owner is least able
to check the result. `OfflineLanguages.pivotsThroughEnglish` identifies these
and the app says so rather than hiding it.

The speech gap is the one with a lever attached. **Small q5_1 was chosen by
reasoning, never measured on the S26 Ultra** -- the open question Codex flagged
and the reason the model picker exists. Full-precision Small (488 MB) is the
next thing to try if transcription is the weak point; Base q5_1 (60 MB) is
worth trying if speed is.

Romanisation is not really a quality gap but a different feature wearing the
same name: ICU says which letters are present, not how a speaker would say
them. Nothing tunes that; it would need a different approach entirely.

---

### The ledger was wrong by 55x
A successful request never settled. The gateway placed a flat $0.01 hold,
returned, and left it standing forever -- only failures reached `settle`. The
hold is about **fifty-five times a real translation**, so the shared allowance
drained at fifty times the rate of actual spending and the remaining balance
meant nothing. 39 requests showed $0.39 held and $0.00 spent.

Fixed in two passes. First, translation and romanisation settled against the
token counts the providers were already reporting and we were discarding: 9x.
Then speech and pictures, which report nothing but bill on things we already
had -- Groq charges per hour of audio and the WAV was measured anyway to
validate it, Vision charges per image and there is one per call: **1.1x**,
which is the deliberate model-ceiling margin.

The $27 ceiling went from about four months of honest accounting to nine years.

### Two sessions collided
Codex reworked the hosted page and merged to `main`; my Android work was
committed locally and never pushed, so `main` knew the 22 MB APK only as an
unexplained binary and Codex's handover said its source did not exist. Codex
then deployed from `main`, which **reverted the published APK to the 33 KB
wrapper** -- the offline app stopped being downloadable and nobody noticed.

Resolved by ownership rather than recency: the hosted page is Codex's, whose
appearance work is further along; the Android app is mine. The lesson is
narrower than "merge more often" -- it is that **unpushed work is invisible
work**, and a second agent will reason from what it can see.

### An APK that would not download
At 33.3 MiB every download failed with an HTTP 500 from Google's frontend:
**Cloud Run refuses any response over 32 MiB**, and nothing reached the app's
own logs. Dropping `armeabi-v7a` fixed it. Bundling ML Kit's OCR model would
have crossed the line again, which is why the unbundled variant is used.

Separately, Gradle's incremental packaging left a 16 MiB unreferenced copy of a
native library inside the APK, so a 21 MiB build measured 38 MiB. **Always
compare clean builds.**

### A page that rendered perfectly with every button dead
Moving the offline page onto the shared stylesheets made it an ES module, and
module scripts need CORS. Loaded from `file:///android_asset` the origin is
opaque, the import was refused, and the script never ran at all -- while the
page rendered correctly, because stylesheets are not modules. `WebViewAssetLoader`
now serves the same files over a real origin.

### Guards that guarded nothing
Four times today a test passed while the thing it checked was broken, always
the same shape: **the guard matched something adjacent to the code rather than
the code**. A comment containing the constant. A helper's definition instead of
its call site. An overridden method's name instead of its body. A pricing
function instead of the adapter that must call it.

Every one was found by mutation -- breaking the code deliberately and seeing
the test stay green. A guard that has never been seen to fail is not yet a
guard.

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

### ~~Hard stop on 2026-10-08~~ — resolved
Replaced by an owner-only monthly reminder (`review_due()`), so the app no
longer stops itself. Only the owner sees it; everyone else is unaffected.

### Arabic cannot be read offline
ML Kit's scripts are Latin, Chinese, Devanagari, Japanese and Korean. A photo of
Arabic still needs the cloud. Tesseract through the NDK would close it — the
desktop app already uses Tesseract, so the path is known — at roughly 40 MB for
`ara.traineddata` and a second OCR engine to maintain. There is an irony worth
naming: Arabic is the language this owner most needs romanised, and it is the
one script ML Kit cannot read.

### Offline romanisation is not a pronunciation guide
ICU maps script to script, so it says which letters are there, not how a speaker
would say them; short vowels absent from written Arabic stay absent. The cloud's
guide, which uses a language model, reads better. The page says so, but someone
comparing the two offline and online will notice the gap.

### Never verified
- **Nothing in the offline app has run on a phone.** No device is attached and
  no emulator image is installed; the arm64-only ABI list means the usual x86
  emulator could not run it either.
- **The self-update path has never completed a real install.** Version 7 has no
  updater, so version 8 still needs installing by hand; the flow only proves
  itself on the step after that.
- Whether the microphone works on the owner's phone in offline mode. Codex's
  native recorder was confirmed working in cloud mode ("apk works great").
- No off-LAN phone test with the PC stopped.
- Cloud Run revision rollback has never been exercised.

---

## 7. Where this could go next

**Settled today, so do not revisit without a new reason**
- **Commercialisation is off.** Ads, subscriptions and the Play submission were
  dropped after the arithmetic: three people cost $2.60 a year and the fixed
  costs dwarf usage. The Play *build* work stands, so the store is a submission
  away if that ever changes.
- **iOS is the hosted page**, added to the Home Screen. Not a native app, not
  TestFlight; those cost $99/year and a 90-day rebuild treadmill for something
  the web app already does, minus offline.

**Do this first**
- **Install version 8 on the phone and actually use the offline mode.** Nothing
  in it has run on hardware. In order of likely trouble: Arabic transcription
  quality; whether Small q5_1 beats Base q5_1 on that phone (this decides the
  default, and is the one question Codex flagged); the microphone permission
  path; a model download interrupted and resumed; installing over the existing
  app without uninstalling.
- **Then let it update itself once**, so the self-update path is proven.

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
- **Reader and saved notes**, which the desktop app has and the cloud does not.
- **Arabic OCR offline**, via Tesseract through the NDK. The toolchain is now
  installed and whisper.cpp proves the native build works, so this is no longer
  blocked on anything but the effort.
- **Live transcription while speaking**, which Codex sequenced after the
  record-then-transcribe flow that now exists.
- **Arabic OCR offline**, via Tesseract through the NDK. The toolchain is
  installed and whisper.cpp proves the native build works, so this is blocked
  on effort alone. It matters more than it looks: pictures are 52% of spend
  online, and Arabic is the language the owner most needs read.
- **More Odia proverbs.** One entry, and the language with the least machine
  translation to fall back on.
- **Production signing.** Still unresolved and now more load-bearing: the app
  installs its own updates, and Android refuses to replace an app signed with a
  different key.

  `debug.keystore` is **deliberately not in git, and must never be**:
  `github.com/Rakshc77/LinguaFusion` is **public**, and the store password is
  the standard `android`, so the file is the whole secret. Anyone holding it
  could sign an APK that Android accepts as an update to the real app.
  `.gitignore` blocks `*.keystore` and `*.jks`, and a test fails if one is ever
  tracked — git history is effectively permanent, so it must not land even once.

  Losing it is equally unrecoverable: no other key can update an installed
  copy, so every user would have to uninstall, losing their downloaded models
  and packs. The owner has copied `LinguaFusion-signing\` (keystore plus a
  README explaining what it is) to **every drive on the build machine**, so a
  single disk failure no longer loses it.

  What that does not cover is losing the machine itself — theft, fire, or
  ransomware reaching every mounted drive at once. One copy somewhere off the
  machine would close that, and is the only outstanding step.

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
- **Build the APK with `clean`.** Incremental packaging leaves stale data inside
  it; a 21 MiB build measured 38 MiB and would not have downloaded.
- **The published APK must stay under 32 MiB**, or Cloud Run answers the
  download with a 500 that never reaches the app's logs.
- **Never give the cloud WebView a JavaScript bridge.** It is served remotely;
  the bridge drives the microphone and deletes files. Use a custom scheme with
  gesture and origin checks, as the recording and offline switches both do.
- **Bump `VERSION` in `sw.js` whenever a cached asset changes**, or installed
  copies keep the old app forever. A test enforces it via `SHELL_STAMP`.
- **`ndkVersion` must stay pinned.** Left unset, AGP downloads and uses its own.
- **A guard that a comment can satisfy guards nothing.** Four tests here have
  now passed while the code they guarded was broken -- matching a comment, a
  definition rather than its call, a method name rather than its body, and a
  helper rather than its caller. Slice to the call site, strip comments, and
  break the code on purpose to see the test fail before trusting it.
- **A source-level check cannot tell you a thing ran.** Every test on the
  offline page read its source; none could detect a script that loaded and did
  nothing. Where behaviour is what matters, drive the behaviour.
- **`_post` reserves budget before dispatch.** Anything that is not a paid
  request -- reading a bill, a health check -- must not go through it, or
  looking at the meter charges the meter.
- **Bump `updates.mjs`, `app-version.json` and `sw.js` together.** They carry
  the same interface version and a test fails if they disagree.
- **Run all three suites**, not one: `pytest cloud_api`, `node --test
  cloud_api/web/*.test.mjs`, and the Android build guards. Five pushes broke CI
  because only pytest was run.
- **Re-sync the offline appearance** after touching `pilot.css`,
  `linguafusion-themes.css` or `themes.mjs`: `scripts/sync_offline_appearance.py`.
  A test enforces byte-identical copies.

---

## 9. Fuller detail

`cloud_api/HOSTING_READINESS.md` carries the full chronological record for the
cloud service: every readiness gate, what was verified and how, exact digests,
and the reasoning behind each decision.

`android/LinguaFusionMobile/OFFLINE_PLAN.md` carries the offline app: Codex's
original design (agreed in a chat that was never committed, so it had to be
reconstructed from screenshots), the toolchain findings, the size traps, and
the ordered list of what to check on the phone.

This file is the summary; those two are the evidence.
