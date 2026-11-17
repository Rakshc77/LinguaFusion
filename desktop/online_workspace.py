"""Shared Qt browser session for the desktop's Online surfaces."""

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from desktop.webengine_probe import BrowserRuntimeProbe


def trusted_origin(url, app_url):
    """Only the configured HTTPS origin can request device capabilities."""
    origin, expected = QUrl(url), QUrl(app_url)
    return (
        origin.scheme() == expected.scheme() == "https"
        and origin.host() == expected.host()
        and origin.port(443) == expected.port(443)
        and not origin.userInfo()
    )


def create_online_view(window, app_url):
    from PySide6.QtWebEngineWidgets import QWebEngineView

    # Layout-only tests substitute a QWidget for the unopened browser.
    if not hasattr(QWebEngineView, "setPage"):
        return QWebEngineView()

    return OnlineBrowserView(window, app_url)


class OnlineBrowserView(QWidget):
    loadFinished = Signal(bool)

    def __init__(self, window, app_url):
        super().__init__()
        self._window = window
        self._app_url = app_url
        self._url = None
        self._pending_url = None
        self._browser = None
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.status = QLabel("Online opens when you select it.")
        self.status.setWordWrap(True)
        self._layout.addWidget(self.status)
        self.browser_button = QPushButton("Open in browser")
        self.browser_button.clicked.connect(self._open_browser)
        self.browser_button.hide()
        self._layout.addWidget(self.browser_button)
        if not hasattr(window, "_online_runtime_probe"):
            window._online_runtime_probe = BrowserRuntimeProbe(window)
        self._probe = window._online_runtime_probe
        self._probe.ready.connect(self._runtime_ready)

    def _open_browser(self):
        if self._url is not None:
            QDesktopServices.openUrl(self._url)

    def setUrl(self, url):
        self._url = QUrl(url)
        self._pending_url = self._url
        self.status.setText("Checking the built-in browser...")
        if self._probe.result is None:
            self._probe.start()
        else:
            self._runtime_ready(self._probe.result)

    def _runtime_ready(self, ok):
        if self._pending_url is None:
            return
        if not ok:
            self.status.setText(
                "The built-in browser could not start. Open LinguaFusion in your browser to use Online."
            )
            self.status.show()
            self.browser_button.show()
            self.loadFinished.emit(False)
            return
        if not self.isVisible():
            return
        if self._browser is None:
            from PySide6.QtWebEngineWidgets import QWebEngineView
            self._browser = QWebEngineView(self)
            _configure_online_view(self._browser, self._window, self._app_url)
            self._browser.loadFinished.connect(self.loadFinished.emit)
            self._layout.addWidget(self._browser, 1)
        self.status.hide()
        self.browser_button.hide()
        url, self._pending_url = self._pending_url, None
        self._browser.setUrl(url)

    def showEvent(self, event):
        super().showEvent(event)
        if self._probe.result is True and self._pending_url is not None:
            self._runtime_ready(True)

    def reload(self):
        if self._browser is not None:
            self._browser.reload()
        elif self._url is not None:
            self.setUrl(self._url)

    def page(self):
        return self._browser.page() if self._browser is not None else None


def _configure_online_view(view, window, app_url):

    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile

    if not hasattr(window, "_online_profile"):
        # Account, Say it and the full workspace share one Firebase session and
        # one IndexedDB store for recording recovery/history. Test runs use an
        # isolated memory profile and never read the owner's browser session.
        profile = (QWebEngineProfile(window) if not window._persist_settings
                   else QWebEngineProfile("LinguaFusionOnline", window))
        if window._persist_settings:
            from backend.config.paths import STORAGE_DIR
            profile.setPersistentStoragePath(str(STORAGE_DIR / "online-browser"))
            profile.setCachePath(str(STORAGE_DIR / "online-browser-cache"))
        window._online_profile = profile

        def download(request):
            raw_url = request.url().toString()
            url = raw_url[5:] if raw_url.startswith("blob:") else raw_url
            if not trusted_origin(url, app_url):
                request.cancel()
                return
            filename, _ = QFileDialog.getSaveFileName(
                window, "Save Online export", request.suggestedFileName()
            )
            if not filename:
                request.cancel()
                return
            from pathlib import Path
            target = Path(filename)
            request.setDownloadDirectory(str(target.parent))
            request.setDownloadFileName(target.name)
            request.accept()

        profile.downloadRequested.connect(download)

    page = QWebEnginePage(window._online_profile, view)
    view.setPage(page)

    def permission(origin, feature):
        allowed = False
        if (trusted_origin(origin, app_url)
                and trusted_origin(page.url(), app_url)
                and feature == QWebEnginePage.Feature.MediaAudioCapture
                and view.isVisible()):
            allowed = QMessageBox.question(
                window, "Allow microphone?",
                "Allow LinguaFusion Online to use your microphone for recording?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            ) == QMessageBox.Yes
        page.setFeaturePermission(
            origin, feature,
            QWebEnginePage.PermissionGrantedByUser if allowed
            else QWebEnginePage.PermissionDeniedByUser,
        )

    page.featurePermissionRequested.connect(permission)
