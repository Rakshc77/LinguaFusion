"""Create an offline QR pairing card for the LinguaFusion phone client."""

from __future__ import annotations

import argparse
import html
from pathlib import Path

from reportlab.graphics import renderSVG
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing


def create_pairing_card(url: str, output: Path, fallback_url: str = "") -> tuple[Path, Path]:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    svg_path = output.with_suffix(".svg")

    widget = QrCodeWidget(url, barLevel="M")
    left, bottom, right, top = widget.getBounds()
    source_width = max(right - left, 1)
    source_height = max(top - bottom, 1)
    qr_size = 360
    drawing = Drawing(qr_size, qr_size, transform=[
        qr_size / source_width, 0, 0, qr_size / source_height,
        -left * qr_size / source_width, -bottom * qr_size / source_height,
    ])
    drawing.add(widget)
    renderSVG.drawToFile(drawing, str(svg_path))

    safe_url = html.escape(url, quote=True)
    safe_fallback_url = html.escape(fallback_url, quote=True)
    safe_svg = html.escape(svg_path.name, quote=True)
    fallback_markup = (
        f'<p class="fallback">Native app not installed? '
        f'<a href="{safe_fallback_url}">Open the browser version</a>.</p>'
        if fallback_url else ""
    )
    output.write_text(
        f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pair LinguaFusion Mobile</title>
<style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#f6f8fc;color:#172033;font:16px/1.45 system-ui,-apple-system,'Segoe UI',sans-serif}}
main{{width:min(540px,calc(100% - 32px));padding:30px;text-align:center;background:#fff;border:1px solid #d7dee8;border-radius:18px;box-shadow:0 18px 50px rgba(23,32,51,.12)}}
.mark{{display:grid;place-items:center;width:48px;height:48px;margin:auto;border-radius:12px;background:#e8f0fe;color:#0b57d0;font-size:25px;font-weight:800}}
h1{{margin:15px 0 5px;font-size:25px}}p{{margin:6px 0;color:#667085}}img{{display:block;width:min(360px,100%);margin:18px auto}}code{{display:block;margin-top:15px;padding:11px;border-radius:9px;background:#f1f4f9;overflow-wrap:anywhere;font-size:12px}}strong{{color:#167647}}a{{color:#0b57d0;font-weight:700}}.fallback{{margin-top:16px}}
</style></head><body><main><div class="mark">文</div><h1>Pair LinguaFusion Mobile</h1>
<p>Install LinguaFusion first, then scan this with your phone camera and choose <b>Open LinguaFusion</b>.</p><img src="{safe_svg}" alt="LinguaFusion app pairing QR code">
<p><strong>The installed app will remember this PC automatically.</strong></p><p>This QR expires after 15 minutes and works once.</p>
{fallback_markup}<code>{safe_url}</code></main></body></html>""",
        encoding="utf-8",
    )
    return output, svg_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--fallback-url", default="")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    html_path, _ = create_pairing_card(args.url, args.output, args.fallback_url)
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
