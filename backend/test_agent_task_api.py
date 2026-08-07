from __future__ import annotations

import os

from fastapi.testclient import TestClient

os.environ.setdefault("LF_WHISPER_DEVICE", "cpu")
os.environ.setdefault("NLLB_DEVICE", "cpu")

from backend import server
from backend.services.agent_task_service import AgentTaskStore


class _WakeOnlyEngine:
    def __init__(self):
        self.notifications = 0

    def notify(self):
        self.notifications += 1


def test_agent_api_enforces_device_scope_and_owner_approval(monkeypatch, tmp_path):
    store = AgentTaskStore(tmp_path / "agent-api.db", tmp_path / "artifacts")
    engine = _WakeOnlyEngine()
    monkeypatch.setattr(server, "get_agent_store", lambda: store)
    monkeypatch.setattr(server, "get_agent_engine", lambda: engine)
    monkeypatch.setattr(server, "API_KEY", "owner-key")

    def authenticate(key, **kwargs):
        if key in {"friend-a-key", "friend-b-key"}:
            suffix = key.split("-")[1]
            return "valid", {"id": f"friend-{suffix}", "name": suffix, "platform": "mobile", "enabled": True}
        return "invalid", None

    monkeypatch.setattr(server, "authenticate_client", authenticate)
    owner_headers = {"X-API-Key": "owner-key"}
    friend_a = {"X-API-Key": "friend-a-key"}
    friend_b = {"X-API-Key": "friend-b-key"}

    with TestClient(server.app) as client:
        tools = client.get("/agent/tools", headers=friend_a)
        assert tools.status_code == 200
        assert {item["name"] for item in tools.json()["tools"]} == {
            "detect_language", "translate_text", "transcribe_audio", "create_note"
        }
        assert tools.json()["phase"] == "B"
        assert tools.json()["planner_enabled"] is True

        monkeypatch.setattr(server, "plan_task", lambda request: {
            "ok": True,
            "request": request,
            "can_execute": True,
            "steps": [{"tool": "translate_text", "input": {
                "text": "Hello", "source_lang": "en", "target_lang": "de"
            }}],
        })
        planned = client.post(
            "/agent/plan", headers=friend_a, json={"request": "Translate Hello to German"}
        )
        assert planned.status_code == 200
        assert planned.json()["can_execute"] is True
        assert planned.json()["request"] == "Translate Hello to German"

        created = client.post(
            "/agent/tasks",
            headers=friend_a,
            json={
                "request": "Save a private note",
                "steps": [
                    {
                        "tool": "create_note",
                        "input": {"title": "Friend note", "content": "Private", "language": "en"},
                    }
                ],
            },
        )
        assert created.status_code == 200
        task = created.json()["task"]
        assert task["owner_id"] == "friend-a"
        assert task["state"] == "awaiting_approval"
        assert engine.notifications == 1

        forbidden = client.post(
            f"/agent/tasks/{task['id']}/approve",
            headers=friend_a,
            json={"permissions": ["local_write"]},
        )
        assert forbidden.status_code == 403

        hidden = client.get(f"/agent/tasks/{task['id']}", headers=friend_b)
        assert hidden.status_code == 403
        assert client.get("/agent/tasks", headers=friend_b).json()["tasks"] == []

        approved = client.post(
            f"/agent/tasks/{task['id']}/approve",
            headers=owner_headers,
            json={"permissions": ["local_write"]},
        )
        assert approved.status_code == 200
        assert approved.json()["task"]["state"] == "queued"
        assert engine.notifications == 2
        assert any(item["id"] == task["id"] for item in client.get(
            "/agent/tasks", headers=owner_headers
        ).json()["tasks"])


def test_agent_api_rejects_unsafe_plan_and_scopes_audio_artifact(monkeypatch, tmp_path):
    store = AgentTaskStore(tmp_path / "agent-api.db", tmp_path / "artifacts")
    engine = _WakeOnlyEngine()
    monkeypatch.setattr(server, "get_agent_store", lambda: store)
    monkeypatch.setattr(server, "get_agent_engine", lambda: engine)
    monkeypatch.setattr(server, "API_KEY", "owner-key")
    headers = {"X-API-Key": "owner-key"}

    with TestClient(server.app) as client:
        unsafe = client.post(
            "/agent/tasks",
            headers=headers,
            json={"request": "Run this", "steps": [{"tool": "shell", "input": {"command": "whoami"}}]},
        )
        assert unsafe.status_code == 422
        assert "Unknown or disabled tool" in unsafe.json()["detail"]

        upload = client.post(
            "/agent/artifacts/audio",
            headers=headers,
            files={"file": ("sample.wav", b"RIFF" + b"\x00" * 256, "audio/wav")},
        )
        assert upload.status_code == 200
        artifact = upload.json()["artifact"]
        assert "path" not in artifact
        assert store.get_artifact(artifact["id"], "owner") is not None

        wrong_type = client.post(
            "/agent/artifacts/audio",
            headers=headers,
            files={"file": ("payload.exe", b"not audio", "application/octet-stream")},
        )
        assert wrong_type.status_code == 415
