"""Guards on the Android build that are expensive to discover on a phone.

These read the build files rather than building, so they are fast and need no
Android SDK. The failures they catch -- a changed signing key, a version code
that stopped increasing -- do not show up until someone tries to install the
result over an app they already have, and by then the damage is done.
"""
import pathlib
import re
import json
import xml.etree.ElementTree as ET

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
    # Two keys now, deliberately. The debug type keeps the original key so
    # sideloaded copies still upgrade in place; the release type carries the
    # store identity. Crossing them either breaks every sideload upgrade or
    # ships a store build signed with a debug key.
    types = re.search(r'buildTypes\s*\{(.*?)\n    \}', GRADLE, re.S)
    assert types, 'the build types moved; re-check this guard'
    debug = re.search(r'debug \{(.*?)\}', types.group(1), re.S)
    assert debug and 'signingConfigs.debug' in debug.group(1)
    release = re.search(r'release \{(.*?)\}', types.group(1), re.S)
    assert release and 'signingConfigs.release' in release.group(1)


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


def test_the_signing_key_is_not_committed():
    # github.com/Rakshc77/LinguaFusion is public. Committing this key would let
    # anyone sign an APK that Android accepts as an update to the real app, and
    # its password is the standard "android", so the file is the whole secret.
    # Git history is effectively permanent, so this must never land even once.
    import subprocess
    tracked = subprocess.run(['git', 'ls-files', '--', 'android/LinguaFusionMobile'],
                             capture_output=True, text=True,
                             cwd=str(PROJECT.parent.parent))
    if tracked.returncode != 0:
        return  # not a git checkout; nothing to protect
    committed = [line for line in tracked.stdout.splitlines()
                 if line.endswith(('.keystore', '.jks'))]
    assert not committed, f'a signing key is tracked by git: {committed}'


def test_the_version_code_is_not_older_than_the_published_apk():
    # Android refuses to install an older version over the copy on the phone.
    # Equality is valid after publish_android_apk.py records a finished build.
    code = int(re.search(r'versionCode\s+(\d+)', GRADLE).group(1))
    details = json.loads((PROJECT.parent.parent / 'cloud_api' / 'web'
                          / 'android-app.json').read_text(encoding='utf-8'))
    assert code >= details['versionCode'], (
        f'versionCode {code} is older than published {details["versionCode"]}')


def test_selected_and_shared_text_have_one_deliberate_entry_point():
    manifest = ET.parse(PROJECT / 'AndroidManifest.xml').getroot()
    android = '{http://schemas.android.com/apk/res/android}'
    activities = {activity.get(android + 'name'): activity
                  for activity in manifest.find('application').findall('activity')}
    activity = activities.get('.ProcessTextActivity')
    assert activity is not None
    assert activity.get(android + 'exported') == 'true'
    filters = activity.findall('intent-filter')
    actions = {action.get(android + 'name') for entry in filters
               for action in entry.findall('action')}
    assert 'android.intent.action.PROCESS_TEXT' in actions
    assert 'android.intent.action.SEND' in actions
    for entry in filters:
        if entry.find('action') is not None:
            assert any(data.get(android + 'mimeType') == 'text/plain'
                       for data in entry.findall('data'))


def test_text_replacement_is_limited_to_editable_process_text_requests():
    source = (PROJECT / 'src' / 'com' / 'linguafusion' / 'mobile'
              / 'ProcessTextActivity.java').read_text(encoding='utf-8')
    assert 'EXTRA_PROCESS_TEXT_READONLY' in source
    assert 'replaceAllowed = processing' in source
    replacement = source[source.index('private void replaceSelection()'):
                         source.index('private void copyTranslation()')]
    assert 'if (!replaceAllowed' in replacement
    assert 'putExtra(Intent.EXTRA_PROCESS_TEXT, translatedText)' in replacement
    assert 'setResult(RESULT_OK, answer)' in replacement


def test_the_apk_carries_only_64_bit_phone_native_code():
    # ML Kit ships four ABIs. The x86 pair is for emulators, and armeabi-v7a
    # is 11.6 MB for 32-bit phones that could not run a 190 MB speech model.
    abi = re.search(r'abiFilters\s+([^\n]+)', GRADLE)
    assert abi, 'without an abiFilters list the APK triples in size'
    assert 'x86' not in abi.group(1), abi.group(1)
    assert 'armeabi' not in abi.group(1), abi.group(1)
    assert "'arm64-v8a'" in abi.group(1)


