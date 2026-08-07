from backend.services.lfie_pipeline_service import workflow_audit_report, attach_lfie_result


def test_workflow_audit_report_basic():
    report = workflow_audit_report(
        workflow="ocr",
        inputs={"file": "scan.pdf"},
        outputs={"text": "Machine: Pump A-17. German line: Ölstand prüfen. Spanish line: La señal debe quedar visible."},
    )
    assert report["ok"] is True
    assert report["workflow"] == "ocr"
    assert report["quality_gate"] in {"pass", "warning", "review_required"}
    assert "output_reports" in report
    assert "text" in report["output_reports"]


def test_attach_lfie_result_preserves_payload():
    payload = {"ok": True, "text": "Rajarshi uses MATLAB and Wireless InSite."}
    out = attach_lfie_result(payload, workflow="speech", output_text=payload["text"])
    assert out["ok"] is True
    assert "lfie" in out
    assert out["lfie"]["workflow"] == "speech"


def test_bad_text_requires_review():
    report = workflow_audit_report(workflow="translation", outputs={"text": "■■■■■ ■■■■■ mainstreammainstreammainstreammainstream"})
    assert report["quality_gate"] in {"warning", "review_required"}


if __name__ == "__main__":
    test_workflow_audit_report_basic()
    test_attach_lfie_result_preserves_payload()
    test_bad_text_requires_review()
    print("Phase 4 LFIE workflow integration tests passed")
