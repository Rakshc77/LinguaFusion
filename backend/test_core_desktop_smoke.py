"""Headless startup smoke test for the real PySide6 desktop window."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap


def test_desktop_window_starts_and_closes():
    script = textwrap.dedent(
        """
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from desktop.main import LinguaFusionWindow

        app = QApplication([])
        window = LinguaFusionWindow()
        expected_pages = {"Translate", "Reader", "Speech", "OCR", "Notes", "Access", "Settings"}
        assert expected_pages <= set(window.page_index)
        assert window.minimumWidth() == 1180
        window.show()

        def finish():
            window.close()
            app.quit()

        QTimer.singleShot(1500, finish)
        exit_code = app.exec()
        window.executor.shutdown(wait=True, cancel_futures=True)
        raise SystemExit(exit_code)
        """
    )
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["SDL_AUDIODRIVER"] = "dummy"
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert completed.returncode == 0, (
        f"Desktop startup failed.\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
