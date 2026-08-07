"""
LinguaFusion Phase 4 LFIE endpoint tests - resilient runner v2.

Run while backend is active:

    python run_lfie_endpoint_tests_v2.py

This runner auto-detects the exact request shape accepted by the current
LFIE endpoint implementation. It tries:
1. JSON object: {"text": "..."}
2. Raw JSON string: "..."
3. Query parameter: ?text=...
4. Form field: text=...

That makes it useful while the LFIE API schema is still being finalized.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8000"


def _read_json_response(req: urllib.request.Request, timeout: int = 90) -> dict:
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"ok": False, "raw": body}


def get_json(path: str) -> dict:
    req = urllib.request.Request(BASE_URL + path, headers={"Accept": "application/json"}, method="GET")
    return _read_json_response(req)


def post_json(path: str, payload) -> dict:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + path,
        data=raw,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Content-Length": str(len(raw)),
        },
        method="POST",
    )
    return _read_json_response(req)


def post_form(path: str, payload: dict) -> dict:
    raw = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + path,
        data=raw,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Content-Length": str(len(raw)),
        },
        method="POST",
    )
    return _read_json_response(req)


def post_query(path: str, payload: dict) -> dict:
    url = BASE_URL + path + "?" + urllib.parse.urlencode(payload)
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="POST")
    return _read_json_response(req)


def try_post(path: str, text: str | None = None, payload: dict | None = None) -> tuple[str, dict]:
    attempts = []

    if payload is not None:
        attempts.append(("json_object_payload", lambda: post_json(path, payload)))

    if text is not None:
        attempts.extend([
            ("json_object_text", lambda: post_json(path, {"text": text})),
            ("raw_json_string", lambda: post_json(path, text)),
            ("query_text", lambda: post_query(path, {"text": text})),
            ("form_text", lambda: post_form(path, {"text": text})),
        ])

    last_error = None
    for label, fn in attempts:
        try:
            result = fn()
            return label, result
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last_error = f"{label}: HTTP {exc.code}: {body}"
        except Exception as exc:
            last_error = f"{label}: {exc}"

    raise RuntimeError(f"All payload attempts failed for {path}. Last error: {last_error}")


def show(title: str, obj, max_chars: int = 2200) -> None:
    print(f"\n[{title}]")
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    print(text[:max_chars])


def assert_ok(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    health = get_json("/health")
    show("1 /health", health)
    assert_ok(health.get("ok") is True, "health.ok is not true")

    status = get_json("/lfie/status")
    show("2 /lfie/status", status)
    assert_ok(isinstance(status, dict), "LFIE status is not a JSON object")

    entity_text = (
        "Rajarshi reviewed a Wireless InSite result in MATLAB and Python before exporting the DOCX report. "
        "The document mentions Fraunhofer HHI, Karlsruhe Institute of Technology, Melsungen, Kolkata, New Delhi, "
        "Baden-Württemberg, 17 dBm, -73.5 dBm, 10 ns, 3.5 GHz, RMS Delay Spread, and PDP cosine similarity."
    )
    mode, entities = try_post("/lfie/entities", text=entity_text)
    show(f"3 /lfie/entities using {mode}", entities)
    assert_ok(isinstance(entities, dict), "entities response is not a JSON object")

    confidence_samples = [
        ("clean", "The Reader imported the DOCX file successfully. German text enthält Umlaute and Spanish text contiene acentos."),
        ("black_boxes", "Hindi section: ■■■■■ ■■■ ■■■■■ ■■■■■ ■■■ ■■■■■■■"),
        ("repetition", "mainstreammainstreammainstreammainstreammainstreammainstreammainstream"),
        ("ocr_noise", "Th crnn\n ed\n T\n wi CNIVUM Ww\n e dropped\n into ACR\n"),
    ]

    confidence_results = []
    for sample_id, sample_text in confidence_samples:
        mode, result = try_post("/lfie/confidence", text=sample_text)
        confidence_results.append({"id": sample_id, "mode": mode, "response": result})
    show("4 /lfie/confidence", {"results": confidence_results}, max_chars=4000)

    consensus_payload = {
        "candidates": [
            {
                "id": "clean",
                "text": "The scanned PDF should be dropped into OCR. Machine: Pump A-17. German line: Ölstand prüfen, Straße freihalten, Gerät schließen. Spanish line: La señal debe quedar visible después de la limpieza.",
                "source": "ocr_psm6",
            },
            {
                "id": "noisy",
                "text": "Th crann ed T wi CNIVUM Ww e dropped into ACR. The Vee Pits OVeMei",
                "source": "ocr_sparse",
            },
            {
                "id": "black_boxes",
                "text": "OCR Test ■■■■■ ■■■■■ Machine ■■■■■ German line ■■■■■",
                "source": "pdf_bad",
            },
        ]
    }
    mode, consensus = try_post("/lfie/consensus", payload=consensus_payload)
    show(f"5 /lfie/consensus using {mode}", consensus)
    assert_ok(isinstance(consensus, dict), "consensus response is not a JSON object")

    translate_payload = {
        "text": (
            "Energy dashboard notes for export testing.\n\n"
            "The operator reviewed voltage alerts, battery status, and a maintenance comment.\n"
            "Please preserve names such as Pandapower, OpenDSS, Excel, GitHub, and Kassel Grid Lab."
        ),
        "source_lang": "auto",
        "target_lang": "hi",
    }
    mode, translation = try_post("/lfie/translate", payload=translate_payload)
    show(f"6 /lfie/translate using {mode}", translation)
    assert_ok(isinstance(translation, dict), "translation response is not a JSON object")

    print("\nPhase 4 LFIE endpoint tests v2 completed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        raise
