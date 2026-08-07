"""Central filesystem paths for LinguaFusion.

Keep all generated/runtime files out of source modules and make Windows/VS Code
runs predictable. Large models stay outside the release ZIP under project_root/models.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _resolve_project_root() -> Path:
    env_root = os.getenv("LINGUAFUSION_PROJECT_ROOT", "").strip()
    if env_root and Path(env_root).is_dir():
        return Path(env_root)

    source_root = Path(__file__).resolve().parents[2]
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        dev_repo = exe_dir.parent.parent
        if (dev_repo / "models").is_dir() and (dev_repo / "backend").is_dir():
            return dev_repo
        if (exe_dir / "models").is_dir():
            return exe_dir
        if (exe_dir.parent / "models").is_dir():
            return exe_dir.parent
    return source_root


def _resolve_models_dir(root: Path) -> Path:
    env_models = os.getenv("LINGUAFUSION_MODELS_DIR") or os.getenv("LF_MODELS_DIR")
    if env_models and Path(env_models).is_dir():
        return Path(env_models)

    candidates = [
        root / "models",
    ]
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([
            exe_dir.parent.parent / "models",
            exe_dir / "models",
            exe_dir.parent / "models",
        ])
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return root / "models"


PROJECT_ROOT = _resolve_project_root()
BACKEND_DIR = PROJECT_ROOT / "backend"
STORAGE_DIR = BACKEND_DIR / "storage"
TEMP_DIR = PROJECT_ROOT / "temp"
MODELS_DIR = _resolve_models_dir(PROJECT_ROOT)
WHISPER_MODELS_DIR = MODELS_DIR / "whisper"
PIPER_MODELS_DIR = MODELS_DIR / "piper"
MMS_TTS_MODELS_DIR = MODELS_DIR / "mms-tts"
ODIA_ASR_MODEL_DIR = MODELS_DIR / "mms-asr-odia"
TESSDATA_DIR = MODELS_DIR / "tessdata"
WHISPER_EXE = PROJECT_ROOT / "tools" / "whispercpp" / "Release" / "whisper-cli.exe"
VERSION_FILE = PROJECT_ROOT / "VERSION"
LEGACY_STORAGE_DIR = PROJECT_ROOT / "storage"

DEFAULT_TESSERACT_EXE = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
TESSERACT_EXE = Path(os.getenv("TESSERACT_CMD", str(DEFAULT_TESSERACT_EXE)))


def ensure_runtime_dirs() -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)


def read_version(default: str = "1.0-alpha.2-foundation-complete") -> str:
    try:
        value = VERSION_FILE.read_text(encoding="utf-8").strip()
        return value or default
    except Exception:
        return default


def migrate_legacy_storage_file(filename: str) -> Path:
    """Move earlier root-level storage files into backend/storage without data loss."""
    ensure_runtime_dirs()
    target = STORAGE_DIR / filename
    legacy = LEGACY_STORAGE_DIR / filename
    if not target.exists() and legacy.exists():
        try:
            shutil.copy2(legacy, target)
        except Exception:
            pass
    return target
