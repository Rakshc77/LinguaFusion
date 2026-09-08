"""Offline policy-contract tests; not a substitute for Firestore emulator QA."""
import copy
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from cloud_api.app import Settings, create_app
from cloud_api.firestore_policy import CEILING_MICRO, FirestorePolicy, new_state


class MemoryPolicy(FirestorePolicy):
    def __init__(self, state=None):
        self.state = state or new_state('owner', 160_000)
        self.lock = threading.Lock()

    def _read(self):
        with self.lock:
            return copy.deepcopy(self.state)

    def _mutate(self, operation):
        with self.lock:
            state = copy.deepcopy(self.state)
            result = operation(state)
            self._validate(state)
            self.state = state
            return result


def test_zero_budget_denied_and_owner_updates_persist():
    policy = MemoryPolicy()
    policy.require_access('owner')
    with pytest.raises(HTTPException) as error:
        policy.reserve('owner', 'model', 10000)
    assert error.value.status_code == 429
    policy.update('owner', 'friend/with.dots', True, 3, 10000)
    key = policy.reserve('friend/with.dots', 'model', 10000)
    restored = MemoryPolicy(policy._read())
    assert restored.spending('friend/with.dots')['unresolved_reserved_usd'] == '0.010000'
    restored.settle(key, 1000)
    restored.settle(key, 0)
    assert restored.spending('friend/with.dots')['estimated_spent_usd'] == '0.001000'
    assert restored.spending('friend/with.dots')['remaining_usd'] == '0.009000'


def test_atomic_shared_lifetime_cap_includes_prior_tests():
    # Leave room for exactly two US$0.01 holds, whatever the ceiling is set to.
    policy = MemoryPolicy(new_state('owner', CEILING_MICRO - 20_000))
    for uid in ['a', 'b']:
        policy.update('owner', uid, True, 100, 1_000_000)
    def request(i):
        try:
            return policy.reserve(['a', 'b'][i % 2], 'model', 10000)
        except HTTPException as error:
            assert error.status_code == 429
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(request, range(20)))
    assert len([r for r in results if r]) == 2
    assert sum(row['attempts'] for row in policy.users()) == 2


def test_revocation_rechecked_before_dispatch_and_rollback():
    policy = MemoryPolicy()
    policy.update('owner', 'friend', True, 10, 10000)
    policy.require_access('friend')
    policy.update('owner', 'friend', False, 10)
    before = policy._read()
    with pytest.raises(HTTPException) as error:
        policy.reserve('friend', 'model', 10000)
    assert error.value.status_code == 403
    assert before == policy._read()


def test_allowance_invalid_inputs_and_bounded_ledger():
    for hold in [-1, True, CEILING_MICRO + 1]:
        with pytest.raises(ValueError):
            new_state('owner', hold)
    policy = MemoryPolicy()
    policy.update('owner', 'owner', True, 100, 1_000_000)
    for hold in [0, -1, True, 1.5]:
        with pytest.raises(HTTPException):
            policy.reserve('owner', 'model', hold)
    policy.state['charges'] = {str(i): {} for i in range(1000)}
    with pytest.raises(HTTPException) as error:
        policy.reserve('owner', 'model', 10000)
    assert error.value.status_code == 503


@pytest.mark.parametrize('settings', [Settings(), Settings(policy_path='local.db'),
    Settings(policy_backend='firestore', project='test'), Settings(policy_backend='unknown')])
def test_cloud_run_refuses_missing_managed_controls(monkeypatch, settings):
    monkeypatch.setenv('K_SERVICE', 'cloud-pilot')
    with pytest.raises(RuntimeError):
        create_app(settings, policy=MemoryPolicy())


def test_cloud_run_refuses_emulators(monkeypatch):
    monkeypatch.setenv('K_SERVICE', 'cloud-pilot')
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', 'localhost:8080')
    with pytest.raises(RuntimeError):
        create_app(Settings(policy_backend='firestore', project='test', owner_uid='owner'), policy=MemoryPolicy())
