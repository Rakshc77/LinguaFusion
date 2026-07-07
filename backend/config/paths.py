"""Central filesystem paths for LinguaFusion.

Keep all generated/runtime files out of source modules and make Windows/VS Code
runs predictable. Large models stay outside the release ZIP under project_root/models.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
STORAGE_DIR = BACKEND_DIR / "storage"
TEMP_DIR = PROJECT_ROOT / "temp"
MODELS_DIR = PROJECT_ROOT / "models"
WHISPER_MODELS_DIR = MODELS_DIR / "whisper"
PIPER_MODELS_DIR = MODELS_DIR / "piper"
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
