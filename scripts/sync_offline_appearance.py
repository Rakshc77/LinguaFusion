"""Copy the shared appearance into the offline Android app.

The offline page ships inside the APK and must render with no network, so it
cannot link the hosted stylesheets -- it needs its own copies. Copies drift,
and drift here is exactly what the owner saw on the phone: the same product
wearing two different faces depending on which mode it was in.

So the copies are made by this script rather than by hand, and a test asserts
they are byte-identical to the originals. Change the appearance in
`cloud_api/web/`, run this, rebuild the APK.
"""
import filecmp
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'cloud_api' / 'web'
TARGET = ROOT / 'android' / 'LinguaFusionMobile' / 'assets' / 'offline'

# The whole of the appearance contract. pilot.css is included even though the
# offline page uses a subset of it: taking part of a stylesheet is how the two
# start to differ again.
SHARED = ['linguafusion-themes.css', 'pilot.css', 'themes.mjs']


def main():
    if not TARGET.is_dir():
        raise SystemExit(f'No offline assets directory at {TARGET}')
    changed = []
    for name in SHARED:
        source, target = SOURCE / name, TARGET / name
        if not source.is_file():
            raise SystemExit(f'Missing shared appearance file: {source}')
        if target.is_file() and filecmp.cmp(source, target, shallow=False):
            continue
        shutil.copy2(source, target)
        changed.append(name)
    print('in step already' if not changed else 'copied: ' + ', '.join(changed))
    print(f'{len(SHARED)} shared files in {TARGET}')
    if changed:
        print('Rebuild the APK for this to reach the phone.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
