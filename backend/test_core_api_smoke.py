"""Live smoke tests for the main LinguaFusion workflows.

The module is safe to include in the normal pytest suite: all tests skip when
the local backend is not running. Set ``LF_TEST_BASE_URL`` to exercise another
local instance. Test-created notes are deleted before the test returns.
"""

from __future__ import annotations

import io
import os
import time
from pathlib import Path

import pytest
import requests
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
REQUEST_TIMEOUT = 180
LOCAL_API_KEY_FILE = Path(__file__).resolve().parent / "storage" / "mobile_api_key.txt"


def _api_headers() -> dict[str, str]:
    key = os.environ.get("LF_TEST_API_KEY", "").strip()
    if not key and LOCAL_API_KEY_FILE.exists():
        key = LOCAL_API_KEY_FILE.read_text(encoding="utf-8").strip()
    return {"X-API-Key": key} if key else {}


@pytest.fixture(scope="session")
def live_api_url() -> str:
    base_url = os.environ.get("LF_TEST_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        response.raise_for_status()
    except requests.RequestException as exc:
        pytest.skip(f"LinguaFusion backend is not available at {base_url}: {exc}")
    return base_url


def _post(base_url: str, path: str, *, data=None, files=None, timeout=REQUEST_TIMEOUT):
    response = requests.post(
        f"{base_url}{path}",
        data=data,
        files=files,
        headers=_api_headers(),
        timeout=timeout,
    )
    assert response.status_code < 400, f"{path}: HTTP {response.status_code}: {response.text[:800]}"
    return response


@pytest.mark.live_api
def test_system_lfie_and_provider_status(live_api_url: str):
    root = requests.get(f"{live_api_url}/", timeout=10).json()
    assert root["ok"] is True
    assert {"translate", "reader", "speech", "ocr", "notes"}.issubset(root["modes"])

    health = requests.get(f"{live_api_url}/diagnostics", headers=_api_headers(), timeout=10).json()
    assert health["services"]["speech"] is True
    assert health["services"]["translation"] is True
    expected_device = os.environ.get("LF_TEST_EXPECT_DEVICE", "cuda").strip().lower()
    assert health["checks"]["faster_whisper"]["device"] == expected_device
    assert health["checks"]["nllb_translate"]["device"] == expected_device
    assert "whisper_cpp" not in health["checks"]

    lfie = requests.get(f"{live_api_url}/lfie/status", headers=_api_headers(), timeout=10).json()
    assert lfie["ok"] is True
    assert "translation_bridge" in lfie["components"]

    providers = requests.get(
        f"{live_api_url}/corrections/providers", headers=_api_headers(), timeout=10
    ).json()
    assert "ollama" in providers["providers"]

    config = requests.get(
        f"{live_api_url}/ai/providers/config", headers=_api_headers(), timeout=10
    ).json()
    assert config["ollama"]["num_gpu"] >= 1
    assert config["ollama"]["keep_alive"] == -1


@pytest.mark.live_api
@pytest.mark.parametrize(
    ("text", "expected_language"),
    [
        ("This offline reader detects English text correctly.", "en"),
        ("Hallo zusammen, wir testen heute die deutsche Sprache.", "de"),
        ("Hola, esta aplicación traduce documentos sin conexión.", "es"),
        ("यह एक सरल हिंदी वाक्य है।", "hi"),
    ],
)
def test_language_detection(live_api_url: str, text: str, expected_language: str):
    result = _post(live_api_url, "/language/detect", data={"text": text}).json()
    assert result["ok"] is True
    assert result["language"] == expected_language


@pytest.mark.live_api
@pytest.mark.parametrize(
    ("text", "source_lang", "target_lang"),
    [
        ("This is a clear offline translation test.", "en", "de"),
        ("Das ist ein klarer Test für die Offline-Übersetzung.", "de", "en"),
        ("Esta es una prueba clara de traducción sin conexión.", "es", "en"),
        ("यह ऑफ़लाइन अनुवाद की एक सरल परीक्षा है।", "hi", "en"),
    ],
)
def test_multilingual_translation(live_api_url: str, text: str, source_lang: str, target_lang: str):
    result = _post(
        live_api_url,
        "/translate",
        data={"text": text, "source_lang": source_lang, "target_lang": target_lang},
    ).json()
    assert result["ok"] is True
    assert result["translated_text"].strip()
    assert result["route"][0] == source_lang
    assert result["route"][-1] == target_lang
    assert "lfie" in result
    nllb = requests.get(f"{live_api_url}/diagnostics", headers=_api_headers(), timeout=10).json()["checks"]["nllb_translate"]
    assert nllb["loaded"] is True, f"NLLB silently fell back instead of loading: {nllb}"
    assert nllb["error"] is None


@pytest.mark.live_api
def test_reader_import_analyze_translate_and_export(live_api_url: str):
    text = (
        "LinguaFusion reads documents locally and preserves private content. "
        "This second sentence gives the analyzer enough clean material to inspect."
    )
    imported = _post(
        live_api_url,
        "/reader/import",
        files={"file": ("reader-smoke.txt", text.encode("utf-8"), "text/plain")},
        data={"lang": "en"},
    ).json()
    assert imported["ok"] is True
    assert "LinguaFusion" in imported["text"]
    assert imported["file_type"] == ".txt"

    analysis = _post(live_api_url, "/reader/analyze", data={"text": text}).json()
    assert analysis["ok"] is True
    assert "lfie" in analysis

    translated = _post(
        live_api_url,
        "/reader/translate",
        data={"text": text, "source_lang": "en", "target_lang": "es"},
    ).json()
    assert translated["ok"] is True
    assert translated["translation"]["translated_text"].strip()

    exported = _post(
        live_api_url,
        "/reader/export",
        data={"text": text, "output_format": "txt", "title": "Smoke Test"},
    )
    assert exported.headers["content-type"].startswith("text/plain")
    assert b"LinguaFusion" in exported.content


@pytest.mark.live_api
def test_document_translation_and_export(live_api_url: str):
    source_text = (
        "LinguaFusion translates this private document locally. "
        "The original file remains on this computer."
    )
    upload = ("translation-smoke.txt", source_text.encode("utf-8"), "text/plain")
    translated = _post(
        live_api_url,
        "/translate/document",
        files={"file": upload},
        data={"source_lang": "en", "target_lang": "de"},
    ).json()
    assert translated["ok"] is True
    assert translated["original_text"].startswith("LinguaFusion")
    assert translated["translation"]["translated_text"].strip()

    exported = _post(
        live_api_url,
        "/translate/document/export",
        files={"file": upload},
        data={"source_lang": "en", "target_lang": "de", "output_format": "txt"},
    )
    assert exported.headers["content-type"].startswith("text/plain")
    assert len(exported.content.strip()) > 20


@pytest.mark.live_api
def test_notes_create_get_list_delete(live_api_url: str):
    created = _post(
        live_api_url,
        "/notes/create",
        data={
            "title": "LinguaFusion pytest smoke note",
            "content": "This note is created and removed by the automated test.",
            "language": "en",
        },
    ).json()
    note_id = int(created["id"])
    try:
        fetched_response = requests.get(
            f"{live_api_url}/notes/{note_id}", headers=_api_headers(), timeout=10
        )
        assert fetched_response.status_code == 200
        fetched = fetched_response.json()
        assert fetched["ok"] is True
        assert fetched["note"]["title"] == created["title"]

        notes_response = requests.get(
            f"{live_api_url}/notes", headers=_api_headers(), timeout=10
        )
        notes_response.raise_for_status()
        assert any(note["id"] == note_id for note in notes_response.json())
    finally:
        deleted = requests.delete(
            f"{live_api_url}/notes/{note_id}", headers=_api_headers(), timeout=10
        )
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] is True


