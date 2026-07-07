import re
import subprocess
import tempfile
from pathlib import Path

from backend.config.paths import PROJECT_ROOT, WHISPER_EXE, WHISPER_MODELS_DIR

ROOT = PROJECT_ROOT
MODELS_DIR = WHISPER_MODELS_DIR

MODEL_PRIORITY = [
    "ggml-medium.bin",
    "ggml-small.bin",
    "ggml-base.bin",
    "ggml-tiny.bin",
]

NOISE_TOKENS = {
    "silence", "music", "musique", "musik", "applause", "laughter", "laughs",
    "noise", "background noise", "inaudible", "keyboard clicking", "guitar music",
}

LOG_PATTERNS = [
    r"load_backend:[^\n]*(?:\n|$)",
    r"whisper_[A-Za-z0-9_]+:[^\n]*(?:\n|$)",
    r"ggml_[A-Za-z0-9_]+:[^\n]*(?:\n|$)",
    r"read_audio_data:[^\n]*(?:\n|$)",
    r"output_txt:[^\n]*(?:\n|$)",
    r"system_info:[^\n]*(?:\n|$)",
    r"main:[^\n]*(?:\n|$)",
    r"sampling:[^\n]*(?:\n|$)",
    r"processing:[^\n]*(?:\n|$)",
    r"detect_language:[^\n]*(?:\n|$)",
    r"error:\s*input file not found ['\"]?false['\"]?[^\n]*(?:\n|$)",
    r"input file not found ['\"]?false['\"]?[^\n]*(?:\n|$)",
    r"whisper_print_timings:[^\n]*(?:\n|$)",
]


def _select_model() -> Path:
    for name in MODEL_PRIORITY:
        candidate = MODELS_DIR / name
        if candidate.exists():
            return candidate
    available = sorted(MODELS_DIR.glob("*.bin"))
    if available:
        return available[0]
    return MODELS_DIR / "ggml-small.bin"


def _normalize_language(language: str) -> str:
    language = (language or "auto").lower().replace("_", "-").split("-")[0]
    aliases = {
        "english": "en", "german": "de", "deutsch": "de",
        "spanish": "es", "espanol": "es", "español": "es",
        "hindi": "hi", "hin": "hi",
    }
    language = aliases.get(language, language)
    if language in {"en", "de", "es", "hi"}:
        return language
    return "auto"


def _remove_logs_anywhere(text: str) -> str:
    cleaned = text or ""
    for pattern in LOG_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    # Some builds print several log fragments in a single wrapped line.
    cleaned = re.sub(r"loaded\s+(?:BLAS|CPU|CUDA|Metal)[^.!?]{0,180}", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"using\s+BLAS\s+backend", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"no\s+GPU\s+found", " ", cleaned, flags=re.IGNORECASE)
    return cleaned


def _remove_noise_markers(text: str) -> str:
    def repl(match: re.Match) -> str:
        token = match.group(1).strip().lower()
        return " " if token in NOISE_TOKENS else match.group(0)
    text = re.sub(r"\(([^()]{1,60})\)", repl, text or "")
    text = re.sub(r"\[([^\[\]]{1,60})\]", repl, text)
    return text


def _remove_timestamps(text: str) -> str:
    text = re.sub(r"\[[0-9:.\s\-\>]+\]", " ", text or "")
    text = re.sub(r"\([0-9:.\s\-\>]+\)", " ", text)
    return text


