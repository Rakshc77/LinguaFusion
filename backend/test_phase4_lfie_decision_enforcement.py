from backend.services.lfie_pipeline_service import (
    workflow_audit_report,
    quality_decision_from_audit,
    enforce_workflow_quality,
    export_quality_preflight,
    consensus_report,
)


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def test_decision_pass_for_clean_output():
    audit = workflow_audit_report(
        workflow="ocr",
        outputs={"text": "Machine: Pump A-17. German line: Ölstand prüfen. Spanish line: La señal debe quedar visible."},
    )
    decision = quality_decision_from_audit(audit)
    assert_true(decision["action"] in {"allow", "warn"}, "Clean output should not require review/blocking")
    assert_true(decision["blocked"] is False, "Clean output should not be blocked")


def test_decision_review_for_broken_output():
    audit = workflow_audit_report(
        workflow="translation",
        outputs={"text": "■■■■■ ■■■■■ mainstreammainstreammainstreammainstreammainstream"},
    )
    decision = quality_decision_from_audit(audit, strict=False)
    assert_true(decision["requires_review"] is True, "Broken output should require review")
    assert_true(decision["action"] == "review_required", "Non-strict broken output should request review")


def test_strict_decision_blocks_broken_output():
    audit = workflow_audit_report(
        workflow="translation",
        outputs={"text": "■■■■■ ■■■■■ mainstreammainstreammainstreammainstreammainstream"},
    )
    decision = quality_decision_from_audit(audit, strict=True)
    assert_true(decision["blocked"] is True, "Strict broken output should be blocked")
    assert_true(decision["action"] == "block", "Strict broken output should return block action")


def test_enforce_workflow_quality_preserves_payload_non_strict():
    payload = {"ok": True, "text": "■■■■■ ■■■■■"}
    result = enforce_workflow_quality(payload, workflow="translation", output_text=payload["text"], strict=False)
    assert_true(result["ok"] is True, "Non-strict enforcement should preserve legacy ok status")
    assert_true(result["requires_review"] is True, "Broken output should be marked for review")
    assert_true("lfie_decision" in result, "Decision metadata missing")


def test_enforce_workflow_quality_blocks_strict():
    payload = {"ok": True, "text": "■■■■■ ■■■■■"}
    result = enforce_workflow_quality(payload, workflow="translation", output_text=payload["text"], strict=True)
    assert_true(result["ok"] is False, "Strict enforcement should set ok false")
    assert_true(result["lfie_decision"]["blocked"] is True, "Strict enforcement should mark blocked")


def test_export_preflight_blocks_bad_pdf_text():
    result = export_quality_preflight("■■■■■ ■■■■■", workflow="reader", output_format="pdf", strict=True)
    assert_true(result["ok"] is False, "Export preflight should block broken PDF text")
    assert_true(result["decision"]["blocked"] is True, "Preflight decision should be blocked")


def test_consensus_selects_non_blocked_candidate():
    candidates = [
        {"provider": "bad_pdf", "text": "■■■■■ ■■■■■"},
        {"provider": "clean_ocr", "text": "The OCR output contains readable text with München, Straße and señal."},
    ]
    result = consensus_report(candidates, workflow="ocr")
    assert_true(result["selected_provider"] == "clean_ocr", "Consensus should select readable candidate")


if __name__ == "__main__":
    test_decision_pass_for_clean_output()
    test_decision_review_for_broken_output()
    test_strict_decision_blocks_broken_output()
    test_enforce_workflow_quality_preserves_payload_non_strict()
    test_enforce_workflow_quality_blocks_strict()
    test_export_preflight_blocks_bad_pdf_text()
    test_consensus_selects_non_blocked_candidate()
    print("Phase 4 LFIE decision enforcement tests passed")