def test_the_published_apk_has_no_dead_space_in_it():
    # Gradle's incremental packaging can leave the previous build's data in the
    # APK as an unreferenced hole. It happened here: a 21 MiB APK measured 38
    # MiB, 16 MiB of it a stale copy of a native library nothing pointed at.
    # The APK still installs, so the only symptom is size -- which is exactly
    # what pushes it over the limit Cloud Run will serve.
    import zipfile
    published = PROJECT.parent.parent / 'cloud_api' / 'web' / 'linguafusion-android.apk'
    if not published.is_file():
        return
    with zipfile.ZipFile(published) as archive:
        packed = sum(entry.compress_size for entry in archive.infolist())
    actual = published.stat().st_size
    # Headers, the central directory and alignment are a small overhead; a
    # whole duplicated library is not.
    overhead = actual - packed
    assert overhead < 2 * 1024 * 1024, (
        f'{overhead / 1048576:.1f} MiB of the APK is not entry data. Build it '
        f'with "gradlew clean stageApk" -- incremental packaging left a hole.')


def test_the_published_apk_is_small_enough_for_cloud_run_to_serve():
    # The QR onboarding flow serves this file, and Cloud Run refuses any
    # response over 32 MiB with a 500 from Google's frontend -- not from the
    # app, so nothing in our own logs explains it. At 33.3 MiB every download
    # failed. The only symptom is that nobody can install, so it is guarded.
    published = PROJECT.parent.parent / 'cloud_api' / 'web' / 'linguafusion-android.apk'
    if not published.is_file():
        return  # nothing published on this machine
    limit = 32 * 1024 * 1024
    size = published.stat().st_size
    assert size < limit, (
        f'the published APK is {size / 1048576:.1f} MiB; Cloud Run will not '
        f'serve anything over {limit / 1048576:.0f} MiB')


def test_the_build_still_stages_the_apk_where_publishing_expects_it():
    # scripts/publish_android_apk.py reads this exact path, and the QR download
    # flow serves what that script stages.
    expected = PROJECT.parent.parent / 'scripts' / 'publish_android_apk.py'
    source = expected.read_text(encoding='utf-8')
    assert "'dist' / 'LinguaFusionMobile-debug.apk'" in source.replace('"', "'")
    task = re.search(r"tasks\.register\('stageApk'.*?\n\}", GRADLE, re.S)
    assert task, 'the staging task moved; publishing would break'
    assert "dist" in task.group(0) and 'assembleSideloadDebug' in task.group(0), \
        'publishing must stage the sideload build, the one allowed to self-update'


MAIN = (PROJECT / 'src' / 'com' / 'linguafusion' / 'mobile' / 'MainActivity.java').read_text(encoding='utf-8')


def test_only_the_bundled_page_gets_the_javascript_bridge():
    # The bridge drives the microphone, deletes model files and clears saved
    # settings. The cloud screen deliberately has none; the offline screen has
    # one only because its page ships inside the APK. If the offline WebView
    # could navigate to a remote page, that page would inherit all of it.
    offline = MAIN[MAIN.index('private void showOfflineApp'):MAIN.index('private static boolean isBundledAsset')]
    assert 'addJavascriptInterface' in offline
    assert 'isBundledAsset' in offline, 'the offline WebView must refuse foreign pages'

    guard = MAIN[MAIN.index('private static boolean isBundledAsset'):]
    guard = guard[:guard.index('\n    }')]
    # Served over a real origin now, because a module script cannot load from
    # file://. The guard still has to pin it to our own assets and nothing else.
    assert '"https".equalsIgnoreCase' in guard, guard
    assert 'appassets.androidplatform.net' in guard, guard
    assert '/assets/offline/' in guard, guard

    cloud = MAIN[MAIN.index('private void showCloudApp'):MAIN.index('private void saveDataUrl')]
    assert 'addJavascriptInterface' not in cloud, \
        'the cloud page must never receive a native bridge'


def test_the_bridge_is_removed_when_the_web_view_goes():
    teardown = MAIN[MAIN.index('private void releaseWebView'):]
    teardown = teardown[:teardown.index('\n    }')]
    for name in ['LinguaFusionNative', 'LinguaFusionOffline']:
        assert f'removeJavascriptInterface("{name}")' in teardown, name


