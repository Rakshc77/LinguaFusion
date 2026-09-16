"""Canonical LinguaFusion language and capability catalogue.

Every desktop/local surface imports this module.  Cloud and Android mirror the
same seven codes in their own runtimes, while explicitly limiting phone-only
Offline speech/translation to ``PHONE_OFFLINE_CORE``.
"""

from __future__ import annotations

LANGUAGES = (
    ("English", "en", "English"),
    ("German", "de", "Deutsch"),
    ("French", "fr", "Français"),
    ("Spanish", "es", "Español"),
    ("Hindi", "hi", "हिन्दी"),
    ("Arabic", "ar", "العربية"),
    ("Odia", "or", "ଓଡ଼ିଆ"),
)

CODES = frozenset(code for _name, code, _native in LANGUAGES)
NAMES = {code: name for name, code, _native in LANGUAGES}
NATIVE_NAMES = {code: native for _name, code, native in LANGUAGES}
DESKTOP_LANGUAGES = tuple((name, code) for name, code, _native in LANGUAGES)

# The compact Android offline product deliberately keeps these five. Hindi and
# Odia remain available Online and in pronunciation/read-aloud where a device
# voice exists; they are never falsely advertised as phone-offline STT/NMT.
PHONE_OFFLINE_CORE = frozenset({"en", "de", "fr", "es", "ar"})

# Local Windows engines: Piper for Latin/Devanagari voices, MMS for Arabic and
# Odia, faster-whisper for all except Odia, and dedicated MMS ASR for Odia.
DESKTOP_ENGINES = {
    "en": {"tts": "piper", "stt": "whisper", "ocr": "eng"},
    "de": {"tts": "piper", "stt": "whisper", "ocr": "deu"},
    "fr": {"tts": "piper", "stt": "whisper", "ocr": "fra"},
    "es": {"tts": "piper", "stt": "whisper", "ocr": "spa"},
    "hi": {"tts": "piper", "stt": "whisper", "ocr": "hin"},
    "ar": {"tts": "mms", "stt": "whisper", "ocr": "ara"},
    "or": {"tts": "mms", "stt": "mms", "ocr": "ori"},
}
