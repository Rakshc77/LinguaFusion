from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.document_intelligence_service import analyze_document
from backend.services.piper_service import split_text_for_mixed_tts
from backend.services.translation_service import _looks_like_table_line


def test_speaking_duration_label():
    analysis = analyze_document("word " * 388)
    assert analysis["estimated_speaking_label"] == "2 min 41 sec"


def test_multilingual_tts_segmentation():
    text = "The first part is English. Hallo zusammen, diese Datei enthält deutsche Wörter. Después aparece una línea en español. कृपया इसे हिंदी में पढ़ें."
    segments = split_text_for_mixed_tts(text, fallback="en")
    langs = [lang for _, lang in segments]
    assert "en" in langs
    assert "de" in langs
    assert "es" in langs
    assert "hi" in langs


def test_mixed_script_sentence_split():
    text = "Hallo zusammen, dies ist Deutsch और यह हिंदी है. The system should detect English too."
    segments = split_text_for_mixed_tts(text, fallback="en")
    langs = [lang for _, lang in segments]
    assert langs[:2] == ["de", "hi"]
    assert langs[-1] == "en"


def test_table_line_detection():
    assert _looks_like_table_line("Item | Category | Value | Expected behavior")
    assert _looks_like_table_line("--- | --- | ---")
    assert not _looks_like_table_line("This is a normal sentence.")


if __name__ == "__main__":
    test_speaking_duration_label()
    test_multilingual_tts_segmentation()
    test_mixed_script_sentence_split()
    test_table_line_detection()
    print("Phase 3 beta2 validation tests passed")
