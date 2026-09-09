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
# "A" outline: M300 348l58-184h32l58 184h-34l-13-44h-54l-13 44z
A_SHAPE = [(300, 348), (358, 164), (390, 164), (448, 348),
           (414, 348), (401, 304), (347, 304), (334, 348)]
# The counter of the A, wound the other way so it reads as a hole.
A_COUNTER = [(355, 276), (393, 276), (374, 212)]

# 180 is what modern iPhones ask for; the other two are for the manifest.
SIZES = {'apple-touch-icon.png': 180, 'icon-192.png': 192, 'icon-512.png': 512}


def render(size):
    """Draw at 4x and downsample: the diagonals of the A alias badly otherwise."""
    scale = 4
    canvas = Image.new('RGB', (512 * scale, 512 * scale), BACKGROUND)
    pen = ImageDraw.Draw(canvas)
    for shape, colour in [(L_SHAPE, LETTER), (A_SHAPE, LETTER), (A_COUNTER, BACKGROUND)]:
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
