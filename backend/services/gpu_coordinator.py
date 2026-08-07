"""Cross-engine GPU serialization and safe VRAM handover.

The 11 GB RTX 2080 Ti cannot keep Ollama, Whisper, NLLB and the larger Odia
ASR model resident simultaneously.  All engines still *infer on the GPU*, but
large one-off MMS jobs temporarily release idle model allocations, then let the
next normal request lazily reload its own model.
"""

from __future__ import annotations

import gc
import threading
from contextlib import contextmanager


_GPU_LOCK = threading.RLock()


def _unload_ollama() -> None:
    try:
        import requests
        from backend.services.free_online_correction_service import _ollama_config

        config = _ollama_config()
        if config.get("enabled"):
            requests.post(
                f"{str(config.get('url', 'http://localhost:11434')).rstrip('/')}/api/generate",
                json={"model": config.get("model", "llama3.1:8b"), "keep_alive": 0},
                timeout=15,
            )
    except Exception:
        pass


def _release_idle_models(requester: str) -> None:
    _unload_ollama()
    if requester != "whisper":
        try:
            from backend.services.whisper_service import release_model

            release_model()
        except Exception:
            pass
    if requester != "nllb":
        try:
            from backend.services.nllb_translation_service import release_model

            release_model()
        except Exception:
            pass
    if requester != "mms_tts":
        try:
            from backend.services.mms_tts_service import release_models

            release_models()
        except Exception:
            pass
    if requester != "odia_asr":
        try:
            from backend.services.odia_asr_service import release_model

            release_model()
        except Exception:
            pass
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


@contextmanager
def gpu_operation(name: str, *, exclusive: bool = False):
    """Serialize GPU inference; optionally make room for a large model."""
    with _GPU_LOCK:
        if exclusive:
            _release_idle_models(name)
        yield
