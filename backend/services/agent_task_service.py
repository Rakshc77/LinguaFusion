"""Permissioned, persistent background task execution for LinguaFusion.

This module is intentionally not an autonomous planner. It accepts only
validated plans made from a small registry of typed LinguaFusion tools. Phase B
may propose these plans, but all execution remains behind this policy layer.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from backend.config.paths import STORAGE_DIR, ensure_runtime_dirs


TASK_STATES = {
    "draft", "awaiting_approval", "queued", "running", "paused",
    "completed", "failed", "cancelled",
}
STEP_STATES = {"queued", "running", "completed", "failed", "cancelled"}
PERMISSIONS = {
    "read_only", "local_processing", "local_write", "destructive", "external",
}
AUTO_PERMISSIONS = {"read_only", "local_processing"}
MAX_STEPS = 12
MAX_REQUEST_LENGTH = 6000
MAX_TIME_BUDGET_SECONDS = 3600
STEP_REFERENCE_RE = re.compile(r"^\$step\.(\d+)\.([A-Za-z_][A-Za-z0-9_.-]*)$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


class DetectLanguageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=100_000)


class TranslateTextInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=100_000)
    source_lang: str = Field(default="auto", min_length=2, max_length=8)
    target_lang: str = Field(min_length=2, max_length=8)

    @field_validator("source_lang", "target_lang")
    @classmethod
    def valid_language(cls, value: str) -> str:
        normalized = value.lower().replace("_", "-").split("-")[0]
        allowed = {"auto", "en", "de", "es", "hi", "ar", "or"}
        if normalized not in allowed:
            raise ValueError(f"Unsupported language: {value}")
        return normalized


class TranscribeAudioInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_id: str = Field(min_length=8, max_length=80)
    language: str = Field(default="auto", min_length=2, max_length=8)

    @field_validator("language")
    @classmethod
    def valid_language(cls, value: str) -> str:
        normalized = value.lower().replace("_", "-").split("-")[0]
        if normalized not in {"auto", "en", "de", "es", "hi", "ar", "or"}:
            raise ValueError(f"Unsupported language: {value}")
        return normalized


class CreateNoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=250_000)
    language: str = Field(default="en", min_length=2, max_length=8)

    @field_validator("language")
    @classmethod
    def valid_language(cls, value: str) -> str:
        normalized = value.lower().replace("_", "-").split("-")[0]
        if normalized not in {"en", "de", "es", "hi", "ar", "or"}:
            raise ValueError(f"Unsupported language: {value}")
        return normalized


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    permission: str
    input_model: type[BaseModel]
    handler: Callable[[dict[str, Any], "ToolContext"], dict[str, Any]]
    result_text_field: str | None = None


@dataclass
class ToolContext:
    task_id: str
    step_id: str
    owner_id: str
    idempotency_key: str
    store: "AgentTaskStore"


def _detect_language_tool(values: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from backend.services.language_service import detect_text_language

    return detect_text_language(values["text"])


def _translate_text_tool(values: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from backend.services.language_service import detect_text_language
    from backend.services.translation_service import translate_with_views

    source = values["source_lang"]
    if source == "auto":
        source = str(detect_text_language(values["text"]).get("language") or "en")
    result = translate_with_views(values["text"], source, values["target_lang"])
    if not result.get("ok", True):
        raise RuntimeError(str(result.get("error") or "Translation failed."))
    return result


def _transcribe_audio_tool(values: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from backend.services.whisper_service import transcribe_audio

    artifact = context.store.get_artifact(values["artifact_id"], context.owner_id)
    if not artifact:
        raise ValueError("Audio artifact is missing or is not owned by this task submitter.")
    path = Path(artifact["path"])
    if not path.exists() or not path.is_file():
        raise FileNotFoundError("The uploaded audio artifact is no longer available.")
    result = transcribe_audio(path, values["language"])
    if not result.get("ok", True):
        raise RuntimeError(str(result.get("error") or "Transcription failed."))
    return result


def _create_note_tool(values: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from backend.services.notes_service import create_note

    note = create_note(
        values["title"],
        values["content"],
        values["language"],
        idempotency_key=context.idempotency_key,
    )
    return {"ok": True, "note": note, "note_id": note["id"]}


DEFAULT_TOOLS: dict[str, ToolDefinition] = {
    "detect_language": ToolDefinition(
        "detect_language", "read_only", DetectLanguageInput, _detect_language_tool, "language"
    ),
    "translate_text": ToolDefinition(
        "translate_text", "local_processing", TranslateTextInput, _translate_text_tool, "translated_text"
    ),
    "transcribe_audio": ToolDefinition(
        "transcribe_audio", "local_processing", TranscribeAudioInput, _transcribe_audio_tool, "text"
    ),
    "create_note": ToolDefinition(
        "create_note", "local_write", CreateNoteInput, _create_note_tool, None
    ),
}


class AgentTaskStore:
    def __init__(self, db_path: Path | None = None, artifacts_dir: Path | None = None):
        ensure_runtime_dirs()
        self.db_path = Path(db_path or (STORAGE_DIR / "agent_tasks.db"))
        self.artifacts_dir = Path(artifacts_dir or (STORAGE_DIR / "agent_artifacts"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_tasks (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    request TEXT NOT NULL,
                    state TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    required_permissions_json TEXT NOT NULL,
                    approved_permissions_json TEXT NOT NULL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    pause_requested INTEGER NOT NULL DEFAULT 0,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    max_retries INTEGER NOT NULL DEFAULT 2,
                    time_budget_seconds INTEGER NOT NULL DEFAULT 600,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    error TEXT,
                    result_json TEXT
                );
                CREATE TABLE IF NOT EXISTS agent_steps (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    tool_name TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    permission TEXT NOT NULL,
                    state TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 2,
                    output_json TEXT,
                    error TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    UNIQUE(task_id, position)
                );
                CREATE TABLE IF NOT EXISTS agent_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE,
                    event TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_artifacts (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_agent_tasks_state_created
                    ON agent_tasks(state, created_at);
                CREATE INDEX IF NOT EXISTS idx_agent_tasks_owner_created
                    ON agent_tasks(owner_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_agent_steps_task_position
                    ON agent_steps(task_id, position);
                CREATE INDEX IF NOT EXISTS idx_agent_audit_task_id
                    ON agent_audit(task_id, id);
                """
            )

    def audit(self, task_id: str, event: str, details: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO agent_audit(task_id,event,details_json,created_at) VALUES(?,?,?,?)",
                (task_id, event, _json(details or {}), _now()),
            )

    def create_artifact(
        self, owner_id: str, source_path: Path, original_name: str, media_type: str
    ) -> dict[str, Any]:
        source = Path(source_path).resolve()
        root = self.artifacts_dir.resolve()
        try:
            source.relative_to(root)
        except ValueError as exc:
            raise ValueError("Agent artifacts must be stored in the managed artifact directory.") from exc
        artifact_id = uuid.uuid4().hex
        record = {
            "id": artifact_id,
            "owner_id": owner_id,
            "path": str(source),
            "original_name": original_name[:240],
            "media_type": (media_type or "application/octet-stream")[:120],
            "size_bytes": source.stat().st_size,
            "created_at": _now(),
        }
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO agent_artifacts
                (id,owner_id,path,original_name,media_type,size_bytes,created_at)
                VALUES(:id,:owner_id,:path,:original_name,:media_type,:size_bytes,:created_at)""",
                record,
            )
        return {key: value for key, value in record.items() if key != "path"}

    def get_artifact(self, artifact_id: str, owner_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM agent_artifacts WHERE id=? AND owner_id=?",
                (artifact_id, owner_id),
            ).fetchone()
        return dict(row) if row else None

    def create_task(
        self,
        owner_id: str,
        request: str,
        steps: list[dict[str, Any]],
        *,
        approved_permissions: set[str] | None = None,
        time_budget_seconds: int = 600,
        max_retries: int = 2,
        tools: dict[str, ToolDefinition] | None = None,
    ) -> dict[str, Any]:
        registry = tools or DEFAULT_TOOLS
        cleaned_request = (request or "").strip()
        if not cleaned_request:
            raise ValueError("A task request is required.")
        if len(cleaned_request) > MAX_REQUEST_LENGTH:
            raise ValueError(f"Task requests are limited to {MAX_REQUEST_LENGTH} characters.")
        if not steps or len(steps) > MAX_STEPS:
            raise ValueError(f"A task must contain between 1 and {MAX_STEPS} steps.")
        time_budget_seconds = max(10, min(int(time_budget_seconds), MAX_TIME_BUDGET_SECONDS))
        max_retries = max(0, min(int(max_retries), 5))

        normalized_steps: list[dict[str, Any]] = []
        required_permissions: set[str] = set()
        for position, raw_step in enumerate(steps):
            if not isinstance(raw_step, dict) or set(raw_step) - {"tool", "input", "max_attempts"}:
                raise ValueError(f"Step {position + 1} contains unknown fields.")
            tool_name = str(raw_step.get("tool") or "").strip()
            definition = registry.get(tool_name)
            if definition is None:
                raise ValueError(f"Unknown or disabled tool: {tool_name}")
            raw_input = raw_step.get("input")
            if not isinstance(raw_input, dict):
                raise ValueError(f"Step {position + 1} input must be an object.")
            try:
                validated = definition.input_model.model_validate(raw_input).model_dump()
            except ValidationError as exc:
                raise ValueError(f"Invalid input for {tool_name}: {exc}") from exc
            self._validate_references(validated, position)
            required_permissions.add(definition.permission)
            normalized_steps.append(
                {
                    "position": position,
                    "tool_name": tool_name,
                    "input": validated,
                    "permission": definition.permission,
                    "max_attempts": max(1, min(int(raw_step.get("max_attempts", 2)), 3)),
                }
            )

        approved = set(approved_permissions or set()) | AUTO_PERMISSIONS
        if not approved.issubset(PERMISSIONS):
            raise ValueError("Plan contains an unknown permission decision.")
        state = "queued" if required_permissions.issubset(approved) else "awaiting_approval"
        task_id = uuid.uuid4().hex
        now = _now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """INSERT INTO agent_tasks
                (id,owner_id,request,state,progress,required_permissions_json,
                 approved_permissions_json,max_retries,time_budget_seconds,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    task_id, owner_id, cleaned_request, state, 0,
                    _json(sorted(required_permissions)), _json(sorted(approved)),
                    max_retries, time_budget_seconds, now, now,
                ),
            )
            for step in normalized_steps:
                step_id = uuid.uuid4().hex
                conn.execute(
                    """INSERT INTO agent_steps
                    (id,task_id,position,tool_name,input_json,permission,state,max_attempts,idempotency_key)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        step_id, task_id, step["position"], step["tool_name"],
                        _json(step["input"]), step["permission"], "queued",
                        step["max_attempts"], f"agent:{task_id}:{step_id}",
                    ),
                )
        self.audit(task_id, "task_created", {"state": state, "steps": len(normalized_steps)})
        return self.get_task(task_id, include_steps=True) or {}

    @staticmethod
    def _validate_references(value: Any, position: int) -> None:
        if isinstance(value, str) and value.startswith("$step."):
            match = STEP_REFERENCE_RE.fullmatch(value)
            if not match:
                raise ValueError(f"Invalid step reference: {value}")
            if int(match.group(1)) >= position:
                raise ValueError("A step may reference only an earlier step.")
        elif isinstance(value, dict):
            for nested in value.values():
                AgentTaskStore._validate_references(nested, position)
        elif isinstance(value, list):
            for nested in value:
                AgentTaskStore._validate_references(nested, position)

    def _task_from_row(self, row: sqlite3.Row, include_steps: bool = False) -> dict[str, Any]:
        task = dict(row)
        task["required_permissions"] = _loads(task.pop("required_permissions_json"), [])
        task["approved_permissions"] = _loads(task.pop("approved_permissions_json"), [])
        task["result"] = _loads(task.pop("result_json"), None)
        task["cancel_requested"] = bool(task["cancel_requested"])
        task["pause_requested"] = bool(task["pause_requested"])
        if include_steps:
            task["steps"] = self.list_steps(task["id"])
        return task

    def get_task(self, task_id: str, include_steps: bool = True) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
        return self._task_from_row(row, include_steps) if row else None

    def list_tasks(self, owner_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        with self.connect() as conn:
            if owner_id:
                rows = conn.execute(
                    "SELECT * FROM agent_tasks WHERE owner_id=? ORDER BY created_at DESC LIMIT ?",
                    (owner_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM agent_tasks ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
        return [self._task_from_row(row, include_steps=False) for row in rows]

    def list_steps(self, task_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_steps WHERE task_id=? ORDER BY position", (task_id,)
            ).fetchall()
        result = []
        for row in rows:
            step = dict(row)
            step["input"] = _loads(step.pop("input_json"), {})
            step["output"] = _loads(step.pop("output_json"), None)
            result.append(step)
        return result

    def list_events(self, task_id: str, after_id: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT id,event,details_json,created_at FROM agent_audit
                WHERE task_id=? AND id>? ORDER BY id LIMIT ?""",
                (task_id, max(0, int(after_id)), max(1, min(int(limit), 500))),
            ).fetchall()
        return [
            {"id": row["id"], "event": row["event"],
             "details": _loads(row["details_json"], {}), "created_at": row["created_at"]}
            for row in rows
        ]

    def approve(self, task_id: str, permissions: set[str]) -> dict[str, Any]:
        if not permissions or not permissions.issubset(PERMISSIONS):
            raise ValueError("One or more permission decisions are invalid.")
        task = self.get_task(task_id, include_steps=False)
        if not task:
            raise KeyError("Task not found.")
        required = set(task["required_permissions"])
        if not permissions.issubset(required):
            raise ValueError("Cannot approve a permission not required by this task.")
        approved = set(task["approved_permissions"]) | permissions | AUTO_PERMISSIONS
        state = "queued" if required.issubset(approved) else "awaiting_approval"
        with self.connect() as conn:
            conn.execute(
                "UPDATE agent_tasks SET approved_permissions_json=?,state=?,updated_at=? WHERE id=?",
                (_json(sorted(approved)), state, _now(), task_id),
            )
        self.audit(task_id, "permissions_approved", {"permissions": sorted(permissions), "state": state})
        return self.get_task(task_id) or {}

    def request_cancel(self, task_id: str) -> dict[str, Any]:
        task = self.get_task(task_id, include_steps=False)
        if not task:
            raise KeyError("Task not found.")
        if task["state"] in {"completed", "failed", "cancelled"}:
            return self.get_task(task_id) or {}
        immediate = task["state"] in {"queued", "paused", "awaiting_approval", "draft"}
        with self.connect() as conn:
            conn.execute(
                """UPDATE agent_tasks SET cancel_requested=1,pause_requested=0,state=?,
                completed_at=CASE WHEN ? THEN ? ELSE completed_at END,updated_at=? WHERE id=?""",
                ("cancelled" if immediate else task["state"], immediate, _now(), _now(), task_id),
            )
            if immediate:
                conn.execute(
                    "UPDATE agent_steps SET state='cancelled' WHERE task_id=? AND state='queued'",
                    (task_id,),
                )
        self.audit(task_id, "cancel_requested", {"immediate": immediate})
        return self.get_task(task_id) or {}

    def request_pause(self, task_id: str) -> dict[str, Any]:
        task = self.get_task(task_id, include_steps=False)
        if not task:
            raise KeyError("Task not found.")
        if task["state"] not in {"queued", "running"}:
            raise ValueError("Only queued or running tasks can be paused.")
        immediate = task["state"] == "queued"
        with self.connect() as conn:
            conn.execute(
                "UPDATE agent_tasks SET pause_requested=1,state=?,updated_at=? WHERE id=?",
                ("paused" if immediate else "running", _now(), task_id),
            )
        self.audit(task_id, "pause_requested", {"immediate": immediate})
        return self.get_task(task_id) or {}

    def resume(self, task_id: str) -> dict[str, Any]:
        task = self.get_task(task_id, include_steps=False)
        if not task:
            raise KeyError("Task not found.")
        if task["state"] != "paused":
            raise ValueError("Only paused tasks can be resumed.")
        with self.connect() as conn:
            conn.execute(
                "UPDATE agent_tasks SET pause_requested=0,state='queued',updated_at=? WHERE id=?",
                (_now(), task_id),
            )
        self.audit(task_id, "task_resumed")
        return self.get_task(task_id) or {}

    def retry(self, task_id: str) -> dict[str, Any]:
        task = self.get_task(task_id, include_steps=False)
        if not task:
            raise KeyError("Task not found.")
        if task["state"] not in {"failed", "cancelled"}:
            raise ValueError("Only failed or cancelled tasks can be retried.")
        if task["retry_count"] >= task["max_retries"]:
            raise ValueError("Task retry budget is exhausted.")
        required = set(task["required_permissions"])
        approved = set(task["approved_permissions"])
        state = "queued" if required.issubset(approved) else "awaiting_approval"
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """UPDATE agent_tasks SET state=?,progress=0,cancel_requested=0,pause_requested=0,
                retry_count=retry_count+1,error=NULL,result_json=NULL,started_at=NULL,completed_at=NULL,
                updated_at=? WHERE id=?""",
                (state, _now(), task_id),
            )
            conn.execute(
                """UPDATE agent_steps SET state='queued',progress=0,error=NULL,started_at=NULL,
                completed_at=NULL WHERE task_id=? AND state!='completed'""",
                (task_id,),
            )
        self.audit(task_id, "task_retried", {"state": state})
        return self.get_task(task_id) or {}

    def recover_interrupted(self) -> None:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            task_ids = [row[0] for row in conn.execute(
                "SELECT id FROM agent_tasks WHERE state='running'"
            ).fetchall()]
            conn.execute(
                """UPDATE agent_steps SET state='queued',progress=0,error='Recovered after restart',
                started_at=NULL WHERE state='running'"""
            )
            conn.execute(
                """UPDATE agent_tasks SET state='queued',pause_requested=0,
                error='Recovered after backend restart',updated_at=? WHERE state='running'""",
                (_now(),),
            )
        for task_id in task_ids:
            self.audit(task_id, "task_recovered")

    def claim_next(self) -> str | None:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT id FROM agent_tasks WHERE state='queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                return None
            task_id = row["id"]
            updated = conn.execute(
                """UPDATE agent_tasks SET state='running',started_at=COALESCE(started_at,?),
                updated_at=? WHERE id=? AND state='queued'""",
                (_now(), _now(), task_id),
            ).rowcount
        return task_id if updated else None

    def resolve_inputs(self, task_id: str, raw_input: dict[str, Any]) -> dict[str, Any]:
        steps = self.list_steps(task_id)

        def resolve(value: Any) -> Any:
            if isinstance(value, str):
                match = STEP_REFERENCE_RE.fullmatch(value)
                if not match:
                    return value
                position = int(match.group(1))
                field_path = match.group(2).split(".")
                if position >= len(steps) or steps[position]["state"] != "completed":
                    raise ValueError(f"Referenced step {position + 1} has no completed output.")
                current: Any = steps[position]["output"]
                for field in field_path:
                    if not isinstance(current, dict) or field not in current:
                        raise ValueError(f"Referenced output field does not exist: {value}")
                    current = current[field]
                return current
            if isinstance(value, dict):
                return {key: resolve(nested) for key, nested in value.items()}
            if isinstance(value, list):
                return [resolve(nested) for nested in value]
            return value

        return resolve(raw_input)


