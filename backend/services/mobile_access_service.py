"""Persistent per-device access control for remote LinguaFusion clients."""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from backend.config.paths import STORAGE_DIR


ACCESS_DB = Path(
    os.environ.get("LINGUAFUSION_ACCESS_DB", str(STORAGE_DIR / "mobile_access.db"))
)
_LOCK = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _token_hash(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _connect() -> sqlite3.Connection:
    ACCESS_DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(ACCESS_DB), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def initialize_registry() -> None:
    with _LOCK, _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS mobile_clients (
                id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                platform TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                last_seen TEXT,
                last_seen_epoch REAL,
                last_ip TEXT,
                user_agent TEXT
            );
            CREATE TABLE IF NOT EXISTS pairing_codes (
                id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL UNIQUE,
                label TEXT NOT NULL,
                public_url TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at REAL NOT NULL,
                used_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_mobile_clients_token
                ON mobile_clients(token_hash);
            CREATE INDEX IF NOT EXISTS idx_pairing_codes_token
                ON pairing_codes(token_hash);
            """
        )


def _clean_name(value: str, fallback: str, limit: int = 80) -> str:
    cleaned = " ".join((value or "").strip().split())
    return (cleaned or fallback)[:limit]


def _normalize_public_url(value: str) -> str:
    url = (value or "").strip().rstrip("/")
    if not (url.startswith("https://") or url.startswith("http://")):
        raise ValueError("Enter a complete http:// or https:// public address.")
    if url.startswith("http://"):
        host = url[7:].split("/", 1)[0].split(":", 1)[0].lower()
        if host not in {"localhost", "127.0.0.1", "::1"} and not (
            host.startswith("10.") or host.startswith("192.168.") or host.startswith("172.")
        ):
            raise ValueError("Internet pairing requires an HTTPS public address.")
    return url


def create_pairing(public_url: str, label: str = "Friend's device", expires_minutes: int = 15) -> dict[str, Any]:
    initialize_registry()
    base = _normalize_public_url(public_url)
    minutes = max(2, min(int(expires_minutes), 60))
    raw_token = secrets.token_urlsafe(32)
    pairing_id = uuid.uuid4().hex
    expires_at = time.time() + minutes * 60
    created_at = _now_iso()
    with _LOCK, _connect() as connection:
        connection.execute("DELETE FROM pairing_codes WHERE expires_at < ? OR used_at IS NOT NULL", (time.time() - 86400,))
        connection.execute(
            "INSERT INTO pairing_codes(id, token_hash, label, public_url, created_at, expires_at) VALUES(?,?,?,?,?,?)",
            (pairing_id, _token_hash(raw_token), _clean_name(label, "Friend's device"), base, created_at, expires_at),
        )
    encoded_server = quote(base, safe="")
    encoded_token = quote(raw_token, safe="")
    return {
        "id": pairing_id,
        "token": raw_token,
        "label": _clean_name(label, "Friend's device"),
        "public_url": base,
        "expires_at": datetime.fromtimestamp(expires_at, timezone.utc).isoformat(timespec="seconds"),
        "app_url": f"linguafusion://pair?server={encoded_server}&token={encoded_token}",
        # The fragment is never sent to the web server or tunnel access logs.
        "web_url": f"{base}/mobile/#pair={encoded_token}",
    }


def register_client(
    device_name: str,
    platform: str,
    remote_ip: str = "",
    user_agent: str = "",
) -> tuple[str, dict[str, Any]]:
    initialize_registry()
    raw_key = secrets.token_urlsafe(32)
    client_id = uuid.uuid4().hex
    now = _now_iso()
    name = _clean_name(device_name, "Unnamed phone")
    platform_name = _clean_name(platform, "unknown", 32).lower()
    with _LOCK, _connect() as connection:
        connection.execute(
            """INSERT INTO mobile_clients
               (id, token_hash, name, platform, enabled, created_at, last_seen, last_seen_epoch, last_ip, user_agent)
               VALUES(?,?,?,?,1,?,?,?,?,?)""",
            (client_id, _token_hash(raw_key), name, platform_name, now, now, time.time(), remote_ip[:80], user_agent[:240]),
        )
    return raw_key, {
        "id": client_id,
        "name": name,
        "platform": platform_name,
        "enabled": True,
        "created_at": now,
    }


def claim_pairing(
    token: str,
    device_name: str,
    platform: str,
    remote_ip: str = "",
    user_agent: str = "",
) -> tuple[str, dict[str, Any]]:
    initialize_registry()
    supplied_hash = _token_hash(token)
    raw_key = secrets.token_urlsafe(32)
    client_id = uuid.uuid4().hex
    now = _now_iso()
    name = _clean_name(device_name, "Unnamed phone")
    platform_name = _clean_name(platform, "unknown", 32).lower()
    now_epoch = time.time()
    with _LOCK, _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id, expires_at, used_at FROM pairing_codes WHERE token_hash=?",
            (supplied_hash,),
        ).fetchone()
        if row is None:
            raise PermissionError("Invalid pairing link.")
        if row["used_at"]:
            raise RuntimeError("Pairing link was already used.")
        if float(row["expires_at"]) < time.time():
            raise TimeoutError("Pairing link expired. Create a fresh QR code.")
        # Create the client and consume the invitation in one SQLite
        # transaction. A storage failure can therefore never burn a valid QR
        # code without also issuing its device credential.
        connection.execute(
            """INSERT INTO mobile_clients
               (id, token_hash, name, platform, enabled, created_at, last_seen, last_seen_epoch, last_ip, user_agent)
               VALUES(?,?,?,?,1,?,?,?,?,?)""",
            (client_id, _token_hash(raw_key), name, platform_name, now, now, now_epoch, remote_ip[:80], user_agent[:240]),
        )
        connection.execute("UPDATE pairing_codes SET used_at=? WHERE id=?", (now, row["id"]))
    return raw_key, {
        "id": client_id,
        "name": name,
        "platform": platform_name,
        "enabled": True,
        "created_at": now,
    }


def authenticate_client(token: str, remote_ip: str = "", user_agent: str = "") -> tuple[str, dict[str, Any] | None]:
    if not token:
        return "invalid", None
    initialize_registry()
    with _LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT id, name, platform, enabled, created_at, last_seen, last_seen_epoch, last_ip FROM mobile_clients WHERE token_hash=?",
            (_token_hash(token),),
        ).fetchone()
        if row is None:
            return "invalid", None
        client = dict(row)
        client["enabled"] = bool(client["enabled"])
        if not client["enabled"]:
            return "disabled", client
        now_epoch = time.time()
        connection.execute(
            "UPDATE mobile_clients SET last_seen=?, last_seen_epoch=?, last_ip=?, user_agent=? WHERE id=?",
            (_now_iso(), now_epoch, remote_ip[:80], user_agent[:240], client["id"]),
        )
        client.update(last_seen=_now_iso(), last_seen_epoch=now_epoch, last_ip=remote_ip[:80])
        return "valid", client


def list_clients() -> list[dict[str, Any]]:
    initialize_registry()
    with _LOCK, _connect() as connection:
        rows = connection.execute(
            "SELECT id, name, platform, enabled, created_at, last_seen, last_seen_epoch, last_ip FROM mobile_clients ORDER BY created_at DESC"
        ).fetchall()
    now = time.time()
    clients: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["enabled"] = bool(item["enabled"])
        item["online"] = bool(item["enabled"] and item.get("last_seen_epoch") and now - float(item["last_seen_epoch"]) < 90)
        clients.append(item)
    return clients


def set_client_enabled(client_id: str, enabled: bool) -> dict[str, Any] | None:
    initialize_registry()
    with _LOCK, _connect() as connection:
        changed = connection.execute(
            "UPDATE mobile_clients SET enabled=? WHERE id=?",
            (1 if enabled else 0, client_id),
        ).rowcount
    if not changed:
        return None
    return next((client for client in list_clients() if client["id"] == client_id), None)


def revoke_client(client_id: str) -> bool:
    initialize_registry()
    with _LOCK, _connect() as connection:
        return bool(connection.execute("DELETE FROM mobile_clients WHERE id=?", (client_id,)).rowcount)


def registry_summary() -> dict[str, int]:
    clients = list_clients()
    return {
        "total": len(clients),
        "enabled": sum(1 for client in clients if client["enabled"]),
        "online": sum(1 for client in clients if client["online"]),
    }
