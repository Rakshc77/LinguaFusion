"""Render deterministic LinguaFusion desktop screenshots for visual QA."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("LF_TEST_MODE", "1")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtTest import QTest
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from desktop.main import LinguaFusionWindow


DEFAULT_STATES = [
    ("minimum", 1180, 720),
    ("standard", 1440, 900),
    ("expanded", 1800, 1050),
]


def _visible_geometry(widget) -> dict:
    top_left = widget.mapToGlobal(widget.rect().topLeft())
    return {
        "visible": widget.isVisible(),
        "x": top_left.x(),
        "y": top_left.y(),
        "width": widget.width(),
        "height": widget.height(),
    }


def _state_metrics(window, page: str, state: str, width: int, height: int, path: Path, theme="light") -> dict:
    result = {
        "page": page,
        "state": state,
        "theme": theme,
        "window": {"width": width, "height": height},
        "file": str(path),
        "sidebar": _visible_geometry(window.sidebar),
        "right_panel": _visible_geometry(window.right_panel),
        "page_scroll": _visible_geometry(window.page_scroll),
        "horizontal_overflow": window.page_scroll.horizontalScrollBar().maximum(),
        "nav_icons_visible": all(not button.icon().isNull() for button in window.nav_buttons.values()),
    }
    if page == "Translate":
        result["translate"] = {
            "source_pane": _visible_geometry(window.translate_source_pane),
            "target_pane": _visible_geometry(window.translate_target_pane),
            "source_input": _visible_geometry(window.translate_input),
            "target_output": _visible_geometry(window.translate_output),
            "source_language": _visible_geometry(window.translate_source),
            "target_language": _visible_geometry(window.translate_target),
            "actions": _visible_geometry(window.translate_action_host),
        }
    return result


def capture(output_dir: Path, prefix: str, pages: list[str], include_layout_variants=False) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    # The offscreen Qt platform does not enumerate Windows fonts reliably in
    # the sandbox. Register the production typeface explicitly for readable QA
    # captures; normal interactive Windows sessions already see it system-wide.
    for font_path in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\seguisb.ttf"):
        QFontDatabase.addApplicationFont(font_path)
    app.setFont(QFont("Segoe UI", 10))
    window = LinguaFusionWindow()
    window.show()
    QTest.qWait(1200)

    results = []
    for state_name, width, height in DEFAULT_STATES:
        window.resize(width, height)
        QTest.qWait(300)
        for page in pages:
            window.switch_page(page)
            QTest.qWait(250)
            filename = f"{prefix}_{page.lower()}_{state_name}_{width}x{height}.png"
            path = output_dir / filename
            if not window.grab().save(str(path), "PNG"):
                raise RuntimeError(f"Could not save {path}")
            results.append(_state_metrics(window, page, state_name, width, height, path))

    if include_layout_variants:
        variants = [
            ("minimum_expanded_nav", 1180, 720, False, False, False, "Translate"),
            ("standard_with_details", 1440, 900, False, True, False, "Translate"),
            ("expanded_focus_canvas", 1800, 1050, True, False, False, "Translate"),
            ("night_focus_canvas", 1800, 1050, True, False, True, "Translate"),
            ("night_settings", 1440, 900, False, False, True, "Settings"),
        ]
        for state_name, width, height, compact_sidebar, show_inspector, dark, page in variants:
            window.sidebar_user_override = compact_sidebar
            window.inspector_user_override = show_inspector
            window.toggle_dark_mode(dark)
            window.resize(width, height)
            window._responsive_mode = None
            window.switch_page(page)
            QTest.qWait(300)
            filename = f"{prefix}_{page.lower()}_{state_name}_{width}x{height}.png"
            path = output_dir / filename
            if not window.grab().save(str(path), "PNG"):
                raise RuntimeError(f"Could not save {path}")
            results.append(
                _state_metrics(
                    window,
                    page,
                    state_name,
                    width,
                    height,
                    path,
                    theme="dark" if dark else "light",
                )
            )

    window.close()
    window.executor.shutdown(wait=True, cancel_futures=True)
    app.processEvents()
    (output_dir / f"{prefix}_metrics.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "temp" / "ui_review")
    parser.add_argument("--prefix", default="current")
    parser.add_argument("--pages", nargs="+", default=["Translate", "Speech", "OCR"])
    parser.add_argument("--include-layout-variants", action="store_true")
    args = parser.parse_args()
    results = capture(args.output_dir, args.prefix, args.pages, args.include_layout_variants)
    print(f"Captured {len(results)} states in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
