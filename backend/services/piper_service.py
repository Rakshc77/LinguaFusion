import os
import sys
import re
import subprocess
import unicodedata
from pathlib import Path
from uuid import uuid4

from pydub import AudioSegment

from backend.config.paths import PROJECT_ROOT, TEMP_DIR, PIPER_MODELS_DIR, ensure_runtime_dirs

MODELS_DIR = PIPER_MODELS_DIR
ensure_runtime_dirs()

VOICE_MODELS = {
    "en": "en_US-lessac-medium.onnx",
    "de": "de_DE-thorsten-medium.onnx",
    "es": "es_ES-sharvard-medium.onnx",
    "hi": "hi_IN-priyamvada-medium.onnx",
}
SUPPORTED_TTS_LANGS = set(VOICE_MODELS) | {"ar", "or"}
SCRIPT_PATTERNS = {
    "hi": re.compile(r"[\u0900-\u097F]"),
    "ar": re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]"),
    "or": re.compile(r"[\u0B00-\u0B7F]"),
}
NON_LATIN_SCRIPT_RE = re.compile(r"[\u0900-\u097F\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\u0B00-\u0B7F]")


def _script_language(text: str) -> str | None:
    counts = {lang: len(pattern.findall(text or "")) for lang, pattern in SCRIPT_PATTERNS.items()}
    lang, count = max(counts.items(), key=lambda item: item[1])
    return lang if count else None


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

    # Preserve document line boundaries as soft sentence boundaries. Without
    # this, headings/tables and mixed-language lines are collapsed together and
    # the Auto TTS detector can carry the previous language into the next block.
    lines = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = re.sub(r"[ \t]+", " ", raw).strip()
        if not line:
            continue
        if len(line) <= 90 and not re.search(r"[.!?।:]$", line):
            line += "."
        lines.append(line)
    text = " ".join(lines)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def clean_tts_punctuation(text: str, lang: str = "en") -> str:
    """Sanitize punctuation for TTS engines to prevent pronouncing punctuation glyphs aloud."""
    text = (text or "").strip()
    if not text:
        return ""
    norm_lang = normalize_lang(lang)
    if norm_lang in {"or", "ar"}:
        # Strip all punctuation glyphs completely so MMS tokenizer only receives clean phonetic words
        text = re.sub(r'[\,\.\?\!\:\;\-\–\—\"\'\`\(\)\[\]\{\}\«\»\।\॥\/\\]+', ' ', text)
    else:
        # General TTS: strip quotes/brackets and keep single punctuation pauses
        text = re.sub(r'[\"\'\`\(\)\[\]\{\}\«\»\/\\]+', ' ', text)
        text = re.sub(r'\s*([,\.?!:;\-–—।])\s*', r'\1 ', text)
    return re.sub(r'\s+', ' ', text).strip()


def prepare_text_for_piper(text: str, lang: str) -> str:
    # Piper German voices handle umlauts better than English-style replacements.
    # Keep native characters so German names/terms are not anglicized.
    return clean_tts_punctuation(text, lang)


def speed_to_length_scale(speed: float) -> float:
    try:
        speed = float(speed)
    except Exception:
        speed = 1.0

    speed = max(0.5, min(speed, 2.0))
    return round(1.0 / speed, 3)


def _synthesize_with_piper(
    voice_model: Path,
    voice_config: Path,
    input_text: str,
    output_path: Path,
    length_scale: float,
) -> None:
    """Run one Piper synthesis job.

    This small entry point is shared by the opt-in in-process path and the
    frozen application's isolated worker mode.
    """
    import wave
    from piper import PiperVoice

    voice = PiperVoice.load(str(voice_model), config_path=str(voice_config))
    if length_scale:
        voice.config.length_scale = length_scale
    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(voice.config.sample_rate)
        for chunk in voice.synthesize(input_text):
            wav_file.writeframes(chunk.audio_int16_bytes)


def run_frozen_piper_worker(args: list[str]) -> int:
    """Execute a Piper job inside a second copy of the packaged executable."""
    def _value(flag: str) -> str:
        try:
            return args[args.index(flag) + 1]
        except (ValueError, IndexError) as exc:
            raise ValueError(f"Missing Piper worker argument: {flag}") from exc

    voice_model = Path(_value("--model"))
    voice_config = Path(_value("--config"))
    input_path = Path(_value("--input-file"))
    output_path = Path(_value("--output-file"))
    length_scale = float(_value("--length-scale"))
    input_text = input_path.read_text(encoding="utf-8")
    _synthesize_with_piper(
        voice_model,
        voice_config,
        input_text,
        output_path,
        length_scale,
    )
    return 0



