from __future__ import annotations

"""Entity and proper-noun protection for LinguaFusion quality pipelines.

This layer is intentionally deterministic and offline. It protects terms that
translation engines commonly mistranslate, especially when the Hindi target should
use cohesive Devanagari transliteration instead of mixed Latin script or literal
wrong translations.
"""

from dataclasses import dataclass
import re
from typing import Dict, Iterable, List, Tuple

from backend.services.correction_service import apply_corrections, load_corrections


@dataclass(frozen=True)
class ProtectedTerm:
    text: str
    canonical: str
    kind: str = "entity"


# Default glossary is small but deliberate: local/user entities, app entities,
# and known speech-test/song entities that Argos often mistranslates.
DEFAULT_PROTECTED_TERMS: Tuple[ProtectedTerm, ...] = (
    ProtectedTerm("LinguaFusion", "LinguaFusion", "product"),

    ProtectedTerm("Lingua-Frischen", "LinguaFusion", "product"),
    ProtectedTerm("Lengua-Frischen", "LinguaFusion", "product"),
    ProtectedTerm("Lingua Fusion", "LinguaFusion", "product"),
    ProtectedTerm("Links-Fusion", "LinguaFusion", "product"),
    ProtectedTerm("Link Fusion", "LinguaFusion", "product"),
    ProtectedTerm("Wireless InSite", "Wireless InSite", "tool"),
    ProtectedTerm("wireless insight", "Wireless InSite", "tool"),
    ProtectedTerm("MATLAB", "MATLAB", "tool"),
    ProtectedTerm("Python", "Python", "tool"),
    ProtectedTerm("LiDAR", "LiDAR", "tool"),
    ProtectedTerm("PDP", "PDP", "metric"),
    ProtectedTerm("Pandaprosumer", "Pandaprosumer", "tool"),
    ProtectedTerm("panel presumer", "Pandaprosumer", "tool"),
    ProtectedTerm("panda prosumer", "Pandaprosumer", "tool"),
    ProtectedTerm("Fraunhofer HHI", "Fraunhofer HHI", "organization"),
    ProtectedTerm("fauna for HHI", "Fraunhofer HHI", "organization"),
    ProtectedTerm("Fraunhofer", "Fraunhofer", "organization"),
    ProtectedTerm("HHI", "HHI", "organization"),
    ProtectedTerm("KIT", "KIT", "organization"),
    ProtectedTerm("Karlsruhe Institute of Technology", "Karlsruhe Institute of Technology", "organization"),
    ProtectedTerm("Karlsruher Institut für Technologie", "Karlsruher Institut für Technologie", "organization"),
    ProtectedTerm("Kulturinstitut für Technologie", "Karlsruher Institut für Technologie", "organization"),
    ProtectedTerm("Baden-Württemberg", "Baden-Württemberg", "place"),
    ProtectedTerm("Baden-Wuttenburg", "Baden-Württemberg", "place"),
    ProtectedTerm("Baden-Wurttemberg", "Baden-Württemberg", "place"),
    ProtectedTerm("Baden Wuttenburg", "Baden-Württemberg", "place"),
    ProtectedTerm("Nordrhein-Westfalen", "Nordrhein-Westfalen", "place"),
    ProtectedTerm("Nordrhein Westfalen", "Nordrhein-Westfalen", "place"),
    ProtectedTerm("Rajarshi", "Rajarshi", "person"),
    ProtectedTerm("Raiarshi", "Rajarshi", "person"),
    ProtectedTerm("Rajashi", "Rajarshi", "person"),
    ProtectedTerm("rajashi", "Rajarshi", "person"),
    ProtectedTerm("Mira Arshi", "Rajarshi", "person"),
    ProtectedTerm("Melsungen", "Melsungen", "place"),
    ProtectedTerm("Melzungen", "Melsungen", "place"),
    ProtectedTerm("Melzongren", "Melsungen", "place"),
    ProtectedTerm("Hessen", "Hessen", "place"),
    ProtectedTerm("Germany", "Germany", "place"),
    ProtectedTerm("India", "India", "place"),
    ProtectedTerm("Kolkata", "Kolkata", "place"),
    ProtectedTerm("Pune", "Pune", "place"),
    ProtectedTerm("Asia", "Asia", "place"),
    ProtectedTerm("Europe", "Europe", "place"),
    ProtectedTerm("Pakistan", "Pakistan", "place"),
    ProtectedTerm("Afghanistan", "Afghanistan", "place"),
    ProtectedTerm("Bangladesh", "Bangladesh", "place"),
    ProtectedTerm("Nepal", "Nepal", "place"),
    ProtectedTerm("Bhutan", "Bhutan", "place"),
    ProtectedTerm("Sri Lanka", "Sri Lanka", "place"),
    ProtectedTerm("Narendra Modi", "Narendra Modi", "person"),
    ProtectedTerm("Narendra Modey", "Narendra Modi", "person"),
    ProtectedTerm("Amit Shah", "Amit Shah", "person"),
    ProtectedTerm("Avid Shah", "Amit Shah", "person"),
    ProtectedTerm("Milky Way", "Milky Way", "place"),
    ProtectedTerm("Milky Way galaxy", "Milky Way galaxy", "place"),
    ProtectedTerm("Earth", "Earth", "place"),
    ProtectedTerm("West Virginia", "West Virginia", "place"),
    ProtectedTerm("west virginia", "West Virginia", "place"),
    ProtectedTerm("Country Roads", "Country Roads", "title"),
    ProtectedTerm("country roads", "Country Roads", "title"),
    ProtectedTerm("Take Me Home, Country Roads", "Take Me Home, Country Roads", "title"),
    ProtectedTerm("John Denver", "John Denver", "person"),
    ProtectedTerm("New Delhi", "New Delhi", "place"),
    ProtectedTerm("New Delhim", "New Delhi", "place"),
    ProtectedTerm("Delhi", "Delhi", "place"),
    ProtectedTerm("Blue Ridge Mountains", "Blue Ridge Mountains", "place"),
    ProtectedTerm("Shenandoah River", "Shenandoah River", "place"),
    ProtectedTerm("Mountain Mama", "Mountain Mama", "lyric"),
)

