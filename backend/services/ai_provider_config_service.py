import json
import os
from typing import Dict, Any

from backend.config.paths import STORAGE_DIR, migrate_legacy_storage_file

CONFIG_FILE = migrate_legacy_storage_file("ai_providers.json")

DEFAULT_CONFIG = {
    "smart_mode_enabled": False,
    "default_mode": "free_auto",
    "ollama": {
        "enabled": True,
        "url": "http://localhost:11434",
        "model": "llama3.1:8b",
        # Ask Ollama to offload every model layer to the GPU. A deliberately
        # high layer count is capped by Ollama at the model's actual count.
        "num_gpu": 999,
        # Keep the model resident until Ollama exits. This avoids paying the
        # load cost again after Ollama's normal five-minute idle timeout.
        "keep_alive": -1,
    },
}


def _ensure_storage() -> None:
    STORAGE_DIR.mkdir(exist_ok=True)
    if not CONFIG_FILE.exists():
        save_ai_provider_config(DEFAULT_CONFIG)


def load_ai_provider_config() -> Dict[str, Any]:
    _ensure_storage()
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}

    config = dict(DEFAULT_CONFIG)
    config.update({k: v for k, v in data.items() if k != "ollama"})

    ollama = dict(DEFAULT_CONFIG["ollama"])
    ollama.update(data.get("ollama") if isinstance(data.get("ollama"), dict) else {})
    # Environment variables remain supported as overrides for local dev/testing.
    if os.getenv("OLLAMA_MODEL"):
        ollama["model"] = os.getenv("OLLAMA_MODEL")
    if os.getenv("OLLAMA_URL"):
        ollama["url"] = os.getenv("OLLAMA_URL")
    if os.getenv("OLLAMA_NUM_GPU"):
        try:
            ollama["num_gpu"] = max(1, int(os.getenv("OLLAMA_NUM_GPU", "999")))
        except ValueError:
            ollama["num_gpu"] = DEFAULT_CONFIG["ollama"]["num_gpu"]
    if os.getenv("OLLAMA_KEEP_ALIVE"):
        raw_keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", "-1").strip()
        try:
            ollama["keep_alive"] = int(raw_keep_alive)
        except ValueError:
            ollama["keep_alive"] = raw_keep_alive
    config["ollama"] = ollama
    return config


def save_ai_provider_config(config: Dict[str, Any]) -> Dict[str, Any]:
    STORAGE_DIR.mkdir(exist_ok=True)
    current = load_ai_provider_config() if CONFIG_FILE.exists() else dict(DEFAULT_CONFIG)

    smart_mode_enabled = bool(config.get("smart_mode_enabled", current.get("smart_mode_enabled", False)))
    default_mode = str(config.get("default_mode", current.get("default_mode", "free_auto")) or "free_auto")

    ollama = dict(current.get("ollama", DEFAULT_CONFIG["ollama"]))
    incoming_ollama = config.get("ollama") if isinstance(config.get("ollama"), dict) else {}
    if "enabled" in incoming_ollama:
        ollama["enabled"] = bool(incoming_ollama["enabled"])
    if incoming_ollama.get("url"):
        ollama["url"] = str(incoming_ollama["url"]).strip()
    if incoming_ollama.get("model"):
        ollama["model"] = str(incoming_ollama["model"]).strip()
    if "num_gpu" in incoming_ollama:
        try:
            ollama["num_gpu"] = max(1, int(incoming_ollama["num_gpu"]))
        except (TypeError, ValueError):
            ollama["num_gpu"] = DEFAULT_CONFIG["ollama"]["num_gpu"]
    if "keep_alive" in incoming_ollama:
        keep_alive = incoming_ollama["keep_alive"]
        try:
            ollama["keep_alive"] = int(keep_alive)
        except (TypeError, ValueError):
            ollama["keep_alive"] = str(keep_alive or "-1").strip()

    clean = {
        "smart_mode_enabled": smart_mode_enabled,
        "default_mode": default_mode,
        "ollama": {
            "enabled": bool(ollama.get("enabled", True)),
            "url": ollama.get("url", DEFAULT_CONFIG["ollama"]["url"]),
            "model": ollama.get("model", DEFAULT_CONFIG["ollama"]["model"]),
            "num_gpu": int(ollama.get("num_gpu", DEFAULT_CONFIG["ollama"]["num_gpu"])),
            "keep_alive": ollama.get("keep_alive", DEFAULT_CONFIG["ollama"]["keep_alive"]),
        },
    }
    CONFIG_FILE.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")
    return clean


def public_ai_provider_config() -> Dict[str, Any]:
    config = load_ai_provider_config()
    ollama = config.get("ollama", DEFAULT_CONFIG["ollama"])
    return {
        "ok": True,
        "smart_mode_enabled": config.get("smart_mode_enabled", False),
        "default_mode": config.get("default_mode", "free_auto"),
        "ollama": {
            "enabled": bool(ollama.get("enabled", True)),
            "url": ollama.get("url", DEFAULT_CONFIG["ollama"]["url"]),
            "model": ollama.get("model", DEFAULT_CONFIG["ollama"]["model"]),
            "num_gpu": int(ollama.get("num_gpu", DEFAULT_CONFIG["ollama"]["num_gpu"])),
            "keep_alive": ollama.get("keep_alive", DEFAULT_CONFIG["ollama"]["keep_alive"]),
        },
        "storage_file": str(CONFIG_FILE),
    }


def test_provider(provider: str) -> Dict[str, Any]:
    """Test one configured provider (languagetool or ollama)."""
    provider = (provider or "").lower().strip()

    if provider not in {"languagetool", "ollama"}:
        return {
            "ok": False,
            "provider": provider,
            "error": "Unknown provider. Use languagetool or ollama.",
        }

    sample = "Ain't no brave can hold my body tight. Baden-Wittenberg is a German state."

    try:
        from backend.services.free_online_correction_service import (
            languagetool_correct,
            ollama_correct,
        )

        if provider == "languagetool":
            result = languagetool_correct(sample, "en")
        else:
            result = ollama_correct(sample, "en")

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
