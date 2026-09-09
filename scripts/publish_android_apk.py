"""Stage the built Android APK for download from the cloud app.

  python scripts/publish_android_apk.py

Copies the signed APK into the served assets and records its size and SHA-256
so the page can show a fingerprint people can check against what they install.

The APK is offered publicly and unauthenticated on purpose: someone scanning
the invite has no account yet, so they cannot authenticate to download it. That
is safe because the APK grants nothing on its own -- it is a shell around the
same web app, and every account still needs Firebase sign-in plus the owner's
approval. It must therefore contain no secret, which is re-checked here rather
than assumed, because a future build could pick one up.
"""
import hashlib
import json
import pathlib
import re
import shutil
import sys
import os
import subprocess
import zipfile
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'android' / 'LinguaFusionMobile' / 'dist' / 'LinguaFusionMobile-debug.apk'
TARGET = ROOT / 'cloud_api' / 'web' / 'linguafusion-android.apk'
DETAILS = ROOT / 'cloud_api' / 'web' / 'android-app.json'

# Values that must never leave the build machine inside a published binary.
SECRET_PATTERNS = [
    rb'sk-or-[A-Za-z0-9_-]{6,}',
    rb'gsk_[A-Za-z0-9_-]{6,}',
    rb'AIza[A-Za-z0-9_-]{10,}',
    rb'BEGIN [A-Z ]*PRIVATE KEY',
    rb'-----BEGIN CERTIFICATE-----',
]
REQUIRED_ENTRIES = {'AndroidManifest.xml', 'classes.dex'}


def main():
    if not SOURCE.is_file():
        raise SystemExit(f'No APK at {SOURCE}. Build it first with '
                         'android/LinguaFusionMobile/build_apk.ps1')
    payload = SOURCE.read_bytes()

    with zipfile.ZipFile(SOURCE) as archive:
        names = set(archive.namelist())
    missing = REQUIRED_ENTRIES - names
    if missing:
        raise SystemExit(f'That file is not a usable APK; missing {sorted(missing)}')
    # Modern target SDKs use v2/v3 signing (no META-INF/*.RSA entry).
    sdk = pathlib.Path(os.environ.get('ANDROID_HOME', pathlib.Path.home() / 'AppData/Local/Android/Sdk'))
    verifiers = sorted((sdk / 'build-tools').glob('*/apksigner.bat'), reverse=True)
    if not verifiers:
        raise SystemExit('Android apksigner is required to verify the APK before publishing.')
    env = os.environ.copy()
    env.setdefault('JAVA_HOME', r'C:\Program Files\Android\Android Studio\jbr')
    verified = subprocess.run([str(verifiers[0]), 'verify', str(SOURCE)], env=env, capture_output=True)
    if verified.returncode:
        raise SystemExit('APK cryptographic signature verification failed.')

    with zipfile.ZipFile(SOURCE) as archive:
        for name in archive.namelist():
            if any(re.search(pattern, archive.read(name)) for pattern in SECRET_PATTERNS):
                raise SystemExit('APK entry contains credential-shaped data; refusing to publish it.')

    # The version the app compares against its own, so it can offer an update
    # instead of expecting someone to notice one exists and reinstall by hand.
    badging = subprocess.run([str(sorted((sdk / 'build-tools').glob('*/aapt2.exe'),
                                         reverse=True)[0]), 'dump', 'badging', str(SOURCE)],
                             capture_output=True, text=True)
    version = re.search(r"versionCode='(\d+)' versionName='([^']*)'", badging.stdout)
    if not version:
        raise SystemExit('Could not read the version out of the APK; refusing to '
                         'publish metadata the updater would misread.')

    digest = hashlib.sha256(payload).hexdigest()
    shutil.copy2(SOURCE, TARGET)
    DETAILS.write_text(json.dumps({
        'file': TARGET.name,
        'bytes': len(payload),
        'sha256': digest,
        'versionCode': int(version.group(1)),
        'versionName': version.group(2),
        'published_at': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'signing': 'debug keystore',
    }, indent=1) + '\n', encoding='utf-8')

    print(json.dumps({'copied_to': str(TARGET), 'bytes': len(payload),
                      'sha256': digest, 'entries': len(names)}, indent=1))
    print('Reminder: this is a debug-signed build. Installing it requires '
          'allowing installation from an unknown source on the phone.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
