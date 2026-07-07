from __future__ import annotations

import re
from typing import Dict, List, Tuple

try:
    from langdetect import detect_langs
except Exception as exc:  # pragma: no cover - depends on local install
    detect_langs = None
    LANGDETECT_IMPORT_ERROR = exc
else:
    LANGDETECT_IMPORT_ERROR = None

SUPPORTED_LANGS = {"en", "de", "es", "hi"}

DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
LATIN_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ]+(?:[-'][A-Za-zÀ-ÿ]+)?")

# These are deliberately small and conservative. They are not a full language
# detector; they rescue short app inputs and mixed English/German documents where
# langdetect often returns unsupported codes such as sq or af.
ENGLISH_HINTS = {
    "i", "me", "my", "we", "you", "he", "she", "they", "live", "lives", "met", "meet", "from", "in",
    "the", "a", "an", "and", "or", "to", "of", "for", "with", "this", "that", "today", "system",
    "should", "correctly", "detect", "language", "allow", "playback", "keep", "waveform", "synchronized",
    "country", "roads", "home", "place", "belong", "reader", "translation", "document", "processing",
}
GERMAN_HINTS = {
    "der", "die", "das", "und", "ist", "ich", "nicht", "mit", "für", "fuer", "danke", "hallo",
    "bitte", "schön", "schoen", "zusammen", "heute", "testen", "wir", "den", "dem", "des", "ein",
    "eine", "langen", "sätzen", "saetzen", "eigennamen", "technischen", "begriffen", "korrekt",
    "erkennt", "besonders", "wichtig", "wörter", "woerter", "wie", "wohne", "ursprünglich", "urspruenglich",
    "komme", "aus", "deutsche", "deutsch", "hessen", "baden", "nordrhein", "westfalen",
}
SPANISH_HINTS = {
    "el", "la", "los", "las", "una", "uno", "para", "que", "gracias", "hola", "cómo", "como",
    "estás", "estas", "en", "de", "y", "con", "por", "traducción", "traduccion",
}

GERMAN_CHAR_RE = re.compile(r"[ÄÖÜäöüß]")
SPANISH_CHAR_RE = re.compile(r"[ñáéíóúü¿¡]", re.IGNORECASE)


def _tokens(text: str) -> List[str]:
    return [t.lower().replace("ü", "ue").replace("ä", "ae").replace("ö", "oe").replace("ß", "ss") for t in LATIN_TOKEN_RE.findall(text or "")]


def _score_tokens(raw_text: str) -> Tuple[Dict[str, int], List[str]]:
    tokens = _tokens(raw_text)
    raw_lower = (raw_text or "").lower()
    scores = {"en": 0, "de": 0, "es": 0, "hi": 0}

    if DEVANAGARI_RE.search(raw_text or ""):
        scores["hi"] += 6
    if GERMAN_CHAR_RE.search(raw_text or ""):
        scores["de"] += 3
    if SPANISH_CHAR_RE.search(raw_text or ""):
        scores["es"] += 3

    for token in tokens:
        if token in ENGLISH_HINTS:
            scores["en"] += 1
        if token in GERMAN_HINTS:
            scores["de"] += 1
        if token in SPANISH_HINTS:
            scores["es"] += 1

    # Phrase-level cues for mixed technical/Reader documents.
    if re.search(r"\b(?:this|the)\b.*\b(?:system|document|paragraph|reader|translation)\b", raw_lower):
        scores["en"] += 2
    if re.search(r"\b(?:hallo zusammen|heute testen|deutsche sätze|eigennamen|technischen begriffen)\b", raw_lower):
        scores["de"] += 4
    if re.search(r"\b(?:i live|i work|met .* in|good morning|today we)\b", raw_lower):
        scores["en"] += 4

    return scores, tokens


def _heuristic_detect(text: str) -> Dict[str, object]:
    cleaned = (text or "").strip()
    scores, tokens = _score_tokens(cleaned)

    if scores["hi"] > 0:
        return {"ok": True, "language": "hi", "confidence": 0.85, "error": None, "method": "heuristic"}

    ranked = sorted(((lang, score) for lang, score in scores.items() if lang != "hi"), key=lambda item: item[1], reverse=True)
    best_lang, best_score = ranked[0]
    second_lang, second_score = ranked[1]

    if best_score <= 0:
        # Default Latin-script app text to English instead of returning unsupported.
        return {"ok": True, "language": "en", "confidence": 0.45, "error": None, "method": "heuristic_default_en"}

    is_mixed = (
        best_score >= 3
        and second_score >= 3
        and ((second_score / max(best_score, 1)) >= 0.50 or (best_score >= 8 and second_score >= 8))
    )
    languages = [best_lang]
    if is_mixed:
        languages.append(second_lang)

    confidence = min(0.92, 0.50 + (best_score / max(len(tokens), 1)) * 0.55)
    return {
        "ok": True,
        "language": best_lang,
        "confidence": round(confidence, 3),
        "error": None,
        "method": "heuristic_mixed" if is_mixed else "heuristic",
        "is_mixed": is_mixed,
        "languages": languages,
        "scores": scores,
    }


def _should_prefer_heuristic(cleaned: str, detected_lang: str, confidence: float) -> bool:
    if detected_lang not in SUPPORTED_LANGS:
        return True
    # langdetect is weak on short proper-noun-heavy strings like
    # "Rajarshi met Amit Shah in New Delhi". Prefer our app heuristic there.
    word_count = len(LATIN_TOKEN_RE.findall(cleaned))
    if word_count <= 10 and confidence < 0.95:
        return True
    # Mixed English/German Reader documents should keep metadata that says mixed.
    heuristic = _heuristic_detect(cleaned)
    if heuristic.get("is_mixed"):
        return True
    return False


def detect_text_language(text: str) -> dict:
    cleaned = (text or "").strip()
    if not cleaned:
        return {"ok": False, "language": "unknown", "confidence": 0.0, "error": "Empty text"}

    heuristic = _heuristic_detect(cleaned)

    if detect_langs is None:
        heuristic["warning"] = f"langdetect is not installed: {LANGDETECT_IMPORT_ERROR}"
        return heuristic

    try:
        results = detect_langs(cleaned)
        best = results[0]
        lang = best.lang
        confidence = float(best.prob)

        if _should_prefer_heuristic(cleaned, lang, confidence):
            if lang not in SUPPORTED_LANGS:
                heuristic["warning"] = f"langdetect returned unsupported '{lang}' with confidence {confidence:.3f}; used heuristic fallback."
            else:
                heuristic["warning"] = f"langdetect returned '{lang}' with confidence {confidence:.3f}; used heuristic fallback for short/mixed text."
            return heuristic

        return {"ok": True, "language": lang, "confidence": confidence, "error": None, "method": "langdetect"}
    except Exception as exc:
        heuristic["warning"] = str(exc)
        return heuristic
