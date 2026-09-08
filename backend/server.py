from __future__ import annotations
import re

import json
import os
import base64
import ipaddress
import secrets as _secrets
import subprocess
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List

from fastapi import APIRouter, Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from backend.config.paths import PROJECT_ROOT, STORAGE_DIR, TEMP_DIR, ensure_runtime_dirs, read_version
from backend.config.runtime import runtime_health
from backend.services.ai_provider_config_service import (
    public_ai_provider_config,
    save_ai_provider_config,
    test_provider,
)
from backend.services.correction_service import apply_corrections, load_corrections, add_correction
from backend.services.document_translation_service import translate_document_preserving_format
from backend.services.document_service import extract_text_from_file as extract_doc_text, export_document, export_subtitles, batch_process_documents, batch_process_ocr
from backend.services.file_reader_service import extract_text_from_file
from backend.services.document_intelligence_service import analyze_document, export_reader_document, normalize_document_text
from backend.services.free_online_correction_service import provider_status, smart_correct_text
from backend.services.language_service import detect_text_language
from backend.services.notes_service import create_note, list_notes, get_note, delete_note
from backend.services.mobile_access_service import (
    authenticate_client,
    claim_pairing,
    create_pairing,
    list_clients,
    register_client,
    registry_summary,
    revoke_client,
    set_client_enabled,
)
from backend.services.ocr_service import extract_text_from_image
from backend.services.piper_service import speak_to_file
from backend.services.reference_lyrics_service import reference_assisted_lyrics
from backend.services.speech_engine_v2 import transcribe_speech_engine_v2
from backend.services.translation_service import translate_with_views
from backend.services.lfie_pipeline_service import (
    analyze_text,
    resolve_entities,
    confidence_report,
    consensus_report,
    translate_with_lfie,
    parse_candidates_json,
    workflow_audit_report,
    attach_lfie_result,
    enforce_workflow_quality,
    quality_decision_from_audit,
    export_quality_preflight,
)
from backend.services.whisper_service import transcribe_audio
from backend.services.agent_task_service import (
    get_agent_engine,
    get_agent_store,
    start_agent_worker,
    stop_agent_worker,
    tool_catalog,
)
from backend.services.agent_planner_service import plan_task, planner_status

ensure_runtime_dirs()

APP_VERSION = read_version()

# ---------------------------------------------------------------------------
# Optional API-key auth.
#
# Set the LINGUAFUSION_API_KEY environment variable before starting the server
# to require clients to send the same value in an "X-API-Key" header.
# If the variable is unset or empty, no authentication is enforced (matches
# the previous localhost-only behaviour).
#
# NOTE: an API key over plain HTTP protects against casual LAN access only.
# Before exposing this server beyond localhost, put it behind HTTPS
# (e.g. Tailscale, Caddy with a self-signed cert, or an SSH tunnel).
# ---------------------------------------------------------------------------
MOBILE_API_KEY_FILE = STORAGE_DIR / "mobile_api_key.txt"
MOBILE_ADMIN_KEY_FILE = STORAGE_DIR / "mobile_admin_key.txt"


def _configured_api_key() -> str:
    env_value = os.environ.get("LINGUAFUSION_API_KEY", "").strip()
    if env_value:
        return env_value
    try:
        return MOBILE_API_KEY_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


API_KEY = _configured_api_key()


def _configured_admin_key() -> str:
    env_value = os.environ.get("LINGUAFUSION_ADMIN_KEY", "").strip()
    if env_value:
        return env_value
    try:
        existing = MOBILE_ADMIN_KEY_FILE.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except OSError:
        pass
    generated = _secrets.token_urlsafe(36)
    try:
        MOBILE_ADMIN_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        MOBILE_ADMIN_KEY_FILE.write_text(generated, encoding="utf-8")
    except OSError:
        pass
    return generated


ADMIN_KEY = _configured_admin_key()
PAIRING_TOKEN = os.environ.get("LINGUAFUSION_PAIRING_TOKEN", "").strip()
PAIRING_WINDOW_SECONDS = 15 * 60
MOBILE_PAIRED_FILE = Path(
    os.environ.get("LINGUAFUSION_PAIRED_FILE", str(STORAGE_DIR / "mobile_paired.flag"))
)
_pairing_deadline = time.monotonic() + PAIRING_WINDOW_SECONDS if PAIRING_TOKEN else 0.0
_pairing_used = False
_pairing_lock = threading.Lock()
_pairing_attempts: dict[str, list[float]] = {}
_pairing_attempts_lock = threading.Lock()
TRUST_PROXY_HEADERS = os.environ.get("LF_TRUST_PROXY_HEADERS", "").strip().lower() in {"1", "true", "yes"}
PUBLIC_ACCESS = os.environ.get("LF_PUBLIC_ACCESS", "").strip().lower() in {"1", "true", "yes"}


def _trusted_proxy_networks() -> tuple[ipaddress._BaseNetwork, ...]:
    """Return the direct peers that may supply forwarding headers.

    Cloudflared connects to the backend from loopback in the supported
    deployment.  Additional proxy networks must be opted into explicitly;
    merely setting LF_TRUST_PROXY_HEADERS must never let an arbitrary LAN
    caller spoof CF-Connecting-IP or X-Forwarded-For.
    """
    configured = os.environ.get("LF_TRUSTED_PROXY_NETWORKS", "127.0.0.1/32,::1/128")
    networks: list[ipaddress._BaseNetwork] = []
    for value in configured.split(","):
        value = value.strip()
        if not value:
            continue
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return tuple(networks)


TRUSTED_PROXY_NETWORKS = _trusted_proxy_networks()


def _direct_peer_is_trusted_proxy(request: Request) -> bool:
    if not request.client:
        return False
    try:
        peer = ipaddress.ip_address(request.client.host)
    except ValueError:
        return False
    return any(peer in network for network in TRUSTED_PROXY_NETWORKS)


def _request_ip(request: Request) -> str:
    if TRUST_PROXY_HEADERS and _direct_peer_is_trusted_proxy(request):
        forwarded = (request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
        try:
            if forwarded:
                return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    return (request.client.host if request.client else "unknown")[:80]


def _check_pairing_rate_limit(request: Request) -> None:
    address = _request_ip(request)
    now = time.time()
    with _pairing_attempts_lock:
        recent = [stamp for stamp in _pairing_attempts.get(address, []) if now - stamp < 600]
        if len(recent) >= 12:
            raise HTTPException(status_code=429, detail="Too many pairing attempts. Wait ten minutes and try again.")
        recent.append(now)
        _pairing_attempts[address] = recent


_backend_access_enabled = True


def get_local_ip() -> str:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def generate_qr_data_url(data_str: str) -> str:
    import io
    import qrcode
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=2,
    )
    qr.add_data(data_str)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    b64_str = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64_str}"


def require_api_key(request: Request, x_api_key: str = Header(default="")) -> None:
    global _backend_access_enabled
    ip = _request_ip(request)
    try:
        addr = ipaddress.ip_address(ip)
        is_local = addr.is_loopback or ip in {"127.0.0.1", "localhost", "::1"}
    except Exception:
        is_local = False

    if not _backend_access_enabled and not is_local:
        raise HTTPException(status_code=403, detail="Backend access has been turned off by the host.")

    if API_KEY and x_api_key and _secrets.compare_digest(x_api_key, API_KEY):
        request.state.mobile_client = {"id": "owner", "name": "Owner", "platform": "desktop", "enabled": True}
        return

    if x_api_key:
        status, client = authenticate_client(
            x_api_key,
            remote_ip=ip,
            user_agent=request.headers.get("user-agent", ""),
        )
        if status == "disabled":
            raise HTTPException(status_code=403, detail="Access paused by the LinguaFusion owner.")
        if status == "valid":
            request.state.mobile_client = client or {"id": "mobile", "name": "Mobile User", "platform": "mobile", "enabled": True}
            return

    # A proxied request is never a direct desktop request, even if proxy
    # recognition was disabled or its forwarding address is malformed.
    forwarded = any(name in request.headers for name in ("cf-connecting-ip", "x-forwarded-for", "forwarded"))
    if is_local and not forwarded:
        request.state.mobile_client = {"id": "local", "name": "Local User", "platform": "desktop", "enabled": True}
        return

    raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header.")


