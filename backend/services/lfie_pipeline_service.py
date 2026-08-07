
from __future__ import annotations

"""LinguaFusion Intelligence Engine (LFIE) shared pipeline layer.

This module provides the central quality, entity, routing and consensus logic
used across speech, OCR, reader, translation and notes workflows. It is fully
local and deterministic by default. Optional online providers are only reported
through capability metadata; this layer does not call remote services directly.
"""

from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Sequence
import json
import math
import re

from backend.services.correction_service import load_corrections
from backend.services.entity_protection_service import entity_glossary, source_quality_normalize
from backend.services.language_service import detect_text_language
from backend.services.free_online_correction_service import provider_status
from backend.services.translation_service import translate_with_views

SUPPORTED_WORKFLOWS = {"speech", "ocr", "reader", "translation", "notes", "search", "generic"}
SUPPORTED_LANGS = {"en", "de", "es", "hi", "ar", "or", "auto", "unknown"}
DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
ODIA_RE = re.compile(r"[\u0B00-\u0B7F]")
LATIN_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9_+./-]*\b")
TOKEN_RE = re.compile(r"[\w\u0900-\u097F\u0600-\u06FF\u0B00-\u0B7F]+", re.UNICODE)
BLACK_BOX_RE = re.compile(r"[■□�]{2,}")
TABLE_PIPE_RE = re.compile(r"\|.*\|")
NUMBER_UNIT_RE = re.compile(r"\b-?\d+(?:[.,]\d+)?\s?(?:EUR|€|USD|INR|dBm|GHz|MHz|ns|ms|kg|bar|%|pcs|min)\b", re.I)
ACRONYM_RE = re.compile(r"\b[A-Z]{2,}(?:[-/][A-Z0-9]{2,})*\b")
TITLE_PHRASE_RE = re.compile(r"\b[A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)?(?:\s+(?:of|the|and|de|da|van|von|[A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)?)){1,5}\b")
REPEATED_SUBSTRING_RE = re.compile(r"(.{4,40}?)\1{2,}", re.S)


@dataclass
class LFIESignal:
    name: str
    severity: str
    message: str
    value: Any = None


@dataclass
class LFIEEntity:
    text: str
    canonical: str
    kind: str
    source: str


def _normalize_workflow(workflow: str) -> str:
    wf = (workflow or "generic").lower().strip()
    return wf if wf in SUPPORTED_WORKFLOWS else "generic"


def _word_count(text: str) -> int:
    return len(TOKEN_RE.findall(text or ""))


def _line_count(text: str) -> int:
    return len([line for line in (text or "").splitlines() if line.strip()])


def _paragraph_count(text: str) -> int:
    return len([p for p in re.split(r"\n\s*\n", text or "") if p.strip()])


def _sentence_count(text: str) -> int:
    pieces = re.split(r"(?<=[.!?।])\s+", (text or "").strip())
    return len([p for p in pieces if p.strip()])


def _repeated_token_ratio(text: str) -> float:
    words = [w.lower() for w in TOKEN_RE.findall(text or "")]
    if not words:
        return 0.0
    counts: Dict[str, int] = {}
    for word in words:
        counts[word] = counts.get(word, 0) + 1
    return max(counts.values()) / max(len(words), 1)