def _ocr_fixture_png() -> bytes:
    image = Image.new("RGB", (1400, 320), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 64)
    except OSError:
        font = ImageFont.load_default()
    draw.text((55, 70), "LinguaFusion offline OCR test 2026", fill="black", font=font)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _ocr_fixture_pdf() -> bytes:
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=(1000, 500))
    pdf.setFont("Helvetica-Bold", 34)
    pdf.drawString(60, 360, "LinguaFusion PDF OCR test 2026")
    pdf.setFont("Helvetica", 24)
    pdf.drawString(60, 300, "Private documents remain offline.")
    pdf.save()
    return output.getvalue()


@pytest.mark.live_api
def test_ocr_extract(live_api_url: str):
    result = _post(
        live_api_url,
        "/ocr/extract",
        files={"file": ("ocr-smoke.png", _ocr_fixture_png(), "image/png")},
        data={"lang": "en", "ai_cleanup": "false"},
    ).json()
    assert result["ok"] is True
    normalized = result["text"].lower()
    assert "linguafusion" in normalized
    assert "ocr" in normalized
    assert "2026" in normalized


@pytest.mark.live_api
def test_pdf_ocr_extract(live_api_url: str):
    result = _post(
        live_api_url,
        "/ocr/extract",
        files={"file": ("ocr-smoke.pdf", _ocr_fixture_pdf(), "application/pdf")},
        data={"lang": "en", "ai_cleanup": "false"},
    ).json()
    assert result["ok"] is True
    normalized = result["text"].lower()
    assert "linguafusion" in normalized
    assert "pdf ocr" in normalized
    assert "2026" in normalized


