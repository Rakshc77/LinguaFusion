"""LinguaFusion Intelligence Engine (LFIE)

A single backend layer for speech/music transcription quality control:
- candidate generation
- offline correction memory
- lyrics/proper-noun cleanup
- optional free online reviewers
- candidate scoring and safe selection

This module intentionally does not store API keys and does not silently learn
corrections. Learning remains user-approved through correction_service.py.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Dict, List, Iterable

from pydub import AudioSegment

from backend.services.whisper_service import transcribe_audio
from backend.services.correction_service import apply_corrections
from backend.services.speech_quality_service import normalize_transcript_text, transcript_quality_report
from backend.services.free_online_correction_service import compare_online_corrections, smart_correct_text, provider_status
from backend.services.music_lyrics_service import refine_lyrics_transcript, choose_best_candidate, score_candidate, reject_bad_candidate


def _candidate(provider: str, text: str, ok: bool = True, error: str | None = None, **extra) -> Dict[str, object]:
    return {"provider": provider, "ok": ok, "text": text or "", "error": error, **extra}


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text or ""))


def _meaningful(text: str) -> bool:
    lower = (text or "").lower()
    if not text or len(text.strip()) < 5:
        return False
    if any(term in lower for term in ["load_backend", "input file not found", "whisper_", "ggml_", "read_audio_data"]):
        return False
    return True


def _music_language(language: str) -> str:
    lang = (language or "auto").lower().replace("_", "-").split("-")[0]
    # Music mode is currently optimized for English songs. Whisper often misclassifies sung English as German.
    if lang in {"", "auto", "de", "german"}:
        return "en"
    if lang in {"en", "english"}:
        return "en"
    return lang


def _chunk_audio(audio_path: Path, chunk_ms: int = 25000, overlap_ms: int = 4000) -> List[Path]:
    audio = AudioSegment.from_file(str(audio_path)).set_channels(1).set_frame_rate(16000)
    if len(audio) <= chunk_ms + 6000:
        return [Path(audio_path)]
    temp_dir = Path(tempfile.mkdtemp(prefix="lfie_song_chunks_"))
    chunks: List[Path] = []
    start = 0
    idx = 0
    while start < len(audio):
        end = min(len(audio), start + chunk_ms)
        segment = audio[start:end]
        if len(segment) >= 7000:
            out = temp_dir / f"chunk_{idx:03d}.wav"
            segment.export(str(out), format="wav")
            chunks.append(out)
        if end >= len(audio):
            break
        start = max(0, end - overlap_ms)
        idx += 1
    return chunks or [Path(audio_path)]


def _merge_chunk_texts(texts: Iterable[str]) -> str:
    # Preserve the chronological order first, then only remove exact pathological duplication.
    pieces: List[str] = []
    for text in texts:
        refined = refine_lyrics_transcript(text, preserve_repeats=True)
        if not refined:
            continue
        pieces.append(refined)
    merged = " ".join(pieces)
    return refine_lyrics_transcript(merged, preserve_repeats=False)


def _whisper_music_candidates(audio_path: Path, language: str) -> Dict[str, object]:
    music_language = _music_language(language)
    chunks = _chunk_audio(Path(audio_path))
    chunk_texts: List[str] = []
    chunk_info: List[Dict[str, object]] = []

    # Candidate A: whole-file pass. For some songs this is better than chunking.
    full = transcribe_audio(Path(audio_path), music_language)
    candidates: List[Dict[str, object]] = []
    if full.get("ok") and full.get("text"):
        candidates.append(_candidate("whisper_full", refine_lyrics_transcript(full.get("text", "")), model=full.get("model")))

    # Candidate B: chunked pass. This usually catches middle/end sections better.
    for idx, chunk_path in enumerate(chunks):
        result = transcribe_audio(chunk_path, music_language)
        text = result.get("text", "") or ""
        chunk_info.append({
            "chunk": idx,
            "path": str(chunk_path),
            "ok": result.get("ok", False),
            "text": text[:1000],
            "error": result.get("error"),
            "language": result.get("language", music_language),
            "model": result.get("model"),
        })
        if result.get("ok") and text:
            chunk_texts.append(text)

    merged = _merge_chunk_texts(chunk_texts)
    if merged:
        candidates.append(_candidate("whisper_chunked", merged, chunk_count=len(chunks)))

    # Candidate C: combined full + chunked, often best when the full pass catches the opening and chunks catch later sections.
    combined_source = " ".join([str(c.get("text", "")) for c in candidates])
    combined = refine_lyrics_transcript(combined_source)
    if combined:
        candidates.append(_candidate("whisper_combined", combined, chunk_count=len(chunks)))

    best_offline = choose_best_candidate(candidates)
    return {
        "ok": bool(best_offline.get("text")),
        "language": music_language,
        "model": full.get("model") if isinstance(full, dict) else None,
        "text": best_offline.get("text", ""),
        "provider": best_offline.get("provider", "whisper_combined"),
        "candidates": candidates,
        "chunks": chunk_info,
        "chunk_count": len(chunks),
        "error": None if best_offline.get("text") else "No usable lyric text found.",
    }


def _online_candidates_for_music(text: str, language: str, smart_mode: str) -> List[Dict[str, object]]:
    if (smart_mode or "offline").lower() in {"offline", "none", ""}:
        return []
    status = provider_status()
    # If no semantic provider is configured, LanguageTool alone is not enough for lyric semantics.
    comparison = compare_online_corrections(text, language)
    candidates: List[Dict[str, object]] = []
    for c in comparison.get("candidates", []):
        provider = str(c.get("provider", "online"))
        candidate_text = c.get("text", "") or ""
        if not candidate_text:
            continue
        refined = refine_lyrics_transcript(candidate_text)
        if refined and not reject_bad_candidate(refined):
            candidates.append(_candidate(provider, refined, bool(c.get("ok", True)), c.get("error")))
    return candidates


def transcribe_with_lfie(
    audio_path: Path,
    language: str = "auto",
    smart_mode: str = "offline",
    music_mode: bool = False,
) -> Dict[str, object]:
    smart_mode = (smart_mode or "offline").lower().strip()
    if music_mode:
        whisper_pack = _whisper_music_candidates(audio_path, language)
        if not whisper_pack.get("ok"):
            return whisper_pack
        raw_text = str(whisper_pack.get("text", ""))
        language = str(whisper_pack.get("language", "en") or "en")
        offline_text = refine_lyrics_transcript(normalize_transcript_text(raw_text))
        candidates: List[Dict[str, object]] = list(whisper_pack.get("candidates", []))
        candidates.append(_candidate("offline_lfie", offline_text))
        baseline_words = max(_word_count(offline_text), 1)
        for c in _online_candidates_for_music(offline_text, language, smart_mode):
            candidates.append(c)
        best = choose_best_candidate(candidates, baseline_words=baseline_words)
        final_text = str(best.get("text", offline_text) or offline_text)
        # Absolute safety: never allow online output to shrink a full song to a small fragment.
        if _word_count(final_text) < max(25, int(baseline_words * 0.55)):
            final_text = offline_text
            best = _candidate("offline_lfie_length_guard", offline_text)
            best["score"] = score_candidate(offline_text)
        final_text = refine_lyrics_transcript(normalize_transcript_text(final_text))
        return {
            "ok": True,
            "text": final_text,
            "raw_text": raw_text,
            "offline_text": offline_text,
            "language": language,
            "model": whisper_pack.get("model"),
            "provider": best.get("provider", "offline_lfie"),
            "engine": "lfie_v1_music",
            "music_mode": True,
            "corrections_applied": final_text != raw_text,
            "quality": transcript_quality_report(raw_text, final_text),
            "chunk_count": whisper_pack.get("chunk_count"),
            "chunks": whisper_pack.get("chunks", []),
            "provider_status": provider_status(),
            "candidates": [
                {
                    "provider": c.get("provider"),
                    "ok": c.get("ok", True),
                    "score": c.get("score", score_candidate(str(c.get("text", ""))) if c.get("text") else None),
                    "words": _word_count(str(c.get("text", ""))),
                    "text": str(c.get("text", ""))[:1600],
                    "error": c.get("error"),
                }
                for c in candidates
            ],
        }

    # Normal speech path: use Whisper + offline corrections + optional smart text correction.
    whisper_result = transcribe_audio(Path(audio_path), language)
    if not whisper_result.get("ok"):
        return whisper_result
    raw_text = str(whisper_result.get("text", "") or "")
    offline_text = normalize_transcript_text(raw_text)
    candidates: List[Dict[str, object]] = [_candidate("whisper_raw", raw_text), _candidate("offline_lfie", offline_text)]
    if smart_mode not in {"offline", "none", ""}:
        smart = smart_correct_text(offline_text, smart_mode, str(whisper_result.get("language", language)))
        if smart.get("text"):
            candidates.append(_candidate(str(smart.get("provider", "smart")), smart.get("text", ""), bool(smart.get("ok", True)), smart.get("error")))
    valid = [c for c in candidates if _meaningful(str(c.get("text", "")))]
    best = valid[-1] if valid else _candidate("offline_lfie", offline_text)
    final_text = normalize_transcript_text(str(best.get("text", offline_text)))
    return {
        "ok": True,
        "text": final_text,
        "raw_text": raw_text,
        "offline_text": offline_text,
        "language": whisper_result.get("language", language),
        "model": whisper_result.get("model"),
        "provider": best.get("provider", "offline_lfie"),
        "engine": "lfie_v1_speech",
        "music_mode": False,
        "corrections_applied": final_text != raw_text,
        "quality": transcript_quality_report(raw_text, final_text),
        "provider_status": provider_status(),
        "candidates": [
            {"provider": c.get("provider"), "ok": c.get("ok", True), "text": str(c.get("text", ""))[:1600], "error": c.get("error")}
            for c in candidates
        ],
    }
