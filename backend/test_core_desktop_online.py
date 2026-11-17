"""Desktop mode switching without network, provider calls or audio hardware."""

import os
import subprocess
import sys
import textwrap
import types

import pytest


@pytest.mark.parametrize("origin,allowed", [
    ("https://app.example", True),
    ("https://app.example:443/path", True),
    ("http://app.example", False),
    ("https://app.example.attacker.test", False),
    ("https://app.example:8443", False),
    ("https://user@app.example", False),
    ("file:///app.example", False),
])
def test_microphone_requires_configured_secure_origin(origin, allowed):
    from desktop.online_workspace import trusted_origin
    assert trusted_origin(origin, "https://app.example") is allowed


def test_shared_browser_session_permissions_and_export_cancel(monkeypatch, tmp_path):
    from PySide6.QtCore import QUrl
    from desktop import online_workspace as online

    class Signal:
        def connect(self, callback):
            self.callback = callback

    class Profile:
        def __init__(self, *args):
            self.downloadRequested = Signal()

    class Page:
        Feature = types.SimpleNamespace(MediaAudioCapture="microphone")
        PermissionGrantedByUser, PermissionDeniedByUser = "allow", "deny"

        def __init__(self, profile, view):
            self.profile = profile
            self.featurePermissionRequested = Signal()
            self.current_url = QUrl("https://app.example/pilot/")
            self.decisions = []

        def url(self):
            return self.current_url

        def setFeaturePermission(self, origin, feature, decision):
            self.decisions.append(decision)

    class View:
        visible = True

        def setUrl(self, url):
            pass

        def setPage(self, page):
            self.page = page

        def isVisible(self):
            return self.visible

    monkeypatch.setitem(sys.modules, "PySide6.QtWebEngineWidgets",
                        types.SimpleNamespace(QWebEngineView=View))
    monkeypatch.setitem(sys.modules, "PySide6.QtWebEngineCore",
                        types.SimpleNamespace(QWebEnginePage=Page, QWebEngineProfile=Profile))
    window = types.SimpleNamespace(_persist_settings=False)
    first = online.create_online_view(window, "https://app.example")
    second = online.create_online_view(window, "https://app.example")
    assert not hasattr(window, "_online_profile")
    first.setUrl(QUrl("https://app.example/pilot/"))
    second.setUrl(QUrl("https://app.example/pilot/"))
    assert first.page.profile is second.page.profile
    prompts = []

    def approve(*args):
        prompts.append(args)
        return online.QMessageBox.Yes

    monkeypatch.setattr(online.QMessageBox, "question", approve)
    permission = first.page.featurePermissionRequested.callback
    for origin, feature in [("https://other.example", "microphone"),
                            ("https://app.example", "camera")]:
        permission(QUrl(origin), feature)
        assert first.page.decisions[-1] == "deny"
    first.visible = False
    permission(QUrl("https://app.example"), "microphone")
    assert first.page.decisions[-1] == "deny" and not prompts
    first.visible = True
    permission(QUrl("https://app.example"), "microphone")
    assert first.page.decisions[-1] == "allow" and len(prompts) == 1
    monkeypatch.setattr(online.QMessageBox, "question", lambda *args: online.QMessageBox.No)
    permission(QUrl("https://app.example"), "microphone")
    assert first.page.decisions[-1] == "deny"

    class Download:
        def __init__(self, url):
            self.address, self.accepted, self.cancelled = url, False, False

        def url(self):
            return QUrl(self.address)

        def suggestedFileName(self):
            return "transcript.txt"

        def cancel(self):
            self.cancelled = True

        def accept(self):
            self.accepted = True

        def setDownloadDirectory(self, value):
            self.directory = value

        def setDownloadFileName(self, value):
            self.filename = value

    monkeypatch.setattr(online.QFileDialog, "getSaveFileName", lambda *args: ("", ""))
    cancelled = Download("blob:https://app.example/export-id")
    window._online_profile.downloadRequested.callback(cancelled)
    assert cancelled.cancelled and not cancelled.accepted
    monkeypatch.setattr(online.QFileDialog, "getSaveFileName",
                        lambda *args: (str(tmp_path / "chosen.txt"), ""))
    accepted = Download("blob:https://app.example/export-id")
    window._online_profile.downloadRequested.callback(accepted)
    assert accepted.accepted and accepted.filename == "chosen.txt"
    assert accepted.directory == str(tmp_path)
    untrusted = Download("https://other.example/file.txt")
    window._online_profile.downloadRequested.callback(untrusted)
    assert untrusted.cancelled and not untrusted.accepted


def test_online_switch_preserves_local_text_and_stops_hidden_playback():
    script = textwrap.dedent('''
        import sys
        import types
        from PySide6.QtCore import Signal
        from PySide6.QtWidgets import QApplication, QWidget

        class Browser(QWidget):
            loadFinished = Signal(bool)
            def __init__(self):
                super().__init__()
                self.urls = []
                self.scripts = []
            def setUrl(self, url):
                self.urls.append(url.toString())
            def reload(self):
                pass
            def page(self):
                return self
            def runJavaScript(self, script):
                self.scripts.append(script)

        sys.modules['PySide6.QtWebEngineWidgets'] = types.SimpleNamespace(QWebEngineView=Browser)
        sys.modules['sounddevice'] = types.SimpleNamespace()
        from desktop.main import LinguaFusionWindow, CLOUD_APP_URL
        LinguaFusionWindow._poll_backend_health_on_startup = lambda self: None
        LinguaFusionWindow.load_ai_provider_settings = lambda self: None
        app = QApplication([])
        window = LinguaFusionWindow()
        window.show()
        app.processEvents()
        view = window.online_workspace_view
        assert view.urls == []  # No cloud navigation before the Online gesture.
        window.translate_input.setPlainText('Grüße from the local workspace')
        window.speech_is_recording = True
        window.set_workspace_mode(True)
        assert not window.online_mode and not view.urls
        window.speech_is_recording = False
        window.set_workspace_mode(True)
        assert window.online_mode
        assert view.urls == [CLOUD_APP_URL + '/pilot/']
        assert not window.page_scroll.isVisible()
        assert not window.sidebar.isVisible()
        assert window.online_workspace.isVisible()
        assert window.online_mode_button.isChecked()
        window.online_workspace_load_finished(False)
        assert 'Could not load' in window.online_workspace_status.text()
        window.online_workspace_load_finished(True)
        assert 'same tools' in window.online_workspace_status.text()
        window.set_workspace_mode(False)
        assert not window.online_mode
        assert window.page_scroll.isVisible() and window.sidebar.isVisible()
        assert "pagehide" in view.scripts[-1]
        assert window.translate_input.toPlainText() == 'Grüße from the local workspace'
        window.set_workspace_mode(True)
        assert len(view.urls) == 1  # Switching keeps Online inputs and draft state.
        window.resize(1180, 720)
        window.update_responsive_layout()
        assert window.scroll_hint.isHidden()
        assert window.system_badge.text() == 'Online workspace'
        window.set_workspace_mode(False)
        window.close()
        window.executor.shutdown(wait=True, cancel_futures=True)
    ''')
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", SDL_AUDIODRIVER="dummy",
               LF_TEST_MODE="1", PYTHONIOENCODING="utf-8")
    completed = subprocess.run([sys.executable, "-c", script], env=env,
                               capture_output=True, text=True, timeout=60)
    assert completed.returncode == 0, completed.stdout + completed.stderr
