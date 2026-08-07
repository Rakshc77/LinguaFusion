from __future__ import annotations

from pathlib import Path


def test_language_detection_and_translation_codes():
    from backend.services.language_service import detect_text_language
    from backend.services.nllb_translation_service import LANG_CODE_MAP

    assert detect_text_language("مرحبا بكم في لينغوافيوجن")["language"] == "ar"
    assert detect_text_language("ଲିଙ୍ଗୁଆଫ୍ୟୁଜନକୁ ସ୍ୱାଗତ")["language"] == "or"
    assert LANG_CODE_MAP["ar"] == "arb_Arab"
    assert LANG_CODE_MAP["or"] == "ory_Orya"


def test_ocr_reader_and_all_client_language_lists():
    from backend.services.file_reader_service import OCR_LANGS as READER_OCR_LANGS
    from backend.services.ocr_service import OCR_LANGS

    assert OCR_LANGS["ar"] == "ara" and OCR_LANGS["or"] == "ori"
    assert READER_OCR_LANGS["ar"] == "ara" and READER_OCR_LANGS["or"] == "ori"
    root = Path(__file__).resolve().parents[1]
    desktop = (root / "desktop" / "main.py").read_text(encoding="utf-8")
    web = (root / "backend" / "mobile_web" / "app.js").read_text(encoding="utf-8")
    for name, code in (("Arabic", "ar"), ("Odia", "or")):
        assert f'("{name}", "{code}")' in desktop
        assert f'["{name}","{code}"]' in web


def test_tts_planner_switches_arabic_and_odia_scripts():
    from backend.services.piper_service import split_text_for_mixed_tts

    plan = split_text_for_mixed_tts("Welcome. مرحبا بالعالم. ନମସ୍କାର ବିଶ୍ୱ।", fallback="en")
    languages = [lang for _text, lang in plan]
    assert languages == ["en", "ar", "or"]


def test_odia_is_routed_away_from_whisper(monkeypatch, tmp_path):
    import backend.services.odia_asr_service as odia
    from backend.services.whisper_service import transcribe_audio

    audio = tmp_path / "odia.wav"
    audio.write_bytes(b"RIFF" + b"\x00" * 64)
    monkeypatch.setattr(odia, "transcribe_odia", lambda path: {"ok": True, "text": "ଠିକ", "language": "or", "model": "mock", "error": None})
    result = transcribe_audio(audio, "or")
    assert result["ok"] is True and result["language"] == "or" and result["text"] == "ଠିକ"


def test_missing_offline_models_fail_with_actionable_messages(tmp_path, monkeypatch):
    import backend.services.mms_tts_service as tts
    import backend.services.odia_asr_service as asr

    monkeypatch.setitem(tts.MODEL_DIRS, "or", tmp_path / "missing-tts")
    monkeypatch.setattr(asr, "ODIA_ASR_MODEL_DIR", tmp_path / "missing-asr")
    tts._cache.clear()
    try:
        tts._load("or")
    except FileNotFoundError as exc:
        assert "install_arabic_odia_models.ps1" in str(exc)
    else:
        raise AssertionError("Missing Odia TTS assets must not silently fall back")
    result = asr.transcribe_odia(tmp_path / "not-there.wav")
    assert result["ok"] is False and "Audio file not found" in result["error"]


def test_multilingual_pdf_export_shapes_complex_scripts(tmp_path):
    import fitz
    from backend.services.complex_script_pdf_service import write_unicode_pdf

    output = write_unicode_pdf(
        "English line\nمرحبا بالعالم\nଓଡ଼ିଆ ଭାଷା ପରୀକ୍ଷା\nहिंदी भाषा परीक्षण",
        "LinguaFusion multilingual export",
        tmp_path / "multilingual.pdf",
    )
    document = fitz.open(output)
    extracted = "".join(page.get_text() for page in document)
    assert "English" in extracted
    assert any("\u0600" <= char <= "\u06ff" or "\ufb50" <= char <= "\ufeff" for char in extracted)
    assert any("\u0b00" <= char <= "\u0b7f" for char in extracted)
    pixmap = document[0].get_pixmap(matrix=fitz.Matrix(1.2, 1.2), alpha=False)
    assert len(pixmap.samples) > 10_000
