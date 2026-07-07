import os
import re
import json
import requests
from typing import Dict, Optional

from backend.config.paths import STORAGE_DIR, LEGACY_STORAGE_DIR
from backend.services.correction_service import apply_corrections

LANGUAGETOOL_URL = "https://api.languagetool.org/v2/check"

CONFIG_FILE = STORAGE_DIR / "ai_providers.json"
ALT_CONFIG_FILE = LEGACY_STORAGE_DIR / "ai_providers.json"


def _load_local_provider_config() -> Dict[str, object]:
    for path in [CONFIG_FILE, ALT_CONFIG_FILE]:
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
        except Exception:
            continue
    return {}


def _config_key(*names: str) -> str:
    data = _load_local_provider_config()

    for name in names:
        value = os.getenv(name)
        if value:
            return value.strip()

    # Current Settings page stores keys under {"keys": {"gemini": "..."}}.
    nested_keys = data.get("keys") if isinstance(data.get("keys"), dict) else {}
    provider_aliases = {
        "gemini": {"GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_KEY", "GOOGLE_KEY"},
        "groq": {"GROQ_API_KEY", "GROQ_KEY"},
        "openrouter": {"OPENROUTER_API_KEY", "OPENROUTER_KEY"},
    }
    upper_names = {n.upper() for n in names}
    for provider, aliases in provider_aliases.items():
        if upper_names & aliases and nested_keys.get(provider):
            return str(nested_keys.get(provider, "")).strip()

    # Backward compatibility for older flat/provider-specific files.
    lower_map = {str(k).lower(): str(v) for k, v in data.items() if not isinstance(v, dict) and v}
    for name in names:
        variants = {
            name.lower(),
            name.lower().replace("_api_key", ""),
            name.lower().replace("_key", ""),
            name.lower().replace("api_key", "apiKey").lower(),
        }
        for variant in variants:
            if variant in lower_map:
                return lower_map[variant].strip()

    for provider in ["gemini", "groq", "openrouter"]:
        provider_data = data.get(provider) or data.get(provider.title()) or {}
        if isinstance(provider_data, dict) and provider.upper() in names[0].upper():
            for field in ["api_key", "apiKey", "key", "token"]:
                if provider_data.get(field):
                    return str(provider_data[field]).strip()
    return ""


def provider_status() -> Dict[str, object]:
    return {
        "ok": True,
        "providers": {
            "languagetool": {
                "available": True,
                "requires_key": False,
                "env": None,
                "note": "Public endpoint, rate-limited, grammar/spelling only.",
            },
            "gemini": {
                "available": bool(_config_key("GEMINI_API_KEY", "GOOGLE_API_KEY")),
                "requires_key": True,
                "env": "GEMINI_API_KEY or GOOGLE_API_KEY",
                "note": "Google AI Studio Gemini API key.",
            },
            "groq": {
                "available": bool(_config_key("GROQ_API_KEY")),
                "requires_key": True,
                "env": "GROQ_API_KEY",
                "note": "GroqCloud OpenAI-compatible endpoint.",
            },
            "openrouter": {
                "available": bool(_config_key("OPENROUTER_API_KEY")),
                "requires_key": True,
                "env": "OPENROUTER_API_KEY",
                "note": "OpenRouter free model router/open-source models.",
            },
        },
    }


def _safe_text(text: str, max_chars: int = 1800) -> str:
    text = (text or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:max_chars].strip()


def _extract_corrected_from_llm(output: str) -> str:
    output = (output or "").strip()
    output = re.sub(r"^```(?:text)?", "", output, flags=re.IGNORECASE).strip()
    output = re.sub(r"```$", "", output).strip()
    for prefix in ["Corrected:", "Corrected transcript:", "Output:"]:
        if output.lower().startswith(prefix.lower()):
            output = output[len(prefix):].strip()
    return output.strip()


def _valid_correction(original: str, corrected: str) -> bool:
    original = (original or "").strip()
    corrected = (corrected or "").strip()
    if not corrected:
        return False
    if not original:
        return True
    if len(corrected) > max(len(original) * 2.2, len(original) + 160):
        return False
    return True


