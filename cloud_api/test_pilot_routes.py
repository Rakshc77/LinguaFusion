"""Readiness gate 6: provider adapters reached only through the managed policy.

These tests are fully offline. Every provider call is served by a MockTransport,
so nothing here can spend the lifetime allowance.
"""
import io
import sqlite3
import tempfile
import wave
import weakref

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from cloud_api.app import Settings, create_app
from cloud_api.pilot_capabilities import (DEFAULT_TRANSLATION_MODEL, PILOT_HOLD_MICRO,
                                          PilotGateway)
from cloud_api.policy import LocalPolicy
from cloud_api.test_budget import TestBudget

FEATURES = frozenset({'translate', 'pronounce', 'transcribe', 'ocr'})
DEFAULT_CHARGE = 'pilot:openrouter/' + DEFAULT_TRANSLATION_MODEL
AUTH = {'Authorization': 'Bearer valid'}
HINDI = 'नमस्ते'


def verify(token):
    if token == 'valid':
        return {'uid': 'friend'}
    raise HTTPException(401, 'Invalid token')


def mono_wav(seconds=1):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as writer:
        writer.setparams((1, 2, 16000, 0, 'NONE', 'NONE'))
        writer.writeframes(b'\x00' * (32000 * seconds))
    return buffer.getvalue()


def build(handler, features=FEATURES, budget_micro=1_000_000, openrouter='key', groq='key'):
    """Return (client, policy, test-budget path). Both ledgers are real SQLite."""
    directory = tempfile.TemporaryDirectory()
    policy = LocalPolicy(directory.name + '/policy.sqlite3', ['friend'])
    policy.update('owner', 'friend', True, 100, budget_micro)
    budget_path = directory.name + '/budget.sqlite3'
    settings = Settings(project='test-project', allowed_uids=frozenset({'friend'}),
                        enabled=True, pilot_features=features, test_budget_path=budget_path,
                        openrouter_key=openrouter, groq_key=groq)
    # A stub token keeps the suite offline: the real minter would call Google.
    client = TestClient(create_app(settings, verify, httpx.MockTransport(handler), policy=policy,
                                   vision_token=lambda: 'stub-access-token'))
    weakref.finalize(client, directory.cleanup)
    return client, policy, budget_path


def charges(policy):
    with sqlite3.connect(policy.path) as db:
        return db.execute('SELECT model,reserved,actual,state FROM charges ORDER BY rowid').fetchall()


def holds(budget_path):
    with sqlite3.connect(budget_path) as db:
        return db.execute('SELECT provider,reserved,actual FROM test_requests ORDER BY rowid').fetchall()


def ok_completion(text='Hallo'):
    def handler(request):
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': text}}]})
    return handler


def unexpected(message):
    def handler(request):
        raise AssertionError(message)
    return handler


def test_capabilities_stay_off_until_the_owner_enables_them():
    client, _, _ = build(ok_completion(), features=frozenset())
    with client:
        body = client.get('/capabilities', headers=AUTH).json()
        assert body['features'] == {'translation': False, 'speech': False, 'ocr': False,
                                    'pronunciation': False, 'tts': False, 'notes': False}
        assert body['pronunciation_languages'] == []
        # Disabled is an explicit refusal, not a silent no-op.
        assert client.post('/api/translate', headers=AUTH,
                           data={'text': 'Hello', 'target_lang': 'de', 'paid_consent': 'true'}).status_code == 503


def test_disabled_capability_touches_neither_ledger():
    client, policy, budget_path = build(ok_completion(), features=frozenset({'ocr'}))
    with client:
        assert client.post('/api/translate', headers=AUTH,
                           data={'text': 'Hello', 'target_lang': 'de', 'paid_consent': 'true'}).status_code == 503
    assert charges(policy) == []
    assert holds(budget_path) == []


