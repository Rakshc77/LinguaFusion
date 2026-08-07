# LFIE Endpoint Test Runner v2

Use this runner if the earlier runner gives:

```text
HTTP 422 for /lfie/entities
Field required: body.text
```

The backend is alive; the endpoint schema is just stricter than the first test runner expected.

## Run

Keep backend running in Terminal 1.

In Terminal 2:

```powershell
cd W:\OfflineSpeechTranslator_dev_v1.0\linguafusion_phase4_lfie_tests_v2
W:\OfflineSpeechTranslator_dev_v1.0\.venv\Scripts\activate
python run_lfie_endpoint_tests_v2.py
```

Expected final line:

```text
Phase 4 LFIE endpoint tests v2 completed.
```

The runner prints which payload mode each endpoint accepts.
