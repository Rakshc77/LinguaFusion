"""Contract checks for the PC-hosted PWA and native mobile wrappers."""

from __future__ import annotations

import json
import html as html_module
import os
import plistlib
import re
import subprocess
import sys
import textwrap
import zipfile
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "backend" / "mobile_web"
ANDROID = ROOT / "android" / "LinguaFusionMobile"
IOS = ROOT / "ios" / "LinguaFusionMobile"


class _IdParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: set[str] = set()

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name == "id" and value:
                self.ids.add(value)


def test_mobile_web_shell_and_authenticated_api_contract():
    script = textwrap.dedent(
        """
        import os
        from pathlib import Path
        pairing_marker = Path("temp/mobile_test_paired.flag")
        access_db = Path("temp/mobile_test_access.db")
        pairing_marker.unlink(missing_ok=True)
        for suffix in ("", "-wal", "-shm"):
            Path(str(access_db) + suffix).unlink(missing_ok=True)
        os.environ["LINGUAFUSION_API_KEY"] = "mobile-test-key"
        os.environ["LINGUAFUSION_ADMIN_KEY"] = "mobile-admin-test-key"
        os.environ["LINGUAFUSION_PAIRING_TOKEN"] = "single-use-test-token"
        os.environ["LINGUAFUSION_PAIRED_FILE"] = str(pairing_marker)
        os.environ["LINGUAFUSION_ACCESS_DB"] = str(access_db)
        from fastapi.testclient import TestClient
        from backend.server import app
        with TestClient(app) as client:
            root = client.get("/")
            assert root.status_code == 200 and root.json()["auth_required"] is True
            shell = client.get("/mobile/")
            assert shell.status_code == 200 and "LinguaFusion Mobile" in shell.text
            assert client.get("/diagnostics").status_code == 401
            assert client.get("/diagnostics", headers={"X-API-Key": "mobile-test-key"}).status_code == 200
            assert client.get("/owner-api/clients").status_code == 401
            assert client.post("/pair", json={"token": "wrong"}).status_code == 403
            paired = client.post("/pair", json={"token": "single-use-test-token", "device_name": "Contract Android", "platform": "android"})
            assert paired.status_code == 200 and paired.json()["api_key"] != "mobile-test-key"
            first_device_key = paired.json()["api_key"]
            assert client.get("/diagnostics", headers={"X-API-Key": first_device_key}).status_code == 200
            assert pairing_marker.read_text(encoding="utf-8").strip() == "paired"
            assert client.post("/pair", json={"token": "single-use-test-token"}).status_code == 410

            admin = {"X-Admin-Key": "mobile-admin-test-key"}
            invitation = client.post("/owner-api/pairings", headers=admin, json={"public_url": "http://127.0.0.1:8000", "label": "Remote iPhone", "expires_minutes": 10})
            assert invitation.status_code == 200
            pairing = invitation.json()["pairing"]
            assert pairing["app_url"].startswith("linguafusion://pair?")
            assert "#pair=" in pairing["web_url"] and pairing["qr_data_uri"].startswith("data:image/svg+xml;base64,")
            second = client.post("/pair", json={"token": pairing["token"], "device_name": "Friend iPhone", "platform": "ios"})
            assert second.status_code == 200
            second_key = second.json()["api_key"]
            assert client.post("/pair", json={"token": pairing["token"]}).status_code == 410
            listed = client.get("/owner-api/clients", headers=admin).json()["clients"]
            friend = next(item for item in listed if item["name"] == "Friend iPhone")
            paused = client.post(f"/owner-api/clients/{friend['id']}/enabled", headers=admin, json={"enabled": False})
            assert paused.status_code == 200 and paused.json()["client"]["enabled"] is False
            assert client.get("/diagnostics", headers={"X-API-Key": second_key}).status_code == 403
            restored = client.post(f"/owner-api/clients/{friend['id']}/enabled", headers=admin, json={"enabled": True})
            assert restored.status_code == 200
            assert client.get("/diagnostics", headers={"X-API-Key": second_key}).status_code == 200
            assert client.delete(f"/owner-api/clients/{friend['id']}", headers=admin).status_code == 200
            assert client.get("/diagnostics", headers={"X-API-Key": second_key}).status_code == 401
        pairing_marker.unlink(missing_ok=True)
        for suffix in ("", "-wal", "-shm"):
            Path(str(access_db) + suffix).unlink(missing_ok=True)
        """
    )
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=45,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_mobile_feature_routes_with_mocked_engines():
    """Exercise every route consumed by the mobile UI without loading GPU models."""
    script = textwrap.dedent(
        r"""
        import os
        from pathlib import Path
        os.environ["LINGUAFUSION_API_KEY"] = "mobile-feature-key"
        from fastapi.testclient import TestClient
        import backend.server as server

        server.attach_lfie_result = lambda result, **kwargs: result
        server.workflow_audit_report = lambda *args, **kwargs: {"ok": True}
        server.analyze_text = lambda *args, **kwargs: {"ok": True}
        server.transcribe_speech_engine_v2 = lambda *args, **kwargs: {"ok": True, "text": "hello phone", "language": "en"}
        server.translate_with_views = lambda text, source, target: {"ok": True, "translated_text": f"{target}:{text}", "route": [source, target]}
        server.extract_text_from_image = lambda *args, **kwargs: {"ok": True, "text": "invoice 42", "language": "en"}
        server.extract_text_from_file = lambda *args, **kwargs: {"ok": True, "text": "reader text", "file_type": "txt", "method": "mock"}
        server.normalize_document_text = lambda text: text
        server.detect_text_language = lambda text: {"ok": True, "language": "en", "confidence": 1.0, "is_mixed": False}
        server.analyze_document = lambda text: {"ok": True, "characters": len(text)}
        audio_path = server.TEMP_DIR / "mobile_contract_audio.wav"
        audio_path.write_bytes(b"RIFF" + b"\x00" * 64)
        server.speak_to_file = lambda *args, **kwargs: audio_path
        headers = {"X-API-Key": "mobile-feature-key"}

        with TestClient(server.app) as client:
            assert client.post("/translate", data={"text": "hello", "source_lang": "en", "target_lang": "de"}).status_code == 401
            translated = client.post("/translate", headers=headers, data={"text": "hello", "source_lang": "en", "target_lang": "de"})
            assert translated.status_code == 200 and translated.json()["translated_text"] == "de:hello"
            speech = client.post("/stt/transcribe", headers=headers, files={"file": ("speech.wav", b"RIFF" + b"\x00" * 64, "audio/wav")}, data={"language": "auto", "smart_mode": "free_auto"})
            assert speech.status_code == 200 and speech.json()["text"] == "hello phone"
            ocr = client.post("/ocr/extract", headers=headers, files={"file": ("scan.png", b"image", "image/png")}, data={"lang": "auto", "ai_cleanup": "false"})
            assert ocr.status_code == 200 and ocr.json()["text"] == "invoice 42"
            reader = client.post("/reader/import", headers=headers, files={"file": ("doc.txt", b"reader text", "text/plain")}, data={"lang": "auto"})
            assert reader.status_code == 200 and reader.json()["text"] == "reader text"
            reader_translation = client.post("/reader/translate", headers=headers, data={"text": "reader text", "source_lang": "auto", "target_lang": "es"})
            assert reader_translation.status_code == 200 and reader_translation.json()["translation"]["translated_text"] == "es:reader text"
            for route in ("/tts/speak", "/reader/speak"):
                spoken = client.post(route, headers=headers, data={"text": "hello", "lang": "en", "speed": "1.0"})
                assert spoken.status_code == 200 and spoken.headers["content-type"].startswith("audio/wav") and spoken.content.startswith(b"RIFF")
        audio_path.unlink(missing_ok=True)
        """
    )
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=60,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_pwa_controls_manifest_and_javascript_ids_are_consistent():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    javascript = (WEB / "app.js").read_text(encoding="utf-8")
    stylesheet = (WEB / "app.css").read_text(encoding="utf-8")
    theme_script = (WEB / "linguafusion-themes.js").read_text(encoding="utf-8")
    theme_styles = (WEB / "linguafusion-themes.css").read_text(encoding="utf-8")
    structure_styles = (WEB / "linguafusion-structure.css").read_text(encoding="utf-8")
    compact_javascript = re.sub(r"\s+", "", javascript)
    compact_stylesheet = re.sub(r"\s+", "", stylesheet)
    parser = _IdParser()
    parser.feed(html)
    referenced_ids = set(re.findall(r'\$\("([A-Za-z][A-Za-z0-9_-]*)"\)', javascript))
    assert referenced_ids <= parser.ids, sorted(referenced_ids - parser.ids)
    manifest = json.loads((WEB / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/mobile/"
    assert {"translateView", "speechView", "ocrView", "readerView", "tasksView", "settingsView", "speechFileName", "ocrFileName", "readerFileName", "speechWaveform", "speechStages", "motionDropdown", "taskList", "queueTaskTranslation", "taskAudioFile", "agentNaturalRequest", "createAgentPlan", "confirmAgentPlan", "discardAgentPlan", "agentPlanPreview"} <= parser.ids
    for marker in ["WavRecorder", "NativeWavRecorder", "nativeRecorderAvailable", "navigator.mediaDevices?.getUserMedia", "/stt/transcribe", "/ocr/extract", "/reader/import", 'endpoint="/speak"', "/reader/speak", "X-API-Key", "claimPairingToken", "/api/mobile/pair/exchange"]:
        assert marker in javascript
    assert "overflow-x:clip" in compact_stylesheet
    assert "minmax(0,1fr)" in compact_stylesheet
    assert "native app / HTTPS" in javascript
    assert {"offlineBanner", "retryConnection"} <= parser.ids
    assert "setInterval(probe,8000)" in compact_javascript
    assert "copyText" in javascript and "document.execCommand" in javascript
    assert "state.probing" in javascript and "validateFile" in javascript
    assert "linguafusionAudio" in javascript and "LFNativeIOSAudioResult" in javascript
    for marker in ["setSpeechStage", "revealSpeechText", "startSpeechWaveFeedback", "createAnalyser", "buildWave", "motionDropdown", "applyMotionMode"]:
        assert marker in javascript
    assert "PC backend is offline" in html
    assert ".offline-banner" in stylesheet
    assert "--safe-top:env(safe-area-inset-top,0px)" in compact_stylesheet
    assert "padding:calc(12px+var(--safe-top))16px12px" in compact_stylesheet
    assert "prefers-reduced-motion" in stylesheet
    service_worker = (WEB / "sw.js").read_text(encoding="utf-8")
    assert 'linguafusion-mobile-v26' in service_worker
    for marker in ["/agent/tasks", "/agent/artifacts/audio", "loadAgentTasks", "runTaskAction"]:
        assert marker in javascript
    assert "if(response.ok)" in service_worker
    assert "caches.match(event.request,{ignoreSearch:true})" in service_worker
    assert "PC backend is offline" in service_worker

    # Native Android and iOS clients load this PWA, so only phone-optimized
    # looks belong in its selector. Typography remains an independent choice.
    assert 'populateThemeSelect($("themeDropdown"), { platform:"mobile" })' in javascript
    assert 'populateFontSelect($("fontDropdown"))' in javascript
    assert 'id="themeDropdown"' in html and 'id="fontDropdown"' in html
    for theme_id in (
        "soft-ui", "sunset", "brutalist", "warm-editorial", "glass-dark",
        "neon-arcade", "warm-minimal", "bold-mono", "nature-calm",
    ):
        assert f'id:"{theme_id}"' in theme_script
        assert f'[data-theme="{theme_id}"]' in theme_styles
    for desktop_only_id in (
        "broadsheet", "editorial-split", "reading-room", "gallery",
        "editorial-luxe", "glass-dark", "aurora-glass", "blueprint", "zen",
    ):
        assert f'id:"{desktop_only_id}"' in theme_script
    for font_id in ("modern", "friendly", "accessible", "editorial", "classic", "technical"):
        assert f'id:"{font_id}"' in theme_script
        assert f'[data-font="{font_id}"]' in theme_styles
    assert "platforms.includes(platform)" in theme_script
    assert "lf-theme" in theme_script and "lf-font" in theme_script
    assert ".lf-speech" in structure_styles
    assert ".speech-stages" in stylesheet
    assert ".speech-waveform" in stylesheet
    assert 'data-motion="off"' in stylesheet


def test_android_apk_and_ios_project_are_installation_ready():
    apk = ANDROID / "dist" / "LinguaFusionMobile-debug.apk"
    assert apk.exists() and apk.stat().st_size > 10_000
    with zipfile.ZipFile(apk) as package:
        entries = set(package.namelist())
    assert {"AndroidManifest.xml", "classes.dex", "resources.arsc"} <= entries
    android_manifest = (ANDROID / "AndroidManifest.xml").read_text(encoding="utf-8")
    assert "android.permission.RECORD_AUDIO" in android_manifest
    assert "android:networkSecurityConfig" in android_manifest
    assert 'android:scheme="linguafusion"' in android_manifest
    assert 'android:host="pair"' in android_manifest
    android_source = (ANDROID / "src" / "com" / "linguafusion" / "mobile" / "MainActivity.java").read_text(encoding="utf-8")
    android_build = (ANDROID / "build_apk.ps1").read_text(encoding="utf-8")
    javascript = (WEB / "app.js").read_text(encoding="utf-8")
    theme_script = (WEB / "linguafusion-themes.js").read_text(encoding="utf-8")
    for storage_key in ["lf.server", "lf.key"]:
        assert storage_key in javascript
        assert storage_key in android_source
    assert "PermissionRequest.RESOURCE_AUDIO_CAPTURE" in android_source
    assert "isTrustedOrigin(request.getOrigin())" in android_source
    assert "onRequestPermissionsResult" in android_source
    assert "showBackendUnavailable" in android_source
    assert "onReceivedError" in android_source and "onReceivedHttpError" in android_source
    assert "Retry connection" in android_source
    assert "handlePairingIntent" in android_source and 'pairingServer + "/pair"' in android_source
    assert "startAudioRecording" in android_source and "AudioRecord" in android_source
    assert "connection.disconnect()" in android_source
    assert "setOnApplyWindowInsetsListener" in android_source
    assert "WindowInsets.Type.systemBars()" in android_source
    assert ".setInsets(insetTypes, Insets.NONE)" in android_source
    assert "setSystemBarTheme" in android_source and "setSystemBarTheme" in theme_script
    assert "status==502||status==503||status==504" in android_source
    assert "The PC backend is offline" in android_source
    assert "--version-code 5" in android_build and "--version-name 1.4" in android_build

    plist_path = IOS / "LinguaFusionMobile" / "Info.plist"
    with plist_path.open("rb") as stream:
        plist = plistlib.load(stream)
    assert "NSLocalNetworkUsageDescription" in plist
    assert "NSMicrophoneUsageDescription" in plist
    assert plist["CFBundleURLTypes"][0]["CFBundleURLSchemes"] == ["linguafusion"]
    assert plist["CFBundleShortVersionString"] == "1.4" and plist["CFBundleVersion"] == "4"
    assert "NSAllowsArbitraryLoadsInWebContent" not in plist.get("NSAppTransportSecurity", {})
    project = (IOS / "LinguaFusionMobile.xcodeproj" / "project.pbxproj").read_text(encoding="utf-8")
    ios_webview = (IOS / "LinguaFusionMobile" / "MobileWebView.swift").read_text(encoding="utf-8")
    assert "lf.server" in ios_webview and "lf.key" in ios_webview
    assert "didFailProvisionalNavigation" in ios_webview
    assert "AVAudioRecorder" in ios_webview and "linguafusionAudio" in ios_webview
    assert "trustedOrigin" in ios_webview and "cancelAudioRecording" in ios_webview
    assert "[502, 503, 504].contains(response.statusCode)" in ios_webview
    ios_content = (IOS / "LinguaFusionMobile" / "ContentView.swift").read_text(encoding="utf-8")
    assert "backendUnavailable" in ios_content and "Retry connection" in ios_content
    assert "handlePairingLink" in ios_content and '"/pair"' in ios_content
    assert "validateConnection" in ios_content and '"/diagnostics"' in ios_content
    assert "[502, 503, 504].contains(http.statusCode)" in ios_content
    credential_store = (IOS / "LinguaFusionMobile" / "CredentialStore.swift").read_text(encoding="utf-8")
    assert "kSecClassGenericPassword" in credential_store and "loadOrMigrateAPIKey" in credential_store
    for source in ["LinguaFusionMobileApp.swift", "ContentView.swift", "MobileWebView.swift", "CredentialStore.swift"]:
        assert source in project


def test_offline_pairing_qr_card_generation(tmp_path):
    from scripts.generate_mobile_pairing_qr import create_pairing_card

    url = "linguafusion://pair?server=http%3A%2F%2F192.168.2.36%3A8000&token=one-time-token"
    fallback = "http://192.168.2.36:8000/mobile/?pair=one-time-token"
    html_path, svg_path = create_pairing_card(url, tmp_path / "pair.html", fallback)
    assert html_path.exists() and svg_path.exists()
    rendered_html = html_path.read_text(encoding="utf-8")
    assert html_module.escape(url, quote=True) in rendered_html
    assert html_module.escape(fallback, quote=True) in rendered_html
    assert "Open LinguaFusion" in rendered_html
    svg = svg_path.read_text(encoding="utf-8")
    assert "<svg" in svg and ("<path" in svg or "<rect" in svg)
