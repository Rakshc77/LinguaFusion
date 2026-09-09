"""The invite's QR must faithfully reproduce the encoded matrix in every format.

An earlier version scaled the code with a reportlab group transform that the SVG
renderer silently discarded, producing an unscannable image while still exiting
successfully. Nothing caught it because nothing read the output back. These
tests re-read each artifact and compare it to the source matrix.
"""
import importlib.util
import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'generate_cloud_invite_qr.py'
URL = 'https://example.invalid/pilot/'

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec('qrcode') is None or importlib.util.find_spec('PIL') is None,
    reason='qrcode and Pillow are needed to build the invite')


def load_module():
    spec = importlib.util.spec_from_file_location('invite_qr', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def built(tmp_path_factory):
    directory = tmp_path_factory.mktemp('invite')
    result = subprocess.run(
        [sys.executable, str(SCRIPT), '--url', URL, '--output', str(directory / 'invite')],
        capture_output=True, text=True, cwd=str(ROOT), timeout=300)
    assert result.returncode == 0, result.stderr[-800:]
    return directory / 'invite', load_module().module_grid(URL)


def test_every_expected_artifact_is_produced(built):
    base, _ = built
    for suffix in ['.html', '.png', '.svg', '.pdf']:
        path = base.with_suffix(suffix)
        assert path.is_file(), suffix
        assert path.stat().st_size > 400, f'{suffix} is suspiciously small'


def test_the_png_pixels_reproduce_the_matrix_exactly(built):
    from PIL import Image
    base, grid = built
    image = Image.open(base.with_suffix('.png')).convert('L')
    side = len(grid)
    scale = image.width / side
    assert image.width == image.height
    for y, row in enumerate(grid):
        for x, dark in enumerate(row):
            # Sample the middle of each module rather than an edge.
            pixel = image.getpixel((int((x + 0.5) * scale), int((y + 0.5) * scale)))
            assert (pixel < 128) == dark, f'module {x},{y} rendered wrong in the PNG'


def test_the_inline_svg_in_the_page_reproduces_the_matrix(built):
    base, grid = built
    page = base.with_suffix('.html').read_text(encoding='utf-8')
    svg = re.search(r'<svg[^>]*aria-label="QR code[^>]*>(.*?)</svg>', page, re.S)
    assert svg, 'the invite page must embed the code, not just a link'

    side = len(grid)
    drawn = {(int(m.group(1)), int(m.group(2)))
             for m in re.finditer(r'<rect x="(\d+)" y="(\d+)" width="1" height="1"', svg.group(1))}
    expected = {(x, y) for y, row in enumerate(grid) for x, dark in enumerate(row) if dark}
    assert drawn == expected, 'the embedded code does not match the encoded matrix'
    assert f'viewBox="0 0 {side} {side}"' in page


def test_the_card_svg_scales_the_code_instead_of_dropping_the_transform(built):
    base, grid = built
    svg = base.with_suffix('.svg').read_text(encoding='utf-8')
    module_count = sum(row.count(True) for row in grid)
    # One rect per dark module, plus page and quiet-zone backgrounds.
    assert svg.count('<rect') >= module_count, 'the card lost modules'

    sizes = {float(w) for w in re.findall(r'<rect[^>]*width="([\d.]+)"', svg)}
    module_sizes = [w for w in sizes if 3 < w < 12]
    assert module_sizes, f'no module-sized rects found; sizes were {sorted(sizes)[:12]}'
    # A dropped transform leaves modules at their raw ~1pt size, far too small
    # to scan. Each module must occupy a real fraction of the printed code.
    assert max(module_sizes) > 4, 'modules are too small to scan; the scaling was lost'


def test_the_invite_carries_no_credential(built):
    base, _ = built
    # Look for credential VALUES, not the English word: "pick a password" is
    # legitimate instruction text on an invite.
    patterns = [r'sk-or-[A-Za-z0-9]', r'gsk_[A-Za-z0-9]', r'Bearer\s+[A-Za-z0-9._-]{8}',
                r'AIza[A-Za-z0-9]', r'(?i)(api[_-]?key|secret|token)\s*[:=]\s*\S']
    for suffix in ['.html', '.svg']:
        text = base.with_suffix(suffix).read_text(encoding='utf-8')
        for pattern in patterns:
            assert not re.search(pattern, text), f'{pattern} matched inside the {suffix} invite'


def test_a_non_https_target_is_refused():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), '--url', 'http://insecure.invalid/'],
        capture_output=True, text=True, cwd=str(ROOT), timeout=120)
    assert result.returncode != 0
    assert 'https' in (result.stdout + result.stderr).lower()


def test_the_invite_offers_the_android_build_through_its_own_qr(built):
    base, _ = built
    module = load_module()
    page = base.with_suffix('.html').read_text(encoding='utf-8')

    codes = re.findall(r'<svg[^>]*aria-label="QR code[^>]*>(.*?)</svg>', page, re.S)
    assert len(codes) == 2, f'expected an app code and an Android code, found {len(codes)}'

    # The second code must encode the APK URL, not repeat the first one.
    android = module.apk_url(URL)
    assert android.endswith('linguafusion-android.apk')
    expected = {(x, y) for y, row in enumerate(module.module_grid(android))
                for x, dark in enumerate(row) if dark}
    drawn = {(int(m.group(1)), int(m.group(2)))
             for m in re.finditer(r'<rect x="(\d+)" y="(\d+)" width="1" height="1"', codes[1])}
    assert drawn == expected, 'the second code does not encode the Android download URL'

    app_only = {(x, y) for y, row in enumerate(module.module_grid(URL))
                for x, dark in enumerate(row) if dark}
    assert drawn != app_only, 'the two codes must differ'
    assert 'outside the Play Store' in page, 'sideloading must be explained, not sprung on people'


def test_the_printed_card_names_the_android_address(built):
    base, _ = built
    svg = base.with_suffix('.svg').read_text(encoding='utf-8')
    assert 'linguafusion-android.apk' in svg, 'the card should say where to get the app'