@pytest.mark.live_api
def test_image_translate(live_api_url: str):
    result = _post(
        live_api_url,
        "/image/translate",
        files={"file": ("image-translate-smoke.png", _ocr_fixture_png(), "image/png")},
        data={"source_lang": "en", "target_lang": "es"},
    ).json()
    assert result["ok"] is True
    assert "linguafusion" in result["extracted_text"].lower()
    assert result["translation"]["translated_text"].strip()


@pytest.mark.live_api
def test_tts_speak(live_api_url: str):
    response = _post(
        live_api_url,
        "/tts/speak",
        data={"text": "LinguaFusion text to speech smoke test.", "lang": "en", "speed": "1.0"},
    )
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content[:4] == b"RIFF"
    assert len(response.content) > 10_000


@pytest.mark.live_api
def test_speech_round_trip_and_translation(live_api_url: str):
    phrase = "LinguaFusion performs private speech recognition on this computer."
    spoken = _post(
        live_api_url,
        "/tts/speak",
        data={"text": phrase, "lang": "en", "speed": "0.9"},
    )
    assert spoken.content[:4] == b"RIFF"

    transcription = _post(
        live_api_url,
        "/stt/transcribe",
        files={"file": ("speech-round-trip.wav", spoken.content, "audio/wav")},
        data={"language": "en", "smart_mode": "offline"},
        timeout=300,
    ).json()
    assert transcription["ok"] is True
    transcript = transcription["text"].strip()
    assert len(transcript.split()) >= 5
    assert "linguafusion" in transcript.lower().replace(" ", "")

    translated = _post(
        live_api_url,
        "/translate",
        data={"text": transcript, "source_lang": "en", "target_lang": "de"},
    ).json()
    assert translated["ok"] is True
    assert translated["translated_text"].strip()


@pytest.mark.live_api
def test_agent_background_queue_and_events(live_api_url: str):
    response = requests.post(
        f"{live_api_url}/agent/tasks",
        headers=_api_headers(),
        json={
            "request": "Detect the language in a background task smoke test",
            "steps": [
                {
                    "tool": "detect_language",
                    "input": {"text": "This private background task runs on the local PC."},
                }
            ],
            "time_budget_seconds": 60,
        },
        timeout=20,
    )
    assert response.status_code == 200, response.text
    task_id = response.json()["task"]["id"]
    deadline = time.monotonic() + 30
    task = None
    while time.monotonic() < deadline:
        task_response = requests.get(
            f"{live_api_url}/agent/tasks/{task_id}", headers=_api_headers(), timeout=10
        )
        task_response.raise_for_status()
        task = task_response.json()["task"]
        if task["state"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.1)
    assert task is not None
    assert task["state"] == "completed", task
    assert task["result"]["language"] == "en"
    events = requests.get(
        f"{live_api_url}/agent/tasks/{task_id}/events", headers=_api_headers(), timeout=10
    ).json()["events"]
    assert events[0]["event"] == "task_created"
    assert events[-1]["event"] == "task_completed"