def test_a_denied_microphone_is_not_reported_as_a_started_recording():
    # startNativeAudioRecording answers "OK", "ERROR: ..." or
    # "PERMISSION_REQUIRED". Folding the last into success leaves the page
    # saying "speak now" over a microphone that was never opened, and the only
    # symptom is an empty recording afterwards.
    host = MAIN[MAIN.index('private final class OfflineHost'):]
    host = host[:host.index('/** The owner-hosted cloud service')]
    start = host[host.index('public String startRecording'):host.index('public void cancelRecording')]
    # Comments stripped first: a guard that a comment can satisfy guards
    # nothing, and the explaining comment here names the very constant that
    # the code must act on.
    code = re.sub(r'//[^\n]*', '', start)
    assert '"PERMISSION_REQUIRED".equals(result)' in code,         'the permission case must be branched on, not merely described'
    assert '"OK".equals(result)' in code,         'success must be recognised positively, not by elimination'


def test_offline_recordings_are_length_capped():
    # Transcription turns each 2-byte sample into a 4-byte float, so an
    # uncapped recording is an uncapped allocation. The cloud path is capped by
    # its dialog; the offline path needs its own.
    import re
    writer = MAIN[MAIN.index('private void writeNativePcm'):]
    writer = writer[:writer.index('\n    }')]
    assert 'Integer.MAX_VALUE' in writer, 'the PC path is unchanged and still unbounded'
    assert 'OFFLINE_RECORDING_SECONDS' in writer, 'offline recordings must be capped'
    seconds = int(re.search(r'OFFLINE_RECORDING_SECONDS = (\d+)', MAIN).group(1))
    assert 0 < seconds <= 600, seconds


def test_the_offline_page_ships_in_the_apk():
    offline = PROJECT / 'assets' / 'offline'
    assert (offline / 'index.html').is_file()
    assert (offline / 'app.js').is_file()
    page = (offline / 'index.html').read_text(encoding='utf-8')
    # It must render with no network at all: nothing may be fetched.
    for remote in ['http://', 'https://', '//cdn', 'fonts.googleapis']:
        assert remote not in page, f'the offline page must not reference {remote}'


# The downloader now belongs to the sideload flavour: the Play build must not
# carry one at all.
UPDATER = (PROJECT / 'src-sideload' / 'com' / 'linguafusion' / 'mobile'
           / 'AppUpdate.java').read_text(encoding='utf-8')


def test_an_update_is_checksummed_before_it_reaches_the_installer():
    # This downloads an executable over the public internet and asks Android to
    # install it over the running app. The published SHA-256 must be verified
    # first, and a mismatch must destroy the file rather than leave it for a
    # later attempt to pick up.
    body = UPDATER[UPDATER.index('String downloadAndInstall'):UPDATER.index('private String install(')]
    verify = body.index('sha256(target)')
    handoff = body.index('return install(target);')
    assert verify < handoff, 'the file is handed to the installer before it is checked'

    mismatch = body[verify:handoff]
    assert 'target.delete()' in mismatch, 'a file that fails its checksum must be deleted'
    assert 'equalsIgnoreCase' in body[:verify + 60], 'hex digests differ only in case'


def test_a_published_update_must_declare_a_version_and_a_digest():
    # Without a versionCode the app cannot tell new from old; without a valid
    # digest there is nothing to verify the download against. Either one
    # missing means offer nothing, not offer blindly.
    check = UPDATER[UPDATER.index('Available check()'):UPDATER.index('boolean canInstall')]
    assert 'published <= installedVersion(context)' in check, \
        'it must compare against what is installed, not merely find a version'
    assert '[0-9a-f]{64}' in check, 'a malformed digest must stop the offer'
    assert 'return null;' in check


def test_the_installer_permission_is_declared():
    manifest = (PROJECT / 'AndroidManifest.xml').read_text(encoding='utf-8')
    assert 'android.permission.REQUEST_INSTALL_PACKAGES' in manifest, \
        'without it the update flow silently does nothing'


