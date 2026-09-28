# LinguaFusion iPhone / iPad cloud app

The 1.5 source uses the same Firebase-approved Cloud Run workspace as Android.
The old PC pairing screen and stored PC device key are removed on upgrade. The
app requires internet, and speech/OCR/translation may use paid APIs only after
the in-app consent step. The native AVFoundation microphone supplies five-minute
WAV parts to the authenticated workspace; no separate provider key is embedded.

This is **source only**. It has not been compiled, signed, installed, or tested
on an iPhone from this Windows workstation. Do not invite iPhone testers or
describe it as a released app until the checks below pass on a Mac and device.

## Mac / TestFlight checklist

1. Clone the repository on a Mac with a current Xcode and open
   `LinguaFusionMobile.xcodeproj`. Keep the existing bundle identifier if you
   control it; select your Apple Development team and signing profile.
2. Build for a real iPhone. Fix any SDK/compiler diagnostics, then test first
   launch, email sign-in, account approval, sign-out and sign-in, and an offline
   launch followed by **Try again**.
3. Test microphone permission (allow and deny), a short recording, 6+ minute
   recording, interruption by a call, and a failed later transcription part.
   Verify that retry sends only unfinished parts and no audio is sent after
   Cancel. Test translation, OCR, pronunciation and paid-consent prompts.
4. Confirm status-bar/home-indicator spacing, camera/photo selection, keyboard
   dismissal, external verification links, and VoiceOver on a real device.
5. Archive and distribute through TestFlight only after those checks and a
   privacy review. Keep the same bundle identifier and signing team for app
   updates. Never include Firebase service-account or provider secrets in the
   iOS project.

Release metadata is checked against `release/manifest.json` by
`scripts/check_release_manifest.py`. Online changes still require a separate
Cloud Run deployment; this project build does not deploy them.
