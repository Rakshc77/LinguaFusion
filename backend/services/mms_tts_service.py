"""Offline Arabic and Odia TTS using small language-specific Meta MMS voices."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from backend.config.paths import MMS_TTS_MODELS_DIR, TEMP_DIR


MODEL_DIRS = {
    "ar": MMS_TTS_MODELS_DIR / "ara",
    "or": MMS_TTS_MODELS_DIR / "ory",
}
DEVICE_PREF = os.environ.get("LF_MMS_TTS_DEVICE", "cuda").strip().lower() or "cuda"
_cache: dict[str, tuple[object, object, str]] = {}
_load_lock = threading.Lock()
_inference_lock = threading.Lock()


def release_models() -> None:
    with _load_lock:
        _cache.clear()


def is_available(lang: str) -> bool:
    model_dir = MODEL_DIRS.get(lang)
    return bool(model_dir and model_dir.is_dir() and (model_dir / "config.json").is_file())


def _load(lang: str):
    cached = _cache.get(lang)
    if cached:
        return cached
    with _load_lock:
        cached = _cache.get(lang)
        if cached:
            return cached
        model_dir = MODEL_DIRS.get(lang)
        if not model_dir or not is_available(lang):
            raise FileNotFoundError(
                f"The offline {lang} TTS model is missing at {model_dir}. "
                "Run scripts\\install_arabic_odia_models.ps1 once while online."
            )

        import torch
        from transformers import AutoTokenizer, VitsModel

        if DEVICE_PREF == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("MMS TTS is configured for GPU, but CUDA is unavailable.")
        device = "cuda" if DEVICE_PREF in {"cuda", "auto"} and torch.cuda.is_available() else "cpu"
        tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
        model = VitsModel.from_pretrained(str(model_dir), local_files_only=True).to(device)
        model.eval()
        _cache[lang] = (tokenizer, model, device)
        return _cache[lang]


def speak_to_file(text: str, lang: str, output_path: Path, speed: float = 1.0) -> Path:
    if lang not in MODEL_DIRS:
        raise ValueError(f"MMS TTS is not configured for language: {lang}")
    from backend.services.piper_service import clean_tts_punctuation

    clean = clean_tts_punctuation(text or "", lang)[:4000]
    if not clean:
        raise ValueError("No readable text available for TTS.")

    import torch

    from backend.services.gpu_coordinator import gpu_operation

    with gpu_operation("mms_tts", exclusive=DEVICE_PREF != "cpu"):
        tokenizer, model, device = _load(lang)
        with _inference_lock, torch.inference_mode():
            inputs = tokenizer(clean, return_tensors="pt")
            model_inputs = {name: value.to(device) for name, value in inputs.items()}
            waveform = model(**model_inputs).waveform[0].detach().float().cpu().numpy()
        rate = int(model.config.sampling_rate)
        if DEVICE_PREF != "cpu" and os.environ.get("LF_MMS_TTS_KEEP_LOADED", "0").lower() not in {"1", "true", "yes"}:
            release_models()
            torch.cuda.empty_cache()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    peak = float(np.max(np.abs(waveform))) if waveform.size else 0.0
    pcm = np.int16(np.clip(waveform / max(peak, 1.0), -1.0, 1.0) * 32767)
    wavfile.write(str(output_path), rate, pcm)

    requested_speed = max(0.5, min(float(speed or 1.0), 2.0))
    if abs(requested_speed - 1.0) > 0.01:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(output_path)
        shifted = audio._spawn(audio.raw_data, overrides={"frame_rate": int(audio.frame_rate * requested_speed)})
        shifted.set_frame_rate(audio.frame_rate).export(output_path, format="wav")
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError("MMS TTS did not create a valid WAV file.")
    return output_path
