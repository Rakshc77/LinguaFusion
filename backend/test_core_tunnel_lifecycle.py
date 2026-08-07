"""Regression checks for permanent and temporary Cloudflare tunnel lifecycle."""

from __future__ import annotations

from pathlib import Path


def test_permanent_public_url_uses_windows_managed_tunnel(monkeypatch):
    from backend.services import tunnel_service

    monkeypatch.setenv("LINGUAFUSION_PUBLIC_URL", "https://linguafusion.fyi/")
    monkeypatch.setattr(tunnel_service, "_TUNNEL_PROCESS", None)
    monkeypatch.setattr(tunnel_service, "_ACTIVE_TUNNEL_URL", "")
    monkeypatch.setattr(tunnel_service, "_TUNNEL_ERROR", "")

    status = tunnel_service.get_tunnel_status()
    assert status == {
        "ok": True,
        "active": True,
        "url": "https://linguafusion.fyi",
        "error": "",
        "managed": False,
        "mode": "windows-service",
    }

    stopped = tunnel_service.stop_tunnel()
    assert stopped["active"] is True
    assert stopped["managed"] is False
    assert stopped["ok"] is False
    assert "Windows service" in stopped["error"]


def test_backend_does_not_spawn_quick_tunnel_without_opt_in():
    server_source = (Path(__file__).resolve().parent / "server.py").read_text(encoding="utf-8")
    guard = 'os.environ.get("LF_AUTO_TUNNEL", "").strip().lower() not in {"1", "true", "yes"}'
    guard_position = server_source.index(guard)
    start_position = server_source.index("start_tunnel(port=8000)", guard_position)
    assert guard_position < start_position
    assert "def stop_managed_tunnel_on_shutdown():" in server_source
