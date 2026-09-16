"""One-time installer for LinguaFusion's seven desktop language packs.

Piper supplies English, German, French, Spanish and Hindi voices. Meta MMS
supplies Arabic/Odia voices plus Odia ASR. Tesseract data covers OCR for all
seven languages. Downloads are retained locally after the first setup.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config.paths import MMS_TTS_MODELS_DIR, ODIA_ASR_MODEL_DIR, PIPER_MODELS_DIR, TESSDATA_DIR


OCR_LANGS = ("eng", "deu", "fra", "spa", "hin", "ara", "ori", "osd")
TESSDATA_BASE = "https://github.com/tesseract-ocr/tessdata_best/raw/main"
PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
PIPER_VOICES = {
    "English": ("en/en_US/lessac/medium", "en_US-lessac-medium.onnx"),
    "German": ("de/de_DE/thorsten/medium", "de_DE-thorsten-medium.onnx"),
    "French": ("fr/fr_FR/tom/medium", "fr_FR-tom-medium.onnx"),
    "Spanish": ("es/es_ES/sharvard/medium", "es_ES-sharvard-medium.onnx"),
    "Hindi": ("hi/hi_IN/priyamvada/medium", "hi_IN-priyamvada-medium.onnx"),
}


def _download(url: str, target: Path, minimum_bytes: int) -> None:
    if target.is_file() and target.stat().st_size >= minimum_bytes:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    try:
        urllib.request.urlretrieve(url, partial)
        if partial.stat().st_size < minimum_bytes:
            raise RuntimeError(f"Downloaded file is unexpectedly small: {target.name}")
        partial.replace(target)
    finally:
        if partial.exists():
            partial.unlink()


def install_ocr() -> None:
    TESSDATA_DIR.mkdir(parents=True, exist_ok=True)
    for code in OCR_LANGS:
        target = TESSDATA_DIR / f"{code}.traineddata"
        if target.is_file() and target.stat().st_size > 100_000:
            print(f"OCR {code}: already installed")
            continue
        print(f"OCR {code}: downloading official tessdata_best pack")
        _download(f"{TESSDATA_BASE}/{code}.traineddata", target, 100_000)


def install_piper_voices() -> None:
    PIPER_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for language, (folder, filename) in PIPER_VOICES.items():
        model = PIPER_MODELS_DIR / filename
        config = PIPER_MODELS_DIR / f"{filename}.json"
        if model.is_file() and model.stat().st_size > 1_000_000 and config.is_file():
            print(f"Voice {language}: already installed")
            continue
        print(f"Voice {language}: downloading official Piper model")
        _download(f"{PIPER_BASE}/{folder}/{filename}", model, 1_000_000)
        _download(f"{PIPER_BASE}/{folder}/{filename}.json", config, 1_000)


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
    print("Installing LinguaFusion seven-language desktop assets")
    install_ocr()
    install_piper_voices()
    install_tts()
    install_odia_asr()
    print("All seven desktop language packs are installed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Installation failed: {exc}", file=sys.stderr)
        raise
