"""Release checks distinguish candidate source from the APK actually offered."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest


@pytest.fixture
def release_snapshot(tmp_path):
    source = Path(__file__).resolve().parents[1]
    paths = [
        'scripts/check_release_manifest.py', 'release/manifest.json',
        'cloud_api/web/app-version.json', 'cloud_api/web/updates.mjs',
        'cloud_api/web/sw.js', 'cloud_api/web/android-app.json',
        'android/LinguaFusionMobile/build.gradle',
        'ios/LinguaFusionMobile/LinguaFusionMobile/Info.plist',
        'ios/LinguaFusionMobile/LinguaFusionMobile/MobileWebView.swift',
        'ios/LinguaFusionMobile/LinguaFusionMobile.xcodeproj/project.pbxproj',
    ]
    for path in paths:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / path, target)
    return tmp_path


def check(snapshot):
    return subprocess.run([sys.executable, str(snapshot / 'scripts/check_release_manifest.py')],
                          capture_output=True, text=True, timeout=15)


def test_candidate_can_be_newer_than_the_published_apk(release_snapshot):
    path = release_snapshot / 'release/manifest.json'
    ledger = json.loads(path.read_text())
    android = ledger['android']
    android['version_code'] = android['published_version_code'] + 1
    android['version_name'] = android['published_version_name'] + '.candidate'
    path.write_text(json.dumps(ledger))
    gradle = release_snapshot / 'android/LinguaFusionMobile/build.gradle'
    text = re.sub(r'\bversionCode\s+\d+', f"versionCode {android['version_code']}", gradle.read_text())
    text = re.sub(r"\bversionName\s+'[^']+'", f"versionName '{android['version_name']}'", text)
    gradle.write_text(text)
    result = check(release_snapshot)
    assert result.returncode == 0, result.stderr


def test_candidate_build_metadata_drift_is_rejected(release_snapshot):
    path = release_snapshot / 'release/manifest.json'
    ledger = json.loads(path.read_text())
    ledger['android']['version_code'] += 1
    path.write_text(json.dumps(ledger))
    result = check(release_snapshot)
    assert result.returncode != 0
    assert 'Android build code' in result.stderr


def test_source_bump_cannot_claim_an_unpublished_apk(release_snapshot):
    path = release_snapshot / 'release/manifest.json'
    ledger = json.loads(path.read_text())
    ledger['android']['published_version_code'] = ledger['android']['version_code']
    ledger['android']['published_version_name'] = ledger['android']['version_name']
    path.write_text(json.dumps(ledger))
    result = check(release_snapshot)
    assert result.returncode != 0
    assert 'published Android APK' in result.stderr
