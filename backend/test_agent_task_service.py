from __future__ import annotations

import time
from pathlib import Path

import pytest

from backend.services import notes_service
from backend.services.agent_task_service import (
    AgentTaskEngine,
    AgentTaskStore,
    CreateNoteInput,
    DetectLanguageInput,
    ToolDefinition,
    TranslateTextInput,
)


def _wait_for(store: AgentTaskStore, task_id: str, states: set[str], timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = store.get_task(task_id)
        if task and task["state"] in states:
            return task
        time.sleep(0.02)
    raise AssertionError(f"Task {task_id} did not reach {states}: {store.get_task(task_id)}")


@pytest.fixture
def store(tmp_path):
    return AgentTaskStore(tmp_path / "tasks.db", tmp_path / "artifacts")


def test_plan_validation_rejects_unknown_tools_and_forward_references(store):
    with pytest.raises(ValueError, match="Unknown or disabled tool"):
        store.create_task("local", "Unsafe plan", [{"tool": "shell", "input": {}}])

    with pytest.raises(ValueError, match="earlier step"):
        store.create_task(
            "local",
            "Invalid dependency",
            [
                {
                    "tool": "translate_text",
                    "input": {"text": "$step.0.text", "source_lang": "en", "target_lang": "de"},
                }
            ],
        )


def test_approval_reference_execution_and_audit(store):
    calls = []

    def translate(values, context):
        calls.append(("translate", values["text"]))
        return {"ok": True, "translated_text": "Hallo Welt"}

    def note(values, context):
        calls.append(("note", values["content"], context.idempotency_key))
        return {"ok": True, "note_id": 42}

    tools = {
        "translate_text": ToolDefinition(
            "translate_text", "local_processing", TranslateTextInput, translate, "translated_text"
        ),
        "create_note": ToolDefinition(
            "create_note", "local_write", CreateNoteInput, note
        ),
    }
    task = store.create_task(
        "friend-1",
        "Translate and save this",
        [
            {
                "tool": "translate_text",
                "input": {"text": "Hello world", "source_lang": "en", "target_lang": "de"},
            },
            {
                "tool": "create_note",
                "input": {"title": "Translation", "content": "$step.0.translated_text", "language": "de"},
            },
        ],
        tools=tools,
    )
    assert task["state"] == "awaiting_approval"
    assert "local_write" in task["required_permissions"]

    approved = store.approve(task["id"], {"local_write"})
    assert approved["state"] == "queued"
    engine = AgentTaskEngine(store, tools, poll_interval=0.02)
    try:
        engine.start()
        engine.notify()
        completed = _wait_for(store, task["id"], {"completed"})
    finally:
        engine.stop()

    assert completed["progress"] == 100
    assert completed["result"]["note_id"] == 42
    assert calls[0] == ("translate", "Hello world")
    assert calls[1][0:2] == ("note", "Hallo Welt")
    events = store.list_events(task["id"])
    assert events[0]["event"] == "task_created"
    assert events[-1]["event"] == "task_completed"


def test_pause_resume_and_cancel_queued_tasks(store):
    tools = {
        "detect_language": ToolDefinition(
            "detect_language",
            "read_only",
            DetectLanguageInput,
            lambda values, context: {"ok": True, "language": "en"},
            "language",
        )
    }
    task = store.create_task(
        "local",
        "Detect language",
        [{"tool": "detect_language", "input": {"text": "Hello"}}],
        tools=tools,
    )
    assert store.request_pause(task["id"])["state"] == "paused"
    assert store.resume(task["id"])["state"] == "queued"
    assert store.request_cancel(task["id"])["state"] == "cancelled"
    assert store.get_task(task["id"])["steps"][0]["state"] == "cancelled"


def test_failed_task_can_retry_with_budget(store):
    attempts = {"count": 0}

    def flaky(values, context):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary failure")
        return {"ok": True, "language": "en"}

    tools = {
        "detect_language": ToolDefinition(
            "detect_language", "read_only", DetectLanguageInput, flaky, "language"
        )
    }
    task = store.create_task(
        "local",
        "Retry language detection",
        [{"tool": "detect_language", "input": {"text": "Hello"}}],
        max_retries=1,
        tools=tools,
    )
    engine = AgentTaskEngine(store, tools, poll_interval=0.02)
    try:
        engine.start()
        failed = _wait_for(store, task["id"], {"failed"})
        assert "temporary failure" in failed["error"]
        store.retry(task["id"])
        engine.notify()
        completed = _wait_for(store, task["id"], {"completed"})
    finally:
        engine.stop()
    assert completed["retry_count"] == 1
    with pytest.raises(ValueError, match="Only failed or cancelled"):
        store.retry(task["id"])


def test_running_tasks_recover_after_restart(store):
    task = store.create_task(
        "local",
        "Recover me",
        [{"tool": "detect_language", "input": {"text": "Hello"}}],
    )
    with store.connect() as conn:
        conn.execute("UPDATE agent_tasks SET state='running' WHERE id=?", (task["id"],))
        conn.execute("UPDATE agent_steps SET state='running' WHERE task_id=?", (task["id"],))
    store.recover_interrupted()
    recovered = store.get_task(task["id"])
    assert recovered["state"] == "queued"
    assert recovered["steps"][0]["state"] == "queued"
    assert any(event["event"] == "task_recovered" for event in store.list_events(task["id"]))


def test_artifacts_are_scoped_to_the_uploading_device(store):
    audio = store.artifacts_dir / "sample.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 100)
    artifact = store.create_artifact("friend-a", audio, "sample.wav", "audio/wav")
    assert store.get_artifact(artifact["id"], "friend-a") is not None
    assert store.get_artifact(artifact["id"], "friend-b") is None
    outside = store.db_path.parent / "outside.wav"
    outside.write_bytes(b"RIFF")
    with pytest.raises(ValueError, match="managed artifact directory"):
        store.create_artifact("friend-a", outside, "outside.wav", "audio/wav")


def test_note_creation_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(notes_service, "DB_PATH", tmp_path / "notes.db")
    notes_service.init_notes_db()
    first = notes_service.create_note("Agent note", "Only once", "en", "stable-key")
    second = notes_service.create_note("Agent note", "Only once", "en", "stable-key")
    assert first["id"] == second["id"]
    assert len(notes_service.list_notes()) == 1