def test_capability_hidden_when_its_credential_is_missing():
    client, _, _ = build(ok_completion(), openrouter='')
    with client:
        body = client.get('/capabilities', headers=AUTH).json()
        assert body['features']['translation'] is False
        assert body['features']['pronunciation'] is False
        assert body['features']['speech'] is True
        assert client.post('/api/translate', headers=AUTH,
                           data={'text': 'Hello', 'target_lang': 'de', 'paid_consent': 'true'}).status_code == 503


def test_paid_consent_is_required_on_every_request():
    client, policy, budget_path = build(ok_completion())
    with client:
        response = client.post('/api/translate', headers=AUTH, data={'text': 'Hello', 'target_lang': 'de'})
    assert response.status_code == 422
    assert charges(policy) == [] and holds(budget_path) == []


def test_unauthenticated_request_never_reaches_a_provider():
    client, policy, budget_path = build(unexpected('unauthenticated request reached a provider'))
    with client:
        response = client.post('/api/translate', data={'text': 'Hi', 'target_lang': 'de', 'paid_consent': 'true'})
    assert response.status_code == 401
    assert charges(policy) == [] and holds(budget_path) == []


def test_success_records_a_hold_in_both_ledgers():
    client, policy, budget_path = build(ok_completion())
    with client:
        response = client.post('/api/translate', headers=AUTH,
                               data={'text': 'Hello', 'target_lang': 'de', 'paid_consent': 'true'})
    assert response.status_code == 200
    assert response.json()['translated_text'] == 'Hallo'
    assert charges(policy) == [(DEFAULT_CHARGE, PILOT_HOLD_MICRO, None, 'unresolved')]
    assert holds(budget_path) == [('openrouter', PILOT_HOLD_MICRO, None)]


def test_pronunciation_keeps_native_text_and_marks_it_approximate():
    client, _, _ = build(ok_completion('Namaste'))
    with client:
        body = client.post('/api/pronounce', headers=AUTH,
                           data={'text': HINDI, 'language': 'hi', 'paid_consent': 'true'}).json()
    assert body['native'] == HINDI
    assert body['romanized'] == 'Namaste'
    assert body['approximate'] is True
    assert 'not an English translation' in body['notice']


def test_pronunciation_refuses_an_unsupported_language_before_dispatch():
    client, policy, budget_path = build(unexpected('unsupported language reached a provider'))
    with client:
        response = client.post('/api/pronounce', headers=AUTH,
                               data={'text': 'Hello', 'language': 'en', 'paid_consent': 'true'})
    assert response.status_code == 422
    assert charges(policy) == [] and holds(budget_path) == []


def test_provider_failure_retains_both_holds_and_does_not_retry():
    attempts = []

    def handler(request):
        attempts.append(request.url.host)
        return httpx.Response(500, json={'error': 'upstream'})

    client, policy, budget_path = build(handler)
    with client:
        response = client.post('/api/translate', headers=AUTH,
                               data={'text': 'Hello', 'target_lang': 'de', 'paid_consent': 'true'})
    assert response.status_code == 502
    assert len(attempts) == 1, 'a failed paid request must never be retried'
    # The provider may still bill for this, so neither hold may be released.
    assert charges(policy) == [(DEFAULT_CHARGE, PILOT_HOLD_MICRO, None, 'unresolved')]
    assert holds(budget_path) == [('openrouter', PILOT_HOLD_MICRO, None)]


def test_exhausted_lifetime_allowance_blocks_dispatch_and_settles_the_policy_hold_to_zero():
    client, policy, budget_path = build(unexpected('dispatched despite an exhausted lifetime allowance'))
    with client:
        # Consume the whole shared allowance outside this user's policy.
        TestBudget(budget_path).reserve('groq', 5_000_000)
        response = client.post('/api/translate', headers=AUTH,
                               data={'text': 'Hello', 'target_lang': 'de', 'paid_consent': 'true'})
    assert response.status_code == 422
    # Nothing was sent, so the per-user hold settles to a truthful zero instead
    # of inflating this user's monthly spend for a request that never happened.
    assert charges(policy) == [(DEFAULT_CHARGE, PILOT_HOLD_MICRO, 0, 'usage_estimate')]
    assert [row for row in holds(budget_path) if row[0] == 'openrouter'] == []


