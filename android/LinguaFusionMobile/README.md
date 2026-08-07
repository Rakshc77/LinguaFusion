# LinguaFusion Mobile for Android

This is a thin native Android shell around the mobile interface served by the
LinguaFusion PC backend. It provides Android microphone permission, file
selection, persistent pairing details and an installable APK without moving
models or user data onto the phone.

1. Install the checked-in APK on the phone.
2. On the PC, confirm the GPU underclock and run
   `scripts\start_mobile_backend.ps1 -PairNewPhone`.
3. Scan the QR code and choose **Open LinguaFusion**. The one-use pairing
   token is exchanged inside the app and the PC address is saved.

To rebuild, run
`powershell -ExecutionPolicy Bypass -File .\android\LinguaFusionMobile\build_apk.ps1`.

The checked-in APK is a signed development build for direct testing. A store
release should use a private release keystore and be tested on physical phones.
The wrapper injects the pairing key into WebView local storage; it is not placed
in the page URL or backend access log. Live speech uses the native Android
microphone recorder, which avoids the browser restriction on microphone access
from a private-network HTTP address.

Use only on a trusted private network, or put the PC behind a VPN/HTTPS tunnel.