def _normalize_spacing(text: str) -> str:
    text = text.replace("�", " ")
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])(?=\S)", r"\1 ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _dedupe_exact_repetition(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    pieces = re.split(r"(?<=[.!?])\s+", text)
    result = []
    counts = {}
    prev = ""
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        norm = re.sub(r"\W+", " ", piece.lower()).strip()
        if not norm:
            continue
        if norm == prev:
            continue
        counts[norm] = counts.get(norm, 0) + 1
        # Keep a repeated chorus twice, but block cascades.
        if counts[norm] > 2:
            continue
        result.append(piece)
        prev = norm
    return " ".join(result).strip()


def _clean_whisper_output(text: str) -> str:
    text = _remove_logs_anywhere(text or "")
    text = _remove_timestamps(text)
    text = _remove_noise_markers(text)
    text = re.sub(r"^\s*false\s*$", " ", text, flags=re.IGNORECASE | re.MULTILINE)
    lines = []
    for line in text.splitlines():
        line = _remove_logs_anywhere(line.strip())
        if not line:
            continue
        if line.startswith("[") and "]" in line:
            line = line.split("]", 1)[1].strip()
        line = _normalize_spacing(line)
        if line:
            lines.append(line)
    merged = _normalize_spacing(" ".join(lines))
    return _dedupe_exact_repetition(merged)


def _read_output_txt(output_prefix: Path) -> str:
    for candidate in [Path(str(output_prefix) + ".txt"), output_prefix.with_suffix(".txt")]:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8", errors="ignore")
    return ""


def _safe_audio_path(audio_path: Path) -> Path:
    path = Path(audio_path)
    if str(path).strip().lower() in {"", "false", "none", "0"}:
        raise FileNotFoundError(f"Invalid audio path passed to Whisper: {audio_path!r}")
    return path


def _run_whisper(audio_path: Path, language: str) -> dict:
    model_path = _select_model()
    try:
        audio_path = _safe_audio_path(audio_path)
    except Exception as exc:
        return {"ok": False, "text": "", "language": language, "model": str(model_path), "error": str(exc)}

    if not WHISPER_EXE.exists():
        return {"ok": False, "text": "", "language": language, "model": str(model_path), "error": f"Missing whisper executable: {WHISPER_EXE}"}
    if not model_path.exists():
        return {"ok": False, "text": "", "language": language, "model": str(model_path), "error": f"Missing whisper model: {model_path}"}
    if not audio_path.exists():
        return {"ok": False, "text": "", "language": language, "model": str(model_path), "error": f"Audio file not found: {audio_path}"}

    with tempfile.TemporaryDirectory() as temp_dir:
        output_prefix = Path(temp_dir) / "whisper_out"
        command = [
            str(WHISPER_EXE),
            "-m", str(model_path),
            "-f", str(audio_path),
            "-l", language,
            "--no-timestamps",
            "-otxt",
            "-of", str(output_prefix),
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True, cwd=str(ROOT))
        except subprocess.CalledProcessError as exc:
            combined = "\n".join([_read_output_txt(output_prefix), exc.stdout or "", exc.stderr or ""])
            cleaned = _clean_whisper_output(combined)
            return {"ok": bool(cleaned), "text": cleaned, "language": language, "model": str(model_path), "error": None if cleaned else _remove_logs_anywhere(exc.stderr or str(exc)).strip()}
        except Exception as exc:
            return {"ok": False, "text": "", "language": language, "model": str(model_path), "error": str(exc)}

        sidecar_text = _read_output_txt(output_prefix)
        cleaned = _clean_whisper_output(sidecar_text)
        if not cleaned:
            cleaned = _clean_whisper_output(result.stdout or "")
        if not cleaned:
            # stderr is diagnostic-only in most whisper.cpp builds; use it only after log cleanup.
            cleaned = _clean_whisper_output(result.stderr or "")
        return {"ok": True, "text": cleaned, "language": language, "model": str(model_path), "error": None}


def transcribe_audio(audio_path: Path, language: str = "auto") -> dict:
    language = _normalize_language(language)
    if language != "auto":
        return _run_whisper(audio_path, language)

    candidates = [_run_whisper(audio_path, "auto"), _run_whisper(audio_path, "en"), _run_whisper(audio_path, "de")]
    good = [c for c in candidates if c.get("text") and not re.search(r"load_backend|input file not found|whisper_|ggml_", c.get("text", ""), re.I)]
    if not good:
        return candidates[0]
    # Prefer the longest meaningful transcript; auto can under-transcribe songs.
    return sorted(good, key=lambda c: len(c.get("text", "")), reverse=True)[0]
