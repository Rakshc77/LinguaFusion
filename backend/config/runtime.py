"""Runtime diagnostics used by /health and desktop Settings."""

from __future__ import annotations

import importlib.metadata
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any

from backend.config.paths import (
    PROJECT_ROOT,
    STORAGE_DIR,
    TEMP_DIR,
    PIPER_MODELS_DIR,
    MMS_TTS_MODELS_DIR,
    ODIA_ASR_MODEL_DIR,
    TESSDATA_DIR,
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
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        completed = subprocess.run([resolved, "-version"], capture_output=True, text=True, timeout=5, creationflags=creation_flags)
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


def _nllb_status() -> Dict[str, Any]:
    """Check the preferred local translation engine without loading its model."""
    try:
        from backend.services import nllb_translation_service as nllb

        dependencies = {}
        for package in ("ctranslate2", "transformers", "sentencepiece"):
            try:
                dependencies[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                dependencies[package] = None

        model_ok = nllb.is_available()
        dependencies_ok = all(dependencies.values())
        loaded = getattr(nllb, "_translator", None) is not None and getattr(nllb, "_tokenizer", None) is not None
        return {
            "ok": model_ok and dependencies_ok,
            "engine": "nllb-200",
            "model_dir": str(nllb.MODEL_DIR),
            "model_ok": model_ok,
            "device": nllb.DEVICE_PREF,
            "gpu_required": nllb.DEVICE_PREF == "cuda",
            "compute_type": getattr(nllb, "_runtime_compute_type", None) or nllb.COMPUTE_TYPE_PREF,
            "loaded": loaded,
            "dependencies": dependencies,
            "error": None if loaded else getattr(nllb, "_load_error", None),
        }
    except Exception as exc:
        return {
            "ok": False,
            "engine": "nllb-200",
            "model_dir": None,
            "model_ok": False,
            "device": os.environ.get("NLLB_DEVICE", "auto"),
            "gpu_required": os.environ.get("NLLB_DEVICE", "auto").lower() == "cuda",
            "compute_type": os.environ.get("NLLB_COMPUTE_TYPE", "auto"),
            "loaded": False,
            "dependencies": {},
            "error": str(exc),
        }

def _faster_whisper_status() -> Dict[str, Any]:
    """Report the speech engine that the application actually uses.

    Importing or warming the model from /health would allocate several GB of
    VRAM, so this check only verifies the installed package and reports the
    live model description when speech has already loaded it.
    """
    configured_model = os.environ.get("LF_WHISPER_MODEL", "small").strip() or "small"
    configured_device = os.environ.get("LF_WHISPER_DEVICE", "cuda").strip().lower() or "cuda"
    try:
        version = importlib.metadata.version("faster-whisper")
        package_ok = True
        error = None
    except importlib.metadata.PackageNotFoundError as exc:
        version = None
        package_ok = False
        error = str(exc)

    module = sys.modules.get("backend.services.whisper_service")
    loaded_description = str(getattr(module, "_model_desc", "") or "") if module else ""
    loaded = bool(loaded_description)
    using_requested_device = not loaded or configured_device == "auto" or f"({configured_device}," in loaded_description

    return {
        "ok": package_ok and using_requested_device,
        "engine": "faster-whisper",
        "version": version,
        "model": configured_model,
        "device": configured_device,
        "gpu_required": configured_device == "cuda",
        "loaded": loaded,
        "runtime": loaded_description or None,
        "error": error,
    }


def runtime_health() -> Dict[str, Any]:
    ensure_runtime_dirs()
    piper_models = {
        lang: {
            "model": str(PIPER_MODELS_DIR / filename),
            "model_ok": (PIPER_MODELS_DIR / filename).exists(),
            "config_ok": Path(str(PIPER_MODELS_DIR / filename) + ".json").exists(),
        }
        for lang, filename in PIPER_VOICES.items()
    }
    mms_tts_models = {
        lang: {
            "model": str(MMS_TTS_MODELS_DIR / folder),
            "model_ok": (MMS_TTS_MODELS_DIR / folder / "config.json").is_file(),
            "device": os.environ.get("LF_MMS_TTS_DEVICE", "cuda"),
        }
        for lang, folder in {"ar": "ara", "or": "ory"}.items()
    }

    nllb_status = _nllb_status()
    argos_status = _argos_status()
    checks = {
        "backend": {"ok": True, "storage_dir": str(STORAGE_DIR), "temp_dir": str(TEMP_DIR)},
        "ffmpeg": _ffmpeg_status(),
        "faster_whisper": _faster_whisper_status(),
        "nllb_translate": nllb_status,
        "argos_translate": argos_status,
        "piper_models": {"ok": all(v["model_ok"] and v["config_ok"] for v in piper_models.values()), "voices": piper_models},
        "mms_tts_models": {"ok": all(v["model_ok"] for v in mms_tts_models.values()), "voices": mms_tts_models},
        "odia_asr": {
            "ok": (ODIA_ASR_MODEL_DIR / "config.json").is_file(),
            "model_dir": str(ODIA_ASR_MODEL_DIR),
            "device": os.environ.get("LF_ODIA_ASR_DEVICE", "cuda"),
        },
        "tesseract": _tool_status(TESSERACT_EXE) if TESSERACT_EXE.exists() else _tool_status(command="tesseract"),
        "tesseract_languages": {
            "ok": all((TESSDATA_DIR / f"{code}.traineddata").is_file() for code in ("eng", "deu", "spa", "hin", "ara", "ori")),
            "directory": str(TESSDATA_DIR),
            "languages": [code for code in ("eng", "deu", "spa", "hin", "ara", "ori") if (TESSDATA_DIR / f"{code}.traineddata").is_file()],
        },
    }

    service_status = {
        "speech": checks["faster_whisper"]["ok"],
        "translation": checks["nllb_translate"]["ok"] or checks["argos_translate"]["ok"],
        "tts": checks["piper_models"]["ok"],
        "arabic_odia_tts": checks["mms_tts_models"]["ok"],
        "odia_speech": checks["odia_asr"]["ok"],
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
