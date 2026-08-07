from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "desktop" / "main.py"
VERSION = ROOT / "VERSION"
ICON = ROOT / "desktop" / "assets" / "linguafusion.ico"
ICON_PNG = ROOT / "desktop" / "assets" / "linguafusion_icon_512.png"


def main():
    source = MAIN.read_text(encoding="utf-8")
    version = VERSION.read_text(encoding="utf-8").strip()
    assert version.startswith("1.0-rc2."), f"Unexpected version: {version}"
    assert ICON.exists() and ICON.stat().st_size > 1000, "Missing Windows icon asset"
    assert ICON_PNG.exists() and ICON_PNG.stat().st_size > 1000, "Missing PNG icon asset"
    required = [
        "apply_app_icon",
        "QIcon",
        "SetCurrentProcessExplicitAppUserModelID",
        "linguafusion.ico",
        "responsive_band_widgets",
        "responsive_compact_cards",
        "medium_band_width",
        "setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)",
        "translate_player_card",
        "reader_player_card",
        "speech_recorder_card",
        "ocr_lang",
    ]
    for marker in required:
        assert marker in source, f"Missing workflow-fit/icon marker: {marker}"
    print("Phase 5 UI workflow fit and icon tests passed")


if __name__ == "__main__":
    main()
