# LinguaFusion Mobile for iPhone and iPad

The version 1.3 SwiftUI/WKWebView client uses the same PC-hosted mobile
interface as Android and keeps all inference on the LinguaFusion PC. It accepts
the one-use `linguafusion://pair` QR link, stores its per-device credential in
the iOS Keychain, reconnects automatically, and uses AVFoundation for reliable
native microphone recording. A stable HTTPS reverse-tunnel address lets an
approved friend connect over the internet without sharing the PC's network.

## Build the native app

1. Copy or clone this repository to a Mac with Xcode 15 or newer.
2. Open `LinguaFusionMobile.xcodeproj`.
3. Select the app target, choose your Apple Development team and a unique bundle identifier.
4. Connect the iPhone/iPad and press Run, or Archive for TestFlight/App Store distribution.

Windows cannot compile or Apple-sign an `.ipa`; Xcode and an Apple signing
identity are required by Apple. Until then, the installable PWA is available:
start friend access, open the browser fallback from the invitation, then in
Safari tap Share and **Add to Home Screen**. The browser stores its own
credential after the one-use pairing exchange and reconnects automatically.

Browsers require HTTPS for live microphone capture from a non-local address.
The configured internet hostname provides that secure context. With plain LAN
HTTP, the PWA still supports translation, OCR, Reader and imported audio; use
the native app or the HTTPS hostname for live recording.

Do not expose port 8000 directly to the public internet. Use the documented
HTTPS reverse-tunnel setup, one-use invitations, and the local owner dashboard
to pause or revoke each friend independently.
