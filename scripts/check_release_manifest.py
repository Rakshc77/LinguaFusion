"""Fail CI if cloud, Android or iOS version copies drift from release/manifest.json."""
import json
import plistlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / "release/manifest.json").read_text(encoding="utf-8"))
cloud, android, ios = (manifest[name] for name in ("cloud", "android", "ios"))


def check(condition, description):
    if not condition:
        raise SystemExit(f"Release manifest mismatch: {description}")


version = cloud["source_version"]
check(json.loads((ROOT / "cloud_api/web/app-version.json").read_text())["version"] == version,
      "Online metadata")
updates = (ROOT / "cloud_api/web/updates.mjs").read_text(encoding="utf-8")
worker = (ROOT / "cloud_api/web/sw.js").read_text(encoding="utf-8")
check(f"APP_VERSION = '{version}'" in updates, "Online update client")
check(f"linguafusion-online-{version}" in worker, "Online service worker")

gradle = (ROOT / "android/LinguaFusionMobile/build.gradle").read_text(encoding="utf-8")
check(re.search(rf"\bversionCode\s+{android['version_code']}\b", gradle), "Android build code")
check(re.search(rf'\bversionName\s+[\'\"]{re.escape(android["version_name"])}[\'\"]', gradle), "Android build name")
apk_meta = json.loads((ROOT / "cloud_api/web/android-app.json").read_text(encoding="utf-8"))
check(apk_meta["versionCode"] == android["version_code"] and
      apk_meta["versionName"] == android["version_name"] and
      apk_meta["sha256"] == android["published_apk_sha256"], "published Android APK")

plist = plistlib.loads((ROOT / "ios/LinguaFusionMobile/LinguaFusionMobile/Info.plist").read_bytes())
project = (ROOT / "ios/LinguaFusionMobile/LinguaFusionMobile.xcodeproj/project.pbxproj").read_text(encoding="utf-8")
check(plist["CFBundleShortVersionString"] == ios["version_name"] and
      plist["CFBundleVersion"] == str(ios["build_number"]), "iOS Info.plist")
check(project.count(f"MARKETING_VERSION = {ios['version_name']};") == 2 and
      project.count(f"CURRENT_PROJECT_VERSION = {ios['build_number']};") == 2 and
      project.count(f"PRODUCT_BUNDLE_IDENTIFIER = {ios['bundle_identifier']};") == 2,
      "iOS Xcode build settings")
swift = (ROOT / "ios/LinguaFusionMobile/LinguaFusionMobile/MobileWebView.swift").read_text(encoding="utf-8")
check(cloud["workspace_url"] in swift, "iOS cloud workspace address")
print("Release manifest matches Online, Android and iOS source metadata.")