class AgentTaskEngine:
    def __init__(
        self,
        store: AgentTaskStore,
        tools: dict[str, ToolDefinition] | None = None,
        poll_interval: float = 0.25,
    ):
        self.store = store
        self.tools = tools or DEFAULT_TOOLS
        self.poll_interval = max(0.02, poll_interval)
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.store.recover_interrupted()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="LinguaFusionAgentWorker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def notify(self) -> None:
        self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            task_id = self.store.claim_next()
            if task_id:
                self._execute_task(task_id)
                continue
            self._wake.wait(self.poll_interval)
            self._wake.clear()

    def _execute_task(self, task_id: str) -> None:
        task = self.store.get_task(task_id, include_steps=False)
        if not task:
            return
        started = time.monotonic()
        self.store.audit(task_id, "task_started")
        steps = self.store.list_steps(task_id)
        total = max(len(steps), 1)
        last_output: dict[str, Any] | None = None
        try:
            for index, step in enumerate(steps):
                current = self.store.get_task(task_id, include_steps=False)
                if not current:
                    return
                if current["cancel_requested"]:
                    self._finish_cancelled(task_id)
                    return
                if current["pause_requested"]:
                    with self.store.connect() as conn:
                        conn.execute(
                            "UPDATE agent_tasks SET state='paused',updated_at=? WHERE id=?",
                            (_now(), task_id),
                        )
                    self.store.audit(task_id, "task_paused")
                    return
                if time.monotonic() - started > current["time_budget_seconds"]:
                    raise TimeoutError("Task time budget was exceeded.")
                if step["state"] == "completed":
                    last_output = step["output"]
                    continue

                definition = self.tools.get(step["tool_name"])
                if definition is None:
                    raise RuntimeError(f"Tool was disabled after planning: {step['tool_name']}")
                resolved = self.store.resolve_inputs(task_id, step["input"])
                validated = definition.input_model.model_validate(resolved).model_dump()
                with self.store.connect() as conn:
                    conn.execute(
                        """UPDATE agent_steps SET state='running',progress=5,attempts=attempts+1,
                        started_at=?,error=NULL WHERE id=?""",
                        (_now(), step["id"]),
                    )
                self.store.audit(task_id, "step_started", {"step_id": step["id"], "tool": step["tool_name"]})
                context = ToolContext(
                    task_id=task_id,
                    step_id=step["id"],
                    owner_id=task["owner_id"],
                    idempotency_key=step["idempotency_key"],
                    store=self.store,
                )
                output = definition.handler(validated, context)
                if not isinstance(output, dict):
                    raise RuntimeError(f"Tool {step['tool_name']} returned an invalid result.")
                if definition.result_text_field:
                    value = output.get(definition.result_text_field)
                    if not isinstance(value, str) or not value.strip():
                        raise RuntimeError(
                            f"Tool {step['tool_name']} returned an empty {definition.result_text_field}."
                        )
                with self.store.connect() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute(
                        """UPDATE agent_steps SET state='completed',progress=100,output_json=?,
                        completed_at=?,error=NULL WHERE id=?""",
                        (_json(output), _now(), step["id"]),
                    )
                    progress = round(((index + 1) / total) * 100)
                    conn.execute(
                        "UPDATE agent_tasks SET progress=?,updated_at=? WHERE id=?",
                        (progress, _now(), task_id),
                    )
                last_output = output
                self.store.audit(task_id, "step_completed", {"step_id": step["id"], "tool": step["tool_name"]})

            with self.store.connect() as conn:
                conn.execute(
                    """UPDATE agent_tasks SET state='completed',progress=100,result_json=?,
                    completed_at=?,updated_at=?,error=NULL WHERE id=?""",
                    (_json(last_output or {}), _now(), _now(), task_id),
                )
            self.store.audit(task_id, "task_completed")
        except Exception as exc:
            error = str(exc)[:2000]
            with self.store.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """UPDATE agent_steps SET state='failed',error=?,completed_at=?
                    WHERE task_id=? AND state='running'""",
                    (error, _now(), task_id),
                )
                conn.execute(
                    """UPDATE agent_tasks SET state='failed',error=?,completed_at=?,updated_at=?
                    WHERE id=?""",
                    (error, _now(), _now(), task_id),
                )
            self.store.audit(task_id, "task_failed", {"error": error})

    def _finish_cancelled(self, task_id: str) -> None:
        with self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE agent_steps SET state='cancelled' WHERE task_id=? AND state IN ('queued','running')",
                (task_id,),
            )
            conn.execute(
                """UPDATE agent_tasks SET state='cancelled',completed_at=?,updated_at=?
                WHERE id=?""",
                (_now(), _now(), task_id),
            )
        self.store.audit(task_id, "task_cancelled")