def languagetool_correct(text: str, language: str = "auto") -> Dict[str, object]:
    source = _safe_text(text, 12000)
    if not source:
        return {"ok": False, "provider": "languagetool", "error": "No text provided.", "text": ""}

    lang = "auto" if language in {"auto", ""} else language
    try:
        response = requests.post(
            LANGUAGETOOL_URL,
            data={"text": source, "language": lang},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return {"ok": False, "provider": "languagetool", "error": str(exc), "text": source}

    corrected = source
    matches = sorted(payload.get("matches", []), key=lambda m: int(m.get("offset", 0)), reverse=True)
    for match in matches:
        replacements = match.get("replacements") or []
        if not replacements:
            continue
        replacement = replacements[0].get("value", "")
        if not replacement:
            continue
        offset = int(match.get("offset", 0))
        length = int(match.get("length", 0))
        if 0 <= offset <= len(corrected) and length > 0:
            corrected = corrected[:offset] + replacement + corrected[offset + length:]

    return {
        "ok": True,
        "provider": "languagetool",
        "text": corrected,
        "changed": corrected != source,
        "raw": payload,
    }


def _semantic_prompt(text: str, language: str = "auto") -> str:
    return (
        "You are correcting ASR/transcription mistakes, not translating. "
        "Preserve the original language, meaning, line order, wording style, repeated chorus structure, "
        "and proper nouns. Fix only likely recognition errors such as wrong homophones or wrong named entities. "
        "Do not add lyrics that are not present. Do not explain. Return only the corrected transcript.\n\n"
        f"Language hint: {language}\n"
        f"Transcript:\n{text}"
    )


def gemini_correct(text: str, language: str = "auto") -> Dict[str, object]:
    key = _config_key("GEMINI_API_KEY", "GOOGLE_API_KEY")
    source = _safe_text(text)
    if not key:
        return {"ok": False, "provider": "gemini", "error": "Missing GEMINI_API_KEY or GOOGLE_API_KEY.", "text": source}
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
        payload = {"contents": [{"parts": [{"text": _semantic_prompt(source, language)}]}], "generationConfig": {"temperature": 0.1}}
        response = requests.post(url, json=payload, timeout=35)
        response.raise_for_status()
        data = response.json()
        corrected = data["candidates"][0]["content"]["parts"][0]["text"]
        corrected = _extract_corrected_from_llm(corrected)
        if not _valid_correction(source, corrected):
            raise RuntimeError("Rejected unsafe correction length.")
        return {"ok": True, "provider": "gemini", "text": corrected, "changed": corrected != source}
    except Exception as exc:
        return {"ok": False, "provider": "gemini", "error": str(exc), "text": source}


def groq_correct(text: str, language: str = "auto") -> Dict[str, object]:
    key = _config_key("GROQ_API_KEY")
    source = _safe_text(text)
    if not key:
        return {"ok": False, "provider": "groq", "error": "Missing GROQ_API_KEY.", "text": source}
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.1-8b-instant",
                "temperature": 0.1,
                "messages": [
                    {"role": "system", "content": "You correct ASR transcript errors. Return only corrected text."},
                    {"role": "user", "content": _semantic_prompt(source, language)},
                ],
            },
            timeout=35,
        )
        response.raise_for_status()
        data = response.json()
        corrected = _extract_corrected_from_llm(data["choices"][0]["message"]["content"])
        if not _valid_correction(source, corrected):
            raise RuntimeError("Rejected unsafe correction length.")
        return {"ok": True, "provider": "groq", "text": corrected, "changed": corrected != source}
    except Exception as exc:
        return {"ok": False, "provider": "groq", "error": str(exc), "text": source}


