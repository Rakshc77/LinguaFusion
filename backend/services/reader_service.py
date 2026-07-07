from pathlib import Path
from backend.services.piper_service import speak_to_file


def read_text_to_audio(
    text: str,
    lang: str = "en",
    output_name: str = "reader_output.wav"
) -> Path:
    return speak_to_file(text, lang, output_name)