from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.entity_protection_service import protect_for_translation, restore_protected_terms, source_quality_normalize
from backend.services.transliteration_service import latin_to_devanagari_pronunciation, normalize_native_output
from backend.services.speech_quality_service import normalize_transcript_text
from backend.services.translation_service import high_confidence_translation_override, translate_with_views
from backend.services.language_service import detect_text_language
from backend.services.piper_service import split_text_for_mixed_tts


def assert_no_latin(text: str):
    assert not any(('A' <= ch <= 'Z') or ('a' <= ch <= 'z') for ch in text), text


def main():
    source = "Country roads take me home to the place I belong, west virginia"
    normalized = source_quality_normalize(source)
    assert "Country Roads" in normalized
    assert "West Virginia" in normalized

    protected, placeholders, entities = protect_for_translation(source, "en", "hi")
    assert placeholders
    assert any(e["canonical"] == "Country Roads" for e in entities), entities
    assert any(e["canonical"] == "West Virginia" for e in entities), entities
    restored = restore_protected_terms(protected, placeholders)
    assert "Country Roads" in restored and "West Virginia" in restored

    expected_song = "कंट्री रोड्स मुझे घर ले जाते हैं, उस जगह जहाँ मैं बिलॉन्ग करता हूँ, वेस्ट वर्जीनिया"
    argos_bad_song_1 = "कंट्री रोड्स मुझे उस स्थान पर ले जाते हैं जहाँ मैं हूं, पश्चिम कुंवारी"
    argos_bad_song_2 = "कंट्री रोड्स मुझे उस स्थान पर घर ले लो आई संबंधित, वेस्ट वर्जीनिया"
    assert normalize_native_output(argos_bad_song_1, "hi") == expected_song
    assert normalize_native_output(argos_bad_song_2, "hi") == expected_song
    assert high_confidence_translation_override(source, "en", "hi") == expected_song
    assert_no_latin(expected_song)

    assert latin_to_devanagari_pronunciation("belong") == "बिलॉन्ग"
    assert latin_to_devanagari_pronunciation("West Virginia") == "वेस्ट वर्जीनिया"
    assert latin_to_devanagari_pronunciation("Country Roads") == "कंट्री रोड्स"
    assert latin_to_devanagari_pronunciation("New Delhi") == "नई दिल्ली"
    assert latin_to_devanagari_pronunciation("Fraunhofer HHI") == "फ्राउनहोफर एचएचआई"

    fixed_place = normalize_native_output("मैं मेलसुंगेन, जर्मनीमें रहता हूँ।", "hi")
    assert fixed_place == "मैं मेलसुंगेन, जर्मनी में रहता हूँ।", fixed_place

    fixed_names = normalize_native_output("राजर्षि ने New DelhiमेंAmit Shahसे मुलाकात की।", "hi")
    assert fixed_names == "राजर्षि ने नई दिल्ली में अमित शाह से मुलाकात की।", fixed_names
    assert high_confidence_translation_override("Rajarshi met Amit Shah in New Delhi.", "en", "hi") == "राजर्षि ने नई दिल्ली में अमित शाह से मुलाकात की।"
    assert detect_text_language("Rajarshi met Amit Shah in New Delhi.")["language"] == "en"
    assert detect_text_language("I live in Melsungen, Germany.")["language"] == "en"
    live_translation = translate_with_views("I live in Melsungen, Germany.", "auto", "hi")
    assert live_translation["ok"], live_translation
    assert live_translation["translated_text"] == "मैं मेलसुंगेन, जर्मनी में रहता हूँ।", live_translation
    names_translation = translate_with_views("Rajarshi met Amit Shah in New Delhi.", "auto", "hi")
    assert names_translation["ok"], names_translation
    assert names_translation["translated_text"] == "राजर्षि ने नई दिल्ली में अमित शाह से मुलाकात की।", names_translation

    assert normalize_transcript_text("Raiarshi lives in Melzungen near west virginia") == "Rajarshi lives in Melsungen near West Virginia"
    german = normalize_transcript_text(
        "Heute teste ich auf Links-Fusion, deutschische Sätze, Ausnahmen und Eigennahmen korrekt erkennt. "
        "Besonders wichtig sind Wörter wie Baden-Wuttenburg, Nordrhein-Westfalen, Fraunhofer HHI und Kulturinstitut für Technologie."
    )
    assert "LinguaFusion" in german, german
    assert "deutsche Sätze" in german, german
    assert "Eigennamen" in german, german
    assert "Baden-Württemberg" in german, german
    assert "Karlsruher Institut für Technologie" in german, german

    reader_text = (
        "This paragraph combines English and German. Hallo zusammen, heute testen wir den Reader "
        "mit langen Sätzen, Eigennamen und technischen Begriffen. The system should correctly detect the language."
    )
    detected_reader = detect_text_language(reader_text)
    assert detected_reader.get("is_mixed"), detected_reader
    tts_segments = split_text_for_mixed_tts(reader_text, fallback="en")
    assert any(lang == "de" for _, lang in tts_segments), tts_segments
    assert any(lang == "en" for _, lang in tts_segments), tts_segments

    mixed = normalize_transcript_text(
        "The system should preserve what's like wireless insight, panel presumer, fauna for HHI and measurement. "
        "Therefore, I would like to translate the text into German and explain it as DocEx."
    )
    assert "Wireless InSite" in mixed, mixed
    assert "Pandaprosumer" in mixed, mixed
    assert "Fraunhofer HHI" in mixed, mixed
    assert "Melsungen" in mixed, mixed
    assert "DOCX" in mixed, mixed

    print("Phase 2 quality tests passed")


if __name__ == "__main__":
    main()