def test_package_installer_confirmation_is_actually_opened():
    # PackageInstaller does not open its confirmation UI just because a
    # session was committed. It returns STATUS_PENDING_USER_ACTION and nests
    # the confirmation Intent in EXTRA_INTENT. Ignoring that callback was the
    # reason 1.14 downloaded successfully and then appeared to do nothing.
    receiver = (SIDELOAD / 'UpdateInstallReceiver.java').read_text(encoding='utf-8')
    assert 'PackageInstaller.STATUS_PENDING_USER_ACTION' in receiver
    assert 'Intent.EXTRA_INTENT' in receiver
    assert 'context.startActivity(confirmation)' in receiver
    assert 'PackageInstaller.EXTRA_STATUS_MESSAGE' in receiver, \
        'installer failures must be visible instead of silently repeating the offer'

    install = UPDATER[UPDATER.index('private String install('):]
    assert 'setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_REQUIRED)' in install
    assert 'PendingIntent.FLAG_UPDATE_CURRENT' in install
    assert 'PendingIntent.FLAG_MUTABLE' in install
    assert 'PendingIntent.getBroadcast' in install

    manifest = (PROJECT / 'src-sideload' / 'AndroidManifest.xml').read_text(encoding='utf-8')
    assert '.UpdateInstallReceiver' in manifest
    assert 'android:exported="false"' in manifest, \
        'the installer callback must not accept fabricated intents from other apps'


def test_a_failed_update_check_stays_quiet():
    # The check runs unprompted on launch. A network failure there is not the
    # person's problem and must not produce an error they did not ask for.
    check = UPDATER[UPDATER.index('Available check()'):UPDATER.index('boolean canInstall')]
    catch = check[check.index('catch (Exception'):]
    assert 'return null' in catch[:120], 'a failed check must be silent, not an error'


def test_the_publisher_records_the_version_it_published():
    # The app compares against this. If publishing stops writing it, every
    # future update becomes invisible and people go back to reinstalling.
    script = (PROJECT.parent.parent / 'scripts' / 'publish_android_apk.py').read_text(encoding='utf-8')
    assert "'versionCode'" in script and "'versionName'" in script
    assert 'dump' in script and 'badging' in script, 'the version must come from the APK itself'


def test_both_modes_share_one_appearance():
    # The offline page ships inside the APK so it cannot link the hosted
    # stylesheets, and hand-maintained copies drifted: the owner saw the two
    # modes wearing different faces on the phone. The copies must be identical
    # to the originals, and made by scripts/sync_offline_appearance.py.
    import filecmp
    web = PROJECT.parent.parent / 'cloud_api' / 'web'
    offline = PROJECT / 'assets' / 'offline'
    for name in ['linguafusion-themes.css', 'pilot.css', 'themes.mjs']:
        assert (offline / name).is_file(), f'{name} is not bundled in the APK'
        assert filecmp.cmp(web / name, offline / name, shallow=False), (
            f'{name} has drifted from the online app. '
            f'Run scripts/sync_offline_appearance.py and rebuild.')

    page = (offline / 'index.html').read_text(encoding='utf-8')
    assert 'linguafusion-themes.css' in page and 'pilot.css' in page, \
        'the offline page must use the shared stylesheets, not its own palette'
    # A private palette is what caused the drift; catch its return.
    assert '--lf-app-bg:#' not in page and '--accent:#' not in page, \
        'the offline page redefines theme colours instead of inheriting them'


def test_an_update_is_never_pushed_at_launch():
    # An update offer that appears unbidden every launch is a nag. It is
    # offered only when someone asks for it.
    updater = (SIDELOAD / 'AppUpdater.java').read_text(encoding='utf-8')
    assert 'offerUpdateIfAny' not in MAIN + updater, 'the launch-time update check is back'
    onresume = re.search(r'protected void onResume\(\)\{(.*?)\n    \}', MAIN, re.S)
    if onresume:
        assert 'AppUpdate' not in onresume.group(1), 'onResume must not check for updates'
    assert 'checkForUpdate(' in MAIN, 'the explicit check must still exist'


def test_the_app_tells_the_page_what_its_own_check_found():
    global MAIN
    # One button asks about two things. The page can only see the interface, so
    # if the app stays silent the status line says "up to date" while meaning
    # only half of it -- which is what the owner saw.
    # The check moved into the flavour; the reporting stayed with the page.
    updater = (SIDELOAD / 'AppUpdater.java').read_text(encoding='utf-8')
    check = updater[updater.index('static void check('):]
    check = check[:check.index('\n    }')]
    assert 'listener.onChecked(' in check, \
        'the updater must answer the caller, not only raise a dialog'
    report = MAIN[MAIN.index('private void checkForUpdate(String requestId)'):]
    report = report[:report.index('\n    }')]
    assert 'LFNativeUpdateResult' in report
    assert 'JSONObject.quote' in report, 'the payload must cross as data, not script'