def _repeated_substring_ratio(text: str) -> float:
    value = re.sub(r"\s+", "", text or "").lower()
    if len(value) < 24:
        return 0.0
    match = REPEATED_SUBSTRING_RE.search(value)
    if match:
        return min(1.0, len(match.group(0)) / max(len(value), 1))
    # Catch single long tokens made from a smaller repeated unit, e.g.
    # mainstreammainstreammainstream.
    for unit_len in range(3, min(30, len(value) // 2) + 1):
        unit = value[:unit_len]
        if len(set(unit)) <= 1:
            continue
        repeats = len(value) // unit_len
        if repeats >= 3 and unit * repeats == value[: unit_len * repeats]:
            return (unit_len * repeats) / max(len(value), 1)
    return 0.0


def _fragmented_line_count(text: str) -> int:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if len(lines) < 4:
        return 0
    count = 0
    for line in lines:
        letters = len(re.findall(r"[A-Za-z]", line))
        words = _word_count(line)
        if len(line) <= 3 or (words <= 1 and len(line) <= 12) or (words <= 2 and letters <= 10):
            count += 1
    return count


def _script_profile(text: str) -> Dict[str, Any]:
    value = text or ""
    latin = len(re.findall(r"[A-Za-z]", value))
    devanagari = len(DEVANAGARI_RE.findall(value))
    arabic = len(ARABIC_RE.findall(value))
    odia = len(ODIA_RE.findall(value))
    digits = len(re.findall(r"\d", value))
    other_letters = len(re.findall(r"[^\W\d_A-Za-z\u0900-\u097F\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\u0B00-\u0B7F]", value, re.UNICODE))
    script_counts = {"latin": latin, "devanagari": devanagari, "arabic": arabic, "odia": odia}
    total_letters = max(sum(script_counts.values()) + other_letters, 1)
    dominant_name, dominant_count = max(script_counts.items(), key=lambda item: item[1])
    return {
        "latin_chars": latin,
        "devanagari_chars": devanagari,
        "arabic_chars": arabic,
        "odia_chars": odia,
        "digit_chars": digits,
        "other_letter_chars": other_letters,
        "dominant_script": dominant_name if dominant_count / total_letters > 0.35 else "mixed",
        "mixed_script": sum(1 for count in script_counts.values() if count > 0) > 1,
    }


def resolve_entities(text: str, workflow: str = "generic") -> Dict[str, Any]:
    """Detect known entities, acronyms and protected document values."""
    value = source_quality_normalize(text or "")
    entities: List[LFIEEntity] = []
    occupied: List[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(not (end <= a or start >= b) for a, b in occupied)

    # Known glossary and user correction terms.
    matches: List[tuple[int, int, str, str, str, str]] = []
    for term in entity_glossary():
        if not term.text:
            continue
        pattern = re.compile(rf"(?<!\w){re.escape(term.text)}(?!\w)", re.I)
        for m in pattern.finditer(value):
            matches.append((m.start(), m.end(), m.group(0), term.canonical, term.kind, "glossary"))

    for pattern, kind, source in [
        (NUMBER_UNIT_RE, "value", "value_detector"),
        (ACRONYM_RE, "acronym", "pattern"),
        (TITLE_PHRASE_RE, "proper_noun", "pattern"),
    ]:
        for m in pattern.finditer(value):
            matches.append((m.start(), m.end(), m.group(0), m.group(0), kind, source))

    def _match_priority(item):
        start, end, original, canonical, kind, source = item
        source_priority = {"glossary": 0, "value_detector": 1, "pattern": 2}.get(source, 3)
        return (source_priority, start, -(end - start))

    for start, end, original, canonical, kind, source in sorted(matches, key=_match_priority):
        if overlaps(start, end):
            continue
        occupied.append((start, end))
        entities.append(LFIEEntity(original, canonical, kind, source))

    return {
        "ok": True,
        "workflow": _normalize_workflow(workflow),
        "normalized_text_changed": value != (text or "").strip(),
        "entities": [asdict(e) for e in entities],
        "entity_count": len(entities),
    }


def confidence_report(text: str, workflow: str = "generic", detected_language: Dict[str, Any] | None = None) -> Dict[str, Any]:
    workflow = _normalize_workflow(workflow)
    value = text or ""
    signals: List[LFIESignal] = []
    score = 1.0

    if not value.strip():
        signals.append(LFIESignal("empty_text", "error", "No usable text was provided."))
        score -= 0.8

    wc = _word_count(value)
    if wc < 3:
        signals.append(LFIESignal("short_text", "warning", "Text is too short for reliable language/quality decisions.", wc))
        score -= 0.15

    if BLACK_BOX_RE.search(value):
        signals.append(LFIESignal("replacement_glyphs", "error", "Text contains replacement/black-box glyphs.", True))
        score -= 0.45

    repeated = _repeated_token_ratio(value)
    repeated_substring = _repeated_substring_ratio(value)
    if repeated > 0.45 and wc >= 5:
        signals.append(LFIESignal("repetition", "warning", "Output may contain repeated tokens.", round(repeated, 3)))
        score -= 0.35
    if repeated_substring > 0.45:
        signals.append(LFIESignal("repeated_substring", "error", "Output contains a repeated substring pattern.", round(repeated_substring, 3)))
        score -= 0.55

    one_char_lines = sum(1 for line in value.splitlines() if len(line.strip()) == 1)
    fragmented_lines = _fragmented_line_count(value)
    words_for_fragment_check = TOKEN_RE.findall(value or "")
    short_word_ratio = 0.0
    if words_for_fragment_check:
        short_words = [w for w in words_for_fragment_check if len(w) <= 2]
        short_word_ratio = len(short_words) / max(len(words_for_fragment_check), 1)
    odd_upper_tokens = len(re.findall(r"\b[A-Z]{2,}[a-z]*[A-Z]+[A-Za-z]*\b", value or ""))
    ocr_fragment_suspected = (workflow == "ocr" and wc >= 6 and short_word_ratio >= 0.38 and (odd_upper_tokens >= 1 or fragmented_lines >= 2))
    if one_char_lines >= 4 or fragmented_lines >= 4 or ocr_fragment_suspected:
        signals.append(LFIESignal("ocr_sparse_noise", "warning", "Fragmented OCR-like text detected; OCR candidate may be noisy.", {"one_char_lines": one_char_lines, "fragmented_lines": fragmented_lines, "short_word_ratio": round(short_word_ratio, 3), "odd_upper_tokens": odd_upper_tokens}))
        score -= 0.55 if fragmented_lines >= 5 or one_char_lines >= 5 or ocr_fragment_suspected else 0.38

    if workflow in {"translation", "reader"} and TABLE_PIPE_RE.search(value):
        signals.append(LFIESignal("table_like_text", "info", "Table-like pipe structure detected.", True))

    if detected_language is None:
        detected_language = detect_text_language(value) if value.strip() else {"ok": False, "language": "unknown", "confidence": 0}
    if detected_language.get("ok"):
        confidence = float(detected_language.get("confidence", 0) or 0)
        if confidence < 0.45 and not detected_language.get("is_mixed"):
            signals.append(LFIESignal("low_language_confidence", "warning", "Language confidence is low.", round(confidence, 3)))
            score -= 0.18
        if detected_language.get("language") not in SUPPORTED_LANGS:
            signals.append(LFIESignal("unsupported_language", "warning", "Detected language is not directly supported.", detected_language.get("language")))
            score -= 0.2
    else:
        signals.append(LFIESignal("language_detection_failed", "warning", detected_language.get("error", "Language detection failed.")))
        score -= 0.15

    script = _script_profile(value)
    if workflow == "translation" and script.get("mixed_script"):
        signals.append(LFIESignal("mixed_script", "info", "Mixed writing systems detected.", script.get("dominant_script")))

    score = max(0.0, min(1.0, score))
    if score >= 0.82:
        level = "high"
    elif score >= 0.58:
        level = "medium"
    else:
        level = "low"
    return {
        "ok": True,
        "workflow": workflow,
        "score": round(score, 3),
        "level": level,
        "signals": [asdict(s) for s in signals],
        "detected_language": detected_language,
        "metrics": {
            "characters": len(value),
            "words": wc,
            "sentences": _sentence_count(value),
            "paragraphs": _paragraph_count(value),
            "lines": _line_count(value),
            "repeated_token_ratio": round(repeated, 3),
            "repeated_substring_ratio": round(repeated_substring, 3),
            "script": script,
        },
    }


def learning_report(text: str) -> Dict[str, Any]:
    corrections = load_corrections()
    lower = (text or "").lower()
    matched = []
    for wrong, correct in corrections.items():
        if str(wrong).lower() in lower or str(correct).lower() in lower:
            matched.append({"wrong": wrong, "correct": correct})
    return {
        "ok": True,
        "correction_count": len(corrections),
        "matched_corrections": matched[:25],
        "matched_count": len(matched),
        "learning_mode": "user_approved_only",
    }


def ai_router_report(workflow: str = "generic", privacy_mode: str = "offline") -> Dict[str, Any]:
    workflow = _normalize_workflow(workflow)
    privacy = (privacy_mode or "offline").lower().strip()
    status = provider_status()
    online_available = any(bool(v) for k, v in status.items() if isinstance(v, bool))
    recommended = "offline"
    reason = "Local-first mode is preferred for this workflow."
    if privacy not in {"offline", "local", "none"} and online_available:
        recommended = "optional_online_review"
        reason = "Online review is available but should remain explicit and user-controlled."
    return {
        "ok": True,
        "workflow": workflow,
        "privacy_mode": privacy,
        "recommended_route": recommended,
        "reason": reason,
        "provider_status": status,
        "policy": "No remote provider is called by LFIE analysis without an explicit workflow request.",
    }


def _candidate_score(text: str, workflow: str = "generic") -> float:
    report = confidence_report(text, workflow)
    score = float(report.get("score", 0))
    # Reward useful length, but cap it so verbosity does not dominate.
    wc = _word_count(text)
    score += min(wc, 120) / 1200.0
    # Penalize black boxes and pathological fragments strongly.
    if BLACK_BOX_RE.search(text or ""):
        score -= 0.6
    if wc < 3:
        score -= 0.2
    return max(0.0, min(1.0, score))


def consensus_report(candidates: Sequence[Dict[str, Any]] | Sequence[str], workflow: str = "generic") -> Dict[str, Any]:
    normalized: List[Dict[str, Any]] = []
    for idx, candidate in enumerate(candidates):
        if isinstance(candidate, str):
            item = {"provider": f"candidate_{idx+1}", "text": candidate, "ok": bool(candidate.strip())}
        else:
            item = dict(candidate)
            item.setdefault("provider", f"candidate_{idx+1}")
            item.setdefault("text", "")
            item.setdefault("ok", bool(str(item.get("text", "")).strip()))
        item["score"] = round(_candidate_score(str(item.get("text", "")), workflow), 3) if item.get("ok") else 0.0
        normalized.append(item)
    ranked = sorted(normalized, key=lambda c: c.get("score", 0), reverse=True)
    best = ranked[0] if ranked else {"provider": "none", "text": "", "score": 0, "ok": False}
    return {
        "ok": bool(ranked),
        "workflow": _normalize_workflow(workflow),
        "selected_provider": best.get("provider"),
        "selected_text": best.get("text", ""),
        "selected_score": best.get("score", 0),
        "candidates": ranked,
    }


def analyze_text(text: str, workflow: str = "generic", privacy_mode: str = "offline") -> Dict[str, Any]:
    workflow = _normalize_workflow(workflow)
    normalized = source_quality_normalize(text or "")
    detected = detect_text_language(normalized) if normalized.strip() else {"ok": False, "language": "unknown", "confidence": 0.0, "error": "Empty text"}
    entities = resolve_entities(normalized, workflow)
    confidence = confidence_report(normalized, workflow, detected)
    learning = learning_report(normalized)
    router = ai_router_report(workflow, privacy_mode)
    return {
        "ok": True,
        "engine": "lfie_v2_shared",
        "workflow": workflow,
        "normalized_text": normalized,
        "source_changed": normalized != (text or "").strip(),
        "language": detected,
        "entities": entities,
        "confidence": confidence,
        "learning": learning,
        "router": router,
    }


def translate_with_lfie(text: str, source_lang: str = "auto", target_lang: str = "de", workflow: str = "translation") -> Dict[str, Any]:
    before = analyze_text(text, workflow="translation")
    resolved_source = source_lang
    if (source_lang or "auto").lower() == "auto":
        lang = before.get("language", {})
        resolved_source = "auto" if lang.get("is_mixed") else lang.get("language", "en")
        if resolved_source not in {"en", "de", "es", "hi", "ar", "or", "auto"}:
            resolved_source = "en"
    translation = translate_with_views(before.get("normalized_text", text), resolved_source, target_lang)
    translated_text = translation.get("translated_text", "") if isinstance(translation, dict) else ""
    after = analyze_text(translated_text, workflow="translation") if translated_text else None
    return {
        "ok": bool(translation.get("ok")) if isinstance(translation, dict) else False,
        "engine": "lfie_v2_translation",
        "source_lang": resolved_source,
        "target_lang": target_lang,
        "analysis_before": before,
        "translation": translation,
        "analysis_after": after,
    }


def parse_candidates_json(candidates_json: str) -> List[Dict[str, Any]]:
    try:
        parsed = json.loads(candidates_json or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid candidates JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise ValueError("Candidates JSON must be a list.")
    output: List[Dict[str, Any]] = []
    for item in parsed:
        if isinstance(item, str):
            output.append({"text": item})
        elif isinstance(item, dict):
            output.append(item)
        else:
            output.append({"text": str(item)})
    return output



def workflow_audit_report(
    workflow: str,
    inputs: Dict[str, Any] | None = None,
    outputs: Dict[str, Any] | None = None,
    privacy_mode: str = "offline",
) -> Dict[str, Any]:
    """Return one LFIE audit object for a complete workflow transaction.

    Phase 4 uses this as the common integration layer. Endpoints can attach the
    report without changing their existing user-facing result shape. The audit
    keeps entity, confidence, language and routing decisions in one predictable
    place across Speech, OCR, Reader, Translation, Notes and Search.
    """
    workflow = _normalize_workflow(workflow)
    inputs = inputs or {}
    outputs = outputs or {}

    def _analyze_fields(fields: Dict[str, Any], prefix: str) -> Dict[str, Any]:
        analyzed: Dict[str, Any] = {}
        for key, value in fields.items():
            if value is None:
                continue
            if isinstance(value, (dict, list, tuple)):
                text = json.dumps(value, ensure_ascii=False)
            else:
                text = str(value)
            if not text.strip():
                continue
            report = analyze_text(text, workflow=workflow, privacy_mode=privacy_mode)
            analyzed[key] = {
                "field": key,
                "label": f"{prefix}.{key}",
                "language": report.get("language"),
                "confidence": report.get("confidence"),
                "entities": report.get("entities"),
                "learning": report.get("learning"),
            }
        return analyzed

    input_reports = _analyze_fields(inputs, "input")
    output_reports = _analyze_fields(outputs, "output")
    all_reports = list(input_reports.values()) + list(output_reports.values())
    confidence_scores: List[float] = []
    blocking_signals: List[Dict[str, Any]] = []
    entity_count = 0
    for item in all_reports:
        conf = item.get("confidence") or {}
        if isinstance(conf, dict):
            confidence_scores.append(float(conf.get("score", 0) or 0))
            for signal in conf.get("signals", []) or []:
                if signal.get("severity") in {"error", "warning"}:
                    blocking_signals.append({"field": item.get("field"), **signal})
        ents = item.get("entities") or {}
        if isinstance(ents, dict):
            entity_count += int(ents.get("entity_count", 0) or 0)

    min_confidence = min(confidence_scores) if confidence_scores else 0.0
    avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
    quality_gate = "pass"
    if any(sig.get("severity") == "error" for sig in blocking_signals) or min_confidence < 0.45:
        quality_gate = "review_required"
    elif blocking_signals or min_confidence < 0.65:
        quality_gate = "warning"

    audit = {
        "ok": True,
        "engine": "lfie_v2_shared",
        "workflow": workflow,
        "quality_gate": quality_gate,
        "min_confidence": round(min_confidence, 3),
        "avg_confidence": round(avg_confidence, 3),
        "entity_count": entity_count,
        "blocking_signals": blocking_signals[:50],
        "input_reports": input_reports,
        "output_reports": output_reports,
        "router": ai_router_report(workflow, privacy_mode),
    }
    audit["decision"] = quality_decision_from_audit(audit, strict=False)
    return audit


def quality_decision_from_audit(audit: Dict[str, Any], strict: bool = False) -> Dict[str, Any]:
    """Convert an LFIE audit into a deterministic workflow decision.

    Phase 4 decision enforcement uses this as the single quality gate. The
    default mode is non-destructive: workflows continue to return their normal
    payloads while also returning a decision object. Callers can set strict=True
    for endpoints that must block review_required output.
    """
    gate = str((audit or {}).get("quality_gate", "warning") or "warning")
    signals = list((audit or {}).get("blocking_signals", []) or [])
    min_conf = float((audit or {}).get("min_confidence", 0.0) or 0.0)
    error_signals = [s for s in signals if s.get("severity") == "error"]
    warning_signals = [s for s in signals if s.get("severity") == "warning"]

    action = "allow"
    blocked = False
    requires_review = False
    if gate == "review_required" or error_signals:
        requires_review = True
        action = "block" if strict else "review_required"
        blocked = bool(strict)
    elif gate == "warning" or warning_signals:
        action = "warn"

    reasons: List[str] = []
    for signal in signals[:10]:
        name = signal.get("name") or "quality_signal"
        msg = signal.get("message") or "Quality signal raised."
        reasons.append(f"{name}: {msg}")

    return {
        "ok": True,
        "gate": gate,
        "action": action,
        "blocked": blocked,
        "requires_review": requires_review,
        "min_confidence": round(min_conf, 3),
        "reason_count": len(reasons),
        "reasons": reasons,
        "strict": bool(strict),
    }


def enforce_workflow_quality(
    result: Dict[str, Any],
    workflow: str,
    input_text: str = "",
    output_text: str = "",
    privacy_mode: str = "offline",
    strict: bool = False,
) -> Dict[str, Any]:
    """Attach LFIE audit and enforce the workflow quality decision.

    This function is the active Phase 4 quality-gate layer. In normal mode it
    adds LFIE warnings/review flags without breaking legacy UI calls. In strict
    mode it marks blocked outputs as not ok and adds an explicit error.
    """
    if not isinstance(result, dict):
        return result
    try:
        audit = workflow_audit_report(
            workflow=workflow,
            inputs={"text": input_text} if input_text else {},
            outputs={"text": output_text} if output_text else {},
            privacy_mode=privacy_mode,
        )
        decision = quality_decision_from_audit(audit, strict=strict)
        result["lfie"] = audit
        result["lfie_decision"] = decision
        result["quality_gate"] = decision.get("gate")
        result["requires_review"] = decision.get("requires_review", False)
        if decision.get("blocked"):
            result["ok"] = False
            result["error"] = "LFIE quality gate blocked this output for review."
    except Exception as exc:
        result["lfie"] = {"ok": False, "workflow": _normalize_workflow(workflow), "error": str(exc)}
        result["lfie_decision"] = {"ok": False, "action": "warn", "blocked": False, "requires_review": True, "reasons": [str(exc)]}
        result["quality_gate"] = "warning"
        result["requires_review"] = True
    return result


def export_quality_preflight(text: str, workflow: str = "translation", output_format: str = "pdf", strict: bool = True) -> Dict[str, Any]:
    """Preflight check for exported text before file rendering.

    It catches empty outputs, black-box glyphs, repeated substrings, and noisy
    OCR fragments before a user receives a broken PDF/DOCX/TXT export.
    """
    audit = workflow_audit_report(workflow=workflow, outputs={"text": text or ""})
    decision = quality_decision_from_audit(audit, strict=strict)
    return {
        "ok": not bool(decision.get("blocked")),
        "workflow": _normalize_workflow(workflow),
        "output_format": (output_format or "txt").lower().strip(),
        "audit": audit,
        "decision": decision,
    }


def attach_lfie_result(
    result: Dict[str, Any],
    workflow: str,
    input_text: str = "",
    output_text: str = "",
    privacy_mode: str = "offline",
) -> Dict[str, Any]:
    """Attach LFIE metadata and non-blocking quality decision to a result."""
    return enforce_workflow_quality(
        result,
        workflow=workflow,
        input_text=input_text,
        output_text=output_text,
        privacy_mode=privacy_mode,
        strict=False,
    )