def test_exhausted_user_budget_blocks_dispatch_before_the_lifetime_allowance():
    client, policy, budget_path = build(unexpected('dispatched despite an exhausted user budget'),
                                        budget_micro=PILOT_HOLD_MICRO - 1)
    with client:
        response = client.post('/api/translate', headers=AUTH,
                               data={'text': 'Hello', 'target_lang': 'de', 'paid_consent': 'true'})
    assert response.status_code == 429
    # The scarce shared allowance stays untouched when the per-user budget
    # already refuses the request.
    assert holds(budget_path) == []


def test_transcription_accepts_audio_larger_than_the_text_body_cap():
    audio = mono_wav(seconds=5)
    assert len(audio) > 64 * 1024, 'fixture must exceed the default text body cap'

    def handler(request):
        assert request.url.host == 'api.groq.com'
        return httpx.Response(200, json={'text': 'hello there'})

    client, _, budget_path = build(handler)
    with client:
        response = client.post('/api/transcribe', headers=AUTH, data={'paid_consent': 'true'},
                               files={'audio': ('a.wav', audio, 'audio/wav')})
    assert response.status_code == 200
    assert response.json()['text'] == 'hello there'
    assert holds(budget_path) == [('groq', PILOT_HOLD_MICRO, None)]


def test_silence_is_returned_unchanged_not_corrected():
    def handler(request):
        return httpx.Response(200, json={'text': ''})

    client, _, _ = build(handler)
    with client:
        body = client.post('/api/transcribe', headers=AUTH, data={'paid_consent': 'true'},
                           files={'audio': ('a.wav', mono_wav(), 'audio/wav')}).json()
    assert body['ok'] is True and body['text'] == ''


def test_oversized_upload_is_refused_before_the_provider():
    client, policy, budget_path = build(unexpected('oversized upload reached a provider'))
    with client:
        response = client.post('/api/transcribe', headers=AUTH, data={'paid_consent': 'true'},
                               files={'audio': ('a.wav', b'\x00' * (6 * 1024 * 1024), 'audio/wav')})
    assert response.status_code == 413
    assert charges(policy) == [] and holds(budget_path) == []


def test_text_route_keeps_the_small_body_cap():
    client, _, _ = build(unexpected('oversized text reached a provider'))
    with client:
        response = client.post('/api/translate', headers=AUTH,
                               data={'text': 'x' * (128 * 1024), 'target_lang': 'de', 'paid_consent': 'true'})
    assert response.status_code == 413


def test_ocr_rejects_a_non_image_without_spending():
    client, _, budget_path = build(unexpected('non-image reached the OCR provider'))
    with client:
        response = client.post('/api/ocr', headers=AUTH, data={'paid_consent': 'true'},
                               files={'image': ('doc.pdf', b'%PDF-1.7 fixture', 'application/pdf')})
    assert response.status_code == 422
    assert 'PNG or JPEG' in response.json()['detail']
    assert holds(budget_path) == []


def test_gateway_refuses_an_unknown_capability_name():
    with pytest.raises(RuntimeError):
        PilotGateway(object(), object(), frozenset({'summarise'}))


def test_cloud_run_refuses_a_local_lifetime_ledger(monkeypatch):
    # On Cloud Run the SQLite file is ephemeral, so the whole allowance would be
    # re-granted on every cold start.
    monkeypatch.setenv('K_SERVICE', 'linguafusion-cloud')
    settings = Settings(project='p', owner_uid='owner', policy_backend='firestore',
                        pilot_features=FEATURES, test_budget_path='/tmp/budget.sqlite3')
    with pytest.raises(RuntimeError, match='cannot back paid capabilities on Cloud Run'):
        create_app(settings, verify, None, policy=object())