def validate_task_plan_preview(
    request: str,
    steps: list[dict[str, Any]],
    *,
    time_budget_seconds: int = 600,
    max_retries: int = 2,
    tools: dict[str, ToolDefinition] | None = None,
) -> dict[str, Any]:
    """Validate a proposed plan without persisting or executing it."""
    registry = tools or DEFAULT_TOOLS
    cleaned_request = (request or "").strip()
    if not cleaned_request:
        raise ValueError("A task request is required.")
    if len(cleaned_request) > MAX_REQUEST_LENGTH:
        raise ValueError(f"Task requests are limited to {MAX_REQUEST_LENGTH} characters.")
    if not isinstance(steps, list) or not steps or len(steps) > MAX_STEPS:
        raise ValueError(f"A task must contain between 1 and {MAX_STEPS} steps.")

    normalized_steps: list[dict[str, Any]] = []
    required_permissions: set[str] = set()
    for position, raw_step in enumerate(steps):
        if not isinstance(raw_step, dict) or set(raw_step) - {"tool", "input", "max_attempts"}:
            raise ValueError(f"Step {position + 1} contains unknown fields.")
        tool_name = str(raw_step.get("tool") or "").strip()
        definition = registry.get(tool_name)
        if definition is None:
            raise ValueError(f"Unknown or disabled tool: {tool_name}")
        raw_input = raw_step.get("input")
        if not isinstance(raw_input, dict):
            raise ValueError(f"Step {position + 1} input must be an object.")
        try:
            validated_input = definition.input_model.model_validate(raw_input).model_dump()
        except ValidationError as exc:
            raise ValueError(f"Invalid input for {tool_name}: {exc}") from exc
        AgentTaskStore._validate_references(validated_input, position)
        required_permissions.add(definition.permission)
        normalized_steps.append({
            "tool": tool_name,
            "input": validated_input,
            "max_attempts": max(1, min(int(raw_step.get("max_attempts", 2)), 3)),
            "permission": definition.permission,
        })

    return {
        "request": cleaned_request,
        "steps": normalized_steps,
        "required_permissions": sorted(required_permissions),
        "automatic_permissions": sorted(required_permissions & AUTO_PERMISSIONS),
        "approval_required": sorted(required_permissions - AUTO_PERMISSIONS),
        "time_budget_seconds": max(10, min(int(time_budget_seconds), MAX_TIME_BUDGET_SECONDS)),
        "max_retries": max(0, min(int(max_retries), 5)),
    }


_STORE = AgentTaskStore()
_ENGINE = AgentTaskEngine(_STORE)


def get_agent_store() -> AgentTaskStore:
    return _STORE


def get_agent_engine() -> AgentTaskEngine:
    return _ENGINE


def start_agent_worker() -> None:
    _ENGINE.start()


def stop_agent_worker() -> None:
    _ENGINE.stop()


def tool_catalog() -> list[dict[str, Any]]:
    return [
        {
            "name": definition.name,
            "permission": definition.permission,
            "input_schema": definition.input_model.model_json_schema(),
        }
        for definition in DEFAULT_TOOLS.values()
    ]
