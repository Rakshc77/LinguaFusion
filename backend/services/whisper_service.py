"""Whisper transcription service backed by faster-whisper.

Drop-in replacement for the old whisper.cpp subprocess version:
- exposes the same entry point: transcribe_audio(audio_path, language="auto") -> dict
- the model is loaded ONCE per process and kept in memory (no per-request reload)
- language "auto" is a single detection pass (no more triple-run heuristic)
- no log-scrubbing regexes needed; faster-whisper returns clean text
- word/segment timestamps are included in the result for future Reader highlighting

Configuration via environment variables (all optional):
- LF_WHISPER_MODEL   model name/size, default "small"
                     (tiny, base, small, medium, large-v3, distil-large-v3, ...)
- LF_WHISPER_DEVICE  "cuda", "cpu", or "auto" (default "cuda": require GPU)

On first use, faster-whisper downloads the chosen model from Hugging Face into
its local cache (~500 MB for small, ~1.5 GB for medium, ~3 GB for large-v3).
After that it works fully offline.
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

MODEL_NAME = os.environ.get("LF_WHISPER_MODEL", "small").strip() or "small"
DEVICE_PREF = os.environ.get("LF_WHISPER_DEVICE", "cuda").strip().lower() or "cuda"
ASR_HOTWORDS = os.environ.get("LF_WHISPER_HOTWORDS", "LinguaFusion").strip()

SUPPORTED_LANGS = {"en", "de", "es", "hi", "ar", "or"}
WHISPER_LANGS = SUPPORTED_LANGS - {"or"}

NOISE_TOKENS = {
    "silence", "music", "musique", "musik", "applause", "laughter", "laughs",
    "noise", "background noise", "inaudible", "keyboard clicking", "guitar music",
}

_model = None
_model_desc = ""
_model_lock = threading.Lock()
_inference_lock = threading.Lock()
_cuda_dll_directory_handles = []
_registered_cuda_dll_dirs = set()
_cuda_library_handles = []
_preloaded_cuda_libraries = set()


def _register_windows_cuda_dll_dirs() -> None:
    """Work around a Windows-only Python 3.8+ behavior change.

    Since Python 3.8, extension modules on Windows no longer search the PATH
    environment variable for their DLL dependencies -- only os.add_dll_directory
    registrations, the extension's own folder, and System32 are searched. Pip
    packages like nvidia-cublas-cu12 / nvidia-cudnn-cu12 install real DLLs into
    site-packages but don't register them this way, so ctranslate2 (which
    faster-whisper is built on) fails to find cublas64_12.dll / cudnn64_9.dll
    even when PATH is set correctly. This registers those folders directly.

    Note: "nvidia" itself is a namespace package (no __init__.py, no __file__),
    so each real subpackage (nvidia.cublas, nvidia.cudnn, ...) must be imported
    individually to find its on-disk location.
    """
    if os.name != "nt":
        return
    preload_by_module = {
        "nvidia.cublas": ("cublasLt64_12.dll", "cublas64_12.dll"),
    }
    for module_name in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_runtime", "nvidia.cuda_nvrtc"):
        try:
            module = __import__(module_name, fromlist=["_"])
            pkg_dirs = list(getattr(module, "__path__", []))
            if not pkg_dirs and getattr(module, "__file__", None):
                pkg_dirs = [str(Path(module.__file__).resolve().parent)]
        except Exception:
            continue
        for pkg_dir in pkg_dirs:
            bin_dir = Path(pkg_dir) / "bin"
            resolved_bin_dir = str(bin_dir.resolve()) if bin_dir.is_dir() else ""
            if resolved_bin_dir and resolved_bin_dir not in _registered_cuda_dll_dirs:
                try:
                    # Keep the returned handle alive for the process lifetime.
                    # Dropping it immediately removes the directory again on
                    # CPython, which made direct NLLB loads miss cublas64_12.dll.
                    handle = os.add_dll_directory(resolved_bin_dir)
                    _cuda_dll_directory_handles.append(handle)
                    _registered_cuda_dll_dirs.add(resolved_bin_dir)
                except (OSError, AttributeError):
                    pass
            # CTranslate2 4.8 loads cuBLAS by name at inference time and does
            # not consistently honor AddDllDirectory on all Windows Python
            # installations. Preload the two core libraries by absolute path
            # and retain their handles so both Whisper and NLLB are reliable.
            for dll_name in preload_by_module.get(module_name, ()):
                dll_path = bin_dir / dll_name
                resolved_dll = str(dll_path.resolve()) if dll_path.is_file() else ""
                if resolved_dll and resolved_dll not in _preloaded_cuda_libraries:
                    try:
                        import ctypes

                        library = ctypes.WinDLL(resolved_dll)
                        _cuda_library_handles.append(library)
                        _preloaded_cuda_libraries.add(resolved_dll)
                    except (OSError, AttributeError):
                        pass


if DEVICE_PREF != "cpu":
    _register_windows_cuda_dll_dirs()


# ---------------------------------------------------------------------------
# Model lifecycle: load once, keep in memory.
# ---------------------------------------------------------------------------


def _load_model():
    """Load the faster-whisper model once. Thread-safe."""
    global _model, _model_desc
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        from faster_whisper import WhisperModel

        attempts = []
        if DEVICE_PREF in {"auto", "cuda"}:
            attempts.append(("cuda", "float16"))
            attempts.append(("cuda", "int8_float16"))
        if DEVICE_PREF in {"auto", "cpu"}:
            attempts.append(("cpu", "int8"))
        if DEVICE_PREF == "cuda" and not attempts:
            attempts.append(("cuda", "float16"))

        last_error: Optional[Exception] = None
        for device, compute_type in attempts:
            try:
                _model = WhisperModel(MODEL_NAME, device=device, compute_type=compute_type)
                _model_desc = f"faster-whisper/{MODEL_NAME} ({device}, {compute_type})"
                return _model
            except Exception as exc:  # missing cuDNN, no GPU, etc. -> try next option
                last_error = exc
                continue
        raise RuntimeError(f"Could not load faster-whisper model '{MODEL_NAME}': {last_error}")


def warm_up() -> str:
    """Optionally call at server startup so the first request isn't slow."""
    _load_model()
    return _model_desc


