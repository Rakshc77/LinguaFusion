import json
import os
from typing import Dict, Any

from backend.config.paths import STORAGE_DIR, migrate_legacy_storage_file

CONFIG_FILE = migrate_legacy_storage_file("ai_providers.json")

DEFAULT_CONFIG = {
    "smart_mode_enabled": False,
    "default_mode": "free_auto",
    "primary_provider": "gemini",
    "keys": {
        "gemini": "",
        "groq": "",
        "openrouter": "",
    },
}


def _ensure_storage() -> None:
    STORAGE_DIR.mkdir(exist_ok=True)
    if not CONFIG_FILE.exists():
        save_ai_provider_config(DEFAULT_CONFIG)


def load_ai_provider_config(include_keys: bool = True) -> Dict[str, Any]:
    _ensure_storage()
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}

    config = dict(DEFAULT_CONFIG)
    config.update({k: v for k, v in data.items() if k != "keys"})
    keys = dict(DEFAULT_CONFIG["keys"])
    keys.update(data.get("keys") if isinstance(data.get("keys"), dict) else {})

    # Environment variables remain supported as overrides/fallbacks.
    env_keys = {
        "gemini": os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "",
        "groq": os.getenv("GROQ_API_KEY") or "",
        "openrouter": os.getenv("OPENROUTER_API_KEY") or "",
    }
    for provider, env_value in env_keys.items():
        if env_value:
            keys[provider] = env_value

    config["keys"] = keys if include_keys else {k: bool(v) for k, v in keys.items()}
    return config


def save_ai_provider_config(config: Dict[str, Any]) -> Dict[str, Any]:
    STORAGE_DIR.mkdir(exist_ok=True)
    current = load_ai_provider_config(include_keys=True) if CONFIG_FILE.exists() else dict(DEFAULT_CONFIG)

    smart_mode_enabled = bool(config.get("smart_mode_enabled", current.get("smart_mode_enabled", False)))
    default_mode = str(config.get("default_mode", current.get("default_mode", "free_auto")) or "free_auto")
    primary_provider = str(config.get("primary_provider", current.get("primary_provider", "gemini")) or "gemini")

    keys = dict(current.get("keys", {}))
    incoming_keys = config.get("keys") if isinstance(config.get("keys"), dict) else {}
    for provider in ["gemini", "groq", "openrouter"]:
        value = incoming_keys.get(provider, None)
        if value is not None:
            keys[provider] = str(value).strip()

    clean = {
        "smart_mode_enabled": smart_mode_enabled,
        "default_mode": default_mode,
        "primary_provider": primary_provider,
        "keys": {
            "gemini": keys.get("gemini", ""),
            "groq": keys.get("groq", ""),
            "openrouter": keys.get("openrouter", ""),
        },
    }
    CONFIG_FILE.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")
    return clean


def get_provider_key(provider: str) -> str:
    provider = (provider or "").lower().strip()
    return load_ai_provider_config(include_keys=True).get("keys", {}).get(provider, "")


def public_ai_provider_config() -> Dict[str, Any]:
    config = load_ai_provider_config(include_keys=True)
    keys = config.get("keys", {})
    return {
        "ok": True,
        "smart_mode_enabled": config.get("smart_mode_enabled", False),
        "default_mode": config.get("default_mode", "free_auto"),
        "primary_provider": config.get("primary_provider", "gemini"),
        "has_keys": {
            "gemini": bool(keys.get("gemini")),
            "groq": bool(keys.get("groq")),
            "openrouter": bool(keys.get("openrouter")),
        },
        "storage_file": str(CONFIG_FILE),
    }


def test_provider(provider: str) -> Dict[str, Any]:
    """Test one configured AI provider without exposing stored API keys."""
    provider = (provider or "").lower().strip()

    if provider not in {"languagetool", "gemini", "groq", "openrouter"}:
        return {
            "ok": False,
            "provider": provider,
            "error": "Unknown provider. Use languagetool, gemini, groq, or openrouter.",
        }

    sample = "Ain't no brave can hold my body tight. Baden-Wittenberg is a German state."

    try:
        from backend.services.free_online_correction_service import (
            languagetool_correct,
            gemini_correct,
            groq_correct,
            openrouter_correct,
        )

        if provider == "languagetool":
            result = languagetool_correct(sample, "en")
        elif provider == "gemini":
            result = gemini_correct(sample, "en")
        elif provider == "groq":
            result = groq_correct(sample, "en")
        else:
            result = openrouter_correct(sample, "en")

        return {
            "ok": bool(result.get("ok")),
            "provider": provider,
            "available": bool(result.get("ok")),
            "changed": bool(result.get("changed")),
            "sample_input": sample,
            "sample_output": result.get("text", ""),
            "error": result.get("error"),
        }
    except Exception as exc:
        return {
            "ok": False,
            "provider": provider,
            "available": False,
            "error": str(exc),
        }
