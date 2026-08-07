"""Background Cloudflare Tunnel manager for LinguaFusion."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional
from urllib.request import urlretrieve

from backend.config.paths import PROJECT_ROOT

TOOLS_DIR = PROJECT_ROOT / "tools"
CLOUDFLARED_EXE = TOOLS_DIR / "cloudflared.exe"

_LOCK = threading.RLock()
_TUNNEL_PROCESS: Optional[subprocess.Popen] = None
_ACTIVE_TUNNEL_URL: str = ""
_TUNNEL_ERROR: str = ""
_MONITOR_THREAD: Optional[threading.Thread] = None


def _external_tunnel_url() -> str:
    value = os.environ.get("LINGUAFUSION_PUBLIC_URL", "").strip().rstrip("/")
    if value.startswith("https://") or value.startswith("http://"):
        return value
    return ""


def ensure_cloudflared_installed() -> Path:
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    if CLOUDFLARED_EXE.exists() and CLOUDFLARED_EXE.stat().st_size > 1000000:
        return CLOUDFLARED_EXE

    url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    try:
        urlretrieve(url, str(CLOUDFLARED_EXE))
    except Exception as exc:
        raise RuntimeError(f"Could not download cloudflared executable: {exc}") from exc

    return CLOUDFLARED_EXE


def get_tunnel_status() -> dict[str, Any]:
    global _TUNNEL_PROCESS, _ACTIVE_TUNNEL_URL, _TUNNEL_ERROR
    with _LOCK:
        running = _TUNNEL_PROCESS is not None and _TUNNEL_PROCESS.poll() is None
        if not running:
            _ACTIVE_TUNNEL_URL = ""
        external_url = _external_tunnel_url()
        if not running and external_url:
            return {
                "ok": True,
                "active": True,
                "url": external_url,
                "error": "",
                "managed": False,
                "mode": "windows-service",
            }
        return {
            "ok": True,
            "active": running,
            "url": _ACTIVE_TUNNEL_URL if running else "",
            "error": _TUNNEL_ERROR if not running else "",
            "managed": running,
            "mode": "quick" if running else "inactive",
        }


def _read_tunnel_output(proc: subprocess.Popen) -> None:
    global _ACTIVE_TUNNEL_URL, _TUNNEL_ERROR
    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
    while True:
        line = proc.stderr.readline() if proc.stderr else ""
        if not line and proc.poll() is not None:
            break
        if line:
            match = url_pattern.search(line)
            if match:
                with _LOCK:
                    _ACTIVE_TUNNEL_URL = match.group(0)


def start_tunnel(port: int = 8000, token: str = "") -> dict[str, Any]:
    global _TUNNEL_PROCESS, _ACTIVE_TUNNEL_URL, _TUNNEL_ERROR, _MONITOR_THREAD
    with _LOCK:
        status = get_tunnel_status()
        if status["active"] and status["url"]:
            return status

        try:
            exe_path = ensure_cloudflared_installed()
        except Exception as exc:
            _TUNNEL_ERROR = str(exc)
            return {"ok": False, "active": False, "url": "", "error": str(exc)}

        _ACTIVE_TUNNEL_URL = ""
        _TUNNEL_ERROR = ""

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        if token:
            cmd = [str(exe_path), "tunnel", "run", "--token", token]
        else:
            cmd = [str(exe_path), "tunnel", "--url", f"http://localhost:{port}"]

        try:
            _TUNNEL_PROCESS = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                creationflags=creation_flags,
                cwd=str(PROJECT_ROOT),
            )
        except Exception as exc:
            _TUNNEL_ERROR = str(exc)
            return {"ok": False, "active": False, "url": "", "error": str(exc)}

        _MONITOR_THREAD = threading.Thread(target=_read_tunnel_output, args=(_TUNNEL_PROCESS,), daemon=True)
        _MONITOR_THREAD.start()

    # Wait up to 12 seconds for tunnel URL generation
    for _ in range(24):
        time.sleep(0.5)
        with _LOCK:
            if _ACTIVE_TUNNEL_URL:
                return {"ok": True, "active": True, "url": _ACTIVE_TUNNEL_URL, "error": ""}
            if _TUNNEL_PROCESS and _TUNNEL_PROCESS.poll() is not None:
                break

    with _LOCK:
        if _ACTIVE_TUNNEL_URL:
            return {"ok": True, "active": True, "url": _ACTIVE_TUNNEL_URL, "error": ""}
        return {
            "ok": False,
            "active": False,
            "url": "",
            "error": "Tunnel process started, but HTTPS URL was not generated in time.",
        }


def stop_tunnel() -> dict[str, Any]:
    global _TUNNEL_PROCESS, _ACTIVE_TUNNEL_URL, _TUNNEL_ERROR
    with _LOCK:
        if _TUNNEL_PROCESS is None and _external_tunnel_url():
            status = get_tunnel_status()
            status["ok"] = False
            status["error"] = "The permanent tunnel is managed by the Cloudflared Windows service."
            return status
        if _TUNNEL_PROCESS is not None:
            try:
                _TUNNEL_PROCESS.terminate()
                _TUNNEL_PROCESS.wait(timeout=3)
            except Exception:
                try:
                    _TUNNEL_PROCESS.kill()
                except Exception:
                    pass
            _TUNNEL_PROCESS = None
        _ACTIVE_TUNNEL_URL = ""
        _TUNNEL_ERROR = ""
        return {"ok": True, "active": False, "url": "", "error": "", "managed": False, "mode": "inactive"}
