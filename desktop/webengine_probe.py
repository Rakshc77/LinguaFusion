"""Check Chromium in a disposable process before it can affect the main window."""

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

READY_MARKER = "LF_WEBENGINE_READY"


def probe_command():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--webengine-probe"]
    return [sys.executable, "-m", "desktop.webengine_probe"]


class BrowserRuntimeProbe(QObject):
    ready = Signal(bool)

    def __init__(self, parent=None, timeout_ms=15000):
        super().__init__(parent)
        self.result = None
        self.running = False
        self.exit_code = None
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(Path(__file__).resolve().parents[1]))
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(timeout_ms)
        self.timer.timeout.connect(self._timeout)

    def start(self):
        if self.result is not None:
            return
        elif not self.running:
            self.running = True
            command = probe_command()
            self.process.setProgram(command[0])
            self.process.setArguments(command[1:])
            self.timer.start()
            self.process.start()

    def _finished(self, code, status):
        self.exit_code = code
        output = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._complete(status == QProcess.NormalExit and code == 0
                       and READY_MARKER in output.splitlines())

    def _error(self, error):
        if error == QProcess.FailedToStart:
            self._complete(False)

    def _timeout(self):
        self.process.kill()
        self._complete(False)

    def _complete(self, ok):
        if self.result is not None:
            return
        self.timer.stop()
        self.result = bool(ok)
        self.running = False
        self.ready.emit(self.result)


def run_probe():
    # No account, profile on disk, remote URL, local inference or GPU compute.
    # Keep Chromium's normal sandbox and security settings in place.
    from PySide6.QtCore import QUrl
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile

    app = QApplication.instance() or QApplication([])
    profile = QWebEngineProfile(app)
    page = QWebEnginePage(profile)
    outcome = [False]

    def verified(value):
        if value == 2:
            outcome[0] = True
            print(READY_MARKER, flush=True)
        app.quit()

    def loaded(ok):
        if ok:
            page.runJavaScript("1 + 1", verified)
        else:
            app.quit()

    page.loadFinished.connect(loaded)
    QTimer.singleShot(8000, app.quit)
    page.setUrl(QUrl("about:blank"))
    app.exec()
    # Destroy pages before their profile, including during normal shutdown.
    from shiboken6 import delete
    delete(page)
    delete(profile)
    return 0 if outcome[0] else 1


if __name__ == "__main__":
    raise SystemExit(run_probe())
