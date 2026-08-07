# LinguaFusion Agentic AI — Safe Local Architecture

**Status:** Phase A implemented August 7, 2026; Phase B is next  
**Current release:** Local-only, owner-controlled, permissioned background task assistant

## Product goal

The assistant should accept a result-oriented request such as:

> Transcribe these three recordings, translate the German parts to English,
> make a clean summary, save it as a note, and export a PDF.

It should turn that request into visible steps, run permitted work in the
background, verify each result, and let the user pause, cancel, retry, or
approve sensitive actions.

## Architecture

1. **Request interpreter** — local Ollama converts the request into a strict
   JSON task plan. The planner may suggest actions but cannot execute code.
2. **Policy gate** — validates the plan, permissions, file boundaries, step
   count, time budget, and allowed tools.
3. **Persistent task queue** — stores tasks and step results in SQLite so an
   app or backend restart does not lose progress.
4. **Tool executor** — calls only typed LinguaFusion tools backed by the
   existing services and APIs.
5. **Quality verifier** — uses LFIE and deterministic checks to reject empty,
   corrupted, truncated, or suspiciously rewritten results.
6. **Task Center UI** — desktop and phone views show the plan, live progress,
   current GPU activity, approvals, results, errors, retry, pause, and cancel.

## Initial allowlisted tools

- Detect language
- Translate text
- Import and translate a document
- Transcribe an uploaded audio file
- OCR an uploaded image or PDF
- Analyze, outline, or summarize imported text
- Create a note
- Export TXT, DOCX, PDF, or subtitles
- Produce TTS audio
- Read recent LinguaFusion task history

Every tool must use a Pydantic input schema and return structured output. The
agent must call the existing service layer rather than duplicating translation,
speech, OCR, correction, or export logic.

## Permission model

| Level | Examples | Default behavior |
| --- | --- | --- |
| Read-only | Inspect an uploaded file, detect language, plan work | Run automatically |
| Local processing | Transcribe, translate, OCR, summarize, TTS | Run automatically when enabled in Agent settings |
| Local write | Create a note or export a new file | Ask once per task, with a remembered owner preference available |
| Destructive | Delete/overwrite files, remove notes, revoke users | Always require an explicit confirmation |
| External | Share, email, upload, or publish anything | Disabled in the first release; always require explicit permission later |

The model must never receive a general-purpose shell, Python execution, raw
filesystem, database, or unrestricted HTTP tool.

## Task contract

Each task records:

- task ID, owner/client ID, request, creation time, and current state;
- a maximum of 12 validated steps;
- input and output artifact references;
- permission requirements and approval decisions;
- per-step attempts, timestamps, progress, and errors;
- cancellation flag, time budget, and retry budget;
- model name and the exact accepted JSON plan;
- an audit trail suitable for the owner Access page.

States: `draft`, `awaiting_approval`, `queued`, `running`, `paused`,
`completed`, `failed`, and `cancelled`.

## GPU scheduling

Agent tasks must use `backend/services/gpu_coordinator.py`. Only one GPU
inference operation may run at a time. Larger Odia/Arabic jobs may request an
exclusive handover, which unloads idle Ollama, Whisper, NLLB, and MMS models
before loading the requested model. The agent queue should show this as
"Waiting for GPU" rather than appearing frozen.

The known RTX 2080 Ti **-500 MHz memory-clock underclock remains mandatory**.
The agent must not automatically change GPU clocks.

## Planning and verification rules

- Ollama must return a schema-constrained JSON plan; prose is rejected.
- Unknown tools, unknown fields, unsafe paths, cyclic dependencies, and more
  than 12 steps are rejected before execution.
- The planner gets metadata and short previews, not unrestricted access to the
  user's files.
- Empty ASR/OCR text stops dependent steps; it is never sent to Ollama.
- Music mode continues to skip LLM correction.
- Existing ASR/OCR word-overlap guardrails remain in force.
- Exports use LFIE quality preflight before a task may finish successfully.
- Every step is idempotent or has an idempotency key so retries do not create
  duplicate notes or files.

## Delivery phases

### Phase A — background-task foundation

- [x] SQLite task store and worker queue
- [x] Typed tool registry (`detect_language`, `translate_text`,
  `transcribe_audio`, `create_note`)
- [x] Task lifecycle, pause/cancel/resume/retry, budgets, restart recovery,
  cross-step references, idempotent note writes, and audit log
- [x] Authenticated REST endpoints, per-device visibility, owner-only write
  approval, managed audio artifacts, and polling-friendly progress events
- [x] Deterministic tests with fake tools; no Ollama dependency in CI
- [x] Initial desktop and phone Task Center surfaces delivered early from
  Phase C so Phase A is usable without raw API calls

### Phase B — local Ollama planner

- structured plan generation using a separately configurable planner model
- validation and one safe repair attempt for malformed JSON
- plan preview and approval UI
- GPU-aware scheduling and clear waiting states

### Phase C — desktop and phone Task Center

- create task from text or voice
- attach files already selected by the user
- progress timeline, pause/cancel/retry, approvals, and result cards
- owner view of tasks submitted by permitted friends

### Phase D — advanced workflows

- reusable user-approved recipes
- scheduled local tasks
- optional external connectors, each separately enabled and permission-gated
- private retrieval over the user's chosen notes/documents

## Recommended first implementation slice

Build Phase A with three tools—`translate_text`, `transcribe_audio`, and
`create_note`—then add the planner and UI only after queue recovery,
cancellation, permissions, and duplicate-prevention tests pass. This gives the
agent a trustworthy execution core before the model is allowed to compose
larger workflows.
