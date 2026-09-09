import json
import logging
import sys
import tempfile
import weakref

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from cloud_api.app import FirebaseVerifier, Settings, create_app
from cloud_api.policy import LocalPolicy


def make_client(handler=None, enabled=True, verifier=None):
    settings = Settings(project='test-project', allowed_uids=frozenset({'friend'}),
                        api_key='test-provider-secret', model='gpt-5.6-luna', enabled=enabled)
    def verify(token):
        if token == 'valid':
            return {'uid': 'friend'}
        if token == 'unapproved':
            return {'uid': 'stranger'}
        raise HTTPException(401, 'Invalid token')
    def default_handler(request):
        return httpx.Response(200, json={'status': 'completed', 'output': [
            {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Guten Morgen'}]}
        ]})
    directory = tempfile.TemporaryDirectory()
    policy = LocalPolicy(directory.name + '/policy.sqlite3', ['friend'])
    policy.update('owner', 'friend', True, 100, 1_000_000)
    class ConsentingTestClient(TestClient):
        def post(self, url, **kwargs):
            if url == '/translate' and isinstance(kwargs.get('data'), dict):
                kwargs['data'] = dict(paid_consent='true', **kwargs['data'])
            return super().post(url, **kwargs)
    client = ConsentingTestClient(create_app(settings, verifier or verify, httpx.MockTransport(handler or default_handler), policy=policy))
    weakref.finalize(client, directory.cleanup)
    return client


def test_pilot_assets_are_public_but_only_allowlisted_files_are_served():
    with make_client() as client:
        page = client.get('/pilot/')
        assert page.status_code == 200
        # The product name, not a tagline: wording changes, identity does not.
        assert 'LinguaFusion' in page.text
        assert 'id="workspace"' in page.text, 'the app shell must be present'
        assert "frame-ancestors 'none'" in page.headers['content-security-policy']
        assert page.headers['cache-control'] == 'no-store'
        for name in ['pilot.css', 'pilot.mjs', 'firebase-config.mjs', 'cloud-auth.mjs', 'cloud-client.mjs']:
            assert client.get('/pilot/' + name).status_code == 200
        for name in ['cloud-auth.test.mjs', '.env', 'app.py', 'env.example']:
            assert client.get('/pilot/' + name).status_code == 404
        assert client.get('/capabilities').status_code == 401


@pytest.mark.parametrize('token,status', [('', 401), ('invalid', 401), ('unapproved', 403)])
def test_unauthorized_calls_never_reach_provider(token, status):
    def unexpected(request):
        raise AssertionError('Unauthorized request reached provider')
    with make_client(unexpected) as client:
        response = client.post('/translate', data={'text': 'hello'}, headers={'Authorization': 'Bearer ' + token})
        assert response.status_code == status


def test_translation_contract_and_server_side_request(caplog):
    def handler(request):
        assert request.url == 'https://api.openai.com/v1/responses'
        assert request.headers['Authorization'] == 'Bearer test-provider-secret'
        payload = json.loads(request.content)
        assert payload['store'] is False and payload['max_output_tokens'] == 2048
        assert payload['model'] == 'gpt-5.6-luna' and payload['input'] == 'Private source example'
        assert 'tools' not in payload
        return httpx.Response(200, json={'status': 'completed', 'output': [
            {'type': 'reasoning', 'summary': []},
            {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Guten Morgen'}]}
        ]})
    caplog.set_level(logging.INFO, logger='linguafusion.cloud')
    with make_client(handler) as client:
        response = client.post('/translate', headers={'Authorization': 'Bearer valid'},
                               data={'text': 'Private source example', 'source_lang': 'en', 'target_lang': 'de'})
    assert response.status_code == 200 and response.json()['translated_text'] == 'Guten Morgen'
    assert response.headers['cache-control'] == 'no-store'
    assert len(response.headers['x-request-id']) == 32
    logs = '\n'.join(r.message for r in caplog.records if r.name == 'linguafusion.cloud')
    assert 'cloud_request' in logs
    assert 'Private source example' not in logs and 'test-provider-secret' not in logs and 'Bearer' not in logs


@pytest.mark.parametrize('data', [{'text': ''}, {'text': '   '}, {'text': 'x' * 4001},
                                 {'text': 'hello', 'target_lang': 'unsupported'}])
def test_invalid_input_does_not_call_provider(data):
    def unexpected(request):
        raise AssertionError('Invalid input reached provider')
    with make_client(unexpected) as client:
        response = client.post('/translate', data=data, headers={'Authorization': 'Bearer valid'})
        assert response.status_code == 422
        assert 'x' * 100 not in response.text


def test_cloud_disabled_and_no_local_auth_bypass():
    with make_client(enabled=False) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/capabilities').status_code == 401
        assert client.get('/docs').status_code == 404
        response = client.post('/translate', data={'text': 'hello'}, headers={'Authorization': 'Bearer valid'})
        assert response.status_code == 503


@pytest.mark.parametrize('upstream,status', [(401, 502), (429, 503), (500, 502)])
def test_provider_errors_are_redacted(upstream, status):
    with make_client(lambda request: httpx.Response(upstream, text='secret provider details')) as client:
        response = client.post('/translate', data={'text': 'hello'}, headers={'Authorization': 'Bearer valid'})
        assert response.status_code == status and 'secret provider details' not in response.text


def test_timeout_and_incomplete_response():
    def timeout(request):
        raise httpx.ReadTimeout('secret internal URL')
    for handler, expected in [(timeout, 504), (lambda r: httpx.Response(200, json={'status': 'incomplete'}), 502)]:
        with make_client(handler) as client:
            response = client.post('/translate', data={'text': 'hello'}, headers={'Authorization': 'Bearer valid'})
            assert response.status_code == expected


def test_rate_limit_and_body_limit():
    with make_client() as client:
        for _ in range(10):
            assert client.post('/translate', data={'text': 'hello'}, headers={'Authorization': 'Bearer valid'}).status_code == 200
        response = client.post('/translate', data={'text': 'hello'}, headers={'Authorization': 'Bearer valid'})
        assert response.status_code == 429 and response.headers['retry-after'] == '10'
        assert client.get('/health').status_code == 200
        assert client.post('/translate', content=b'x' * (65536 + 1)).status_code == 413


def test_firebase_verifier_checks_revocation(monkeypatch):
    import firebase_admin
    from firebase_admin import auth
    sentinel = object()
    monkeypatch.setattr(firebase_admin, 'initialize_app', lambda **kwargs: sentinel)
    def check(token, app, check_revoked):
        assert token == 'token' and app is sentinel and check_revoked is True
        return {'uid': 'friend'}
    monkeypatch.delenv('FIREBASE_AUTH_EMULATOR_HOST', raising=False)
    monkeypatch.setattr(auth, 'verify_id_token', check)
    assert FirebaseVerifier('test-project')('token')['uid'] == 'friend'
    monkeypatch.setenv('FIREBASE_AUTH_EMULATOR_HOST', 'localhost:9099')
    with pytest.raises(HTTPException) as error:
        FirebaseVerifier('test-project')('token')
    assert error.value.status_code == 503


def test_cloud_import_does_not_load_local_models():
    assert 'backend.server' not in sys.modules
    assert 'torch' not in sys.modules
