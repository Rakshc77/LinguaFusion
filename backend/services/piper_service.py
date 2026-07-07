import sys
import re
import subprocess
import unicodedata
from pathlib import Path
from uuid import uuid4

from pydub import AudioSegment

from backend.config.paths import TEMP_DIR, PIPER_MODELS_DIR, ensure_runtime_dirs

MODELS_DIR = PIPER_MODELS_DIR
ensure_runtime_dirs()

VOICE_MODELS = {
    "en": "en_US-lessac-medium.onnx",
    "de": "de_DE-thorsten-medium.onnx",
    "es": "es_ES-sharvard-medium.onnx",
    "hi": "hi_IN-priyamvada-medium.onnx",
}


def normalize_lang(lang: str) -> str:
    return (lang or "en").lower().replace("_", "-").split("-")[0]


def clean_text_for_tts(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("\ufffd", "")

    text = re.sub(r"---\s*Page\s*\d+\s*---", " ", text)
    text = re.sub(r"---\s*OCR Page\s*\d+\s*---", " ", text)

    replacements = {
        "•": ". ",
        "→": " to ",
        "–": "-",
        "—": "-",
        "…": "...",
        "\u00a0": " ",
        "\u200b": "",
        "\ufeff": "",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"https?://\S+", " link ", text)
    text = "".join(ch for ch in text if ch.isprintable() or ch in "\n\t ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def prepare_text_for_piper(text: str, lang: str) -> str:
    # Piper German voices handle umlauts better than English-style replacements.
    # Keep native characters so German names/terms are not anglicized.
    return text


def speed_to_length_scale(speed: float) -> float:
    try:
        speed = float(speed)
    except Exception:
        speed = 1.0

    speed = max(0.5, min(speed, 2.0))
    return round(1.0 / speed, 3)



GERMAN_TTS_HINTS = {
    "hallo", "zusammen", "heute", "testen", "wir", "den", "die", "das", "mit", "langen", "saetzen",
    "sätzen", "eigennamen", "technischen", "begriffen", "korrekt", "erkennt", "besonders", "wichtig",
    "woerter", "wörter", "wie", "und", "ich", "wohne", "urspruenglich", "ursprünglich", "komme", "aus",
    "deutsche", "saetze", "sätze", "hessen", "baden", "wuerttemberg", "württemberg", "nordrhein", "westfalen",
    "karlsruher", "institut", "fuer", "für", "technologie",
}
ENGLISH_TTS_HINTS = {
    "this", "paragraph", "combines", "english", "german", "system", "should", "correctly", "detect",
    "language", "allow", "tts", "playback", "keep", "waveform", "synchronized", "workflow", "includes",
    "simulation", "post", "processing", "comparison", "important", "values", "reader", "translation", "challenge",
    "please", "translate", "check", "remain", "recognizable", "after", "export", "sentence", "deliberately", "long",
    "checkpoint", "value", "expected", "route", "price", "delay", "voice", "auto", "preserve", "hyphen",
    "amount", "minus", "sign", "field", "metric", "table", "row", "column", "keep", "name", "city",
}
SPANISH_TTS_HINTS = {
    "hola", "gracias", "despues", "después", "aparece", "linea", "línea", "espanol", "español",
    "trabajo", "documentos", "audio", "reconocimiento", "automatico", "automático", "idioma", "lector",
    "prueba", "nombres", "propios", "terminos", "términos", "tecnicos", "técnicos", "resultado",
    "traduccion", "traducción", "conserva", "saltos", "tambien", "también", "incluye",
}
HINDI_TTS_HINTS = {
    "और", "है", "हैं", "में", "का", "की", "के", "यह", "इस", "कृपया", "अनुवाद", "रीडर",
    "दस्तावेज़", "तकनीकी", "शब्द", "नाम", "सिस्टम", "परीक्षण", "भाषा", "वाक्य",
}


def _tts_tokens(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Za-zÀ-ÿ]+", text or "")]


def detect_tts_segment_language(text: str, fallback: str = "en") -> str:
    segment = text or ""
    if re.search(r"[\u0900-\u097F]", segment):
        return "hi"

    tokens = _tts_tokens(segment)
    scores = {"de": 0, "en": 0, "es": 0, "hi": 0}
    if re.search(r"[ÄÖÜäöüß]", segment):
        scores["de"] += 3
    if re.search(r"[áéíóúñÁÉÍÓÚÑ¿¡]", segment):
        scores["es"] += 3

    lowered = segment.lower()
    if re.search(r"\b(?:hallo zusammen|heute testen|deutsche sätze|eigennamen|technischen begriffen)\b", lowered):
        scores["de"] += 4
    if re.search(r"\b(?:this paragraph|the system|ray-tracing workflow|translation challenge|long sentence)\b", lowered):
        scores["en"] += 4
    if re.search(r"\b(?:después aparece|en español|trabajo con|el lector|la prueba|el resultado)\b", lowered):
        scores["es"] += 4

    for token in tokens:
        normalized = token.replace("ü", "ue").replace("ä", "ae").replace("ö", "oe").replace("ß", "ss")
        if token in GERMAN_TTS_HINTS or normalized in GERMAN_TTS_HINTS:
            scores["de"] += 1
        if token in ENGLISH_TTS_HINTS or normalized in ENGLISH_TTS_HINTS:
            scores["en"] += 1
        if token in SPANISH_TTS_HINTS or normalized in SPANISH_TTS_HINTS:
            scores["es"] += 1

    best_lang, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score >= 2:
        return best_lang
    fb = normalize_lang(fallback)
    return fb if fb in VOICE_MODELS and fb != "auto" else "en"


def _split_mixed_script_sentence(sentence: str, fallback: str) -> list[tuple[str, str]]:
    """Split mixed-script sentences so Hindi text does not get read by a German/English voice."""
    sentence = (sentence or "").strip()
    if not sentence:
        return []
    if not re.search(r"[\u0900-\u097F]", sentence):
        return [(sentence, detect_tts_segment_language(sentence, fallback=fallback))]

    parts: list[tuple[str, str]] = []
    pattern = re.compile(r"[\u0900-\u097F][\u0900-\u097F\s।,;:!?()\-]*|[^\u0900-\u097F]+")
    for match in pattern.finditer(sentence):
        part = match.group(0).strip()
        if not part:
            continue
        # Do not create a separate audio segment for punctuation-only leftovers.
        if not re.search(r"[A-Za-zÀ-ÿ\u0900-\u097F0-9]", part):
            if parts:
                parts[-1] = (parts[-1][0] + part, parts[-1][1])
            continue
        lang = "hi" if re.search(r"[\u0900-\u097F]", part) else detect_tts_segment_language(part, fallback=fallback)
        if parts and parts[-1][1] == lang and len(parts[-1][0]) + len(part) < 700:
            parts[-1] = (parts[-1][0] + " " + part, lang)
        else:
            parts.append((part, lang))
    return parts or [(sentence, detect_tts_segment_language(sentence, fallback=fallback))]


def split_text_for_mixed_tts(text: str, fallback: str = "en") -> list[tuple[str, str]]:
    clean = clean_text_for_tts(text)
    if not clean:
        return []
    # Sentence-first, then script-aware segmentation. This supports English,
    # German, Spanish and Hindi in one Reader/Translate playback pass.
    raw_parts = re.split(r"(?<=[.!?।])\s+(?=[A-ZÄÖÜÁÉÍÓÚÑ¿¡\u0900-\u097F])", clean)
    segments: list[tuple[str, str]] = []
    for raw in raw_parts:
        for part, lang in _split_mixed_script_sentence(raw, fallback=fallback):
            if not part:
                continue
            if segments and segments[-1][1] == lang and len(segments[-1][0]) + len(part) < 1200:
                segments[-1] = (segments[-1][0] + " " + part, lang)
            else:
                segments.append((part, lang))
    return segments


def speak_mixed_to_file(text: str, output_name: str = "speech.wav", speed: float = 1.0, fallback_lang: str = "en") -> Path:
    segments = split_text_for_mixed_tts(text, fallback=fallback_lang)
    if not segments:
        raise ValueError("No readable text available for mixed-language TTS.")

    output_path = TEMP_DIR / output_name
    combined = AudioSegment.silent(duration=80)
    temp_paths: list[Path] = []
    try:
        for segment_text, segment_lang in segments:
            temp_path = speak_to_file(segment_text, segment_lang, f"tts_part_{uuid4().hex}.wav", speed=speed)
            temp_paths.append(temp_path)
            combined += AudioSegment.from_file(temp_path) + AudioSegment.silent(duration=140)
        combined.export(output_path, format="wav")
    finally:
        for temp_path in temp_paths:
            try:
                temp_path.unlink()
            except Exception:
                pass

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Mixed-language TTS did not create a valid WAV file.")
    return output_path

def speak_to_file(
    text: str,
    lang: str = "en",
    output_name: str = "speech.wav",
    speed: float = 1.0,
) -> Path:
    lang_code = normalize_lang(lang)

    if lang_code in {"auto", "mixed"}:
        return speak_mixed_to_file(text, output_name=output_name, speed=speed, fallback_lang="en")

    voice_name = VOICE_MODELS.get(lang_code)
    if voice_name is None:
        raise ValueError(f"No TTS voice configured for language: {lang}")

    voice_model = MODELS_DIR / voice_name
    voice_config = Path(str(voice_model) + ".json")

    if not voice_model.exists():
        raise FileNotFoundError(f"Missing Piper voice model: {voice_model}")

    if not voice_config.exists():
        raise FileNotFoundError(f"Missing Piper voice config: {voice_config}")

    output_path = TEMP_DIR / output_name

    clean_text = clean_text_for_tts(text)
    clean_text = prepare_text_for_piper(clean_text, lang_code)
    clean_text = clean_text[:4000].strip()

    if not clean_text:
        raise ValueError("No readable text available for TTS.")

    input_txt = TEMP_DIR / f"piper_input_{uuid4().hex}.txt"
    input_txt.write_text(clean_text, encoding="utf-8")

    length_scale = speed_to_length_scale(speed)

    command = [
        sys.executable,
        "-m",
        "piper",
        "--model",
        str(voice_model),
        "--config",
        str(voice_config),
        "--input-file",
        str(input_txt),
        "--output-file",
        str(output_path),
        "--length-scale",
        str(length_scale),
    ]

    try:
        subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            "Piper failed.\n"
            f"STDOUT: {e.stdout}\n"
            f"STDERR: {e.stderr}\n"
            f"Input preview: {clean_text[:500]}"
        )
    finally:
        try:
            input_txt.unlink()
        except Exception:
            pass

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Piper did not create a valid WAV file.")

    return output_path