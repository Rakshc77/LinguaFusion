import os
import re
import json
import requests
from typing import Dict

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


def _ollama_config() -> Dict[str, object]:
    data = _load_local_provider_config()
    ollama = data.get("ollama") if isinstance(data.get("ollama"), dict) else {}
    url = os.getenv("OLLAMA_URL") or ollama.get("url") or "http://localhost:11434"
    model = os.getenv("OLLAMA_MODEL") or ollama.get("model") or "llama3.1:8b"
    enabled = ollama.get("enabled", True)
    try:
        num_gpu = max(1, int(os.getenv("OLLAMA_NUM_GPU") or ollama.get("num_gpu") or 999))
    except (TypeError, ValueError):
        num_gpu = 999
    raw_keep_alive = os.getenv("OLLAMA_KEEP_ALIVE") or ollama.get("keep_alive", -1)
    try:
        keep_alive = int(raw_keep_alive)
    except (TypeError, ValueError):
        keep_alive = str(raw_keep_alive or "-1").strip()
    return {
        "url": str(url).rstrip("/"),
        "model": str(model),
        "enabled": bool(enabled),
        "num_gpu": num_gpu,
        "keep_alive": keep_alive,
    }


def _ollama_generation_options(config: Dict[str, object]) -> Dict[str, object]:
    """Deterministic correction with full GPU layer offload requested."""
    return {"temperature": 0.0, "num_gpu": int(config.get("num_gpu", 999))}


def _ollama_post(*args, **kwargs):
    from backend.services.gpu_coordinator import gpu_operation

    with gpu_operation("ollama"):
        return requests.post(*args, **kwargs)


def _ollama_reachable(url: str, timeout: float = 1.5) -> bool:
    if not url:
        return False
    try:
        response = requests.get(f"{url}/api/tags", timeout=timeout)
        return response.status_code == 200
    except Exception:
        return False


