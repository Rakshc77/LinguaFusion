"""Shared Qt browser session for the desktop's Online surfaces."""

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QFileDialog, QMessageBox


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

    class OnlineWebView(QWebEngineView):
        def setUrl(self, url):
            # Qt initializes Chromium when a profile/page is created. Delay it
            # until the user actually opens an Online surface, just as the
            # original unopened QWebEngineViews did during local startup.
            if not getattr(self, "_online_configured", False):
                _configure_online_view(self, window, app_url)
                self._online_configured = True
            super().setUrl(url)

    return OnlineWebView()


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
