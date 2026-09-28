# Release ledger and gates

`manifest.json` records one candidate version set. Online, Android, and iOS
projects necessarily copy version values into their platform metadata; CI runs
`python scripts/check_release_manifest.py` and fails when they disagree.

The Online candidate is not published merely by changing the manifest. Build
and deploy Cloud Run, then check `/pilot/app-version.json`, sign-in, approval,
translation, OCR, and both short and interrupted multi-part speech. Update the
published-version field only after confirming the live service.

Android 1.27 / code 28 is unchanged. Existing sideload users can update only
with an APK signed by the **same** certificate. Do not regenerate the debug
keystore or silently switch it to a new release key. The expected sideload
certificate fingerprint and published APK hash are pinned in the manifest.
Before any Play distribution, decide whether it is a separate package or an
explicit data/export migration; a different signature is not an in-place
update. Do not upload the signing key to the repository.

iOS 1.5 / build 5 is source-only. A Mac with Xcode, an Apple signing team, and
real-device testing are required before TestFlight. The supported iPhone path
is the native cloud-backed client, not the legacy PC-pairing app. See the iOS
README for the device acceptance checklist. The optional manual GitHub Actions
`iOS source build` compiles on a Mac runner without signing; run it when ready,
then still validate on a real device. It is manual to avoid surprise macOS
runner charges.
