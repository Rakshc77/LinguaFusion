"""End-to-end Piper -> faster-whisper multilingual speed matrix.

Requires the local backend at http://127.0.0.1:8000. The test deliberately
uses smart_mode=offline so the score measures ASR rather than LLM correction.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
import wave
from pathlib import Path
from typing import Iterable

import requests


SERVER_URL = "http://127.0.0.1:8000"
TEMP_DIR = Path(__file__).resolve().parents[1] / "temp"
SPEEDS = (0.75, 1.0, 1.4)
SAMPLES = {
    "en": (
        "Today we are testing offline speech recognition at different speaking speeds. "
        "The quick brown fox jumps over the lazy dog near the railway station."
    ),
    "de": (
        "Heute testen wir die Offline-Spracherkennung mit verschiedenen Sprechgeschwindigkeiten. "
        "Der schnelle braune Fuchs springt über den faulen Hund am Bahnhof."
    ),
    "es": (
        "Hoy probamos el reconocimiento de voz sin conexión a diferentes velocidades. "
        "El rápido zorro marrón salta sobre el perro perezoso cerca de la estación."
    ),
    "hi": (
        "आज हम अलग-अलग बोलने की गति पर ऑफ़लाइन वाक् पहचान का परीक्षण कर रहे हैं। "
        "तेज़ भूरी लोमड़ी रेलवे स्टेशन के पास आलसी कुत्ते के ऊपर कूदती है।"
    ),
}


def _tokens(text: str) -> list[str]:
    # Python's ``\w`` does not keep every Devanagari combining mark attached
    # to its base letter, which inflated Hindi word counts and made WER invalid.
    # Group Unicode letters, numbers, and marks into orthographic word tokens.
    tokens: list[str] = []
    current: list[str] = []
    for char in unicodedata.normalize("NFC", (text or "").casefold()):
        if unicodedata.category(char)[0] in {"L", "M", "N"}:
            current.append(char)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens


def _edit_distance(reference: Iterable[str], hypothesis: Iterable[str]) -> int:
    ref = list(reference)
    hyp = list(hypothesis)
    previous = list(range(len(hyp) + 1))
    for ref_index, ref_token in enumerate(ref, start=1):
        current = [ref_index]
        for hyp_index, hyp_token in enumerate(hyp, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[hyp_index] + 1,
                    previous[hyp_index - 1] + (ref_token != hyp_token),
                )
            )
        previous = current
    return previous[-1]


def word_error_rate(reference: str, hypothesis: str) -> float:
    reference_tokens = _tokens(reference)
    return _edit_distance(reference_tokens, _tokens(hypothesis)) / max(len(reference_tokens), 1)


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / max(audio.getframerate(), 1)


def run_case(language: str, text: str, speed: float, smart_mode: str = "offline") -> dict[str, object]:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    speed_label = str(speed).replace(".", "_")
    audio_path = TEMP_DIR / f"speech_speed_matrix_{language}_{speed_label}.wav"
    try:
        tts_response = requests.post(
            f"{SERVER_URL}/tts/speak",
            data={"text": text, "lang": language, "speed": speed},
            timeout=180,
        )
        tts_response.raise_for_status()
        if not tts_response.headers.get("content-type", "").startswith("audio/"):
            raise RuntimeError(f"TTS returned non-audio data: {tts_response.text[:500]}")
        audio_path.write_bytes(tts_response.content)

        with audio_path.open("rb") as audio_file:
            stt_response = requests.post(
                f"{SERVER_URL}/stt/transcribe",
                files={"file": (audio_path.name, audio_file, "audio/wav")},
                data={"language": language, "smart_mode": smart_mode},
                timeout=600,
            )
        payload = stt_response.json()
        if not stt_response.ok or not payload.get("ok"):
            raise RuntimeError(f"STT failed: {payload}")

        transcript = str(payload.get("text", ""))
        raw_transcript = str(payload.get("raw_text", transcript))
        return {
            "language": language,
            "speed": speed,
            "audio_seconds": round(wav_duration(audio_path), 2),
            "reference_words": len(_tokens(text)),
            "transcript_words": len(_tokens(transcript)),
            "wer": round(word_error_rate(text, transcript), 4),
            "raw_wer": round(word_error_rate(text, raw_transcript), 4),
            "vad_fallback_used": bool(payload.get("vad_fallback_used", False)),
            "model": payload.get("model"),
            "provider": payload.get("provider"),
            "reference": text,
            "raw_transcript": raw_transcript,
            "transcript": transcript,
        }
    finally:
        audio_path.unlink(missing_ok=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    health = requests.get(f"{SERVER_URL}/health", timeout=10)
    health.raise_for_status()

    parser = argparse.ArgumentParser()
    parser.add_argument("languages", nargs="*", choices=sorted(SAMPLES))
    parser.add_argument("--smart-mode", default="offline", choices=("offline", "ollama"))
    args = parser.parse_args()

    requested_languages = args.languages or list(SAMPLES)
    unknown = [language for language in requested_languages if language not in SAMPLES]
    if unknown:
        raise ValueError(f"Unsupported test language(s): {', '.join(unknown)}")

    results = []
    for language in requested_languages:
        text = SAMPLES[language]
        for speed in SPEEDS:
            result = run_case(language, text, speed, smart_mode=args.smart_mode)
            results.append(result)
            print(
                f"{language} {speed:>4}x | {result['audio_seconds']:>6}s | "
                f"WER {float(result['wer']) * 100:>5.1f}% | "
                f"raw {float(result['raw_wer']) * 100:>5.1f}% | "
                f"provider={result['provider']} | VAD fallback={result['vad_fallback_used']}"
            )
            print(f"  {result['transcript']}")

    summary = {}
    for language in requested_languages:
        rows = [row for row in results if row["language"] == language]
        summary[language] = round(sum(float(row["wer"]) for row in rows) / len(rows), 4)

    print("\nSUMMARY")
    for language, average_wer in summary.items():
        print(f"{language}: average WER {average_wer * 100:.1f}%")
    print("RESULT_JSON=" + json.dumps({"results": results, "summary": summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