def test_pilot_page_and_controller_agree_on_every_element_id():
    # A typo in $('...') fails silently at runtime and would break the pane only
    # once a signed-in user reached it, so check the contract statically.
    import pathlib
    import re
    web = pathlib.Path(__file__).parent / 'web'
    page_ids = set(re.findall(r'id="([^"]+)"', (web / 'index.html').read_text(encoding='utf-8')))
    used_ids = set(re.findall(r"\$\('([^']+)'\)", (web / 'pilot.mjs').read_text(encoding='utf-8')))
    assert not used_ids - page_ids, f'pilot.mjs references missing element ids: {sorted(used_ids - page_ids)}'
    for required in ['pronunciationPane', 'pronounceText', 'pronounceLanguage', 'pronounceConsent',
                     'pronounceNative', 'pronounceRoman', 'pronounceNotice', 'copyNative', 'copyRoman']:
        assert required in page_ids, f'the pronunciation pane lost #{required}'


def test_pronunciation_module_is_served_but_tests_are_not():
    client, _, _ = build(ok_completion())
    with client:
        assert client.get('/pilot/pronunciation.mjs').status_code == 200
        assert client.get('/pilot/pronunciation.test.mjs').status_code == 404


def test_container_build_copies_every_module_the_app_imports():
    # A module missing from the Dockerfile crashes the container at startup, and
    # only in the deployed environment. Check the build context statically.
    import ast
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    dockerfile = (root / 'cloud_api' / 'Dockerfile').read_text(encoding='utf-8')
    dockerignore = (root / 'cloud_api' / 'Dockerfile.dockerignore').read_text(encoding='utf-8')

    imported = set()
    for source in ['app.py', 'pilot_capabilities.py', 'pilot_providers.py', 'firestore_policy.py']:
        tree = ast.parse((root / 'cloud_api' / source).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or '').startswith(('cloud_api', 'backend')):
                imported.add(node.module.replace('.', '/') + '.py')

    assert imported, 'no first-party imports discovered; the check would pass vacuously'
    for module in sorted(imported):
        assert module in dockerfile, f'{module} is imported but never COPYed into the image'
        assert '!' + module in dockerignore, f'{module} is excluded by the build context allowlist'


def test_container_never_ships_ledgers_or_credentials():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    dockerfile = (root / 'cloud_api' / 'Dockerfile').read_text(encoding='utf-8')
    for forbidden in ['local-data', 'credentials', '.sqlite3', 'application_default']:
        assert forbidden not in dockerfile, f'the image must never contain {forbidden}'


def test_a_consent_checkbox_is_never_disabled_by_its_own_fieldset():
    # The consent box sits inside #pronounceFields. Gating that fieldset on the
    # checkbox disables the control the user needs to proceed -- an unescapable
    # deadlock that looks like a dead pane. Gate the submit button instead.
    import pathlib
    import re
    web = pathlib.Path(__file__).parent / 'web'
    page = (web / 'index.html').read_text(encoding='utf-8')
    script = (web / 'pilot.mjs').read_text(encoding='utf-8')

    fieldset = re.search(r'<fieldset id="pronounceFields".*?</fieldset>', page, re.S)
    assert fieldset, 'the pronunciation fieldset moved; re-check this guard'
    assert 'pronounceConsent' in fieldset.group(0), 'guard assumes the checkbox is inside the fieldset'

    for line in script.splitlines():
        if "$('pronounceFields').disabled" in line and '=' in line:
            assert 'pronounceConsent' not in line, (
                'the fieldset containing the consent checkbox must not be gated on that checkbox')
    assert re.search(r"\$\('pronounce'\)\.disabled\s*=.*pronounceConsent", script), \
        'the submit button should be what consent gates'


def test_the_raw_uid_form_is_hidden_behind_a_toggle():
    # The field takes a Firebase UID and invites an email address instead.
    # Approving from the request queue is the intended path, so the manual form
    # ships collapsed rather than sitting open next to it.
    import pathlib
    import re
    web = pathlib.Path(__file__).parent / 'web'
    page = (web / 'index.html').read_text(encoding='utf-8')
    script = (web / 'pilot.mjs').read_text(encoding='utf-8')

    form = re.search(r'<form id="ownerPolicyForm"([^>]*)>', page)
    assert form, 'the owner policy form moved'
    assert 'hidden' in form.group(1), 'the raw UID form must ship collapsed'
    assert 'id="toggleAdvanced"' in page, 'there must be a control to open it'
    assert 'not an email address' in page, 'the field should say what it expects'
    # Choosing "Edit policy" on a user must open the form, or it silently does nothing.
    assert 'showAdvanced(true)' in script


