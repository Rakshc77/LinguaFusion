"""Render the app icon to PNG, because iOS will not use the SVG.

Safari ignores SVG icons when a page is added to the home screen, so without a
PNG `apple-touch-icon` an installed app shows a screenshot thumbnail instead of
its own icon. Chrome accepts the SVG but prefers PNGs for the launcher.

The geometry is transcribed from cloud_api/web/icon.svg rather than traced by
eye, so the two cannot drift apart in shape -- only in colour, which is checked
by a test.

Deliberately square with no rounded corners: iOS applies its own mask, and a
corner radius baked into the file is rounded a second time and looks wrong.
"""
import pathlib
import sys

from PIL import Image, ImageDraw

WEB = pathlib.Path(__file__).resolve().parents[1] / 'cloud_api' / 'web'
SOURCE = WEB / 'icon.svg'

# From icon.svg, on its 512x512 canvas.
BACKGROUND = '#1155cf'
LETTER = '#ffffff'
# "L": M150 348V164h34v154h86v30z
L_SHAPE = [(150, 348), (150, 164), (184, 164), (184, 318), (270, 318), (270, 348)]
# "F": M300 164h110v30h-76v46h58v30h-58v78h-34z
# Same 34-wide stem and 30-tall arms as the L, so they read as one typeface.
F_SHAPE = [(300, 164), (410, 164), (410, 194), (334, 194), (334, 240),
           (392, 240), (392, 270), (334, 270), (334, 348), (300, 348)]

# 180 is what modern iPhones ask for; the other two are for the manifest.
SIZES = {'apple-touch-icon.png': 180, 'icon-192.png': 192, 'icon-512.png': 512}


def render(size):
    """Draw at 4x and downsample, so the small sizes keep clean edges."""
    scale = 4
    canvas = Image.new('RGB', (512 * scale, 512 * scale), BACKGROUND)
    pen = ImageDraw.Draw(canvas)
    for shape, colour in [(L_SHAPE, LETTER), (F_SHAPE, LETTER)]:
        pen.polygon([(x * scale, y * scale) for x, y in shape], fill=colour)
    return canvas.resize((size, size), Image.LANCZOS)


def main():
    if not SOURCE.is_file():
        raise SystemExit(f'{SOURCE} is missing; the PNGs are derived from it')
    for name, size in SIZES.items():
        target = WEB / name
        render(size).save(target, 'PNG', optimize=True)
        print(f'{name:<22} {size}x{size}  {target.stat().st_size / 1024:.1f} KB')
    print('Icons written. They are opaque and square on purpose: iOS masks them itself.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
