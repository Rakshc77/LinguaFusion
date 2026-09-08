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

The public `/health` endpoint intentionally returns only application identity
and liveness. Detailed model and filesystem diagnostics are available at
`/diagnostics` only to an authenticated device or the local desktop app.

Forwarded client-IP headers are accepted only when the direct connection comes
from loopback, which is where the supported local `cloudflared` service
connects. If a different local reverse proxy is introduced, add only its
specific address or subnet to `LF_TRUSTED_PROXY_NETWORKS`; never use an
unrestricted LAN range without reviewing the owner-control boundary.

Single-file uploads and combined batch contents default to a 100 MB application
limit (`LF_MAX_UPLOAD_MB`). Batches allow 20 files (`LF_MAX_BATCH_FILES`).
Before multipart parsing, request bodies are checked against a 101 MB cap
(`LF_MAX_REQUEST_MB`, default upload limit plus 1 MB for form overhead).
This includes streamed requests without Content-Length. At most four multipart
requests run concurrently (`LF_MAX_CONCURRENT_UPLOADS`); additional uploads
receive HTTP 429 with Retry-After. Receiving a request body has a 120-second
deadline (`LF_UPLOAD_TIMEOUT_SECONDS`). Oversized requests return 413 and slow
uploads return 408. Limits are per backend process; run one worker on this PC.
Health and owner controls remain available while uploads are occupied.
Generated TTS and export files are deleted after their
response is delivered. Abandoned API-created `upload_<uuid>` and `audio_<uuid>`
files are removed after 24 hours on backend startup; unrelated files are kept.

Remote feature requests require a valid owner or paired-device key even when
the owner API key is missing from configuration. Only direct, non-forwarded
loopback requests retain the desktop convenience exemption. Start Uvicorn with
`--no-proxy-headers`: the application validates forwarding headers against the
actual socket peer. The standard backend script and embedded desktop backend
already do this.

## Local backup and recovery

From the project directory, run:

```powershell
.\scripts\backup_storage.ps1
```

This creates a timestamped ZIP in `backups/` containing application storage,
notes, corrections, settings, paired-device credentials, and agent artifacts.
Models and binaries are excluded. SQLite databases use live snapshots rather
than copying open database files. Each snapshot is integrity-checked; archived
files are checked against SHA-256 checksums. Backups are not encrypted and must
remain private. The folder is excluded from Git. Existing backups are never
overwritten or automatically deleted.

Verify an archive and rehearse recovery into a NEW directory:

```powershell
.\.venv\Scripts\python.exe .\scripts\storage_backup.py verify --archive .\backups\YOUR-BACKUP.zip
.\.venv\Scripts\python.exe .\scripts\storage_backup.py restore --archive .\backups\YOUR-BACKUP.zip --destination .\backups\recovered-storage
```

Recovery refuses an existing destination and rejects corrupt, oversized, or
unsafe archive entries. To put recovered storage into service, stop the desktop
and backend first, preserve the current `backend/storage` directory as a
rollback, and replace it with the recovered directory. This replacement is
deliberately manual. Restoring old access data can re-enable previously revoked
devices: review permissions before reconnecting the public tunnel. Live
snapshots are consistent per database, not a transaction across every file;
pause background jobs or stop the backend for a coordinated full snapshot.

Recommended policy: take a backup before updates and after important changes;
retain at least seven daily and four weekly copies, including a private copy
on another drive for disk-failure recovery. No scheduled job or automatic
retention/deletion has been enabled.

## Arabic and Odia offline assets

The first setup for Arabic and Odia speech, OCR, and voices is larger than the
normal application install. Run once:

```powershell
.\scripts\install_arabic_odia_models.ps1
```

Arabic speech uses Whisper; Odia speech uses the dedicated local MMS model.
Both languages are available for translation, OCR, TTS, Reader, and Unicode PDF
export after the installer completes.