def test_the_installable_app_assets_are_served_and_tests_are_not():
    client, _, _ = build(ok_completion())
    with client:
        for asset, media in [('manifest.webmanifest', 'application/manifest+json'),
                             ('icon.svg', 'image/svg+xml'),
                             ('sw.js', 'text/javascript'),
                             ('wav.mjs', 'text/javascript')]:
            response = client.get('/pilot/' + asset)
            assert response.status_code == 200, asset
            assert response.headers['content-type'].startswith(media), (asset, response.headers['content-type'])
        # A worker may only control paths at or below its own directory.
        assert client.get('/pilot/sw.js').headers.get('service-worker-allowed') == '/pilot/'
        for hidden in ['wav.test.mjs', 'pronunciation.test.mjs', 'cloud-auth.test.mjs']:
            assert client.get('/pilot/' + hidden).status_code == 404, hidden


def test_the_page_policy_allows_the_worker_and_manifest_but_stays_closed():
    client, _, _ = build(ok_completion())
    with client:
        policy = client.get('/pilot/').headers['content-security-policy']
    for required in ["manifest-src 'self'", "worker-src 'self'", "default-src 'none'",
                     "frame-ancestors 'none'", "base-uri 'none'"]:
        assert required in policy, required
    # Nothing may be widened to a wildcard while adding app features.
    assert '*' not in policy, policy


def test_the_service_worker_never_caches_api_responses():
    # A cached /capabilities or /usage would show one person's approval state
    # and spending to the next person on a shared device.
    import pathlib
    worker = (pathlib.Path(__file__).parent / 'web' / 'sw.js').read_text(encoding='utf-8')
    for route in ['/api/', '/owner/', '/usage', '/capabilities', '/access/']:
        assert route not in worker.split('const SHELL')[1].split(']')[0], route
    assert 'SHELL.includes(url.pathname)' in worker, 'caching must be restricted to the static shell'


def test_owner_decisions_never_depend_on_a_browser_dialog():
    # window.confirm() returns false without displaying anything in installed
    # PWAs, Android WebViews, and pages where dialogs were suppressed. Using it
    # made Approve silently do nothing, with no error shown.
    import pathlib
    import re
    script = (pathlib.Path(__file__).parent / 'web' / 'pilot.mjs').read_text(encoding='utf-8')
    code = '\n'.join(line for line in script.splitlines() if not line.strip().startswith('//'))
    for blocked in [r'\bconfirm\s*\(', r'\balert\s*\(', r'\bprompt\s*\(']:
        assert not re.search(blocked, code), f'{blocked} blocks the UI where dialogs are suppressed'
    assert 'confirmInPage' in code, 'decisions must confirm inside the page'


def test_the_android_build_is_downloadable_without_an_account():
    # Someone arriving from the invite has no account yet, so the APK must be
    # reachable unauthenticated. It carries no secret and grants nothing on its
    # own: sign-in and owner approval still gate every capability.
    client, _, _ = build(ok_completion())
    with client:
        apk = client.get('/pilot/linguafusion-android.apk')
        assert apk.status_code == 200
        assert apk.headers['content-type'].startswith('application/vnd.android.package-archive')
        assert 'attachment' in apk.headers.get('content-disposition', ''), \
            'the APK must download, never render in the browser'
        assert apk.content[:2] == b'PK', 'that is not an APK'

        details = client.get('/pilot/android-app.json')
        assert details.status_code == 200
        body = details.json()
        assert len(body['sha256']) == 64
        assert body['bytes'] == len(apk.content)