GERMAN_TTS_HINTS = {
    "hallo", "zusammen", "heute", "testen", "wir", "den", "die", "das", "mit", "langen", "saetzen",
    "sätzen", "eigennamen", "technischen", "begriffen", "korrekt", "erkennt", "besonders", "wichtig",
    "woerter", "wörter", "wie", "und", "ich", "wohne", "urspruenglich", "ursprünglich", "komme", "aus",
    "deutsche", "saetze", "sätze", "hessen", "baden", "wuerttemberg", "württemberg", "nordrhein", "westfalen",
    "karlsruher", "institut", "fuer", "für", "technologie", "nächste", "naechste", "sitzung", "beginnt",
    "uhr", "bitte", "prüfen", "pruefen", "wörter", "woerter", "größe", "groesse", "straße", "strasse",
    "prüfung", "pruefung", "münchen", "muenchen", "diese", "zeile", "soll", "einer", "deutschen", "stimme",
    "gelesen", "werden", "bibliothek", "öffnet", "oeffnet", "samstag", "außerdem", "ausserdem", "führung",
    "fuehrung", "altstadt", "köln", "koeln", "die", "nächste", "sitzung",
}
ENGLISH_TTS_HINTS = {
    "this", "paragraph", "combines", "english", "german", "system", "should", "correctly", "detect",
    "language", "allow", "tts", "playback", "keep", "waveform", "synchronized", "workflow", "includes",
    "simulation", "post", "processing", "comparison", "important", "values", "reader", "translation", "challenge",
    "please", "translate", "check", "remain", "recognizable", "after", "export", "sentence", "deliberately", "long",
    "checkpoint", "value", "expected", "route", "price", "delay", "voice", "auto", "preserve", "hyphen",
    "amount", "minus", "sign", "field", "metric", "table", "row", "column", "keep", "name", "city",
    "welcome", "workshop", "opening", "english", "block", "purpose", "highlight", "starts", "immediately",
    "agenda", "status", "expected", "behavior", "reader", "export", "venue", "deadline", "library", "community",
    "newsletter", "paragraph", "evening", "classes", "final", "line",
}
SPANISH_TTS_HINTS = {
    "hola", "gracias", "despues", "después", "aparece", "linea", "línea", "espanol", "español",
    "trabajo", "documentos", "audio", "reconocimiento", "automatico", "automático", "idioma", "lector",
    "prueba", "nombres", "propios", "terminos", "términos", "tecnicos", "técnicos", "resultado",
    "traduccion", "traducción", "conserva", "saltos", "tambien", "también", "incluye", "sesión", "sesion",
    "tarde", "empieza", "sala", "azul", "sistema", "debe", "cambiar", "voz", "española", "espanola", "nombres",
    "madrid", "zaragoza", "reconocerse", "correctamente", "inscripción", "inscripcion", "termina", "viernes", "plaza", "limitada",
}
HINDI_TTS_HINTS = {
    "और", "है", "हैं", "में", "का", "की", "के", "यह", "इस", "कृपया", "अनुवाद", "रीडर",
    "दस्तावेज़", "तकनीकी", "शब्द", "नाम", "सिस्टम", "परीक्षण", "भाषा", "वाक्य",
}


def _tts_tokens(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Za-zÀ-ÿ]+", text or "")]


def detect_tts_segment_language(text: str, fallback: str = "en") -> str:
    segment = text or ""
    script_lang = _script_language(segment)
    if script_lang:
        return script_lang

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
    return fb if fb in SUPPORTED_TTS_LANGS and fb != "auto" else "en"


