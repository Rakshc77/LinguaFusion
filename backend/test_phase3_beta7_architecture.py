from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.piper_service import split_text_for_mixed_tts
from backend.services.document_intelligence_service import export_reader_document, _devanagari_pdf_font_path


def test_structured_tts_plan_keeps_language_handover():
    text = """Opening
Welcome to the workshop.
German session
Die nächste Sitzung beginnt um 10:30 Uhr. Bitte prüfen Sie Wörter wie Größe, Straße und München.
Spanish session
La sesión de la tarde empieza en la sala Azul.
Hindi session
यह हिंदी सत्र की सूचना है। कृपया इसे हिंदी आवाज़ में पढ़ें।
Agenda table
10:30 | Prüfung der Ausgabe | German | German voice
14:00 | Resumen del día | Spanish | Spanish voice
"""
    segments = split_text_for_mixed_tts(text, fallback="en")
    langs = [lang for _, lang in segments]
    assert "en" in langs, segments
    assert "de" in langs, segments
    assert "es" in langs, segments
    assert "hi" in langs, segments
    # Metadata/table rows should not drive the entire row into German/Spanish.
    table_rows = [(seg, lang) for seg, lang in segments if "|" in seg]
    assert table_rows, segments
    assert all(lang in {"en", "hi"} for _, lang in table_rows), table_rows


def test_devanagari_pdf_export_uses_safe_renderer():
    assert _devanagari_pdf_font_path() is not None
    path = export_reader_document(
        "Hello\nयह हिंदी परीक्षण वाक्य है। MATLAB और Python पहचानने योग्य रहें।\nEnd",
        "pdf",
        title="LinguaFusion Test",
    )
    assert path.exists()
    assert path.stat().st_size > 1000


if __name__ == "__main__":
    test_structured_tts_plan_keeps_language_handover()
    test_devanagari_pdf_export_uses_safe_renderer()
    print("Phase 3 beta7 architecture tests passed")