def require_admin_key(request: Request, x_admin_key: str = Header(default="")) -> None:
    if PUBLIC_ACCESS:
        try:
            owner_address = ipaddress.ip_address(_request_ip(request))
        except ValueError:
            owner_address = None
        if owner_address is None or not (owner_address.is_loopback or owner_address.is_private):
            raise HTTPException(status_code=403, detail="Owner controls are available only on the PC or private network.")
    if not x_admin_key or not _secrets.compare_digest(x_admin_key, ADMIN_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Key header.")


# ---------------------------------------------------------------------------
# Temp-file hygiene.
# ---------------------------------------------------------------------------
TEMP_MAX_AGE_SECONDS = 24 * 60 * 60  # purge leftovers older than 24h on startup


def _purge_stale_temp_files() -> None:
    try:
        now = time.time()
        for path in TEMP_DIR.iterdir():
            # The shared temp folder also contains user imports, diagnostics
            # and test artifacts. Only sweep files allocated by this API.
            if not re.fullmatch(r"(?:upload|audio)_[0-9a-f]{32}\.[A-Za-z0-9]+", path.name) or not path.is_file():
                continue
            try:
                if now - path.stat().st_mtime > TEMP_MAX_AGE_SECONDS:
                    path.unlink(missing_ok=True)
            except OSError:
                pass
    except OSError:
        pass


def _unlink_quietly(*paths: Path) -> None:
    for path in paths:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass


@contextmanager
def temp_files() -> Iterator[List[Path]]:
    """Collect per-request temp paths and delete them when the request ends."""
    paths: List[Path] = []
    try:
        yield paths
    finally:
        _unlink_quietly(*paths)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_runtime_dirs()
    _purge_stale_temp_files()
    start_agent_worker()
    try:
        yield
    finally:
        stop_agent_worker()


app = FastAPI(
    title="LinguaFusion",
    description="Offline-first speech, translation, reader, notes and OCR assistant.",
    version=APP_VERSION,
    lifespan=lifespan,
)
from backend.request_limits import RequestLimitsMiddleware

app.add_middleware(
    RequestLimitsMiddleware,
    max_bytes=max(1, int(os.environ.get('LF_MAX_REQUEST_MB', str(max(1, int(os.environ.get('LF_MAX_UPLOAD_MB', '100'))) + 1)))) * 1024 * 1024,
    max_uploads=max(1, int(os.environ.get('LF_MAX_CONCURRENT_UPLOADS', '4'))),
    timeout_seconds=max(1, int(os.environ.get('LF_UPLOAD_TIMEOUT_SECONDS', '120'))),
)


@app.get("/health", include_in_schema=False)
@app.get("/api/health", include_in_schema=False)
async def health_check():
    """Minimal unauthenticated liveness response safe for public probes."""
    return {
        "ok": True,
        "app": "LinguaFusion",
        "version": APP_VERSION,
        "status": "running",
        "auth_required": bool(API_KEY or PUBLIC_ACCESS),
    }


@app.get("/", include_in_schema=False)
async def root_redirect(request: Request):
    """Redirect browser navigation to mobile interface, or return JSON status for API probes."""
    accept = request.headers.get("accept", "").lower()
    if "text/html" in accept and "application/json" not in accept:
        return RedirectResponse(url="/mobile/")
    return {
        "ok": True,
        "app": "LinguaFusion",
        "version": APP_VERSION,
        "status": "running",
        "auth_required": bool(API_KEY),
        "modes": ["translate", "reader", "speech", "ocr", "notes", "settings"],
    }


@app.post("/pair")
@app.post("/api/pair/exchange")
@app.post("/api/mobile/pair/exchange")
@app.post("/pair/exchange")
@app.post("/mobile/pair/exchange")
async def exchange_mobile_pairing_token(request: Request) -> Dict[str, Any]:
    """Exchange a one-use QR token for one unique device credential."""
    global _pairing_used
    _check_pairing_rate_limit(request)

    supplied_token = ""
    device_name = "Unnamed phone"
    platform = "unknown"
    try:
        payload = await request.json()
        if isinstance(payload, dict):
            supplied_token = str(payload.get("token", "")).strip()
            device_name = str(payload.get("device_name", "Unnamed phone")).strip()
            platform = str(payload.get("platform", "unknown")).strip()
    except Exception:
        pass

    if not supplied_token:
        try:
            form_data = await request.form()
            supplied_token = str(form_data.get("token", "")).strip()
            device_name = str(form_data.get("device_name", "Unnamed phone")).strip()
            platform = str(form_data.get("platform", "unknown")).strip()
        except Exception:
            pass

    if not supplied_token:
        raise HTTPException(status_code=403, detail="Invalid pairing link.")
    try:
        device_key, mobile_client = claim_pairing(
            supplied_token,
            device_name,
            platform,
            _request_ip(request),
            request.headers.get("user-agent", ""),
        )
    except PermissionError:
        # Backward-compatible one-use token from start_mobile_backend.ps1.
        if not PAIRING_TOKEN:
            raise HTTPException(status_code=403, detail="Invalid pairing link.")
        with _pairing_lock:
            if time.monotonic() > _pairing_deadline:
                raise HTTPException(status_code=410, detail="Pairing link expired. Create a fresh QR code.")
            if _pairing_used:
                raise HTTPException(status_code=410, detail="Pairing link was already used.")
            if not _secrets.compare_digest(supplied_token, PAIRING_TOKEN):
                raise HTTPException(status_code=403, detail="Invalid pairing link.")
            _pairing_used = True
        device_key, mobile_client = register_client(
            device_name,
            platform,
            _request_ip(request),
            request.headers.get("user-agent", ""),
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=410, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=410, detail=str(exc))
    try:
        MOBILE_PAIRED_FILE.parent.mkdir(parents=True, exist_ok=True)
        MOBILE_PAIRED_FILE.write_text("paired\n", encoding="utf-8")
    except OSError:
        pass
    return {
        "ok": True,
        "api_key": device_key,
        "client": mobile_client,
        "expires": "until revoked by the owner",
    }


@app.get("/api/access/status", dependencies=[Depends(require_admin_key)])
async def get_access_status() -> Dict[str, Any]:
    local_ip = get_local_ip()
    port = int(os.environ.get("PORT", "8000"))
    public_url = os.environ.get("LINGUAFUSION_PUBLIC_URL", "").strip().rstrip("/")
    if not public_url:
        public_url = f"http://{local_ip}:{port}"
    return {
        "ok": True,
        "enabled": _backend_access_enabled,
        "local_ip": local_ip,
        "public_url": public_url,
        "clients": list_clients(),
        "summary": registry_summary(),
    }


@app.post("/api/access/toggle", dependencies=[Depends(require_admin_key)])
async def toggle_access_status(request: Request) -> Dict[str, Any]:
    global _backend_access_enabled
    try:
        body = await request.json()
    except Exception:
        body = {}
    if isinstance(body, dict) and "enabled" in body:
        _backend_access_enabled = bool(body["enabled"])
    else:
        _backend_access_enabled = not _backend_access_enabled
    return {"ok": True, "enabled": _backend_access_enabled}


@app.get("/api/access/tunnel/status", dependencies=[Depends(require_admin_key)])
async def api_tunnel_status() -> Dict[str, Any]:
    from backend.services.tunnel_service import get_tunnel_status
    return get_tunnel_status()


@app.post("/api/access/tunnel/toggle", dependencies=[Depends(require_admin_key)])
async def api_tunnel_toggle(request: Request) -> Dict[str, Any]:
    from backend.services.tunnel_service import get_tunnel_status, start_tunnel, stop_tunnel
    try:
        body = await request.json()
    except Exception:
        body = {}
    enable = body.get("enabled")
    if enable is True:
        return start_tunnel()
    elif enable is False:
        return stop_tunnel()
    else:
        status = get_tunnel_status()
        if status.get("active"):
            return stop_tunnel()
        else:
            return start_tunnel()


@app.get("/api/access/qr", dependencies=[Depends(require_admin_key)])
async def get_access_qr(label: str = "Friend device", public_url: str = "") -> Dict[str, Any]:
    from backend.services.tunnel_service import get_tunnel_status
    local_ip = get_local_ip()
    port = int(os.environ.get("PORT", "8000"))
    pub = public_url.strip().rstrip("/")
    if pub and (pub.startswith("http://") or pub.startswith("https://")):
        base_url = pub
    else:
        tunnel_st = get_tunnel_status()
        if tunnel_st.get("active") and tunnel_st.get("url"):
            base_url = tunnel_st["url"]
        else:
            base_url = f"http://{local_ip}:{port}"
    pairing = create_pairing(public_url=base_url, label=label, expires_minutes=15)
    qr_data_url = generate_qr_data_url(pairing["web_url"])
    return {
        "ok": True,
        "pairing": pairing,
        "qr_data_url": qr_data_url,
    }


@app.get("/api/access/clients", dependencies=[Depends(require_admin_key)])
async def get_access_clients() -> Dict[str, Any]:
    return {"ok": True, "clients": list_clients()}


@app.post("/api/access/clients/{client_id}/toggle", dependencies=[Depends(require_admin_key)])
async def toggle_client_access(client_id: str, request: Request) -> Dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        body = {}
    enabled = bool(body.get("enabled", True)) if isinstance(body, dict) else True
    updated = set_client_enabled(client_id, enabled)
    if updated is None:
        raise HTTPException(status_code=404, detail="Client not found.")
    return {"ok": True, "client": updated}


@app.delete("/api/access/clients/{client_id}", dependencies=[Depends(require_admin_key)])
async def revoke_client_access(client_id: str) -> Dict[str, Any]:
    success = revoke_client(client_id)
    if not success:
        raise HTTPException(status_code=404, detail="Client not found.")
    return {"ok": True, "revoked_id": client_id}

def _resolve_static_dir(subpath: str) -> Path:
    candidates = [
        Path(__file__).resolve().parent / subpath,
        PROJECT_ROOT / "backend" / subpath,
        Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) / "backend" / subpath,
        Path(sys.executable).resolve().parent / "backend" / subpath,
        Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) / subpath,
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return Path(__file__).resolve().parent / subpath


class NoCacheStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs) -> FileResponse:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


MOBILE_WEB_DIR = _resolve_static_dir("mobile_web")
OWNER_WEB_DIR = _resolve_static_dir("owner_web")
DESKTOP_ASSETS_DIR = PROJECT_ROOT / "desktop" / "assets"
if MOBILE_WEB_DIR.is_dir():
    app.mount("/mobile", NoCacheStaticFiles(directory=str(MOBILE_WEB_DIR), html=True), name="mobile")
if OWNER_WEB_DIR.is_dir():
    app.mount("/owner", NoCacheStaticFiles(directory=str(OWNER_WEB_DIR), html=True), name="owner")
if DESKTOP_ASSETS_DIR.is_dir():
    app.mount("/app-assets", StaticFiles(directory=str(DESKTOP_ASSETS_DIR)), name="app-assets")

# All feature endpoints hang off this router so the auth dependency applies in
# one place. Root and /health stay on the bare app for unauthenticated
# connectivity checks from clients.
api = APIRouter(dependencies=[Depends(require_api_key)])


@api.get("/pair/verify", tags=["System"])
def verify_pairing(request: Request):
    """Authenticated check to verify device pairing key validity."""
    client = getattr(request.state, "mobile_client", {}) or {}
    return {
        "ok": True,
        "authenticated": True,
        "client_id": client.get("id", "local"),
        "client_name": client.get("name", "Local User"),
    }


def api_error(stage: str, exc: Exception | str, status_code: int = 500, **extra: Any) -> JSONResponse:
    """Uniform error payload with a real HTTP status code.

    The body shape ({ok, stage, error, ...}) is unchanged from earlier
    versions, so clients that inspect the JSON keep working. Clients that
    previously relied on errors arriving with HTTP 200 must now also accept
    4xx/5xx responses (most HTTP libraries parse the JSON body either way).
    """
    if isinstance(exc, HTTPException):
        status_code = exc.status_code
        message = str(exc.detail)
    else:
        message = str(exc)
    payload = {
        "ok": False,
        "stage": stage,
        "error": message,
        **extra,
    }
    return JSONResponse(status_code=status_code, content=payload)


MAX_UPLOAD_BYTES = max(1, int(os.environ.get("LF_MAX_UPLOAD_MB", "100"))) * 1024 * 1024
MAX_BATCH_FILES = max(1, int(os.environ.get('LF_MAX_BATCH_FILES', '20')))


def read_batch_uploads(files: List[UploadFile]):
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(413, f'Batch uploads are limited to {MAX_BATCH_FILES} files.')
    result = []
    total = 0
    for file in files:
        content = file.file.read(MAX_UPLOAD_BYTES - total + 1)
        total += len(content)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(413, 'Combined batch files exceed the upload limit.')
        result.append((file.filename, content))
    return result


def save_upload(upload_file: UploadFile) -> Path:
    ensure_runtime_dirs()
    filename = upload_file.filename or "upload.bin"
    suffix = Path(filename).suffix.lower() or ".bin"
    if len(suffix) > 12:
        suffix = ".bin"
    path = TEMP_DIR / f"upload_{uuid.uuid4().hex}{suffix}"
    written = 0
    try:
        with open(path, "wb") as buffer:
            while True:
                chunk = upload_file.file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Uploads are limited to {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
                    )
                buffer.write(chunk)
    except Exception:
        _unlink_quietly(path)
        raise
    return path


def convert_to_wav(input_path: Path) -> Path:
    # Microphone recordings and imported WAV files are already directly
    # readable by faster-whisper.  The old whisper.cpp pipeline required an
    # ffmpeg normalization pass for every upload, but keeping that requirement
    # after the faster-whisper migration made even valid WAV transcription fail
    # whenever the external ffmpeg executable was not installed/on PATH.
    if input_path.suffix.lower() == ".wav":
        return input_path

    output_path = TEMP_DIR / f"audio_{uuid.uuid4().hex}.wav"
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(output_path),
    ]
    try:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=True, creationflags=creation_flags)
    except (FileNotFoundError, PermissionError) as exc:
        raise RuntimeError("ffmpeg was not found. Install ffmpeg or add it to PATH before using speech/audio features.") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError((exc.stderr or "Audio conversion failed.").strip()) from exc
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Audio conversion did not create a valid WAV file.")
    return output_path


@api.get("/diagnostics", tags=["System"])
def diagnostics():
    return runtime_health()


# ---------------------------------------------------------------------------
# Owner-only friend access management.
# ---------------------------------------------------------------------------


def _pairing_qr_data_uri(value: str) -> str:
    from reportlab.graphics import renderSVG
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing

    widget = QrCodeWidget(value, barLevel="M")
    left, bottom, right, top = widget.getBounds()
    width = max(right - left, 1)
    height = max(top - bottom, 1)
    size = 420
    drawing = Drawing(size, size, transform=[size / width, 0, 0, size / height, -left * size / width, -bottom * size / height])
    drawing.add(widget)
    svg = renderSVG.drawToString(drawing)
    if isinstance(svg, str):
        svg = svg.encode("utf-8")
    encoded = base64.b64encode(svg).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


