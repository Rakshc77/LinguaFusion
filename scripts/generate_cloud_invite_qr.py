"""Make an invite with a QR code for the cloud app: PNG, SVG, PDF and a web page.

  python scripts/generate_cloud_invite_qr.py

Scanning it opens the app. The invite carries the four steps that follow,
because a QR code alone leaves people guessing: create an account, confirm the
address, ask the owner for access, then wait to be approved.

The invite contains NO credential and NO personal data. It is safe to print,
photograph or forward; scanning it grants nothing on its own, because every
account is still approved by hand.

Implementation note: the module grid is computed once with `qrcode` and then
drawn as explicit rectangles at absolute coordinates. An earlier version scaled
a reportlab widget with a group transform, which the SVG renderer silently
dropped -- producing an unscaled, unscannable code. Absolute geometry cannot
fail that way, and render_report() re-measures what was drawn.
"""
import argparse
import html
import sys
from pathlib import Path

DEFAULT_URL = 'https://linguafusion-cloud-pilot-jl77ipbeua-ey.a.run.app/pilot/'
# The Android build is optional. The website does everything the app does, so
# the invite leads with the website and offers the app as a second choice.
APK_SUFFIX = 'linguafusion-android.apk'
QUIET_MODULES = 4          # required white border; a code without it will not scan
CARD_QR_POINTS = 288       # QR side length on the printed card, in points

STEPS = [
    ('Scan and open', 'Point your camera at the code. The app opens in your browser.'),
    ('Create an account', 'Choose "I need to create an account" and pick a password.'),
    ('Confirm your email', 'Open the link we email you, then choose Continue.'),
    ('Ask for access', 'Send your name and organisation. The owner approves each person by hand.'),
]


def module_grid(url):
    """The QR matrix including its quiet zone, as rows of booleans."""
    import qrcode
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=QUIET_MODULES)
    code.add_data(url)
    code.make(fit=True)
    grid = [[bool(cell) for cell in row] for row in code.get_matrix()]
    if not grid or len(grid) != len(grid[0]):
        raise SystemExit('The QR matrix is not square; refusing to emit an unscannable code.')
    return grid


def qr_svg_markup(grid, size):
    """Inline SVG for the grid. One rect per dark module, absolute coordinates."""
    side = len(grid)
    step = size / side
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
             f'viewBox="0 0 {side} {side}" shape-rendering="crispEdges" role="img" '
             f'aria-label="QR code linking to the app">',
             f'<rect width="{side}" height="{side}" fill="#ffffff"/>']
    for y, row in enumerate(grid):
        for x, dark in enumerate(row):
            if dark:
                parts.append(f'<rect x="{x}" y="{y}" width="1" height="1" fill="#000000"/>')
    parts.append('</svg>')
    return ''.join(parts), step


def render_png(grid, path, scale=10):
    from PIL import Image
    side = len(grid)
    image = Image.new('1', (side, side), 1)
    pixels = image.load()
    for y, row in enumerate(grid):
        for x, dark in enumerate(row):
            if dark:
                pixels[x, y] = 0
    image.resize((side * scale, side * scale), Image.NEAREST).save(path)
    return path


def build_card(url, grid, output, title):
    """A4 card with the code drawn as absolute rectangles, never a transform."""
    from reportlab.graphics import renderPDF, renderSVG
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.lib.colors import black, white

    width, height = 595, 842
    card = Drawing(width, height)
    card.add(Rect(0, 0, width, height, fillColor=white, strokeColor=None))
    card.add(String(56, height - 80, title, fontName='Helvetica-Bold', fontSize=24))
    card.add(String(56, height - 106,
                    'Translation, pronunciation, speech and reading text from pictures.',
                    fontName='Helvetica', fontSize=11))

    side = len(grid)
    step = CARD_QR_POINTS / side
    origin_x = (width - CARD_QR_POINTS) / 2
    top_y = height - 140
    drawn = 0
    for y, row in enumerate(grid):
        for x, dark in enumerate(row):
            if not dark:
                continue
            # reportlab's origin is bottom-left; the grid's first row is the top.
            card.add(Rect(origin_x + x * step, top_y - (y + 1) * step, step, step,
                          fillColor=black, strokeColor=None, strokeWidth=0))
            drawn += 1

    y_text = top_y - CARD_QR_POINTS - 34
    for index, (heading, detail) in enumerate(STEPS, start=1):
        card.add(String(56, y_text, f'{index}.  {heading}', fontName='Helvetica-Bold', fontSize=13))
        card.add(String(76, y_text - 16, detail, fontName='Helvetica', fontSize=10))
        y_text -= 46

    card.add(String(56, y_text - 4, 'If the code will not scan, type this address:',
                    fontName='Helvetica-Bold', fontSize=9))
    card.add(String(56, y_text - 18, url, fontName='Helvetica', fontSize=9))
    card.add(String(56, y_text - 34, 'Optional Android app (the website does the same):',
                    fontName='Helvetica-Bold', fontSize=9))
    card.add(String(56, y_text - 48, apk_url(url), fontName='Helvetica', fontSize=9))
    card.add(String(56, 56, 'Approval is manual: scanning this code does not grant access by itself.',
                    fontName='Helvetica-Oblique', fontSize=9))
    card.add(String(56, 42, 'This card contains no password and no personal data.',
                    fontName='Helvetica-Oblique', fontSize=9))

    renderSVG.drawToFile(card, str(output.with_suffix('.svg')))
    renderPDF.drawToFile(card, str(output.with_suffix('.pdf')))
    return drawn, output.with_suffix('.svg'), output.with_suffix('.pdf')


