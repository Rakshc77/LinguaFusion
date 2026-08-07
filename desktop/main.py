import os
import re
import subprocess
import sys
import json
import hashlib
import math
import time
from pathlib import Path

# PyInstaller's windowless bootloader deliberately leaves stdout/stderr as
# ``None``.  A few native dependencies write startup diagnostics during
# import, so give them a harmless sink before importing pygame/Qt/audio
# modules.  Keeping the streams attached also makes backend-only mode behave
# identically in console and production builds.
if getattr(sys, "frozen", False):
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

# Ensure project root directory is in sys.path when main.py is launched directly or frozen
if getattr(sys, "frozen", False):
    _meipass = getattr(sys, "_MEIPASS", str(Path(sys.executable).parent))
    if _meipass not in sys.path:
        sys.path.insert(0, _meipass)
    _exec_dir = str(Path(sys.executable).parent)
    if _exec_dir not in sys.path:
        sys.path.insert(0, _exec_dir)
else:
    _project_root = str(Path(__file__).resolve().parents[1])
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)

def _register_cuda_dll_dirs() -> None:
    seen_dirs = set()
    search_roots = []
    if getattr(sys, "frozen", False):
        search_roots.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)))
    else:
        proj_dir = Path(__file__).resolve().parents[1]
        venv_site = proj_dir / ".venv" / "Lib" / "site-packages"
        torch_lib = venv_site / "torch" / "lib"
        if torch_lib.exists():
            search_roots.append(torch_lib)
        search_roots.extend([venv_site, proj_dir])

    for base_dir in search_roots:
        if not base_dir.exists():
            continue
        for dll_name in ("cublas64_12.dll", "cublasLt64_12.dll", "cudnn64_9.dll", "cudart64_12.dll", "nvJitLink_120_0.dll"):
            for dll_path in base_dir.rglob(dll_name):
                parent = dll_path.parent
                if parent not in seen_dirs:
                    seen_dirs.add(parent)
                    try:
                        os.add_dll_directory(str(parent))
                        os.environ["PATH"] = str(parent) + os.pathsep + os.environ.get("PATH", "")
                    except (AttributeError, OSError):
                        pass

_register_cuda_dll_dirs()

import requests as _requests
import pygame
import numpy as np
import sounddevice as sd
import soundfile as sf
from pydub import AudioSegment
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import Qt, QTimer, QPointF, QSize, Signal, QSettings, QRunnable, QThreadPool, QObject, QPropertyAnimation, QEasingCurve, QUrl
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtGui import QShortcut, QKeySequence, QPainter, QPen, QColor, QPainterPath, QTextCursor, QTextCharFormat, QIcon, QPixmap, QAction, QFontDatabase, QLinearGradient, QPalette
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QTextEdit,
    QVBoxLayout, QWidget, QCheckBox, QInputDialog, QMessageBox, QStyle, QSystemTrayIcon, QMenu, QGraphicsOpacityEffect
)

try:
    from desktop.iconography import app_icon
except ModuleNotFoundError:
    try:
        from iconography import app_icon
    except ModuleNotFoundError:
        def app_icon(*args, **kwargs):
            return QIcon()

SERVER_URL = "http://localhost:8000"


