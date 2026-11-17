"""Exercise native-browser isolation, including failure and deadline handling."""

import os
import subprocess
import sys
import textwrap

import pytest


@pytest.mark.parametrize("mode,expected", [
    ("ready", True), ("empty", False), ("failed", False),
    ("missing", False), ("timeout", False),
])
def test_probe_requires_verified_success_and_finishes_once(mode, expected):
    script = textwrap.dedent('''
        import sys
        from PySide6.QtCore import QCoreApplication, QTimer
        from desktop import webengine_probe as runtime
        mode = sys.argv[1]
        programs = {
            'ready': "print('LF_WEBENGINE_READY')",
            'empty': "pass",
            'failed': "print('LF_WEBENGINE_READY'); raise SystemExit(17)",
            'timeout': "import time; time.sleep(10)",
        }
        runtime.probe_command = lambda: ([sys.executable + '.missing'] if mode == 'missing'
            else [sys.executable, '-c', programs[mode]])
        app = QCoreApplication([])
        probe = runtime.BrowserRuntimeProbe(timeout_ms=500 if mode != 'timeout' else 100)
        results = []
        def completed(ok):
            results.append(ok)
            QTimer.singleShot(200, app.quit)
        probe.ready.connect(completed)
        probe.start()
        probe.start()  # Concurrent requests still launch only one check.
        QTimer.singleShot(3000, app.quit)
        app.exec()
        assert results == [mode == 'ready'], results
        assert not probe.running
        assert probe.result == (mode == 'ready')
        print('verified', probe.result)
    ''')
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    result = subprocess.run([sys.executable, "-c", script, mode], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"verified {expected}" in result.stdout


def test_real_browser_probe_cannot_terminate_its_desktop_host():
    script = textwrap.dedent('''
        from PySide6.QtCore import QTimer, QUrl
        from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
        from desktop.online_workspace import create_online_view
        app = QApplication([])
        window = QWidget()
        window._persist_settings = False
        layout = QVBoxLayout(window)
        view = create_online_view(window, 'https://app.example')
        layout.addWidget(view)
        window.show()
        outcomes = []
        def finished(ok):
            outcomes.append(ok)
            assert window.isVisible()
            if not ok:
                assert view.page() is None
                assert view.browser_button.isVisible()
                assert 'could not start' in view.status.text()
                assert not hasattr(window, '_online_profile')
            QTimer.singleShot(50, app.quit)
        view.loadFinished.connect(finished)
        view.setUrl(QUrl('about:blank'))  # No cloud, credentials or audio hardware.
        QTimer.singleShot(20000, app.quit)
        app.exec()
        assert len(outcomes) == 1, outcomes
        print('Desktop host survived; embedded browser available:', outcomes[0])
    ''')
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", LF_TEST_MODE="1",
               PYTHONIOENCODING="utf-8")
    result = subprocess.run([sys.executable, "-u", "-c", script], env=env,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Desktop host survived" in result.stdout
