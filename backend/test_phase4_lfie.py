
from backend.services.lfie_pipeline_service import (
    analyze_text,
    resolve_entities,
    confidence_report,
    consensus_report,
    parse_candidates_json,
)


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def test_lfie_analysis():
    text = "Rajarshi uses LinguaFusion with Wireless InSite, MATLAB, Python and 3.5 GHz data in Melsungen."
    result = analyze_text(text, workflow="reader")
    assert_true(result["ok"], "LFIE analysis did not return ok")
    assert_true(result["engine"] == "lfie_v2_shared", "Wrong LFIE engine name")
    assert_true(result["confidence"]["score"] > 0.5, "Confidence score unexpectedly low")
    names = {e["canonical"] for e in result["entities"]["entities"]}
    for expected in ["Rajarshi", "LinguaFusion", "Wireless InSite", "MATLAB", "Python", "Melsungen"]:
        assert_true(expected in names, f"Missing entity: {expected}")


def test_lfie_confidence_flags():
    bad = "■■■■ ■■■■"
    report = confidence_report(bad, workflow="translation")
    signal_names = {s["name"] for s in report["signals"]}
    assert_true("replacement_glyphs" in signal_names, "Black-box glyph signal missing")
    assert_true(report["score"] < 0.7, "Bad text score should be reduced")


def test_lfie_consensus():
    candidates = [
        {"provider": "bad", "text": "mainstream mainstream mainstream mainstream mainstream mainstream"},
        {"provider": "good", "text": "The OCR output contains readable German and Spanish text."},
    ]
    result = consensus_report(candidates, workflow="ocr")
    assert_true(result["ok"], "Consensus failed")
    assert_true(result["selected_provider"] == "good", "Consensus did not choose the cleaner candidate")


def test_parse_candidates_json():
    candidates = parse_candidates_json('[{"provider":"a","text":"hello"}, "world"]')
    assert_true(len(candidates) == 2, "Candidate parser length mismatch")
    assert_true(candidates[1]["text"] == "world", "String candidate was not normalized")


if __name__ == "__main__":
    test_lfie_analysis()
    test_lfie_confidence_flags()
    test_lfie_consensus()
    test_parse_candidates_json()
    print("Phase 4 LFIE tests passed")
