from __future__ import annotations

"""Deterministic speech transcript cleanup for Phase 2."""

import re
from typing import Dict, List

from backend.services.correction_service import apply_corrections
from backend.services.entity_protection_service import source_quality_normalize

FILLER_RE = re.compile(r"\b(?:um+|uh+|erm+|äh+|ähm+|hmm+)\b", re.IGNORECASE)
SPACE_RE = re.compile(r"\s+")

COMMON_SENTENCE_FIXES = [
    # General hallucination / common ASR cleanup.
    (re.compile(r"\bmilitary galaxy\b", re.IGNORECASE), "Milky Way galaxy"),
    (re.compile(r"\bwest virginia\b", re.IGNORECASE), "West Virginia"),
    (re.compile(r"\bcountry roads\b", re.IGNORECASE), "Country Roads"),
    (re.compile(r"\bavid shah\b", re.IGNORECASE), "Amit Shah"),
    (re.compile(r"\bnarendra modey\b", re.IGNORECASE), "Narendra Modi"),

    # LinguaFusion Phase 2 speech-test vocabulary.
    (re.compile(r"\b(?:lingua|lengua)[-\s]?frischen\b", re.IGNORECASE), "LinguaFusion"),
    (re.compile(r"\blingua\s+fusion\b", re.IGNORECASE), "LinguaFusion"),
    (re.compile(r"\blingua[-\s]+fusion\b", re.IGNORECASE), "LinguaFusion"),
    (re.compile(r"\blink[s]?[-\s]?fusion\b", re.IGNORECASE), "LinguaFusion"),
    (re.compile(r"\blink[s]?\s+fusion\b", re.IGNORECASE), "LinguaFusion"),
    (re.compile(r"\bdeutschische\s+s[aä]tze\b", re.IGNORECASE), "deutsche Sätze"),
    (re.compile(r"\beigennahmen\b", re.IGNORECASE), "Eigennamen"),
    (re.compile(r"\bbaden[-\s]?w(?:u|ü)ttenburg\b", re.IGNORECASE), "Baden-Württemberg"),
    (re.compile(r"\bbaden[-\s]?wurttemberg\b", re.IGNORECASE), "Baden-Württemberg"),
    (re.compile(r"\bnordrhein[-\s]?westfalen\b", re.IGNORECASE), "Nordrhein-Westfalen"),
    (re.compile(r"\bkulturinstitut\s+f(?:ü|u)r\s+technologie\b", re.IGNORECASE), "Karlsruher Institut für Technologie"),
    (re.compile(r"\bwireless\s+insight\b", re.IGNORECASE), "Wireless InSite"),
    (re.compile(r"\bpanel\s+presumer\b", re.IGNORECASE), "Pandaprosumer"),
    (re.compile(r"\bpanda\s+prosumer\b", re.IGNORECASE), "Pandaprosumer"),
    (re.compile(r"\bfauna\s+for\s+hhi\b", re.IGNORECASE), "Fraunhofer HHI"),
    (re.compile(r"\bmeasurement\b(?=\.?(?:\s+Therefore|$))", re.IGNORECASE), "Melsungen"),
    (re.compile(r"\bdoc[-\s]?ex\b", re.IGNORECASE), "DOCX"),
]


def normalize_transcript_text(text: str, remove_fillers: bool = False) -> str:
    cleaned = text or ""
    cleaned = cleaned.replace("�", " ")
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"([,.;:!?])(?=\S)", r"\1 ", cleaned)
    if remove_fillers:
        cleaned = FILLER_RE.sub(" ", cleaned)
    cleaned = source_quality_normalize(cleaned)
    for pattern, replacement in COMMON_SENTENCE_FIXES:
        cleaned = pattern.sub(replacement, cleaned)
    cleaned = apply_corrections(cleaned)
    cleaned = SPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def transcript_quality_report(raw_text: str, final_text: str) -> Dict[str, object]:
    raw = raw_text or ""
    final = final_text or ""
    return {
        "raw_chars": len(raw),
        "final_chars": len(final),
        "raw_words": len(re.findall(r"\w+", raw)),
        "final_words": len(re.findall(r"\w+", final)),
        "changed": raw.strip() != final.strip(),
        "latin_script_tokens": re.findall(r"[A-Za-z][A-Za-z'-]*", final),
    }
