# Running LinguaFusion on Windows

From the project root:

```powershell
.\scripts\start_backend.ps1
```

In another terminal:

```powershell
.\scripts\start_desktop.ps1
```

The regular backend listens only on this PC. Before starting GPU inference,
confirm the MSI Afterburner **-500 MHz memory-clock offset** is active.

Check health:

```text
http://localhost:8000/health
```

Expected version:

```text
1.0-rc2.12-ui-consumer-polish
```

## Connect an Android, iPhone or iPad

Use the separate LAN launcher. Install the native app first, then scan the QR
card and choose **Open LinguaFusion**. The app exchanges a one-use token and
stores the PC connection automatically:

```powershell
.\scripts\start_mobile_backend.ps1
```

- Android: install
  `android\LinguaFusionMobile\dist\LinguaFusionMobile-debug.apk`, scan a fresh
  QR, and allow microphone access when Speech is first used. Version 1.1 uses
  native WAV recording and remembers the connection.
- iPhone/iPad PWA: choose **Open the browser version** below the QR card, then
  in Safari tap Share and **Add to Home Screen**. Plain LAN HTTP supports
  imported audio but not live browser microphone capture.
- Native iOS: open `ios\LinguaFusionMobile\LinguaFusionMobile.xcodeproj` on a
  Mac, select an Apple Development team, and build to the device. Version 1.1
  accepts the same QR and records through native AVFoundation.

Keep the devices on a trusted private network. The pairing key protects API
requests, but plain LAN HTTP is not suitable for exposure to the public
internet; use a private VPN or an HTTPS reverse proxy for remote access.

Previously paired phones reconnect without another QR or key. To add or reset
a phone, start with:

```powershell
.\scripts\start_mobile_backend.ps1 -PairNewPhone
```