owner_api = APIRouter(prefix="/owner-api", dependencies=[Depends(require_admin_key)])


@owner_api.get("/status", tags=["Owner access"])
def owner_access_status():
    return {
        "ok": True,
        "summary": registry_summary(),
        "public_url": os.environ.get("LINGUAFUSION_PUBLIC_URL", "").strip().rstrip("/"),
    }


@owner_api.get("/clients", tags=["Owner access"])
def owner_clients():
    return {
        "ok": True,
        "clients": list_clients(),
        "summary": registry_summary(),
        "public_url": os.environ.get("LINGUAFUSION_PUBLIC_URL", "").strip().rstrip("/"),
    }


@owner_api.post("/clients/{client_id}/enabled", tags=["Owner access"])
async def owner_set_client_enabled(client_id: str, request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid access-control request.")
    if not isinstance(payload, dict) or not isinstance(payload.get("enabled"), bool):
        raise HTTPException(status_code=422, detail="The enabled field must be true or false.")
    client = set_client_enabled(client_id, payload["enabled"])
    if client is None:
        raise HTTPException(status_code=404, detail="Friend device not found.")
    return {"ok": True, "client": client, "summary": registry_summary()}


@owner_api.delete("/clients/{client_id}", tags=["Owner access"])
def owner_revoke_client(client_id: str):
    if not revoke_client(client_id):
        raise HTTPException(status_code=404, detail="Friend device not found.")
    return {"ok": True, "revoked": True, "summary": registry_summary()}


@owner_api.post("/pairings", tags=["Owner access"])
async def owner_create_pairing(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid pairing request.")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid pairing request.")
    public_url = str(payload.get("public_url") or os.environ.get("LINGUAFUSION_PUBLIC_URL", "")).strip()
    label = str(payload.get("label", "Friend's device"))
    expires_minutes = payload.get("expires_minutes", 15)
    try:
        pairing = create_pairing(public_url, label, int(expires_minutes))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    pairing["qr_data_uri"] = _pairing_qr_data_uri(pairing["app_url"])
    return {"ok": True, "pairing": pairing}


app.include_router(owner_api)


# ---------------------------------------------------------------------------
# Speech endpoints.
#
# NOTE: these are deliberately plain `def`, not `async def`. FastAPI runs sync
# endpoints in a worker threadpool, so a long transcription no longer blocks
# the event loop (previously one transcription froze every other request,
# including /health). Keep any endpoint that performs blocking work (model
# inference, subprocess, disk I/O) as plain `def`.
# ---------------------------------------------------------------------------


@api.post("/stt/transcribe", tags=["Speech"])
def stt_transcribe(
    file: UploadFile = File(...),
    language: str = Form("auto"),
    smart_mode: str = Form("offline"),
):
    with temp_files() as tmp:
        try:
            uploaded_path = save_upload(file)
            tmp.append(uploaded_path)
            wav_path = convert_to_wav(uploaded_path)
            tmp.append(wav_path)
            result = transcribe_speech_engine_v2(wav_path, language=language, smart_mode=smart_mode, music_mode=False)
            if isinstance(result, dict):
                result = attach_lfie_result(result, workflow="speech", output_text=result.get("text", ""))
            return result
        except Exception as exc:
            return api_error("speech_transcription", exc, text="", language=language)


@api.post("/stt/full-song-pass", tags=["Speech"])
def stt_full_song_pass(
    file: UploadFile = File(...),
    language: str = Form("auto"),
    smart_mode: str = Form("free_auto"),
):
    with temp_files() as tmp:
        try:
            uploaded_path = save_upload(file)
            tmp.append(uploaded_path)
            wav_path = convert_to_wav(uploaded_path)
            tmp.append(wav_path)
            result = transcribe_speech_engine_v2(wav_path, language=language, smart_mode=smart_mode, music_mode=True)
            if isinstance(result, dict):
                result = attach_lfie_result(result, workflow="speech", output_text=result.get("text", ""))
            return result
        except Exception as exc:
            return api_error("song_transcription", exc, text="", language=language)


@api.post("/stt/reference-lyrics-pass", tags=["Speech"])
def stt_reference_lyrics_pass(
    file: UploadFile = File(...),
    reference_lyrics: str = Form(...),
    language: str = Form("auto"),
    smart_mode: str = Form("free_auto"),
):
    with temp_files() as tmp:
        try:
            uploaded_path = save_upload(file)
            tmp.append(uploaded_path)
            wav_path = convert_to_wav(uploaded_path)
            tmp.append(wav_path)
            base = transcribe_speech_engine_v2(wav_path, language=language, smart_mode=smart_mode, music_mode=True)
            aligned = reference_assisted_lyrics(base.get("text", ""), reference_lyrics)
            aligned.update({
                "language": base.get("language", "en"),
                "model": base.get("model"),
                "base_provider": base.get("provider"),
                "base_engine": base.get("engine"),
                "chunk_count": base.get("chunk_count"),
                "provider_status": base.get("provider_status"),
            })
            if isinstance(aligned, dict):
                aligned = attach_lfie_result(aligned, workflow="speech", input_text=reference_lyrics, output_text=aligned.get("text", ""))
            return aligned
        except Exception as exc:
            return api_error("reference_lyrics_pass", exc, text="", language=language)


@api.get("/corrections", tags=["Speech"])
def corrections_list():
    return {"ok": True, "corrections": load_corrections()}


@api.post("/corrections/add", tags=["Speech"])
def corrections_add(wrong: str = Form(...), correct: str = Form(...)):
    try:
        return {"ok": True, "corrections": add_correction(wrong, correct)}
    except Exception as exc:
        return api_error("corrections_add", exc)


@api.post("/corrections/apply", tags=["Speech"])
def corrections_apply(text: str = Form(...)):
    return {"ok": True, "text": apply_corrections(text)}


@api.get("/corrections/providers", tags=["Speech"])
def corrections_providers():
    return provider_status()


@api.post("/corrections/smart", tags=["Speech"])
def corrections_smart(text: str = Form(...), mode: str = Form("free_auto"), language: str = Form("auto")):
    try:
        return smart_correct_text(text, mode, language)
    except Exception as exc:
        return api_error("corrections_smart", exc, text=text, provider="error")


@api.get("/ai/providers/config", tags=["Speech"])
def ai_provider_config_get():
    return public_ai_provider_config()


@api.post("/ai/providers/config", tags=["Speech"])
def ai_provider_config_save(
    smart_mode_enabled: bool = Form(False),
    default_mode: str = Form("free_auto"),
    ollama_enabled: bool = Form(True),
    ollama_url: str = Form("http://localhost:11434"),
    ollama_model: str = Form("llama3.1:8b"),
    ollama_num_gpu: int = Form(999),
    ollama_keep_alive: int = Form(-1),
):
    save_ai_provider_config({
        "smart_mode_enabled": smart_mode_enabled,
        "default_mode": default_mode,
        "ollama": {
            "enabled": ollama_enabled,
            "url": ollama_url,
            "model": ollama_model,
            "num_gpu": max(1, ollama_num_gpu),
            "keep_alive": ollama_keep_alive,
        },
    })
    public = public_ai_provider_config()
    public["saved"] = True
    return public


@api.post("/ai/providers/test", tags=["Speech"])
def ai_provider_test(provider: str = Form(...)):
    return test_provider(provider)


# ---------------------------------------------------------------------------
# LFIE endpoints.
#
# These parse the raw request themselves (JSON, form, or query params), which
# genuinely requires `async def`. The heavy analysis calls are therefore
# pushed to the threadpool explicitly with run_in_threadpool so they don't
# block the event loop.
# ---------------------------------------------------------------------------


async def _read_request_payload(request: Request) -> Dict[str, Any]:
    """Read JSON or form payloads without enforcing one transport shape.

    Phase 4 exposes LFIE as a shared API layer. These endpoints intentionally
    accept normal JSON clients and form-based desktop clients so internal
    services, tests and future UI code share one stable contract.

    NOTE: avoid putting sensitive values in query parameters; they end up in
    access logs. The query-param fallback exists for quick smoke tests only.
    """
    content_type = (request.headers.get("content-type") or "").lower()

    if "application/json" in content_type:
        body = await request.body()
        if not body:
            return {}
        try:
            parsed = json.loads(body.decode("utf-8"))
        except Exception:
            return {"text": body.decode("utf-8", errors="replace")}
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, str):
            return {"text": parsed}
        return {"payload": parsed}

    # application/x-www-form-urlencoded and multipart/form-data
    try:
        form = await request.form()
        if form:
            return {str(k): v for k, v in form.items()}
    except Exception:
        pass

    # Query-param fallback for scripts and quick smoke tests.
    if request.query_params:
        return dict(request.query_params)

    body = await request.body()
    if body:
        return {"text": body.decode("utf-8", errors="replace")}
    return {}


