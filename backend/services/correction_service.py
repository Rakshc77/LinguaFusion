import json
import re
from typing import Dict

from backend.config.paths import STORAGE_DIR, migrate_legacy_storage_file

CORRECTIONS_FILE = migrate_legacy_storage_file("corrections.json")

DEFAULT_CORRECTIONS = {
    # User / local proper nouns
    "Mira Arshi": "Rajarshi",
    "Mira Arshee": "Rajarshi",
    "Mira Rishi": "Rajarshi",
    "Mira Arshi.": "Rajarshi.",
    "Raiarshi": "Rajarshi",
    "Rajashri": "Rajarshi",
    "Rajashi": "Rajarshi",
    "Rajashi": "Rajarshi",
    "rajashi": "Rajarshi",
    "Rajar she": "Rajarshi",

    # Places
    "Melzungen": "Melsungen",
    "Melzongren": "Melsungen",
    "Melzongen": "Melsungen",
    "Melsongren": "Melsungen",
    "Melsonghen": "Melsungen",
    "Baden-Wittenberg": "Baden-Württemberg",
    "Nordrein-Westfalen": "Nordrhein-Westfalen",

    # Public figures / common entities
    "Avid Shah": "Amit Shah",
    "Avit Shah": "Amit Shah",
    "Narendra Modey": "Narendra Modi",
    "Narendra Moody": "Narendra Modi",

    # Common ASR semantic corrections
    "military galaxy": "Milky Way galaxy",
    "Lingua Fusion": "LinguaFusion",
    "Shandong River": "Shenandoah River",
    "Mount Parma": "Mountain Mama",
    "Run to Rome": "Country Roads",
    "Mine is lady": "Miner's lady",
    "Get around her": "Gather 'round her",

    # Phase 2 proper-noun / song-title protection
    "west virginia": "West Virginia",
    "West virginia": "West Virginia",
    "country roads": "Country Roads",
    "Country roads": "Country Roads",
    "Take me home country roads": "Take Me Home, Country Roads",
    "Blue rich mountains": "Blue Ridge Mountains",
    "Blue Ridge Mountain": "Blue Ridge Mountains",
    "Shenandoa River": "Shenandoah River",
    "Shenandoah river": "Shenandoah River",
    "Malky Way": "Milky Way",
}



def _ensure_storage() -> None:
    STORAGE_DIR.mkdir(exist_ok=True)
    if not CORRECTIONS_FILE.exists():
        CORRECTIONS_FILE.write_text(
            json.dumps(DEFAULT_CORRECTIONS, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def load_corrections() -> Dict[str, str]:
    _ensure_storage()
    try:
        data = json.loads(CORRECTIONS_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return dict(DEFAULT_CORRECTIONS)
        merged = dict(DEFAULT_CORRECTIONS)
        merged.update({str(k): str(v) for k, v in data.items() if str(k).strip()})
        return merged
    except Exception:
        return dict(DEFAULT_CORRECTIONS)


def save_corrections(corrections: Dict[str, str]) -> None:
    _ensure_storage()
    cleaned = {
        str(k).strip(): str(v).strip()
        for k, v in corrections.items()
        if str(k).strip() and str(v).strip()
    }
    CORRECTIONS_FILE.write_text(
        json.dumps(cleaned, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def add_correction(wrong: str, correct: str) -> Dict[str, str]:
    corrections = load_corrections()
    wrong = (wrong or "").strip()
    correct = (correct or "").strip()
    if not wrong or not correct:
        raise ValueError("Both wrong and correct values are required.")
    corrections[wrong] = correct
    save_corrections(corrections)
    return corrections


def apply_corrections(text: str) -> str:
    if not text:
        return ""

    corrected = str(text)
    corrections = load_corrections()

    # Longest first prevents partial replacements from blocking phrase replacements.
    for wrong, correct in sorted(corrections.items(), key=lambda item: len(item[0]), reverse=True):
        wrong = wrong.strip()
        correct = correct.strip()
        if not wrong or not correct:
            continue

        # Phrase-aware, case-insensitive replacement. (?<!\w)/(?!\w) keeps words intact.
        pattern = re.compile(rf"(?<!\w){re.escape(wrong)}(?!\w)", re.IGNORECASE)
        corrected = pattern.sub(correct, corrected)

    return corrected
