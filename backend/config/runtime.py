"""Runtime diagnostics used by /health and desktop Settings."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any

from backend.config.paths import (
    PROJECT_ROOT,
    STORAGE_DIR,
    TEMP_DIR,
    WHISPER_EXE,
    WHISPER_MODELS_DIR,
    PIPER_MODELS_DIR,
    TESSERACT_EXE,
    ensure_runtime_dirs,
    read_version,
)

PIPER_VOICES = {
    "en": "en_US-lessac-medium.onnx",
    "de": "de_DE-thorsten-medium.onnx",
    "es": "es_ES-sharvard-medium.onnx",
    "hi": "hi_IN-priyamvada-medium.onnx",
}

WHISPER_MODEL_PRIORITY = [
    "ggml-medium.bin",
    "ggml-small.bin",
    "ggml-base.bin",
    "ggml-tiny.bin",
]


def _tool_status(path: Path | None = None, command: str | None = None) -> Dict[str, Any]:
    if path is not None:
        return {"ok": path.exists(), "path": str(path)}
    resolved = shutil.which(command or "")
    return {"ok": bool(resolved), "path": resolved or None}


def _ffmpeg_status() -> Dict[str, Any]:
    resolved = shutil.which("ffmpeg")
    if not resolved:
        return {"ok": False, "path": None, "version": None}
    try:
        completed = subprocess.run([resolved, "-version"], capture_output=True, text=True, timeout=5)
        first_line = (completed.stdout or completed.stderr or "").splitlines()[0] if (completed.stdout or completed.stderr) else None
    except Exception:
        first_line = None
    return {"ok": True, "path": resolved, "version": first_line}



def _argos_status() -> Dict[str, Any]:
    try:
        import argostranslate.translate
        languages = argostranslate.translate.get_installed_languages()
        codes = sorted(getattr(lang, "code", "") for lang in languages if getattr(lang, "code", ""))
        required = {"en", "de", "es", "hi"}
        return {"ok": bool(required & set(codes)), "installed_languages": codes, "error": None}
    except Exception as exc:
        return {"ok": False, "installed_languages": [], "error": str(exc)}

def _selected_whisper_model() -> Path:
    for name in WHISPER_MODEL_PRIORITY:
        candidate = WHISPER_MODELS_DIR / name
        if candidate.exists():
            return candidate
    available = sorted(WHISPER_MODELS_DIR.glob("*.bin")) if WHISPER_MODELS_DIR.exists() else []
    return available[0] if available else WHISPER_MODELS_DIR / "ggml-small.bin"


def runtime_health() -> Dict[str, Any]:
    ensure_runtime_dirs()
    whisper_model = _selected_whisper_model()
    piper_models = {
        lang: {
            "model": str(PIPER_MODELS_DIR / filename),
            "model_ok": (PIPER_MODELS_DIR / filename).exists(),
            "config_ok": Path(str(PIPER_MODELS_DIR / filename) + ".json").exists(),
        }
        for lang, filename in PIPER_VOICES.items()
    }

    checks = {
        "backend": {"ok": True, "storage_dir": str(STORAGE_DIR), "temp_dir": str(TEMP_DIR)},
        "ffmpeg": _ffmpeg_status(),
        "whisper_cpp": _tool_status(WHISPER_EXE),
        "whisper_model": {"ok": whisper_model.exists(), "path": str(whisper_model)},
        "argos_translate": _argos_status(),
        "piper_models": {"ok": all(v["model_ok"] and v["config_ok"] for v in piper_models.values()), "voices": piper_models},
        "tesseract": _tool_status(TESSERACT_EXE) if TESSERACT_EXE.exists() else _tool_status(command="tesseract"),
    }

    service_status = {
        "speech": checks["ffmpeg"]["ok"] and checks["whisper_cpp"]["ok"] and checks["whisper_model"]["ok"],
        "translation": checks["argos_translate"]["ok"],
        "tts": checks["piper_models"]["ok"],
        "ocr": checks["tesseract"]["ok"],
        "reader": True,
        "notes": True,
    }

    return {
        "ok": True,
        "app": "LinguaFusion",
        "version": read_version(),
        "mode": "local-first",
        "project_root": str(PROJECT_ROOT),
        "services": service_status,
        "checks": checks,
    }