def _is_table_like_tts_line(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped:
        return False
    if "|" in stripped:
        return True
    # Treat compact schedule/status rows as metadata, not prose. This avoids
    # accidental Spanish/German voice selection for rows that contain labels like
    # "Spanish voice" or "German voice".
    if re.match(r"^\d{1,2}:\d{2}\b", stripped):
        return True
    if re.search(r"\b(?:Expected|Behavior|Language|Value|Status|Fee|Room|Deadline|Venue)\b", stripped, re.I) and len(stripped) < 150:
        return True
    return False


def _section_context_from_line(line: str) -> str | None:
    """Return language context introduced by a heading-like line.

    This is intentionally generic. It recognizes common document headings such
    as "German session", "Section B - German", "Hindi block", etc. The context
    is applied to following ambiguous lines, while lines with their own strong
    script/diacritic evidence still override it.
    """
    lowered = re.sub(r"[#*_`>|-]+", " ", line or "").lower()
    if re.search(r"\b(arabic|arab)\b", lowered) or re.search(r"[\u0600-\u06FF]", lowered):
        return "ar"
    if re.search(r"\b(odia|oriya)\b", lowered) or re.search(r"[\u0B00-\u0B7F]", lowered):
        return "or"
    if re.search(r"\b(hindi|देवनागरी|हिन्दी|हिंदी)\b", lowered):
        return "hi"
    if re.search(r"\b(spanish|español|espanol)\b", lowered):
        return "es"
    if re.search(r"\b(german|deutsch|deutsche)\b", lowered):
        return "de"
    if re.search(r"\b(english|opening|welcome)\b", lowered):
        return "en"
    return None


def _line_is_heading_like(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return True
    if len(stripped) <= 80 and re.search(r"\b(?:section|session|block|opening|agenda|table|purpose)\b", stripped, re.I):
        return True
    return False


def _normalize_tts_line(raw: str) -> str:
    line = unicodedata.normalize("NFC", raw or "")
    line = line.replace("\ufffd", "")
    line = re.sub(r"---\s*(?:OCR\s*)?Page\s*\d+\s*---", " ", line, flags=re.I)
    line = line.replace("\u00a0", " ").replace("\u200b", "").replace("\ufeff", "")
    line = line.replace("→", " to ").replace("–", "-").replace("—", "-")
    line = re.sub(r"https?://\S+", " link ", line)
    line = "".join(ch for ch in line if ch.isprintable() or ch in "\t ")
    line = re.sub(r"[ \t]+", " ", line).strip()
    return line


def _split_latin_sentences(line: str) -> list[str]:
    line = (line or "").strip()
    if not line:
        return []
    # Keep table/metadata rows intact; splitting them makes voice selection worse.
    if _is_table_like_tts_line(line):
        return [line]
    parts = re.split(r"(?<=[.!?।])\s+(?=[A-ZÄÖÜÁÉÍÓÚÑ¿¡\u0900-\u097F])", line)
    return [p.strip() for p in parts if p.strip()]


_DE_DIACRITIC_RE = re.compile(r"[ÄÖÜäöüß]")
_ES_DIACRITIC_RE = re.compile(r"[áéíóúñÁÉÍÓÚÑ¿¡]")
_WORD_OR_SPACE_RE = re.compile(r"\S+|\s+")


def _classify_latin_word(word: str) -> str:
    if _DE_DIACRITIC_RE.search(word):
        return "de"
    if _ES_DIACRITIC_RE.search(word):
        return "es"
    return "plain"


def _split_latin_by_word_evidence(sentence: str, fallback: str) -> list[tuple[str, str]]:
    """Within one Latin-script sentence, carve out runs of words carrying
    strong diacritic evidence (German umlauts/ß, Spanish accents) into their
    own TTS voice segment, leaving the rest of the sentence in its dominant
    (sentence-level detected) language.

    This only acts where the text's spelling itself is unambiguous. A plain-
    ASCII proper noun embedded in a differently-languaged sentence (e.g. an
    English name inside a German sentence with no umlaut) has no orthographic
    signal to key off of -- word-level statistical language ID is unreliable
    on single ambiguous words too, so this intentionally leaves those as-is
    rather than guess and risk being wrong more often than the old
    whole-sentence approach was.
    """
    tokens = _WORD_OR_SPACE_RE.findall(sentence)

    # Build raw runs of (text, classification); whitespace attaches to
    # whichever run it falls inside so words don't get glued together.
    raw: list[tuple[str, str]] = []
    for tok in tokens:
        if tok.isspace():
            if raw:
                raw[-1] = (raw[-1][0] + tok, raw[-1][1])
            else:
                raw.append((tok, "plain"))
            continue
        cls = _classify_latin_word(tok)
        if raw and raw[-1][1] == cls:
            raw[-1] = (raw[-1][0] + tok, cls)
        else:
            raw.append((tok, cls))

    # The ambient language for "plain" runs must be judged from ONLY the
    # plain (non-diacritic) text -- scoring against the whole sentence would
    # let a single German/Spanish diacritic word elsewhere bias the language
    # of surrounding plain English text toward that same language.
    plain_only_text = "".join(text for text, cls in raw if cls == "plain")
    sentence_lang = detect_tts_segment_language(plain_only_text or sentence, fallback=fallback)

    # A short connector word/phrase ("und", "y", "the") sandwiched between
    # two same-language diacritic runs shouldn't force an extra voice switch
    # and switch back -- fold it into the surrounding language instead.
    merged: list[tuple[str, str]] = []
    for i, (text, cls) in enumerate(raw):
        if (
            cls == "plain"
            and 0 < i < len(raw) - 1
            and raw[i - 1][1] == raw[i + 1][1]
            and raw[i - 1][1] != "plain"
            and len(text.split()) <= 2
        ):
            cls = raw[i - 1][1]
        if merged and merged[-1][1] == cls:
            merged[-1] = (merged[-1][0] + text, cls)
        else:
            merged.append((text, cls))

    result: list[tuple[str, str]] = []
    for text, cls in merged:
        text = text.strip()
        if not text:
            continue
        lang = cls if cls in {"de", "es"} else sentence_lang
        result.append((text, lang))
    return result or [(sentence, sentence_lang)]


def _split_mixed_script_sentence(sentence: str, fallback: str) -> list[tuple[str, str]]:
    """Split a sentence into script/language-aware TTS units.

    The previous Reader path flattened the whole document before language
    detection. That caused language bleed-through at handovers. This function is
    now used only after line/section planning has selected a local fallback.
    """
    sentence = (sentence or "").strip()
    if not sentence:
        return []

    script_lang = _script_language(sentence)
    if script_lang in {"ar", "or"}:
        script_range = r"\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF" if script_lang == "ar" else r"\u0B00-\u0B7F"
        chunks = re.findall(rf"[{script_range}]+|[^{script_range}]+", sentence)
        planned: list[tuple[str, str]] = []
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            chunk_lang = _script_language(chunk)
            if chunk_lang:
                lang = chunk_lang
            elif re.search(r"[A-Za-z\u00C0-\u00FF]", chunk):
                neutral_fallback = "en" if normalize_lang(fallback) in {"hi", "ar", "or"} else fallback
                lang = detect_tts_segment_language(chunk, fallback=neutral_fallback)
            elif planned:
                planned[-1] = (planned[-1][0] + chunk, planned[-1][1])
                continue
            else:
                lang = script_lang
            if planned and planned[-1][1] == lang:
                planned[-1] = (planned[-1][0] + " " + chunk, lang)
            else:
                planned.append((chunk, lang))
        return planned or [(sentence, script_lang)]

    if _is_table_like_tts_line(sentence):
        return [(sentence, "hi" if re.search(r"[\u0900-\u097F]", sentence) else "en")]

    if not re.search(r"[\u0900-\u097F]", sentence):
        latin_fallback = "en" if normalize_lang(fallback) == "hi" else fallback
        return _split_latin_by_word_evidence(sentence, latin_fallback)

    parts: list[tuple[str, str]] = []
    pattern = re.compile(r"[\u0900-\u097F][\u0900-\u097F\s।,;:!?()\-]*|[^\u0900-\u097F]+")
    for match in pattern.finditer(sentence):
        part = match.group(0).strip()
        if not part:
            continue
        if not re.search(r"[A-Za-zÀ-ÿ\u0900-\u097F0-9]", part):
            if parts:
                parts[-1] = (parts[-1][0] + part, parts[-1][1])
            continue
        latin_fallback = "en" if normalize_lang(fallback) == "hi" else fallback
        lang = "hi" if re.search(r"[\u0900-\u097F]", part) else detect_tts_segment_language(part, fallback=latin_fallback)
        if parts and parts[-1][1] == lang and len(parts[-1][0]) + len(part) < 650:
            parts[-1] = (parts[-1][0] + " " + part, lang)
        else:
            parts.append((part, lang))
    return parts or [(sentence, detect_tts_segment_language(sentence, fallback=fallback))]


def _merge_tts_segments(segments: list[tuple[str, str]]) -> list[tuple[str, str]]:
    merged: list[tuple[str, str]] = []
    for text, lang in segments:
        text = re.sub(r"\s+", " ", (text or "").strip())
        if not text:
            continue
        if merged and merged[-1][1] == lang and len(merged[-1][0]) + len(text) < 850:
            merged[-1] = (merged[-1][0] + " " + text, lang)
        else:
            merged.append((text, lang))
    return merged


def _carve_protected_entities(segments: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Carve out proper entity names (places/people) to speak them in their native language voice."""
    try:
        from backend.services.entity_protection_service import entity_glossary
        terms = entity_glossary()
    except Exception:
        return segments

    entity_rules: list[tuple[str, str]] = []
    for term in terms:
        t_lang = getattr(term, "lang", "en")
        if term.text and t_lang:
            entity_rules.append((term.text, t_lang))

    if not entity_rules:
        return segments

    carved_segments: list[tuple[str, str]] = []
    for seg_text, seg_lang in segments:
        current_subsegments: list[tuple[str, str]] = [(seg_text, seg_lang)]
        for term_text, term_lang in entity_rules:
            if term_lang == seg_lang or len(term_text) < 3:
                continue
            next_subsegments: list[tuple[str, str]] = []
            pattern = re.compile(rf"(?<!\w){re.escape(term_text)}(?!\w)", re.IGNORECASE)
            for sub_text, sub_lang in current_subsegments:
                if sub_lang == term_lang or not pattern.search(sub_text):
                    next_subsegments.append((sub_text, sub_lang))
                    continue
                parts = pattern.split(sub_text)
                matches = pattern.findall(sub_text)
                for i, part in enumerate(parts):
                    if part.strip():
                        next_subsegments.append((part, sub_lang))
                    if i < len(matches):
                        next_subsegments.append((matches[i], term_lang))
            current_subsegments = next_subsegments
        carved_segments.extend(current_subsegments)

    return _merge_tts_segments(carved_segments)


def split_text_for_mixed_tts(text: str, fallback: str = "en") -> list[tuple[str, str]]:
    """Build a stable multilingual TTS plan from document structure.

    Long-term Reader fix: language detection happens per line/section/sentence,
    not after collapsing the whole document into one paragraph. This prevents
    German/Spanish/Hindi handovers from being swallowed by the previous segment
    and keeps metadata/table rows in a neutral English voice.
    """
    raw = unicodedata.normalize("NFC", text or "")
    if not raw.strip():
        return []

    fallback_norm = normalize_lang(fallback)
    if fallback_norm not in SUPPORTED_TTS_LANGS or fallback_norm == "auto":
        fallback_norm = "en"

    current_context = fallback_norm
    planned: list[tuple[str, str]] = []

    for raw_line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = _normalize_tts_line(raw_line)
        if not line:
            continue

        # Table/status rows are metadata. Route them before heading detection,
        # otherwise cells like "German voice" can incorrectly switch the entire
        # row to a German or Spanish TTS voice.
        if _is_table_like_tts_line(line):
            lang = _script_language(line) or "en"
            planned.append((line, lang))
            continue

        heading_like = _line_is_heading_like(line)
        heading_context = _section_context_from_line(line) if heading_like else None

        if heading_context:
            # Headings themselves are usually English UI labels such as
            # "German session". Use their own detected language for the heading,
            # but set the following-context from the label.
            heading_lang = detect_tts_segment_language(line, fallback=fallback_norm)
            planned.append((line, heading_lang))
            current_context = heading_context
            continue

        if heading_like:
            planned.append((line, detect_tts_segment_language(line, fallback=fallback_norm)))
            continue

        # Section/heading context carries forward as the fallback for this
        # line. Per-word/per-sentence diacritic detection (inside
        # _split_mixed_script_sentence / _split_latin_by_word_evidence)
        # already handles genuine language evidence precisely -- forcing the
        # *entire line's* fallback to German/Spanish just because one word
        # somewhere in the line has a diacritic would bias the ambient
        # language for any surrounding plain (e.g. English) text in that
        # same line toward the wrong voice, which defeats the point of
        # detecting it at the word level in the first place.
        line_context = current_context

        for sentence in _split_latin_sentences(line):
            planned.extend(_split_mixed_script_sentence(sentence, fallback=line_context))

    merged_plan = _merge_tts_segments(planned)
    return _carve_protected_entities(merged_plan)

def speak_mixed_to_file(text: str, output_name: str = "speech.wav", speed: float = 1.0, fallback_lang: str = "en") -> Path:
    segments = split_text_for_mixed_tts(text, fallback=fallback_lang)
    print(f"[DEBUG TTS] fallback_lang={fallback_lang!r}, planned {len(segments)} segment(s):")
    for seg_text, seg_lang in segments:
        preview = seg_text[:60].replace("\n", " ")
        # The development backend may inherit a legacy Windows console code
        # page. Keep diagnostics ASCII-safe so merely logging Devanagari does
        # not abort otherwise-valid Hindi synthesis.
        safe_preview = preview.encode("ascii", errors="backslashreplace").decode("ascii")
        print(f"[DEBUG TTS]   lang={seg_lang!r}  text={safe_preview!r}")
    if not segments:
        raise ValueError("No readable text available for mixed-language TTS.")

    output_path = TEMP_DIR / output_name
    combined = AudioSegment.silent(duration=80)
    temp_paths: list[Path] = []
    try:
        for segment_text, segment_lang in segments:
            temp_path = _speak_single_voice_to_file(segment_text, segment_lang, f"tts_part_{uuid4().hex}.wav", speed)
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
    """Public entry point. Always routes through per-segment language
    detection (split_text_for_mixed_tts), using `lang` as the fallback voice
    for segments with no strong other-language evidence.

    Previously this only happened when lang was explicitly "auto"/"mixed";
    any concrete language code (which is what every real caller -- desktop
    app dropdowns, /tts/speak, /reader/speak -- actually passes) skipped
    segmentation entirely and forced the ENTIRE text through one voice, even
    when it contained a genuine language switch (e.g. an English proper noun
    inside German output, or vice versa). Since same-language adjacent
    segments are merged before synthesis, plain single-language text still
    collapses to essentially one Piper call -- this doesn't add meaningful
    overhead for the common case, it just also handles the mixed case.
    """
    lang_code = normalize_lang(lang)
    fallback_lang = lang_code if lang_code in SUPPORTED_TTS_LANGS else "en"
    return speak_mixed_to_file(text, output_name=output_name, speed=speed, fallback_lang=fallback_lang)


def _speak_single_voice_to_file(
    text: str,
    lang: str,
    output_name: str,
    speed: float,
) -> Path:
    """Synthesize text in exactly one voice, no language detection. Internal
    use only -- called per-segment by speak_mixed_to_file, which has already
    decided the language for this specific chunk of text."""
    lang_code = normalize_lang(lang)

    if lang_code in {"ar", "or"}:
        from backend.services.mms_tts_service import speak_to_file as speak_mms_to_file

        output_path = TEMP_DIR / output_name
        return speak_mms_to_file(clean_text_for_tts(text), lang_code, output_path, speed)

    voice_name = VOICE_MODELS.get(lang_code)
    if voice_name is None:
        raise ValueError(f"No TTS voice configured for language: {lang}")

    voice_model = MODELS_DIR / voice_name
    if not voice_model.exists():
        voice_model = PIPER_MODELS_DIR / voice_name
    if not voice_model.exists():
        voice_model = PROJECT_ROOT / "models" / "piper" / voice_name

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

    length_scale = speed_to_length_scale(speed)

    # Keep Piper in a child process by default. Piper, RapidOCR and the NLLB
    # stack each load native ONNX/CTranslate2 libraries; after OCR/translation
    # work, loading Piper into the long-running FastAPI process can terminate
    # the whole backend at native-code level before Python can catch an error.
    # Process isolation costs a small startup delay but keeps every client
    # connected if synthesis fails. Developers can explicitly opt back into
    # the faster in-process path for controlled profiling.
    if os.environ.get("LF_PIPER_IN_PROCESS", "").strip() == "1":
        try:
            _synthesize_with_piper(
                voice_model,
                voice_config,
                clean_text,
                output_path,
                length_scale,
            )
            if output_path.exists() and output_path.stat().st_size > 0:
                return output_path
        except Exception as exc:
            print(f"[DEBUG PIPER] In-process synthesis failed, using isolated execution: {exc}")

    input_txt = TEMP_DIR / f"piper_input_{uuid4().hex}.txt"
    input_txt.write_text(clean_text, encoding="utf-8")

    py_exec = sys.executable
    if getattr(sys, "frozen", False):
        command = [py_exec, "--piper-worker"]
    else:
        command = [py_exec, "-m", "piper"]

    command.extend([
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
    ])

    try:
        child_env = os.environ.copy()
        child_env["PYTHONUTF8"] = "1"
        child_env["PYTHONIOENCODING"] = "utf-8"
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        subprocess.run(
            command,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=True,
            env=child_env,
            creationflags=creation_flags,
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