URL_EMAIL_NUMBER_RE = re.compile(
    r"""
    https?://\S+                |  # URLs
    www\.\S+                    |  # www URLs
    [\w\.-]+@[\w\.-]+\.\w+      |  # emails
    \b\d{1,2}:\d{2}\b           |  # times
    \b\d+[.,]?\d*\s?(?:MB|GB|KB|kg|km|cm|mm|%|€|\$|INR)\b
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Conservative titlecase phrase detection. Single capitalized words are not
# protected unless they are in the glossary because they can simply start a sentence.
TITLECASE_PHRASE_RE = re.compile(
    r"\b[A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)?(?:\s+(?:of|the|and|de|da|van|von|[A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)?)){1,5}\b"
)
ACRONYM_RE = re.compile(r"\b[A-Z]{2,8}(?:[-/][A-Z0-9]{2,8})*\b")


def normalize_lang(lang: str) -> str:
    return (lang or "").lower().replace("_", "-").split("-")[0]


def source_quality_normalize(text: str) -> str:
    """Apply approved correction memory before downstream translation/STT display."""
    corrected = apply_corrections(text or "")
    # Preserve casing for known title/song/location phrases. This is case-insensitive,
    # but phrase-aware, so it will not touch partial words.
    for term in DEFAULT_PROTECTED_TERMS:
        if term.text.lower() == term.canonical.lower() and term.text == term.canonical:
            continue
        pattern = re.compile(rf"(?<!\w){re.escape(term.text)}(?!\w)", re.IGNORECASE)
        corrected = pattern.sub(term.canonical, corrected)
    return re.sub(r"\s+", " ", corrected).strip()


def _correction_terms() -> List[ProtectedTerm]:
    terms: List[ProtectedTerm] = []
    try:
        corrections = load_corrections()
    except Exception:
        return terms
    for wrong, correct in corrections.items():
        wrong = str(wrong).strip()
        correct = str(correct).strip()
        if not wrong or not correct:
            continue
        # Protect user-approved corrected entities and common phrase corrections.
        if re.search(r"[A-Z][a-z]|[ÄÖÜäöüß]|\s|[-']", correct):
            terms.append(ProtectedTerm(wrong, correct, "correction"))
            terms.append(ProtectedTerm(correct, correct, "correction"))
    return terms


def entity_glossary() -> List[ProtectedTerm]:
    dedup: Dict[str, ProtectedTerm] = {}
    for term in list(DEFAULT_PROTECTED_TERMS) + _correction_terms():
        key = term.text.lower()
        # Prefer explicit defaults over correction duplicates, but keep longer terms.
        if key not in dedup or len(term.text) > len(dedup[key].text):
            dedup[key] = term
    return sorted(dedup.values(), key=lambda item: len(item.text), reverse=True)


def _placeholder(index: int) -> str:
    # Numeric placeholders are least likely to be translated by offline NMT engines.
    return f"999770{index:03d}077999"


def _restore_placeholder_variants(text: str, key: str, value: str) -> str:
    restored = text
    variants = {
        key,
        key.lower(),
        key.upper(),
        f" {key} ",
        " ".join(key),
        key.replace("999", " 999 "),
        key.replace("077", " 077 "),
    }
    compact_pattern = re.compile(r"\s*".join(map(re.escape, key)))
    variants.add(compact_pattern.sub("", key))
    for variant in sorted(variants, key=len, reverse=True):
        if variant:
            restored = restored.replace(variant, value)
    # Regex fallback for arbitrary spaces inserted between digits.
    spaced = r"\s*".join(re.escape(ch) for ch in key)
    restored = re.sub(spaced, value, restored)
    return restored


def protect_for_translation(text: str, source_lang: str = "auto", target_lang: str = "de") -> Tuple[str, Dict[str, str], List[Dict[str, str]]]:
    """Protect non-translatable tokens and, for Hindi target, proper nouns.

    Returns protected text, placeholder map, and structured metadata.
    """
    source = source_quality_normalize(text or "")
    target = normalize_lang(target_lang)
    placeholders: Dict[str, str] = {}
    metadata: List[Dict[str, str]] = []
    occupied: List[Tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(not (end <= s or start >= e) for s, e in occupied)

    matches: List[Tuple[int, int, str, str, str]] = []

    for match in URL_EMAIL_NUMBER_RE.finditer(source):
        matches.append((match.start(), match.end(), match.group(0), match.group(0), "literal"))

    if target == "hi":
        # Protect explicit known/user terms first.
        for term in entity_glossary():
            if not term.text:
                continue
            pattern = re.compile(rf"(?<!\w){re.escape(term.text)}(?!\w)", re.IGNORECASE)
            for match in pattern.finditer(source):
                matches.append((match.start(), match.end(), match.group(0), term.canonical, term.kind))

        # Then protect titlecase multi-word names and acronyms.
        for pattern, kind in [(TITLECASE_PHRASE_RE, "proper_noun"), (ACRONYM_RE, "acronym")]:
            for match in pattern.finditer(source):
                value = match.group(0)
                if len(value.strip()) >= 2:
                    matches.append((match.start(), match.end(), value, value, kind))

    # Resolve overlapping matches by longest span first.
    selected: List[Tuple[int, int, str, str, str]] = []
    for start, end, original, canonical, kind in sorted(matches, key=lambda m: (-(m[1] - m[0]), m[0])):
        if overlaps(start, end):
            continue
        occupied.append((start, end))
        selected.append((start, end, original, canonical, kind))

    selected.sort(key=lambda m: m[0])
    pieces: List[str] = []
    cursor = 0
    for idx, (start, end, original, canonical, kind) in enumerate(selected):
        pieces.append(source[cursor:start])
        key = _placeholder(idx)
        placeholders[key] = canonical
        metadata.append({"placeholder": key, "original": original, "canonical": canonical, "kind": kind})
        pieces.append(f" {key} ")
        cursor = end
    pieces.append(source[cursor:])

    protected = re.sub(r"\s+", " ", "".join(pieces)).strip()
    return protected, placeholders, metadata


def restore_protected_terms(text: str, placeholders: Dict[str, str]) -> str:
    restored = text or ""
    for key, value in placeholders.items():
        restored = _restore_placeholder_variants(restored, key, value)
    restored = re.sub(r"\s+([,.;:!?])", r"\1", restored)
    restored = re.sub(r"([,.;:!?])(?=\S)", r"\1 ", restored)
    restored = re.sub(r"\s+", " ", restored)
    return restored.strip()
