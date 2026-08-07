"""RapidOCR-based text extraction for photos and screenshots.

Tesseract (ocr_service.py) is fast and works well on clean, flat document
scans -- which is what the Reader/PDF path renders via PyMuPDF. But for
photos taken at an angle, screenshots with mixed fonts/backgrounds, or
generally messier real-world images, RapidOCR (built on onnxruntime, which
is already installed for faster-whisper's dependencies) tends to do
noticeably better.

This module is intentionally separate from ocr_service.py and only used for
plain image files (.jpg/.png/etc, not PDFs) -- see extract_text_from_image()
in ocr_service.py for the routing logic and automatic fallback to Tesseract
if RapidOCR isn't installed or fails.

Setup (one-time):
    pip install rapidocr-onnxruntime

No model download step needed -- the package ships its own detection and
recognition models and downloads them automatically on first use (~15MB).
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, Optional

_engine = None
_engine_lock = threading.Lock()
_import_error: Optional[str] = None


def is_available() -> bool:
    global _import_error
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except Exception as exc:
        _import_error = str(exc)
        return False


def _get_engine():
    global _engine
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is not None:
            return _engine
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
        return _engine


def extract_text_rapidocr(image_path: Path) -> Dict[str, Any]:
    """Run RapidOCR on an image file. Returns the same shape ocr_service's
    Tesseract path returns, so callers can use either interchangeably."""
    try:
        engine = _get_engine()
        result, _elapse = engine(str(image_path))
    except Exception as exc:
        return {"ok": False, "text": "", "average_confidence": None, "lines": [], "error": str(exc)}

    if not result:
        return {"ok": False, "text": "", "average_confidence": None, "lines": [], "error": "RapidOCR found no text."}

    lines = []
    scores = []
    for _box, text, score in result:
        text = (text or "").strip()
        if not text:
            continue
        lines.append(text)
        try:
            scores.append(float(score))
        except Exception:
            pass

    full_text = "\n".join(lines).strip()
    avg_confidence = round(sum(scores) / len(scores) * 100, 1) if scores else None  # RapidOCR scores are 0-1; match Tesseract's 0-100 scale
    return {
        "ok": bool(full_text),
        "text": full_text,
        "average_confidence": avg_confidence,
        "lines": lines[:200],
        "error": None if full_text else "RapidOCR found no readable text.",
    }