def test_the_offline_page_is_served_from_an_origin_modules_can_load_from():
    # The page uses an ES module script, and module scripts need CORS. Served
    # from file:///android_asset the origin is opaque, the import is refused,
    # and the whole script silently never runs: the page renders correctly --
    # stylesheets are not modules -- while every button is dead. It must come
    # from a real origin, which WebViewAssetLoader provides out of the APK.
    page = (PROJECT / 'assets' / 'offline' / 'index.html').read_text(encoding='utf-8')
    uses_modules = 'type="module"' in page or "type='module'" in page
    app = (PROJECT / 'assets' / 'offline' / 'app.js').read_text(encoding='utf-8')
    imports = bool(re.search(r'^\s*import\s', app, re.M))
    if not (uses_modules or imports):
        return  # a classic script is fine from anywhere

    origin = re.search(r'OFFLINE_PAGE = ([^;]+);', MAIN)
    assert origin, 'the offline page URL moved; re-check this guard'
    assert 'file://' not in origin.group(1), \
        'a module script cannot load from file://; serve it over an origin'
    assert 'WebViewAssetLoader' in MAIN, \
        'something must map that origin onto the APK assets'
    # The call, not the method name: overriding shouldInterceptRequest and
    # returning null leaves the name in the file and every asset unserved.
    assert 'assets.shouldInterceptRequest(' in MAIN, \
        'the loader has to actually serve, not merely be constructed'


PLAY = PROJECT / 'src-play' / 'com' / 'linguafusion' / 'mobile'
SIDELOAD = PROJECT / 'src-sideload' / 'com' / 'linguafusion' / 'mobile'


def test_the_play_build_cannot_update_itself():
    # Google Play's Device and Network Abuse policy forbids an app it
    # distributes from replacing itself by any route but Play. Breaking this
    # is not a bug report, it is a removal from the store, so the downloader
    # is absent from the flavour rather than disabled inside it.
    assert (SIDELOAD / 'AppUpdate.java').is_file(), 'the downloader belongs to sideload'
    assert not (PLAY / 'AppUpdate.java').is_file(), 'the Play flavour must not carry a downloader'
    for flavour in [PLAY, SIDELOAD]:
        assert (flavour / 'AppUpdater.java').is_file(), f'{flavour.name} needs its own updater'
    play = (PLAY / 'AppUpdater.java').read_text(encoding='utf-8')
    assert 'return false;' in play, 'the Play updater must report itself unsupported'
    for banned in ['PackageInstaller', 'downloadAndInstall', 'HttpURLConnection']:
        assert banned not in play, f'the Play updater must not reference {banned}'

    manifest = (PROJECT / 'src-play' / 'AndroidManifest.xml').read_text(encoding='utf-8')
    assert 'REQUEST_INSTALL_PACKAGES' in manifest and 'tools:node="remove"' in manifest, \
        'the install permission must be removed from the Play manifest'


def test_a_release_build_cannot_fall_back_to_the_debug_key():
    # Signing a store build with the debug key would produce something that
    # looks shippable and is not, and the mistake only shows at upload.
    release = re.search(r'release \{(.*?)\n        \}', GRADLE, re.S)
    assert release, 'the release signing config moved; re-check this guard'
    assert 'debug' not in release.group(1), 'release signing must not reference the debug key'
    types = re.search(r'buildTypes \{(.*?)\n    \}', GRADLE, re.S)
    assert 'signingConfig signingConfigs.release' in types.group(1), \
        'the release build type must use the release key'


def test_no_signing_material_is_in_the_repository():
    # The release key is a store identity as well as an upgrade path. It lives
    # outside the checkout, and this repository is public.
    import subprocess
    tracked = subprocess.run(['git', 'ls-files'], capture_output=True, text=True,
                             cwd=str(PROJECT.parent.parent))
    if tracked.returncode != 0:
        return
    bad = [line for line in tracked.stdout.splitlines()
           if line.endswith(('.keystore', '.jks')) or 'signing.properties' in line]
    assert not bad, f'signing material is tracked by git: {bad}'
