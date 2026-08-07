from pathlib import Path
from tempfile import NamedTemporaryFile
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.document_intelligence_service import export_reader_document
from backend.services.document_translation_service import translate_document_preserving_format
from backend.services.ocr_service import extract_text_from_image


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    reader_text = "Hello\nनमस्ते, यह हिंदी परीक्षण है।\n16:00 | हिंदी निष्कर्ष | Hindi | Hindi voice"
    reader_pdf = export_reader_document(reader_text, "pdf", title="Beta8 Reader Export")
    assert_true(Path(reader_pdf).exists() and Path(reader_pdf).stat().st_size > 1000, "Reader Hindi PDF export failed")

    src = Path(NamedTemporaryFile(delete=False, suffix=".txt").name)
    src.write_text("Energy dashboard notes\n\nHindi line: कृपया तालिका और अनुच्छेद क्रम को साफ रखें।", encoding="utf-8")
    translated_pdf = translate_document_preserving_format(src, "en", "hi", "pdf")
    assert_true(Path(translated_pdf).exists() and Path(translated_pdf).stat().st_size > 1000, "Translate Hindi PDF export failed")

    csv_src = Path(NamedTemporaryFile(delete=False, suffix=".csv").name)
    csv_src.write_text("Category,Owner,Cost\nVenue,Anika,240.00 EUR\nProjector,Media Desk,-10.00 EUR\n", encoding="utf-8")
    csv_pdf = translate_document_preserving_format(csv_src, "en", "de", "pdf")
    assert_true(Path(csv_pdf).exists() and Path(csv_pdf).stat().st_size > 1000, "CSV PDF export failed")

    print("Phase 3 beta8 stabilization tests passed")


if __name__ == "__main__":
    main()
