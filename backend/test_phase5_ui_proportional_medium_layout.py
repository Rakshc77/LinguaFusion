from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "desktop" / "main.py"
VERSION = ROOT / "VERSION"


def main():
    source = MAIN.read_text(encoding="utf-8")
    version = VERSION.read_text(encoding="utf-8").strip()
    assert version.startswith("1.0-rc2."), f"Unexpected version: {version}"
    required = [
        "setMinimumSize(1180, 640)",
        "self.page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)",
        "responsive_band_widgets",
        "responsive_compact_cards",
        "medium_band_width",
        "medium_combo_width",
        "register_band_widget",
        "register_compact_card",
        "↓ More controls below",
    ]
    for marker in required:
        assert marker in source, f"Missing Phase 5 UI marker: {marker}"
    print("Phase 5 phase5_ui_proportional_medium_layout passed")


if __name__ == "__main__":
    main()
