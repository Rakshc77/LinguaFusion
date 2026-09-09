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

~300–400 MB with Whisper Base, ~650–750 MB with Small. Most of that is
downloaded models, so the APK itself stays much smaller.

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
  is installed, and without `cmdline-tools` they must be added through Android
  Studio's SDK Manager by hand. **This is a prerequisite the owner has to do;
  it cannot be scripted from here.**

So the real order of work is:

1. Migrate `build_apk.ps1` to Gradle, changing nothing else. Verify the APK
   still installs *over* the existing one — the debug keystore must be reused,
   or every install breaks (see below).
2. Offline translation via ML Kit, behind the Cloud/Offline switch.
3. Install NDK + CMake, then offline transcription via whisper.cpp.

Steps 1 and 2 are unblocked. Step 3 waits on an SDK Manager install.

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
