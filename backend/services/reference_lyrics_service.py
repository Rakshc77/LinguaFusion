"""Reference-assisted lyrics alignment for LinguaFusion.

This module does not fetch lyrics from the internet. It only uses user-supplied
reference text. That avoids licensing/copyright problems and gives the app a
safe way to produce an accurate lyrics transcript when the user has a legitimate
reference.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Dict, List

from backend.services.music_lyrics_service import refine_lyrics_transcript
from backend.services.correction_service import apply_corrections


def normalize_reference_lyrics(text: str) -> str:
    text = text or ""
    text = text.replace("\ufeff", "")
    lines: List[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Drop common section labels, but keep real lyric content.
        if re.fullmatch(r"\[?(verse|chorus|bridge|intro|outro|hook|pre-chorus|refrain)\s*\d*\]?", line, re.IGNORECASE):
            continue
        line = re.sub(r"\s+", " ", line)
        lines.append(line)
    if not lines:
        compact = re.sub(r"\s+", " ", text).strip()
        return compact
    return "\n".join(lines).strip()


def _tokens(text: str) -> List[str]:
    return re.findall(r"[A-Za-zÀ-ÿ0-9']+", (text or "").lower())


def similarity(a: str, b: str) -> float:
    a_tokens = _tokens(a)
    b_tokens = _tokens(b)
    if not a_tokens or not b_tokens:
        return 0.0
    return SequenceMatcher(None, " ".join(a_tokens), " ".join(b_tokens)).ratio()


def reference_assisted_lyrics(asr_text: str, reference_text: str) -> Dict[str, object]:
    """Return a safe final lyrics transcript using a user-supplied reference.

    If the ASR and reference are reasonably similar, the reference becomes the
    final transcript. If they are too different, we keep the ASR and report that
    the reference was not trusted.
    """
    cleaned_asr = refine_lyrics_transcript(apply_corrections(asr_text or ""))
    reference = normalize_reference_lyrics(reference_text)
    sim = similarity(cleaned_asr, reference)

    # Songs with weak ASR may have modest similarity, so threshold is deliberately
    # not too high. But it still prevents a completely unrelated pasted lyric from
    # replacing the transcript.
    accepted = bool(reference and (sim >= 0.18 or len(_tokens(cleaned_asr)) < 20))
    final_text = reference if accepted else cleaned_asr

    return {
        "ok": bool(final_text),
        "text": final_text,
        "raw_text": asr_text or "",
        "offline_text": cleaned_asr,
        "reference_text": reference,
        "reference_similarity": round(sim, 3),
        "reference_accepted": accepted,
        "provider": "reference_lyrics" if accepted else "offline_lfie_reference_rejected",
        "engine": "lfie_v1_reference_lyrics",
        "error": None if final_text else "No usable transcript/reference text available.",
    }
