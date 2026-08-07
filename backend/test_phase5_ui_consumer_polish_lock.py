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
    assert ICON.exists() and ICON.stat().st_size > 1000, "Missing Windows icon"
    assert APP_ICON.exists() and APP_ICON.stat().st_size > 1000, "Missing production app icon"
    assert ICONOGRAPHY.exists(), "Missing code-native icon system"
    required = [
        "APP_USER_MODEL_ID",
        "set_windows_app_user_model_id()",
        "app_icon_path()",
        "QTimer.singleShot(0, window.apply_app_icon)",
        "from desktop.iconography import app_icon",
        "self.sidebar_toggle_btn",
        "self.inspector_toggle_btn",
        "self.translate_swap_btn",
        "self.ocr_controls_row",
        "QHBoxLayout(controls_host)",
        "self.ocr_lang.setMaximumWidth(160)",
    ]
    for marker in required:
        assert marker in source, f"Missing consumer polish lock marker: {marker}"
    assert "Icons are painted with Qt at 2x resolution" in ICONOGRAPHY.read_text(encoding="utf-8")
    print("Phase 5 UI consumer polish lock tests passed")


if __name__ == "__main__":
    main()