def _desktop_api_key() -> str:
    value = os.environ.get("LINGUAFUSION_API_KEY", "").strip()
    if value:
        return value
    try:
        return (Path(__file__).resolve().parents[1] / "backend" / "storage" / "mobile_api_key.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


class _AuthenticatedRequests:
    """Drop-in requests facade that shares the optional mobile pairing key."""

    def __init__(self, module):
        self._module = module

    def _kwargs(self, kwargs):
        key = _desktop_api_key()
        headers = dict(kwargs.pop("headers", {}) or {})
        if key:
            headers.setdefault("X-API-Key", key)
        kwargs["headers"] = headers
        return kwargs

    def get(self, *args, **kwargs):
        return self._module.get(*args, **self._kwargs(kwargs))

    def post(self, *args, **kwargs):
        return self._module.post(*args, **self._kwargs(kwargs))

    def delete(self, *args, **kwargs):
        return self._module.delete(*args, **self._kwargs(kwargs))

    def put(self, *args, **kwargs):
        return self._module.put(*args, **self._kwargs(kwargs))

    def patch(self, *args, **kwargs):
        return self._module.patch(*args, **self._kwargs(kwargs))

    def request(self, *args, **kwargs):
        return self._module.request(*args, **self._kwargs(kwargs))

    def __getattr__(self, name):
        return getattr(self._module, name)


requests = _AuthenticatedRequests(_requests)

APP_USER_MODEL_ID = "LinguaFusion.Desktop"


def set_windows_app_user_model_id():
    """Set Windows AppUserModelID before QApplication so the taskbar uses the app icon."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


set_windows_app_user_model_id()


def app_icon_path() -> Path:
    if getattr(sys, "frozen", False):
        base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        p = base_dir / "desktop" / "assets" / "linguafusion.ico"
        if p.exists():
            return p
        p2 = base_dir / "assets" / "linguafusion.ico"
        if p2.exists():
            return p2
    return Path(__file__).resolve().parent / "assets" / "linguafusion.ico"


def is_autostart_enabled() -> bool:
    if not sys.platform.startswith("win"):
        return False
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return False
    shortcut_path = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "LinguaFusion.lnk"
    return shortcut_path.exists()


def set_autostart_enabled(enabled: bool) -> bool:
    if not sys.platform.startswith("win"):
        return False
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return False
    try:
        startup_dir = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        startup_dir.mkdir(parents=True, exist_ok=True)
        shortcut_path = startup_dir / "LinguaFusion.lnk"
        if not enabled:
            if shortcut_path.exists():
                shortcut_path.unlink()
            return True

        if getattr(sys, "frozen", False):
            exe_path = str(Path(sys.executable).resolve())
            work_dir = str(Path(sys.executable).resolve().parent)
            args = "--autostart"
        else:
            exe_path = str(Path(sys.executable).resolve())
            work_dir = str(Path(__file__).resolve().parents[1])
            main_py = str(Path(__file__).resolve())
            args = f'"{main_py}" --autostart'

        ps_cmd = (
            f"$WshShell = New-Object -ComObject WScript.Shell; "
            f"$Shortcut = $WshShell.CreateShortcut('{shortcut_path}'); "
            f"$Shortcut.TargetPath = '{exe_path}'; "
            f"$Shortcut.Arguments = '{args}'; "
            f"$Shortcut.WorkingDirectory = '{work_dir}'; "
            f"$Shortcut.IconLocation = '{exe_path},0'; "
            f"$Shortcut.Description = 'LinguaFusion Windows Startup'; "
            f"$Shortcut.Save()"
        )
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps_cmd], creationflags=creation_flags, check=True)
        return True
    except Exception as exc:
        print("set_autostart_enabled error:", exc)
        return False


LANGUAGES = [
    ("English", "en"),
    ("German", "de"),
    ("Spanish", "es"),
    ("Hindi", "hi"),
    ("Arabic", "ar"),
    ("Odia", "or"),
]

DOCUMENT_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".rtf", ".html", ".htm", ".csv", ".json", ".xml"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac", ".wma"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
OCR_EXTENSIONS = IMAGE_EXTENSIONS | {".pdf"}


class SmoothScrollArea(QScrollArea):
    WHEEL_STEP = 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PageScroll")
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.viewport().setObjectName("PageScrollViewport")
        self.viewport().setAutoFillBackground(True)
        self._scroll_anim = None
        self._scroll_target = 0.0
        self._scroll_direction = 0
        self.verticalScrollBar().rangeChanged.connect(self._clamp_scroll_target)

    def _clamp_scroll_target(self, minimum, maximum):
        self._scroll_target = max(float(minimum), min(float(maximum), self._scroll_target))

    def _finish_scroll_animation(self, animation):
        if self._scroll_anim is animation:
            self._scroll_target = float(self.verticalScrollBar().value())
            self._scroll_direction = 0
            self._scroll_anim = None
        animation.deleteLater()

    def _queue_scroll(self, offset, *, smooth=True):
        """Apply a signed scroll offset while preserving rapid wheel intent."""
        bar = self.verticalScrollBar()
        if not bar or bar.maximum() <= bar.minimum() or offset == 0:
            return False

        direction = 1 if offset > 0 else -1
        animation_running = (
            self._scroll_anim is not None
            and self._scroll_anim.state() == QPropertyAnimation.Running
        )
        if animation_running and direction == self._scroll_direction:
            base = self._scroll_target
        else:
            # Direction reversals begin at the position currently on screen so
            # they react immediately instead of first completing old momentum.
            base = float(bar.value())

        target = max(float(bar.minimum()), min(float(bar.maximum()), base + float(offset)))
        self._scroll_target = target
        self._scroll_direction = direction

        old_animation = self._scroll_anim
        if old_animation is not None:
            old_animation.stop()
            old_animation.deleteLater()
            self._scroll_anim = None

        motion_mode = getattr(self.window(), "current_motion", "full")
        if not smooth or motion_mode == "off":
            bar.setValue(round(target))
            self._scroll_target = float(bar.value())
            self._scroll_direction = 0
            return True

        distance = abs(target - bar.value())
        if distance < 1:
            return True

        duration = 90 if motion_mode == "reduced" else min(220, max(110, round(90 + distance * 0.22)))
        animation = QPropertyAnimation(bar, b"value", self)
        animation.setDuration(duration)
        animation.setStartValue(bar.value())
        animation.setEndValue(round(target))
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.finished.connect(lambda anim=animation: self._finish_scroll_animation(anim))
        self._scroll_anim = animation
        animation.start()
        return True

    def wheelEvent(self, event):
        pixel_delta = event.pixelDelta().y()
        if pixel_delta:
            # Precision touchpads already provide smooth pixel movement.
            if self._queue_scroll(-pixel_delta, smooth=False):
                event.accept()
                return

        angle_delta = event.angleDelta().y()
        if angle_delta:
            offset = -(angle_delta / 120.0) * self.WHEEL_STEP
            if self._queue_scroll(offset, smooth=True):
                event.accept()
                return

        super().wheelEvent(event)

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        # Translucent theme layers can otherwise expose Qt's scroll-blit cache
        # for a frame, leaving visible copies of labels and controls behind.
        self.viewport().update()


class WheelSafeComboBox(QComboBox):
    """Prevent closed dropdowns from stealing page-scroll wheel events."""

    def wheelEvent(self, event):
        if self.view().isVisible():
            super().wheelEvent(event)
            return
        event.ignore()


class Card(QFrame):
    def __init__(self, object_name="Card"):
        super().__init__()
        self.setObjectName(object_name)
        self.setFrameShape(QFrame.NoFrame)


class SkeletonWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.offset = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.setInterval(30)

    def start(self):
        self.timer.start()
        self.show()

    def stop(self):
        self.timer.stop()
        self.hide()

    def _animate(self):
        self.offset = (self.offset + 0.05) % 2.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        
        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setSpread(QLinearGradient.RepeatSpread)
        grad.setColorAt(0.0, QColor(200, 200, 200, 50))
        grad.setColorAt(0.5, QColor(220, 220, 220, 150))
        grad.setColorAt(1.0, QColor(200, 200, 200, 50))
        
        grad.setStart(self.width() * self.offset - self.width(), 0)
        grad.setFinalStop(self.width() * self.offset, 0)

        painter.setBrush(grad)
        painter.setPen(Qt.NoPen)
        
        y = 10
        h = 20
        painter.drawRoundedRect(10, y, self.width() - 40, h, 6, 6)
        painter.drawRoundedRect(10, y + 30, self.width() - 80, h, 6, 6)
        painter.drawRoundedRect(10, y + 60, self.width() - 60, h, 6, 6)


class ThemeToggle(QPushButton):
    """Keyboard-accessible A/C theme switch painted without platform glyphs."""

    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setFixedSize(54, 30)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName("Use dark theme")
        self.setToolTip("Switch between Broadsheet (A) and Night Studio (C)")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        checked = self.isChecked()
        track = QColor("#2674D9" if checked else "#D7DEE8")
        if self.isDown():
            track = QColor("#1F63BC" if checked else "#C7D0DC")
        painter.setPen(Qt.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(1, 3, 52, 24, 12, 12)
        knob_x = 29 if checked else 5
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(knob_x, 5, 20, 20)
        if self.hasFocus():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#4C9AFF" if checked else "#0B57D0"), 2))
            painter.drawRoundedRect(1, 1, 52, 28, 14, 14)
        painter.end()


class WaveformLoaderSignals(QObject):
    finished = Signal(list)

class WaveformLoaderTask(QRunnable):
    def __init__(self, audio_path: str, bins: int):
        super().__init__()
        self.audio_path = audio_path
        self.bins = bins
        self.signals = WaveformLoaderSignals()

    def run(self):
        try:
            audio = AudioSegment.from_file(self.audio_path)
            audio = audio.set_channels(1)
            samples = audio.get_array_of_samples()

            if not samples:
                self.signals.finished.emit([])
                return

            total = len(samples)
            bins = max(80, min(self.bins, 900))
            step = max(1, total // bins)
            raw = []

            for i in range(0, total, step):
                chunk = samples[i:i + step]
                if not chunk:
                    continue
                peak = max(abs(x) for x in chunk)
                raw.append(float(peak))

            maximum = max(raw) if raw else 1.0
            normalized = [value / maximum for value in raw]

            # Smooth the contour so it looks like a podcast waveform, not blocks.
            smoothed = []
            window = 5
            for i in range(len(normalized)):
                left = max(0, i - window)
                right = min(len(normalized), i + window + 1)
                smoothed.append(sum(normalized[left:right]) / (right - left))

            self.signals.finished.emit(smoothed)
        except Exception as e:
            print(f"[WaveformLoader] Error: {e}")
            self.signals.finished.emit([])


class AudioWaveform(QWidget):
    """Spotify/Apple-style waveform drawn from the actual WAV audio."""
    seek_requested = Signal(float)

    def __init__(self):
        super().__init__()
        self.progress = 0.0
        self.peaks = []
        self.setMinimumHeight(44)

    def set_progress(self, progress: float):
        self.progress = max(0.0, min(1.0, progress))
        self.update()

    def clear_waveform(self):
        self.peaks = []
        self.progress = 0.0
        self.update()

    def _emit_seek_from_x(self, x_position: int):
        width = max(self.width(), 1)
        progress = max(0.0, min(1.0, x_position / width))
        self.seek_requested.emit(progress)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._emit_seek_from_x(event.position().x())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._emit_seek_from_x(event.position().x())

    def load_audio(self, audio_path: str, bins: int = 420):
        task = WaveformLoaderTask(audio_path, bins)
        task.signals.finished.connect(self._on_audio_loaded)
        QThreadPool.globalInstance().start(task)

    def _on_audio_loaded(self, peaks: list):
        self.peaks = peaks
        self.progress = 0.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        width = max(self.width(), 1)
        height = max(self.height(), 1)
        center_y = height / 2
        max_amp = height * 0.36

        baseline_pen = QPen(QColor(54, 72, 104), 2)
        inactive_pen = QPen(QColor(70, 88, 120), 2)
        active_pen = QPen(QColor(96, 120, 255), 3)
        playhead_pen = QPen(QColor(245, 248, 255), 2)

        painter.setPen(baseline_pen)
        painter.drawLine(0, int(center_y), width, int(center_y))

        if not self.peaks:
            # Calm empty-state curve.
            path = QPainterPath()
            path.moveTo(0, center_y)
            for x in range(width + 1):
                t = x / width
                y = center_y + math.sin(t * math.pi * 10) * max_amp * 0.25
                path.lineTo(x, y)
            painter.setPen(inactive_pen)
            painter.drawPath(path)
            return

        top_path = QPainterPath()
        bottom_path = QPainterPath()

        count = len(self.peaks)
        for i, peak in enumerate(self.peaks):
            x = (i / max(count - 1, 1)) * width
            amp = max(2.0, peak * max_amp)
            y_top = center_y - amp
            y_bottom = center_y + amp
            if i == 0:
                top_path.moveTo(x, y_top)
                bottom_path.moveTo(x, y_bottom)
            else:
                top_path.lineTo(x, y_top)
                bottom_path.lineTo(x, y_bottom)

        painter.setPen(inactive_pen)
        painter.drawPath(top_path)
        painter.drawPath(bottom_path)

        active_width = int(width * self.progress)
        if active_width > 0:
            painter.save()
            painter.setClipRect(0, 0, active_width, height)
            painter.setPen(active_pen)
            painter.drawPath(top_path)
            painter.drawPath(bottom_path)
            painter.restore()

        # Smooth podcast-style progress line.
        progress_y = int(height - 7)
        painter.setPen(QPen(QColor(54, 72, 104), 2))
        painter.drawLine(0, progress_y, width, progress_y)
        painter.setPen(QPen(QColor(59, 130, 246), 4))
        painter.drawLine(0, progress_y, active_width, progress_y)

        x = active_width
        painter.setPen(playhead_pen)
        painter.drawLine(x, 5, x, height - 2)
        painter.setBrush(QColor(245, 248, 255))
        painter.drawEllipse(QPointF(x, 8), 5, 5)


class LinguaFusionWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        import os
        font_reg_path = os.path.join("desktop", "assets", "fonts", "Inter-Regular.ttf")
        font_bold_path = os.path.join("desktop", "assets", "fonts", "Inter-Bold.ttf")
        if os.path.exists(font_reg_path) and os.path.exists(font_bold_path):
            QFontDatabase.addApplicationFont(font_reg_path)
            QFontDatabase.addApplicationFont(font_bold_path)
        self.setWindowTitle("LinguaFusion")
        self.resize(1500, 940)
        # Phase 5 policy: medium desktop is the smallest supported layout.
        # The page scrolls vertically when content cannot fit; horizontal
        # overflow is avoided by proportional controls instead of ultra-compact squeezing.
        self.setMinimumSize(1180, 640)
        self.app_settings = QSettings("LinguaFusion", "LinguaFusion")
        self._persist_settings = os.environ.get("LF_TEST_MODE", "").strip() != "1"
        self.current_theme = (
            self.app_settings.value("appearance/theme_id", "broadsheet", type=str)
            if self._persist_settings else "broadsheet"
        )
        if self.current_theme not in self.DESKTOP_THEME_IDS:
            self.current_theme = "broadsheet"
        self.current_font = (
            self.app_settings.value("appearance/font_id", "modern", type=str)
            if self._persist_settings else "modern"
        )
        if self.current_font not in self.DESKTOP_FONT_SPECS:
            self.current_font = "modern"
        self.current_motion = (
            self.app_settings.value("appearance/motion", "full", type=str)
            if self._persist_settings else "full"
        )
        if self.current_motion not in {"full", "reduced", "off"}:
            self.current_motion = "full"
        self.dark_mode = self.DESKTOP_THEME_SPECS[self.current_theme]["dark"]
        self.apply_app_icon()
        self.setAcceptDrops(True)
        self._responsive_mode = None
        self.sidebar_collapsed = False
        self.inspector_collapsed = False
        self.sidebar_user_override = None
        self.inspector_user_override = None
        self.responsive_text_edits = []
        self.responsive_buttons = []
        self.responsive_export_buttons = []
        self.responsive_playback_buttons = []
        self.responsive_band_widgets = []
        self.responsive_compact_cards = []
        self.responsive_general_buttons = []

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self.update_responsive_layout)

        self.executor = ThreadPoolExecutor(max_workers=4)
        self.generated_audio_files = []
        self.audio_paused = False
        self.current_page_name = "Translate"
        self.recent_history = {name: [] for name in ["Translate", "Reader", "Speech", "OCR", "Notes", "Tasks", "Settings"]}
        self.reader_current_file = "None"
        self.reader_detected_language = "Auto"
        self.reader_voice_label = "Auto"
        self.reader_playback_status = "Stopped"
        self.reader_base_audio_path = None
        self.reader_current_audio_path = None
        self.reader_active_audio_path = None
        self.reader_audio_duration_ms = 0
        self.reader_active_duration_ms = 0
        self.reader_last_rate = 1.0
        self.reader_paused_pos_ms = 0
        self.reader_seek_base_original_ms = 0
        self.reader_waveform_bars = ""
        self.reader_analysis = {}
        self.reader_sentence_ranges = []
        self.reader_current_sentence_index = -1
        self.reader_bookmarks = []
        self.reader_bookmark_counter = 0
        self.reader_cursor_audio_cache = {}
        self.reader_full_audio_cache_key = None
        self.reader_full_audio_path = None
        self.reader_highlight_enabled = True
        self.reader_playback_sentence_offset = 0
        self.reader_playback_sentence_count = 0
        self.translate_document_name = None
        self.translate_document_source_path = None
        self.last_translation_plain_text = ""
        self.last_translation_tts_text = ""
        self.last_translation_input_snapshot = ""
        self.last_translation_source_snapshot = ""
        self.last_translation_target_snapshot = ""
        self.active_audio_context = "Reader"

        self.speech_is_recording = False
        self.speech_is_paused = False
        self.speech_frames = []
        self.speech_levels = []
        self.speech_stream = None
        self.speech_sample_rate = 16000
        self.speech_channels = 1
        self.speech_recording_started_at = None
        self.speech_elapsed_when_paused = 0.0
        self.speech_current_wav_path = None
        self.last_speech_transcript = ""
        self.last_speech_translation = ""
        self.last_speech_language = "auto"
        self.speech_live_transcribing = False
        self.speech_last_live_frame_count = 0
        self.speech_auto_final_pending = False
        self._speech_reveal_timers = {}
        self.corrections = {}
        self.smart_provider_status = {}

        self.audio_backend_ready = False
        self.audio_backend_error = None
        if os.name == "nt":
            os.environ.setdefault("SDL_AUDIODRIVER", "directsound")
        try:
            pygame.mixer.init()
            self.audio_backend_ready = True
        except Exception as exc:
            self.audio_backend_error = str(exc)

        self.playback_timer = QTimer(self)
        self.playback_timer.setInterval(16)
        self.playback_timer.timeout.connect(self.update_playback_ui)

        self.speech_timer = QTimer(self)
        self.speech_timer.setInterval(80)
        self.speech_timer.timeout.connect(self.update_speech_recording_ui)

        self.speech_live_timer = QTimer(self)
        self.speech_live_timer.setInterval(6000)
        self.speech_live_timer.timeout.connect(self.live_transcribe_speech_snapshot)

        self._is_backend_online = False
        self.build_shell()
        self.apply_style()
        self.switch_page("Translate")
        self.setup_system_tray()

        self.backend_poll_timer = QTimer(self)
        self.backend_poll_timer.setInterval(400)
        self.backend_poll_timer.timeout.connect(self._poll_backend_health_on_startup)
        self.backend_poll_timer.start()
        QTimer.singleShot(50, self._poll_backend_health_on_startup)

    def setup_system_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon_path = app_icon_path()
        if not icon_path.exists():
            return
        self.tray_icon = QSystemTrayIcon(QIcon(str(icon_path)), self)
        self.tray_icon.setToolTip("LinguaFusion - Background Active")

        menu = QMenu(self)
        show_action = QAction("Open LinguaFusion", self)
        show_action.triggered.connect(self.show_normal_and_raise)
        menu.addAction(show_action)

        menu.addSeparator()

        tunnel_action = QAction("Toggle Cloudflare Tunnel", self)
        tunnel_action.triggered.connect(self.toggle_cloud_tunnel)
        menu.addAction(tunnel_action)

        menu.addSeparator()

        quit_action = QAction("Quit LinguaFusion", self)
        quit_action.triggered.connect(self.force_quit_app)
        menu.addAction(quit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

    def on_tray_icon_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_normal_and_raise()

    def show_normal_and_raise(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def force_quit_app(self):
        self._is_force_quitting = True
        app = QApplication.instance()
        if app:
            app.quit()

    def closeEvent(self, event):
        minimize_to_tray = self.app_settings.value("system/minimize_to_tray", True, type=bool)
        if minimize_to_tray and hasattr(self, "tray_icon") and self.tray_icon.isVisible() and not getattr(self, "_is_force_quitting", False):
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "LinguaFusion",
                "LinguaFusion is running in the background. Double-click tray icon to open.",
                QSystemTrayIcon.Information,
                2000,
            )
            return
        event.accept()

    def apply_app_icon(self):
        icon_path = app_icon_path()
        if icon_path.exists():
            icon = QIcon(str(icon_path))
            self.setWindowIcon(icon)
            app = QApplication.instance()
            if app:
                app.setWindowIcon(icon)
                if hasattr(app, "setDesktopFileName") and not getattr(sys, "frozen", False):
                    app.setDesktopFileName("LinguaFusion.Desktop")

    # ---------- Shell ----------
    def build_shell(self):
        root = QWidget()
        root.setObjectName("Root")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.content_shell = QWidget()
        content = self.content_shell
        content_layout = QHBoxLayout(content)
        self.content_layout = content_layout
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.sidebar = self.build_sidebar()
        self.main_area = self.build_main_area()
        self.right_panel = self.build_right_panel()

        content_layout.addWidget(self.sidebar)
        content_layout.addWidget(self.main_area, 1)
        content_layout.addWidget(self.right_panel)

        self.footer = self.build_footer()

        root_layout.addWidget(content, 1)
        root_layout.addWidget(self.footer)
        self.setCentralWidget(root)

    def build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(238)
        sidebar.setMinimumWidth(72)
        sidebar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 18, 16, 16)
        layout.setSpacing(10)

        brand = QHBoxLayout()
        logo = QLabel()
        self.logo_label = logo
        logo.setObjectName("Logo")
        logo.setAlignment(Qt.AlignCenter)
        logo.setFixedSize(42, 42)
        # The in-app mark uses the same crisp line language as the navigation.
        # The packaged .ico remains the Windows/taskbar identity.
        logo.setPixmap(app_icon("translate", 30, normal="#00DCEB").pixmap(QSize(30, 30)))
        title_col = QVBoxLayout()
        title = QLabel("LinguaFusion")
        self.brand_title = title
        title.setObjectName("AppTitle")
        subtitle = QLabel("Private workspace")
        self.brand_subtitle = subtitle
        subtitle.setObjectName("Muted")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        brand.addWidget(logo)
        brand.addLayout(title_col, 1)
        self.sidebar_toggle_btn = QPushButton()
        self.sidebar_toggle_btn.setObjectName("ChromeButton")
        self.sidebar_toggle_btn.setIcon(app_icon("chevron-left", 18))
        self.sidebar_toggle_btn.setIconSize(QSize(18, 18))
        self.sidebar_toggle_btn.setFixedSize(34, 34)
        self.sidebar_toggle_btn.setToolTip("Collapse navigation")
        self.sidebar_toggle_btn.setAccessibleName("Collapse navigation")
        self.sidebar_toggle_btn.clicked.connect(self.toggle_sidebar)
        brand.addWidget(self.sidebar_toggle_btn)
        layout.addLayout(brand)
        layout.addSpacing(12)

        self.nav_buttons = {}
        self.nav_metadata = {}
        nav_items = [
            ("Translate", "translate"),
            ("Reader", "reader"),
            ("Speech", "microphone"),
            ("OCR", "scan"),
            ("Notes", "notes"),
            ("Tasks", "history"),
            ("Access", "share"),
            ("Settings", "settings"),
        ]
        for name, icon_name in nav_items:
            btn = QPushButton(name)
            self.nav_metadata[name] = (icon_name, name)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setIcon(app_icon(icon_name, 20))
            btn.setIconSize(QSize(20, 20))
            btn.setMinimumHeight(44)
            btn.setAccessibleName(name)
            btn.clicked.connect(lambda checked=False, page=name: self.switch_page(page))
            self.nav_buttons[name] = btn
            layout.addWidget(btn)

        layout.addStretch(1)

        recent_header = QHBoxLayout()
        self.recent_header_label = QLabel("RECENT")
        recent = self.recent_header_label
        recent.setObjectName("SectionLabel")
        self.recent_more_label = QLabel("More")
        more = self.recent_more_label
        more.setObjectName("LinkLabel")
        recent_header.addWidget(recent)
        recent_header.addStretch(1)
        recent_header.addWidget(more)
        layout.addLayout(recent_header)

        self.recent_items_box = QVBoxLayout()
        layout.addLayout(self.recent_items_box)
        self.update_recent_items("Translate")

        self.sidebar_import_btn = QPushButton("Import file")
        import_btn = self.sidebar_import_btn
        import_btn.setObjectName("PrimaryButton")
        import_btn.setIcon(app_icon("upload", 18, normal="#FFFFFF", active="#FFFFFF"))
        import_btn.setIconSize(QSize(18, 18))
        import_btn.clicked.connect(lambda: self.switch_page("Reader"))
        self.register_band_widget(import_btn)
        layout.addWidget(import_btn)
        return sidebar

    def build_main_area(self):
        area = QWidget()
        area.setObjectName("MainArea")
        layout = QVBoxLayout(area)
        self.main_area_layout = layout
        area.setMinimumWidth(0)
        area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.setContentsMargins(28, 20, 12, 14)
        layout.setSpacing(18)

        topbar = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setObjectName("SearchBox")
        self.search_box.setMinimumWidth(0)
        topbar.addWidget(self.search_box)
        topbar.addStretch(1)
        
        # Action controls for workflow toggling right sidebar
        self.global_action_btn = QPushButton("Export")
        self.global_action_btn.setObjectName("SecondaryButton")
        self.global_action_btn.setIcon(app_icon("share", 16))
        self.global_action_btn.setVisible(False)
        topbar.addWidget(self.global_action_btn)
        topbar.addSpacing(8)
        self.inspector_toggle_btn = QPushButton()
        self.inspector_toggle_btn.setObjectName("ChromeButton")
        self.inspector_toggle_btn.setIcon(app_icon("panel", 19))
        self.inspector_toggle_btn.setIconSize(QSize(19, 19))
        self.inspector_toggle_btn.setFixedSize(38, 38)
        self.inspector_toggle_btn.setToolTip("Hide details panel")
        self.inspector_toggle_btn.setAccessibleName("Toggle details panel")
        self.inspector_toggle_btn.clicked.connect(self.toggle_inspector)
        topbar.addWidget(self.inspector_toggle_btn)
        self.system_badge = QLabel("● Server Online")
        self.system_badge.setObjectName("StatusBadge")
        self.system_badge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        topbar.addWidget(self.system_badge)
        layout.addLayout(topbar)

        self.pages = QStackedWidget()
        self.pages.setObjectName("PageStack")
        # Keep pages fluid at the medium width floor. Controls now shrink
        # proportionally instead of forcing a horizontal content canvas.
        self.pages.setMinimumWidth(0)
        # QStackedWidget reports the widest hidden page as its size hint. Ignore
        # that horizontal hint so the visible workflow fits the scroll viewport
        # instead of creating a hidden 10–30 px overflow strip.
        self.pages.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.page_index = {}
        for display_name, canonical_name, builder in [
            ("Translate", "Translate", self.build_translate_page),
            ("Audio Reader", "Reader", self.build_reader_page),
            ("Speech", "Speech", self.build_speech_page),
            ("Scan / OCR", "OCR", self.build_ocr_page),
            ("Saved Notes", "Notes", self.build_notes_page),
            ("Task Center", "Tasks", self.build_tasks_page),
            ("Remote Access", "Access", self.build_access_page),
            ("Settings", "Settings", self.build_settings_page),
        ]:
            idx = self.pages.addWidget(builder())
            self.page_index[display_name] = idx
            self.page_index[canonical_name] = idx

        self.page_scroll = SmoothScrollArea()
        self.page_scroll.setWidget(self.pages)
        layout.addWidget(self.page_scroll, 1)

        self.scroll_hint = QLabel("↓ More controls below")
        self.scroll_hint.setObjectName("ScrollHint")
        self.scroll_hint.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.scroll_hint.setVisible(False)
        # Right-aligned compact badge instead of a full-width green bar.
        layout.addWidget(self.scroll_hint, 0, Qt.AlignRight)
        return area

    def build_right_panel(self):
        panel = QWidget()
        panel.setObjectName("RightPanel")
        panel.setFixedWidth(278)
        panel.setMinimumWidth(0)
        self.right_layout = QVBoxLayout(panel)
        self.right_layout.setContentsMargins(14, 74, 18, 18)
        self.right_layout.setSpacing(12)
        return panel

    def build_footer(self):
        footer = QFrame()
        footer.setObjectName("Footer")
        footer.setFixedHeight(46)
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(18, 0, 18, 0)
        self.footer_left = QLabel("● Ready")
        self.footer_left.setObjectName("FooterBadge")
        self.footer_center = QLabel("Processing stays on this device")
        self.footer_center.setObjectName("Muted")
        self.footer_right = QLabel("Local  •  Private  •  GPU accelerated")
        self.footer_right.setObjectName("FooterText")
        layout.addWidget(self.footer_left)
        layout.addStretch(1)
        layout.addWidget(self.footer_center)
        layout.addStretch(1)
        layout.addWidget(self.footer_right)
        return footer

    # ---------- Styling ----------
    # ---------- Cleaned PC Theme Concepts System ----------
    DESKTOP_THEME_SPECS = {
        "broadsheet": {"name": "Broadsheet (Classic Newspaper)", "group": "Editorial", "dark": False, "bg": "#F6F1E4", "sidebar": "#F6F1E4", "card": "#F6F1E4", "border": "#E2D9C5", "text": "#2B2622", "muted": "#6E6353", "accent": "#8A3A1F", "accent_hover": "#752E15", "btn_text": "#F6F1E4", "nav_active": "#E8DEC9", "nav_active_text": "#8A3A1F"},
        "editorial-split": {"name": "Editorial Split (Dark Rail Split)", "group": "Editorial", "dark": False, "bg": "#F4EFE4", "sidebar": "#2B2622", "card": "#F4EFE4", "border": "#E3DCCB", "text": "#2B2622", "muted": "#8A7F6B", "accent": "#A05A3C", "accent_hover": "#8C4A2E", "btn_text": "#F4EFE4", "nav_active": "#3D3732", "nav_active_text": "#F4EFE4"},
        "reading-room": {"name": "Reading Room (Literary Ivory)", "group": "Editorial", "dark": False, "bg": "#F7F3EA", "sidebar": "#EFE8D6", "card": "#F7F3EA", "border": "#E0D7C3", "text": "#2A2119", "muted": "#6A5D4A", "accent": "#B04A2F", "accent_hover": "#9A3A20", "btn_text": "#F7F3EA", "nav_active": "#EFE8D6", "nav_active_text": "#B04A2F"},
        "gallery": {"name": "Gallery (Avant-garde Lime)", "group": "Editorial", "dark": True, "bg": "#0E0E10", "sidebar": "#161618", "card": "#0E0E10", "border": "#262628", "text": "#F2F2EE", "muted": "#5F5F63", "accent": "#D8FF3D", "accent_hover": "#C2EB29", "btn_text": "#0E0E10", "nav_active": "#161618", "nav_active_text": "#D8FF3D"},
        "editorial-luxe": {"name": "Editorial Luxe (Fashion Gold)", "group": "Editorial", "dark": False, "bg": "#F4EFE4", "sidebar": "#ECE5D4", "card": "#F4EFE4", "border": "#DDD2BA", "text": "#2A2118", "muted": "#9C8A63", "accent": "#9C7A3C", "accent_hover": "#7A5F2A", "btn_text": "#F4EFE4", "nav_active": "#ECE5D4", "nav_active_text": "#9C7A3C"},
        "glass-dark": {"name": "Glass Dark (Cyan Deep Glass)", "group": "Dark", "dark": True, "bg": "#070D18", "sidebar": "#0C1A2E", "card": "#0C1A2E", "border": "#1B2F4A", "text": "#EAF6FB", "muted": "#7FA9C4", "accent": "#22D3EE", "accent_hover": "#0EC0DB", "btn_text": "#03121A", "nav_active": "#16314D", "nav_active_text": "#22D3EE"},
        "aurora-glass": {"name": "Aurora Glass (Frosted Teal Glass)", "group": "Dark", "dark": True, "bg": "#0C1018", "sidebar": "#121826", "card": "#121826", "border": "#2D3A50", "text": "#EEF3FB", "muted": "#8AA0C8", "accent": "#2DD4BF", "accent_hover": "#14B8A6", "btn_text": "#05201C", "nav_active": "#1A2438", "nav_active_text": "#2DD4BF"},
        "blueprint": {"name": "Technical Blueprint (Drafting Navy)", "group": "Utility", "dark": True, "bg": "#0A1830", "sidebar": "#0D2140", "card": "#0D2140", "border": "#2A4A75", "text": "#EAF4FF", "muted": "#5F8FBF", "accent": "#5FD0FF", "accent_hover": "#38BDF8", "btn_text": "#06223D", "nav_active": "#0D2140", "nav_active_text": "#5FD0FF"},
        "zen": {"name": "Zen Focus (Minimalist Monochrome)", "group": "Dark", "dark": True, "bg": "#0A0A0A", "sidebar": "#111111", "card": "#141414", "border": "#262626", "text": "#F4F4F4", "muted": "#6F6F6F", "accent": "#F4F4F4", "accent_hover": "#E0E0E0", "btn_text": "#0A0A0A", "nav_active": "#222222", "nav_active_text": "#F4F4F4"}
    }

    DESKTOP_THEME_IDS = (
        "broadsheet",
        "editorial-split",
        "reading-room",
        "gallery",
        "editorial-luxe",
        "glass-dark",
        "aurora-glass",
        "blueprint",
        "zen",
    )

    # Typography is deliberately independent from the visual look. These are
    # native Windows stacks, so every choice remains available offline.
    DESKTOP_FONT_SPECS = {
        "modern": {"name": "Modern Sans", "group": "Sans", "body": "Segoe UI", "display": "Segoe UI", "mono": "Consolas"},
        "friendly": {"name": "Friendly Rounded", "group": "Sans", "body": "Trebuchet MS", "display": "Trebuchet MS", "mono": "Consolas"},
        "accessible": {"name": "Accessibility Sans", "group": "Sans", "body": "Arial", "display": "Arial", "mono": "Consolas"},
        "editorial": {"name": "Editorial Serif", "group": "Serif", "body": "Georgia", "display": "Georgia", "mono": "Consolas"},
        "classic": {"name": "Classic Serif", "group": "Serif", "body": "Times New Roman", "display": "Times New Roman", "mono": "Consolas"},
        "technical": {"name": "Technical Mono", "group": "Monospace", "body": "Consolas", "display": "Consolas", "mono": "Consolas"},
    }

    DESKTOP_LOOK_METRICS = {
        "broadsheet": (2, 2, 240),
        "editorial-split": (2, 2, 210),
        "reading-room": (0, 0, 300),
        "gallery": (0, 0, 180),
        "editorial-luxe": (0, 0, 260),
        "glass-dark": (16, 12, 240),
        "aurora-glass": (18, 12, 260),
        "blueprint": (2, 2, 160),
        "zen": (0, 0, 300),
    }

    def _generate_qss(self, spec):
        bg = spec["bg"]
        sidebar = spec["sidebar"]
        card = spec["card"]
        border = spec["border"]
        text = spec["text"]
        muted = spec["muted"]
        accent = spec["accent"]
        accent_hover = spec["accent_hover"]
        btn_text = spec["btn_text"]
        nav_active = spec["nav_active"]
        nav_active_text = spec["nav_active_text"]
        font_spec = self.DESKTOP_FONT_SPECS.get(
            getattr(self, "current_font", "modern"),
            self.DESKTOP_FONT_SPECS["modern"],
        )
        body_font = font_spec["body"]
        display_font = font_spec["display"]
        # The former Signal Deck layer forced Consolas across almost the whole
        # application, which made the independent Font selector appear broken.
        # Text workspaces do not contain source code, so the selected body font
        # is the appropriate monospace fallback here as well.
        mono_font = body_font
        card_radius, control_radius, _motion_ms = self.DESKTOP_LOOK_METRICS.get(
            getattr(self, "current_theme", "broadsheet"),
            self.DESKTOP_LOOK_METRICS["broadsheet"],
        )
        qss = f"""
            #Root, QMainWindow {{ background: {bg}; color: {text}; font-family: '{body_font}'; font-size: 14px; }}
            #Sidebar {{ background: {sidebar}; border-right: 1px solid {border}; }}
            #MainArea, #RightPanel {{ background: {bg}; }}
            #PageScroll, #PageScrollViewport, #PageStack {{ background: {bg}; border: none; }}
            #Logo {{ background: transparent; padding: 0px; }}
            #AppTitle {{ font-family: '{display_font}'; font-size: 18px; font-weight: 800; color: {text}; letter-spacing: -0.3px; }}
            #Muted {{ color: {muted}; font-size: 13px; }}
            #SectionLabel {{ color: {muted}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
            #NavButton {{ text-align: left; background: transparent; color: {muted}; border: none; border-radius: {control_radius}px; padding: 10px 14px; font-size: 14px; font-weight: 600; }}
            #NavButton:hover {{ background: {nav_active}; color: {nav_active_text}; }}
            #NavButton:checked {{ background: {nav_active}; color: {nav_active_text}; border-left: 3px solid {accent}; padding-left: 11px; font-weight: 700; }}
            #PrimaryButton {{ background: {accent}; color: {btn_text}; border: 1px solid {accent}; border-radius: {control_radius}px; padding: 10px 18px; font-weight: 800; min-height: 22px; }}
            #PrimaryButton:hover {{ background: {accent_hover}; border-color: {accent_hover}; }}
            #PrimaryButton:pressed {{ background: {accent_hover}; }}
            #SecondaryButton {{ background: {card}; color: {text}; border: 1px solid {border}; border-radius: {control_radius}px; padding: 9px 14px; font-weight: 600; }}
            #SecondaryButton:hover {{ border-color: {accent}; color: {text}; }}
            #ChromeButton {{ background: transparent; color: {muted}; border: 1px solid transparent; border-radius: {control_radius}px; padding: 6px; }}
            #ChromeButton:hover {{ background: {card}; border-color: {border}; }}
            #SearchBox {{ background: {card}; border: 1px solid {border}; border-radius: {control_radius}px; padding: 9px 14px; color: {text}; min-height: 20px; }}
            #SearchBox:focus {{ border: 2px solid {accent}; padding: 8px 13px; }}
            #StatusBadge, #FooterBadge {{ background: {nav_active}; color: {accent}; border: 1px solid {border}; border-radius: 12px; padding: 6px 12px; font-weight: 700; }}
            #Footer {{ background: {sidebar}; border-top: 1px solid {border}; }}
            #FooterText {{ color: {muted}; }}
            #PageTitle, #CardTitle, #PaneTitle {{ font-family: '{display_font}'; }}
            #PageTitle {{ font-size: 27px; font-weight: 800; color: {text}; letter-spacing: -.4px; }}
            #Card {{ background: {card}; border: 1px solid {border}; border-radius: {card_radius}px; }}
            #Card[speechState="listening"] {{ border: 2px solid {accent}; }}
            #Card[speechState="processing"], #Card[speechState="translating"] {{ border: 1px solid {accent}; }}
            #SmallCard {{ background: {card}; border: 1px solid {border}; border-radius: {card_radius}px; }}
            #TranslateWorkspace {{ background: transparent; border: none; }}
            #TranslatePane {{ background: {card}; border: 1px solid {border}; border-radius: {card_radius}px; }}
            #PaneHeader {{ background: {sidebar}; border-bottom: 1px solid {border}; border-top-left-radius: {card_radius}px; border-top-right-radius: {card_radius}px; }}
            #PaneFooter {{ background: {sidebar}; border-top: 1px solid {border}; border-bottom-left-radius: {card_radius}px; border-bottom-right-radius: {card_radius}px; }}
            #PaneTitle {{ font-size: 14px; font-weight: 700; color: {text}; }}
            #Counter {{ color: {muted}; font-size: 11px; }}
            #SwapButton {{ background: {card}; color: {accent}; border: 1px solid {border}; border-radius: 21px; padding: 9px; }}
            #SwapButton:hover {{ background: {nav_active}; border-color: {accent}; }}
            #PaneToolButton {{ background: transparent; color: {muted}; border: 1px solid transparent; border-radius: 8px; padding: 5px 8px; }}
            #PaneToolButton:hover {{ background: {sidebar}; border-color: {border}; }}
            QTextEdit {{ background: {card}; color: {text}; border: 1px solid {border}; border-radius: {control_radius}px; padding: 14px; selection-background-color: {accent}; font-family: '{body_font}'; font-size: 15px; }}
            QTextEdit:focus {{ border: 2px solid {accent}; padding: 13px; }}
            #TranslatePane QTextEdit {{ border: none; border-radius: 0px; padding: 14px; }}
            #TranslatePane QTextEdit:focus {{ border: none; padding: 14px; }}
            QComboBox {{ background: {card}; color: {text}; border: 1px solid {border}; border-radius: {control_radius}px; padding: 7px 12px; min-height: 28px; font-family: '{body_font}'; font-weight: 600; }}
            QPlainTextEdit {{ font-family: '{mono_font}'; }}
            QComboBox:focus, QComboBox:hover {{ border: 1px solid {accent}; }}
            QToolTip {{ background: {text}; color: {bg}; border: none; padding: 6px 10px; border-radius: 6px; }}
            QLabel[statusType="success"] {{ color: #10B981; font-weight: 700; }}
            QLabel[statusType="warning"] {{ color: #F59E0B; font-weight: 700; }}
            QLabel[statusType="error"] {{ color: #EF4444; font-weight: 700; }}
            #SpeechStage {{ color: {muted}; border-bottom: 2px solid {border}; padding: 7px 5px; font-size: 11px; font-weight: 700; }}
            #SpeechStage[stageState="complete"] {{ color: {text}; border-bottom-color: {accent}; }}
            #SpeechStage[stageState="active"] {{ color: {accent}; border-bottom: 3px solid {accent}; padding-bottom: 6px; }}
            QPushButton[recording="true"] {{ background: #EF4444; color: white; border-radius: 10px; }}

            /* Signal Deck is intentionally scoped to the Speech workspace. */
            #SignalSpeechPage {{ background: #0A0C10; color: #E2E8F0; }}
            #SignalCommandStrip {{
                background: #11141B;
                border: 1px solid #1E2530;
                border-radius: 3px;
            }}
            #SignalTitle {{
                color: #00DCEB;
                font-family: '{mono_font}';
                font-size: 12px;
                font-weight: 800;
                letter-spacing: 1px;
            }}
            #SignalControls QLabel {{
                color: #94A3B8;
                font-family: '{mono_font}';
                font-size: 10px;
                font-weight: 700;
            }}
            #SignalControls QComboBox {{
                background: #1E2530;
                color: #E2E8F0;
                border: 1px solid #334155;
                border-radius: 3px;
                min-height: 26px;
                padding: 4px 9px;
                font-family: '{mono_font}';
                font-size: 11px;
            }}
            #SignalControls QComboBox:hover, #SignalControls QComboBox:focus {{
                border-color: #00DCEB;
            }}
            #SignalCheck {{
                color: #94A3B8;
                spacing: 6px;
                font-family: '{mono_font}';
                font-size: 10px;
                font-weight: 700;
            }}
            #SignalPrivacyBadge {{
                background: #10261F;
                color: #34D399;
                border: 1px solid #1B5E48;
                border-radius: 3px;
                padding: 6px 9px;
                font-family: '{mono_font}';
                font-size: 10px;
                font-weight: 800;
            }}
            #SignalRecorder {{
                background: #11141B;
                border: 1px solid #1E2530;
                border-radius: 3px;
            }}
            #SignalStatus {{
                color: #94A3B8;
                font-family: '{mono_font}';
                font-size: 11px;
                font-weight: 700;
            }}
            #SignalTimer {{
                color: #E2E8F0;
                font-family: '{mono_font}';
                font-size: 30px;
                font-weight: 700;
                min-width: 104px;
            }}
            #SignalSpeechPage #SpeechStage {{
                background: #0A0C10;
                color: #64748B;
                border: 1px solid #1E2530;
                border-radius: 0px;
                padding: 7px 5px;
                font-family: '{mono_font}';
                font-size: 10px;
                font-weight: 800;
            }}
            #SignalSpeechPage #SpeechStage[stageState="complete"] {{
                color: #34D399;
                border-color: #1B5E48;
            }}
            #SignalSpeechPage #SpeechStage[stageState="active"] {{
                color: #0A0C10;
                background: #00DCEB;
                border-color: #00DCEB;
            }}
            #SignalRecordButton {{
                background: #00DCEB;
                color: #071014;
                border: 1px solid #00DCEB;
                border-radius: 3px;
                padding: 10px 18px;
                font-family: '{mono_font}';
                font-weight: 900;
            }}
            #SignalRecordButton:hover {{ background: #31E8F2; }}
            #SignalRecordButton[recording="true"] {{
                background: #F59E0B;
                color: #0A0C10;
                border-color: #F59E0B;
                border-radius: 3px;
            }}
            #SignalToolButton {{
                background: #11141B;
                color: #CBD5E1;
                border: 1px solid #334155;
                border-radius: 3px;
                padding: 8px 11px;
                font-family: '{mono_font}';
                font-size: 10px;
                font-weight: 700;
            }}
            #SignalToolButton:hover {{ color: #00DCEB; border-color: #00DCEB; }}
            #SignalToolButton:disabled {{ color: #475569; border-color: #1E2530; }}
            #SignalGpuSafety {{
                color: #F59E0B;
                font-family: '{mono_font}';
                font-size: 9px;
                font-weight: 800;
            }}
            #SignalActionStrip {{
                background: #11141B;
                border: 1px solid #1E2530;
                border-radius: 3px;
                padding: 6px;
            }}
            #SignalPaneLabel {{
                background: #11141B;
                color: #94A3B8;
                border: 1px solid #1E2530;
                border-bottom: none;
                padding: 8px 11px;
                font-family: '{mono_font}';
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 1px;
            }}
            #SignalTranscript, #SignalTranslation {{
                background: #0A0C10;
                color: #E2E8F0;
                border: 1px solid #1E2530;
                border-radius: 0px;
                padding: 14px;
                selection-background-color: #00DCEB;
                selection-color: #071014;
                font-family: '{body_font}';
                font-size: 15px;
            }}
            #SignalTranscript:focus {{ border-color: #00DCEB; }}

            #SignalReaderPage, #SignalOcrPage, #SignalNotesPage,
            #SignalAccessPage, #SignalSettingsPage {{
                background: #0A0C10;
                color: #E2E8F0;
            }}
            #SignalReaderPage #PageTitle, #SignalOcrPage #PageTitle,
            #SignalNotesPage #PageTitle, #SignalAccessPage #PageTitle,
            #SignalSettingsPage #PageTitle {{
                color: #E2E8F0;
                font-family: '{mono_font}';
                font-size: 18px;
                font-weight: 800;
                letter-spacing: 1px;
            }}
            #SignalFunctionStrip {{
                background: #11141B;
                border: 1px solid #1E2530;
                border-radius: 3px;
                padding: 8px;
            }}
            #SignalMetaLine {{
                color: #64748B;
                font-family: '{mono_font}';
                font-size: 10px;
            }}
            #SignalReaderText, #SignalOcrText, #SignalOcrTranslation,
            #SignalNoteTitle, #SignalNoteEditor, #SignalNotesList {{
                background: #0A0C10;
                color: #E2E8F0;
                border: 1px solid #1E2530;
                border-radius: 0px;
                padding: 14px;
                selection-background-color: #00DCEB;
                selection-color: #071014;
                font-size: 15px;
            }}
            #SignalReaderText:focus, #SignalOcrText:focus,
            #SignalNoteEditor:focus {{ border-color: #00DCEB; }}
            #SignalReaderPlayer {{
                background: #11141B;
                border: 1px solid #1E2530;
                border-radius: 3px;
            }}
            #SignalTranslatePage #PrimaryButton, #SignalReaderPage #PrimaryButton, #SignalOcrPage #PrimaryButton,
            #SignalNotesPage #PrimaryButton, #SignalAccessPage #PrimaryButton,
            #SignalSettingsPage #PrimaryButton {{
                background: #00DCEB;
                color: #071014;
                border: 1px solid #00DCEB;
                border-radius: 3px;
                font-family: '{mono_font}';
                font-weight: 800;
            }}
            #SignalTranslatePage #SecondaryButton, #SignalReaderPage #SecondaryButton, #SignalOcrPage #SecondaryButton,
            #SignalNotesPage #SecondaryButton, #SignalAccessPage #SecondaryButton,
            #SignalSettingsPage #SecondaryButton {{
                background: #11141B;
                color: #CBD5E1;
                border: 1px solid #334155;
                border-radius: 3px;
                font-family: '{mono_font}';
                font-weight: 700;
            }}
            #SignalTranslatePage #SecondaryButton:hover, #SignalReaderPage #SecondaryButton:hover, #SignalOcrPage #SecondaryButton:hover,
            #SignalNotesPage #SecondaryButton:hover, #SignalAccessPage #SecondaryButton:hover,
            #SignalSettingsPage #SecondaryButton:hover {{
                color: #00DCEB;
                border-color: #00DCEB;
            }}
            #SignalTranslatePage QComboBox, #SignalReaderPage QComboBox, #SignalOcrPage QComboBox,
            #SignalNotesPage QComboBox, #SignalAccessPage QComboBox,
            #SignalSettingsPage QComboBox {{
                background: #1E2530;
                color: #E2E8F0;
                border: 1px solid #334155;
                border-radius: 3px;
                min-height: 26px;
                font-family: '{mono_font}';
            }}
            #SignalAccessCard, #SignalSettingsCard {{
                background: #11141B;
                border: 1px solid #1E2530;
                border-radius: 3px;
            }}
            #SignalAccessPage #CardTitle, #SignalSettingsPage #CardTitle {{
                color: #00DCEB;
                font-family: '{mono_font}';
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 1px;
            }}
            #SignalQrPanel {{
                background: #0A0C10;
                color: #64748B;
                border: 1px dashed #334155;
                padding: 12px;
                font-family: '{mono_font}';
            }}

            /* Signal Deck shared application shell. */
            #Root, #MainArea, #RightPanel, #PageScroll, #PageScrollViewport,
            #PageStack {{ background: #0A0C10; color: #E2E8F0; }}
            #Sidebar {{
                background: #0A0C10;
                border-right: 1px solid #1E2530;
            }}
            #AppTitle {{
                color: #E2E8F0;
                font-family: '{mono_font}';
                font-size: 15px;
                font-weight: 800;
                letter-spacing: .5px;
            }}
            #Sidebar #Muted, #Sidebar #SectionLabel, #Sidebar #LinkLabel {{
                color: #64748B;
                font-family: '{mono_font}';
                font-size: 10px;
                font-weight: 700;
            }}
            #NavButton {{
                text-align: left;
                background: transparent;
                color: #64748B;
                border: 1px solid transparent;
                border-radius: 3px;
                padding: 10px 12px;
                font-family: '{mono_font}';
                font-size: 11px;
                font-weight: 800;
            }}
            #NavButton:hover {{
                background: #11141B;
                color: #CBD5E1;
                border-color: #1E2530;
            }}
            #NavButton:checked {{
                background: #11141B;
                color: #00DCEB;
                border: 1px solid #1E2530;
                border-left: 3px solid #00DCEB;
                padding-left: 10px;
            }}
            #Sidebar #PrimaryButton {{
                background: #00DCEB;
                color: #071014;
                border: 1px solid #00DCEB;
                border-radius: 3px;
                font-family: '{mono_font}';
                font-weight: 800;
            }}
            #SearchBox {{
                background: #11141B;
                color: #CBD5E1;
                border: 1px solid #1E2530;
                border-radius: 3px;
                padding: 8px 12px;
                font-family: '{mono_font}';
                font-size: 11px;
            }}
            #SearchBox:focus {{ border-color: #00DCEB; }}
            #StatusBadge, #FooterBadge {{
                background: #10261F;
                color: #34D399;
                border: 1px solid #1B5E48;
                border-radius: 3px;
                padding: 6px 10px;
                font-family: '{mono_font}';
                font-size: 10px;
                font-weight: 800;
            }}
            #RightPanel #SmallCard {{
                background: #11141B;
                border: 1px solid #1E2530;
                border-radius: 3px;
            }}
            #RightPanel #CardTitle {{
                color: #00DCEB;
                font-family: '{mono_font}';
                font-size: 10px;
                font-weight: 800;
            }}
            #RightPanel #Muted {{ color: #64748B; font-family: '{mono_font}'; font-size: 10px; }}
            #RightPanel #SecondaryButton {{
                background: #11141B;
                color: #CBD5E1;
                border: 1px solid #334155;
                border-radius: 3px;
                font-family: '{mono_font}';
                font-size: 10px;
                font-weight: 700;
            }}
            #RightPanel #SecondaryButton:hover {{
                color: #00DCEB;
                border-color: #00DCEB;
            }}
            #ChromeButton {{
                background: transparent;
                color: #64748B;
                border: 1px solid transparent;
                border-radius: 3px;
            }}
            #ChromeButton:hover {{
                background: #11141B;
                color: #00DCEB;
                border-color: #334155;
            }}
            #Footer {{
                background: #11141B;
                border-top: 1px solid #1E2530;
            }}
            #FooterText, #Footer #Muted {{
                color: #64748B;
                font-family: '{mono_font}';
                font-size: 10px;
            }}

            #SignalTranslatePage {{ background: #0A0C10; color: #E2E8F0; }}
            #SignalTranslatePage #PageTitle {{
                color: #E2E8F0;
                font-family: '{mono_font}';
                font-size: 18px;
                font-weight: 800;
                letter-spacing: 1px;
            }}
            #SignalTranslatePage #TranslateWorkspace {{ background: #0A0C10; border: none; }}
            #SignalTranslatePage #TranslatePane {{
                background: #0A0C10;
                border: 1px solid #1E2530;
                border-radius: 0px;
            }}
            #SignalTranslatePage #PaneHeader, #SignalTranslatePage #PaneFooter {{
                background: #11141B;
                border-color: #1E2530;
                border-radius: 0px;
            }}
            #SignalTranslatePage #PaneTitle {{
                color: #94A3B8;
                font-family: '{mono_font}';
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 1px;
            }}
            #SignalTranslateInput, #SignalTranslateOutput {{
                background: #0A0C10;
                color: #E2E8F0;
                border: none;
                border-radius: 0px;
                padding: 16px;
                selection-background-color: #00DCEB;
                selection-color: #071014;
                font-size: 15px;
            }}
            #SignalTranslateInput:focus {{ border: 1px solid #00DCEB; padding: 15px; }}
            #SignalTranslatePage #Counter {{
                color: #64748B;
                font-family: '{mono_font}';
                font-size: 9px;
            }}
            #SignalTranslatePage #PaneToolButton {{
                background: transparent;
                color: #94A3B8;
                border: 1px solid transparent;
                border-radius: 3px;
                font-family: '{mono_font}';
                font-size: 10px;
            }}
            #SignalTranslatePage #PaneToolButton:hover {{
                color: #00DCEB;
                border-color: #334155;
            }}
            #SignalTranslatePage #SwapButton {{
                background: #11141B;
                color: #00DCEB;
                border: 1px solid #334155;
                border-radius: 3px;
            }}
            #SignalTranslatePlayer {{
                background: #11141B;
                border: 1px solid #1E2530;
                border-radius: 3px;
            }}
        """

        # Signal Deck began as one fixed visual concept. It later grew to
        # style the complete shell and every main page, but retained its
        # hard-coded cyan/dark tokens. Because those rules occur last in the
        # stylesheet they overrode every selected desktop theme. Keep the
        # useful component-specific rules while resolving their legacy tokens
        # through the active theme palette.
        legacy_signal_tokens = {
            "#0A0C10": bg,
            "#11141B": card,
            "#1E2530": border,
            "#334155": border,
            "#E2E8F0": text,
            "#CBD5E1": text,
            "#94A3B8": muted,
            "#64748B": muted,
            "#475569": muted,
            "#00DCEB": accent,
            "#31E8F2": accent_hover,
            "#071014": btn_text,
        }
        for legacy_color, active_color in legacy_signal_tokens.items():
            qss = qss.replace(legacy_color, active_color)
        qss = qss.replace(
            "border-radius: 3px",
            f"border-radius: {control_radius}px",
        )
        return qss

    def _invert_theme_spec(self, spec):
        inverted = dict(spec)
        inverted["dark"] = not spec["dark"]
        if spec["dark"]:
            inverted["bg"] = "#F8FAFC"
            inverted["sidebar"] = "#FFFFFF"
            inverted["card"] = "#FFFFFF"
            inverted["border"] = "#CBD5E1"
            inverted["text"] = "#0F172A"
            inverted["muted"] = "#64748B"
            inverted["nav_active"] = "#E2E8F0"
            inverted["nav_active_text"] = spec["accent"]
        else:
            inverted["bg"] = "#0F172A"
            inverted["sidebar"] = "#1E293B"
            inverted["card"] = "#1E293B"
            inverted["border"] = "#334155"
            inverted["text"] = "#F8FAFC"
            inverted["muted"] = "#94A3B8"
            inverted["nav_active"] = "#334155"
            inverted["nav_active_text"] = "#38BDF8"
        return inverted

    def toggle_color_inversion(self):
        self.color_inversion_active = not getattr(self, "color_inversion_active", False)
        self.apply_style()
        self.set_status(f"Color mode inverted ({'Dark' if self.dark_mode else 'Light'})")

    def apply_style(self):
        theme_id = getattr(self, "current_theme", "broadsheet")
        spec = self.DESKTOP_THEME_SPECS.get(theme_id, self.DESKTOP_THEME_SPECS["broadsheet"])
        if getattr(self, "color_inversion_active", False):
            spec = self._invert_theme_spec(spec)
        self.dark_mode = spec["dark"]
        self.setStyleSheet(self._generate_qss(spec))
        page_background = QColor(spec["bg"])
        for widget in (
            getattr(getattr(self, "page_scroll", None), "viewport", lambda: None)(),
            getattr(self, "pages", None),
        ):
            if widget is None:
                continue
            palette = widget.palette()
            palette.setColor(QPalette.Window, page_background)
            palette.setColor(QPalette.Base, page_background)
            widget.setPalette(palette)
            widget.setAutoFillBackground(True)
            widget.update()
        self.refresh_interface_icons()

    def set_theme(self, theme_id: str):
        if theme_id not in self.DESKTOP_THEME_IDS:
            theme_id = "broadsheet"
        self.current_theme = theme_id
        spec = self.DESKTOP_THEME_SPECS[theme_id]
        if self._persist_settings:
            self.app_settings.setValue("appearance/theme_id", theme_id)
        if hasattr(self, "theme_combo"):
            index = self.theme_combo.findData(theme_id)
            if index >= 0 and self.theme_combo.currentIndex() != index:
                self.theme_combo.blockSignals(True)
                self.theme_combo.setCurrentIndex(index)
                self.theme_combo.blockSignals(False)
        if hasattr(self, "theme_status_label"):
            self.theme_status_label.setText(f"Active Look: {spec['name']}")
        self.apply_style()
        self.animate_page_transition()

    def set_font(self, font_id: str):
        if font_id not in self.DESKTOP_FONT_SPECS:
            font_id = "modern"
        self.current_font = font_id
        font_spec = self.DESKTOP_FONT_SPECS[font_id]
        if self._persist_settings:
            self.app_settings.setValue("appearance/font_id", font_id)
        if hasattr(self, "font_combo"):
            index = self.font_combo.findData(font_id)
            if index >= 0 and self.font_combo.currentIndex() != index:
                self.font_combo.blockSignals(True)
                self.font_combo.setCurrentIndex(index)
                self.font_combo.blockSignals(False)
        if hasattr(self, "font_status_label"):
            self.font_status_label.setText(f"Active Font: {font_spec['name']}")
        self.apply_style()
        self.animate_page_transition()

    def set_motion(self, motion_id: str):
        if motion_id not in {"full", "reduced", "off"}:
            motion_id = "full"
        self.current_motion = motion_id
        if self._persist_settings:
            self.app_settings.setValue("appearance/motion", motion_id)
        if hasattr(self, "motion_combo"):
            index = self.motion_combo.findData(motion_id)
            if index >= 0 and self.motion_combo.currentIndex() != index:
                self.motion_combo.blockSignals(True)
                self.motion_combo.setCurrentIndex(index)
                self.motion_combo.blockSignals(False)
        if hasattr(self, "motion_status_label"):
            label = {"full": "Full motion", "reduced": "Reduced motion", "off": "Motion off"}[motion_id]
            self.motion_status_label.setText(f"Active Motion: {label}")

    def motion_duration(self, milliseconds: int) -> int:
        mode = getattr(self, "current_motion", "full")
        if mode == "off":
            return 0
        if mode == "reduced":
            return max(45, min(100, milliseconds // 3))
        return milliseconds

    def animate_page_transition(self):
        current_widget = self.pages.currentWidget() if hasattr(self, "pages") else None
        if current_widget is None:
            return

        previous_animation = getattr(current_widget, "_fade_anim", None)
        if previous_animation is not None:
            previous_animation.stop()
            previous_animation.deleteLater()
            current_widget._fade_anim = None
        if current_widget.graphicsEffect() is not None:
            current_widget.setGraphicsEffect(None)

        motion_ms = self.DESKTOP_LOOK_METRICS.get(
            getattr(self, "current_theme", "broadsheet"),
            self.DESKTOP_LOOK_METRICS["broadsheet"],
        )[2]
        duration = self.motion_duration(motion_ms)
        if duration <= 0:
            current_widget.update()
            return

        effect = QGraphicsOpacityEffect(current_widget)
        current_widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", current_widget)
        animation.setDuration(duration)
        animation.setStartValue(0.2)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)

        def finish_transition():
            if current_widget.graphicsEffect() is effect:
                current_widget.setGraphicsEffect(None)
            if getattr(current_widget, "_fade_anim", None) is animation:
                current_widget._fade_anim = None
            animation.deleteLater()
            current_widget.update()
            if hasattr(self, "page_scroll"):
                self.page_scroll.viewport().update()

        animation.finished.connect(finish_transition)
        current_widget._fade_anim = animation
        animation.start()

    def refresh_interface_icons(self):
        normal = "#64748B"
        active = "#00DCEB"
        for name, button in getattr(self, "nav_buttons", {}).items():
            icon_name, _ = self.nav_metadata.get(name, ("info", name))
            button.setIcon(app_icon(icon_name, 20, normal=normal, active=active))
        if hasattr(self, "sidebar_toggle_btn"):
            icon_name = "chevron-right" if self.sidebar_collapsed else "chevron-left"
            self.sidebar_toggle_btn.setIcon(app_icon(icon_name, 18, normal=normal, active=active))
        if hasattr(self, "inspector_toggle_btn"):
            self.inspector_toggle_btn.setIcon(app_icon("panel", 19, normal=normal, active=active))
        if hasattr(self, "search_action"):
            self.search_action.setIcon(app_icon("search", 18, normal=normal, active=active))
        for button in getattr(self, "responsive_buttons", []):
            self.apply_media_button_icon(button)
            self.apply_contextual_button_icon(button)

    def toggle_sidebar(self):
        self.sidebar_user_override = not self.sidebar_collapsed
        self._responsive_mode = None
        self.update_responsive_layout()
        self.refresh_interface_icons()

    def toggle_inspector(self):
        self.inspector_user_override = not self.right_panel.isVisible()
        self._responsive_mode = None
        self.update_responsive_layout()

    # ---------- Shared helpers ----------
    def run_background(self, task, on_success, on_error=None):
        print("[DEBUG] run_background: submitting task")
        future = self.executor.submit(task)
        timer = QTimer(self)
        timer.setInterval(100)

        def check_future():
            if not future.done():
                return
            print("[DEBUG] run_background: future done, calling on_success")
            timer.stop()
            timer.deleteLater()
            try:
                result = future.result()
                print(f"[DEBUG] run_background: result = {str(result)[:200]}")
                on_success(result)
                print("[DEBUG] run_background: on_success completed")
            except Exception as exc:
                print(f"[DEBUG] run_background: EXCEPTION: {exc!r}")
                if on_error is not None:
                    on_error(exc)
                    return
                exc_str = str(exc)
                if not getattr(self, "_is_backend_online", False) and any(
                    err_msg in exc_str for err_msg in ("ConnectionRefused", "Max retries", "Failed to establish a new connection")
                ):
                    if hasattr(self, "system_badge"):
                        self.system_badge.setText("● Starting Backend...")
                    self.set_status("Initializing local backend services...")
                else:
                    self.set_status(f"Error: {exc}", error=True)
                    if hasattr(self, "system_badge"):
                        self.system_badge.setText("● Backend Offline")

        timer.timeout.connect(check_future)
        timer.start()

    def set_status(self, message, error=False):
        self.footer_left.setText(("⚠ " if error else "● ") + message)
        if error:
            self.footer_left.setProperty('statusType', 'error')
        else:
            self.footer_left.setProperty('statusType', 'success')
        self.footer_left.style().unpolish(self.footer_left)
        self.footer_left.style().polish(self.footer_left)

    def ensure_audio_backend(self) -> bool:
        if getattr(self, "audio_backend_ready", False):
            return True
        message = "Audio backend unavailable"
        if getattr(self, "audio_backend_error", None):
            message += f": {self.audio_backend_error}"
        self.set_status(message, error=True)
        return False


    def apply_app_icon(self):
        """Apply the desktop/taskbar icon when the app is run directly."""
        try:
            set_windows_app_user_model_id()
            icon_path = app_icon_path()
            if icon_path.exists():
                icon = QIcon(str(icon_path))
                self.setWindowIcon(icon)
                app = QApplication.instance()
                if app is not None:
                    app.setWindowIcon(icon)
        except Exception:
            pass

    def register_band_widget(self, widget):
        """Register a widget that should stay inside the medium-width content band."""
        if widget not in self.responsive_band_widgets:
            self.responsive_band_widgets.append(widget)
        widget.setMinimumWidth(0)
        widget.setSizePolicy(QSizePolicy.Preferred, widget.sizePolicy().verticalPolicy())
        return widget

    def register_compact_card(self, widget):
        """Register a card/player that should shrink with the medium-width content band."""
        if widget not in self.responsive_compact_cards:
            self.responsive_compact_cards.append(widget)
        widget.setMinimumWidth(0)
        widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        return widget

    def focus_search(self):
        self.search_box.setFocus()
        self.search_box.selectAll()
        self.set_status("Search focused")

    def run_global_search(self):
        query = self.search_box.text().strip().lower()
        if not query:
            self.set_status("Enter a search term")
            return

        matches = []
        for page, items in self.recent_history.items():
            for item in items:
                if query in item[1].lower():
                    matches.append((page, item[1]))

        if matches:
            page, text = matches[0]
            self.switch_page(page)
            self.set_status(f"Found in {page}: {text}")
        else:
            self.set_status(f"No recent match for: {query}")

    def add_recent(self, page_name, label, icon=None):
        if page_name not in self.recent_history:
            self.recent_history[page_name] = []
        default_icons = {name: "•" for name in self.recent_history}
        entry = (icon or default_icons.get(page_name, "•"), str(label), "now")
        old_items = [item for item in self.recent_history[page_name] if item[1] != entry[1]]
        self.recent_history[page_name] = [entry] + old_items[:5]
        if self.current_page_name == page_name:
            self.update_recent_items(page_name)

    def language_box(self, default="en", include_auto=False):
        box = WheelSafeComboBox()
        if include_auto:
            box.addItem("Auto", "auto")
        for label, code in LANGUAGES:
            box.addItem(label, code)
        idx = box.findData(default)
        if idx >= 0:
            box.setCurrentIndex(idx)
        return self.make_responsive_combo(box)

    def page_title(self, title, subtitle=None):
        wrap = QVBoxLayout()
        label = QLabel(title)
        label.setObjectName("PageTitle")
        wrap.addWidget(label)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("Muted")
            wrap.addWidget(sub)
        return wrap

    def make_responsive_combo(self, combo):
        combo.setMinimumWidth(150)
        combo.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        return combo

    def make_responsive_text_edit(self, edit):
        edit.setMinimumWidth(0)
        edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.responsive_text_edits.append(edit)
        self.register_band_widget(edit)
        return edit

    def register_responsive_button(self, button, compact_text=None, ultra_text=None, group="general"):
        def clean_label(value):
            return re.sub(r"^[^\w+]+", "", value or "").strip()

        full_text = clean_label(button.text())
        compact_text = clean_label(compact_text or full_text)
        ultra_text = clean_label(ultra_text or compact_text or full_text)
        button.setText(full_text)
        button._lf_full_text = full_text
        button._lf_compact_text = compact_text
        button._lf_ultra_text = ultra_text
        button.setMinimumWidth(0)
        button.setToolTip(button.text())
        button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        if group == "playback":
            button.setProperty("lfPlayback", True)
        self.apply_media_button_icon(button)
        self.apply_contextual_button_icon(button)
        self.responsive_buttons.append(button)
        if group == "export":
            self.responsive_export_buttons.append(button)
        if group == "playback":
            self.responsive_playback_buttons.append(button)
        return button

    def register_general_button(self, button, compact_text=None):
        full_text = re.sub(r"^[^\w+]+", "", button.text() or "").strip()
        compact_text = re.sub(r"^[^\w+]+", "", compact_text or full_text).strip()
        button.setText(full_text)
        button._lf_full_text = full_text
        button._lf_compact_text = compact_text
        button.setToolTip(button.text())
        button.setMinimumWidth(0)
        button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.apply_media_button_icon(button)
        self.apply_contextual_button_icon(button)
        if button not in self.responsive_general_buttons:
            self.responsive_general_buttons.append(button)
        return button

    def media_icon_kind(self, text):
        text = (text or "").lower()
        if "rewind" in text or "restart" in text or "back" in text:
            return "rewind"
        if "pause" in text:
            return "pause"
        if "stop" in text:
            return "stop"
        if "read" in text or "play" in text or "from cursor" in text:
            return "play"
        return None

    def media_icon_text(self, text):
        kind = self.media_icon_kind(text)
        return "" if kind else text

    def apply_media_button_icon(self, button):
        """Apply theme-safe vector playback icons without font glyphs."""
        kind = self.media_icon_kind(getattr(button, "_lf_full_text", button.text()))
        if not kind:
            return
        dark = getattr(self, "dark_mode", False)
        primary = button.objectName() == "PrimaryButton"
        normal = "#FFFFFF" if primary else ("#E6EBF2" if dark else "#344054")
        active = "#FFFFFF" if primary else ("#79B3FF" if dark else "#0B57D0")
        button.setIcon(app_icon(kind, 18, normal=normal, active=active, selected=normal))
        button.setIconSize(QSize(18, 18))
        button.setProperty("lfMediaButton", True)

    def apply_contextual_button_icon(self, button):
        """Give common workflow actions consistent semantic icons."""
        if self.media_icon_kind(getattr(button, "_lf_full_text", button.text())):
            return
        text = getattr(button, "_lf_full_text", button.text()).lower()
        kind = None
        if "translate" in text:
            kind = "translate"
        elif "record" in text:
            kind = "microphone"
        elif "import" in text:
            kind = "upload"
        elif "export" in text:
            kind = "download"
        elif "save" in text:
            kind = "save"
        elif "copy" in text:
            kind = "copy"
        if kind is None:
            return
        button._lf_icon_kind = kind
        dark = getattr(self, "dark_mode", False)
        primary = button.objectName() == "PrimaryButton"
        normal = "#FFFFFF" if primary else ("#D6DEE9" if dark else "#52606D")
        active = "#FFFFFF" if primary else ("#79B3FF" if dark else "#0B57D0")
        button.setIcon(app_icon(kind, 18, normal=normal, active=active, selected=normal))
        button.setIconSize(QSize(18, 18))

    def set_language_grid_layout(self, grid, first_label, first_widget, second_label, second_widget, stacked, fit=False):
        while grid.count():
            # Keep widgets parented to their host while rearranging the grid.
            # setParent(None) makes a QWidget a temporary top-level window;
            # during interactive resizing Windows can visibly flash that tiny
            # window before it is inserted again.
            grid.takeAt(0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        # Reset stale stretch settings whenever the responsive layout changes.
        # Without this, a previous wide layout can leave empty columns that push
        # Target/export controls outside the visible medium-width page.
        for col in range(8):
            grid.setColumnStretch(col, 0)
            grid.setColumnMinimumWidth(col, 0)
        for row in range(4):
            grid.setRowStretch(row, 0)
            grid.setRowMinimumHeight(row, 0)

        first_label.setVisible(not stacked)
        second_label.setVisible(not stacked)
        if stacked:
            first_widget.setToolTip(first_label.text())
            second_widget.setToolTip(second_label.text())
            grid.addWidget(first_widget, 0, 0)
            grid.addWidget(second_widget, 1, 0)
            grid.setColumnStretch(0, 1)
            grid.setRowMinimumHeight(0, 46)
            grid.setRowMinimumHeight(1, 46)
            return

        first_label.setVisible(True)
        second_label.setVisible(True)
        first_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        second_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        grid.addWidget(first_label, 0, 0)
        grid.addWidget(first_widget, 0, 1)
        grid.addWidget(second_label, 0, 2)
        grid.addWidget(second_widget, 0, 3)

        if fit:
            # Medium-width fit mode keeps the original left-to-right Source / Target
            # arrangement, but packs the four controls together and leaves all extra
            # width after the Target field. This avoids detached combo arrows and
            # horizontal scrolling while preserving the normal desktop layout.
            grid.setColumnStretch(4, 1)
            first_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            second_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        else:
            first_widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            second_widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            grid.setColumnStretch(1, 1)
            grid.setColumnStretch(3, 1)


    def set_action_grid_layout(self, grid, buttons, compact):
        while grid.count():
            # Taking an item out of a layout is enough. Preserve the widget's
            # parent so action buttons never become transient tool windows.
            grid.takeAt(0)
        grid.setHorizontalSpacing(9 if compact else 10)
        grid.setVerticalSpacing(8)
        for col in range(8):
            grid.setColumnStretch(col, 0)
            grid.setColumnMinimumWidth(col, 0)
        for row in range(3):
            grid.setRowStretch(row, 0)
            grid.setRowMinimumHeight(row, 0)

        # Keep one clean row in the medium layout. Controls stay packed in the
        # same visual band instead of drifting to the far right or requiring
        # horizontal scrolling.
        for idx, button in enumerate(buttons):
            grid.addWidget(button, 0, idx)
        grid.setColumnStretch(len(buttons), 1)


    def switch_page(self, page_name):
        self.current_page_name = page_name
        self.pages.setCurrentIndex(self.page_index[page_name])
        self.animate_page_transition()

        if hasattr(self, "page_scroll"):
            QTimer.singleShot(0, lambda: self.page_scroll.verticalScrollBar().setValue(0))
        for name, button in self.nav_buttons.items():
            button.setChecked(name == page_name)
        self.update_right_panel(page_name)
        self.update_recent_items(page_name)
        self.update_responsive_layout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start(50)

    def _update_responsive_layout_legacy(self):
        if not hasattr(self, "right_panel") or not hasattr(self, "sidebar"):
            return

        width = self.width()
        # Stable Phase 5 policy: keep a medium-width floor and scale the page
        # proportionally at that floor instead of forcing a horizontal canvas.
        if width < 1350:
            mode = "medium"
        else:
            mode = "wide"

        compact_sidebar = False
        ultra_compact = False
        responsive_state = (mode, ultra_compact)
        if responsive_state == getattr(self, "_responsive_mode", None):
            return
        self._responsive_mode = responsive_state

        self.right_panel.setVisible(mode == "wide")
        self.right_panel.setMaximumWidth(330 if mode == "wide" else 0)

        # Narrow windows need a genuinely narrow sidebar. Do not leave brand text
        # or nested labels visible because that forces horizontal overflow.
        self.sidebar.setFixedWidth(58 if compact_sidebar else 288)
        sidebar_layout = self.sidebar.layout()
        if sidebar_layout:
            sidebar_layout.setContentsMargins(8 if compact_sidebar else 26, 18 if compact_sidebar else 22, 8 if compact_sidebar else 24, 18 if compact_sidebar else 22)
            sidebar_layout.setSpacing(11 if compact_sidebar else 16)

        if hasattr(self, "logo_label"):
            self.logo_label.setText("L" if compact_sidebar else "💬")
            self.logo_label.setFixedSize(38 if compact_sidebar else 58, 58 if compact_sidebar else 58)
        for attr in ["brand_title", "brand_subtitle"]:
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setVisible(not compact_sidebar)

        for name, button in self.nav_buttons.items():
            icon, label = self.nav_metadata.get(name, ("•", name))
            button.setText(icon if compact_sidebar else f"{icon}   {label}")
            button.setToolTip(label)
            button.setMinimumWidth(0)
            button.setMaximumWidth(44 if compact_sidebar else 9999)

        for attr in ["recent_header_label", "recent_more_label", "sidebar_import_btn"]:
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setVisible(not compact_sidebar)

        if hasattr(self, "recent_items_box"):
            for idx in range(self.recent_items_box.count()):
                item = self.recent_items_box.itemAt(idx)
                widget = item.widget()
                layout = item.layout()
                if widget is not None:
                    widget.setVisible(not compact_sidebar)
                if layout is not None:
                    for child_idx in range(layout.count()):
                        child_item = layout.itemAt(child_idx)
                        child_widget = child_item.widget() if child_item is not None else None
                        if child_widget is not None:
                            child_widget.setVisible(not compact_sidebar)

        if hasattr(self, "main_area_layout"):
            if mode == "wide":
                self.main_area_layout.setContentsMargins(28, 20, 12, 14)
                self.main_area_layout.setSpacing(18)
            elif mode == "medium":
                self.main_area_layout.setContentsMargins(18, 16, 14, 10)
                self.main_area_layout.setSpacing(12)
            else:
                self.main_area_layout.setContentsMargins(14, 14, 14, 10)
                self.main_area_layout.setSpacing(10)

        if hasattr(self, "page_scroll"):
            self.page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        if hasattr(self, "pages"):
            self.pages.setMinimumWidth(0)
        if hasattr(self, "search_box"):
            self.search_box.setMaximumWidth(520 if mode == "wide" else 300)
            self.search_box.setPlaceholderText("🔎  Search anything..." if mode == "medium" else "🔎  Search anything...                                      Ctrl + K")
        if hasattr(self, "system_badge"):
            self.system_badge.setText("● Ready" if mode == "compact" else "● Offline Ready")

        # Balanced medium layout: all major workflow fields share the same
        # compact visual band. This removes horizontal scroll, keeps dropdown
        # arrows attached to their fields, and leaves only vertical scrolling
        # for lower playback controls.
        side_width = 288 if not compact_sidebar else 58
        panel_width = 0 if mode == "medium" else 330
        content_width = max(620, width - side_width - panel_width - 120)
        medium_band_width = max(640, min(800, int(content_width * 0.80)))
        medium_combo_width = max(190, min(235, int((medium_band_width - 150) / 2)))
        for attr in ["translate_source", "translate_target", "reader_lang", "reader_tts_lang", "speech_language", "speech_target_language", "speech_correction_mode", "ocr_lang"]:
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setMaximumWidth(medium_combo_width if mode == "medium" else 9999)
                widget.setMinimumWidth(170 if mode == "medium" else 0)
                widget.setMinimumHeight(34 if mode == "medium" else 40)
        for widget in getattr(self, "responsive_band_widgets", []):
            if widget is not None:
                widget.setMaximumWidth(medium_band_width if mode == "medium" else 9999)
        for widget in getattr(self, "responsive_compact_cards", []):
            if widget is not None:
                widget.setMaximumWidth(medium_band_width if mode == "medium" else 9999)
        for edit in getattr(self, "responsive_text_edits", []):
            if mode == "medium":
                # Keep the boxes usable in the medium layout. The old 82px cap
                # made transcripts unreadable; vertical page scroll absorbs
                # the extra height, per the Phase 5 policy.
                edit.setMinimumHeight(58)
                edit.setMaximumHeight(160)
            else:
                edit.setMaximumHeight(9999)
        for attr in ["translate_input", "translate_output"]:
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setMinimumHeight(58 if mode == "medium" else 112)
                widget.setMaximumHeight(150 if mode == "medium" else 9999)

        if hasattr(self, "translate_controls_grid"):
            self.set_language_grid_layout(self.translate_controls_grid, self.translate_source_label, self.translate_source, self.translate_target_label, self.translate_target, False, fit=(mode == "medium"))
        if hasattr(self, "reader_controls_grid"):
            self.set_language_grid_layout(self.reader_controls_grid, self.reader_ocr_label, self.reader_lang, self.reader_tts_label, self.reader_tts_lang, False, fit=(mode == "medium"))
        if hasattr(self, "translate_action_grid") and hasattr(self, "translate_action_buttons"):
            self.set_action_grid_layout(self.translate_action_grid, self.translate_action_buttons, mode == "medium")
        if hasattr(self, "ocr_controls_host"):
            self.ocr_controls_host.setMaximumWidth(medium_band_width if mode == "medium" else 9999)
        if hasattr(self, "ocr_text"):
            self.ocr_text.setMinimumHeight(180 if mode == "medium" else 260)
            self.ocr_text.setMaximumHeight(260 if mode == "medium" else 9999)

        for button in getattr(self, "responsive_buttons", []):
            is_playback = button in getattr(self, "responsive_playback_buttons", [])
            if mode == "wide":
                label_attr = "_lf_full_text"
            elif is_playback:
                label_attr = "_lf_ultra_text"
            else:
                label_attr = "_lf_compact_text"
            text = getattr(button, label_attr, button.text())
            if mode != "wide" and is_playback:
                text = self.media_icon_text(getattr(button, "_lf_full_text", text))
            button.setText(text)
            button.setToolTip(getattr(button, "_lf_full_text", text))
            self.apply_media_button_icon(button)
            if mode == "wide":
                button.setMaximumWidth(9999)
            elif button in getattr(self, "responsive_export_buttons", []):
                # No hard max width: rows that end in a stretch keep these at
                # their small preferred size, while rows without a stretch
                # (Speech EXPORT) fill evenly instead of floating with gaps.
                button.setMinimumWidth(56)
                button.setMaximumWidth(9999)
                button.setMaximumHeight(36)
            elif is_playback:
                button.setMinimumWidth(52)
                button.setMaximumWidth(58)
                button.setMaximumHeight(38)
            else:
                button.setMinimumWidth(92)
                button.setMaximumWidth(112)
                button.setMaximumHeight(38)

        for button in getattr(self, "responsive_general_buttons", []):
            full_text = getattr(button, "_lf_full_text", button.text())
            if mode == "medium":
                compact = getattr(button, "_lf_compact_text", button.text())
                if self.media_icon_kind(full_text):
                    compact = self.media_icon_text(full_text)
                    button.setMinimumWidth(52)
                else:
                    button.setMinimumWidth(80)
                # Let the buttons fill their row like the wide layout does.
                # Hard max widths left the un-stretched Speech rows with big
                # floating gaps between tiny buttons.
                button.setMaximumWidth(9999)
                button.setText(compact)
                button.setMaximumHeight(38)
            else:
                button.setText(full_text)
                button.setMaximumWidth(9999)
                button.setMaximumHeight(9999)
            self.apply_media_button_icon(button)

        for edit in getattr(self, "responsive_text_edits", []):
            edit.setMinimumWidth(0)

        # Medium layout keeps the waveform readable while compressing the
        # player vertically; icon-only playback buttons keep controls clear
        # of the waveform.
        for attr in ["translate_waveform", "reader_waveform", "speech_waveform"]:
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setVisible(True)
                widget.setMinimumHeight(26 if mode == "medium" else 44)
                widget.setMaximumHeight(32 if mode == "medium" else 64)
        for attr in ["translate_player_card", "reader_player_card"]:
            widget = getattr(self, attr, None)
            if widget is not None:
                # 100-132px fits card margins (28) + waveform row (~32) +
                # a 38px control row with spacing. The old 58-70px clamp
                # forced Qt to paint those rows on top of each other.
                widget.setMinimumHeight(100 if mode == "medium" else 126)
                widget.setMaximumHeight(132 if mode == "medium" else 9999)
                widget.setMaximumWidth(medium_band_width if mode == "medium" else 9999)
        recorder = getattr(self, "speech_recorder_card", None)
        if recorder is not None:
            # Never height-clamp the recorder card: it stacks status + timer +
            # waveform + two labelled button rows (~230px of content), so any
            # cap made everything overlap into unreadable slivers. Only its
            # width follows the medium band; vertical scroll handles the rest.
            recorder.setMinimumHeight(0)
            recorder.setMaximumHeight(9999)
            recorder.setMaximumWidth(medium_band_width if mode == "medium" else 9999)
        for attr in ["translate_time_right", "reader_time_right"]:
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setVisible(mode == "wide")
        for attr in ["translate_speed_label", "reader_speed_label", "translate_speed", "reader_speed"]:
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setVisible(mode == "wide")

        if hasattr(self, "scroll_hint"):
            self.scroll_hint.setVisible(mode == "medium" and self.current_page_name in {"Translate", "Reader", "Speech"})

        if hasattr(self, "footer"):
            self.footer.setFixedHeight(48 if mode == "medium" else 70)
        if hasattr(self, "footer_center"):
            self.footer_center.setVisible(True)
        if hasattr(self, "footer_right"):
            self.footer_right.setVisible(mode == "wide")

    def update_responsive_layout(self):
        """Keep every workflow usable while navigation and details flex around it."""
        if not hasattr(self, "right_panel") or not hasattr(self, "sidebar"):
            return

        width = self.width()
        mode = "medium" if width < 1350 else "wide"
        auto_compact_sidebar = width < 1280
        compact_sidebar = (
            auto_compact_sidebar
            if self.sidebar_user_override is None
            else bool(self.sidebar_user_override)
        )
        auto_show_inspector = width >= 1520
        show_inspector = (
            auto_show_inspector
            if self.inspector_user_override is None
            else bool(self.inspector_user_override)
        )
        self.sidebar_collapsed = compact_sidebar
        self.inspector_collapsed = not show_inspector

        short_window = self.height() < 780
        responsive_state = (mode, compact_sidebar, show_inspector, short_window, self.current_page_name)
        self._responsive_mode = responsive_state

        self.right_panel.setVisible(show_inspector)
        self.right_panel.setFixedWidth(278 if show_inspector else 0)
        
        target_width = 72 if compact_sidebar else 238
        if not hasattr(self, "_sidebar_anim"):
            self._sidebar_anim = QPropertyAnimation(self.sidebar, b"maximumWidth")
            self._sidebar_anim.setDuration(200)
            self._sidebar_anim.setEasingCurve(QEasingCurve.InOutCubic)
        
        self._sidebar_anim.setEndValue(target_width)
        self._sidebar_anim.start()

        sidebar_layout = self.sidebar.layout()
        if sidebar_layout:
            sidebar_layout.setContentsMargins(
                10 if compact_sidebar else 16,
                18,
                10 if compact_sidebar else 16,
                16,
            )
            sidebar_layout.setSpacing(9 if compact_sidebar else 10)

        if hasattr(self, "logo_label"):
            self.logo_label.setVisible(not compact_sidebar)
            self.logo_label.setFixedSize(42, 42)
        for attr in ("brand_title", "brand_subtitle"):
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setVisible(not compact_sidebar)

        for name, button in self.nav_buttons.items():
            _, label = self.nav_metadata.get(name, ("info", name))
            button.setText("" if compact_sidebar else label)
            button.setToolTip(label)
            button.setAccessibleName(label)
            button.setFixedWidth(52 if compact_sidebar else 206)
            button.setIconSize(QSize(21, 21))

        if hasattr(self, "sidebar_toggle_btn"):
            toggle_label = "Expand navigation" if compact_sidebar else "Collapse navigation"
            self.sidebar_toggle_btn.setToolTip(toggle_label)
            self.sidebar_toggle_btn.setAccessibleName(toggle_label)
            self.sidebar_toggle_btn.setFixedSize(34, 34)

        for attr in ("recent_header_label", "recent_more_label", "sidebar_import_btn"):
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setVisible(not compact_sidebar)
        if hasattr(self, "recent_items_box"):
            for index in range(self.recent_items_box.count()):
                item = self.recent_items_box.itemAt(index)
                if item.widget() is not None:
                    item.widget().setVisible(not compact_sidebar)
                child_layout = item.layout()
                if child_layout is not None:
                    for child_index in range(child_layout.count()):
                        child = child_layout.itemAt(child_index)
                        if child.widget() is not None:
                            child.widget().setVisible(not compact_sidebar)

        if mode == "wide":
            self.main_area_layout.setContentsMargins(24, 18, 20, 12)
            self.main_area_layout.setSpacing(14)
        else:
            self.main_area_layout.setContentsMargins(18, 14, 16, 10)
            self.main_area_layout.setSpacing(11)

        self.page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.pages.setMinimumWidth(0)
        self.search_box.setMaximumWidth(520 if mode == "wide" else 380)
        self.search_box.setMinimumWidth(320 if mode == "medium" else 360)
        self.search_box.setPlaceholderText(
            "Search recent activity" if mode == "medium" else "Search recent activity  •  Ctrl+K"
        )
        self.system_badge.setText("● Offline ready")
        inspector_label = "Hide details panel" if show_inspector else "Show details panel"
        self.inspector_toggle_btn.setToolTip(inspector_label)
        self.inspector_toggle_btn.setAccessibleName(inspector_label)

        side_width = 72 if compact_sidebar else 238
        panel_width = 278 if show_inspector else 0
        content_width = max(620, width - side_width - panel_width - 70)
        medium_band_width = max(620, min(900, int(content_width * 0.92)))
        medium_combo_width = max(180, min(230, int((medium_band_width - 130) / 2)))

        combo_names = (
            "translate_source", "translate_target", "reader_lang", "reader_tts_lang",
            "speech_language", "speech_target_language", "speech_correction_mode", "ocr_lang",
        )
        for attr in combo_names:
            widget = getattr(self, attr, None)
            if widget is not None:
                is_translate_combo = widget in {
                    getattr(self, "translate_source", None),
                    getattr(self, "translate_target", None),
                }
                widget.setMaximumWidth(190 if is_translate_combo else (medium_combo_width if mode == "medium" else 9999))
                widget.setMinimumWidth(140 if is_translate_combo else 150)
                widget.setMinimumHeight(34 if mode == "medium" else 38)

        if hasattr(self, "translate_workspace"):
            self.translate_workspace.setMinimumHeight(300)
            self.translate_workspace.setMaximumHeight(420 if short_window else 9999)

        translate_edits = {
            getattr(self, "translate_input", None),
            getattr(self, "translate_output", None),
        }
        unconstrained_bands = translate_edits | {getattr(self, "translate_action_host", None)}
        for widget in self.responsive_band_widgets:
            if widget is not None:
                widget.setMaximumWidth(
                    9999 if widget in unconstrained_bands else (medium_band_width if mode == "medium" else 9999)
                )
        for widget in self.responsive_compact_cards:
            if widget is not None:
                is_translate_player = widget is getattr(self, "translate_player_card", None)
                widget.setMaximumWidth(
                    9999 if is_translate_player else (medium_band_width if mode == "medium" else 9999)
                )
        for edit in self.responsive_text_edits:
            edit.setMinimumWidth(0)
            if edit is getattr(self, "health_output", None):
                edit.setMinimumHeight(160)
                edit.setMaximumHeight(9999)
            elif edit in translate_edits:
                edit.setMinimumHeight(190)
                edit.setMaximumHeight(9999)
            elif mode == "medium":
                edit.setMinimumHeight(58)
                edit.setMaximumHeight(160)
            else:
                edit.setMaximumHeight(9999)

        if hasattr(self, "reader_controls_grid"):
            self.set_language_grid_layout(
                self.reader_controls_grid,
                self.reader_ocr_label,
                self.reader_lang,
                self.reader_tts_label,
                self.reader_tts_lang,
                False,
                fit=(mode == "medium"),
            )
        if hasattr(self, "translate_action_grid"):
            self.set_action_grid_layout(self.translate_action_grid, self.translate_action_buttons, mode == "medium")
        if hasattr(self, "ocr_controls_host"):
            self.ocr_controls_host.setMaximumWidth(medium_band_width if mode == "medium" else 9999)
        if hasattr(self, "ocr_text"):
            self.ocr_text.setMinimumHeight(180 if mode == "medium" else 260)
            self.ocr_text.setMaximumHeight(260 if mode == "medium" else 9999)

        for button in self.responsive_buttons:
            is_playback = button in self.responsive_playback_buttons
            if mode == "wide":
                text = getattr(button, "_lf_full_text", button.text())
            elif is_playback:
                text = ""
            else:
                text = getattr(button, "_lf_compact_text", button.text())
            button.setText(text)
            button.setToolTip(getattr(button, "_lf_full_text", text))
            self.apply_media_button_icon(button)
            if mode == "wide":
                button.setMinimumWidth(0)
                button.setMaximumWidth(9999)
                button.setMaximumHeight(9999)
            elif button in self.responsive_export_buttons:
                button.setMinimumWidth(56)
                button.setMaximumWidth(9999)
                button.setMaximumHeight(38)
            elif is_playback:
                button.setMinimumWidth(42)
                button.setMaximumWidth(46)
                button.setMaximumHeight(38)
            else:
                button.setMinimumWidth(88)
                button.setMaximumWidth(116)
                button.setMaximumHeight(38)

        for button in self.responsive_general_buttons:
            full_text = getattr(button, "_lf_full_text", button.text())
            if mode == "medium":
                button.setText("" if self.media_icon_kind(full_text) else getattr(button, "_lf_compact_text", full_text))
                button.setMinimumWidth(42 if self.media_icon_kind(full_text) else 80)
                button.setMaximumHeight(38)
            else:
                button.setText(full_text)
                button.setMinimumWidth(0)
                button.setMaximumHeight(9999)
            button.setMaximumWidth(9999)
            self.apply_media_button_icon(button)

        for attr in ("translate_waveform", "reader_waveform", "speech_waveform"):
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setVisible(True)
                widget.setMinimumHeight(26 if mode == "medium" else 44)
                widget.setMaximumHeight(32 if mode == "medium" else 64)
        for attr in ("translate_player_card", "reader_player_card"):
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setMinimumHeight(100 if mode == "medium" else 126)
                widget.setMaximumHeight(132 if mode == "medium" else 9999)
        recorder = getattr(self, "speech_recorder_card", None)
        if recorder is not None:
            recorder.setMinimumHeight(0)
            recorder.setMaximumHeight(9999)
            recorder.setMaximumWidth(medium_band_width if mode == "medium" else 9999)
        for attr in ("translate_time_right", "reader_time_right"):
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setVisible(mode == "wide")
        for attr in ("translate_speed_label", "reader_speed_label", "translate_speed", "reader_speed"):
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setVisible(mode == "wide")

        self.scroll_hint.setVisible(mode == "medium" and self.current_page_name in {"Reader", "Speech"})
        self.footer.setFixedHeight(44 if mode == "medium" else 46)
        self.footer_center.setVisible(True)
        self.footer_right.setVisible(mode == "wide" and width >= 1420)
        self.refresh_interface_icons()

    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            child = item.layout()
            if child:
                self.clear_layout(child)

    def update_recent_items(self, page_name):
        if not hasattr(self, "recent_items_box"):
            return
        self.clear_layout(self.recent_items_box)
        items = self.recent_history.get(page_name, [])
        if not items:
            items = [("•", f"No recent {page_name.lower()} items", "")]
        for icon, text, time_label in items[:6]:
            row = QHBoxLayout()
            name = QLabel(f"{icon}  {text}")
            name.setObjectName("Muted")
            stamp = QLabel(time_label)
            stamp.setObjectName("Muted")
            row.addWidget(name)
            row.addStretch(1)
            row.addWidget(stamp)
            self.recent_items_box.addLayout(row)

    def info_card(self, title, rows):
        card = Card("SmallCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("CardTitle")
        layout.addWidget(heading)
        for left, right in rows:
            row = QHBoxLayout()
            l = QLabel(left)
            l.setObjectName("Muted")
            r = QLabel(str(right))
            r.setAlignment(Qt.AlignRight)
            row.addWidget(l)
            row.addStretch(1)
            row.addWidget(r)
            layout.addLayout(row)
        return card

    def translate_actions_card(self):
        card = Card("SmallCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(9)
        heading = QLabel("QUICK ACTIONS")
        heading.setObjectName("CardTitle")
        layout.addWidget(heading)

        copy_button = QPushButton("Copy translation")
        copy_button.setObjectName("SecondaryButton")
        copy_button.setIcon(app_icon("copy", 17))
        copy_button.setIconSize(QSize(17, 17))
        copy_button.setAccessibleName("Copy translated text")
        copy_button.clicked.connect(self.copy_translation_output)
        layout.addWidget(copy_button)

        import_button = QPushButton("Import document")
        import_button.setObjectName("SecondaryButton")
        import_button.setIcon(app_icon("upload", 17))
        import_button.setIconSize(QSize(17, 17))
        import_button.clicked.connect(self.import_translate_document)
        layout.addWidget(import_button)
        return card

    def update_right_panel(self, page_name):
        self.clear_layout(self.right_layout)
        if page_name == "Translate":
            self.right_layout.addWidget(self.translate_actions_card())
            source = self.translate_source.currentText() if hasattr(self, "translate_source") else "Auto"
            target = self.translate_target.currentText() if hasattr(self, "translate_target") else "—"
            self.right_layout.addWidget(self.info_card("TRANSLATION INFO", [("Source", source), ("Target", target), ("Route", getattr(self, "last_translation_route", "—"))]))
        elif page_name == "Reader":
            self.right_layout.addWidget(self.info_card("READER INFO", [("File", self.reader_current_file), ("Language", self.reader_detected_language), ("Voice", self.reader_tts_lang.currentText() if hasattr(self, "reader_tts_lang") else self.reader_voice_label)]))
            speed = self.reader_speed.currentText() if hasattr(self, "reader_speed") else "1.0x"
            self.right_layout.addWidget(self.info_card("PLAYBACK", [("Speed", speed), ("Status", self.reader_playback_status), ("Duration", self.format_ms(self.reader_audio_duration_ms))]))
        elif page_name == "OCR":
            self.right_layout.addWidget(self.info_card("OCR INFO", [("Language", self.ocr_lang.currentText() if hasattr(self, "ocr_lang") else "Auto"), ("Input", "Image/PDF"), ("Status", getattr(self, "ocr_status", "Ready"))]))
        elif page_name == "Speech":
            self.right_layout.addWidget(self.info_card("SPEECH", [("Recorder", "Ready"), ("STT", "Offline"), ("Export", "Available")]))
        elif page_name == "Notes":
            self.right_layout.addWidget(self.info_card("NOTES", [("Storage", "SQLite"), ("Search", "Ctrl+K")]))
        elif page_name == "Tasks":
            self.right_layout.addWidget(self.info_card("TASK ENGINE", [("Planner", "Phase B pending"), ("Execution", "Allowlisted"), ("Storage", "Persistent")]))
        else:
            self.right_layout.addWidget(self.info_card("SYSTEM", [("Backend", "Checking"), ("Mode", "Offline")]))
        self.right_layout.addStretch(1)

    # ---------- Translate ----------
    def _build_translate_page_legacy(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addLayout(self.page_title("Translate", "Translate text offline with language-aware views."))

        controls_host = QWidget()
        self.translate_controls_host = self.register_band_widget(controls_host)
        controls = QGridLayout(controls_host)
        controls.setContentsMargins(0, 0, 0, 0)
        self.translate_controls_grid = controls
        self.translate_source_label = QLabel("Source")
        self.translate_target_label = QLabel("Target")
        self.translate_source = self.language_box("auto", include_auto=True)
        self.translate_target = self.language_box("de")
        self.set_language_grid_layout(controls, self.translate_source_label, self.translate_source, self.translate_target_label, self.translate_target, False)
        layout.addWidget(controls_host)

        self.translate_input = self.make_responsive_text_edit(QTextEdit())
        self.translate_input.setObjectName("SignalTranslateInput")
        self.translate_input.setPlaceholderText("Enter or paste text...")
        self.translate_output = self.make_responsive_text_edit(QTextEdit())
        self.translate_output.setObjectName("SignalTranslateOutput")
        self.translate_output.setReadOnly(True)
        self.translate_output.setPlaceholderText("Translation output will appear here...")

        button_host = QWidget()
        self.translate_action_host = self.register_band_widget(button_host)
        button_row = QGridLayout(button_host)
        button_row.setContentsMargins(0, 0, 0, 0)
        self.translate_action_grid = button_row
        import_doc_btn = self.register_responsive_button(QPushButton("＋ Import Document"), "+ Document", "+ Doc")
        import_doc_btn.setObjectName("SecondaryButton")
        import_doc_btn.clicked.connect(self.import_translate_document)

        btn = self.register_responsive_button(QPushButton("Translate"), "Translate", "Go")
        btn.setObjectName("PrimaryButton")
        btn.clicked.connect(self.translate_text)

        export_txt_btn = self.register_responsive_button(QPushButton("Export TXT"), "TXT", "TXT", group="export")
        export_txt_btn.setObjectName("SecondaryButton")
        export_txt_btn.clicked.connect(lambda: self.export_translation("txt"))

        export_docx_btn = self.register_responsive_button(QPushButton("Export DOCX"), "DOCX", "DOCX", group="export")
        export_docx_btn.setObjectName("SecondaryButton")
        export_docx_btn.clicked.connect(lambda: self.export_translation("docx"))

        export_pdf_btn = self.register_responsive_button(QPushButton("Export PDF"), "PDF", "PDF", group="export")
        export_pdf_btn.setObjectName("SecondaryButton")
        export_pdf_btn.clicked.connect(lambda: self.export_translation("pdf"))

        self.translate_action_buttons = [import_doc_btn, btn, export_txt_btn, export_docx_btn, export_pdf_btn]
        self.set_action_grid_layout(button_row, self.translate_action_buttons, False)

        translate_input_label = QLabel("INPUT")
        translate_input_label.setObjectName("SectionLabel")
        layout.addWidget(translate_input_label)
        layout.addWidget(self.translate_input, 1)
        layout.addWidget(button_host)
        translate_output_label = QLabel("OUTPUT")
        translate_output_label.setObjectName("SectionLabel")
        layout.addWidget(translate_output_label)
        layout.addWidget(self.translate_output, 1)

        translate_player = self.register_compact_card(Card("Card"))
        self.translate_player_card = translate_player
        translate_player.setMinimumHeight(118)
        translate_player_layout = QVBoxLayout(translate_player)
        translate_player_layout.setContentsMargins(18, 14, 18, 14)

        translate_player_top = QHBoxLayout()
        self.translate_time_left = QLabel("00:00")
        self.translate_time_left.setObjectName("BigText")
        self.translate_time_right = QLabel("00:00")
        self.translate_time_right.setObjectName("BigText")
        self.translate_waveform = AudioWaveform()
        self.translate_waveform.seek_requested.connect(self.seek_reader_to_progress)
        translate_player_top.addWidget(self.translate_time_left)
        translate_player_top.addWidget(self.translate_waveform, 1)
        translate_player_top.addWidget(self.translate_time_right)

        translate_controls = QHBoxLayout()
        for label, handler in [
            ("⏪ Rewind", self.rewind_audio),
            ("▶ Read Translation", self.read_translation_aloud),
            ("⏸ Pause / Resume", self.pause_resume_audio),
            ("■ Stop", self.stop_audio),
        ]:
            compact_label = label.replace("Read Translation", "Read").replace("Pause / Resume", "Pause")
            ultra_label = label.split()[0]
            control = self.register_responsive_button(QPushButton(label), compact_label, ultra_label, group="playback")
            control.setObjectName("SecondaryButton" if "Read" not in label else "PrimaryButton")
            control.clicked.connect(handler)
            translate_controls.addWidget(control)

        translate_controls.addStretch(1)
        translate_speed_group = QHBoxLayout()
        translate_speed_group.setSpacing(8)
        translate_speed_label = QLabel("Speed")
        self.translate_speed_label = translate_speed_label
        translate_speed_label.setObjectName("Muted")
        self.translate_speed = WheelSafeComboBox()
        self.translate_speed.setObjectName("SpeedBox")
        for label, value in [("0.75x", 0.75), ("1.0x", 1.0), ("1.25x", 1.25), ("1.5x", 1.5)]:
            self.translate_speed.addItem(label, value)
        self.translate_speed.setCurrentIndex(1)
        self.translate_speed.currentIndexChanged.connect(self.change_playback_speed)
        translate_speed_group.addWidget(translate_speed_label)
        translate_speed_group.addWidget(self.translate_speed)
        translate_controls.addLayout(translate_speed_group)

        translate_player_layout.addLayout(translate_player_top)
        translate_player_layout.addLayout(translate_controls)
        layout.addWidget(translate_player)
        return page

    def build_translate_page(self):
        page = QWidget()
        page.setObjectName("SignalTranslatePage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addLayout(self.page_title("TRANSLATE / SIGNAL DECK", "Local NLLB translation • private processing • export-ready output"))

        workspace = QFrame()
        workspace.setObjectName("TranslateWorkspace")
        self.translate_workspace = workspace
        self.translate_controls_host = workspace
        workspace_grid = QGridLayout(workspace)
        self.translate_workspace_grid = workspace_grid
        self.translate_controls_grid = workspace_grid
        workspace_grid.setContentsMargins(0, 0, 0, 0)
        workspace_grid.setHorizontalSpacing(10)
        workspace_grid.setVerticalSpacing(0)

        self.translate_source = self.language_box("auto", include_auto=True)
        self.translate_source.setAccessibleName("Source language")
        self.translate_target = self.language_box("de")
        self.translate_target.setAccessibleName("Target language")
        self.translate_source_label = QLabel("Source text")
        self.translate_target_label = QLabel("Translation")
        self.translate_source_label.setObjectName("PaneTitle")
        self.translate_target_label.setObjectName("PaneTitle")

        self.translate_input = self.make_responsive_text_edit(QTextEdit())
        self.translate_input.setObjectName("SignalTranslateInput")
        self.translate_input.setAccessibleName("Text to translate")
        self.translate_input.setPlaceholderText("Type, paste, or import text")
        self.translate_output = self.make_responsive_text_edit(QTextEdit())
        self.translate_output.setObjectName("SignalTranslateOutput")
        self.translate_output.setAccessibleName("Translated text")
        self.translate_output.setReadOnly(True)
        self.translate_output.setPlaceholderText("Your translation will appear here")

        source_pane = Card("TranslatePane")
        self.translate_source_pane = source_pane
        source_layout = QVBoxLayout(source_pane)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.setSpacing(0)
        source_header = QWidget()
        source_header.setObjectName("PaneHeader")
        source_header_layout = QHBoxLayout(source_header)
        source_header_layout.setContentsMargins(16, 12, 12, 12)
        source_header_layout.setSpacing(12)
        source_header_layout.addWidget(self.translate_source_label)
        source_header_layout.addStretch(1)
        source_header_layout.addWidget(self.translate_source)
        source_layout.addWidget(source_header)
        source_layout.addWidget(self.translate_input, 1)

        source_footer = QWidget()
        source_footer.setObjectName("PaneFooter")
        source_footer_layout = QHBoxLayout(source_footer)
        source_footer_layout.setContentsMargins(12, 8, 12, 8)
        self.translate_input_count = QLabel("0 characters")
        self.translate_input_count.setObjectName("Counter")
        source_footer_layout.addWidget(self.translate_input_count)
        source_footer_layout.addStretch(1)
        speech_button = QPushButton("Speech")
        speech_button.setObjectName("PaneToolButton")
        speech_button.setIcon(app_icon("microphone", 16))
        speech_button.setIconSize(QSize(16, 16))
        speech_button.setToolTip("Open speech input")
        speech_button.setAccessibleName("Open speech input")
        speech_button.clicked.connect(lambda: self.switch_page("Speech"))
        source_footer_layout.addWidget(speech_button)
        clear_button = QPushButton("Clear")
        clear_button.setObjectName("PaneToolButton")
        clear_button.setIcon(app_icon("trash", 16))
        clear_button.setIconSize(QSize(16, 16))
        clear_button.setAccessibleName("Clear source text")
        clear_button.setToolTip("Clear source text")
        clear_button.clicked.connect(self.clear_translate_input)
        source_footer_layout.addWidget(clear_button)
        source_layout.addWidget(source_footer)

        target_pane = Card("TranslatePane")
        self.translate_target_pane = target_pane
        target_layout = QVBoxLayout(target_pane)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.setSpacing(0)
        target_header = QWidget()
        target_header.setObjectName("PaneHeader")
        target_header_layout = QHBoxLayout(target_header)
        target_header_layout.setContentsMargins(16, 12, 12, 12)
        target_header_layout.setSpacing(12)
        target_header_layout.addWidget(self.translate_target_label)
        target_header_layout.addStretch(1)
        target_header_layout.addWidget(self.translate_target)
        target_layout.addWidget(target_header)
        self.translate_output_stack = QStackedWidget()
        self.translate_output_stack.addWidget(self.translate_output)
        self.translate_skeleton = SkeletonWidget()
        self.translate_output_stack.addWidget(self.translate_skeleton)
        target_layout.addWidget(self.translate_output_stack, 1)

        target_footer = QWidget()
        target_footer.setObjectName("PaneFooter")
        target_footer_layout = QHBoxLayout(target_footer)
        target_footer_layout.setContentsMargins(12, 8, 12, 8)
        self.translate_output_count = QLabel("0 characters")
        self.translate_output_count.setObjectName("Counter")
        target_footer_layout.addWidget(self.translate_output_count)
        target_footer_layout.addStretch(1)
        listen_button = QPushButton("Listen")
        listen_button.setObjectName("PaneToolButton")
        listen_button.setIcon(app_icon("play", 16))
        listen_button.setIconSize(QSize(16, 16))
        listen_button.setToolTip("Listen to translation")
        listen_button.setAccessibleName("Listen to translated text")
        listen_button.clicked.connect(self.read_translation_aloud)
        target_footer_layout.addWidget(listen_button)
        copy_button = QPushButton("Copy")
        copy_button.setObjectName("PaneToolButton")
        copy_button.setIcon(app_icon("copy", 16))
        copy_button.setIconSize(QSize(16, 16))
        copy_button.setAccessibleName("Copy translated text")
        copy_button.setToolTip("Copy translated text")
        copy_button.clicked.connect(self.copy_translation_output)
        target_footer_layout.addWidget(copy_button)
        target_layout.addWidget(target_footer)

        swap_button = QPushButton()
        self.translate_swap_btn = swap_button
        swap_button.setObjectName("SwapButton")
        swap_button.setIcon(app_icon("swap", 19, normal="#0B57D0", active="#0847AD"))
        swap_button.setIconSize(QSize(19, 19))
        swap_button.setFixedSize(42, 42)
        swap_button.setAccessibleName("Swap source and target languages")
        swap_button.setToolTip("Swap languages and text")
        swap_button.clicked.connect(self.swap_translation_languages)

        workspace_grid.addWidget(source_pane, 0, 0)
        workspace_grid.addWidget(swap_button, 0, 1, Qt.AlignCenter)
        workspace_grid.addWidget(target_pane, 0, 2)
        workspace_grid.setColumnStretch(0, 1)
        workspace_grid.setColumnStretch(2, 1)
        workspace_grid.setRowStretch(0, 1)
        layout.addWidget(workspace, 1)

        self.translate_input.textChanged.connect(self.update_translate_counts)
        self.translate_output.textChanged.connect(self.update_translate_counts)
        self.translate_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.translate_shortcut.activated.connect(self.translate_text)

        button_host = QWidget()
        button_host.setObjectName("SignalActionStrip")
        self.translate_action_host = self.register_band_widget(button_host)
        button_row = QGridLayout(button_host)
        button_row.setContentsMargins(0, 0, 0, 0)
        self.translate_action_grid = button_row

        translate_button = QPushButton("Translate")
        translate_button.setObjectName("PrimaryButton")
        translate_button.setIcon(app_icon("translate", 18, normal="#FFFFFF", active="#FFFFFF"))
        translate_button.setIconSize(QSize(18, 18))
        translate_button = self.register_responsive_button(translate_button, "Translate", "Translate")
        translate_button.clicked.connect(self.translate_text)

        import_doc_btn = QPushButton("Import document")
        import_doc_btn.setObjectName("SecondaryButton")
        import_doc_btn.setIcon(app_icon("upload", 18))
        import_doc_btn.setIconSize(QSize(18, 18))
        import_doc_btn = self.register_responsive_button(import_doc_btn, "Import", "Import")
        import_doc_btn.clicked.connect(self.import_translate_document)

        batch_doc_btn = QPushButton("📁 Batch Translate")
        batch_doc_btn.setObjectName("SecondaryButton")
        batch_doc_btn.setIcon(app_icon("folder", 18))
        batch_doc_btn.setIconSize(QSize(18, 18))
        batch_doc_btn = self.register_responsive_button(batch_doc_btn, "Batch", "Batch")
        batch_doc_btn.clicked.connect(self.batch_translate_documents)

        self.translate_export_format = WheelSafeComboBox()
        for label, fmt in [("DOCX (.docx)", "docx"), ("PDF (.pdf)", "pdf"), ("Text (.txt)", "txt")]:
            self.translate_export_format.addItem(label, fmt)
        self.translate_export_format = self.make_responsive_combo(self.translate_export_format)

        export_btn = QPushButton("⤓ Export")
        export_btn.setObjectName("SecondaryButton")
        export_btn.setIcon(app_icon("download", 17))
        export_btn.setIconSize(QSize(17, 17))
        export_btn = self.register_responsive_button(export_btn, "Export", "Export", group="export")
        export_btn.clicked.connect(lambda: self.export_translation(self.translate_export_format.currentData()))

        self.translate_action_buttons = [translate_button, import_doc_btn, batch_doc_btn, self.translate_export_format, export_btn]
        self.set_action_grid_layout(button_row, self.translate_action_buttons, False)
        layout.addWidget(button_host)

        translate_player = self.register_compact_card(Card("Card"))
        translate_player.setObjectName("SignalTranslatePlayer")
        self.translate_player_card = translate_player
        translate_player.setMinimumHeight(118)
        translate_player_layout = QVBoxLayout(translate_player)
        translate_player_layout.setContentsMargins(16, 12, 16, 12)
        translate_player_layout.setSpacing(8)

        translate_player_top = QHBoxLayout()
        self.translate_time_left = QLabel("00:00")
        self.translate_time_left.setObjectName("SignalTimer")
        self.translate_time_right = QLabel("00:00")
        self.translate_time_right.setObjectName("SignalTimer")
        self.translate_waveform = AudioWaveform()
        self.translate_waveform.seek_requested.connect(self.seek_reader_to_progress)
        translate_player_top.addWidget(self.translate_time_left)
        translate_player_top.addWidget(self.translate_waveform, 1)
        translate_player_top.addWidget(self.translate_time_right)

        translate_controls = QHBoxLayout()
        for label, compact_label, handler, primary in (
            ("Rewind", "Rewind", self.rewind_audio, False),
            ("Read translation", "Read", self.read_translation_aloud, True),
            ("Pause / resume", "Pause", self.pause_resume_audio, False),
            ("Stop", "Stop", self.stop_audio, False),
        ):
            control = QPushButton(label)
            control.setObjectName("PrimaryButton" if primary else "SecondaryButton")
            control = self.register_responsive_button(
                control, compact_label, compact_label, group="playback"
            )
            control.clicked.connect(handler)
            translate_controls.addWidget(control)

        translate_controls.addStretch(1)
        translate_speed_group = QHBoxLayout()
        translate_speed_group.setSpacing(8)
        self.translate_speed_label = QLabel("Speed")
        self.translate_speed_label.setObjectName("Muted")
        self.translate_speed = WheelSafeComboBox()
        self.translate_speed.setObjectName("SpeedBox")
        self.translate_speed.setAccessibleName("Playback speed")
        for label, value in (("0.75x", 0.75), ("1.0x", 1.0), ("1.25x", 1.25), ("1.5x", 1.5)):
            self.translate_speed.addItem(label, value)
        self.translate_speed.setCurrentIndex(1)
        self.translate_speed.currentIndexChanged.connect(self.change_playback_speed)
        translate_speed_group.addWidget(self.translate_speed_label)
        translate_speed_group.addWidget(self.translate_speed)
        translate_controls.addLayout(translate_speed_group)

        translate_player_layout.addLayout(translate_player_top)
        translate_player_layout.addLayout(translate_controls)
        layout.addWidget(translate_player)
        return page

    def update_translate_counts(self):
        if hasattr(self, "translate_input_count"):
            self.translate_input_count.setText(
                f"{len(self.translate_input.toPlainText()):,} characters"
            )
        if hasattr(self, "translate_output_count"):
            self.translate_output_count.setText(
                f"{len(self.translate_output.toPlainText()):,} characters"
            )

    def clear_translate_input(self):
        self.translate_input.clear()
        self.translate_input.setFocus()

    def copy_translation_output(self):
        text = self.translate_output.toPlainText()
        if not text.strip():
            self.set_status("There is no translated text to copy.")
            return
        QApplication.clipboard().setText(text)
        self.set_status("Translation copied to the clipboard.")

    def swap_translation_languages(self):
        source_code = self.translate_source.currentData()
        target_code = self.translate_target.currentData()
        next_source = target_code
        next_target = source_code if source_code != "auto" else "en"
        source_index = self.translate_source.findData(next_source)
        target_index = self.translate_target.findData(next_target)
        if source_index >= 0:
            self.translate_source.setCurrentIndex(source_index)
        if target_index >= 0:
            self.translate_target.setCurrentIndex(target_index)

        current_input = self.translate_input.toPlainText()
        current_output = self.translate_output.toPlainText()
        if current_output.strip():
            self.translate_input.setPlainText(current_output)
            self.translate_output.setPlainText(current_input)
        self.update_right_panel("Translate")

    def simplify_route(self, route):
        if not route:
            return "—"
        compact = []
        for item in route:
            if item and (not compact or compact[-1] != item):
                compact.append(item)
        if len(compact) > 2:
            return f"{compact[0]} → {compact[-1]}"
        return " → ".join(compact) or "—"

    def format_translation_output(self, translation):
        # Phase 3: keep normal output clean and export-ready. Auxiliary Hindi
        # romanization/devanagari views are intentionally hidden from the main
        # document workflow so they do not contaminate TXT/DOCX/PDF exports.
        return (translation.get("translated_text", "") or "").strip()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                suffix = Path(url.toLocalFile()).suffix.lower()
                if suffix in DOCUMENT_EXTENSIONS or suffix in AUDIO_EXTENSIONS or suffix in OCR_EXTENSIONS:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasUrls():
            event.ignore()
            return

        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.toLocalFile()]
        if not paths:
            event.ignore()
            return

        if len(paths) == 1:
            first = paths[0]
            suffix = Path(first).suffix.lower()
            if suffix in AUDIO_EXTENSIONS:
                self.import_speech_audio_path(first)
            elif suffix in IMAGE_EXTENSIONS or (self.current_page_name == "OCR" and suffix == ".pdf"):
                self.ocr_extract_path(first)
            elif self.current_page_name == "Reader":
                self.import_reader_document_path(first)
            else:
                self.import_translate_document_path(first)
        else:
            if all(Path(p).suffix.lower() in (IMAGE_EXTENSIONS | {".pdf"}) for p in paths) or self.current_page_name == "OCR":
                self.batch_ocr_documents(paths)
            else:
                self.batch_translate_documents(paths)

        event.acceptProposedAction()

    def import_translate_document(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open document for translation",
            "",
            "Documents (*.txt *.md *.pdf *.docx *.rtf *.html *.htm *.csv *.json *.xml)",
        )
        if path:
            self.import_translate_document_path(path)

    def import_translate_document_path(self, path: str):
        self.switch_page("Translate")
        self.translate_output.setText("")
        self.translate_input.setText("Importing document...")
        self.translate_document_name = Path(path).name
        self.translate_document_source_path = str(Path(path).resolve())
        self.set_status(f"Importing {self.translate_document_name}")

        def task():
            with open(path, "rb") as file:
                response = requests.post(
                    f"{SERVER_URL}/reader/import",
                    files={"file": file},
                    data={"lang": self.translate_source.currentData()},
                    timeout=240,
                )
            return response.json()

        def success(data):
            if not data.get("ok"):
                self.translate_input.setText(str(data))
                self.set_status("Document import failed", error=True)
                return

            detected = data.get("detected_language", {}) or {}
            detected_lang = detected.get("language")
            # Keep Source on Auto for mixed-language imports. Otherwise the UI can
            # accidentally force the whole file through one stale route.
            if detected_lang and not detected.get("is_mixed"):
                idx = self.translate_source.findData(detected_lang)
                if idx >= 0:
                    self.translate_source.setCurrentIndex(idx)

            self.translate_input.setText(data.get("text", ""))
            self.add_recent("Translate", self.translate_document_name, "📄")
            self.set_status(f"Document ready: {self.translate_document_name}")
            self.update_right_panel("Translate")

        self.run_background(task, success)

    def can_use_format_preserving_export(self, file_type: str) -> bool:
        if file_type not in {"txt", "docx", "pdf"}:
            return False
        if not self.translate_document_source_path:
            return False
        return Path(self.translate_document_source_path).suffix.lower() in {".txt", ".md", ".csv", ".docx", ".pdf"}

    def export_format_preserving_translation(self, file_type: str, save_path: str):
        if not self.translate_document_source_path:
            raise RuntimeError("No imported source document available for format-preserving export.")

        with open(self.translate_document_source_path, "rb") as source_file:
            response = requests.post(
                f"{SERVER_URL}/translate/document/export",
                files={"file": source_file},
                data={
                    "source_lang": self.translate_source.currentData(),
                    "target_lang": self.translate_target.currentData(),
                    "output_format": file_type,
                },
                timeout=600,
            )

        if response.status_code != 200:
            raise RuntimeError(response.text)

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            payload = response.json()
            if not payload.get("ok", False):
                raise RuntimeError(payload.get("error") or str(payload))

        Path(save_path).write_bytes(response.content)

    def export_translation(self, file_type: str):
        text = (self.last_translation_plain_text or self.translate_output.toPlainText()).strip()
        if not text or text == "Translating...":
            self.set_status("No translation to export", error=True)
            return

        filters = {
            "txt": "Text File (*.txt)",
            "md": "Markdown File (*.md)",
            "docx": "Word Document (*.docx)",
            "pdf": "PDF File (*.pdf)",
        }
        default_name = "translated_text." + file_type
        if self.translate_document_name:
            default_name = Path(self.translate_document_name).stem + "_translated." + file_type

        path, _ = QFileDialog.getSaveFileName(self, "Export translation", default_name, filters.get(file_type, "Text File (*.txt)"))
        if not path:
            return

        try:
            if self.can_use_format_preserving_export(file_type):
                self.set_status(f"Exporting {file_type.upper()} with source formatting")
                self.export_format_preserving_translation(file_type, path)
            elif file_type in ("txt", "md"):
                Path(path).write_text(text, encoding="utf-8")
            elif file_type == "docx":
                from docx import Document
                document = Document()
                document.add_heading("LinguaFusion Translation", level=1)
                for paragraph in text.split("\n"):
                    document.add_paragraph(paragraph)
                document.save(path)
            elif file_type == "pdf":
                from backend.services.complex_script_pdf_service import write_unicode_pdf
                write_unicode_pdf(text, "LinguaFusion Translation", path)
            self.set_status(f"Exported {file_type.upper()}: {Path(path).name}")
        except Exception as exc:
            self.set_status(f"Export failed: {exc}", error=True)

    def translate_text(self):
        self.translate_output_stack.setCurrentIndex(1)
        self.translate_skeleton.start()
        self.set_status("Translating")

        def task():
            try:
                response = requests.post(
                    f"{SERVER_URL}/reader/translate",
                    data={
                        "text": self.translate_input.toPlainText(),
                        "source_lang": self.translate_source.currentData(),
                        "target_lang": self.translate_target.currentData(),
                    },
                    timeout=600,
                )
                return response.json()
            except Exception as e:
                return {"ok": False, "error": f"Request failed: {str(e)}"}

        def success(data):
            self.translate_skeleton.stop()
            self.translate_output_stack.setCurrentIndex(0)
            if not data.get("ok"):
                message = data.get("error") or data.get("stage") or "Translation failed."
                self.translate_output.setText(f"Translation failed: {message}")
                self.set_status("Translation failed", error=True)
                return
            translation = data.get("translation", {})
            if not translation.get("ok", False):
                partial = (translation.get("translated_text") or "").strip()
                message = translation.get("error") or "Translation quality check failed."
                self.translate_output.setText((partial + "\n\n" if partial else "") + f"Translation failed: {message}")
                self.set_status("Translation failed", error=True)
                return
            self.last_translation_route = self.simplify_route(translation.get("route", []))
            formatted = self.format_translation_output(translation)
            self.last_translation_plain_text = formatted
            self.last_translation_tts_text = translation.get("translated_text", "")
            self.last_translation_input_snapshot = self.translate_input.toPlainText()
            self.last_translation_source_snapshot = self.translate_source.currentData()
            self.last_translation_target_snapshot = self.translate_target.currentData()
            self.translate_output.setText(formatted)
            label = self.translate_document_name or f"{data.get('source_lang', self.translate_source.currentData())} → {data.get('target_lang', self.translate_target.currentData())}"
            self.add_recent("Translate", label)
            self.set_status("Translation complete")
            self.update_right_panel("Translate")

        self.run_background(task, success)

    # ---------- Reader ----------
    def build_reader_page(self):
        page = QWidget()
        page.setObjectName("SignalReaderPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(self.page_title("AUDIO READER / DOCUMENT STREAM", "Local Piper playback • sentence tracking • private document processing"))

        controls_host = QWidget()
        controls_host.setObjectName("SignalFunctionStrip")
        self.reader_controls_host = self.register_band_widget(controls_host)
        controls = QGridLayout(controls_host)
        controls.setContentsMargins(0, 0, 0, 0)
        self.reader_controls_grid = controls
        self.reader_ocr_label = QLabel("OCR language")
        self.reader_tts_label = QLabel("TTS language")
        self.reader_lang = self.language_box("auto", include_auto=True)
        self.reader_tts_lang = self.language_box("auto", include_auto=True)
        self.set_language_grid_layout(controls, self.reader_ocr_label, self.reader_lang, self.reader_tts_label, self.reader_tts_lang, False)
        layout.addWidget(controls_host)

        import_btn = self.register_responsive_button(QPushButton("Import Document"), "Import", "+ Doc")
        import_btn.setObjectName("SignalRecordButton")
        import_btn.clicked.connect(self.import_document)
        self.register_band_widget(import_btn)
        layout.addWidget(import_btn)

        self.reader_info = QLabel("No document loaded.")
        self.reader_info.setObjectName("SignalStatus")
        self.reader_stats = QLabel("Statistics: no document loaded.")
        self.reader_stats.setObjectName("SignalMetaLine")

        tools_host = QWidget()
        tools_host.setObjectName("SignalActionStrip")
        self.reader_tools_host = self.register_band_widget(tools_host)
        tools_row = QHBoxLayout(tools_host)
        tools_row.setContentsMargins(0, 0, 0, 0)
        seek_cursor_btn = self.register_responsive_button(QPushButton("▶ From Cursor"), "▶ Cursor", "Cursor")
        seek_cursor_btn.setObjectName("SecondaryButton")
        seek_cursor_btn.clicked.connect(self.seek_reader_to_cursor)
        tools_row.addWidget(seek_cursor_btn)
        tools_row.addStretch(1)

        self.reader_export_format = WheelSafeComboBox()
        for label, fmt in [("DOCX (.docx)", "docx"), ("PDF (.pdf)", "pdf"), ("Text (.txt)", "txt")]:
            self.reader_export_format.addItem(label, fmt)
        self.reader_export_format = self.make_responsive_combo(self.reader_export_format)

        export_reader_btn = QPushButton("⤓ Export")
        export_reader_btn.setObjectName("SecondaryButton")
        export_reader_btn.clicked.connect(lambda: self.export_reader_text(self.reader_export_format.currentData()))
        tools_row.addWidget(self.reader_export_format)
        tools_row.addWidget(export_reader_btn)

        self.reader_text = self.make_responsive_text_edit(QTextEdit())
        self.reader_text.setObjectName("SignalReaderText")
        self.reader_text.cursorPositionChanged.connect(self.update_reader_cursor_status)
        layout.addWidget(self.reader_info)
        layout.addWidget(self.reader_stats)
        layout.addWidget(tools_host)
        layout.addWidget(self.reader_text, 1)

        player = self.register_compact_card(Card("Card"))
        player.setObjectName("SignalReaderPlayer")
        self.reader_player_card = player
        player.setMinimumHeight(118)
        player_layout = QVBoxLayout(player)
        player_layout.setContentsMargins(18, 14, 18, 14)

        player_top = QHBoxLayout()
        self.reader_time_left = QLabel("00:00")
        self.reader_time_left.setObjectName("SignalTimer")
        self.reader_time_right = QLabel("00:00")
        self.reader_time_right.setObjectName("SignalTimer")
        self.reader_waveform = AudioWaveform()
        self.reader_waveform.seek_requested.connect(self.seek_reader_to_progress)
        player_top.addWidget(self.reader_time_left)
        player_top.addWidget(self.reader_waveform, 1)
        player_top.addWidget(self.reader_time_right)

        controls_row = QHBoxLayout()
        self.reader_speed = WheelSafeComboBox()
        self.reader_speed.setObjectName("SpeedBox")
        for label, value in [("0.75x", 0.75), ("1.0x", 1.0), ("1.25x", 1.25), ("1.5x", 1.5)]:
            self.reader_speed.addItem(label, value)
        self.reader_speed.setCurrentIndex(1)
        self.reader_speed.currentIndexChanged.connect(self.change_playback_speed)

        for label, handler in [("⏪ Rewind", self.rewind_audio), ("▶ Read", self.reader_speak), ("⏸ Pause / Resume", self.pause_resume_audio), ("■ Stop", self.stop_audio), ("⇄ Translate", self.send_reader_to_translate)]:
            compact_label = label.replace("Pause / Resume", "Pause").replace("Translate", "Trans")
            ultra_label = label.split()[0]
            b = self.register_responsive_button(QPushButton(label), compact_label, ultra_label, group="playback")
            b.setObjectName("SecondaryButton" if "Read" not in label else "PrimaryButton")
            b.clicked.connect(handler)
            controls_row.addWidget(b)

        controls_row.addStretch(1)
        speed_group = QHBoxLayout()
        speed_group.setSpacing(8)
        speed_label = QLabel("Speed")
        self.reader_speed_label = speed_label
        speed_label.setObjectName("Muted")
        speed_group.addWidget(speed_label)
        speed_group.addWidget(self.reader_speed)
        controls_row.addLayout(speed_group)

        player_layout.addLayout(player_top)
        player_layout.addLayout(controls_row)
        layout.addWidget(player)
        return page

    def import_document(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open document",
            "",
            "Documents (*.txt *.md *.pdf *.docx *.rtf *.html *.htm *.csv *.json *.xml)",
        )
        if path:
            self.import_reader_document_path(path)

    def batch_translate_documents(self, paths=None):
        if not paths:
            paths, _ = QFileDialog.getOpenFileNames(
                self,
                "Select documents to batch translate",
                "",
                "Documents (*.txt *.md *.docx *.pdf);;All Files (*.*)",
            )
        if not paths:
            return
        target_dir = QFileDialog.getExistingDirectory(self, "Select output folder for translated documents")
        if not target_dir:
            return
        target_lang, ok_lang = QInputDialog.getItem(
            self, "Target Language", "Select target language for batch translation:",
            [f"{label} ({code})" for label, code in LANGUAGES], 1, False
        )
        if not ok_lang or not target_lang:
            return
        target_code = target_lang.split("(")[-1].strip(")")

        export_fmt, ok_fmt = QInputDialog.getItem(
            self, "Export Format", "Select output format for translated documents:",
            ["Same as source", "DOCX (.docx)", "PDF (.pdf)", "Text (.txt)", "Markdown (.md)"], 0, False
        )
        if not ok_fmt or not export_fmt:
            return
        fmt_code = "same" if "Same" in export_fmt else ("docx" if "DOCX" in export_fmt else ("pdf" if "PDF" in export_fmt else ("md" if "Markdown" in export_fmt else "txt")))

        def task():
            files_payload = []
            opened_files = []
            try:
                for p in paths:
                    f = open(p, "rb")
                    opened_files.append(f)
                    files_payload.append(("files", (Path(p).name, f)))

                response = requests.post(
                    f"{SERVER_URL}/document/batch_translate",
                    files=files_payload,
                    data={
                        "source_lang": self.translate_source.currentData() if hasattr(self, "translate_source") else "auto",
                        "target_lang": target_code,
                        "export_format": fmt_code,
                    },
                    timeout=600,
                )
                return response
            finally:
                for f in opened_files:
                    try:
                        f.close()
                    except Exception:
                        pass

        def success(response):
            if response.status_code != 200:
                self.set_status(f"Batch translation failed: {response.text}", error=True)
                return
            import zipfile, io
            zip_file = zipfile.ZipFile(io.BytesIO(response.content))
            zip_file.extractall(target_dir)
            self.set_status(f"Batch translation complete! Saved {len(zip_file.namelist())} files to {Path(target_dir).name}")

        self.set_status(f"Batch translating {len(paths)} documents...")
        self.run_background(task, success)

    def batch_ocr_documents(self, paths=None):
        if not paths:
            paths, _ = QFileDialog.getOpenFileNames(
                self,
                "Select images or PDFs to batch OCR",
                "",
                "Images / PDFs (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.pdf);;All Files (*.*)",
            )
        if not paths:
            return
        target_dir = QFileDialog.getExistingDirectory(self, "Select output folder for OCR files")
        if not target_dir:
            return
        target_lang, ok_lang = QInputDialog.getItem(
            self, "Translate OCR Text?", "Select translation target (or None to keep original text):",
            ["None (Keep Extracted Text Only)", *[f"{label} ({code})" for label, code in LANGUAGES]], 0, False
        )
        if not ok_lang or not target_lang:
            return
        target_code = "none" if "None" in target_lang else target_lang.split("(")[-1].strip(")")

        export_fmt, ok_fmt = QInputDialog.getItem(
            self, "Export Format", "Select output format for OCR files:",
            ["DOCX (.docx)", "PDF (.pdf)", "Text (.txt)", "Markdown (.md)"], 0, False
        )
        if not ok_fmt or not export_fmt:
            return
        fmt_code = "docx" if "DOCX" in export_fmt else ("pdf" if "PDF" in export_fmt else ("md" if "Markdown" in export_fmt else "txt"))

        def task():
            files_payload = []
            opened_files = []
            try:
                for p in paths:
                    f = open(p, "rb")
                    opened_files.append(f)
                    files_payload.append(("files", (Path(p).name, f)))

                response = requests.post(
                    f"{SERVER_URL}/ocr/batch_extract",
                    files=files_payload,
                    data={
                        "ocr_lang": self.ocr_lang.currentData() if hasattr(self, "ocr_lang") else "auto",
                        "target_lang": target_code,
                        "export_format": fmt_code,
                    },
                    timeout=600,
                )
                return response
            finally:
                for f in opened_files:
                    try:
                        f.close()
                    except Exception:
                        pass

        def success(response):
            if response.status_code != 200:
                self.set_status(f"Batch OCR failed: {response.text}", error=True)
                return
            import zipfile, io
            zip_file = zipfile.ZipFile(io.BytesIO(response.content))
            zip_file.extractall(target_dir)
            self.set_status(f"Batch OCR complete! Saved {len(zip_file.namelist())} files to {Path(target_dir).name}")

        self.set_status(f"Processing batch OCR for {len(paths)} files...")
        self.run_background(task, success)

    def do_speech_export(self):
        fmt = self.speech_export_format.currentData() if hasattr(self, "speech_export_format") else "srt"
        if fmt in ("srt", "vtt"):
            self.export_speech_subtitles(fmt)
        else:
            self.export_speech_text(fmt)

    def import_reader_document_path(self, path: str):
        self.switch_page("Reader")
        self.reader_info.setText("Importing document...")
        self.reader_text.setText("Importing document...")
        self.set_status("Importing document")

        def task():
            with open(path, "rb") as f:
                response = requests.post(
                    f"{SERVER_URL}/reader/import",
                    files={"file": f},
                    data={"lang": self.reader_lang.currentData()},
                    timeout=240,
                )
            return response.json()

        def success(data):
            if not data.get("ok"):
                self.reader_info.setText("Import failed.")
                self.reader_text.setText(str(data))
                self.set_status("Import failed", error=True)
                return

            detected = data.get("detected_language", {})
            detected_lang = detected.get("language")
            confidence = detected.get("confidence", 0)
            self.reader_current_file = Path(path).name
            self.reader_detected_language = detected_lang or "Auto"
            self.reader_info.setText(
                f"File: {data.get('file_type')} | "
                f"Method: {data.get('method')} | "
                f"Detected: {detected_lang} ({round(confidence, 2)})"
            )
            # Keep TTS language on Auto by default. Auto now routes English,
            # German, Spanish and Hindi segments to the right Piper voice.
            self.reader_text.setPlainText(data["text"])
            self.reader_analysis = data.get("analysis", {}) or {}
            self.reader_sentence_ranges = self.reader_analysis.get("sentence_ranges", []) or []
            self.reader_current_sentence_index = -1
            self.reader_playback_sentence_offset = 0
            self.reader_playback_sentence_count = len(self.reader_sentence_ranges or [])
            self.reader_bookmarks = []
            self.reader_cursor_audio_cache = {}
            self.reader_full_audio_cache_key = None
            self.reader_full_audio_path = None
            self.update_reader_stats_label()
            self.clear_reader_highlight()
            self.add_recent("Reader", self.reader_current_file)
            self.set_status(f"{detected_lang or 'Language'} detected")
            self.update_right_panel("Reader")

        self.run_background(task, success)


    def update_reader_stats_label(self):
        if not hasattr(self, "reader_stats"):
            return
        analysis = self.reader_analysis or {}
        if not analysis:
            self.reader_stats.setText("Statistics: no document loaded.")
            return
        terms = analysis.get("technical_terms") or []
        term_preview = ", ".join(terms[:5]) if terms else "none"
        spoken_label = analysis.get("estimated_speaking_label")
        if not spoken_label:
            seconds = int(round(float(analysis.get("estimated_speaking_minutes", 0) or 0) * 60))
            spoken_label = self.format_duration_words(seconds)
        self.reader_stats.setText(
            f"Statistics: {analysis.get('words', 0)} words · "
            f"{analysis.get('sentences', 0)} sentences · "
            f"{analysis.get('paragraphs', 0)} paragraphs · "
            f"{spoken_label} spoken · Terms: {term_preview}"
        )

    def update_reader_cursor_status(self):
        if self.current_page_name != "Reader" or not hasattr(self, "reader_text"):
            return
        pos = self.reader_text.textCursor().position()
        sentence = self.find_reader_sentence_for_position(pos)
        if sentence and self.reader_playback_status != "Playing":
            self.set_status(f"Cursor at sentence {sentence.get('index', 0) + 1}")

    def find_reader_sentence_for_position(self, position: int):
        ranges = self.reader_sentence_ranges or []
        if not ranges:
            return None
        position = max(0, int(position or 0))
        for sentence in ranges:
            if int(sentence.get("start", 0)) <= position <= int(sentence.get("end", 0)):
                return sentence
        # If the cursor is in whitespace between sentences, choose the next
        # sentence; otherwise choose the closest previous sentence.
        for sentence in ranges:
            if position < int(sentence.get("start", 0)):
                return sentence
        return ranges[-1]

    def clear_reader_highlight(self):
        if hasattr(self, "reader_text"):
            self.reader_text.setExtraSelections([])
        self.reader_current_sentence_index = -1

    def highlight_reader_sentence(self, sentence_index: int):
        if not hasattr(self, "reader_text") or sentence_index < 0:
            return
        if sentence_index == self.reader_current_sentence_index:
            return
        if sentence_index >= len(self.reader_sentence_ranges):
            return
        sentence = self.reader_sentence_ranges[sentence_index]
        cursor = QTextCursor(self.reader_text.document())
        cursor.setPosition(int(sentence.get("start", 0)))
        cursor.setPosition(int(sentence.get("end", 0)), QTextCursor.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(59, 130, 246, 70))
        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format = fmt
        self.reader_text.setExtraSelections([selection])
        self.reader_current_sentence_index = sentence_index

    def reader_sentence_weight(self, item) -> int:
        text = item.get("text", "") or ""
        words = int(item.get("words", 0) or 0)
        if words <= 0:
            words = max(1, len(re.findall(r"[\w\u0900-\u097F]+", text)))
        # Short headings/table labels are spoken quickly. Long mixed-language
        # sentences need their natural word weight.
        if len(text.strip()) <= 40 and words <= 5:
            words = max(1, int(words * 0.65))
        return max(1, words)

    def reader_sentence_timeline(self, duration_ms: int | None = None):
        ranges = self.reader_sentence_ranges or []
        duration = int(duration_ms if duration_ms is not None else (self.reader_audio_duration_ms or 0))
        if not ranges or duration <= 0:
            return []
        weights = [self.reader_sentence_weight(item) for item in ranges]
        total = max(1, sum(weights))
        timeline = []
        running = 0
        for idx, weight in enumerate(weights):
            start = int((running / total) * duration)
            running += weight
            end = int((running / total) * duration)
            timeline.append((idx, max(0, start), max(start + 1, min(duration, end))))
        return timeline

    def update_reader_sentence_highlight(self, progress: float):
        if not self.reader_highlight_enabled or not self.reader_sentence_ranges:
            return
        duration = max(self.reader_audio_duration_ms or 1, 1)
        original_elapsed = max(0, min(duration, int(max(0.0, min(1.0, progress)) * duration)))
        timeline = self.reader_sentence_timeline(duration)
        if not timeline:
            return

        offset = max(0, int(getattr(self, "reader_playback_sentence_offset", 0) or 0))
        # When From Cursor starts with a small safety lead-in, keep the selected
        # sentence highlighted while playback is entering that sentence. This
        # avoids the UI jumping to the previous/next sentence after a cursor seek.
        if offset > 0 and offset < len(timeline):
            selected_start = timeline[offset][1]
            if original_elapsed <= selected_start + 900:
                self.highlight_reader_sentence(offset)
                return

        # Time-based highlight is more robust after pause/resume and seek than
        # local progress over the remaining text. Use a small lookahead because
        # pygame position updates lag slightly behind audible playback.
        adjusted = original_elapsed + 350
        index = timeline[-1][0]
        for idx, start, end in timeline:
            if start <= adjusted < end:
                index = idx
                break
        self.highlight_reader_sentence(index)

    def reader_full_tts_cache_key(self, text: str) -> str:
        basis = "|".join([
            self.reader_tts_lang.currentData() or "auto",
            str(self.reader_speed.currentData() or 1.0),
            hashlib.sha1((text or "").encode("utf-8", errors="ignore")).hexdigest(),
        ])
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()

    def estimate_sentence_start_ms(self, sentence_index: int, duration_ms: int | None = None, cursor_safe: bool = False) -> int:
        ranges = self.reader_sentence_ranges or []
        if not ranges:
            return 0
        sentence_index = max(0, min(int(sentence_index or 0), len(ranges) - 1))
        duration = int(duration_ms if duration_ms is not None else (self.reader_audio_duration_ms or 0))
        timeline = self.reader_sentence_timeline(duration)
        if not timeline:
            return 0
        start = timeline[sentence_index][1]
        if cursor_safe and sentence_index > 0:
            end = timeline[sentence_index][2]
            sentence_span = max(1, end - start)
            # Piper does not provide timestamps. Use a generous lead-in so
            # From Cursor never starts at the end of the selected sentence or
            # in the next sentence. This prefers a small repeat over skipping.
            guard = min(5000, max(1500, int(sentence_span * 0.60)))
            start = max(0, start - guard)
        return max(0, min(max(duration - 1, 0), int(start)))

    def load_audio_base_without_playing(self, audio_path: str):
        self.reader_base_audio_path = str(Path(audio_path).resolve())
        self.reader_current_audio_path = self.reader_base_audio_path
        self.reader_seek_base_original_ms = 0
        self.reader_audio_duration_ms = len(AudioSegment.from_file(self.reader_base_audio_path))
        self.reader_active_duration_ms = self.effective_duration_ms()
        self.reader_time_left.setText("00:00")
        self.reader_time_right.setText(self.format_ms(self.reader_audio_duration_ms))
        self.reader_waveform.load_audio(self.reader_base_audio_path)
        self.reader_waveform.set_progress(0)
        if hasattr(self, "translate_time_left"):
            self.translate_time_left.setText("00:00")
            self.translate_time_right.setText(self.format_ms(self.reader_audio_duration_ms))
            self.translate_waveform.load_audio(self.reader_base_audio_path)
            self.translate_waveform.set_progress(0)

    def seek_reader_to_cursor(self):
        if not hasattr(self, "reader_text"):
            return
        full_text = self.reader_text.toPlainText()
        if not full_text.strip():
            self.set_status("No document loaded", error=True)
            return
        clean_full_text = self.clean_reader_text_for_tts(full_text)
        if not clean_full_text:
            self.set_status("No readable text", error=True)
            return

        pos = self.reader_text.textCursor().position()
        sentence = self.find_reader_sentence_for_position(pos)
        sentence_index = int(sentence.get("index", 0)) if sentence else 0
        if sentence:
            self.highlight_reader_sentence(sentence_index)

        full_cache_key = self.reader_full_tts_cache_key(clean_full_text)
        cached_full = (
            self.reader_full_audio_cache_key == full_cache_key
            and self.reader_full_audio_path
            and Path(self.reader_full_audio_path).exists()
        )

        self.reader_playback_sentence_offset = sentence_index
        self.reader_playback_sentence_count = max(1, len(self.reader_sentence_ranges or []) - sentence_index)

        if cached_full:
            if str(Path(self.reader_base_audio_path or "").resolve()) != str(Path(self.reader_full_audio_path).resolve()):
                self.load_audio_base_without_playing(self.reader_full_audio_path)
            start_ms = self.estimate_sentence_start_ms(sentence_index, cursor_safe=True)
            self.set_status(f"Playing from cursor at {self.format_ms(start_ms)}")
            self.play_current_audio_from(start_ms)
            return

        # First From Cursor use generates the full document audio once, then
        # seeks into that full cached waveform. This avoids creating separate
        # cursor-only audio and makes later cursor/seek behavior stable.
        self.reader_speak_text(
            clean_full_text,
            sentence_offset=sentence_index,
            full_cache_key=full_cache_key,
            play_from_sentence_index=sentence_index,
        )

    def add_reader_bookmark(self):
        if not hasattr(self, "reader_text"):
            return
        pos = self.reader_text.textCursor().position()
        text = self.reader_text.toPlainText()
        if not text.strip():
            self.set_status("No document loaded", error=True)
            return
        sentence = self.find_reader_sentence_for_position(pos)
        snippet = (sentence.get("text") if sentence else text[max(0, pos-40):pos+80]).strip()
        snippet = re.sub(r"\s+", " ", snippet)[:70]
        self.reader_bookmark_counter += 1
        label = f"B{self.reader_bookmark_counter}: {snippet or 'Position ' + str(pos)}"
        item = {"label": label, "position": pos, "snippet": snippet}
        self.reader_bookmarks.append(item)
        if hasattr(self, "reader_bookmark_box"):
            self.reader_bookmark_box.addItem(label, item)
            self.reader_bookmark_box.setCurrentIndex(self.reader_bookmark_box.count() - 1)
        self.set_status("Bookmark added")

    def go_reader_bookmark(self):
        if not hasattr(self, "reader_bookmark_box") or not hasattr(self, "reader_text"):
            return
        item = self.reader_bookmark_box.currentData()
        if not item:
            self.set_status("No bookmark selected", error=True)
            return
        pos = int(item.get("position", 0))
        cursor = self.reader_text.textCursor()
        cursor.setPosition(max(0, min(pos, len(self.reader_text.toPlainText()))))
        self.reader_text.setTextCursor(cursor)
        sentence = self.find_reader_sentence_for_position(pos)
        if sentence:
            self.highlight_reader_sentence(int(sentence.get("index", 0)))
        self.set_status(f"Bookmark opened: {item.get('label', '')[:40]}. Press From Cursor to read from here.")

    def export_reader_text(self, file_type: str):
        text = self.reader_text.toPlainText().strip() if hasattr(self, "reader_text") else ""
        if not text:
            self.set_status("No reader text to export", error=True)
            return
        filters = {"txt": "Text File (*.txt)", "docx": "Word Document (*.docx)", "pdf": "PDF File (*.pdf)"}
        default_name = Path(self.reader_current_file).stem if self.reader_current_file and self.reader_current_file != "None" else "reader_export"
        path, _ = QFileDialog.getSaveFileName(self, "Export reader document", f"{default_name}.{file_type}", filters[file_type])
        if not path:
            return
        self.set_status(f"Exporting reader {file_type.upper()}")

        def task():
            response = requests.post(
                f"{SERVER_URL}/reader/export",
                data={"text": text, "output_format": file_type, "title": default_name},
                timeout=240,
            )
            if response.status_code != 200:
                raise RuntimeError(response.text)
            if "application/json" in response.headers.get("content-type", ""):
                payload = response.json()
                if not payload.get("ok", False):
                    raise RuntimeError(payload.get("error") or str(payload))
            Path(path).write_bytes(response.content)
            return path

        def success(saved_path):
            self.set_status(f"Exported reader {file_type.upper()}: {Path(saved_path).name}")

        self.run_background(task, success)

    def clean_reader_text_for_tts(self, text):
        # Preserve line boundaries for Auto TTS. The backend Reader TTS planner
        # uses lines/headings as language-handover boundaries. Flattening the
        # document into one paragraph causes language bleed-through.
        lines = []
        for line in text.splitlines():
            cleaned = line.strip()
            if not cleaned or cleaned.startswith("--- Page") or cleaned.startswith("--- OCR Page"):
                continue
            lines.append(re.sub(r"\s+", " ", cleaned))
        return "\n".join(lines).strip()

    def reader_speak_text(self, text: str, sentence_offset: int = 0, cache_key: str | None = None, full_cache_key: str | None = None, play_from_sentence_index: int | None = None):
        text = self.clean_reader_text_for_tts(text)
        if not text:
            self.set_status("No text to read", error=True)
            return
        self.active_audio_context = "Reader"
        self.reader_playback_sentence_offset = max(0, int(sentence_offset or 0))
        self.reader_playback_sentence_count = max(1, len(self.reader_sentence_ranges or []) - self.reader_playback_sentence_offset)
        self.set_status("Generating reader audio")

        def task():
            response = requests.post(
                f"{SERVER_URL}/reader/speak",
                data={"text": text[:7000], "lang": self.reader_tts_lang.currentData(), "speed": "1.0"},
                timeout=360,
            )
            if response.status_code != 200:
                raise RuntimeError(response.text)
            out_path = Path(f"reader_output_{uuid4().hex}.wav").resolve()
            with open(out_path, "wb") as f:
                f.write(response.content)
            return str(out_path)

        def success(path):
            self.generated_audio_files.append(path)
            if cache_key:
                self.reader_cursor_audio_cache[cache_key] = path
            if full_cache_key:
                self.reader_full_audio_cache_key = full_cache_key
                self.reader_full_audio_path = path
            if play_from_sentence_index is not None:
                self.load_audio_base_without_playing(path)
                start_ms = self.estimate_sentence_start_ms(int(play_from_sentence_index), self.reader_audio_duration_ms, cursor_safe=True)
                self.reader_playback_sentence_offset = max(0, int(play_from_sentence_index))
                self.reader_playback_sentence_count = max(1, len(self.reader_sentence_ranges or []) - self.reader_playback_sentence_offset)
                self.play_current_audio_from(start_ms)
            else:
                self.play_audio_file(path)
            self.reader_playback_status = "Playing"
            self.set_status("Playing")
            self.update_right_panel("Reader")

        self.run_background(task, success)

    def reader_speak(self):
        self.reader_playback_sentence_offset = 0
        self.reader_playback_sentence_count = len(self.reader_sentence_ranges or [])
        text = self.reader_text.toPlainText() if hasattr(self, "reader_text") else ""
        clean_text = self.clean_reader_text_for_tts(text)
        full_cache_key = self.reader_full_tts_cache_key(clean_text) if clean_text else None
        self.reader_speak_text(text, sentence_offset=0, full_cache_key=full_cache_key)

    def format_ms(self, ms):
        if not ms or ms < 0:
            return "00:00"
        total_seconds = int(ms / 1000)
        return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"

    def format_duration_words(self, seconds):
        try:
            total = max(0, int(round(float(seconds))))
        except Exception:
            total = 0
        minutes, secs = divmod(total, 60)
        if minutes and secs:
            return f"{minutes} min {secs} sec"
        if minutes:
            return f"{minutes} min"
        return f"{secs} sec"

    def playback_rate(self) -> float:
        if getattr(self, "active_audio_context", "Reader") == "Translate" and hasattr(self, "translate_speed"):
            return float(self.translate_speed.currentData() or 1.0)
        if hasattr(self, "reader_speed"):
            return float(self.reader_speed.currentData() or 1.0)
        return 1.0

    def original_position_ms(self) -> int:
        """Return approximate position in the original, unmodified audio timeline."""
        if not self.reader_current_audio_path:
            return 0

        if not self.ensure_audio_backend():
            return self.reader_seek_base_original_ms

        if self.audio_paused:
            active_pos = self.reader_paused_pos_ms
        else:
            active_pos = max(pygame.mixer.music.get_pos(), 0)

        original_elapsed = self.reader_seek_base_original_ms + int(active_pos * max(self.reader_last_rate, 0.01))
        return max(0, min(original_elapsed, self.reader_audio_duration_ms or original_elapsed))

    def effective_duration_ms(self) -> int:
        if not self.reader_audio_duration_ms:
            return 0
        return int(self.reader_audio_duration_ms / max(self.playback_rate(), 0.01))

    def make_playback_segment_audio(self, source_path: str, speed: float, start_original_ms: int = 0) -> str:
        """
        Build the exact audio chunk pygame should play.

        pygame cannot reliably seek inside generated WAV files with play(start=...).
        So for seeking/dragging we create a temporary WAV segment starting at the
        requested original-audio position, then optionally apply ffmpeg atempo for
        speed control. This makes click/drag seek stable instead of jumping back to 0.
        """
        source = Path(source_path)
        speed = max(0.5, min(float(speed or 1.0), 2.0))
        start_original_ms = max(0, min(int(start_original_ms or 0), self.reader_audio_duration_ms or 0))

        if speed == 1.0 and start_original_ms == 0:
            return str(source)

        segment = AudioSegment.from_file(str(source))
        if start_original_ms > 0:
            segment = segment[start_original_ms:]

        temp_segment_path = Path(f"reader_segment_{uuid4().hex}.wav").resolve()
        segment.export(str(temp_segment_path), format="wav")
        self.generated_audio_files.append(str(temp_segment_path))

        if speed == 1.0:
            return str(temp_segment_path)

        adjusted_path = Path(f"reader_speed_{speed}_{uuid4().hex}.wav").resolve()
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(temp_segment_path),
                "-filter:a",
                f"atempo={speed}",
                str(adjusted_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            creationflags=creation_flags,
        )

        self.generated_audio_files.append(str(adjusted_path))
        return str(adjusted_path)

    def play_current_audio_from(self, original_position_ms: int = 0):
        if not self.ensure_audio_backend():
            return
        if not self.reader_base_audio_path:
            self.set_status("No audio loaded", error=True)
            return

        rate = self.playback_rate()
        self.reader_last_rate = rate
        self.reader_seek_base_original_ms = max(0, min(int(original_position_ms or 0), self.reader_audio_duration_ms or 0))
        self.reader_active_audio_path = self.make_playback_segment_audio(
            self.reader_base_audio_path,
            rate,
            self.reader_seek_base_original_ms,
        )
        self.reader_current_audio_path = self.reader_active_audio_path
        remaining_original = max(0, (self.reader_audio_duration_ms or 0) - self.reader_seek_base_original_ms)
        self.reader_active_duration_ms = int(remaining_original / max(rate, 0.01))

        pygame.mixer.music.stop()
        pygame.mixer.music.load(self.reader_active_audio_path)
        pygame.mixer.music.play()

        self.audio_paused = False
        self.reader_paused_pos_ms = 0
        self.reader_playback_status = "Playing"
        self.playback_timer.start()
        self.update_playback_ui()
        self.update_right_panel("Reader")

    def change_playback_speed(self):
        rate = self.playback_rate()
        if self.reader_base_audio_path:
            original_pos = self.original_position_ms()
            was_playing = self.ensure_audio_backend() and pygame.mixer.music.get_busy() and not self.audio_paused
            self.play_current_audio_from(original_pos)
            if not was_playing:
                pygame.mixer.music.pause()
                self.audio_paused = True
                self.reader_playback_status = "Paused"
        self.set_status(f"Playback speed set to {rate:g}x")
        self.update_playback_ui()
        if self.current_page_name == "Reader":
            self.update_right_panel("Reader")

    def update_playback_ui(self):
        if not self.reader_current_audio_path:
            return
        if not self.ensure_audio_backend():
            self.playback_timer.stop()
            return

        active_pos = self.reader_paused_pos_ms if self.audio_paused else max(pygame.mixer.music.get_pos(), 0)
        original_elapsed = self.reader_seek_base_original_ms + int(active_pos * max(self.reader_last_rate, 0.01))
        original_elapsed = max(0, min(original_elapsed, self.reader_audio_duration_ms or original_elapsed))

        duration = max(self.reader_audio_duration_ms or 1, 1)
        progress = max(0.0, min(1.0, original_elapsed / duration))

        self.reader_time_left.setText(self.format_ms(original_elapsed))
        self.reader_time_right.setText(self.format_ms(self.reader_audio_duration_ms))
        self.reader_waveform.set_progress(progress)
        if self.current_page_name == "Reader":
            self.update_reader_sentence_highlight(progress)

        if hasattr(self, "translate_time_left"):
            self.translate_time_left.setText(self.format_ms(original_elapsed))
            self.translate_time_right.setText(self.format_ms(self.reader_audio_duration_ms))
            self.translate_waveform.set_progress(progress)

        if progress >= 0.999 and not pygame.mixer.music.get_busy() and self.reader_playback_status == "Playing":
            self.reader_playback_status = "Stopped"
            self.audio_paused = False
            self.reader_paused_pos_ms = 0
            self.reader_seek_base_original_ms = 0
            self.playback_timer.stop()
            self.set_status("Audio finished")

        # Do not rebuild the right-side Reader cards on every playback tick.
        # Recreating those widgets at 60 FPS caused visible flicker while audio played.
        # The cards are refreshed only on discrete state changes: play, pause, stop, speed, import.

    def play_audio_file(self, audio_path):
        self.reader_base_audio_path = str(Path(audio_path).resolve())
        self.reader_current_audio_path = self.reader_base_audio_path
        self.reader_seek_base_original_ms = 0
        self.reader_audio_duration_ms = len(AudioSegment.from_file(self.reader_base_audio_path))
        self.reader_active_duration_ms = self.effective_duration_ms()
        self.reader_time_left.setText("00:00")
        self.reader_time_right.setText(self.format_ms(self.reader_audio_duration_ms))
        self.reader_waveform.load_audio(self.reader_base_audio_path)
        self.reader_waveform.set_progress(0)
        if hasattr(self, "translate_time_left"):
            self.translate_time_left.setText("00:00")
            self.translate_time_right.setText(self.format_ms(self.reader_audio_duration_ms))
            self.translate_waveform.load_audio(self.reader_base_audio_path)
            self.translate_waveform.set_progress(0)
        self.play_current_audio_from(0)

    def seek_reader_to_progress(self, progress: float):
        if not self.reader_base_audio_path or not self.reader_audio_duration_ms:
            self.set_status("No audio loaded", error=True)
            return

        progress = max(0.0, min(1.0, progress))
        original_position = int(self.reader_audio_duration_ms * progress)
        was_paused = self.audio_paused or self.reader_playback_status == "Paused"

        self.play_current_audio_from(original_position)

        if was_paused:
            pygame.mixer.music.pause()
            self.audio_paused = True
            self.reader_paused_pos_ms = 0
            self.reader_playback_status = "Paused"

        self.reader_waveform.set_progress(progress)
        self.reader_time_left.setText(self.format_ms(original_position))
        self.set_status(f"Jumped to {self.format_ms(original_position)}")
        self.update_right_panel("Reader")

    def rewind_audio(self):
        if not self.reader_base_audio_path:
            self.set_status("No audio loaded", error=True)
            return
        self.play_current_audio_from(0)
        self.reader_waveform.set_progress(0)
        self.set_status("Audio rewound")
        self.update_right_panel("Reader")

    def pause_resume_audio(self):
        if not self.ensure_audio_backend():
            return
        if not self.reader_current_audio_path:
            self.set_status("No audio loaded", error=True)
            return

        if self.audio_paused:
            pygame.mixer.music.unpause()
            self.audio_paused = False
            self.reader_playback_status = "Playing"
            self.playback_timer.start()
            self.set_status("Audio resumed")
        else:
            self.reader_paused_pos_ms = max(pygame.mixer.music.get_pos(), 0)
            pygame.mixer.music.pause()
            self.audio_paused = True
            self.reader_playback_status = "Paused"
            self.set_status("Audio paused")
        self.update_right_panel("Reader")

    def stop_audio(self):
        if self.ensure_audio_backend():
            pygame.mixer.music.stop()
        self.audio_paused = False
        self.reader_paused_pos_ms = 0
        self.reader_seek_base_original_ms = 0
        self.reader_playback_status = "Stopped"
        self.playback_timer.stop()
        if hasattr(self, "reader_time_left"):
            self.reader_time_left.setText("00:00")
            self.reader_waveform.set_progress(0)
            self.clear_reader_highlight()
        if hasattr(self, "translate_time_left"):
            self.translate_time_left.setText("00:00")
            self.translate_waveform.set_progress(0)
        self.set_status("Audio stopped")
        self.update_right_panel("Reader")

    def send_reader_to_translate(self):
        text = self.reader_text.toPlainText().strip()
        if not text:
            self.set_status("No reader text to send", error=True)
            return
        self.translate_input.setPlainText(text)
        detected = self.reader_detected_language if self.reader_detected_language and self.reader_detected_language != "Auto" else "auto"
        idx = self.translate_source.findData(detected)
        if idx >= 0:
            self.translate_source.setCurrentIndex(idx)
        self.switch_page("Translate")
        self.set_status("Reader text sent to Translate")

    def read_translation_aloud(self):
        current_input = self.translate_input.toPlainText().strip()
        current_source = self.translate_source.currentData()
        current_target = self.translate_target.currentData()

        if not current_input:
            self.set_status("No text to translate/read", error=True)
            return

        needs_translation = (
            not self.last_translation_tts_text.strip()
            or self.last_translation_input_snapshot != self.translate_input.toPlainText()
            or self.last_translation_source_snapshot != current_source
            or self.last_translation_target_snapshot != current_target
        )

        if needs_translation:
            self.translate_output.setText("Translating before reading...")
            self.set_status("Translating before reading")

            def translate_task():
                response = requests.post(
                    f"{SERVER_URL}/reader/translate",
                    data={
                        "text": self.translate_input.toPlainText(),
                        "source_lang": current_source,
                        "target_lang": current_target,
                    },
                    timeout=180,
                )
                return response.json()

            def translate_success(data):
                if not data.get("ok"):
                    self.translate_output.setText(str(data))
                    self.set_status("Translation failed", error=True)
                    return

                translation = data["translation"]
                self.last_translation_route = self.simplify_route(translation.get("route", []))
                formatted = self.format_translation_output(translation)
                self.last_translation_plain_text = formatted
                self.last_translation_tts_text = translation.get("translated_text", "")
                self.last_translation_input_snapshot = self.translate_input.toPlainText()
                self.last_translation_source_snapshot = current_source
                self.last_translation_target_snapshot = current_target
                self.translate_output.setText(formatted)
                label = self.translate_document_name or f"{data.get('source_lang', current_source)} → {data.get('target_lang', current_target)}"
                self.add_recent("Translate", label)
                self.update_right_panel("Translate")
                self.generate_translation_audio()

            self.run_background(translate_task, translate_success)
            return

        self.generate_translation_audio()

    def generate_translation_audio(self):
        text = (self.last_translation_tts_text or self.last_translation_plain_text or self.translate_output.toPlainText()).strip()
        if not text or text in {"Translating...", "Translating before reading..."}:
            self.set_status("No translation to read", error=True)
            return

        target_lang = self.translate_target.currentData() or "en"
        self.active_audio_context = "Translate"
        self.set_status("Generating translation audio")

        def task():
            response = requests.post(
                f"{SERVER_URL}/reader/speak",
                data={"text": text[:5000], "lang": target_lang, "speed": "1.0"},
                timeout=240,
            )
            if response.status_code != 200:
                raise RuntimeError(response.text)
            out_path = Path(f"translation_output_{uuid4().hex}.wav").resolve()
            with open(out_path, "wb") as audio_file:
                audio_file.write(response.content)
            return str(out_path)

        def success(path):
            self.generated_audio_files.append(path)
            self.play_audio_file(path)
            self.reader_playback_status = "Playing"
            self.set_status("Reading translation")
            self.update_right_panel(self.current_page_name)

        self.run_background(task, success)

    # ---------- OCR ----------
    def build_ocr_page(self):
        page = QWidget()
        page.setObjectName("SignalOcrPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(self.page_title("SCAN / OCR PIPELINE", "RapidOCR images • Tesseract scanned PDFs • local translation"))

        controls_host = QWidget()
        controls_host.setObjectName("SignalFunctionStrip")
        self.ocr_controls_host = self.register_band_widget(controls_host)
        controls = QHBoxLayout(controls_host)
        self.ocr_controls_row = controls
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(10)

        self.ocr_language_label = QLabel("OCR lang")
        self.ocr_lang = self.language_box("auto", include_auto=True)
        self.ocr_lang.setMinimumWidth(120)
        self.ocr_lang.setMaximumWidth(160)

        self.ocr_ai_cleanup_cb = QCheckBox("AI CLEANUP / OFF BY DEFAULT")
        self.ocr_ai_cleanup_cb.setObjectName("SignalCheck")
        self.ocr_ai_cleanup_cb.setToolTip("Use local LLM to clean up OCR typos and formatting")

        self.ocr_target_label = QLabel("Translate to")
        self.ocr_target_lang = self.language_box("de", include_auto=False)
        self.ocr_target_lang.setMinimumWidth(120)
        self.ocr_target_lang.setMaximumWidth(160)

        btn_extract = self.register_responsive_button(QPushButton("Extract Text"), "Extract", "OCR")
        btn_extract.setObjectName("SecondaryButton")
        btn_extract.clicked.connect(lambda: self.ocr_extract(translate=False))

        btn_translate = self.register_responsive_button(QPushButton("Extract & Translate"), "Ext & Trans", "OCRTrans")
        btn_translate.setObjectName("PrimaryButton")
        btn_translate.clicked.connect(lambda: self.ocr_extract(translate=True))

        btn_batch_ocr = self.register_responsive_button(QPushButton("📁 Batch OCR"), "Batch OCR", "BatchOCR")
        btn_batch_ocr.setObjectName("SecondaryButton")
        btn_batch_ocr.clicked.connect(self.batch_ocr_documents)

        controls.addWidget(self.ocr_language_label)
        controls.addWidget(self.ocr_lang)
        controls.addWidget(self.ocr_ai_cleanup_cb)
        controls.addWidget(self.ocr_target_label)
        controls.addWidget(self.ocr_target_lang)
        controls.addWidget(btn_extract)
        controls.addWidget(btn_translate)
        controls.addWidget(btn_batch_ocr)
        controls.addStretch(1)
        route_status = QLabel("ROUTE  AUTO  •  IMAGE→RAPIDOCR  •  PDF→TESSERACT")
        route_status.setObjectName("SignalMetaLine")
        controls.addWidget(route_status)
        layout.addWidget(controls_host)

        # Content split area: Extracted text & Translated text
        panes_row = QHBoxLayout()
        panes_row.setSpacing(12)

        # Left pane: Extracted OCR Text
        left_box = QVBoxLayout()
        left_lbl = QLabel("EXTRACTED TEXT")
        left_lbl.setObjectName("SignalPaneLabel")
        self.ocr_text = self.make_responsive_text_edit(QTextEdit())
        self.ocr_text.setObjectName("SignalOcrText")
        self.ocr_text.setPlaceholderText("Extracted OCR text will appear here...")
        self.ocr_text.setMinimumHeight(210)
        left_box.addWidget(left_lbl)
        left_box.addWidget(self.ocr_text, 1)
        panes_row.addLayout(left_box, 1)

        # Right pane: Translated Text
        right_box = QVBoxLayout()
        right_lbl = QLabel("TRANSLATED TEXT")
        right_lbl.setObjectName("SignalPaneLabel")
        self.ocr_translated_text = self.make_responsive_text_edit(QTextEdit())
        self.ocr_translated_text.setObjectName("SignalOcrTranslation")
        self.ocr_translated_text.setPlaceholderText("Translation will appear here...")
        self.ocr_translated_text.setMinimumHeight(210)
        right_box.addWidget(right_lbl)
        right_box.addWidget(self.ocr_translated_text, 1)
        panes_row.addLayout(right_box, 1)

        layout.addLayout(panes_row, 1)

        # Bottom actions row
        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)

        send_to_translate_btn = QPushButton("⇄ Send to Translate Tab")
        send_to_translate_btn.setObjectName("SecondaryButton")
        send_to_translate_btn.clicked.connect(self.ocr_send_to_translate)

        send_to_reader_btn = QPushButton("📖 Send to Reader Tab")
        send_to_reader_btn.setObjectName("SecondaryButton")
        send_to_reader_btn.clicked.connect(self.ocr_send_to_reader)

        self.ocr_export_format = WheelSafeComboBox()
        for label, fmt in [("DOCX (.docx)", "docx"), ("PDF (.pdf)", "pdf"), ("Text (.txt)", "txt")]:
            self.ocr_export_format.addItem(label, fmt)
        self.ocr_export_format = self.make_responsive_combo(self.ocr_export_format)

        export_ocr_btn = QPushButton("⤓ Export")
        export_ocr_btn.setObjectName("SecondaryButton")
        export_ocr_btn.clicked.connect(lambda: self.export_ocr_text(self.ocr_export_format.currentData()))

        actions_row.addWidget(send_to_translate_btn)
        actions_row.addWidget(send_to_reader_btn)
        actions_row.addWidget(self.ocr_export_format)
        actions_row.addWidget(export_ocr_btn)
        actions_row.addStretch(1)

        layout.addLayout(actions_row)
        return page

    def ocr_send_to_translate(self):
        text = self.ocr_text.toPlainText().strip()
        if not text:
            self.set_status("No OCR text to send", error=True)
            return
        self.switch_page("Translate")
        self.translate_input.setPlainText(text)
        self.set_status("Sent OCR text to Translate tab")

    def ocr_send_to_reader(self):
        text = self.ocr_text.toPlainText().strip()
        if not text:
            self.set_status("No OCR text to send", error=True)
            return
        self.switch_page("Reader")
        self.reader_input.setPlainText(text)
        self.set_status("Sent OCR text to Reader tab")

    def ocr_extract(self, translate=False):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open image or scanned PDF",
            "",
            "Images/PDF (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.pdf);;All Files (*.*)",
        )
        if path:
            self.ocr_extract_path(path, translate=translate)

    def ocr_extract_path(self, path: str, translate=False):
        if not path:
            return
        suffix = Path(path).suffix.lower()
        if suffix not in OCR_EXTENSIONS:
            self.set_status(f"Unsupported OCR file: {suffix}", error=True)
            return
        self.switch_page("OCR")
        self.ocr_text.setText("Extracting OCR text...")
        if translate:
            self.ocr_translated_text.setText("Translating...")
        else:
            self.ocr_translated_text.setText("")
        self.set_status("Running OCR & Translation" if translate else "Running OCR")

        def task():
            ai_cleanup = self.ocr_ai_cleanup_cb.isChecked() if hasattr(self, "ocr_ai_cleanup_cb") else False
            with open(path, "rb") as f:
                response = requests.post(
                    f"{SERVER_URL}/ocr/extract",
                    files={"file": f},
                    data={
                        "lang": self.ocr_lang.currentData(),
                        "ai_cleanup": "true" if ai_cleanup else "false",
                    },
                    timeout=300,
                )
            ocr_res = response.json()
            if not ocr_res.get("ok"):
                return ocr_res

            if translate and ocr_res.get("text"):
                target_lang = self.ocr_target_lang.currentData() if hasattr(self, "ocr_target_lang") else "de"
                source_lang = self.ocr_lang.currentData() if hasattr(self, "ocr_lang") else "auto"
                extracted_text = ocr_res.get("text", "").strip()
                translated_text = ""
                try:
                    trans_res = requests.post(
                        f"{SERVER_URL}/reader/translate",
                        data={
                            "text": extracted_text,
                            "source_lang": source_lang,
                            "target_lang": target_lang,
                        },
                        timeout=300,
                    ).json()
                    if isinstance(trans_res, dict):
                        t_obj = trans_res.get("translation")
                        if isinstance(t_obj, dict):
                            translated_text = t_obj.get("translated_text", "")
                        elif isinstance(t_obj, str):
                            translated_text = t_obj
                        else:
                            translated_text = trans_res.get("translated_text", "")
                except Exception as exc:
                    print(f"[DEBUG] /reader/translate error: {exc}")

                if not translated_text and extracted_text:
                    try:
                        fallback_res = requests.post(
                            f"{SERVER_URL}/translate",
                            data={
                                "text": extracted_text,
                                "source_lang": source_lang,
                                "target_lang": target_lang,
                            },
                            timeout=300,
                        ).json()
                        if isinstance(fallback_res, dict):
                            translated_text = fallback_res.get("translated_text", "")
                    except Exception as exc:
                        print(f"[DEBUG] /translate fallback error: {exc}")

                ocr_res["translated_text"] = translated_text
            return ocr_res

        def success(data):
            if not isinstance(data, dict):
                self.ocr_text.setPlainText(str(data))
                self.set_status("OCR failed", error=True)
                return

            details = []
            if data.get("average_confidence") is not None:
                details.append(f"Average confidence: {data.get('average_confidence')}%")
            if data.get("line_count") is not None:
                details.append(f"Lines: {data.get('line_count')}")
            body = data.get("text", str(data))
            if details and data.get("ok"):
                body = body + "\n\n--- OCR Diagnostics ---\n" + "\n".join(details)
            self.ocr_text.setPlainText(body)
            if translate:
                self.ocr_translated_text.setPlainText(data.get("translated_text") or "No translation returned.")

            self.ocr_status = "Complete" if data.get("ok") else "Failed"
            if data.get("ok"):
                self.add_recent("OCR", Path(path).name)
            self.set_status("OCR & Translation complete" if (translate and data.get("ok")) else ("OCR complete" if data.get("ok") else "OCR failed"), error=not data.get("ok"))
            self.update_right_panel("OCR")

        self.run_background(task, success)

    # ---------- Notes ----------
    def build_notes_page(self):
        page = QWidget()
        page.setObjectName("SignalNotesPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(self.page_title("SAVED NOTES / LOCAL VAULT", "Searchable local archive for speech, OCR, reader, and translation results"))

        command_strip = QFrame()
        command_strip.setObjectName("SignalFunctionStrip")
        command_row = QHBoxLayout(command_strip)
        command_row.setContentsMargins(8, 6, 8, 6)
        search = QLineEdit()
        search.setObjectName("SearchBox")
        search.setPlaceholderText("Search local notes...")
        command_row.addWidget(search, 1)
        source_filter = WheelSafeComboBox()
        for item in ("All sources", "Speech", "OCR", "Reader", "Translate"):
            source_filter.addItem(item)
        command_row.addWidget(source_filter)
        vault_status = QLabel("LOCAL VAULT  •  PRIVATE")
        vault_status.setObjectName("SignalPrivacyBadge")
        command_row.addWidget(vault_status)
        layout.addWidget(command_strip)

        self.note_title = self.make_responsive_text_edit(QTextEdit())
        self.note_title.setObjectName("SignalNoteTitle")
        self.note_title.setMaximumHeight(52)
        self.note_content = self.make_responsive_text_edit(QTextEdit())
        self.note_content.setObjectName("SignalNoteEditor")
        self.notes_list = self.make_responsive_text_edit(QTextEdit())
        self.notes_list.setObjectName("SignalNotesList")
        self.notes_list.setReadOnly(True)
        save_btn = self.register_general_button(QPushButton("Save Note"), "Save")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self.save_note)
        refresh_btn = QPushButton("Refresh Notes")
        refresh_btn.setObjectName("SecondaryButton")
        refresh_btn.clicked.connect(self.load_notes)

        workspace = QGridLayout()
        workspace.setContentsMargins(0, 0, 0, 0)
        workspace.setHorizontalSpacing(10)
        list_label = QLabel("NOTE INDEX  /  MODIFIED DESC")
        list_label.setObjectName("SignalPaneLabel")
        editor_label = QLabel("NOTE DETAIL  /  EDITOR")
        editor_label.setObjectName("SignalPaneLabel")
        workspace.addWidget(list_label, 0, 0)
        workspace.addWidget(editor_label, 0, 1)
        workspace.addWidget(self.notes_list, 1, 0, 3, 1)
        workspace.addWidget(self.note_title, 1, 1)
        workspace.addWidget(self.note_content, 2, 1)
        editor_actions = QHBoxLayout()
        editor_actions.addWidget(save_btn)
        editor_actions.addWidget(refresh_btn)
        editor_actions.addStretch(1)
        editor_actions.addWidget(QLabel("SOURCE  MANUAL  •  LANGUAGE  EN"))
        workspace.addLayout(editor_actions, 3, 1)
        workspace.setColumnStretch(0, 2)
        workspace.setColumnStretch(1, 3)
        workspace.setRowStretch(2, 1)
        layout.addLayout(workspace, 1)
        return page

    def save_note(self):
        def task():
            response = requests.post(f"{SERVER_URL}/notes/create", data={"title": self.note_title.toPlainText().strip() or "Untitled", "content": self.note_content.toPlainText(), "language": "en"}, timeout=30)
            return response.json()
        def success(data):
            title = data.get('title', 'Untitled')
            self.add_recent("Notes", title)
            self.set_status(f"Note saved: {title}")
        self.run_background(task, success)

    def load_notes(self):
        def task():
            return requests.get(f"{SERVER_URL}/notes", timeout=30).json()
        def success(notes):
            self.notes_list.setText("\n\n".join(f"[{n['id']}] {n['title']} ({n['language']})\n{n['content'][:300]}" for n in notes))
            self.set_status("Notes loaded")
        self.run_background(task, success)

    # ---------- Background Task Center ----------
    def build_tasks_page(self):
        page = QWidget()
        page.setObjectName("SignalTasksPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(self.page_title(
            "TASK CENTER / BACKGROUND AI",
            "Permission-controlled workflows that continue while you use the rest of LinguaFusion",
        ))

        safety_strip = QFrame()
        safety_strip.setObjectName("SignalFunctionStrip")
        safety_row = QHBoxLayout(safety_strip)
        safety_row.setContentsMargins(10, 7, 10, 7)
        safety_row.addWidget(QLabel("PHASE A  •  VALIDATED TASK PLANS"))
        safety_row.addStretch(1)
        safety_badge = QLabel("NO SHELL  •  NO UNRESTRICTED FILE ACCESS  •  LOCAL WRITES ASK FIRST")
        safety_badge.setObjectName("SignalPrivacyBadge")
        safety_row.addWidget(safety_badge)
        layout.addWidget(safety_strip)

        planner = Card("Card")
        planner.setObjectName("SignalTaskPlanner")
        planner_layout = QVBoxLayout(planner)
        planner_layout.setContentsMargins(18, 16, 18, 16)
        planner_layout.setSpacing(10)
        planner_title = QLabel("ASK LINGUAFUSION")
        planner_title.setObjectName("CardTitle")
        planner_layout.addWidget(planner_title)
        planner_help = QLabel(
            "Describe a multi-step translation, transcription, or note task in ordinary language. "
            "Ollama creates a preview only; nothing runs until you confirm it."
        )
        planner_help.setObjectName("Muted")
        planner_help.setWordWrap(True)
        planner_layout.addWidget(planner_help)
        self.agent_natural_request = self.make_responsive_text_edit(QTextEdit())
        self.agent_natural_request.setPlaceholderText(
            "Example: Translate 'Good morning' to Odia, then save the result as a note called Greeting"
        )
        self.agent_natural_request.setMinimumHeight(82)
        planner_layout.addWidget(self.agent_natural_request)
        planner_actions = QHBoxLayout()
        self.agent_plan_button = QPushButton("Create Safe Plan")
        self.agent_plan_button.setObjectName("PrimaryButton")
        self.agent_plan_button.clicked.connect(self.plan_agent_request)
        self.agent_confirm_plan_button = QPushButton("Confirm & Queue")
        self.agent_confirm_plan_button.setObjectName("SecondaryButton")
        self.agent_confirm_plan_button.setEnabled(False)
        self.agent_confirm_plan_button.clicked.connect(self.confirm_agent_plan)
        discard_plan = QPushButton("Discard")
        discard_plan.setObjectName("SecondaryButton")
        discard_plan.clicked.connect(self.clear_agent_plan)
        planner_actions.addWidget(self.agent_plan_button)
        planner_actions.addWidget(self.agent_confirm_plan_button)
        planner_actions.addWidget(discard_plan)
        planner_actions.addStretch(1)
        planner_layout.addLayout(planner_actions)
        self.agent_plan_preview_text = self.make_responsive_text_edit(QTextEdit())
        self.agent_plan_preview_text.setReadOnly(True)
        self.agent_plan_preview_text.setMinimumHeight(115)
        self.agent_plan_preview_text.setPlaceholderText(
            "The proposed steps and permission requirements will appear here for review."
        )
        planner_layout.addWidget(self.agent_plan_preview_text)
        self.agent_plan_preview = None
        layout.addWidget(planner)

        composer = Card("Card")
        composer.setObjectName("SignalTaskComposer")
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(18, 16, 18, 16)
        composer_layout.setSpacing(10)
        composer_title = QLabel("QUEUE A TRANSLATION WORKFLOW")
        composer_title.setObjectName("CardTitle")
        composer_layout.addWidget(composer_title)

        language_row = QHBoxLayout()
        self.agent_source_lang = WheelSafeComboBox()
        self.agent_source_lang.addItem("Detect language", "auto")
        for label, code in LANGUAGES:
            self.agent_source_lang.addItem(label, code)
        self.agent_target_lang = self.language_box("de")
        language_row.addWidget(QLabel("From"))
        language_row.addWidget(self.agent_source_lang, 1)
        language_row.addWidget(QLabel("To"))
        language_row.addWidget(self.agent_target_lang, 1)
        composer_layout.addLayout(language_row)

        self.agent_request_text = self.make_responsive_text_edit(QTextEdit())
        self.agent_request_text.setPlaceholderText("Enter the text to translate in the background…")
        self.agent_request_text.setMinimumHeight(105)
        composer_layout.addWidget(self.agent_request_text)

        note_row = QHBoxLayout()
        self.agent_save_note = QCheckBox("Save the result as a local note (requires approval)")
        self.agent_note_title = QLineEdit()
        self.agent_note_title.setPlaceholderText("Note title")
        note_row.addWidget(self.agent_save_note)
        note_row.addWidget(self.agent_note_title, 1)
        composer_layout.addLayout(note_row)

        queue_row = QHBoxLayout()
        queue_translation = QPushButton("Queue Translation")
        queue_translation.setObjectName("PrimaryButton")
        queue_translation.clicked.connect(self.queue_agent_translation)
        queue_audio = QPushButton("Queue Audio Transcription")
        queue_audio.setObjectName("SecondaryButton")
        queue_audio.clicked.connect(self.queue_agent_audio)
        queue_row.addWidget(queue_translation)
        queue_row.addWidget(queue_audio)
        queue_row.addStretch(1)
        composer_layout.addLayout(queue_row)
        layout.addWidget(composer)

        monitor = Card("Card")
        monitor.setObjectName("SignalTaskMonitor")
        monitor_layout = QVBoxLayout(monitor)
        monitor_layout.setContentsMargins(18, 16, 18, 16)
        monitor_layout.setSpacing(10)
        monitor_header = QHBoxLayout()
        monitor_title = QLabel("LIVE TASK QUEUE")
        monitor_title.setObjectName("CardTitle")
        monitor_header.addWidget(monitor_title)
        self.agent_task_selector = WheelSafeComboBox()
        self.agent_task_selector.setMinimumWidth(280)
        monitor_header.addWidget(self.agent_task_selector, 1)
        refresh = QPushButton("Refresh")
        refresh.setObjectName("SecondaryButton")
        refresh.clicked.connect(self.load_agent_tasks)
        monitor_header.addWidget(refresh)
        monitor_layout.addLayout(monitor_header)

        action_row = QHBoxLayout()
        for label, action in [
            ("Approve Write", "approve"),
            ("Pause", "pause"),
            ("Resume", "resume"),
            ("Cancel", "cancel"),
            ("Retry", "retry"),
        ]:
            button = QPushButton(label)
            button.setObjectName("PrimaryButton" if action == "approve" else "SecondaryButton")
            button.clicked.connect(lambda checked=False, value=action: self.agent_task_action(value))
            action_row.addWidget(button)
        action_row.addStretch(1)
        monitor_layout.addLayout(action_row)

        self.agent_task_output = self.make_responsive_text_edit(QTextEdit())
        self.agent_task_output.setReadOnly(True)
        self.agent_task_output.setMinimumHeight(230)
        self.agent_task_output.setPlaceholderText("Queued tasks, progress, approvals, and results appear here.")
        monitor_layout.addWidget(self.agent_task_output, 1)
        layout.addWidget(monitor, 1)

        self.agent_poll_timer = QTimer(page)
        self.agent_poll_timer.setInterval(1500)
        self.agent_poll_timer.timeout.connect(
            lambda: self.load_agent_tasks(silent=True) if self.current_page_name == "Tasks" else None
        )
        self.agent_poll_timer.start()
        QTimer.singleShot(500, lambda: self.load_agent_tasks(silent=True))
        return page

    def plan_agent_request(self):
        request_text = self.agent_natural_request.toPlainText().strip()
        if not request_text:
            self.set_status("Describe the task you want LinguaFusion to plan.", error=True)
            return
        self.agent_plan_preview = None
        self.agent_confirm_plan_button.setEnabled(False)
        self.agent_plan_preview_text.setPlainText("Ollama is preparing a restricted plan on this PC...")
        self.set_status("Creating a safe local plan...")

        def task():
            response = requests.post(
                f"{SERVER_URL}/agent/plan",
                json={"request": request_text},
                timeout=150,
            )
            if not response.ok:
                try:
                    detail = response.json().get("detail", response.text)
                except Exception:
                    detail = response.text
                raise RuntimeError(str(detail))
            return response.json()

        def success(plan):
            self.agent_plan_preview = plan if plan.get("can_execute") else None
            self.agent_confirm_plan_button.setEnabled(bool(self.agent_plan_preview))
            self.agent_plan_preview_text.setPlainText(self._format_agent_plan(plan))
            if plan.get("can_execute"):
                self.set_status("Plan ready. Review every step, then confirm to queue it.")
            else:
                self.set_status("That request needs a capability that is currently disabled.", error=True)

        def failure(exc):
            self.agent_plan_preview_text.setPlainText(f"Plan unavailable: {exc}")
            self.set_status(f"Could not create the plan: {exc}", error=True)

        self.run_background(task, success, failure)

    @staticmethod
    def _format_agent_plan(plan):
        lines = [
            str(plan.get("title") or "Proposed plan"),
            str(plan.get("summary") or ""),
            "",
        ]
        if not plan.get("can_execute"):
            lines.append("CANNOT RUN WITH THE CURRENT SAFE TOOL SET")
        for index, step in enumerate(plan.get("steps") or [], 1):
            tool_name = str(step.get("tool") or "").replace("_", " ").title()
            lines.append(f"{index}. {tool_name}")
        automatic = plan.get("automatic_permissions") or []
        approval = plan.get("approval_required") or []
        if automatic:
            lines.append("\nRuns automatically: " + ", ".join(automatic))
        if approval:
            lines.append("PC-owner approval required: " + ", ".join(approval))
        for warning in plan.get("warnings") or []:
            lines.append("Note: " + str(warning))
        lines.append(f"\nPlanner: {plan.get('model', 'local Ollama')} - Nothing has run yet")
        return "\n".join(lines).strip()

    def clear_agent_plan(self):
        self.agent_plan_preview = None
        self.agent_confirm_plan_button.setEnabled(False)
        self.agent_plan_preview_text.clear()
        self.set_status("Plan discarded. Nothing was executed.")

    def confirm_agent_plan(self):
        plan = self.agent_plan_preview
        if not plan or not plan.get("can_execute"):
            self.set_status("Create and review a valid plan first.", error=True)
            return
        payload = {
            "request": plan.get("request", ""),
            "steps": plan.get("steps", []),
            "time_budget_seconds": plan.get("time_budget_seconds", 600),
            "max_retries": plan.get("max_retries", 2),
        }
        self.agent_confirm_plan_button.setEnabled(False)

        def task():
            response = requests.post(f"{SERVER_URL}/agent/tasks", json=payload, timeout=30)
            if not response.ok:
                detail = response.json().get("detail", response.text)
                raise RuntimeError(str(detail))
            return response.json()

        def success(data):
            queued = data.get("task", {})
            self.agent_plan_preview = None
            message = (
                "Waiting for PC-owner write approval."
                if queued.get("state") == "awaiting_approval"
                else "Execution has started."
            )
            self.agent_plan_preview_text.append("\n\nQueued safely. " + message)
            self.set_status("Confirmed plan queued in Task Center")
            self.load_agent_tasks(silent=True, select_task_id=queued.get("id"))

        def failure(exc):
            self.agent_confirm_plan_button.setEnabled(True)
            self.set_status(f"Could not queue the confirmed plan: {exc}", error=True)

        self.run_background(task, success, failure)

    def queue_agent_translation(self):
        text = self.agent_request_text.toPlainText().strip()
        if not text:
            self.set_status("Enter text before queueing a task.", error=True)
            return
        source = self.agent_source_lang.currentData() or "auto"
        target = self.agent_target_lang.currentData() or "de"
        steps = [{
            "tool": "translate_text",
            "input": {"text": text, "source_lang": source, "target_lang": target},
        }]
        if self.agent_save_note.isChecked():
            title = self.agent_note_title.text().strip() or "Background translation"
            steps.append({
                "tool": "create_note",
                "input": {"title": title, "content": "$step.0.translated_text", "language": target},
            })
        payload = {
            "request": "Translate text" + (" and save it as a note" if len(steps) > 1 else ""),
            "steps": steps,
            "time_budget_seconds": 900,
        }

        def task():
            response = requests.post(f"{SERVER_URL}/agent/tasks", json=payload, timeout=30)
            response.raise_for_status()
            return response.json()

        def success(data):
            queued = data.get("task", {})
            self.set_status(
                "Task is waiting for write approval" if queued.get("state") == "awaiting_approval" else "Background task queued"
            )
            self.load_agent_tasks(silent=True, select_task_id=queued.get("id"))

        self.run_background(task, success)

    def queue_agent_audio(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose audio for background transcription",
            "",
            "Audio files (*.wav *.mp3 *.m4a *.flac *.ogg *.webm *.aac *.mp4)",
        )
        if not path:
            return
        language = self.agent_source_lang.currentData() or "auto"
        self.set_status("Uploading audio to the private task store…")

        def task():
            with open(path, "rb") as handle:
                upload = requests.post(
                    f"{SERVER_URL}/agent/artifacts/audio",
                    files={"file": (Path(path).name, handle, "application/octet-stream")},
                    timeout=180,
                )
            upload.raise_for_status()
            artifact = upload.json()["artifact"]
            response = requests.post(
                f"{SERVER_URL}/agent/tasks",
                json={
                    "request": f"Transcribe {Path(path).name}",
                    "steps": [{
                        "tool": "transcribe_audio",
                        "input": {"artifact_id": artifact["id"], "language": language},
                    }],
                    "time_budget_seconds": 1800,
                },
                timeout=30,
            )
            response.raise_for_status()
            return response.json()

        def success(data):
            queued = data.get("task", {})
            self.set_status("Audio transcription queued in the background")
            self.load_agent_tasks(silent=True, select_task_id=queued.get("id"))

        self.run_background(task, success)

    def load_agent_tasks(self, silent=False, select_task_id=None):
        if getattr(self, "_agent_refreshing", False):
            return
        self._agent_refreshing = True

        def task():
            response = requests.get(f"{SERVER_URL}/agent/tasks?limit=50&details=true", timeout=20)
            response.raise_for_status()
            return response.json().get("tasks", [])

        def success(tasks):
            self._agent_refreshing = False
            current_id = select_task_id or self.agent_task_selector.currentData()
            self.agent_task_selector.blockSignals(True)
            self.agent_task_selector.clear()
            lines = []
            selected_index = 0
            for index, item in enumerate(tasks):
                label = f"{item.get('state', 'unknown').upper()}  {item.get('progress', 0)}%  •  {item.get('request', 'Task')[:55]}"
                self.agent_task_selector.addItem(label, item.get("id"))
                if item.get("id") == current_id:
                    selected_index = index
                lines.append(self._format_agent_task(item))
            if tasks:
                self.agent_task_selector.setCurrentIndex(selected_index)
            self.agent_task_selector.blockSignals(False)
            self.agent_task_output.setPlainText("\n\n".join(lines) if lines else "No background tasks yet.")
            if not silent:
                self.set_status(f"Task Center refreshed • {len(tasks)} task(s)")

        def failure(exc):
            self._agent_refreshing = False
            if not silent:
                self.set_status(f"Task Center refresh failed: {exc}", error=True)

        self.run_background(task, success, failure)

    @staticmethod
    def _format_agent_task(task):
        pending = sorted(set(task.get("required_permissions", [])) - set(task.get("approved_permissions", [])))
        lines = [
            f"{task.get('state', 'unknown').upper()}  •  {task.get('progress', 0)}%  •  {task.get('id', '')[:10]}",
            task.get("request", ""),
            f"Submitted by: {task.get('owner_id', 'local')}",
        ]
        if pending:
            lines.append("Approval needed: " + ", ".join(pending))
        if task.get("error"):
            lines.append("Error: " + str(task["error"]))
        for step in task.get("steps", []):
            lines.append(
                f"  {int(step.get('position', 0)) + 1}. {step.get('tool_name')} — {step.get('state')} ({step.get('progress', 0)}%)"
            )
        result = task.get("result") or {}
        preview = result.get("translated_text") or result.get("text")
        if preview:
            lines.append("Result: " + str(preview)[:600])
        return "\n".join(lines)

    def agent_task_action(self, action):
        task_id = self.agent_task_selector.currentData()
        if not task_id:
            self.set_status("Select a task first.", error=True)
            return
        endpoint = action
        body = {"permissions": ["local_write"]} if action == "approve" else None

        def task():
            response = requests.post(
                f"{SERVER_URL}/agent/tasks/{task_id}/{endpoint}", json=body, timeout=20
            )
            if not response.ok:
                detail = response.json().get("detail", response.text)
                raise RuntimeError(str(detail))
            return response.json()

        def success(data):
            updated = data.get("task", {})
            self.set_status(f"Task {action}: {updated.get('state', 'updated')}")
            self.load_agent_tasks(silent=True, select_task_id=task_id)

        self.run_background(task, success)

    # ---------- Speech / Settings ----------
    def build_speech_page(self):
        page = QWidget()
        page.setObjectName("SignalSpeechPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        command_strip = QFrame()
        command_strip.setObjectName("SignalCommandStrip")
        command_layout = QHBoxLayout(command_strip)
        command_layout.setContentsMargins(14, 8, 14, 8)
        command_layout.setSpacing(10)
        signal_title = QLabel("●  SPEECH / LIVE CAPTURE")
        signal_title.setObjectName("SignalTitle")
        command_layout.addWidget(signal_title)

        controls_host = QWidget()
        controls_host.setObjectName("SignalControls")
        self.speech_controls_host = self.register_band_widget(controls_host)
        controls = QGridLayout(controls_host)
        controls.setContentsMargins(0, 0, 0, 0)
        self.speech_language = self.make_responsive_combo(WheelSafeComboBox())
        self.speech_language.addItem("Auto", "auto")
        for label, code in LANGUAGES:
            self.speech_language.addItem(label, code)
        self.speech_target_language = self.language_box("de")
        self.speech_live_translation = QCheckBox("Live Translation")
        self.speech_live_translation.setObjectName("Muted")
        self.speech_live_translation.setChecked(True)
        self.speech_smart_correction = QCheckBox("Smart Correction")
        self.speech_smart_correction.setObjectName("Muted")
        self.speech_smart_correction.setChecked(True)
        self.speech_correction_mode = self.make_responsive_combo(WheelSafeComboBox())
        self.speech_correction_mode.addItem("Free Auto", "free_auto")
        self.speech_correction_mode.addItem("LanguageTool", "languagetool")
        self.speech_correction_mode.addItem("Offline only", "offline")
        controls.addWidget(QLabel("STT language"), 0, 0)
        controls.addWidget(self.speech_language, 0, 1)
        controls.addWidget(QLabel("Translate to"), 0, 2)
        controls.addWidget(self.speech_target_language, 0, 3)
        controls.addWidget(self.speech_live_translation, 0, 4)
        controls.addWidget(self.speech_smart_correction, 1, 0)
        controls.addWidget(QLabel("Correction"), 1, 2)
        controls.addWidget(self.speech_correction_mode, 1, 3)
        controls.setColumnStretch(1, 1)
        controls.setColumnStretch(3, 1)
        command_layout.addWidget(controls_host, 1)
        privacy_badge = QLabel("▣ LOCAL / PRIVATE")
        privacy_badge.setObjectName("SignalPrivacyBadge")
        command_layout.addWidget(privacy_badge)
        layout.addWidget(command_strip)

        recorder = self.register_compact_card(Card("Card"))
        recorder.setObjectName("SignalRecorder")
        self.speech_recorder_card = recorder
        recorder_layout = QVBoxLayout(recorder)
        recorder_layout.setContentsMargins(18, 14, 18, 14)
        self.speech_status_label = QLabel("Ready to record or import audio.")
        self.speech_status_label.setObjectName("SignalStatus")
        recorder_layout.addWidget(self.speech_status_label)

        wave_row = QHBoxLayout()
        self.speech_timer_label = QLabel("00:00")
        self.speech_timer_label.setObjectName("SignalTimer")
        self.speech_waveform = AudioWaveform()
        wave_row.addWidget(self.speech_timer_label)
        wave_row.addWidget(self.speech_waveform, 1)
        recorder_layout.addLayout(wave_row)

        speech_stage_row = QHBoxLayout()
        speech_stage_row.setSpacing(8)
        self.speech_stage_labels = {}
        for stage_id, stage_text in [
            ("listening", "01  LISTENING"),
            ("processing", "02  TRANSCRIBING"),
            ("translating", "03  TRANSLATING"),
            ("complete", "04  COMPLETE"),
        ]:
            stage_label = QLabel(stage_text)
            stage_label.setObjectName("SpeechStage")
            stage_label.setProperty("stageState", "idle")
            stage_label.setAlignment(Qt.AlignCenter)
            stage_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            speech_stage_row.addWidget(stage_label, 1)
            self.speech_stage_labels[stage_id] = stage_label
        recorder_layout.addLayout(speech_stage_row)

        record_btn = self.register_general_button(QPushButton("● Record"), "● Rec")
        record_btn.setObjectName("SignalRecordButton")
        record_btn.setMinimumHeight(48)
        record_btn.clicked.connect(self.start_speech_recording)
        pause_btn = self.register_general_button(QPushButton("⏸ Pause / Resume"), "⏸")
        pause_btn.setObjectName("SignalToolButton")
        pause_btn.clicked.connect(self.pause_resume_speech_recording)
        stop_btn = self.register_general_button(QPushButton("■ Stop"), "■")
        stop_btn.setObjectName("SignalToolButton")
        stop_btn.clicked.connect(self.stop_speech_recording)
        self.speech_record_button = record_btn
        self.speech_pause_button = pause_btn
        self.speech_stop_button = stop_btn
        self.speech_pause_button.setEnabled(False)
        self.speech_stop_button.setEnabled(False)
        import_audio_btn = self.register_general_button(QPushButton("＋ Import Audio"), "+ Audio")
        import_audio_btn.setObjectName("SignalToolButton")
        import_audio_btn.clicked.connect(self.import_speech_audio)
        full_song_btn = self.register_general_button(QPushButton("🎵 Full Song Pass"), "🎵 Song")
        full_song_btn.setObjectName("SignalToolButton")
        full_song_btn.clicked.connect(self.full_song_pass)
        reference_lyrics_btn = self.register_general_button(QPushButton("📄 Reference Lyrics"), "📄 Ref")
        reference_lyrics_btn.setObjectName("SignalToolButton")
        reference_lyrics_btn.clicked.connect(self.reference_lyrics_pass)

        record_row = QHBoxLayout()
        record_row.setSpacing(8)
        for btn in [record_btn, pause_btn, stop_btn]:
            record_row.addWidget(btn)
        record_row.addStretch(1)
        recorder_layout.addLayout(record_row)

        alt_input_label = QLabel("OR IMPORT")
        alt_input_label.setObjectName("SectionLabel")
        recorder_layout.addSpacing(4)
        recorder_layout.addWidget(alt_input_label)
        alt_input_row = QHBoxLayout()
        alt_input_row.setSpacing(8)
        for btn in [import_audio_btn, full_song_btn, reference_lyrics_btn]:
            alt_input_row.addWidget(btn)
        alt_input_row.addStretch(1)
        gpu_safety = QLabel("RTX 2080 Ti  •  11 GB VRAM  •  -500 MHz MEMORY OFFSET REQUIRED  •  CPU FALLBACK AVAILABLE")
        gpu_safety.setObjectName("SignalGpuSafety")
        gpu_safety.setToolTip("Confirm the -500 MHz memory clock offset in MSI Afterburner before GPU inference.")
        alt_input_row.addWidget(gpu_safety)
        recorder_layout.addLayout(alt_input_row)
        layout.addWidget(recorder)

        action_host = QWidget()
        action_host.setObjectName("SignalActionStrip")
        self.speech_action_host = self.register_band_widget(action_host)
        action_row = QVBoxLayout(action_host)
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        correct_btn = self.register_general_button(QPushButton("＋ Add Correction"), "+ Corr")
        correct_btn.setObjectName("SecondaryButton")
        correct_btn.clicked.connect(self.add_manual_correction)
        smart_fix_btn = self.register_general_button(QPushButton("✨ Smart Fix Selection"), "✨ Fix")
        smart_fix_btn.setObjectName("SecondaryButton")
        smart_fix_btn.clicked.connect(self.smart_fix_selection)
        read_transcript_btn = self.register_general_button(QPushButton("▶ Read Transcript"), "▶ Tr")
        read_transcript_btn.setObjectName("PrimaryButton")
        read_transcript_btn.clicked.connect(self.read_speech_transcript)
        read_translation_btn = self.register_general_button(QPushButton("▶ Read Translation"), "▶ T")
        read_translation_btn.setObjectName("SecondaryButton")
        read_translation_btn.clicked.connect(self.read_speech_translation)
        pause_audio_btn = self.register_general_button(QPushButton("⏸ Pause / Resume"), "⏸")
        pause_audio_btn.setObjectName("SecondaryButton")
        pause_audio_btn.clicked.connect(self.pause_resume_audio)
        stop_audio_btn = self.register_general_button(QPushButton("■ Stop"), "■")
        stop_audio_btn.setObjectName("SecondaryButton")
        stop_audio_btn.clicked.connect(self.stop_audio)
        rewind_audio_btn = self.register_general_button(QPushButton("⏪ Restart"), "⏪")
        rewind_audio_btn.setObjectName("SecondaryButton")
        rewind_audio_btn.clicked.connect(self.rewind_audio)
        self.speech_export_format = WheelSafeComboBox()
        for label, fmt in [
            ("Subtitles (.srt)", "srt"),
            ("Subtitles (.vtt)", "vtt"),
            ("DOCX (.docx)", "docx"),
            ("PDF (.pdf)", "pdf"),
            ("Text (.txt)", "txt"),
        ]:
            self.speech_export_format.addItem(label, fmt)
        self.speech_export_format = self.make_responsive_combo(self.speech_export_format)

        export_speech_btn = QPushButton("⤓ Export")
        export_speech_btn.setObjectName("SecondaryButton")
        export_speech_btn.clicked.connect(self.do_speech_export)
        save_note_btn = self.register_general_button(QPushButton("Save Note"), "Save")
        save_note_btn.setObjectName("SecondaryButton")
        save_note_btn.clicked.connect(self.save_speech_as_note)

        correction_label = QLabel("CORRECTION")
        correction_label.setObjectName("SectionLabel")
        action_row.addWidget(correction_label)
        correction_row = QHBoxLayout()
        correction_row.setSpacing(8)
        for btn in [correct_btn, smart_fix_btn]:
            correction_row.addWidget(btn)
        action_row.addLayout(correction_row)

        playback_label = QLabel("PLAYBACK")
        playback_label.setObjectName("SectionLabel")
        action_row.addWidget(playback_label)
        playback_row = QHBoxLayout()
        playback_row.setSpacing(8)
        for btn in [read_transcript_btn, read_translation_btn, pause_audio_btn, stop_audio_btn, rewind_audio_btn]:
            playback_row.addWidget(btn)
        action_row.addLayout(playback_row)

        export_label = QLabel("EXPORT")
        export_label.setObjectName("SectionLabel")
        action_row.addWidget(export_label)
        export_row = QHBoxLayout()
        export_row.setSpacing(8)
        export_row.addWidget(self.speech_export_format)
        export_row.addWidget(export_speech_btn)
        export_row.addWidget(save_note_btn)
        action_row.addLayout(export_row)
        layout.addWidget(action_host)

        results = QGridLayout()
        results.setContentsMargins(0, 0, 0, 0)
        results.setHorizontalSpacing(10)
        results.setVerticalSpacing(0)
        speech_transcript_label = QLabel("LIVE TRANSCRIPT  /  SOURCE")
        speech_transcript_label.setObjectName("SignalPaneLabel")
        speech_translation_label = QLabel("LIVE TRANSLATION  /  TARGET")
        speech_translation_label.setObjectName("SignalPaneLabel")
        results.addWidget(speech_transcript_label, 0, 0)
        results.addWidget(speech_translation_label, 0, 1)
        self.speech_transcript = self.make_responsive_text_edit(QTextEdit())
        self.speech_transcript.setObjectName("SignalTranscript")
        self.speech_transcript.setPlaceholderText("Live transcript appears here automatically while recording...")
        self.speech_translation = self.make_responsive_text_edit(QTextEdit())
        self.speech_translation.setObjectName("SignalTranslation")
        self.speech_translation.setReadOnly(True)
        self.speech_translation.setPlaceholderText("Translated transcript will appear here...")
        results.addWidget(self.speech_transcript, 1, 0)
        results.addWidget(self.speech_translation, 1, 1)
        results.setColumnStretch(0, 1)
        results.setColumnStretch(1, 1)
        results.setRowStretch(1, 1)
        layout.addLayout(results, 1)
        return page

    def set_speech_stage(self, stage: str, message: str = "", error: bool = False):
        stages = ["listening", "processing", "translating", "complete"]
        active_index = stages.index(stage) if stage in stages else -1
        for index, stage_id in enumerate(stages):
            label = getattr(self, "speech_stage_labels", {}).get(stage_id)
            if label is None:
                continue
            state = "active" if index == active_index else "complete" if active_index >= 0 and index < active_index else "idle"
            label.setProperty("stageState", state)
            label.style().unpolish(label)
            label.style().polish(label)

        recorder = getattr(self, "speech_recorder_card", None)
        if recorder is not None:
            recorder.setProperty("speechState", "error" if error else stage or "idle")
            recorder.style().unpolish(recorder)
            recorder.style().polish(recorder)

        status = getattr(self, "speech_status_label", None)
        if status is not None and message:
            status.setText(message)
            status.setProperty("statusType", "error" if error else "success" if stage == "complete" else "")
            status.style().unpolish(status)
            status.style().polish(status)

        recording = stage == "listening" and getattr(self, "speech_is_recording", False)
        record_button = getattr(self, "speech_record_button", None)
        if record_button is not None:
            record_button.setProperty("recording", recording)
            record_button.setEnabled(not recording and stage not in {"processing", "translating"})
            record_button.setText("● Listening" if recording else "● Record")
            record_button.style().unpolish(record_button)
            record_button.style().polish(record_button)
        pause_button = getattr(self, "speech_pause_button", None)
        stop_button = getattr(self, "speech_stop_button", None)
        if pause_button is not None:
            pause_button.setEnabled(recording)
        if stop_button is not None:
            stop_button.setEnabled(recording)

    def reveal_speech_text(self, widget: QTextEdit, text: str):
        value = (text or "").strip()
        existing = self._speech_reveal_timers.pop(widget, None)
        if existing is not None:
            existing.stop()
        if not value:
            widget.clear()
            return
        words = value.split()
        if getattr(self, "current_motion", "full") != "full" or len(words) < 6:
            widget.setText(value)
            self.animate_speech_result(widget)
            return

        widget.clear()
        timer = QTimer(widget)
        timer.setInterval(24)
        chunk_size = max(1, math.ceil(len(words) / 45))
        cursor = {"value": 0}

        def reveal_chunk():
            cursor["value"] = min(len(words), cursor["value"] + chunk_size)
            widget.setPlainText(" ".join(words[:cursor["value"]]))
            text_cursor = widget.textCursor()
            text_cursor.movePosition(QTextCursor.End)
            widget.setTextCursor(text_cursor)
            if cursor["value"] >= len(words):
                timer.stop()
                self._speech_reveal_timers.pop(widget, None)
                self.animate_speech_result(widget)

        timer.timeout.connect(reveal_chunk)
        self._speech_reveal_timers[widget] = timer
        timer.start()

    def animate_speech_result(self, widget: QWidget):
        duration = self.motion_duration(340)
        if duration <= 0:
            return
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", widget)
        animation.setDuration(duration)
        animation.setStartValue(0.45)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)

        def clear_effect():
            if widget.graphicsEffect() is effect:
                widget.setGraphicsEffect(None)

        animation.finished.connect(clear_effect)
        widget._speech_reveal_animation = animation
        animation.start(QPropertyAnimation.DeleteWhenStopped)

    def load_corrections_from_backend(self):
        def task():
            try:
                return requests.get(f"{SERVER_URL}/corrections", timeout=10).json()
            except Exception:
                return {"ok": False, "corrections": {}}

        def success(data):
            if data.get("ok"):
                self.corrections = data.get("corrections", {}) or {}

        self.run_background(task, success)

    def load_smart_provider_status(self):
        def task():
            try:
                return requests.get(f"{SERVER_URL}/corrections/providers", timeout=10).json()
            except Exception as exc:
                return {"ok": False, "error": str(exc), "providers": {}}

        def success(data):
            self.smart_provider_status = data.get("providers", {}) if data.get("ok") else {}

        self.run_background(task, success)

    def current_smart_mode(self, for_live: bool = False) -> str:
        if for_live:
            # Keep live snapshots cheap and fast. Online semantic correction runs on final/import or selection.
            return "offline"
        if hasattr(self, "speech_smart_correction") and self.speech_smart_correction.isChecked():
            return self.speech_correction_mode.currentData() or self.ai_provider_config.get("default_mode", "free_auto")
        return "offline"

    def selected_text_widget(self):
        widget = QApplication.focusWidget()
        if isinstance(widget, QTextEdit) and widget.textCursor().hasSelection():
            return widget
        for candidate in [
            getattr(self, "speech_transcript", None),
            getattr(self, "speech_translation", None),
            getattr(self, "reader_text", None),
            getattr(self, "translate_output", None),
            getattr(self, "translate_input", None),
        ]:
            if isinstance(candidate, QTextEdit) and candidate.textCursor().hasSelection():
                return candidate
        return None

    def apply_local_corrections(self, text: str) -> str:
        corrected = text or ""
        for wrong, correct in sorted((self.corrections or {}).items(), key=lambda item: len(item[0]), reverse=True):
            if not wrong or not correct:
                continue
            corrected = re.sub(rf"(?<!\w){re.escape(wrong)}(?!\w)", correct, corrected, flags=re.IGNORECASE)
        return corrected.strip()

    def add_manual_correction(self):
        selected_widget = self.selected_text_widget()
        selected = selected_widget.textCursor().selectedText().replace("\u2029", " ").strip() if selected_widget else ""
        wrong, ok = QInputDialog.getText(self, "Add Correction", "Wrong text:", text=selected)
        if not ok or not wrong.strip():
            return
        correct, ok = QInputDialog.getText(self, "Add Correction", "Correct text:")
        if not ok or not correct.strip():
            return

        def task():
            response = requests.post(
                f"{SERVER_URL}/corrections/add",
                data={"wrong": wrong.strip(), "correct": correct.strip()},
                timeout=20,
            )
            return response.json()

        def success(data):
            if not data.get("ok"):
                self.set_status(f"Correction failed: {data.get('error')}", error=True)
                return
            self.corrections = data.get("corrections", {}) or {}
            transcript = self.apply_local_corrections(self.speech_transcript.toPlainText())
            self.speech_transcript.setText(transcript)
            self.last_speech_transcript = transcript
            self.set_status(f"Learned correction: {wrong.strip()} → {correct.strip()}")
            QMessageBox.information(self, "Correction saved", f"LinguaFusion will now replace:\n\n{wrong.strip()} → {correct.strip()}")

        self.run_background(task, success)

    def smart_fix_selection(self):
        widget = self.selected_text_widget()
        if not widget:
            self.set_status("Select text first, then use Smart Fix Selection", error=True)
            return

        selected = widget.textCursor().selectedText().replace("\u2029", " ").strip()
        if not selected:
            self.set_status("No selected text", error=True)
            return

        mode = self.speech_correction_mode.currentData() if hasattr(self, "speech_correction_mode") else "free_auto"
        if mode == "offline":
            mode = "free_auto"

        if mode not in {"offline", "languagetool"}:
            confirm = QMessageBox.question(
                self,
                "Online correction",
                f"Send this selected text to the selected free online provider?\n\n{selected[:500]}",
            )
            if confirm != QMessageBox.Yes:
                return

        self.set_status(f"Smart correcting selection with {mode}")

        def task():
            response = requests.post(
                f"{SERVER_URL}/corrections/smart",
                data={"text": selected, "mode": mode, "language": self.speech_language.currentData()},
                timeout=80,
            )
            return response.json()

        def success(data):
            if not data.get("ok"):
                self.set_status(f"Smart correction failed: {data.get('error')}", error=True)
                return

            corrected = (data.get("text") or selected).strip()
            provider = data.get("provider", mode)
            if corrected == selected:
                self.set_status(f"No change suggested by {provider}")
                return

            accept = QMessageBox.question(
                self,
                "Apply smart correction?",
                f"Provider: {provider}\n\nBefore:\n{selected}\n\nAfter:\n{corrected}\n\nApply this change?",
            )
            if accept != QMessageBox.Yes:
                self.set_status("Smart correction ignored")
                return

            cursor = widget.textCursor()
            cursor.insertText(corrected)
            widget.setTextCursor(cursor)

            learn = QMessageBox.question(
                self,
                "Learn correction?",
                "Save this selected correction to offline memory for future transcripts?",
            )
            if learn == QMessageBox.Yes:
                self.save_learned_correction(selected, corrected)
            else:
                self.set_status(f"Applied smart correction from {provider}")

        self.run_background(task, success)

    def save_learned_correction(self, wrong: str, correct: str):
        def task():
            response = requests.post(
                f"{SERVER_URL}/corrections/add",
                data={"wrong": wrong.strip(), "correct": correct.strip()},
                timeout=20,
            )
            return response.json()

        def success(data):
            if data.get("ok"):
                self.corrections = data.get("corrections", {}) or {}
                self.set_status("Smart correction learned offline")
            else:
                self.set_status(f"Learning failed: {data.get('error')}", error=True)

        self.run_background(task, success)

    def maybe_live_translate_speech(self, transcript: str):
        if not hasattr(self, "speech_live_translation") or not self.speech_live_translation.isChecked():
            if not self.speech_is_recording:
                self.set_speech_stage("complete", "Transcript complete.")
            return
        if not transcript or transcript in {"Transcribing...", "Listening... live transcription will update every few seconds."}:
            return
        if not self.speech_is_recording:
            self.set_speech_stage("translating", "Transcript ready. Translating on the PC...")

        def task():
            response = requests.post(
                f"{SERVER_URL}/reader/translate",
                data={
                    "text": transcript,
                    "source_lang": self.speech_language.currentData(),
                    "target_lang": self.speech_target_language.currentData(),
                },
                timeout=180,
            )
            return response.json()

        def success(data):
            if not data.get("ok"):
                if not self.speech_is_recording:
                    self.set_speech_stage("complete", "Transcript complete; translation was unavailable.")
                return
            translation = data["translation"]
            formatted = self.format_translation_output(translation)
            self.last_speech_translation = translation.get("translated_text", "")
            self.reveal_speech_text(self.speech_translation, formatted)
            if self.speech_is_recording:
                self.set_speech_stage("listening", "Listening... live transcript and translation are updating.")
            else:
                self.set_speech_stage("complete", "Transcript and translation complete.")

        self.run_background(task, success)

    def write_speech_frames_to_temp_wav(self, frames, prefix: str = "speech_snapshot") -> str:
        if not frames:
            raise RuntimeError("No audio frames available.")
        audio = np.concatenate(frames, axis=0)
        out_path = Path(f"{prefix}_{uuid4().hex}.wav").resolve()
        sf.write(str(out_path), audio, self.speech_sample_rate)
        self.generated_audio_files.append(str(out_path))
        return str(out_path)

    def live_transcribe_speech_snapshot(self):
        if not self.speech_is_recording or self.speech_is_paused or self.speech_live_transcribing:
            return
        if len(self.speech_frames) < 25:
            return
        if len(self.speech_frames) == self.speech_last_live_frame_count:
            return

        frames_snapshot = [frame.copy() for frame in self.speech_frames]
        self.speech_last_live_frame_count = len(frames_snapshot)
        self.speech_live_transcribing = True
        self.set_speech_stage("listening", "Listening... updating the live transcript in the background.")

        def task():
            wav_path = self.write_speech_frames_to_temp_wav(frames_snapshot, "speech_live")
            with open(wav_path, "rb") as audio_file:
                response = requests.post(
                    f"{SERVER_URL}/stt/transcribe",
                    files={"file": audio_file},
                    data={"language": self.speech_language.currentData(), "smart_mode": self.current_smart_mode(for_live=True)},
                    timeout=600,
                )
            return response.json()

        def success(data):
            self.speech_live_transcribing = False
            if not data.get("ok"):
                self.set_speech_stage("listening", "Listening... live transcription is not available yet.")
                return
            transcript = self.apply_local_corrections(data.get("text", "").strip())
            if transcript:
                self.last_speech_transcript = transcript
                self.reveal_speech_text(self.speech_transcript, transcript)
                self.maybe_live_translate_speech(transcript)
                self.set_speech_stage("listening", "Listening... live transcript is updating.")

        self.run_background(task, success)

    def update_speech_recording_ui(self):
        if self.speech_is_recording and not self.speech_is_paused and self.speech_recording_started_at:
            elapsed = self.speech_elapsed_when_paused + (time.time() - self.speech_recording_started_at)
        else:
            elapsed = self.speech_elapsed_when_paused
        total_seconds = int(max(0, elapsed))
        if hasattr(self, "speech_timer_label"):
            self.speech_timer_label.setText(f"{total_seconds // 60:02d}:{total_seconds % 60:02d}")
        if hasattr(self, "speech_waveform"):
            levels = self.speech_levels[-160:]
            if levels:
                # Absolute RMS scaling preserves the difference between room
                # noise and real speech instead of normalizing silence to 100%.
                self.speech_waveform.peaks = [
                    max(0.035, min(1.0, (value - 0.0025) / 0.075))
                    for value in levels
                ]
                self.speech_waveform.set_progress(1.0 if self.speech_is_recording else 0.0)

    def start_speech_recording(self):
        if self.speech_is_recording:
            self.set_status("Recording already active")
            return
        self.stop_audio()
        self.speech_frames = []
        self.speech_levels = []
        self.speech_current_wav_path = None
        self.speech_live_transcribing = False
        self.speech_last_live_frame_count = 0
        self.last_speech_transcript = ""
        self.last_speech_translation = ""
        self.last_speech_language = "auto"
        self.speech_is_recording = True
        self.speech_is_paused = False
        self.speech_elapsed_when_paused = 0.0
        self.speech_recording_started_at = time.time()
        if hasattr(self, "speech_transcript"):
            self.speech_transcript.setText("Listening... live transcription will update every few seconds.")
        if hasattr(self, "speech_translation"):
            self.speech_translation.setText("")

        def callback(indata, frames, time_info, status):
            if status:
                pass
            if self.speech_is_recording and not self.speech_is_paused:
                block = indata.copy()
                self.speech_frames.append(block)
                try:
                    self.speech_levels.append(float(np.sqrt(np.mean(block ** 2))))
                except Exception:
                    self.speech_levels.append(0.0)

        try:
            self.speech_stream = sd.InputStream(
                samplerate=self.speech_sample_rate,
                channels=self.speech_channels,
                dtype="float32",
                callback=callback,
            )
            self.speech_stream.start()
            self.speech_timer.start()
            self.speech_live_timer.start()
            self.set_speech_stage("listening", "Listening... speak naturally. Live transcription is automatic.")
            self.set_status("Recording")
        except Exception as exc:
            self.speech_is_recording = False
            self.speech_is_paused = False
            self.set_speech_stage("", "Microphone error.", error=True)
            self.set_status(f"Microphone error: {exc}", error=True)

    def pause_resume_speech_recording(self):
        if not self.speech_is_recording:
            self.set_status("No active recording to pause", error=True)
            return
        if self.speech_is_paused:
            self.speech_is_paused = False
            self.speech_recording_started_at = time.time()
            self.speech_live_timer.start()
            self.set_speech_stage("listening", "Listening resumed... live transcription is active.")
            self.set_status("Recording resumed")
        else:
            if self.speech_recording_started_at:
                self.speech_elapsed_when_paused += time.time() - self.speech_recording_started_at
            self.speech_recording_started_at = None
            self.speech_is_paused = True
            self.speech_live_timer.stop()
            self.set_speech_stage("listening", "Recording paused. Resume when you are ready.")
            self.set_status("Recording paused")
        self.update_speech_recording_ui()

    def stop_speech_recording(self):
        if not self.speech_is_recording:
            self.set_status("No active recording")
            return
        if not self.speech_is_paused and self.speech_recording_started_at:
            self.speech_elapsed_when_paused += time.time() - self.speech_recording_started_at
        self.speech_recording_started_at = None
        self.speech_is_recording = False
        self.speech_is_paused = False
        self.speech_timer.stop()
        self.speech_live_timer.stop()
        try:
            if self.speech_stream:
                self.speech_stream.stop()
                self.speech_stream.close()
        except Exception:
            pass
        self.speech_stream = None

        if not self.speech_frames:
            self.set_speech_stage("", "No audio captured.", error=True)
            self.set_status("No audio captured", error=True)
            return

        out_path = self.write_speech_frames_to_temp_wav(self.speech_frames, "speech_recording")
        self.speech_current_wav_path = out_path
        self.set_speech_stage("processing", f"Recording saved. Processing {Path(out_path).name} on the PC...")
        self.speech_waveform.load_audio(out_path)
        self.set_status("Recording stopped; transcribing automatically")
        self.transcribe_speech_audio(auto=True)

    def import_speech_audio(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open audio file",
            "",
            "Audio Files (*.wav *.mp3 *.m4a *.ogg *.flac *.aac *.wma);;All Files (*.*)",
        )
        if path:
            self.import_speech_audio_path(path)

    def import_speech_audio_path(self, path: str):
        if not path:
            return
        suffix = Path(path).suffix.lower()
        if suffix not in AUDIO_EXTENSIONS:
            self.set_status(f"Unsupported audio file: {suffix}", error=True)
            return
        self.switch_page("Speech")
        self.speech_current_wav_path = str(Path(path).resolve())
        self.speech_waveform.load_audio(self.speech_current_wav_path)
        try:
            duration = len(AudioSegment.from_file(self.speech_current_wav_path))
            self.speech_timer_label.setText(self.format_ms(duration))
        except Exception:
            pass
        self.set_speech_stage("processing", f"Loaded {Path(path).name}. Processing speech on the PC...")
        self.add_recent("Speech", Path(path).name, "🎙")
        self.set_status("Audio loaded by drag/drop; transcribing automatically")
        self.transcribe_speech_audio(auto=True)

    def full_song_pass(self):
        if self.speech_is_recording:
            self.stop_speech_recording()
            return

        if not self.speech_current_wav_path:
            self.set_status("No song/audio loaded for Full Song Pass", error=True)
            return

        self.set_speech_stage("processing", "Running Full Song Pass: full-file Whisper and provider comparison...")
        self.set_status("Full Song Pass running")
        self.speech_transcript.setText("Full Song Pass running... this may take longer than live STT.")

        def task():
            with open(self.speech_current_wav_path, "rb") as audio_file:
                response = requests.post(
                    f"{SERVER_URL}/stt/full-song-pass",
                    files={"file": audio_file},
                    data={
                        "language": self.speech_language.currentData(),
                        "smart_mode": self.speech_correction_mode.currentData() if hasattr(self, "speech_correction_mode") else "free_auto",
                    },
                    timeout=900,
                )
            return response.json()

        def success(data):
            if not data.get("ok"):
                self.speech_transcript.setText(str(data))
                self.set_speech_stage("", "Full Song Pass failed.", error=True)
                self.set_status("Full Song Pass failed", error=True)
                return

            transcript = data.get("text", "").strip()
            self.last_speech_transcript = transcript
            self.last_speech_language = data.get("language", self.speech_language.currentData()) or "auto"
            self.reveal_speech_text(self.speech_transcript, transcript)
            provider = data.get("provider", "offline")
            candidates = data.get("candidates", []) or []
            engine = data.get("engine", "speech_engine_v2")
            best_score = "—"
            for candidate in candidates:
                if candidate.get("provider") == provider and candidate.get("score") is not None:
                    best_score = str(round(float(candidate.get("score", 0)), 1))
                    break
            self.set_speech_stage(
                "complete",
                f"Full Song Pass ready: selected {provider} from {len(candidates)} candidates · {engine} · score {best_score}",
            )
            self.set_status(f"Full Song Pass complete: {provider}")
            self.add_recent("Speech", "Full Song Pass", "🎵")

            if hasattr(self, "speech_live_translation") and self.speech_live_translation.isChecked():
                self.translate_speech_transcript()

        self.run_background(task, success)


    def reference_lyrics_pass(self):
        if self.speech_is_recording:
            self.stop_speech_recording()
            return

        if not self.speech_current_wav_path:
            self.set_status("No song/audio loaded for Reference Lyrics", error=True)
            return

        reference, ok = QInputDialog.getMultiLineText(
            self,
            "Reference Lyrics",
            "Paste the reference lyrics here. LinguaFusion will not fetch lyrics automatically.",
            "",
        )
        if not ok or not reference.strip():
            self.set_status("Reference lyrics cancelled")
            return

        self.set_speech_stage("processing", "Running Reference Lyrics Pass...")
        self.set_status("Reference Lyrics Pass running")
        self.speech_transcript.setText("Reference Lyrics Pass running...")

        def task():
            with open(self.speech_current_wav_path, "rb") as audio_file:
                response = requests.post(
                    f"{SERVER_URL}/stt/reference-lyrics-pass",
                    files={"file": audio_file},
                    data={
                        "reference_lyrics": reference,
                        "language": self.speech_language.currentData(),
                        "smart_mode": self.speech_correction_mode.currentData() if hasattr(self, "speech_correction_mode") else "free_auto",
                    },
                    timeout=900,
                )
            return response.json()

        def success(data):
            if not data.get("ok"):
                self.speech_transcript.setText(str(data))
                self.set_speech_stage("", "Reference Lyrics Pass failed.", error=True)
                self.set_status("Reference Lyrics Pass failed", error=True)
                return

            transcript = data.get("text", "").strip()
            self.last_speech_transcript = transcript
            self.last_speech_language = data.get("language", "en") or "en"
            self.reveal_speech_text(self.speech_transcript, transcript)
            provider = data.get("provider", "reference_lyrics")
            accepted = data.get("reference_accepted", False)
            similarity = data.get("reference_similarity", "—")
            status = "accepted" if accepted else "not accepted"
            self.set_speech_stage(
                "complete",
                f"Reference Lyrics Pass ready: {status} · similarity {similarity} · {provider}",
            )
            self.set_status(f"Reference Lyrics Pass complete: {status}")
            self.add_recent("Speech", "Reference Lyrics Pass", "📄")

            if hasattr(self, "speech_live_translation") and self.speech_live_translation.isChecked():
                self.translate_speech_transcript()

        self.run_background(task, success)

    def transcribe_speech_audio(self, auto: bool = False):
        if self.speech_is_recording:
            self.stop_speech_recording()
            return
        if not self.speech_current_wav_path:
            self.set_status("No speech audio available", error=True)
            return
        if not auto or not self.last_speech_transcript:
            self.speech_transcript.setText("Transcribing...")
        self.set_speech_stage("processing", "Processing speech on the PC GPU...")
        self.set_status("Transcribing speech")

        def task():
            print("[DEBUG] transcribe task: starting request")
            with open(self.speech_current_wav_path, "rb") as audio_file:
                response = requests.post(
                    f"{SERVER_URL}/stt/transcribe",
                    files={"file": audio_file},
                    data={"language": self.speech_language.currentData(), "smart_mode": self.current_smart_mode(for_live=False)},
                    timeout=600,
                )
            print(f"[DEBUG] transcribe task: got response, status={response.status_code}")
            return response.json()

        def success(data):
            print(f"[DEBUG] transcribe success: data.ok={data.get('ok')}")
            if not data.get("ok"):
                self.speech_transcript.setText(str(data))
                self.set_speech_stage("", "Transcription failed.", error=True)
                self.set_status("Transcription failed", error=True)
                return
            transcript = self.apply_local_corrections(data.get("text", "").strip())
            self.last_speech_transcript = transcript
            self.last_speech_language = data.get("language", self.speech_language.currentData()) or "auto"
            self.reveal_speech_text(self.speech_transcript, transcript)
            self.maybe_live_translate_speech(transcript)
            self.add_recent("Speech", "Transcript", "🎙")
            provider = data.get("provider", "offline")
            engine = data.get("engine", "speech_engine_v2")
            if not self.speech_live_translation.isChecked():
                self.set_speech_stage("complete", f"Transcript complete: {self.last_speech_language} · {provider} · {engine}")
            self.set_status("Transcription complete")

        self.run_background(task, success)

    def translate_speech_transcript(self, auto_read: bool = False):
        transcript = self.speech_transcript.toPlainText().strip()
        if not transcript or transcript in {"Transcribing...", "Full Song Pass running... this may take longer than live STT."}:
            self.set_status("No transcript to translate", error=True)
            return

        # For music/full-song pass, the UI source may still be Auto. Use the detected language when available.
        source_lang = getattr(self, "last_speech_language", "auto") or self.speech_language.currentData()
        if source_lang == "auto":
            # Lyrics/songs tested so far are English; reader/translate works better with an explicit source.
            source_lang = "en"

        self.speech_translation.setText("Translating transcript...")
        self.set_speech_stage("translating", "Translating the transcript on the PC...")
        self.set_status("Translating transcript")

        def task():
            response = requests.post(
                f"{SERVER_URL}/reader/translate",
                data={
                    "text": transcript,
                    "source_lang": source_lang,
                    "target_lang": self.speech_target_language.currentData(),
                },
                timeout=180,
            )
            return response.json()

        def success(data):
            translation = data.get("translation", {}) if isinstance(data, dict) else {}
            if not data.get("ok") or not translation.get("ok", False):
                error = translation.get("error") or data.get("error") or "Translation engine rejected this transcript."
                fallback = translation.get("translated_text", "") or ""
                message = f"Translation unavailable: {error}"
                if fallback:
                    message += "\n\nBest partial output:\n" + fallback
                self.speech_translation.setText(message)
                self.set_speech_stage("complete", "Transcript complete; translation was unavailable.")
                self.set_status("Transcript translation failed", error=True)
                return

            formatted = self.format_translation_output(translation)
            self.last_speech_translation = translation.get("translated_text", "")
            self.reveal_speech_text(self.speech_translation, formatted)
            self.set_speech_stage("complete", "Transcript and translation complete.")
            self.set_status("Transcript translated")
            if auto_read:
                self.read_speech_translation()

        self.run_background(task, success)

    def generate_speech_audio_from_text(self, text: str, lang: str, status_label: str):
        if not text or text in {"Transcribing...", "Translating transcript..."}:
            self.set_status("No speech text to read", error=True)
            return
        if lang == "auto":
            lang = "en"
        self.active_audio_context = "Reader"
        self.set_status(status_label)

        def task():
            response = requests.post(
                f"{SERVER_URL}/reader/speak",
                data={"text": text[:5000], "lang": lang, "speed": "1.0"},
                timeout=240,
            )
            if response.status_code != 200:
                raise RuntimeError(response.text)
            out_path = Path(f"speech_tts_{uuid4().hex}.wav").resolve()
            with open(out_path, "wb") as audio_file:
                audio_file.write(response.content)
            return str(out_path)

        def success(path):
            self.generated_audio_files.append(path)
            self.play_audio_file(path)
            self.reader_playback_status = "Playing"
            self.set_status("Playing speech audio")

        self.run_background(task, success)

    def read_speech_transcript(self):
        text = self.speech_transcript.toPlainText().strip()
        self.generate_speech_audio_from_text(text, self.speech_language.currentData(), "Generating transcript audio")

    def read_speech_translation(self):
        text = (self.last_speech_translation or self.speech_translation.toPlainText()).strip()
        if not text or text == "Translating transcript...":
            self.translate_speech_transcript(auto_read=True)
            return
        self.generate_speech_audio_from_text(text, self.speech_target_language.currentData(), "Generating translation audio")

    def speech_export_text(self) -> str:
        transcript = self.speech_transcript.toPlainText().strip()
        translation = self.speech_translation.toPlainText().strip()
        parts = []
        if transcript and transcript != "Transcribing...":
            parts.append("Transcript\n----------\n" + transcript)
        if translation and translation != "Translating transcript...":
            parts.append("Translation\n----------\n" + translation)
        return "\n\n".join(parts).strip()

    def export_speech_text(self, file_type: str):
        text = self.speech_export_text()
        if not text:
            self.set_status("No speech text to export", error=True)
            return
        filters = {
            "txt": "Text File (*.txt)",
            "docx": "Word Document (*.docx)",
            "pdf": "PDF File (*.pdf)",
        }
        path, _ = QFileDialog.getSaveFileName(self, "Export speech text", f"speech_export.{file_type}", filters[file_type])
        if not path:
            return
        try:
            if file_type == "txt":
                Path(path).write_text(text, encoding="utf-8")
            elif file_type == "docx":
                from docx import Document
                doc = Document()
                doc.add_heading("LinguaFusion Speech Export", level=1)
                for paragraph in text.split("\n"):
                    doc.add_paragraph(paragraph)
                doc.save(path)
            elif file_type == "pdf":
                from backend.services.complex_script_pdf_service import write_unicode_pdf
                write_unicode_pdf(text, "LinguaFusion Speech Export", path)
            self.set_status(f"Speech export saved: {Path(path).name}")
        except Exception as exc:
            self.set_status(f"Export failed: {exc}", error=True)

    def export_speech_subtitles(self, file_type: str):
        transcript = self.speech_transcript.toPlainText().strip()
        if not transcript or transcript == "Transcribing...":
            self.set_status("No speech transcript to export", error=True)
            return
        filter_str = "SubRip Subtitles (*.srt)" if file_type == "srt" else "WebVTT Subtitles (*.vtt)"
        path, _ = QFileDialog.getSaveFileName(self, f"Export {file_type.upper()} subtitles", f"speech_subtitles.{file_type}", filter_str)
        if not path:
            return
        try:
            segments = getattr(self, "last_speech_segments", None) or []
            if not segments:
                segments = [{"start": 0.0, "end": 5.0, "text": transcript}]
            response = requests.post(
                f"{SERVER_URL}/speech/export_subtitles",
                data={"segments_json": json.dumps(segments), "format_type": file_type},
                timeout=120,
            )
            if response.status_code != 200:
                raise RuntimeError(response.text)
            Path(path).write_bytes(response.content)
            self.set_status(f"Exported subtitles: {Path(path).name}")
        except Exception as exc:
            self.set_status(f"Export failed: {exc}", error=True)

    def export_ocr_text(self, file_type: str):
        extracted = self.ocr_text.toPlainText().strip()
        translated = self.ocr_translated_text.toPlainText().strip()
        parts = []
        if extracted and extracted != "Extracting OCR text...":
            parts.append("Extracted OCR Text\n------------------\n" + extracted)
        if translated and translated != "Translating...":
            parts.append("OCR Translation\n---------------\n" + translated)
        text = "\n\n".join(parts).strip()
        if not text:
            self.set_status("No OCR text to export", error=True)
            return
        filters = {"txt": "Text File (*.txt)", "docx": "Word Document (*.docx)", "pdf": "PDF File (*.pdf)"}
        path, _ = QFileDialog.getSaveFileName(self, "Export OCR text", f"ocr_export.{file_type}", filters[file_type])
        if not path:
            return
        try:
            response = requests.post(
                f"{SERVER_URL}/document/export",
                data={"text": text, "format_type": file_type, "title": "LinguaFusion OCR Export"},
                timeout=120,
            )
            if response.status_code != 200:
                raise RuntimeError(response.text)
            Path(path).write_bytes(response.content)
            self.set_status(f"Exported OCR text: {Path(path).name}")
        except Exception as exc:
            self.set_status(f"Export failed: {exc}", error=True)

    def save_speech_transcript(self):
        self.export_speech_text("txt")

    def save_speech_as_note(self):
        text = self.speech_export_text()
        if not text:
            self.set_status("No speech text to save", error=True)
            return
        def task():
            response = requests.post(
                f"{SERVER_URL}/notes/create",
                data={"title": "Speech note", "content": text, "language": self.speech_language.currentData()},
                timeout=30,
            )
            return response.json()
        def success(data):
            self.add_recent("Notes", data.get("title", "Speech note"), "📝")
            self.set_status("Speech saved as note")
        self.run_background(task, success)

    # ---------- Settings ----------
    def build_settings_page(self):
        page = QWidget()
        page.setObjectName("SignalSettingsPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(self.page_title("SETTINGS / LOCAL CONFIGURATION", "Appearance, models, audio, privacy, storage, and GPU safety"))

        settings_index = QFrame()
        settings_index.setObjectName("SignalFunctionStrip")
        settings_index_layout = QHBoxLayout(settings_index)
        settings_index_layout.setContentsMargins(8, 6, 8, 6)
        for section in ("APPEARANCE", "MODELS", "AUDIO", "TRANSLATION", "OCR", "PRIVACY", "STORAGE", "ADVANCED"):
            label = QLabel(section)
            label.setObjectName("SignalMetaLine")
            settings_index_layout.addWidget(label)
        settings_index_layout.addStretch(1)
        layout.addWidget(settings_index)

        # Startup & System Tray Card
        startup_card = Card("Card")
        startup_card.setObjectName("SignalSettingsCard")
        startup_layout = QVBoxLayout(startup_card)
        startup_layout.setContentsMargins(18, 16, 18, 16)
        startup_layout.setSpacing(10)

        startup_title = QLabel("WINDOWS STARTUP & BACKGROUND SYSTEM TRAY")
        startup_title.setObjectName("CardTitle")
        startup_layout.addWidget(startup_title)

        startup_desc = QLabel(
            "Configure LinguaFusion to start automatically at PC boot and run continuously in the Windows System Tray."
        )
        startup_desc.setObjectName("Muted")
        startup_desc.setWordWrap(True)
        startup_layout.addWidget(startup_desc)

        self.autostart_checkbox = QCheckBox("Start LinguaFusion automatically when Windows boots up")
        self.autostart_checkbox.setChecked(is_autostart_enabled())
        self.autostart_checkbox.toggled.connect(self.toggle_autostart_setting)
        startup_layout.addWidget(self.autostart_checkbox)

        self.tray_checkbox = QCheckBox("Minimize to System Tray on close (keeps background backend & tunnel active)")
        self.tray_checkbox.setChecked(self.app_settings.value("system/minimize_to_tray", True, type=bool))
        self.tray_checkbox.toggled.connect(lambda checked: self.app_settings.setValue("system/minimize_to_tray", checked))
        startup_layout.addWidget(self.tray_checkbox)

        layout.addWidget(startup_card)

        appearance_card = Card("Card")
        appearance_card.setObjectName("SignalSettingsCard")
        appearance_layout = QVBoxLayout(appearance_card)
        appearance_layout.setContentsMargins(18, 16, 18, 16)
        appearance_layout.setSpacing(12)
        appearance_title = QLabel("Appearance")
        appearance_title.setObjectName("CardTitle")
        appearance_layout.addWidget(appearance_title)
        appearance_description = QLabel(
            "Choose one of nine PC-optimized looks, then choose the workspace font independently. "
            "Changing the look keeps your font choice, and changing the font keeps your look. "
            "Motion can be reduced or disabled without changing either."
        )
        appearance_description.setObjectName("Muted")
        appearance_description.setWordWrap(True)
        appearance_layout.addWidget(appearance_description)

        theme_row = QHBoxLayout()
        theme_row.setSpacing(12)
        combo_label = QLabel("PC look:")
        combo_label.setObjectName("PaneTitle")
        theme_row.addWidget(combo_label)

        self.theme_combo = WheelSafeComboBox()
        self.theme_combo.setMinimumHeight(38)
        self.theme_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        groups = {}
        for tid in self.DESKTOP_THEME_IDS:
            tspec = self.DESKTOP_THEME_SPECS[tid]
            grp = tspec.get("group", "Light")
            groups.setdefault(grp, []).append((tid, tspec))

        for grp_name, items in groups.items():
            for tid, tspec in items:
                self.theme_combo.addItem(f"[{grp_name}] {tspec['name']}", userData=tid)

        curr_idx = self.theme_combo.findData(getattr(self, "current_theme", "broadsheet"))
        if curr_idx >= 0:
            self.theme_combo.setCurrentIndex(curr_idx)

        self.theme_combo.currentIndexChanged.connect(
            lambda idx: self.set_theme(self.theme_combo.itemData(idx))
        )
        theme_row.addWidget(self.theme_combo, 1)
        appearance_layout.addLayout(theme_row)

        curr_spec = self.DESKTOP_THEME_SPECS.get(getattr(self, "current_theme", "broadsheet"), self.DESKTOP_THEME_SPECS["broadsheet"])
        self.theme_status_label = QLabel(f"Active Look: {curr_spec['name']}")
        self.theme_status_label.setObjectName("Muted")
        appearance_layout.addWidget(self.theme_status_label)

        font_row = QHBoxLayout()
        font_row.setSpacing(12)
        font_label = QLabel("Font:")
        font_label.setObjectName("PaneTitle")
        font_row.addWidget(font_label)

        self.font_combo = WheelSafeComboBox()
        self.font_combo.setMinimumHeight(38)
        self.font_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        for font_id, font_spec in self.DESKTOP_FONT_SPECS.items():
            self.font_combo.addItem(
                f"[{font_spec['group']}] {font_spec['name']}",
                userData=font_id,
            )
        font_index = self.font_combo.findData(getattr(self, "current_font", "modern"))
        if font_index >= 0:
            self.font_combo.setCurrentIndex(font_index)
        self.font_combo.currentIndexChanged.connect(
            lambda idx: self.set_font(self.font_combo.itemData(idx))
        )
        font_row.addWidget(self.font_combo, 1)
        appearance_layout.addLayout(font_row)

        active_font = self.DESKTOP_FONT_SPECS.get(
            getattr(self, "current_font", "modern"),
            self.DESKTOP_FONT_SPECS["modern"],
        )
        self.font_status_label = QLabel(f"Active Font: {active_font['name']}")
        self.font_status_label.setObjectName("Muted")
        appearance_layout.addWidget(self.font_status_label)

        motion_row = QHBoxLayout()
        motion_row.setSpacing(12)
        motion_label = QLabel("Motion:")
        motion_label.setObjectName("PaneTitle")
        motion_row.addWidget(motion_label)
        self.motion_combo = WheelSafeComboBox()
        self.motion_combo.setMinimumHeight(38)
        self.motion_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.motion_combo.addItem("Full motion", "full")
        self.motion_combo.addItem("Reduced motion", "reduced")
        self.motion_combo.addItem("Motion off", "off")
        motion_index = self.motion_combo.findData(getattr(self, "current_motion", "full"))
        if motion_index >= 0:
            self.motion_combo.setCurrentIndex(motion_index)
        self.motion_combo.currentIndexChanged.connect(
            lambda idx: self.set_motion(self.motion_combo.itemData(idx))
        )
        motion_row.addWidget(self.motion_combo, 1)
        appearance_layout.addLayout(motion_row)

        motion_names = {"full": "Full motion", "reduced": "Reduced motion", "off": "Motion off"}
        self.motion_status_label = QLabel(
            f"Active Motion: {motion_names.get(getattr(self, 'current_motion', 'full'), 'Full motion')}"
        )
        self.motion_status_label.setObjectName("Muted")
        appearance_layout.addWidget(self.motion_status_label)
        layout.addWidget(appearance_card)

        gpu_card = Card("Card")
        gpu_card.setObjectName("SignalSettingsCard")
        gpu_layout = QVBoxLayout(gpu_card)
        gpu_layout.setContentsMargins(18, 14, 18, 14)
        gpu_layout.setSpacing(8)
        gpu_title = QLabel("GPU SAFETY / RTX 2080 Ti")
        gpu_title.setObjectName("CardTitle")
        gpu_layout.addWidget(gpu_title)
        gpu_notice = QLabel(
            "Required before CUDA inference: apply a -500 MHz memory clock offset in MSI Afterburner. "
            "LinguaFusion cannot verify Afterburner automatically; confirm it manually before using "
            "faster-whisper or Ollama on the GPU."
        )
        gpu_notice.setObjectName("SignalGpuSafety")
        gpu_notice.setWordWrap(True)
        gpu_layout.addWidget(gpu_notice)
        gpu_fallback = QLabel("SAFE FALLBACK  •  set LF_WHISPER_DEVICE=cpu")
        gpu_fallback.setObjectName("SignalStatus")
        gpu_layout.addWidget(gpu_fallback)
        layout.addWidget(gpu_card)

        ai_card = Card("Card")
        ai_card.setObjectName("SignalSettingsCard")
        ai_layout = QVBoxLayout(ai_card)
        ai_layout.setContentsMargins(18, 16, 18, 16)
        ai_layout.setSpacing(12)
        ai_title = QLabel("Local AI (Ollama)")
        ai_title.setObjectName("CardTitle")
        ai_layout.addWidget(ai_title)

        ai_desc = QLabel(
            "Speech and OCR correction run automatically through your local Ollama model "
            "when it's running -- nothing to enable, no keys, no internet involved."
        )
        ai_desc.setObjectName("Muted")
        ai_desc.setWordWrap(True)
        ai_layout.addWidget(ai_desc)

        self.ollama_status_label = QLabel("Status: checking...")
        ai_layout.addWidget(self.ollama_status_label)

        ollama_btns = QHBoxLayout()
        ollama_test_btn = QPushButton("Check Ollama Status")
        ollama_test_btn.setObjectName("PrimaryButton")
        ollama_test_btn.clicked.connect(lambda: self.test_ai_provider("ollama"))
        ollama_btns.addWidget(ollama_test_btn)
        ollama_btns.addStretch(1)
        ai_layout.addLayout(ollama_btns)
        layout.addWidget(ai_card)

        QTimer.singleShot(300, self.load_ai_provider_settings)
        return page

    def toggle_autostart_setting(self, checked: bool):
        ok = set_autostart_enabled(checked)
        if ok:
            msg = "LinguaFusion set to start with Windows." if checked else "LinguaFusion removed from Windows startup."
            self.set_status(msg)
        else:
            self.set_status("Could not update Windows startup setting.", error=True)
            if hasattr(self, "autostart_checkbox"):
                self.autostart_checkbox.blockSignals(True)
                self.autostart_checkbox.setChecked(is_autostart_enabled())
                self.autostart_checkbox.blockSignals(False)

    def build_access_page(self):
        page = QWidget()
        page.setObjectName("SignalAccessPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(self.page_title(
            "REMOTE ACCESS / SESSION CONTROL",
            "Pair devices, review exposure, and manage backend permissions."
        ))

        exposure_strip = QFrame()
        exposure_strip.setObjectName("SignalFunctionStrip")
        exposure_row = QHBoxLayout(exposure_strip)
        exposure_row.setContentsMargins(10, 7, 10, 7)
        exposure_row.addWidget(QLabel("SERVICE  BACKEND API"))
        exposure_row.addWidget(QLabel("PAIRING  KEY REQUIRED"))
        exposure_row.addStretch(1)
        exposure_warning = QLabel("⚠ PUBLIC TUNNEL MAY EXPOSE THIS PC BEYOND THE LOCAL SUBNET")
        exposure_warning.setObjectName("SignalGpuSafety")
        exposure_row.addWidget(exposure_warning)
        layout.addWidget(exposure_strip)

        # Card 1: Master Backend Toggle
        master_card = Card("Card")
        master_card.setObjectName("SignalAccessCard")
        master_layout = QVBoxLayout(master_card)
        master_layout.setContentsMargins(18, 16, 18, 16)
        master_layout.setSpacing(12)

        master_title = QLabel("GLOBAL BACKEND SERVER ACCESS")
        master_title.setObjectName("CardTitle")
        master_layout.addWidget(master_title)

        self.access_status_label = QLabel("Status: Checking access state...")
        self.access_status_label.setObjectName("SignalTimer")
        master_layout.addWidget(self.access_status_label)

        self.access_toggle_btn = QPushButton("Toggle Access ON / OFF")
        self.access_toggle_btn.setObjectName("PrimaryButton")
        self.access_toggle_btn.clicked.connect(self.toggle_global_access)
        master_layout.addWidget(self.access_toggle_btn)

        layout.addWidget(master_card)

        # Card 2: Permanent Public Domain (Cloudflare Named Tunnel)
        tunnel_card = Card("Card")
        tunnel_card.setObjectName("SignalAccessCard")
        tunnel_layout = QVBoxLayout(tunnel_card)
        tunnel_layout.setContentsMargins(18, 16, 18, 16)
        tunnel_layout.setSpacing(12)

        tunnel_title = QLabel("PERMANENT PUBLIC DOMAIN (CLOUDFLARE TUNNEL)")
        tunnel_title.setObjectName("CardTitle")
        tunnel_layout.addWidget(tunnel_title)

        tunnel_desc = QLabel(
            "Your permanent domain https://linguafusion.fyi is active 24/7 whenever your PC is powered on. Previously connected mobile devices and web apps will automatically reach this PC without typing new URLs."
        )
        tunnel_desc.setObjectName("Muted")
        tunnel_desc.setWordWrap(True)
        tunnel_layout.addWidget(tunnel_desc)

        self.tunnel_status_label = QLabel("Domain Status: ACTIVE  •  https://linguafusion.fyi")
        self.tunnel_status_label.setObjectName("SignalStatus")
        tunnel_layout.addWidget(self.tunnel_status_label)

        layout.addWidget(tunnel_card)

        # Card 3: Share QR Code for Joining
        qr_card = Card("Card")
        qr_card.setObjectName("SignalAccessCard")
        qr_layout = QVBoxLayout(qr_card)
        qr_layout.setContentsMargins(18, 16, 18, 16)
        qr_layout.setSpacing(12)

        qr_title = QLabel("SHARE QR CODE FOR JOINING")
        qr_title.setObjectName("CardTitle")
        qr_layout.addWidget(qr_title)

        qr_desc = QLabel(
            "Scan this QR code with your phone (iOS Safari or Android Chrome) or share the join link to allow friends/devices to connect. Works directly as a Web App—no App Store download required!"
        )
        qr_desc.setObjectName("Muted")
        qr_desc.setWordWrap(True)
        qr_layout.addWidget(qr_desc)

        public_url_box = QHBoxLayout()
        pub_lbl = QLabel("Public Domain / Tunnel URL:")
        pub_lbl.setObjectName("Muted")
        self.public_url_input = QLineEdit("https://linguafusion.fyi")
        self.public_url_input.setObjectName("SearchBox")
        self.public_url_input.setPlaceholderText("e.g. https://xxxx.trycloudflare.com (auto-filled when tunnel is active)")
        public_url_box.addWidget(pub_lbl)
        public_url_box.addWidget(self.public_url_input, 1)
        qr_layout.addLayout(public_url_box)

        gen_qr_btn = QPushButton("Generate Fresh Join QR Code")
        gen_qr_btn.setObjectName("SecondaryButton")
        gen_qr_btn.clicked.connect(self.fetch_access_qr)
        qr_layout.addWidget(gen_qr_btn)

        self.qr_image_label = QLabel("Click 'Generate Fresh Join QR Code' to show QR")
        self.qr_image_label.setObjectName("SignalQrPanel")
        self.qr_image_label.setAlignment(Qt.AlignCenter)
        self.qr_image_label.setMinimumHeight(180)
        qr_layout.addWidget(self.qr_image_label)

        self.qr_url_label = QLabel("")
        self.qr_url_label.setObjectName("LinkLabel")
        self.qr_url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.qr_url_label.setWordWrap(True)
        qr_layout.addWidget(self.qr_url_label)

        layout.addWidget(qr_card)

        # Card 3: Connected Users & Devices
        clients_card = Card("Card")
        clients_card.setObjectName("SignalAccessCard")
        clients_layout = QVBoxLayout(clients_card)
        clients_layout.setContentsMargins(18, 16, 18, 16)
        clients_layout.setSpacing(12)

        clients_header = QHBoxLayout()
        clients_title = QLabel("CONNECTED DEVICES & PERMISSIONS")
        clients_title.setObjectName("CardTitle")
        clients_header.addWidget(clients_title)
        clients_header.addStretch(1)

        refresh_btn = QPushButton("Refresh Devices List")
        refresh_btn.setObjectName("SecondaryButton")
        refresh_btn.clicked.connect(self.load_access_clients)
        clients_header.addWidget(refresh_btn)
        clients_layout.addLayout(clients_header)

        self.clients_container = QVBoxLayout()
        clients_layout.addLayout(self.clients_container)

        layout.addWidget(clients_card)

        QTimer.singleShot(400, self.load_access_status)
        return page

    def load_access_status(self):
        def task():
            return requests.get(f"{SERVER_URL}/api/access/status", timeout=5).json()

        def success(data):
            if not data.get("ok"):
                self.access_status_label.setText("Status: Unable to reach backend access API")
                return
            enabled = data.get("enabled", True)
            public_url = data.get("public_url", "")
            if enabled:
                self.access_status_label.setText(f"Status: ACTIVE  •  Listening on {public_url}")
                self.access_toggle_btn.setText("Disable Global Access (Turn OFF)")
            else:
                self.access_status_label.setText("Status: DISABLED (Remote requests blocked)")
                self.access_toggle_btn.setText("Enable Global Access (Turn ON)")
            self.load_access_clients_data(data.get("clients", []))
            self.check_tunnel_status()

    def auto_start_tunnel_on_launch(self):
        def task():
            try:
                status = requests.get(f"{SERVER_URL}/api/access/tunnel/status", timeout=5).json()
                if not status.get("active"):
                    requests.post(f"{SERVER_URL}/api/access/tunnel/toggle", json={}, timeout=15)
            except Exception:
                pass

        def success(_):
            self.check_tunnel_status()

        self.run_background(task, success)

    def check_tunnel_status(self):
        def task():
            try:
                return requests.get(f"{SERVER_URL}/api/access/tunnel/status", timeout=5).json()
            except Exception as exc:
                return {"active": False, "error": str(exc)}

        def success(data):
            if not hasattr(self, "tunnel_status_label"):
                return
            if data.get("active") and data.get("url"):
                url = data.get("url", "")
                self.tunnel_status_label.setText(f"Tunnel Status: ACTIVE  •  {url}")
                if hasattr(self, "tunnel_toggle_btn"):
                    self.tunnel_toggle_btn.setText("Stop Public HTTPS Tunnel")
                if hasattr(self, "public_url_input") and not self.public_url_input.text().strip():
                    self.public_url_input.setText(url)
            else:
                err = data.get("error", "")
                lbl = f"Tunnel Status: INACTIVE ({err})" if err else "Tunnel Status: INACTIVE (Click below to start)"
                self.tunnel_status_label.setText(lbl)
                if hasattr(self, "tunnel_toggle_btn"):
                    self.tunnel_toggle_btn.setText("Start Public HTTPS Tunnel")

        self.run_background(task, success)

    def toggle_cloud_tunnel(self):
        self.set_status("Updating Cloudflare HTTPS tunnel...")
        if hasattr(self, "tunnel_toggle_btn"):
            self.tunnel_toggle_btn.setText("Connecting tunnel...")
            self.tunnel_toggle_btn.setEnabled(False)

        def task():
            return requests.post(f"{SERVER_URL}/api/access/tunnel/toggle", json={}, timeout=20).json()

        def success(data):
            if hasattr(self, "tunnel_toggle_btn"):
                self.tunnel_toggle_btn.setEnabled(True)
            if data.get("active") and data.get("url"):
                url = data.get("url", "")
                if hasattr(self, "public_url_input"):
                    self.public_url_input.setText(url)
                self.set_status(f"Cloudflare HTTPS tunnel active: {url}")
            elif data.get("error"):
                self.set_status(f"Tunnel error: {data.get('error')}", error=True)
            else:
                self.set_status("Cloudflare HTTPS tunnel stopped")
            self.check_tunnel_status()

        self.run_background(task, success)

    def toggle_global_access(self):
        def task():
            return requests.post(f"{SERVER_URL}/api/access/toggle", json={}, timeout=5).json()

        def success(data):
            if data.get("ok"):
                self.load_access_status()
                self.set_status("Global backend access updated")

        self.run_background(task, success)

    def fetch_access_qr(self):
        pub_url = self.public_url_input.text().strip() if hasattr(self, "public_url_input") else ""

        def task():
            from urllib.parse import quote
            query = f"label=MobileDevice&public_url={quote(pub_url, safe='')}" if pub_url else "label=MobileDevice"
            return requests.get(f"{SERVER_URL}/api/access/qr?{query}", timeout=10).json()

        def success(data):
            if not data.get("ok"):
                self.set_status("Failed to generate QR code", error=True)
                return
            pairing = data.get("pairing", {})
            qr_data_url = data.get("qr_data_url", "")
            web_url = pairing.get("web_url", "")
            self.qr_url_label.setText(f"Join URL: {web_url}")
            if qr_data_url and "," in qr_data_url:
                import base64
                b64 = qr_data_url.split(",", 1)[1]
                raw_png = base64.b64decode(b64)
                pixmap = QPixmap()
                pixmap.loadFromData(raw_png, "PNG")
                if not pixmap.isNull():
                    scaled = pixmap.scaled(220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.qr_image_label.setPixmap(scaled)
            self.set_status("Fresh join QR code generated")

        self.run_background(task, success)

    def load_access_clients(self):
        def task():
            return requests.get(f"{SERVER_URL}/api/access/clients", timeout=5).json()

        def success(data):
            if data.get("ok"):
                self.load_access_clients_data(data.get("clients", []))
                self.set_status("Device list refreshed")

        self.run_background(task, success)

    def load_access_clients_data(self, clients: list):
        if not hasattr(self, "clients_container"):
            return
        while self.clients_container.count():
            item = self.clients_container.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not clients:
            empty = QLabel("No paired mobile or remote devices yet.")
            empty.setObjectName("Muted")
            self.clients_container.addWidget(empty)
            return

        for client in clients:
            client_id = client.get("id", "")
            name = client.get("name", "Unnamed device")
            platform = client.get("platform", "unknown")
            last_ip = client.get("last_ip") or "Never connected"
            enabled = client.get("enabled", True)
            online = client.get("online", False)

            row_card = Card("SmallCard")
            row_layout = QHBoxLayout(row_card)
            row_layout.setContentsMargins(14, 10, 14, 10)

            status_icon = "● Online" if online else ("Enabled" if enabled else "Disabled")
            info_text = f"<b>{name}</b> ({platform})  •  IP: {last_ip}  •  Status: {status_icon}"
            lbl = QLabel(info_text)
            row_layout.addWidget(lbl)
            row_layout.addStretch(1)

            toggle_btn = QPushButton("Disable" if enabled else "Enable")
            toggle_btn.setObjectName("SecondaryButton")
            toggle_btn.clicked.connect(lambda checked=False, cid=client_id, en=not enabled: self.toggle_client_device(cid, en))
            row_layout.addWidget(toggle_btn)

            revoke_btn = QPushButton("Revoke")
            revoke_btn.setObjectName("SecondaryButton")
            revoke_btn.clicked.connect(lambda checked=False, cid=client_id: self.revoke_client_device(cid))
            row_layout.addWidget(revoke_btn)

            self.clients_container.addWidget(row_card)

    def toggle_client_device(self, client_id: str, enabled: bool):
        def task():
            return requests.post(f"{SERVER_URL}/api/access/clients/{client_id}/toggle", json={"enabled": enabled}, timeout=5).json()

        def success(data):
            if data.get("ok"):
                self.load_access_clients()
                self.set_status("Client permission updated")

        self.run_background(task, success)

    def revoke_client_device(self, client_id: str):
        def task():
            return requests.delete(f"{SERVER_URL}/api/access/clients/{client_id}", timeout=5).json()

        def success(data):
            if data.get("ok"):
                self.load_access_clients()
                self.set_status("Client device revoked")

        self.run_background(task, success)

    def _poll_backend_health_on_startup(self):
        def task():
            try:
                resp = requests.get(f"{SERVER_URL}/health", timeout=1)
                return resp.status_code == 200
            except Exception:
                return False

        def success(is_online):
            if is_online:
                self._is_backend_online = True
                if hasattr(self, "backend_poll_timer") and self.backend_poll_timer.isActive():
                    self.backend_poll_timer.stop()
                self.check_health()
                self.load_corrections_from_backend()
                self.load_smart_provider_status()
                self.load_ai_provider_settings()
                # Auto-start Cloudflare Tunnel so remote/mobile devices connect without manual steps
                self.auto_start_tunnel_on_launch()

        self.run_background(task, success)

    def check_health(self):
        def task():
            response = requests.get(f"{SERVER_URL}/health", timeout=10)
            response.raise_for_status()
            return response.json()

        def success(data):
            services = data.get("services", {}) if isinstance(data, dict) else {}
            critical_ready = bool(services.get("speech")) and bool(services.get("tts"))
            self.system_badge.setText("● Offline Ready" if critical_ready else "● Backend Running")
            self.set_status("Ready" if critical_ready else "Backend running; check diagnostics")
            if hasattr(self, "health_output"):
                self.health_output.setText(json.dumps(data, indent=2, ensure_ascii=False))

        self.run_background(task, success)

    def check_smart_providers(self):
        def task():
            return requests.get(f"{SERVER_URL}/corrections/providers", timeout=10).json()

        def success(data):
            self.smart_provider_status = data.get("providers", {}) if data.get("ok") else {}
            if hasattr(self, "health_output"):
                self.health_output.setText(json.dumps(data, indent=2, ensure_ascii=False))
            self.set_status("Smart providers checked")

        self.run_background(task, success)

    def load_ai_provider_settings(self):
        if not hasattr(self, "ollama_status_label"):
            return

        def task():
            return requests.get(f"{SERVER_URL}/ai/providers/config", timeout=10).json()

        def success(data):
            if not data.get("ok"):
                self.set_status("Could not load Ollama status", error=True)
                self.ollama_status_label.setText("Status: could not reach backend")
                return
            self.ai_provider_config = data
            ollama = data.get("ollama", {})
            if ollama.get("enabled"):
                self.ollama_status_label.setText(f"Status: enabled · model {ollama.get('model', '?')} · {ollama.get('url', '?')}")
            else:
                self.ollama_status_label.setText("Status: disabled in backend config")

            if hasattr(self, "speech_correction_mode"):
                idx = self.speech_correction_mode.findData(data.get("default_mode", "free_auto"))
                if idx >= 0:
                    self.speech_correction_mode.setCurrentIndex(idx)

            if hasattr(self, "health_output"):
                self.health_output.setText(json.dumps(data, indent=2, ensure_ascii=False))
            self.set_status("Ollama status loaded")

        self.run_background(task, success)

    def test_ai_provider(self, provider: str):
        self.set_status(f"Testing {provider} provider")

        def delayed_test():
            time.sleep(0.5)
            return requests.post(f"{SERVER_URL}/ai/providers/test", data={"provider": provider}, timeout=90).json()

        def success(data):
            if hasattr(self, "health_output"):
                self.health_output.setText(json.dumps(data, indent=2, ensure_ascii=False))
            if data.get("ok"):
                self.set_status(f"{provider} test successful")
            else:
                self.set_status(f"{provider} test failed: {data.get('error')}", error=True)

        self.run_background(delayed_test, success)

    def build_design_demo_page(self):
        page = QWidget()
        page.setObjectName("DesignDemoPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        web_view = QWebEngineView()

        if getattr(sys, "frozen", False):
            base_dir = Path(sys._MEIPASS)
        else:
            base_dir = Path(__file__).resolve().parent

        demo_path = base_dir / "design" / "demo.html"
        if not demo_path.exists():
            demo_path = base_dir / "desktop" / "design" / "demo.html"

        if demo_path.exists():
            web_view.setUrl(QUrl.fromLocalFile(str(demo_path.resolve())))
        else:
            web_view.setHtml("<h2 style='color:red;padding:20px;'>Design demo HTML not found.</h2>")

        layout.addWidget(web_view)
        return page

    def closeEvent(self, event):
        try:
            self.playback_timer.stop()
            if hasattr(self, "speech_timer"):
                self.speech_timer.stop()
            if hasattr(self, "speech_live_timer"):
                self.speech_live_timer.stop()
            if getattr(self, "speech_stream", None):
                self.speech_stream.stop()
                self.speech_stream.close()
            if getattr(self, "audio_backend_ready", False):
                pygame.mixer.music.stop()
                pygame.mixer.quit()
        except Exception:
            pass
        for audio_file in self.generated_audio_files:
            try:
                os.remove(audio_file)
            except Exception:
                pass
        event.accept()


def _free_stale_backend_port(port: int = 8000):
    """If port 8000 is occupied by an unresponsive or zombie process (e.g. after hibernate), kill it so a fresh backend can bind cleanly."""
    if sys.platform != "win32":
        return
    try:
        cmd = f'netstat -ano | findstr LISTENING | findstr :{port}'
        output = subprocess.check_output(cmd, shell=True, text=True, errors="ignore")
        for line in output.strip().splitlines():
            parts = line.split()
            if len(parts) >= 5:
                pid = parts[-1]
                if pid and pid.isdigit() and int(pid) != os.getpid():
                    subprocess.run(f'taskkill /F /PID {pid}', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def ensure_backend_running():
    """Check if FastAPI backend is responsive on http://localhost:8000.
    If not running or unresponsive (e.g. after hibernate), clean up stale port locks and spawn backend.
    """
    try:
        response = requests.get(f"{SERVER_URL}/health", timeout=0.5)
        if response.status_code == 200:
            return None  # Already running
    except Exception:
        pass

    _free_stale_backend_port(8000)

    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    env = os.environ.copy()
    env.setdefault("LF_WHISPER_MODEL", "medium")
    env.setdefault("LF_WHISPER_DEVICE", "cuda")
    env.setdefault("NLLB_DEVICE", "cuda")
    env.setdefault("NLLB_COMPUTE_TYPE", "int8")

    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--backend"]
        cwd = str(Path(sys.executable).resolve().parent)
    else:
        project_root = Path(__file__).resolve().parents[1]
        raw_exe = Path(sys.executable)
        if raw_exe.name.lower() == "pythonw.exe":
            python_exe = str(raw_exe.parent / "python.exe")
        else:
            python_exe = sys.executable
        cmd = [python_exe, str(Path(__file__).resolve()), "--backend"]
        cwd = str(project_root)
        venv_site = project_root / ".venv" / "Lib" / "site-packages"
        cuda_bins = [
            str(venv_site / "nvidia" / "cublas" / "bin"),
            str(venv_site / "nvidia" / "cuda_runtime" / "bin"),
            str(venv_site / "torch" / "lib"),
        ]
        env["PATH"] = os.pathsep.join([p for p in cuda_bins if os.path.exists(p)]) + os.pathsep + env.get("PATH", "")
        env["PYTHONPATH"] = str(project_root)

    process = subprocess.Popen(
        cmd,
        creationflags=creation_flags,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    return process


SINGLE_INSTANCE_SERVER_NAME = "LinguaFusion_SingleInstance_Server"


def handle_single_instance_check() -> tuple[QLocalServer | None, bool]:
    """Check if another instance of LinguaFusion is running.
    If so, notify it to restore its window and return (None, False).
    Otherwise, return (server_instance, True).
    """
    for arg in sys.argv[1:]:
        if "multiprocessing" in arg or "from_parent" in arg or "parent_pid" in arg or "backend" in arg:
            return None, False

    socket = QLocalSocket()
    socket.connectToServer(SINGLE_INSTANCE_SERVER_NAME)
    if socket.waitForConnected(500):
        socket.write(b"SHOW_WINDOW")
        socket.waitForBytesWritten(1000)
        socket.disconnectFromServer()
        return None, False

    server = QLocalServer()
    QLocalServer.removeServer(SINGLE_INSTANCE_SERVER_NAME)
    if not server.listen(SINGLE_INSTANCE_SERVER_NAME):
        QLocalServer.removeServer(SINGLE_INSTANCE_SERVER_NAME)
        server.listen(SINGLE_INSTANCE_SERVER_NAME)

    return server, True


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()

    if "--piper-worker" in sys.argv:
        from backend.services.piper_service import run_frozen_piper_worker

        worker_args = sys.argv[sys.argv.index("--piper-worker") + 1:]
        sys.exit(run_frozen_piper_worker(worker_args))

    if "--backend" in sys.argv:
        os.environ.setdefault("LF_WHISPER_MODEL", "medium")
        os.environ.setdefault("LF_WHISPER_DEVICE", "cuda")
        os.environ.setdefault("NLLB_DEVICE", "cuda")
        os.environ.setdefault("NLLB_COMPUTE_TYPE", "int8")

        import uvicorn
        from backend.server import app

        host = os.environ.get("HOST", "0.0.0.0")
        port = int(os.environ.get("PORT", "8000"))
        uvicorn.run(app, host=host, port=port, log_level="warning")
        sys.exit(0)

    set_windows_app_user_model_id()
    app = QApplication(sys.argv)
    if not getattr(sys, "frozen", False):
        app.setDesktopFileName("LinguaFusion.Desktop")
    app.setApplicationName("LinguaFusion")

    server, is_primary = handle_single_instance_check()
    if not is_primary:
        # Secondary instance launched (e.g. from taskbar/shortcut while app is running):
        # We notified the running instance to show its window, so exit cleanly now.
        sys.exit(0)

    # Primary instance: launch backend server and initialize UI
    backend_process = ensure_backend_running()

    icon_path = app_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = LinguaFusionWindow()

    def _on_single_instance_message():
        client = server.nextPendingConnection() if server else None
        if not client:
            return

        def _read_and_process():
            msg = client.readAll().data().decode("utf-8", errors="ignore")
            if "SHOW_WINDOW" in msg:
                window.show()
                window.setWindowState(window.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
                window.raise_()
                window.activateWindow()
            client.disconnectFromServer()

        client.readyRead.connect(_read_and_process)

    if server:
        server.newConnection.connect(_on_single_instance_message)

    if "--autostart" in sys.argv or "--minimized" in sys.argv:
        window.hide()
        if hasattr(window, "tray_icon") and window.tray_icon.isVisible():
            window.tray_icon.showMessage(
                "LinguaFusion",
                "Started in background. LinguaFusion is ready for connection.",
                QSystemTrayIcon.Information,
                3000,
            )
    else:
        window.show()
        window.raise_()
        window.activateWindow()

    QTimer.singleShot(0, window.apply_app_icon)
    exit_code = app.exec()
    if server:
        server.close()
        QLocalServer.removeServer(SINGLE_INSTANCE_SERVER_NAME)
    if backend_process is not None:
        backend_process.terminate()
    sys.exit(exit_code)