def test_the_published_apk_matches_its_advertised_fingerprint():
    # The page shows this fingerprint so someone can check what they installed.
    # If the two ever drift, the check is worse than useless.
    import hashlib
    import json
    import pathlib
    web = pathlib.Path(__file__).parent / 'web'
    payload = (web / 'linguafusion-android.apk').read_bytes()
    details = json.loads((web / 'android-app.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(payload).hexdigest() == details['sha256']
    assert len(payload) == details['bytes']


def test_the_published_apk_carries_no_credential():
    import pathlib
    import re
    payload = (pathlib.Path(__file__).parent / 'web' / 'linguafusion-android.apk').read_bytes()
    for pattern in [rb'sk-or-[A-Za-z0-9_-]{6,}', rb'gsk_[A-Za-z0-9_-]{6,}',
                    rb'AIza[A-Za-z0-9_-]{10,}', rb'BEGIN [A-Z ]*PRIVATE KEY']:
        assert not re.search(pattern, payload), f'{pattern} found inside a published binary'


def test_the_service_worker_does_not_cache_the_android_build():
    # A stale cached APK would be installed while the page advertised a newer
    # fingerprint, making the fingerprint check fail for no good reason.
    import pathlib
    worker = (pathlib.Path(__file__).parent / 'web' / 'sw.js').read_text(encoding='utf-8')
    shell = worker.split('const SHELL')[1].split(']')[0]
    assert '.apk' not in shell and 'android-app.json' not in shell


def test_a_changed_shell_asset_forces_a_new_cache_version():
    # The service worker serves the cached shell first. Shipping an edited
    # asset without bumping VERSION leaves every already-installed copy --
    # phone home screens and the Android app included -- running the old code
    # indefinitely, with no error anywhere to suggest why.
    import hashlib
    import pathlib
    import re
    web = pathlib.Path(__file__).parent / 'web'
    worker = (web / 'sw.js').read_text(encoding='utf-8')
    names = re.findall(r"'/pilot/([^']*)'", worker.split('const SHELL = [')[1].split(']')[0])
    assert names, 'the shell list moved; re-check this guard'

    digest = hashlib.sha256()
    for name in sorted(names):
        digest.update(name.encode() + bytes([0]) + (web / (name or 'index.html')).read_bytes())
    expected = digest.hexdigest()[:12]

    recorded = re.search(r"const SHELL_STAMP = '([0-9a-f]+)';", worker)
    assert recorded, 'sw.js must record a SHELL_STAMP'
    assert recorded.group(1) == expected, (
        'a cached shell asset changed. Bump VERSION in sw.js and set '
        f"SHELL_STAMP to '{expected}', or installed copies keep the old app.")


def test_the_appearance_assets_are_served():
    client, _, _ = build(ok_completion())
    with client:
        for asset, media in [('themes.mjs', 'text/javascript'),
                             ('linguafusion-themes.css', 'text/css')]:
            response = client.get('/pilot/' + asset)
            assert response.status_code == 200, asset
            assert response.headers['content-type'].startswith(media), asset


def test_the_picker_offers_exactly_the_two_designed_looks_and_every_font():
    # The shared theme sheet still carries the older phone and PC looks, because
    # the desktop and phone clients read the same file. The cloud picker must
    # list only the two this client designed; offering the rest would promise
    # appearances nobody checked here.
    import pathlib
    import re
    web = pathlib.Path(__file__).parent / 'web'
    module = (web / 'themes.mjs').read_text(encoding='utf-8')
    registry = module.split('export const CLOUD_THEMES')[1].split('];')[0]
    offered = re.findall(r"\{ id: '([a-z-]+)', name:", registry)
    assert offered == ['studio', 'minimal'], offered
    fonts = re.findall(r'id:"([a-z]+)", name:"[^"]+", group:"(?:Sans|Serif|Monospace)"', module)
    assert set(fonts) == {'modern', 'friendly', 'accessible', 'editorial', 'classic', 'technical'}

    # And each offered look must actually exist in the sheet, in both modes.
    themes = (web / 'linguafusion-themes.css').read_text(encoding='utf-8')
    for look in offered:
        assert f'[data-theme="{look}"] {{' in themes, f'{look} has no definition'
        assert f'[data-theme="{look}"][data-mode="dark"]' in themes,             f'{look} would look identical by day and by night'


def test_an_explicit_day_night_choice_beats_the_device_preference():
    # Someone on a light phone who picks Night must get night. The literal
    # colours that are not derived from --lf-* tokens live in a media query, so
    # without a data-mode rule of higher specificity they would stay light and
    # sit unreadably on the dark surfaces the theme sheet supplies.
    import pathlib
    import re
    css = (pathlib.Path(__file__).parent / 'web' / 'pilot.css').read_text(encoding='utf-8')
    media = re.search(r'@media\(prefers-color-scheme:dark\)\s*\{\s*:root\s*\{(.*?)\}\s*\}', css, re.S)
    assert media, 'the dark fallback block moved; re-check this guard'
    literals = [token for token, value in re.findall(r'(--[a-z-]+)\s*:\s*([^;]+);', media.group(1))
                if 'var(--lf-' not in value]
    assert literals, 'expected some non-token literals in the dark block'
    for mode in ['light', 'dark']:
        rule = re.search(rf'html\[data-mode="{mode}"\]\s*\{{(.*?)\}}', css, re.S)
        assert rule, f'no explicit rule for {mode} mode'
        for token in literals:
            assert re.search(rf'{re.escape(token)}\s*:', rule.group(1)),                 f'{token} is not restated for {mode} mode and would follow the device instead'


def test_the_look_and_the_mode_are_remembered_separately():
    # Choosing a look must not reset someone's brightness, and vice versa.
    import pathlib
    module = (pathlib.Path(__file__).parent / 'web' / 'themes.mjs').read_text(encoding='utf-8')
    assert "'lf-theme'" in module and "'lf-mode'" in module and "'lf-font'" in module
    body = module.split('export function applyTheme')[1].split('export function applyMode')[0]
    assert 'dataset.mode' not in body, 'picking a look must not also set the mode'


def test_appearance_survives_storage_being_unavailable():
    # Private windows and blocked site data make localStorage THROW rather than
    # return null, which would break the whole module at import time.
    import pathlib
    module = (pathlib.Path(__file__).parent / 'web' / 'themes.mjs').read_text(encoding='utf-8')
    for accessor in ['localStorage.getItem', 'localStorage.setItem']:
        index = module.index(accessor)
        window = module[max(0, index - 120):index + 120]
        assert 'try' in window and 'catch' in window, f'{accessor} must be guarded'


def test_no_remote_font_is_fetched():
    # The product is offline-first; a webfont would make typography depend on
    # the network and leak a request to a third party.
    import pathlib
    web = pathlib.Path(__file__).parent / 'web'
    for name in ['linguafusion-themes.css', 'pilot.css']:
        text = (web / name).read_text(encoding='utf-8')
        assert '@import' not in text, name
        assert 'fonts.googleapis' not in text and 'fonts.gstatic' not in text, name


def test_the_dark_preference_never_overrides_a_chosen_look():
    # The dark-mode block sits later in the cascade at equal specificity. If it
    # assigns literal colours, every theme becomes inert on a dark-mode phone
    # while still appearing to switch.
    import pathlib
    import re
    css = (pathlib.Path(__file__).parent / 'web' / 'pilot.css').read_text(encoding='utf-8')
    block = re.search(r'@media\(prefers-color-scheme:dark\)\s*\{\s*:root\s*\{(.*?)\}\s*\}', css, re.S)
    assert block, 'the dark fallback block moved; re-check this guard'
    for token in ['--bg', '--panel', '--text', '--muted', '--accent']:
        assignment = re.search(rf'{re.escape(token)}\s*:\s*([^;]+);', block.group(1))
        assert assignment, f'{token} missing from the dark block'
        assert 'var(--lf-' in assignment.group(1), \
            f'{token} hardcodes a colour and would override the chosen look'


def test_the_primary_button_label_contrasts_with_its_own_accent():
    # A look is free to make the accent light -- Minimal's night mode uses a
    # near-white block with a dark label. A hardcoded white label is invisible
    # on it, so the colour has to come from the look's own on-accent token.
    import pathlib
    import re
    web = pathlib.Path(__file__).parent / 'web'
    css = (web / 'pilot.css').read_text(encoding='utf-8')
    rule = re.search(r'\nbutton \{(.*?)\}', css, re.S)
    assert rule, 'the button rule moved; re-check this guard'
    colour = re.search(r'(?<!-)color\s*:\s*([^;]+);', rule.group(1))
    assert colour and '--lf-on-accent' in colour.group(1),         f'the label must read through --lf-on-accent, got {colour and colour.group(1)}'

    # And every offered look must actually define that token, or the fallback
    # (white) silently comes back for it.
    themes = (web / 'linguafusion-themes.css').read_text(encoding='utf-8')
    module = (web / 'themes.mjs').read_text(encoding='utf-8')
    registry = module.split('export const CLOUD_THEMES')[1].split('];')[0]
    for look in re.findall(r"\{ id: '([a-z-]+)', name:", registry):
        for selector in [f'[data-theme="{look}"] {{', f'[data-theme="{look}"][data-mode="dark"]']:
            start = themes.index(selector)
            block = themes[start:themes.index('}', start)]
            assert '--lf-on-accent' in block, f'{look} {selector} leaves the label colour to chance'


def test_the_fixed_navigation_bar_is_opaque_in_every_look():
    # Content scrolls underneath it. Several looks define --lf-surface-bg (which
    # --panel maps to) as a translucent overlay for a blurred backdrop, and one
    # sets it to `transparent`, so page text showed through the bar.
    import pathlib
    import re
    web = pathlib.Path(__file__).parent / 'web'
    css = (web / 'pilot.css').read_text(encoding='utf-8')
    rule = re.search(r'\.bottom-nav\s*\{(.*?)\}', css, re.S)
    assert rule, 'the navigation rule moved; re-check this guard'
    background = re.search(r'background\s*:\s*([^;]+);', rule.group(1))
    assert background, 'the bar needs an explicit background'
    assert '--panel' not in background.group(1) and '--lf-surface-bg' not in background.group(1), \
        'the bar must not use a surface token; those are translucent in several looks'

    # And confirm the token it does use really is opaque in every look. A
    # `transparent` colour STOP inside a layered gradient is fine as long as an
    # opaque colour is painted underneath, so look for a solid colour rather
    # than banning the word.
    themes = (web / 'linguafusion-themes.css').read_text(encoding='utf-8')
    for value in re.findall(r'--lf-app-bg\s*:\s*([^;]+);', themes):
        stripped = value.strip()
        assert stripped != 'transparent', 'a fully transparent bar would leak the page through it'
        assert re.search(r'#[0-9a-fA-F]{3,8}|rgb\(', stripped),             f'no opaque colour in this look, the bar could leak: {stripped}'


def test_the_microphone_is_released_and_retried_before_giving_up():
    # A stream still held from an earlier attempt makes Android refuse the next
    # one with NotReadableError, which reads as "another app is using it" when
    # the page itself is the culprit. And several devices reject tuned
    # constraints and report that as NotReadableError rather than a constraint
    # error, so a plain request must be tried before the person is told to go
    # hunting for another app.
    import pathlib
    import re
    script = (pathlib.Path(__file__).parent / 'web' / 'pilot.mjs').read_text(encoding='utf-8')
    opener = re.search(r'async function openMicrophone\(\)\s*\{(.*?)\n\}', script, re.S)
    assert opener, 'the microphone opener moved; re-check this guard'
    body = opener.group(1)
    handler = script[script.index("$('recordToggle').addEventListener('click', async"):]
    assert handler.index('stopCapture()') < handler.index('await openMicrophone()'), 'release before opening'
    assert handler.index('captureStarting ||') < handler.index('await openMicrophone()'), 'serialize starts'
    assert 'audio: true' in body, 'a plain request must be tried as a fallback'
    assert "'NotAllowedError'" in body, 'a refused permission must not be retried pointlessly'
