# Offline Android app — plan and toolchain findings

Written 2026-09-09. The design here is Codex's, agreed with the owner in a
chat that was never committed; it is recorded now so it cannot be lost again.
The toolchain findings below are mine, checked against this machine.

## What we are building

The APK today is a WebView around the cloud app: the interface and the
microphone are local, everything else needs the network. The goal is that the
phone needs **neither the PC nor the cloud**.

Languages: **English, German, Arabic, Spanish, French.** Explicitly **not**
Hindi or Odia — Odia transcription is not supported by either engine below and
would need a separate model.

Codex's three levels, in the order he recommended building them:

| Level | Capability | Requires |
|---|---|---|
| 1 | Open the app, view saved results, make recordings | Local storage, offline interface caching |
| 2 | Record offline, transcribe/translate when the network returns | A persistent upload queue with retry |
| 3 | Transcribe, translate and OCR entirely offline | On-device engines and downloaded models |

First increment: **record → stop → transcribe → translate, fully offline**,
behind an explicit **Cloud/Offline switch**. Live transcription while speaking
is a later step. Then a **Manage offline languages** screen to add and remove
translation packs and choose the speech model, so adding a supported language
later is a normal app action rather than a new build.

### Engines

- **Translation — Google ML Kit** (`com.google.mlkit:translate`). Runs
  on-device once its packs are downloaded, roughly 30 MB per language,
  ~120–150 MB for the five. Non-English pairs pivot through English, so
  German → Arabic loses nuance; expect quality below the cloud models.
- **Transcription — multilingual Whisper via `whisper.cpp`.** One model covers
  all five languages. Base is 142 MiB, Small is 466 MiB. Benchmark both on the
  owner's S26 Ultra before choosing a default. Arabic dialects, background
  noise and mixed-language speech need particular testing.

### Expected size installed

Codex's estimate assumed unquantised models. The q5_1 builds change the deal
considerably, and are what the app offers:

| Model | Download | Note |
|---|---|---|
| Base q5_1 | 60 MB | smallest and fastest |
| **Small q5_1** | **190 MB** | **the default** |
| Small, full precision | 488 MB | last few points of accuracy |

With translation packs (~30 MB each) and a 35 MB APK, a full install is around
**300 MB** with Small q5_1 rather than the 650-750 MB originally estimated.

## Toolchain findings — read this before estimating

Codex estimated 3–5 days to a prototype and 1–2 weeks to a reliable release.
That estimate assumes a build system this project does not have.

**This is not a Gradle project.** `build_apk.ps1` runs aapt2 → javac → d8 →
zipalign → apksigner by hand, producing a single `classes.dex` from
`src/**/*.java`. It has no dependency resolution, no AAR handling, and no
native build step.

Checked on this machine:

| Needed for | Present? |
|---|---|
| Gradle (any: PATH, wrapper, Android Studio plugin) | **No** |
| Android NDK (`$SDK/ndk`) | **No** |
| CMake (`$SDK/cmake`) | **No** |
| `cmdline-tools` / `sdkmanager` | **No** — the NDK cannot be installed from the CLI |
| Build-tools 34–37, platforms 35/36/36.1, Android Studio JBR | Yes |

Consequences:

- **ML Kit translation needs Gradle, but not the NDK.** It is a Maven artifact
  whose AAR carries its own prebuilt native code, and the unbundled models
  arrive through Google Play Services. Migrating the build to Gradle is
  therefore enough to unblock the whole translation half.
- **Whisper needs Gradle *and* the NDK and CMake**, to cross-compile
  `whisper.cpp` for arm64-v8a and package the `.so` plus JNI bindings. Neither
  is installed. I first concluded they could only be added by hand through
  Android Studio's SDK Manager; that was wrong, and the update below says how
  they were actually obtained.

**Update, same day: the toolchain problem is solved.** The NDK and CMake are
published as plain archives in the same repository index the SDK Manager reads,
so they were fetched directly, with checksums verified, rather than through
Android Studio. NDK r28c and CMake 4.1.2 now sit in the SDK where the SDK
Manager would have put them, and `ndkVersion` is pinned so AGP does not quietly
substitute its own -- left unset, it downloaded and used NDK 27.

## Status

Done:

1. **Gradle migration.** AGP 8.13.2 on Gradle 8.14.5, same debug keystore --
   verified, the built APK carries the original certificate -- versionCode 7.
2. **whisper.cpp compiled in**, both ABIs, 1.7 MB and 1.2 MB.
3. **ML Kit translation wired up**, with pack download and removal.
4. **A bundled offline page** (`assets/offline/`) and an offline mode: record,
   transcribe, translate and manage storage, with no network at all.
5. **Reading pictures**, via ML Kit's unbundled Latin model -- English, German,
   Spanish and French.
6. **Romanising** Arabic, Hindi and Odia through ICU, which Android carries in
   the platform, so it needs no dependency and nothing downloaded. Android 10
   and newer; below that the feature is hidden rather than broken.
