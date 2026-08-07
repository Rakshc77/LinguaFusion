from backend.services.lfie_pipeline_service import confidence_report, consensus_report


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def test_repetition_quality_signal():
    report = confidence_report("mainstreammainstreammainstreammainstreammainstreammainstreammainstream")
    signals = {s["name"] for s in report["signals"]}
    assert_true("repeated_substring" in signals, "Repeated substring signal missing")
    assert_true(report["level"] == "low", "Repeated substring should be low confidence")


def test_sparse_ocr_quality_signal():
    report = confidence_report("Th crnn\n ed\n T\n wi CNIVUM Ww\n e dropped\n into ACR\n")
    signals = {s["name"] for s in report["signals"]}
    assert_true("ocr_sparse_noise" in signals, "Sparse OCR signal missing")
    assert_true(report["level"] in {"low", "medium"}, "Sparse OCR should not be high confidence")


def test_consensus_rejects_broken_output():
    candidates = [
        {"provider": "clean", "text": "The scanned PDF should be dropped into OCR. Machine: Pump A-17. German line: Ölstand prüfen, Straße freihalten, Gerät schließen."},
        {"provider": "noise", "text": "Th crnn\n ed\n T\n wi CNIVUM Ww\n e dropped\n into ACR\n"},
        {"provider": "boxes", "text": "OCR Test ■■■■■ ■■■■■ Machine ■■■■■"},
    ]
    result = consensus_report(candidates, workflow="ocr")
    assert_true(result["selected_provider"] == "clean", "Consensus did not choose the clean candidate")


if __name__ == "__main__":
    test_repetition_quality_signal()
    test_sparse_ocr_quality_signal()
    test_consensus_rejects_broken_output()
    print("Phase 4 LFIE API contract tests passed")