def _payload_text(payload: Dict[str, Any], default: str = "") -> str:
    value = payload.get("text", default)
    if value is None:
        return default
    return str(value)


def _payload_str(payload: Dict[str, Any], key: str, default: str = "") -> str:
    value = payload.get(key, default)
    if value is None:
        return default
    return str(value)


def _payload_candidates(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    if "candidates" in payload:
        value = payload.get("candidates")
        if isinstance(value, list):
            parsed = value
        elif isinstance(value, str):
            parsed = json.loads(value)
        else:
            parsed = []
    elif "candidates_json" in payload:
        parsed = json.loads(str(payload.get("candidates_json") or "[]"))
    elif "payload" in payload and isinstance(payload.get("payload"), list):
        parsed = payload["payload"]
    else:
        parsed = []

    output: list[Dict[str, Any]] = []
    for item in parsed:
        if isinstance(item, dict):
            output.append(item)
        else:
            output.append({"text": str(item)})
    return output


@api.get("/lfie/status", tags=["LFIE"])
def lfie_status():
    return {
        "ok": True,
        "engine": "lfie_v2_shared",
        "version": APP_VERSION,
        "components": [
            "audio_analyzer",
            "confidence_engine",
            "learning_engine",
            "entity_resolver",
            "ai_router",
            "consensus_engine",
            "translation_bridge",
            "export_quality_layer",
            "decision_enforcer",
        ],
        "mode": "local-first",
        "integration_targets": ["speech", "ocr", "reader", "translation", "notes", "search"],
    }


@api.post("/lfie/analyze", tags=["LFIE"])
async def lfie_analyze(request: Request):
    try:
        payload = await _read_request_payload(request)
        text = _payload_text(payload)
        workflow = _payload_str(payload, "workflow", "generic")
        privacy_mode = _payload_str(payload, "privacy_mode", "offline")
        return await run_in_threadpool(analyze_text, text, workflow=workflow, privacy_mode=privacy_mode)
    except Exception as exc:
        return api_error("lfie_analyze", exc)


@api.post("/lfie/entities", tags=["LFIE"])
async def lfie_entities(request: Request):
    try:
        payload = await _read_request_payload(request)
        text = _payload_text(payload)
        workflow = _payload_str(payload, "workflow", "generic")
        return await run_in_threadpool(resolve_entities, text, workflow=workflow)
    except Exception as exc:
        return api_error("lfie_entities", exc)


@api.post("/lfie/confidence", tags=["LFIE"])
async def lfie_confidence(request: Request):
    try:
        payload = await _read_request_payload(request)
        text = _payload_text(payload)
        workflow = _payload_str(payload, "workflow", "generic")
        return await run_in_threadpool(confidence_report, text, workflow=workflow)
    except Exception as exc:
        return api_error("lfie_confidence", exc)


@api.post("/lfie/consensus", tags=["LFIE"])
async def lfie_consensus(request: Request):
    try:
        payload = await _read_request_payload(request)
        candidates = _payload_candidates(payload)
        workflow = _payload_str(payload, "workflow", "generic")
        return await run_in_threadpool(consensus_report, candidates, workflow=workflow)
    except Exception as exc:
        return api_error("lfie_consensus", exc)


@api.post("/lfie/workflow/audit", tags=["LFIE"])
async def lfie_workflow_audit(request: Request):
    try:
        payload = await _read_request_payload(request)
        workflow = _payload_str(payload, "workflow", "generic")
        privacy_mode = _payload_str(payload, "privacy_mode", "offline")
        inputs = payload.get("inputs", {}) if isinstance(payload.get("inputs", {}), dict) else {"text": _payload_text(payload)}
        outputs = payload.get("outputs", {}) if isinstance(payload.get("outputs", {}), dict) else {}
        return await run_in_threadpool(workflow_audit_report, workflow=workflow, inputs=inputs, outputs=outputs, privacy_mode=privacy_mode)
    except Exception as exc:
        return api_error("lfie_workflow_audit", exc)


@api.post("/lfie/workflow/decision", tags=["LFIE"])
async def lfie_workflow_decision(request: Request):
    try:
        payload = await _read_request_payload(request)
        workflow = _payload_str(payload, "workflow", "generic")
        privacy_mode = _payload_str(payload, "privacy_mode", "offline")
        strict = bool(payload.get("strict", False)) if isinstance(payload, dict) else False
        inputs = payload.get("inputs", {}) if isinstance(payload.get("inputs", {}), dict) else {"text": _payload_text(payload)}
        outputs = payload.get("outputs", {}) if isinstance(payload.get("outputs", {}), dict) else {}
        audit = await run_in_threadpool(workflow_audit_report, workflow=workflow, inputs=inputs, outputs=outputs, privacy_mode=privacy_mode)
        decision = quality_decision_from_audit(audit, strict=strict)
        return {"ok": True, "workflow": audit.get("workflow"), "audit": audit, "decision": decision}
    except Exception as exc:
        return api_error("lfie_workflow_decision", exc)


@api.post("/lfie/translate", tags=["LFIE"])
async def lfie_translate(request: Request):
    try:
        payload = await _read_request_payload(request)
        text = _payload_text(payload)
        source_lang = _payload_str(payload, "source_lang", "auto")
        target_lang = _payload_str(payload, "target_lang", "de")
        return await run_in_threadpool(translate_with_lfie, text, source_lang=source_lang, target_lang=target_lang)
    except Exception as exc:
        return api_error("lfie_translate", exc)


# ---------------------------------------------------------------------------
# Translation endpoints.
# ---------------------------------------------------------------------------


@api.post("/translate", tags=["Translation"])
def translate_only(text: str = Form(...), source_lang: str = Form(...), target_lang: str = Form(...)):
    try:
        result = translate_with_views(text, source_lang, target_lang)
        if isinstance(result, dict):
            result = attach_lfie_result(result, workflow="translation", input_text=text, output_text=result.get("translated_text", ""))
        return result
    except Exception as exc:
        return api_error("translation", exc, translated_text="", route=[], views=None)


@api.post("/translate/document", tags=["Translation"])
def translate_document(file: UploadFile = File(...), source_lang: str = Form("auto"), target_lang: str = Form("de")):
    with temp_files() as tmp:
        try:
            uploaded_path = save_upload(file)
            tmp.append(uploaded_path)
            extracted = extract_text_from_file(uploaded_path, source_lang)
            if not extracted.get("ok"):
                return api_error("file_import", extracted.get("error", "File import failed."), status_code=422)

            text = extracted.get("text", "")
            if source_lang == "auto":
                detected = detect_text_language(text)
                if not detected.get("ok"):
                    return api_error("language_detection", detected.get("error", "Language detection failed."), status_code=422)
                resolved_source_lang = "auto" if detected.get("is_mixed") else detected.get("language")
            else:
                resolved_source_lang = source_lang
                detected = {"ok": True, "language": source_lang, "confidence": 1.0, "error": None}

            translation = translate_with_views(text, resolved_source_lang, target_lang)
            payload = {
                "ok": translation.get("ok"),
                "file_type": extracted.get("file_type"),
                "method": extracted.get("method"),
                "source_lang": resolved_source_lang,
                "target_lang": target_lang,
                "detected_language": detected,
                "original_text": text,
                "translation": translation,
            }
            translated_text = translation.get("translated_text", "") if isinstance(translation, dict) else ""
            payload = attach_lfie_result(payload, workflow="translation", input_text=text, output_text=translated_text)
            return payload
        except Exception as exc:
            return api_error("document_translation", exc)


@api.post("/translate/document/export", tags=["Translation"])
def translate_document_export(
    file: UploadFile = File(...),
    source_lang: str = Form("auto"),
    target_lang: str = Form("de"),
    output_format: str = Form("docx"),
):
    uploaded_path: Path | None = None
    try:
        uploaded_path = save_upload(file)
        exported_path = translate_document_preserving_format(uploaded_path, source_lang, target_lang, output_format)
        suffix = "." + output_format.lower().strip().lstrip(".")
        filename = f"{Path(file.filename or 'document').stem}_translated{suffix}"
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if suffix == ".docx" else ("application/pdf" if suffix == ".pdf" else "text/plain")
        # The uploaded input is deleted after the response finishes streaming.
        return FileResponse(
            exported_path,
            media_type=media_type,
            filename=filename,
            background=BackgroundTask(_unlink_quietly, uploaded_path, exported_path),
        )
    except Exception as exc:
        if uploaded_path is not None:
            _unlink_quietly(uploaded_path)
        return api_error("format_preserving_export", exc)


# ---------------------------------------------------------------------------
# TTS / interpreter endpoints.
# ---------------------------------------------------------------------------


@api.post("/tts/speak", tags=["TTS"])
def tts_speak(text: str = Form(...), lang: str = Form("en"), speed: float = Form(1.0)):
    try:
        speech_path = speak_to_file(text, lang, f"tts_{uuid.uuid4().hex}.wav", speed=speed)
        return FileResponse(
            speech_path,
            media_type="audio/wav",
            filename="speech.wav",
            background=BackgroundTask(_unlink_quietly, speech_path),
        )
    except Exception as exc:
        return api_error("tts", exc)


@api.post("/interpreter/full", tags=["Interpreter"])
def interpreter_full(file: UploadFile = File(...), source_lang: str = Form("auto"), target_lang: str = Form("de")):
    with temp_files() as tmp:
        try:
            uploaded_path = save_upload(file)
            tmp.append(uploaded_path)
            wav_path = convert_to_wav(uploaded_path)
            tmp.append(wav_path)
            stt_result = transcribe_speech_engine_v2(wav_path, language=source_lang, smart_mode="offline", music_mode=False)
            if not stt_result.get("ok"):
                return api_error("stt", stt_result.get("error", "Speech transcription failed."), status_code=422)

            detected_text = stt_result.get("text", "")
            translation_source = stt_result.get("language") or ("en" if source_lang == "auto" else source_lang)
            if translation_source == "auto":
                translation_source = "en"
            translation_result = translate_with_views(detected_text, translation_source, target_lang)
            if not translation_result.get("ok"):
                return api_error("translation", translation_result.get("error", "Translation failed."), original_text=detected_text, status_code=422)

            payload = {"ok": True, "original_text": detected_text, "target_lang": target_lang, "translation": translation_result}
            payload = attach_lfie_result(payload, workflow="speech", output_text=detected_text)
            translated_text = translation_result.get("translated_text", "") if isinstance(translation_result, dict) else ""
            payload["translation_lfie"] = workflow_audit_report("translation", inputs={"text": detected_text}, outputs={"text": translated_text})
            return payload
        except Exception as exc:
            return api_error("interpreter", exc)


# ---------------------------------------------------------------------------
# Notes endpoints.
# ---------------------------------------------------------------------------


@api.post("/notes/create", tags=["Notes"])
def notes_create(title: str = Form(...), content: str = Form(...), language: str = Form("en")):
    try:
        note = create_note(title, content, language)
        note["lfie"] = workflow_audit_report("notes", inputs={"title": title, "content": content})
        return note
    except Exception as exc:
        return api_error("notes_create", exc)


@api.get("/notes", tags=["Notes"])
def notes_list():
    try:
        return list_notes()
    except Exception as exc:
        return api_error("notes_list", exc)


@api.get("/notes/{note_id}", tags=["Notes"])
def notes_get(note_id: int):
    try:
        note = get_note(note_id)
        if not note:
            return api_error("notes_get", "Note not found", status_code=404, note=None)
        return {"ok": True, "note": note, "error": None}
    except Exception as exc:
        return api_error("notes_get", exc)


@api.delete("/notes/{note_id}", tags=["Notes"])
def notes_delete(note_id: int):
    try:
        deleted = delete_note(note_id)
        if not deleted:
            return api_error("notes_delete", "Note not found", status_code=404, deleted=False)
        return {"ok": True, "deleted": True}
    except Exception as exc:
        return api_error("notes_delete", exc)


# ---------------------------------------------------------------------------
# Agentic background tasks (Phase A: typed plans, no autonomous planner).
# ---------------------------------------------------------------------------


AGENT_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm", ".aac", ".mp4"}
AGENT_ARTIFACT_MAX_BYTES = 250 * 1024 * 1024


def _agent_client(request: Request) -> dict[str, Any]:
    return getattr(request.state, "mobile_client", {}) or {
        "id": "local", "name": "Local User", "platform": "desktop"
    }


def _agent_is_owner(request: Request) -> bool:
    return str(_agent_client(request).get("id") or "") in {"owner", "local"}


def _agent_authorized_task(request: Request, task_id: str) -> dict[str, Any]:
    task = get_agent_store().get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Background task not found.")
    client_id = str(_agent_client(request).get("id") or "local")
    if not _agent_is_owner(request) and task["owner_id"] != client_id:
        raise HTTPException(status_code=403, detail="This task belongs to another device.")
    return task


@api.get("/agent/tools", tags=["Agent Tasks"])
def agent_tools():
    return {
        "ok": True,
        "phase": "B",
        "planner_enabled": True,
        "planner": planner_status(),
        "tools": tool_catalog(),
        "permissions": {
            "automatic": ["read_only", "local_processing"],
            "approval_required": ["local_write"],
            "disabled": ["destructive", "external"],
        },
    }


@api.get("/agent/planner/status", tags=["Agent Tasks"])
def agent_planner_status():
    return {"ok": True, "planner": planner_status()}


@api.post("/agent/plan", tags=["Agent Tasks"])
async def agent_plan_task(payload: Dict[str, Any]):
    unknown = set(payload) - {"request"}
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown planner fields: {', '.join(sorted(unknown))}")
    try:
        return await run_in_threadpool(plan_task, str(payload.get("request") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@api.post("/agent/artifacts/audio", tags=["Agent Tasks"])
def agent_upload_audio(request: Request, file: UploadFile = File(...)):
    suffix = Path(file.filename or "audio.bin").suffix.lower()
    if suffix not in AGENT_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported audio file type.")
    store = get_agent_store()
    destination = store.artifacts_dir / f"{uuid.uuid4().hex}{suffix}"
    try:
        written = 0
        with open(destination, "wb") as target:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > AGENT_ARTIFACT_MAX_BYTES:
                    raise HTTPException(status_code=413, detail="Audio uploads are limited to 250 MB.")
                target.write(chunk)
        if written <= 0:
            raise HTTPException(status_code=422, detail="The uploaded audio file is empty.")
        client = _agent_client(request)
        artifact = store.create_artifact(
            str(client.get("id") or "local"),
            destination,
            file.filename or destination.name,
            file.content_type or "application/octet-stream",
        )
        return {"ok": True, "artifact": artifact}
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    except Exception as exc:
        destination.unlink(missing_ok=True)
        return api_error("agent_artifact", exc)


@api.post("/agent/tasks", tags=["Agent Tasks"])
def agent_create_task(request: Request, payload: Dict[str, Any]):
    unknown = set(payload) - {"request", "steps", "time_budget_seconds", "max_retries"}
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown task fields: {', '.join(sorted(unknown))}")
    try:
        client = _agent_client(request)
        task = get_agent_store().create_task(
            owner_id=str(client.get("id") or "local"),
            request=str(payload.get("request") or ""),
            steps=payload.get("steps") or [],
            time_budget_seconds=int(payload.get("time_budget_seconds", 600)),
            max_retries=int(payload.get("max_retries", 2)),
        )
        get_agent_engine().notify()
        return {"ok": True, "task": task}
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@api.get("/agent/tasks", tags=["Agent Tasks"])
def agent_list_tasks(request: Request, limit: int = 50, details: bool = False):
    client_id = str(_agent_client(request).get("id") or "local")
    owner_filter = None if _agent_is_owner(request) else client_id
    store = get_agent_store()
    tasks = store.list_tasks(owner_filter, limit)
    if details:
        tasks = [store.get_task(task["id"], include_steps=True) or task for task in tasks]
    return {"ok": True, "tasks": tasks}


@api.get("/agent/tasks/{task_id}", tags=["Agent Tasks"])
def agent_get_task(request: Request, task_id: str):
    return {"ok": True, "task": _agent_authorized_task(request, task_id)}


@api.get("/agent/tasks/{task_id}/events", tags=["Agent Tasks"])
def agent_task_events(request: Request, task_id: str, after_id: int = 0, limit: int = 200):
    _agent_authorized_task(request, task_id)
    return {
        "ok": True,
        "events": get_agent_store().list_events(task_id, after_id=after_id, limit=limit),
    }


@api.post("/agent/tasks/{task_id}/approve", tags=["Agent Tasks"])
def agent_approve_task(request: Request, task_id: str, payload: Dict[str, Any]):
    task = _agent_authorized_task(request, task_id)
    if not _agent_is_owner(request):
        raise HTTPException(status_code=403, detail="Only the PC owner can approve local writes.")
    permissions = payload.get("permissions")
    if not isinstance(permissions, list):
        raise HTTPException(status_code=422, detail="permissions must be a list.")
    try:
        updated = get_agent_store().approve(task["id"], {str(value) for value in permissions})
        get_agent_engine().notify()
        return {"ok": True, "task": updated}
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@api.post("/agent/tasks/{task_id}/cancel", tags=["Agent Tasks"])
def agent_cancel_task(request: Request, task_id: str):
    task = _agent_authorized_task(request, task_id)
    return {"ok": True, "task": get_agent_store().request_cancel(task["id"])}


@api.post("/agent/tasks/{task_id}/pause", tags=["Agent Tasks"])
def agent_pause_task(request: Request, task_id: str):
    task = _agent_authorized_task(request, task_id)
    try:
        return {"ok": True, "task": get_agent_store().request_pause(task["id"])}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@api.post("/agent/tasks/{task_id}/resume", tags=["Agent Tasks"])
def agent_resume_task(request: Request, task_id: str):
    task = _agent_authorized_task(request, task_id)
    try:
        updated = get_agent_store().resume(task["id"])
        get_agent_engine().notify()
        return {"ok": True, "task": updated}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@api.post("/agent/tasks/{task_id}/retry", tags=["Agent Tasks"])
def agent_retry_task(request: Request, task_id: str):
    task = _agent_authorized_task(request, task_id)
    try:
        updated = get_agent_store().retry(task["id"])
        get_agent_engine().notify()
        return {"ok": True, "task": updated}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# OCR endpoints.
# ---------------------------------------------------------------------------


@api.post("/ocr/extract", tags=["OCR"])
def ocr_extract(file: UploadFile = File(...), lang: str = Form("en"), ai_cleanup: bool = Form(False)):
    with temp_files() as tmp:
        try:
            uploaded_path = save_upload(file)
            tmp.append(uploaded_path)
            result = extract_text_from_image(uploaded_path, lang, ai_cleanup=ai_cleanup)
            if isinstance(result, dict):
                result = attach_lfie_result(result, workflow="ocr", output_text=result.get("text", ""))
            return result
        except Exception as exc:
            return api_error("ocr", exc, text="", language=lang)


@api.post("/image/translate", tags=["OCR"])
def image_translate(file: UploadFile = File(...), source_lang: str = Form("en"), target_lang: str = Form("de")):
    with temp_files() as tmp:
        try:
            uploaded_path = save_upload(file)
            tmp.append(uploaded_path)
            ocr_result = extract_text_from_image(uploaded_path, source_lang)
            if not ocr_result.get("ok"):
                return api_error("ocr", ocr_result.get("error", "OCR failed."), status_code=422)
            extracted_text = ocr_result.get("text", "")
            translation_result = translate_with_views(extracted_text, source_lang, target_lang)
            if not translation_result.get("ok"):
                return api_error("translation", translation_result.get("error", "Translation failed."), extracted_text=extracted_text, status_code=422)
            payload = {"ok": True, "extracted_text": extracted_text, "translation": translation_result}
            payload["ocr_lfie"] = workflow_audit_report("ocr", outputs={"text": extracted_text})
            payload["translation_lfie"] = workflow_audit_report("translation", inputs={"text": extracted_text}, outputs={"text": translation_result.get("translated_text", "") if isinstance(translation_result, dict) else ""})
            return payload
        except Exception as exc:
            return api_error("image_translate", exc)


# ---------------------------------------------------------------------------
# Reader endpoints.
# ---------------------------------------------------------------------------


@api.post("/reader/import", tags=["Reader"])
def reader_import(file: UploadFile = File(...), lang: str = Form("auto")):
    with temp_files() as tmp:
        try:
            uploaded_path = save_upload(file)
            tmp.append(uploaded_path)
            result = extract_text_from_file(uploaded_path, lang)
            if not result.get("ok"):
                return result
            raw_text = result.get("text", "")
            text = normalize_document_text(raw_text)
            detected_language = detect_text_language(text)
            analysis = analyze_document(text)
            lfie = analyze_text(text, workflow="reader")
            return {
                "ok": True,
                "file_type": result.get("file_type"),
                "method": result.get("method"),
                "detected_language": detected_language,
                "analysis": analysis,
                "lfie": lfie,
                "lfie_audit": workflow_audit_report("reader", inputs={"text": text}),
                "text": text,
            }
        except Exception as exc:
            return api_error("reader_import", exc, text="")


@api.post("/reader/analyze", tags=["Reader"])
def reader_analyze(text: str = Form(...)):
    try:
        analysis = analyze_document(text)
        if isinstance(analysis, dict):
            analysis["lfie"] = workflow_audit_report("reader", inputs={"text": text})
        return analysis
    except Exception as exc:
        return api_error("reader_analyze", exc)


@api.post("/reader/export", tags=["Reader"])
def reader_export(text: str = Form(...), output_format: str = Form("txt"), title: str = Form("LinguaFusion Reader Export")):
    try:
        preflight = export_quality_preflight(text, workflow="reader", output_format=output_format, strict=True)
        if not preflight.get("ok"):
            return api_error("reader_export_quality_gate", "LFIE quality gate blocked export for review.", preflight=preflight, status_code=422)
        exported_path = export_reader_document(text, output_format, title=title)
        suffix = "." + output_format.lower().strip().lstrip(".")
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if suffix == ".docx" else ("application/pdf" if suffix == ".pdf" else "text/plain")
        return FileResponse(
            exported_path,
            media_type=media_type,
            filename=f"reader_export{suffix}",
            background=BackgroundTask(_unlink_quietly, exported_path),
        )
    except Exception as exc:
        return api_error("reader_export", exc)


@api.post("/reader/speak", tags=["Reader"])
def reader_speak(text: str = Form(...), lang: str = Form("en"), speed: float = Form(1.0)):
    try:
        speech_path = speak_to_file(text, lang, f"reader_{uuid.uuid4().hex}.wav", speed=speed)
        return FileResponse(
            speech_path,
            media_type="audio/wav",
            filename="reader_output.wav",
            background=BackgroundTask(_unlink_quietly, speech_path),
        )
    except Exception as exc:
        return api_error("reader_speak", exc)


@api.post("/reader/translate", tags=["Reader"])
def reader_translate(text: str = Form(...), target_lang: str = Form("de"), source_lang: str = Form("auto")):
    try:
        resolved_source = source_lang
        if source_lang == "auto":
            detected = detect_text_language(text)
            if not detected.get("ok"):
                return api_error("language_detection", detected.get("error", "Language detection failed."), status_code=422)
            if detected.get("is_mixed"):
                resolved_source = "auto"
            else:
                resolved_source = detected.get("language")
                if resolved_source not in {"en", "de", "es", "hi", "ar", "or"}:
                    resolved_source = "en"
        translation = translate_with_views(text, resolved_source, target_lang)
        payload = {"ok": translation.get("ok"), "source_lang": resolved_source, "target_lang": target_lang, "translation": translation}
        payload = attach_lfie_result(payload, workflow="translation", input_text=text, output_text=translation.get("translated_text", "") if isinstance(translation, dict) else "")
        return payload
    except Exception as exc:
        return api_error("reader_translate", exc)


# ---------------------------------------------------------------------------
# Language endpoints.
# ---------------------------------------------------------------------------


@api.post("/language/detect", tags=["Language"])
def language_detect(text: str = Form(...)):
    try:
        return detect_text_language(text)
    except Exception as exc:
        return api_error("language_detection", exc)


# ---------------------------------------------------------------------------
# Document Import / Export & Subtitle Endpoints.
# ---------------------------------------------------------------------------


@api.post("/document/import", tags=["Document"])
def document_import(file: UploadFile = File(...)):
    try:
        temp_path = save_upload(file)
        text = extract_doc_text(temp_path)
        try:
            os.remove(temp_path)
        except Exception:
            pass
        return {"ok": True, "filename": file.filename, "text": text}
    except Exception as exc:
        return api_error("document_import", exc)


@api.post("/document/export", tags=["Document"])
def document_export(text: str = Form(...), format_type: str = Form("txt"), title: str = Form("LinguaFusion Export")):
    try:
        file_bytes = export_document(text, format_type=format_type, title=title)
        fmt = format_type.lower().strip(".")
        if fmt == "docx":
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            filename = f"export_{uuid.uuid4().hex[:8]}.docx"
        elif fmt == "pdf":
            media_type = "application/pdf"
            filename = f"export_{uuid.uuid4().hex[:8]}.pdf"
        else:
            media_type = "text/plain"
            filename = f"export_{uuid.uuid4().hex[:8]}.txt"
        return Response(content=file_bytes, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    except Exception as exc:
        return api_error("document_export", exc)


@api.post("/speech/export_subtitles", tags=["Speech"])
def speech_export_subtitles(segments_json: str = Form(...), format_type: str = Form("srt")):
    try:
        segments = json.loads(segments_json)
        subtitle_content = export_subtitles(segments, format_type=format_type)
        fmt = format_type.lower().strip(".")
        media_type = "text/vtt" if fmt == "vtt" else "application/x-subrip"
        filename = f"transcript_{uuid.uuid4().hex[:8]}.{fmt}"
        return Response(content=subtitle_content.encode("utf-8"), media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    except Exception as exc:
        return api_error("speech_export_subtitles", exc)


@api.post("/document/batch_translate", tags=["Document"])
def document_batch_translate(
    files: List[UploadFile] = File(...),
    source_lang: str = Form("auto"),
    target_lang: str = Form("de"),
    export_format: str = Form("same"),
):
    try:
        def do_translate(text: str, src: str, tgt: str) -> str:
            res = translate_with_views(text, source_lang=src, target_lang=tgt)
            if isinstance(res, dict):
                return str(res.get("translated_text", text))
            return str(res)

        files_data = read_batch_uploads(files)

        zip_bytes = batch_process_documents(files_data, source_lang, target_lang, do_translate, export_format=export_format)
        filename = f"translated_documents_{uuid.uuid4().hex[:8]}.zip"
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        return api_error("document_batch_translate", exc)


@api.post("/ocr/batch_extract", tags=["OCR"])
def ocr_batch_extract(
    files: List[UploadFile] = File(...),
    ocr_lang: str = Form("auto"),
    target_lang: str = Form("none"),
    export_format: str = Form("docx"),
):
    try:
        def do_ocr(path_str: str, lang: str) -> str:
            from backend.services.ocr_service import extract_text_from_image
            res = extract_text_from_image(path_str, lang=lang, ai_cleanup=False)
            if isinstance(res, dict):
                return str(res.get("text", ""))
            return str(res)

        def do_translate(text: str, src: str, tgt: str) -> str:
            res = translate_with_views(text, source_lang=src, target_lang=tgt)
            if isinstance(res, dict):
                return str(res.get("translated_text", text))
            return str(res)

        files_data = read_batch_uploads(files)

        zip_bytes = batch_process_ocr(files_data, ocr_lang, target_lang, do_ocr, do_translate, export_format=export_format)
        filename = f"batch_ocr_{uuid.uuid4().hex[:8]}.zip"
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        return api_error("ocr_batch_extract", exc)


@app.on_event("startup")
def auto_start_tunnel_on_boot():
    if os.environ.get("LF_AUTO_TUNNEL", "").strip().lower() not in {"1", "true", "yes"}:
        return
    try:
        from backend.services.tunnel_service import start_tunnel
        def _boot_tunnel():
            time.sleep(1)
            start_tunnel(port=8000)
        t = threading.Thread(target=_boot_tunnel, daemon=True)
        t.start()
    except Exception:
        pass


@app.on_event("shutdown")
def stop_managed_tunnel_on_shutdown():
    try:
        from backend.services.tunnel_service import get_tunnel_status, stop_tunnel
        status = get_tunnel_status()
        if status.get("managed") and status.get("active"):
            stop_tunnel()
    except Exception:
        pass


@app.on_event("startup")
def auto_preload_models():
    if os.environ.get("LF_PRELOAD_MODELS", "1").strip() != "1":
        return
    def _preload():
        time.sleep(3)
        print("Pre-warming AI models...")
        def _warm_whisper():
            try:
                from backend.services.whisper_service import _load_model
                _load_model()
            except Exception:
                pass
        def _warm_nllb():
            try:
                from backend.services.nllb_translation_service import _load
                _load()
            except Exception:
                pass
        threading.Thread(target=_warm_whisper, daemon=True).start()
        threading.Thread(target=_warm_nllb, daemon=True).start()
    threading.Thread(target=_preload, daemon=True).start()


app.include_router(api)


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("backend.server:app", host=host, port=port, reload=False)
