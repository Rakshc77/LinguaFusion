# LinguaFusion Mobile for Android

The Android app provides the owner-approved Online service and a phone-only
Offline mode. Offline speech uses whisper.cpp; translation uses downloaded ML
Kit language packs; picture reading uses on-device ML Kit OCR; romanisation
uses ICU. The supported Offline translation languages are English, German,
Arabic, Spanish and French. No PC is involved.

## Translate text in WhatsApp and other apps

Android can send deliberately selected text to LinguaFusion without granting
screen-reading access. Select an editable passage, open the selection menu and
choose **Translate with LinguaFusion**. A compact on-device preview lets the
person choose or swap languages, copy the result, or return it to the calling
field with **Replace selected text**.

Read-only selections cannot be replaced. For chat bubbles that expose Share
instead of Android's standard selection menu, share the text to **Translate
with LinguaFusion**, then use **Copy and return**. Both routes use the same
downloaded Offline language packs and store only the selected language pair.
They request no accessibility, overlay, screen-capture or clipboard-reading
permission. Clipboard access occurs only after the person taps Copy.

The integration is implemented by `ProcessTextActivity`, registered for
`ACTION_PROCESS_TEXT` and text-only `ACTION_SEND`. Do not add background
clipboard monitoring as a fallback; current Android versions restrict it and
it would materially weaken the deliberate-selection privacy boundary.

## Build and publish

The sideload flavour can update itself; the Play flavour omits the APK installer.
Both flavours include the selected-text integration. Always build clean because
incremental APK packaging has previously left enough dead data to exceed Cloud
Run's 32 MiB response limit.

```powershell
cd android\LinguaFusionMobile
.\gradlew.bat clean stageApk
cd ..\..
.venv-cloud\Scripts\python.exe scripts\publish_android_apk.py
```

The published sideload APK must use the existing debug keystore, whose expected
certificate fingerprint is pinned in `test_build_contract.py`. Replacing or
regenerating that key prevents Android from installing over existing copies.
The publish script verifies the signature, scans for credential-shaped data,
copies the APK to the cloud assets and derives its version, size and SHA-256.

Useful source checks:

```powershell
.venv-cloud\Scripts\python.exe -m pytest android\LinguaFusionMobile\test_build_contract.py -q
cd android\LinguaFusionMobile
.\gradlew.bat compileSideloadDebugJavaWithJavac testSideloadDebugUnitTest
```
