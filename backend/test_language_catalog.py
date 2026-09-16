"""Locks the honest seven-language capability matrix across local surfaces."""

from backend.language_catalog import (
    CODES,
    DESKTOP_ENGINES,
    LANGUAGES,
    PHONE_OFFLINE_CORE,
)
from backend.config.runtime import PIPER_VOICES as RUNTIME_PIPER_VOICES
from scripts.install_arabic_odia_models import OCR_LANGS, PIPER_VOICES


EXPECTED_CODES = ("en", "de", "fr", "es", "hi", "ar", "or")


def test_canonical_catalog_is_complete_and_ordered():
    assert tuple(code for _name, code, _native in LANGUAGES) == EXPECTED_CODES
    assert CODES == set(EXPECTED_CODES)
    assert set(DESKTOP_ENGINES) == set(EXPECTED_CODES)


def test_phone_offline_core_stays_truthful():
    assert PHONE_OFFLINE_CORE == {"en", "de", "fr", "es", "ar"}
    assert "hi" not in PHONE_OFFLINE_CORE
    assert "or" not in PHONE_OFFLINE_CORE


def test_every_desktop_language_has_voice_speech_and_ocr_engines():
    for code in EXPECTED_CODES:
        assert DESKTOP_ENGINES[code]["tts"] in {"piper", "mms"}
        assert DESKTOP_ENGINES[code]["stt"] in {"whisper", "mms"}
        assert DESKTOP_ENGINES[code]["ocr"] in OCR_LANGS


def test_french_pack_is_part_of_runtime_and_installer():
    assert RUNTIME_PIPER_VOICES["fr"] == "fr_FR-tom-medium.onnx"
    assert PIPER_VOICES["French"][1] == "fr_FR-tom-medium.onnx"
    assert "fra" in OCR_LANGS


def test_french_text_is_detected_by_the_local_fallback():
    from backend.services.language_service import detect_text_language

    result = detect_text_language(
        "Bonjour, cette traduction française utilise une voix et un document local."
    )
    assert result["language"] == "fr"
