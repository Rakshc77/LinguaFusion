from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.translation_service import translate_with_views


def assert_ok(result):
    assert result.get("ok"), result
    text = result.get("translated_text", "")
    assert text.strip(), result
    assert "{'ok': False" not in text
    assert "Translation failed" not in text


def main() -> None:
    en_hi = """Please summarize the offline reader output after the audio playback finishes.

The LiDAR point cloud was cleaned in Blender, then the propagation result was compared with the measured received power.
"""
    result = translate_with_views(en_hi, "en", "hi")
    assert_ok(result)
    assert "\n\n" in result["translated_text"], result["translated_text"]

    es_hi = """El sistema debe traducir este texto sin mostrar un error interno.

Trabajo con documentos, audio grabado y reconocimiento automático del idioma.
"""
    result = translate_with_views(es_hi, "es", "hi")
    assert_ok(result)

    en_de = "The channel model uses ray tracing, interpolation, and cosine similarity to compare dynamic frames."
    result = translate_with_views(en_de, "en", "de")
    assert_ok(result)
    assert not result.get("views"), result

    mixed_en = "Heute testen wir den gemischten Modus. The first sentence contains German and English."
    result = translate_with_views(mixed_en, "auto", "en")
    assert_ok(result)
    assert not result.get("views"), result

    print("Phase 2 import translation validation tests passed")


if __name__ == "__main__":
    main()
