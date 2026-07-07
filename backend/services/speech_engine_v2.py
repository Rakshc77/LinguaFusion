from pathlib import Path
from typing import Dict

from backend.services.linguafusion_intelligence_engine import transcribe_with_lfie


def transcribe_speech_engine_v2(
    audio_path: Path,
    language: str = "auto",
    smart_mode: str = "offline",
    music_mode: bool = False,
) -> Dict[str, object]:
    """Compatibility wrapper. The actual pipeline is now LFIE v1."""
    return transcribe_with_lfie(
        Path(audio_path),
        language=language,
        smart_mode=smart_mode,
        music_mode=music_mode,
    )
