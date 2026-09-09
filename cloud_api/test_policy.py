from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from cloud_api.app import Settings, create_app
from cloud_api.policy import LocalPolicy


def test_policies_and_usage_survive_restart(tmp_path):
    path = tmp_path / 'policy.db'
    policy = LocalPolicy(path, ['friend'], 1)
    policy.reserve('friend')
    policy = LocalPolicy(path, ['friend'])
    with pytest.raises(HTTPException) as error:
        policy.reserve('friend')
    assert error.value.status_code == 429
    policy.update('owner', 'friend', False, 20)
    with pytest.raises(HTTPException) as error:
        LocalPolicy(path, ['friend']).require_access('friend')
    assert error.value.status_code == 403


def test_atomic_reservations_across_connections(tmp_path):
    path = tmp_path / 'policy.db'
    LocalPolicy(path, ['friend'], 3)
    def reserve(_):
        try:
            LocalPolicy(path).reserve('friend')
            return True
        except HTTPException:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(reserve, range(20))) == 3
    assert LocalPolicy(path).users()[0]['attempts'] == 3


def test_owner_controls_and_revocation(tmp_path):
    policy = LocalPolicy(tmp_path / 'policy.db', ['owner', 'friend'])
    settings = Settings(owner_uid='owner')
    with TestClient(create_app(settings, verifier=lambda token: {'uid': token}, policy=policy)) as client:
        assert client.get('/owner/users').status_code == 401
        assert client.get('/owner/users', headers={'Authorization': 'Bearer friend'}).status_code == 403
        owner = {'Authorization': 'Bearer owner'}
        assert client.post('/owner/users/friend', headers=owner, data={'enabled': 'false', 'monthly_limit': 2}).status_code == 200
        assert client.get('/capabilities', headers={'Authorization': 'Bearer friend'}).status_code == 403
        assert client.post('/owner/users/friend', headers=owner, data={'enabled': 'true', 'monthly_limit': 2}).status_code == 200
        assert client.get('/capabilities', headers={'Authorization': 'Bearer friend'}).status_code == 200
        assert client.post('/owner/users/owner', headers=owner, data={'enabled': 'false', 'monthly_limit': 2}).status_code == 422
        assert client.post('/owner/users/friend', headers=owner, data={'enabled': 'true', 'monthly_limit': -1}).status_code == 422


def test_provider_failure_still_consumes_reservation(tmp_path):
    policy = LocalPolicy(tmp_path / 'policy.db', ['friend'], 1)
    policy.update('owner', 'friend', True, 1, 1_000_000)
    calls = []
    def fail(request):
        calls.append(True)
        return httpx.Response(500)
    settings = Settings(enabled=True, model='gpt-5.6-luna', api_key='fake')
    with TestClient(create_app(settings, verifier=lambda token: {'uid': 'friend'}, policy=policy, transport=httpx.MockTransport(fail))) as client:
        args = dict(headers={'Authorization': 'Bearer fake'}, data={'text': 'hello', 'paid_consent': 'true'})
        assert client.post('/translate', **args).status_code == 502
        assert client.post('/translate', **args).status_code == 429
        assert len(calls) == 1


def test_cloud_run_refuses_local_persistence(monkeypatch, tmp_path):
    monkeypatch.setenv('K_SERVICE', 'cloud-pilot')
    with pytest.raises(RuntimeError):
        create_app(Settings(policy_path=str(tmp_path / 'policy.db')))


def test_ai_fails_closed_without_store():
    settings = Settings(enabled=True, model='test', api_key='fake', allowed_uids=frozenset({'friend'}))
    with TestClient(create_app(settings, verifier=lambda token: {'uid': 'friend'})) as client:
        headers = {'Authorization': 'Bearer fake'}
        assert client.get('/capabilities', headers=headers).json()['translation_ready'] is False
        assert client.post('/translate', headers=headers, data={'text': 'hello'}).status_code == 503


def test_corrupt_policy_never_dispatches_provider(tmp_path):
    policy = LocalPolicy(tmp_path / 'policy.db', ['friend'])
    settings = Settings(enabled=True, model='test', api_key='fake')
    def unexpected(request):
        raise AssertionError('Unavailable policy must block provider calls')
    # A missing schema simulates an unavailable policy database without touching real data.
    from contextlib import closing
    with closing(policy.connect()) as db, db:
        db.execute('DROP TABLE users')
    with TestClient(create_app(settings, verifier=lambda token: {'uid': 'friend'}, policy=policy,
                               transport=httpx.MockTransport(unexpected))) as client:
        assert client.post('/translate', headers={'Authorization': 'Bearer fake'}, data={'text': 'hello'}).status_code == 503


def test_reapproval_does_not_reset_usage(tmp_path):
    policy = LocalPolicy(tmp_path / 'policy.db', ['friend'], 1)
    policy.reserve('friend')
    policy.update('owner', 'friend', False, 1)
    policy.update('owner', 'friend', True, 1)
    with pytest.raises(HTTPException) as error:
        policy.reserve('friend')
    assert error.value.status_code == 429
