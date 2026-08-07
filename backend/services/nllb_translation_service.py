"""NLLB-200 translation backed by ctranslate2.

A drop-in quality upgrade over Argos Translate: NLLB-200 is a purpose-built
translation model (not a general chat LLM), so unlike routing translation
through Ollama, it has no tendency to "helpfully" rewrite or embellish --
its only job is translation. Runs on ctranslate2, which is already installed
for faster-whisper, so this adds no new heavy dependency beyond the model
weights themselves and the `transformers` package (for its tokenizer).

Setup (one-time, requires internet the first time only):
    pip install transformers sentencepiece
    ct2-transformers-converter --model facebook/nllb-200-distilled-600M \\
        --output_dir models/nllb-200-distilled-600m --quantization int8 \\
        --copy_files tokenizer_config.json special_tokens_map.json \\
            tokenizer.json sentencepiece.bpe.model

That downloads ~2.4GB from Hugging Face and converts it into a ctranslate2
model (~600MB on disk after int8 quantization). Place the output at
<project_root>/models/nllb-200-distilled-600m, or point NLLB_MODEL_DIR at
wherever you put it.

If the model directory doesn't exist, is_available() returns False and
translation_service.py automatically falls back to Argos -- nothing breaks
if you haven't set this up yet.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional

from backend.config.paths import PROJECT_ROOT
from backend.services.whisper_service import _register_windows_cuda_dll_dirs

DEFAULT_MODEL_DIR = PROJECT_ROOT / "models" / "nllb-200-distilled-600m"
MODEL_DIR = Path(os.environ.get("NLLB_MODEL_DIR", str(DEFAULT_MODEL_DIR)))
DEVICE_PREF = os.environ.get("NLLB_DEVICE", "auto").strip().lower() or "auto"
COMPUTE_TYPE_PREF = os.environ.get("NLLB_COMPUTE_TYPE", "auto").strip().lower() or "auto"

# CTranslate2 needs the same pip-installed cuBLAS/cuDNN DLL directories as
# faster-whisper. Register them here as well so translation does not depend on
# the server importing the speech service first.
if DEVICE_PREF != "cpu":
    _register_windows_cuda_dll_dirs()

# NLLB uses its own language codes (FLORES-200 style), not plain ISO codes.
LANG_CODE_MAP = {
    "en": "eng_Latn",
    "de": "deu_Latn",
    "es": "spa_Latn",
    "hi": "hin_Deva",
    "ar": "arb_Arab",
    "or": "ory_Orya",
}

_translator = None
_tokenizer = None
_load_lock = threading.Lock()
_inference_lock = threading.Lock()
_load_error: Optional[str] = None
_runtime_compute_type: Optional[str] = None


def release_model() -> None:
    """Release cached NLLB GPU objects before a larger exclusive model job."""
    global _translator, _tokenizer, _runtime_compute_type
    with _load_lock:
        _translator = None
        _tokenizer = None
        _runtime_compute_type = None


def is_available() -> bool:
    """Cheap completeness check that does not allocate the model."""
    required = ("config.json", "model.bin", "shared_vocabulary.json", "tokenizer_config.json")
    has_tokenizer_payload = (MODEL_DIR / "tokenizer.json").is_file() or (MODEL_DIR / "sentencepiece.bpe.model").is_file()
    return MODEL_DIR.is_dir() and all((MODEL_DIR / name).is_file() for name in required) and has_tokenizer_payload


def _load():
    global _translator, _tokenizer, _load_error, _runtime_compute_type
    if _translator is not None and _tokenizer is not None:
        return _translator, _tokenizer
    with _load_lock:
        if _translator is not None and _tokenizer is not None:
            return _translator, _tokenizer
        try:
            import ctranslate2
            from transformers import AutoTokenizer

            device = DEVICE_PREF
            if device == "auto":
                device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
            compute_type = COMPUTE_TYPE_PREF
            if compute_type == "auto":
                # Pure int8 is stable on this Turing GPU and keeps NLLB near
                # 1 GB of VRAM so medium Whisper and Ollama can coexist. Avoid
                # int8_float16 here: repeated calls stalled on this card.
                compute_type = "int8"
            # Publish the pair atomically. Assigning the CUDA translator before
            # tokenization was ready used to strand ~2 GB of VRAM after a
            # tokenizer failure while every request silently fell back to Argos.
            translator = ctranslate2.Translator(str(MODEL_DIR), device=device, compute_type=compute_type)
            tokenizer = AutoTokenizer.from_pretrained(
                str(MODEL_DIR),
                local_files_only=True,
                use_fast=False,
            )
            _translator = translator
            _tokenizer = tokenizer
            _load_error = None
            _runtime_compute_type = compute_type
            return _translator, _tokenizer
        except Exception as exc:
            _translator = None
            _tokenizer = None
            _runtime_compute_type = None
            _load_error = str(exc)
            raise RuntimeError(f"Could not load NLLB model from {MODEL_DIR}: {exc}") from exc


_TRANSLATION_CACHE = {}
_TRANSLATION_CACHE_LOCK = threading.Lock()

def nllb_translate(text: str, source_lang: str, target_lang: str) -> str:
    """Translate a single string. Raises on any failure -- callers should
    catch and fall back to Argos rather than surfacing this to the user."""
    text = (text or "").strip()
    if not text:
        return ""
        
    cache_key = (text, source_lang, target_lang)
    with _TRANSLATION_CACHE_LOCK:
        if cache_key in _TRANSLATION_CACHE:
            val = _TRANSLATION_CACHE.pop(cache_key)
            _TRANSLATION_CACHE[cache_key] = val
            return val

    source_code = LANG_CODE_MAP.get(source_lang)
    target_code = LANG_CODE_MAP.get(target_lang)
    if not source_code or not target_code:
        raise ValueError(f"Unsupported language pair for NLLB: {source_lang} -> {target_lang}")

    # src_lang is mutable tokenizer state and the CTranslate2 instance owns a
    # shared CUDA context. FastAPI may run multiple translation routes in its
    # worker pool, so protect the entire encode/infer/decode operation.
    from backend.services.gpu_coordinator import gpu_operation

    with gpu_operation("nllb"), _inference_lock:
        translator, tokenizer = _load()
        tokenizer.src_lang = source_code
        source_tokens = tokenizer.convert_ids_to_tokens(tokenizer(text).input_ids)
        target_prefix = [target_code]
        max_target_length = max(64, min(512, len(source_tokens) * 3 + 16))

        results = translator.translate_batch(
            [source_tokens],
            target_prefix=[target_prefix],
            beam_size=4,
            max_decoding_length=max_target_length,
        )
        output_tokens = results[0].hypotheses[0][1:]  # drop the target-language prefix token
        output_ids = tokenizer.convert_tokens_to_ids(output_tokens)
        result_text = tokenizer.decode(output_ids, skip_special_tokens=True).strip()
        
    with _TRANSLATION_CACHE_LOCK:
        _TRANSLATION_CACHE[cache_key] = result_text
        if len(_TRANSLATION_CACHE) > 512:
            keys_to_remove = list(_TRANSLATION_CACHE.keys())[:256]
            for k in keys_to_remove:
                _TRANSLATION_CACHE.pop(k, None)
                
    return result_text
