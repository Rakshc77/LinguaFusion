# LinguaFusion friend access

Friend access uses a stable HTTPS hostname in front of the local FastAPI
server. Each phone receives its own random credential from a one-use QR code.
The owner can pause, restore, or revoke devices independently at
`http://127.0.0.1:8000/owner/`.

## Network boundary

Do not forward port 8000 on the router. Publish only the local HTTP service
through an HTTPS reverse tunnel. The supplied Cloudflare example maps one
public hostname to `http://127.0.0.1:8000`; any equivalent HTTPS reverse proxy
can be used.

1. Install `cloudflared` from Cloudflare and create a named tunnel/public
   hostname.
2. Point that hostname at `http://127.0.0.1:8000`. A starter configuration is
   available in `config/cloudflared.example.yml`.
3. Start that named tunnel in its own terminal and leave it running:

```powershell
cloudflared tunnel --config .\config\cloudflared.yml run linguafusion
```

4. Confirm MSI Afterburner has the -500 MHz memory-clock offset applied.
5. Start the backend in a second terminal:

```powershell
.\scripts\start_friend_backend.ps1 -PublicUrl https://linguafusion.example.com
```

6. Open `http://127.0.0.1:8000/owner/` on the PC, enter the printed admin key,
   create an invitation,
   and send or show the QR code to one friend. It expires and works once.

The QR contains only a short-lived pairing secret. It never contains the owner
admin key. Disable temporarily with the Allowed/Paused toggle. Revoke only when
the device should be forced to pair again.

Owner-control APIs are restricted to the PC/private network. Friends can use
the public app address, but cannot list devices or change permissions through
the public tunnel. Keep both the tunnel and backend terminals open while
friends are testing.

## Arabic and Odia offline assets

The first setup for Arabic and Odia speech, OCR, and voices is larger than the
normal application install. Run once:

```powershell
.\scripts\install_arabic_odia_models.ps1
```

Arabic speech uses Whisper; Odia speech uses the dedicated local MMS model.
Both languages are available for translation, OCR, TTS, Reader, and Unicode PDF
export after the installer completes.