def apk_url(url):
    return url.rstrip('/') + '/' + APK_SUFFIX


def build_html(url, grid, output, title):
    markup, _ = qr_svg_markup(grid, 320)
    android = apk_url(url)
    android_markup, _ = qr_svg_markup(module_grid(android), 200)
    steps = '\n'.join(
        f'<li><strong>{html.escape(h)}</strong><br><span>{html.escape(d)}</span></li>'
        for h, d in STEPS)
    page = output.with_suffix('.html')
    page.write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
 body {{ font: 16px/1.6 system-ui, sans-serif; margin: 0; padding: 24px;
        max-width: 640px; margin-inline: auto; color: #172338; background: #f5f7fc; }}
 h1 {{ font-size: 28px; margin: 0 0 8px; }}
 .qr {{ background: #fff; padding: 16px; border-radius: 16px; display: inline-block;
        border: 1px solid #c8d2e3; }}
 .qr.small svg {{ width: 200px; height: 200px; }}
 h2 {{ font-size: 20px; margin-top: 32px; }}
 ol {{ padding-left: 20px; }} li {{ margin-bottom: 14px; }}
 li span {{ color: #526079; font-size: 14px; }}
 .link {{ word-break: break-all; background: #fff; border: 1px solid #c8d2e3;
          border-radius: 9px; padding: 12px; display: block; }}
 .note {{ color: #526079; font-size: 13px; }}
 a.open {{ display: inline-block; background: #1155cf; color: #fff; text-decoration: none;
           padding: 12px 20px; border-radius: 9px; font-weight: 600; margin: 8px 0 20px; }}
 @media (prefers-color-scheme: dark) {{
   body {{ background: #101724; color: #eff4ff; }}
   .link {{ background: #192333; border-color: #52617a; }}
   li span, .note {{ color: #b6c4d9; }}
 }}
</style></head><body>
<h1>{html.escape(title)}</h1>
<p>Translation, pronunciation guides, speech to text, and reading text from pictures.</p>
<p class="qr">{markup}</p>
<p><a class="open" href="{html.escape(url)}">Open the app</a></p>
<ol>{steps}</ol>
<p class="note">Or type this address:</p>
<code class="link">{html.escape(url)}</code>
<h2>Android app (optional)</h2>
<p>The website already does everything. If you would rather have an icon on your home screen, scan this second code or open the link to download it.</p>
<p class="qr small">{android_markup}</p>
<p><a class="open" href="{html.escape(android)}">Download for Android</a></p>
<p class="note">Your phone will warn that this came from outside the Play Store and ask you to allow it. That is expected for a privately shared app. Installing it grants nothing on its own: you still create an account and wait for the owner to approve you.</p>
<p class="note">Approval is manual: opening this link does not grant access by itself.
This page contains no password and no personal data.</p>
</body></html>
""", encoding='utf-8')
    return page


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default=DEFAULT_URL)
    parser.add_argument('--output', default='dist_installer/linguafusion-cloud-invite')
    parser.add_argument('--title', default='Join LinguaFusion Cloud')
    arguments = parser.parse_args()
    if not arguments.url.startswith('https://'):
        raise SystemExit('The invite must point at an https address.')

    output = Path(arguments.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    grid = module_grid(arguments.url)
    expected_dark = sum(row.count(True) for row in grid)

    written = [build_html(arguments.url, grid, output, arguments.title)]
    written.append(render_png(grid, output.with_suffix('.png')))
    drawn, svg_path, pdf_path = build_card(arguments.url, grid, output, arguments.title)
    written += [svg_path, pdf_path]

    if drawn != expected_dark:
        raise SystemExit(f'Card drew {drawn} modules but the grid has {expected_dark}.')
    print(f'QR: {len(grid)}x{len(grid)} modules including a {QUIET_MODULES}-module quiet zone, '
          f'{expected_dark} dark modules drawn in every format')
    print('URL:', arguments.url)
    for item in written:
        print('wrote', item)
    return 0


if __name__ == '__main__':
    sys.exit(main())
