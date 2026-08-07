"""GPU-backed Odia speech recognition using a local MMS ASR checkpoint.

Whisper does not include Odia in its supported language-token list.  This
module therefore uses an Odia-targeted copy of Meta's MMS multilingual ASR
model.  The installer saves the selected adapter with the base model so runtime
inference is entirely offline and never needs a Hugging Face account.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

import numpy as np
from pydub import AudioSegment

from backend.config.paths import ODIA_ASR_MODEL_DIR


DEVICE_PREF = os.environ.get("LF_ODIA_ASR_DEVICE", "cuda").strip().lower() or "cuda"
_processor = None
_model = None
_device = ""
_load_lock = threading.Lock()
_inference_lock = threading.Lock()


def release_model() -> None:
    global _processor, _model, _device
    with _load_lock:
        _processor = None
        _model = None
        _device = ""


def is_available() -> bool:
    return ODIA_ASR_MODEL_DIR.is_dir() and (ODIA_ASR_MODEL_DIR / "config.json").is_file()


def _load():
    global _processor, _model, _device
    if _processor is not None and _model is not None:
        return _processor, _model, _device
    with _load_lock:
        if _processor is not None and _model is not None:
            return _processor, _model, _device
        if not is_available():
            raise FileNotFoundError(
                f"The offline Odia speech model is missing at {ODIA_ASR_MODEL_DIR}. "
                "Run scripts\\install_arabic_odia_models.ps1 once while online."
            )

        import torch
        from transformers import AutoModelForCTC, AutoProcessor

        if DEVICE_PREF == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("Odia speech is configured for GPU, but CUDA is unavailable.")
        device = "cuda" if DEVICE_PREF in {"cuda", "auto"} and torch.cuda.is_available() else "cpu"
        processor = AutoProcessor.from_pretrained(str(ODIA_ASR_MODEL_DIR), local_files_only=True)
        model = AutoModelForCTC.from_pretrained(str(ODIA_ASR_MODEL_DIR), local_files_only=True)
        model.to(device)
        model.eval()
        _processor, _model, _device = processor, model, device
        return _processor, _model, _device


def _read_16khz_mono(path: Path) -> tuple[np.ndarray, float]:
    audio = AudioSegment.from_file(path).set_channels(1).set_frame_rate(16000).set_sample_width(2)
    samples = np.asarray(audio.get_array_of_samples(), dtype=np.float32) / 32768.0
    return samples, len(audio) / 1000.0


def transcribe_odia(audio_path: Path) -> dict[str, Any]:
    path = Path(audio_path)
    if not path.is_file():
        return {"ok": False, "text": "", "language": "or", "model": "mms-asr-odia", "error": f"Audio file not found: {path}"}
    try:
        import torch

        from backend.services.gpu_coordinator import gpu_operation

        samples, duration = _read_16khz_mono(path)
        if samples.size == 0:
            raise ValueError("The audio file contains no samples.")
        with gpu_operation("odia_asr", exclusive=DEVICE_PREF != "cpu"):
            processor, model, device = _load()
            try:
                with _inference_lock, torch.inference_mode():
                    inputs = processor(samples, sampling_rate=16000, return_tensors="pt")
                    model_inputs = {name: value.to(device) for name, value in inputs.items()}
                    logits = model(**model_inputs).logits
                    prediction_ids = torch.argmax(logits, dim=-1)
                    text = processor.batch_decode(prediction_ids.detach().cpu())[0].strip()
            finally:
                if DEVICE_PREF != "cpu" and os.environ.get("LF_ODIA_ASR_KEEP_LOADED", "0").lower() not in {"1", "true", "yes"}:
                    release_model()
                    torch.cuda.empty_cache()
        result = {
            "ok": True,
            "text": text,
            "language": "or",
            "language_probability": 1.0,
            "model": f"mms-asr-odia ({device})",
            "duration": round(duration, 2),
            "segments": [],
            "error": None,
        }
        return result
    except Exception as exc:
        return {"ok": False, "text": "", "language": "or", "model": "mms-asr-odia", "error": str(exc)}
