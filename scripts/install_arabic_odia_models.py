"""One-time installer for Arabic/Odia OCR, TTS, and Odia ASR assets."""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config.paths import MMS_TTS_MODELS_DIR, ODIA_ASR_MODEL_DIR, TESSDATA_DIR


OCR_LANGS = ("eng", "deu", "spa", "hin", "ara", "ori", "osd")
TESSDATA_BASE = "https://github.com/tesseract-ocr/tessdata_best/raw/main"


def install_ocr() -> None:
    TESSDATA_DIR.mkdir(parents=True, exist_ok=True)
    for code in OCR_LANGS:
        target = TESSDATA_DIR / f"{code}.traineddata"
        if target.is_file() and target.stat().st_size > 100_000:
            print(f"OCR {code}: already installed")
            continue
        print(f"OCR {code}: downloading official tessdata_best pack")
        urllib.request.urlretrieve(f"{TESSDATA_BASE}/{code}.traineddata", target)


def install_tts() -> None:
    from transformers import AutoTokenizer, VitsModel

    for language, repo in (("ara", "facebook/mms-tts-ara"), ("ory", "facebook/mms-tts-ory")):
        target = MMS_TTS_MODELS_DIR / language
        if (target / "config.json").is_file():
            print(f"TTS {language}: already installed")
            continue
        print(f"TTS {language}: downloading {repo}")
        target.mkdir(parents=True, exist_ok=True)
        tokenizer = AutoTokenizer.from_pretrained(repo)
        model = VitsModel.from_pretrained(repo)
        tokenizer.save_pretrained(target)
        model.save_pretrained(target)
        del tokenizer, model


def install_odia_asr() -> None:
    if (ODIA_ASR_MODEL_DIR / "config.json").is_file():
        print("Odia ASR: already installed")
        return
    import torch
    from transformers import AutoProcessor, Wav2Vec2ForCTC

    repo = "facebook/mms-1b-all"
    print("Odia ASR: downloading Meta MMS base plus the Odia (ory) adapter; this is the largest download")
    ODIA_ASR_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    processor = AutoProcessor.from_pretrained(repo, target_lang="ory")
    model = Wav2Vec2ForCTC.from_pretrained(
        repo,
        target_lang="ory",
        ignore_mismatched_sizes=True,
        low_cpu_mem_usage=False,
    )
    processor.save_pretrained(ODIA_ASR_MODEL_DIR)
    model.save_pretrained(ODIA_ASR_MODEL_DIR)
    del processor, model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def main() -> int:
    print("Installing LinguaFusion Arabic and Odia offline assets")
    install_ocr()
    install_tts()
    install_odia_asr()
    print("Arabic and Odia assets are installed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Installation failed: {exc}", file=sys.stderr)
        raise
