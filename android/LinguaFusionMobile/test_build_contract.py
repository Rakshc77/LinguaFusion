"""Guards on the Android build that are expensive to discover on a phone.

These read the build files rather than building, so they are fast and need no
Android SDK. The failures they catch -- a changed signing key, a version code
that stopped increasing -- do not show up until someone tries to install the
result over an app they already have, and by then the damage is done.
"""
import pathlib
import re

PROJECT = pathlib.Path(__file__).parent
GRADLE = (PROJECT / 'build.gradle').read_text(encoding='utf-8')

# The certificate the original hand-rolled build signed with, read back from
# the keystore with keytool. Android identifies an app by package name AND
# signature: sign with anything else and the only way to install is to
# uninstall first, which throws away everything stored on the device.
EXPECTED_SIGNER = '2cdb19692817f5c591f3f92fd07b657779e204496a57c23f159983ae6dc8514e'


def test_the_app_is_still_signed_with_the_original_debug_keystore():
    signing = re.search(r'signingConfigs\s*\{(.*?)\n    \}', GRADLE, re.S)
    assert signing, 'the signing block moved; re-check this guard'
    assert "storeFile file('debug.keystore')" in signing.group(1)
    assert "keyAlias 'androiddebugkey'" in signing.group(1)
    # Both build types must use it, or a release build silently gets a
    # different key and stops installing over existing copies.
    types = re.search(r'buildTypes\s*\{(.*?)\n    \}', GRADLE, re.S)
    assert types and types.group(1).count('signingConfig signingConfigs.debug') == 2


def test_the_signing_keystore_is_present_and_unchanged():
    # The keystore is not in git. If it is ever lost, this fails loudly rather
    # than the build quietly generating a new key and breaking every upgrade.
    import subprocess
    keystore = PROJECT / 'debug.keystore'
    assert keystore.is_file(), (
        'debug.keystore is missing. It is not in git and cannot be regenerated '
        'identically; without it no build can install over an existing copy.')
    keytool = pathlib.Path(r'C:\Program Files\Android\Android Studio\jbr\bin\keytool.exe')
    if not keytool.is_file():
        return  # nothing to check against on a machine without the JDK
    listed = subprocess.run(
        [str(keytool), '-list', '-v', '-keystore', str(keystore), '-storepass',
         'android', '-alias', 'androiddebugkey'], capture_output=True, text=True)
    digest = re.search(r'SHA256:\s*([0-9A-F:]+)', listed.stdout)
    assert digest, listed.stdout[-400:]
    assert digest.group(1).replace(':', '').lower() == EXPECTED_SIGNER, \
        'the keystore holds a different certificate; upgrades would break'


def test_the_version_code_only_ever_goes_up():
    # Android refuses to install a lower version code over a higher one, and
    # the last hand-built APK shipped 6.
    code = int(re.search(r'versionCode\s+(\d+)', GRADLE).group(1))
    assert code > 6, f'versionCode {code} would not install over the shipped 6'


def test_the_apk_carries_no_emulator_only_native_code():
    # ML Kit ships four ABIs. The x86 pair is 35 MB that no phone can use, and
    # this app is only ever installed on phones.
    abi = re.search(r'abiFilters\s+([^\n]+)', GRADLE)
    assert abi, 'without an abiFilters list the APK doubles in size'
    assert 'x86' not in abi.group(1), abi.group(1)
    assert "'arm64-v8a'" in abi.group(1)


def test_the_build_still_stages_the_apk_where_publishing_expects_it():
    # scripts/publish_android_apk.py reads this exact path, and the QR download
    # flow serves what that script stages.
    expected = PROJECT.parent.parent / 'scripts' / 'publish_android_apk.py'
    source = expected.read_text(encoding='utf-8')
    assert "'dist' / 'LinguaFusionMobile-debug.apk'" in source.replace('"', "'")
    task = re.search(r"tasks\.register\('stageApk'.*?\n\}", GRADLE, re.S)
    assert task, 'the staging task moved; publishing would break'
    assert "dist" in task.group(0) and 'assembleDebug' in task.group(0)
