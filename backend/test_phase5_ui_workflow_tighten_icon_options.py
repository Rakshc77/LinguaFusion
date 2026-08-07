from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "desktop" / "main.py"
VERSION = ROOT / "VERSION"
ICON = ROOT / "desktop" / "assets" / "linguafusion.ico"
PRODUCTION_ICONS = [
    ICON,
    ROOT / "desktop" / "assets" / "linguafusion_icon_512.png",
    ROOT / "desktop" / "assets" / "linguafusion_taskbar_256.png",
]
ICONOGRAPHY = ROOT / "desktop" / "iconography.py"


def main():
    source = MAIN.read_text(encoding="utf-8")
    version = VERSION.read_text(encoding="utf-8").strip()
    assert version.startswith("1.0-rc2."), f"Unexpected version: {version}"
    assert all(path.exists() and path.stat().st_size > 1000 for path in PRODUCTION_ICONS), "Missing production desktop icon"
    icon_source = ICONOGRAPHY.read_text(encoding="utf-8")
    required = [
        "apply_media_button_icon",
        "media_icon_kind",
        "apply_contextual_button_icon",
        "app_icon(kind, 18",
        "ocr_controls_host",
        'current_page_name in {"Reader", "Speech"}',
        "setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)",
        "medium_band_width",
        "responsive_compact_cards",
    ]
    for marker in required:
        assert marker in source, f"Missing Phase 5 tighten/icon marker: {marker}"
    for marker in ['name == "play"', 'name == "pause"', 'name == "stop"', 'name == "rewind"']:
        assert marker in icon_source, f"Missing media vector icon: {marker}"
    print("Phase 5 UI workflow tighten and icon options tests passed")


if __name__ == "__main__":
    main()