def release_model() -> None:
    """Release the cached Whisper allocation for an exclusive GPU handover."""
    global _model, _model_desc
    with _model_lock:
        _model = None
        _model_desc = ""


# ---------------------------------------------------------------------------
# Text cleanup (kept from the previous implementation; still useful for songs).
# ---------------------------------------------------------------------------


def _normalize_language(language: str) -> str:
    language = (language or "auto").lower().replace("_", "-").split("-")[0]
    aliases = {
        "english": "en", "german": "de", "deutsch": "de",
        "spanish": "es", "espanol": "es", "español": "es",
        "hindi": "hi", "hin": "hi",
        "arabic": "ar", "ara": "ar",
        "odia": "or", "oriya": "or", "ory": "or", "ori": "or",
    }
    language = aliases.get(language, language)
    if language in SUPPORTED_LANGS:
        return language
    return "auto"


def _remove_noise_markers(text: str) -> str:
    def repl(match: re.Match) -> str:
        token = match.group(1).strip().lower()
        return " " if token in NOISE_TOKENS else match.group(0)

    text = re.sub(r"\(([^()]{1,60})\)", repl, text or "")
    text = re.sub(r"\[([^\[\]]{1,60})\]", repl, text)
    return text


def _normalize_spacing(text: str) -> str:
    text = (text or "").replace("\ufffd", " ")
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])(?=\S)", r"\1 ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _dedupe_exact_repetition(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    pieces = re.split(r"(?<=[.!?])\s+", text)
    result: List[str] = []
    counts: Dict[str, int] = {}
    prev = ""
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        norm = re.sub(r"\W+", " ", piece.lower()).strip()
        if not norm:
            continue
        if norm == prev:
            continue
        counts[norm] = counts.get(norm, 0) + 1
        # Keep a repeated chorus twice, but block cascades.
        if counts[norm] > 2:
            continue
        result.append(piece)
        prev = norm
    return " ".join(result).strip()


def _clean_text(text: str) -> str:
    text = _remove_noise_markers(text or "")
    text = _normalize_spacing(text)
    return _dedupe_exact_repetition(text)


# ---------------------------------------------------------------------------
# Public API.
# ---------------------------------------------------------------------------


def transcribe_audio(audio_path: Path, language: str = "auto") -> Dict[str, Any]:
    """Transcribe an audio file. Same contract as the old whisper.cpp version.

    Returns:
        {ok, text, language, model, error, duration, segments}
        where segments is a list of {start, end, text, words} with word-level
        timestamps (words: list of {start, end, word}).
    """
    language = _normalize_language(language)
    path = Path(audio_path)

    if str(path).strip().lower() in {"", "false", "none", "0"} or not path.exists():
        return {"ok": False, "text": "", "language": language, "model": _model_desc or MODEL_NAME,
                "error": f"Audio file not found: {audio_path!r}"}

    # Whisper has no Odia language token. Route explicitly selected Odia
    # through the dedicated offline MMS recognizer instead of silently using
    # Whisper auto-detection and returning low-quality text.
    if language == "or":
        from backend.services.odia_asr_service import transcribe_odia

        return transcribe_odia(path)

    lang_arg = None if language == "auto" else language
    try:
        # FastAPI runs speech endpoints in its worker pool. Live transcription
        # can therefore overlap the final transcription fired when recording
        # stops. Both requests share this model (and its CUDA context), so keep
        # inference single-file to avoid concurrent VRAM use/corrupt output.
        # The generator must be consumed while holding the lock because most of
        # faster-whisper's actual work happens during iteration.
        from backend.services.gpu_coordinator import gpu_operation

        with gpu_operation("whisper"), _inference_lock:
            model = _load_model()

            def run_pass(use_vad: bool):
                segments_iter, pass_info = model.transcribe(
                    str(path),
                    language=lang_arg,
                    beam_size=5,
                    hotwords=ASR_HOTWORDS or None,
                    word_timestamps=True,
                    # Whisper tends to loop on music/silence when conditioning on its
                    # own previous output; disabling this reduces repetition cascades.
                    condition_on_previous_text=False,
                    # VAD usually removes silence hallucinations, but narration over
                    # music and some compressed voices can be rejected wholesale.
                    vad_filter=use_vad,
                )

                pass_segments: List[Dict[str, Any]] = []
                pass_parts: List[str] = []
                for seg in segments_iter:
                    pass_parts.append(seg.text)
                    pass_segments.append({
                        "start": round(float(seg.start or 0.0), 3),
                        "end": round(float(seg.end or 0.0), 3),
                        "text": seg.text.strip(),
                        "words": [
                            {"start": round(float(w.start or 0.0), 3),
                             "end": round(float(w.end or 0.0), 3),
                             "word": w.word}
                            for w in (seg.words or [])
                        ],
                    })
                return pass_parts, pass_segments, pass_info

            try:
                parts, segments, info = run_pass(use_vad=True)
                vad_fallback_used = False
                if not _clean_text(" ".join(parts)):
                    # A non-empty, valid audio file must get one unfiltered retry.
                    # This fixed real 16 kHz speech that Silero VAD classified as
                    # entirely non-speech even though 95/97 seconds had signal.
                    parts, segments, info = run_pass(use_vad=False)
                    vad_fallback_used = True
            except Exception:
                # If Silero VAD or ONNXRuntime encounters a missing model file or load failure,
                # smoothly fall back to standard non-VAD transcription pass.
                parts, segments, info = run_pass(use_vad=False)
                vad_fallback_used = True

        text = _clean_text(" ".join(parts))
        detected = getattr(info, "language", None) or (lang_arg or "en")
        if detected not in SUPPORTED_LANGS:
            detected = lang_arg or detected

        return {
            "ok": True,
            "text": text,
            "language": detected,
            "language_probability": round(float(getattr(info, "language_probability", 0.0) or 0.0), 3),
            "model": _model_desc or MODEL_NAME,
            "duration": round(float(getattr(info, "duration", 0.0) or 0.0), 2),
            "segments": segments,
            "vad_fallback_used": vad_fallback_used,
            "error": None,
        }
    except Exception as exc:
        return {"ok": False, "text": "", "language": language, "model": _model_desc or MODEL_NAME, "error": str(exc)}