7. **A switch in the app header**, beside day/night, so offline mode is
   reachable from anywhere rather than only before signing in.

Not done, and why:

- ~~Nothing has run on a phone.~~ **Confirmed working on the owner's phone on
  9 September**, app 1.13: speech, translation, reading pictures and
  romanisation, all with no network. Quality is below the online path, for the
  reasons set out in CURRENT_STATE_CLAUDE.md. The build machine still cannot
  test it -- no device, no usable emulator -- so this was the owner's
  verification, not this workspace's.
- **Arabic OCR is still online-only.** ML Kit's scripts are Latin, Chinese,
  Devanagari, Japanese and Korean, so a photo of Arabic still needs the cloud.
  Tesseract through the NDK would close that, at roughly 40 MB for
  `ara.traineddata` and a second OCR engine to maintain -- the desktop app
  already uses Tesseract, so the path is known.
- **No live transcription while speaking.** Codex placed it after this, and it
  stays there.
- **No benchmarking on the S26 Ultra**, so Small q5_1 as the default is a
  reasoned choice rather than a measured one. That was the open question
  Codex flagged, and it is why the model picker exists.

## What already helps

`MainActivity.java` records with `AudioRecord` at **16 kHz, mono, 16-bit PCM**
(`NATIVE_SAMPLE_RATE = 16000`, `CHANNEL_IN_MONO`, `ENCODING_PCM_16BIT`).
That is exactly Whisper's expected input, so the capture path needs no change
— the PCM can be handed straight to the model instead of being wrapped in a
WAV and uploaded. The `NativeBridge` JavaScript interface is also already the
right shape for exposing local engines to the web UI.

## Carry-over risks

- **Signing.** The APK is debug-signed. Changing the keystore breaks in-place
  upgrades — everyone must uninstall first, losing local data. Decide the
  production signing story *before* shipping an offline build that stores
  anything worth keeping.
- **Quality.** ML Kit pivoting through English is a real downgrade from the
  cloud models, and the offline path must not silently look like the online
  one. The Cloud/Offline switch should be visible in the result, not just in
  settings.
- **Size.** A 300–700 MB install is a different proposition from today's APK.
  Model downloads need to be resumable and removable, which is what the
  "Manage offline languages" screen is for.

## What to check on the phone

None of this could be verified here, in rough order of what is most likely to
be wrong:

1. **Transcription accuracy and speed** in each of the five languages, and how
   long a one-minute recording really takes. Arabic is the one to watch.
2. **Whether Small q5_1 beats Base q5_1** on that hardware, which decides the
   default.
3. **The microphone permission path**: refuse it, then grant it and record
   again. Refusing used to look like a successful recording that captured
   nothing.
4. **A model download interrupted** by killing the app or dropping Wi-Fi, then
   resumed. A partial file should resume; a damaged one should be discarded
   rather than loaded.
5. **Removing a translation pack**, then confirming that pair refuses cleanly
   instead of returning bad output.
6. **Installing over the existing app** without uninstalling. This should work,
   because the certificate matches, but it is the most expensive thing to get
   wrong.

## Two size traps, both real

The published APK is downloaded through Cloud Run, which refuses to serve any
response over **32 MiB**, with an HTTP 500 from Google's frontend that never
reaches the app's logs. Two separate things pushed past it:

- Building for `armeabi-v7a` as well as `arm64-v8a` (33.3 MiB).
- Bundling ML Kit's Latin OCR model instead of letting Play Services fetch it
  (33.2 MiB against 21.2 MiB unbundled).

And a third that only looked like size: Gradle's incremental packaging left a
16 MiB unreferenced copy of a native library inside the APK, so a 21 MiB build
measured 38 MiB. `gradlew clean stageApk` fixed it, and a test now fails if the
published APK carries more than 2 MiB that is not entry data.

The lesson for anyone measuring this later: **compare clean builds**. An
incremental one led me to the right conclusion for the wrong reason once.

## Updating the app

The app is distributed privately, so nothing updates it automatically. It now
checks on each launch, compares the published `versionCode` with its own, and
offers the newer build. Downloading, verifying and handing it to the installer
happens in the app.

**Android always shows its own install confirmation** for an app from outside
Play. That prompt cannot be removed and should not be. What is removed is
everything around it -- noticing an update exists, opening a browser, finding
the file, checking a fingerprint by eye.

Two things are load-bearing:

- The download is verified against the published SHA-256 **before** the
  installer sees it, and a mismatch deletes the file. It is an executable
  fetched over the public internet and installed over the running app.
- The signature must keep matching. Android refuses to replace an app with one
  signed by a different key, so the debug keystore stays as important as ever.

`REQUEST_INSTALL_PACKAGES` is declared for this, and on Android 8 and later the
person must also allow this specific app to install; the app sends them to that
switch rather than describing where it is.

The one manual step left is a single install of version 8, because the version
before it has no updater in it.