def openrouter_correct(text: str, language: str = "auto") -> Dict[str, object]:
    key = _config_key("OPENROUTER_API_KEY")
    source = _safe_text(text)
    if not key:
        return {"ok": False, "provider": "openrouter", "error": "Missing OPENROUTER_API_KEY.", "text": source}
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "X-Title": "LinguaFusion"},
            json={
                "model": "openrouter/free",
                "temperature": 0.1,
                "messages": [
                    {"role": "system", "content": "Correct ASR transcript errors. Return only corrected text."},
                    {"role": "user", "content": _semantic_prompt(source, language)},
                ],
            },
            timeout=45,
        )
        response.raise_for_status()
        data = response.json()
        corrected = _extract_corrected_from_llm(data["choices"][0]["message"]["content"])
        if not _valid_correction(source, corrected):
            raise RuntimeError("Rejected unsafe correction length.")
        return {"ok": True, "provider": "openrouter", "text": corrected, "changed": corrected != source}
    except Exception as exc:
        return {"ok": False, "provider": "openrouter", "error": str(exc), "text": source}


def smart_correct_text(text: str, mode: str = "offline", language: str = "auto") -> Dict[str, object]:
    source = _safe_text(text, 12000)
    mode = (mode or "offline").lower().strip()

    offline = apply_corrections(source)
    if mode in {"offline", "none", ""}:
        return {"ok": True, "provider": "offline", "text": offline, "changed": offline != source, "attempts": []}

    attempts = []

    if mode in {"languagetool", "free_auto", "smart_free"}:
        lt = languagetool_correct(offline, language)
        attempts.append({k: lt.get(k) for k in ["provider", "ok", "error", "changed"]})
        if lt.get("ok") and lt.get("changed") and mode == "languagetool":
            return {"ok": True, "provider": "languagetool", "text": apply_corrections(lt["text"]), "changed": True, "attempts": attempts}
        if lt.get("ok") and mode in {"free_auto", "smart_free"}:
            offline = apply_corrections(lt.get("text", offline))

    ordered = []
    if mode == "gemini":
        ordered = [gemini_correct]
    elif mode == "groq":
        ordered = [groq_correct]
    elif mode == "openrouter":
        ordered = [openrouter_correct]
    elif mode in {"free_auto", "smart_free"}:
        ordered = [gemini_correct, groq_correct, openrouter_correct]

    for provider_func in ordered:
        result = provider_func(offline, language)
        attempts.append({k: result.get(k) for k in ["provider", "ok", "error", "changed"]})
        if result.get("ok") and result.get("text"):
            final_text = apply_corrections(result["text"])
            return {
                "ok": True,
                "provider": result.get("provider"),
                "text": final_text,
                "changed": final_text != source,
                "attempts": attempts,
            }

    return {"ok": True, "provider": "offline", "text": offline, "changed": offline != source, "attempts": attempts}


def compare_online_corrections(text: str, language: str = "auto") -> Dict[str, object]:
    """Run offline + all available free providers and return candidates for comparison."""
    source = _safe_text(text, 12000)
    candidates = []

    offline_text = apply_corrections(source)
    candidates.append({"provider": "offline", "ok": True, "text": offline_text, "changed": offline_text != source})

    lt = languagetool_correct(offline_text, language)
    candidates.append({k: lt.get(k) for k in ["provider", "ok", "text", "changed", "error"]})

    for fn in [gemini_correct, groq_correct, openrouter_correct]:
        result = fn(offline_text, language)
        candidates.append({k: result.get(k) for k in ["provider", "ok", "text", "changed", "error"]})

    valid = [c for c in candidates if c.get("ok") and c.get("text")]
    # Prefer semantic providers when they return a safe changed result; otherwise keep offline/LT.
    preferred_order = {"gemini": 0, "groq": 1, "openrouter": 2, "languagetool": 3, "offline": 4}
    changed = [c for c in valid if c.get("changed")]
    pool = changed or valid
    best = sorted(pool, key=lambda c: preferred_order.get(str(c.get("provider")), 99))[0] if pool else candidates[0]
    return {"ok": True, "provider": best.get("provider"), "text": best.get("text", source), "candidates": candidates}
