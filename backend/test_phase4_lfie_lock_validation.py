from backend.services.lfie_pipeline_service import (
    analyze_text,
    workflow_audit_report,
    quality_decision_from_audit,
    enforce_workflow_quality,
    export_quality_preflight,
    consensus_report,
    translate_with_lfie,
)
from backend.services.document_intelligence_service import analyze_document, export_reader_document
from backend.services.file_reader_service import extract_csv_text
from pathlib import Path
from tempfile import NamedTemporaryFile


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def test_phase4_version_marker():
    version = Path(__file__).resolve().parents[1].joinpath("VERSION").read_text(encoding="utf-8").strip()
    assert_true(version.startswith("1.0-rc1.") or version.startswith("1.0-rc2."), f"Unexpected version marker: {version}")


def test_lfie_clean_workflow_not_overblocked():
    result = enforce_workflow_quality(
        {"ok": True, "text": "The Reader imported the document. MATLAB and Wireless InSite remain recognizable."},
        workflow="reader",
        output_text="The Reader imported the document. MATLAB and Wireless InSite remain recognizable.",
        strict=False,
    )
    assert_true(result["ok"] is True, "LFIE should not break clean legacy workflow payloads")
    assert_true(result["lfie_decision"]["blocked"] is False, "Clean Reader output should not be blocked")
    assert_true(result["quality_gate"] in {"pass", "warning"}, "Clean Reader output should not require review")


def test_lfie_bad_export_blocked_in_strict_mode():
    preflight = export_quality_preflight("Hindi section: ■■■■■ ■■■■■ ■■■■■", workflow="translation", output_format="pdf", strict=True)
    assert_true(preflight["ok"] is False, "Broken PDF text must fail strict export preflight")
    assert_true(preflight["decision"]["blocked"] is True, "Broken PDF text must be blocked in strict mode")


def test_lfie_repetition_and_noise_are_reviewable():
    repeated = workflow_audit_report("translation", outputs={"text": "mainstreammainstreammainstreammainstreammainstreammainstream"})
    noisy = workflow_audit_report("ocr", outputs={"text": "Th crnn\n ed\n T\n wi CNIVUM Ww\n e dropped\n into ACR\n"})
    assert_true(quality_decision_from_audit(repeated)["requires_review"] is True, "Repeated output should require review")
    assert_true(quality_decision_from_audit(noisy)["action"] in {"warn", "review_required", "block"}, "Sparse OCR output should be warned or reviewed")


def test_consensus_selects_readable_candidate():
    result = consensus_report(
        [
            {"provider": "black_boxes", "text": "■■■■■ ■■■■■ ■■■■■"},
            {"provider": "repeated", "text": "translationtranslationtranslationtranslationtranslation"},
            {"provider": "clean", "text": "Machine Pump A-17. German line: Ölstand prüfen. Spanish line: La señal debe quedar visible."},
        ],
        workflow="ocr",
    )
    assert_true(result["selected_provider"] == "clean", "Consensus should select the readable candidate")


def test_reader_document_workflow_still_operates():
    text = "Reader lock validation.\n\nThis file mentions MATLAB, Python, Wireless InSite and Fraunhofer HHI.\nGuten Morgen zusammen. La prueba continúa. कृपया पाठ पढ़ें।"
    analysis = analyze_document(text)
    assert_true(analysis["ok"] is True, "Reader document analysis should still work")
    assert_true(analysis["words"] >= 10, "Reader document statistics should be populated")
    export_path = export_reader_document(text, "txt", title="LFIE Lock Validation")
    assert_true(export_path.exists() and export_path.stat().st_size > 0, "Reader TXT export should still work")
    export_path.unlink(missing_ok=True)


def test_csv_table_workflow_still_operates():
    path = Path(NamedTemporaryFile(delete=False, suffix=".csv").name)
    try:
        path.write_text("Item,Owner,Value\nVenue booking,Anika,240.00 EUR\nProjector rental,Media Desk,-10.00 EUR\n", encoding="utf-8")
        text = extract_csv_text(path)
        assert_true("Item | Owner | Value" in text, "CSV table header should be preserved")
        assert_true("Projector rental | Media Desk | -10.00 EUR" in text, "CSV row should be preserved")
    finally:
        path.unlink(missing_ok=True)


def test_translate_bridge_returns_structured_metadata():
    result = translate_with_lfie("The battery status was checked at 08:15.", source_lang="en", target_lang="de")
    assert_true(isinstance(result, dict), "LFIE translation bridge should return a dictionary")
    assert_true("analysis_before" in result, "LFIE translation bridge should include pre-translation analysis")
    assert_true("translation" in result, "LFIE translation bridge should include translation payload")


def test_lfie_entity_and_language_regression():
    report = analyze_text(
        "Rajarshi used MATLAB, Python and Wireless InSite in Melsungen. German line: Größe und Straße. Spanish line: número y dirección.",
        workflow="translation",
    )
    entities = report.get("entities", {}).get("entities", [])
    names = {item.get("canonical") for item in entities}
    assert_true("MATLAB" in names, "MATLAB entity missing")
    assert_true("Wireless InSite" in names, "Wireless InSite entity missing")
    assert_true(report.get("confidence", {}).get("score", 0) > 0.5, "Mixed but readable text should not be treated as broken")


if __name__ == "__main__":
    test_phase4_version_marker()
    test_lfie_clean_workflow_not_overblocked()
    test_lfie_bad_export_blocked_in_strict_mode()
    test_lfie_repetition_and_noise_are_reviewable()
    test_consensus_selects_readable_candidate()
    test_reader_document_workflow_still_operates()
    test_csv_table_workflow_still_operates()
    test_translate_bridge_returns_structured_metadata()
    test_lfie_entity_and_language_regression()
    print("Phase 4 LFIE lock validation tests passed")
