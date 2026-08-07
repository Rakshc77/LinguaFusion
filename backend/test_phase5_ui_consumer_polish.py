from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "desktop" / "main.py"
VERSION = ROOT / "VERSION"
ICON = ROOT / "desktop" / "assets" / "linguafusion.ico"
APP_ICON = ROOT / "desktop" / "assets" / "linguafusion_icon_512.png"
ICONOGRAPHY = ROOT / "desktop" / "iconography.py"


def main():
    source = MAIN.read_text(encoding="utf-8")
    version = VERSION.read_text(encoding="utf-8").strip()
    assert version.startswith("1.0-rc2."), f"Unexpected version: {version}"
    assert ICON.exists() and ICON.stat().st_size > 1000, "Missing default Windows icon"
    assert APP_ICON.exists() and APP_ICON.stat().st_size > 1000, "Missing production app icon"
    icon_source = ICONOGRAPHY.read_text(encoding="utf-8")
    required = [
        "from desktop.iconography import app_icon",
        "apply_contextual_button_icon",
        "Apply theme-safe vector playback icons",
        "TranslatePane",
        "PaneToolButton",
        "self.ocr_language_label",
        "Extract Text",
        "self.ocr_text.setMinimumHeight(210)",
        "QTimer.singleShot(0, lambda: self.page_scroll.verticalScrollBar().setValue(0))",
        'current_page_name in {"Reader", "Speech"}',
    ]
    for marker in required:
        assert marker in source, f"Missing consumer polish marker: {marker}"
    for marker in ["def app_icon(", "QPainter.Antialiasing", 'name == "swap"']:
        assert marker in icon_source, f"Missing vector icon marker: {marker}"
    print("Phase 5 UI consumer polish tests passed")


if __name__ == "__main__":
    main()