def provider_status() -> Dict[str, object]:
    ollama = _ollama_config()
    return {
        "ok": True,
        "providers": {
            "languagetool": {
                "available": True,
                "requires_key": False,
                "env": None,
                "note": "Public endpoint, rate-limited, grammar/spelling only.",
            },
            "ollama": {
                "available": bool(ollama.get("enabled")) and _ollama_reachable(ollama.get("url", "")),
                "requires_key": False,
                "env": "OLLAMA_URL / OLLAMA_MODEL (optional overrides)",
                "note": f"Local model via Ollama ({ollama.get('model')}). No internet, no API key, no rate limits.",
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


def _valid_correction(original: str, corrected: str, min_overlap: float = 0.55) -> bool:
    original = (original or "").strip()
    corrected = (corrected or "").strip()
    if not corrected:
        return False
    if not original:
        return True
    if len(corrected) > max(len(original) * 2.2, len(original) + 160):
        return False

    # Guard against hallucinated rewrites: a real correction fixes individual
    # words, so most of the original vocabulary should still be present.
    # A wholesale rewrite (different words, same rough length) slips past a
    # pure length check but fails this overlap check.
    # Uses \w (Unicode word chars) rather than [a-zA-Z] so German/Spanish
    # umlauts and accents count as letters too -- a pure-ASCII regex here
    # would undercount overlap for exactly the text this guardrail most
    # needs to protect.
    orig_words = set(re.findall(r"[^\W\d_]+", original.lower(), flags=re.UNICODE))
    corr_words = set(re.findall(r"[^\W\d_]+", corrected.lower(), flags=re.UNICODE))
    if len(orig_words) >= 6:
        overlap = len(orig_words & corr_words) / len(orig_words)
        if overlap < min_overlap:
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
        "You are a strict ASR (speech-to-text) error corrector. You are NOT a writer, "
        "lyricist, or paraphraser. Your only job is to fix individual words that were "
        "almost certainly misheard by the speech recognizer -- wrong homophones, wrong "
        "proper nouns, wrong small words. Everything else must stay byte-for-byte identical: "
        "same word order, same sentence structure, same line breaks, same repeated "
        "chorus/phrase structure, same overall wording and length. "
        "Do NOT rewrite, paraphrase, summarize, or improve the style. Do NOT invent words, "
        "lines, or lyrics that are not implied by the input. If you are not confident a "
        "word is wrong, leave it exactly as-is. "
        "Output ONLY the corrected transcript with no preamble, no explanation, no quotes.\n\n"
        f"Language hint: {language}\n"
        f"Transcript:\n{text}"
    )


def ollama_correct(text: str, language: str = "auto") -> Dict[str, object]:
    """Correct ASR transcript errors using a local Ollama model.

    Local-first: no internet, no API key, no per-request cost or rate limit.
    Requires Ollama running locally (see https://ollama.com) with a model
    pulled, e.g. `ollama pull llama3.1:8b`.
    """
    config = _ollama_config()
    source = _safe_text(text)
    if not source:
        return {"ok": False, "provider": "ollama", "error": "No transcript text to correct.", "text": ""}
    if not config.get("enabled"):
        return {"ok": False, "provider": "ollama", "error": "Ollama provider disabled in settings.", "text": source}
    url = config.get("url", "")
    model = config.get("model", "llama3.1:8b")
    try:
        response = _ollama_post(
            f"{url}/api/chat",
            json={
                "model": model,
                "stream": False,
                "keep_alive": config.get("keep_alive", -1),
                "options": _ollama_generation_options(config),
                "messages": [
                    {"role": "system", "content": "You correct ASR transcript errors. Return only the corrected text, nothing else."},
                    {"role": "user", "content": _semantic_prompt(source, language)},
                ],
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        corrected = _extract_corrected_from_llm(data.get("message", {}).get("content", ""))
        if not _valid_correction(source, corrected):
            raise RuntimeError("Rejected unsafe correction length.")
        return {"ok": True, "provider": "ollama", "text": corrected, "changed": corrected != source}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "provider": "ollama", "error": f"Could not reach Ollama at {url}. Is it running?", "text": source}
    except Exception as exc:
        return {"ok": False, "provider": "ollama", "error": str(exc), "text": source}


def _ocr_correction_prompt(text: str, language: str = "auto") -> str:
    return (
        "You are a strict OCR (optical character recognition) error corrector. "
        "You are NOT a writer or editor. Your only job is to fix individual "
        "characters that were almost certainly misread by the OCR engine -- "
        "most commonly: missing or wrong umlauts (u/o/a instead of ü/ö/ä), "
        "missing eszett (ss instead of ß), a digit misread as a similar-looking "
        "letter or vice versa (0/O, 1/l/I, 5/S), and words incorrectly split or "
        "joined at line breaks. "
        "Everything else must stay exactly as given: same word order, same line "
        "breaks, same numbers (unless a digit was clearly misread as a letter), "
        "same table structure and '|' separators, same overall length and "
        "wording. Do NOT rewrite, reword, summarize, or add any words, lines, "
        "or explanation that are not already implied character-for-character by "
        "the input. If you are not confident a character is wrong, leave it "
        "exactly as-is. "
        "Output ONLY the corrected text with no preamble, no explanation, no quotes.\n\n"
        f"Language hint: {language}\n"
        f"OCR text:\n{text}"
    )


def ocr_correct_text(text: str, language: str = "auto") -> Dict[str, object]:
    """Restore likely OCR misreads (missing umlauts/ß, 0/O, 1/l/I, etc.) using
    the local Ollama model, with the same word-overlap guardrail used for
    speech correction -- but stricter, since OCR text often carries numbers,
    item codes, and technical values that must not be allowed to drift.

    Returns the original text unchanged (ok=True, changed=False) if Ollama
    isn't available or the guardrail rejects the result, rather than ever
    surfacing a broken/hallucinated correction.
    """
    config = _ollama_config()
    source = _safe_text(text, 6000)
    if not source:
        return {"ok": True, "provider": "offline", "text": "", "changed": False}
    if not config.get("enabled"):
        return {"ok": True, "provider": "offline", "text": source, "changed": False}

    url = config.get("url", "")
    model = config.get("model", "llama3.1:8b")
    try:
        response = _ollama_post(
            f"{url}/api/chat",
            json={
                "model": model,
                "stream": False,
                "keep_alive": config.get("keep_alive", -1),
                "options": _ollama_generation_options(config),
                "messages": [
                    {"role": "system", "content": "You correct OCR character-recognition errors. Return only the corrected text, nothing else."},
                    {"role": "user", "content": _ocr_correction_prompt(source, language)},
                ],
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        corrected = _extract_corrected_from_llm(data.get("message", {}).get("content", ""))
        # Stricter overlap threshold than speech correction (0.75 vs 0.55):
        # OCR text often contains item codes, prices, and technical values
        # where any drift matters more than in conversational ASR text.
        if not _valid_correction(source, corrected, min_overlap=0.75):
            return {"ok": True, "provider": "offline", "text": source, "changed": False}
        return {"ok": True, "provider": "ollama", "text": corrected, "changed": corrected != source}
    except requests.exceptions.ConnectionError:
        return {"ok": True, "provider": "offline", "text": source, "changed": False, "note": f"Ollama unreachable at {url}"}
    except Exception:
        return {"ok": True, "provider": "offline", "text": source, "changed": False}


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
    if mode == "ollama":
        ordered = [ollama_correct]
    elif mode in {"free_auto", "smart_free"}:
        # Local-first: Ollama is now the only semantic-correction provider.
        ordered = [ollama_correct]

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
    """Run offline + available free providers and return candidates for comparison."""
    source = _safe_text(text, 12000)
    candidates = []

    offline_text = apply_corrections(source)
    candidates.append({"provider": "offline", "ok": True, "text": offline_text, "changed": offline_text != source})

    lt = languagetool_correct(offline_text, language)
    candidates.append({k: lt.get(k) for k in ["provider", "ok", "text", "changed", "error"]})

    result = ollama_correct(offline_text, language)
    candidates.append({k: result.get(k) for k in ["provider", "ok", "text", "changed", "error"]})

    valid = [c for c in candidates if c.get("ok") and c.get("text")]
    # Local-first: Ollama ranks above languagetool/offline when it produced a usable result.
    preferred_order = {"ollama": 0, "languagetool": 1, "offline": 2}
    changed = [c for c in valid if c.get("changed")]
    pool = changed or valid
    best = sorted(pool, key=lambda c: preferred_order.get(str(c.get("provider")), 99))[0] if pool else candidates[0]
    return {"ok": True, "provider": best.get("provider"), "text": best.get("text", source), "candidates": candidates}
