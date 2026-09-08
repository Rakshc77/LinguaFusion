"""Access requests: who may ask, what is stored, and who may decide.

A fake Firestore client exercises the real AccessRequests logic rather than a
reimplementation of it, so validation and status handling are genuinely tested.
"""
import json
import logging

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from cloud_api.access_requests import AccessRequests
from cloud_api.app import APPROVED_MONTHLY_BUDGET_MICRO, APPROVED_MONTHLY_LIMIT, Settings, create_app

OWNER = 'owner-uid'
STRANGER = 'stranger-uid'


# --- a small in-memory stand-in for Firestore ---------------------------------

class FakeSnapshot:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class FakeDocument:
    def __init__(self, store, key):
        self.store, self.key = store, key

    def get(self, timeout=None):
        return FakeSnapshot(self.store.get(self.key))

    def set(self, record):
        self.store[self.key] = dict(record)

    def update(self, changes):
        self.store[self.key].update(changes)

    def delete(self):
        self.store.pop(self.key, None)


class FakeCollection:
    def __init__(self, store, filters=(), cap=None):
        self.store, self.filters, self.cap = store, filters, cap

    def document(self, key):
        return FakeDocument(self.store, key)

    def where(self, field=None, _operator=None, value=None, filter=None):
        # Mirrors the real keyword-argument call the code now uses.
        if filter is not None:
            field, value = filter.field_path, filter.value
        return FakeCollection(self.store, self.filters + ((field, value),), self.cap)

    def limit(self, count):
        return FakeCollection(self.store, self.filters, count)

    def stream(self, timeout=None):
        rows = [r for r in self.store.values()
                if all(r.get(f) == v for f, v in self.filters)]
        return [FakeSnapshot(r) for r in rows[:self.cap]]


class FakeClient:
    def __init__(self):
        self.store = {}

    def collection(self, _name):
        return FakeCollection(self.store)


def make_store():
    return AccessRequests('project', client=FakeClient())


# --- storage rules ------------------------------------------------------------

def test_required_fields_are_enforced_and_bounded():
    store = make_store()
    for name, organisation in [('', 'Acme'), ('   ', 'Acme'), ('Ada', ''), (None, 'Acme'),
                               ('x' * 121, 'Acme'), ('Ada', 'y' * 121), ('Ada\x07', 'Acme')]:
        with pytest.raises(HTTPException) as error:
            store.submit(STRANGER, 'a@example.com', name, organisation)
        assert error.value.status_code == 422
    with pytest.raises(HTTPException):
        store.submit(STRANGER, 'not-an-email', 'Ada', 'Acme')


def test_whitespace_is_normalised_not_rejected():
    record = make_store().submit(STRANGER, 'a@example.com', '  Ada   Lovelace ', ' Acme  Ltd ')
    assert record['name'] == 'Ada Lovelace'
    assert record['organisation'] == 'Acme Ltd'
    assert record['status'] == 'pending'


def test_resubmitting_cannot_undo_an_approval():
    store = make_store()
    store.submit(STRANGER, 'a@example.com', 'Ada', 'Acme')
    store.decide(STRANGER, 'approved', OWNER)
    again = store.submit(STRANGER, 'a@example.com', 'Someone Else', 'Other')
    assert again['status'] == 'approved', 'an approved user must not be reset to pending'
    assert store.get(STRANGER)['name'] == 'Ada', 'approved details must not be silently rewritten'


def test_decisions_are_recorded_with_who_and_when():
    store = make_store()
    store.submit(STRANGER, 'a@example.com', 'Ada', 'Acme')
    record = store.decide(STRANGER, 'denied', OWNER)
    assert record['status'] == 'denied'
    assert record['decided_by'] == OWNER and record['decided_at']
    with pytest.raises(HTTPException) as error:
        store.decide('nobody', 'approved', OWNER)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException):
        store.decide(STRANGER, 'maybe', OWNER)


def test_personal_data_can_be_erased():
    store = make_store()
    store.submit(STRANGER, 'a@example.com', 'Ada', 'Acme')
    store.delete(STRANGER)
    assert store.get(STRANGER) is None


def test_listing_filters_by_status():
    store = make_store()
    store.submit('a', 'a@example.com', 'A', 'Acme')
    store.submit('b', 'b@example.com', 'B', 'Beta')
    store.decide('b', 'approved', OWNER)
    assert {r['uid'] for r in store.list('pending')} == {'a'}
    assert {r['uid'] for r in store.list()} == {'a', 'b'}


# --- endpoint behaviour -------------------------------------------------------

class RecordingPolicy:
    enforces_lifetime_ceiling = True

    def __init__(self, approved=()):
        self.approved = set(approved)
        self.limits = {}
        self.updates = []

    def require_access(self, uid):
        if uid not in self.approved:
            raise HTTPException(403, 'Cloud access has not been approved by the owner.')

    def update(self, actor, uid, enabled, monthly_limit, budget=None):
        self.updates.append((actor, uid, enabled, monthly_limit, budget))
        self.limits[uid] = monthly_limit
        self.approved.add(uid) if enabled else self.approved.discard(uid)

    def users(self):
        # Mirrors the real policy: every known account, enabled or not.
        return [dict(uid=uid, enabled=1 if uid in self.approved else 0,
                     monthly_limit=self.limits.get(uid, 540), attempts=0)
                for uid in sorted(self.approved | set(self.limits))]

    def spending(self, uid=None):
        return {'month': '2026-09', 'estimated_spent_usd': '0.000000',
                'unresolved_reserved_usd': '0.000000', 'budget_usd': '5.400000',
                'remaining_usd': '5.400000'}


TOKENS = {
    'owner': {'uid': OWNER, 'email': 'owner@example.com', 'email_verified': True},
    'stranger': {'uid': STRANGER, 'email': 'ada@example.com', 'email_verified': True},
    'unverified': {'uid': 'unverified-uid', 'email': 'x@example.com', 'email_verified': False},
}


def build(policy=None, store=None):
    policy = policy or RecordingPolicy([OWNER])
    store = store or make_store()

    def verify(token):
        if token in TOKENS:
            return TOKENS[token]
        raise HTTPException(401, 'Invalid token')

    settings = Settings(project='p', owner_uid=OWNER, enabled=False)
    client = TestClient(create_app(settings, verify, httpx.MockTransport(lambda r: httpx.Response(500)),
                                   policy=policy, access_store=store))
    return client, policy, store


def auth(name):
    return {'Authorization': f'Bearer {name}'}


def test_an_unapproved_person_may_request_access_but_nothing_else():
    client, _, store = build()
    with client:
        submitted = client.post('/access/request', headers=auth('stranger'),
                                data={'name': 'Ada Lovelace', 'organisation': 'Acme'})
        assert submitted.status_code == 200
        assert submitted.json()['status'] == 'pending'
        # Still not approved: every protected endpoint stays shut.
        assert client.get('/capabilities', headers=auth('stranger')).status_code == 403
        assert client.get('/owner/requests', headers=auth('stranger')).status_code == 403
    assert store.get(STRANGER)['email'] == 'ada@example.com'


def test_an_unverified_email_cannot_request_access():
    client, _, store = build()
    with client:
        response = client.post('/access/request', headers=auth('unverified'),
                               data={'name': 'Ada', 'organisation': 'Acme'})
    assert response.status_code == 403
    assert store.list() == [], 'nothing may be stored for an unverified address'


def test_an_anonymous_visitor_cannot_request_access():
    client, _, store = build()
    with client:
        assert client.post('/access/request', data={'name': 'Ada', 'organisation': 'Acme'}).status_code == 401
    assert store.list() == []


def test_the_email_comes_from_the_token_not_the_form():
    client, _, store = build()
    with client:
        client.post('/access/request', headers=auth('stranger'),
                    data={'name': 'Ada', 'organisation': 'Acme', 'email': 'victim@example.com'})
    # A submitted email field must be ignored entirely.
    assert store.get(STRANGER)['email'] == 'ada@example.com'


def test_owner_approval_grants_the_agreed_monthly_allowance():
    client, policy, store = build()
    with client:
        client.post('/access/request', headers=auth('stranger'),
                    data={'name': 'Ada', 'organisation': 'Acme'})
        listed = client.get('/owner/requests', headers=auth('owner'), params={'status': 'pending'}).json()
        assert [r['uid'] for r in listed['requests']] == [STRANGER]

        decided = client.post(f'/owner/requests/{STRANGER}', headers=auth('owner'),
                              data={'decision': 'approved'})
        assert decided.status_code == 200
    assert policy.updates[-1] == (OWNER, STRANGER, True, APPROVED_MONTHLY_LIMIT, APPROVED_MONTHLY_BUDGET_MICRO)
    assert store.get(STRANGER)['status'] == 'approved'


def test_denial_revokes_access_in_the_ledger_too():
    policy = RecordingPolicy([OWNER, STRANGER])
    client, policy, store = build(policy=policy)
    with client:
        client.post('/access/request', headers=auth('stranger'),
                    data={'name': 'Ada', 'organisation': 'Acme'})
        assert client.post(f'/owner/requests/{STRANGER}', headers=auth('owner'),
                           data={'decision': 'denied'}).status_code == 200
    # Denial must not leave a stale enabled row behind in the policy.
    assert policy.updates[-1] == (OWNER, STRANGER, False, 0, 0)
    assert STRANGER not in policy.approved


def test_only_the_owner_can_list_or_decide():
    client, policy, store = build(policy=RecordingPolicy([OWNER, STRANGER]))
    with client:
        client.post('/access/request', headers=auth('stranger'),
                    data={'name': 'Ada', 'organisation': 'Acme'})
        assert client.get('/owner/requests', headers=auth('stranger')).status_code == 403
        assert client.post(f'/owner/requests/{STRANGER}', headers=auth('stranger'),
                           data={'decision': 'approved'}).status_code == 403
    assert not any(u[2] for u in policy.updates), 'a non-owner must not change any policy'


def test_the_owner_cannot_deny_themselves():
    client, _, store = build()
    with client:
        client.post('/access/request', headers=auth('owner'),
                    data={'name': 'Owner', 'organisation': 'LinguaFusion'})
        response = client.post(f'/owner/requests/{OWNER}', headers=auth('owner'),
                               data={'decision': 'denied'})
    assert response.status_code == 422


def test_the_notification_log_line_carries_no_personal_data(caplog):
    client, _, _ = build()
    with caplog.at_level(logging.INFO, logger='linguafusion.cloud'), client:
        client.post('/access/request', headers=auth('stranger'),
                    data={'name': 'Ada Lovelace', 'organisation': 'Acme Ltd'})
    lines = [r.getMessage() for r in caplog.records]
    submitted = [l for l in lines if 'access_request_submitted' in l]
    assert submitted, 'the owner needs a signal that a request arrived'
    blob = ' '.join(lines)
    for secret in ['Ada', 'Lovelace', 'Acme', 'ada@example.com', STRANGER]:
        assert secret not in blob, f'{secret} must not reach the logs'
    assert json.loads(submitted[0])['uid_prefix'] == STRANGER[:8]


def test_requests_are_unavailable_rather_than_crashing_when_unconfigured():
    def verify(token):
        return TOKENS.get(token) or (_ for _ in ()).throw(HTTPException(401, 'no'))

    settings = Settings(project='p', owner_uid=OWNER)
    client = TestClient(create_app(settings, verify, None,
                                   policy=RecordingPolicy([OWNER]), access_store=None))
    with client:
        assert client.post('/access/request', headers=auth('stranger'),
                           data={'name': 'Ada', 'organisation': 'Acme'}).status_code == 503


def test_the_owner_sees_who_each_person_is_not_just_a_uid():
    client, policy, store = build()
    policy.approved.add(STRANGER)
    store.submit(STRANGER, 'ada@example.com', 'Ada Lovelace', 'Acme Ltd')
    store.decide(STRANGER, 'approved', OWNER)
    with client:
        body = client.get('/owner/users', headers=auth('owner')).json()
    rows = {row['uid']: row for row in body['users']}
    assert rows[STRANGER]['name'] == 'Ada Lovelace'
    assert rows[STRANGER]['email'] == 'ada@example.com'
    assert rows[STRANGER]['organisation'] == 'Acme Ltd'
    assert rows[STRANGER]['is_owner'] is False
    # Usage figures must accompany the identity, or the owner cannot judge.
    assert 'spending' in rows[STRANGER] and 'monthly_limit' in rows[STRANGER]


def test_removing_a_person_revokes_access_and_erases_their_details():
    client, policy, store = build()
    policy.approved.add(STRANGER)
    store.submit(STRANGER, 'ada@example.com', 'Ada Lovelace', 'Acme')
    with client:
        removed = client.delete(f'/owner/users/{STRANGER}', headers=auth('owner'))
        assert removed.status_code == 200
    assert policy.updates[-1] == (OWNER, STRANGER, False, 0, 0), 'access must be revoked'
    assert store.get(STRANGER) is None, 'personal data must be erased'


def test_the_owner_cannot_remove_themselves_and_others_cannot_remove_anyone():
    client, policy, store = build(policy=RecordingPolicy([OWNER, STRANGER]))
    store.submit(STRANGER, 'ada@example.com', 'Ada', 'Acme')
    with client:
        assert client.delete(f'/owner/users/{OWNER}', headers=auth('owner')).status_code == 422
        assert client.delete(f'/owner/users/{STRANGER}', headers=auth('stranger')).status_code == 403
    assert store.get(STRANGER) is not None, 'a non-owner must not erase anyone'


def test_a_missing_access_record_still_lists_the_person():
    # Someone added by UID through the advanced form has no request record.
    client, policy, store = build(policy=RecordingPolicy([OWNER, 'manual-uid']))
    with client:
        body = client.get('/owner/users', headers=auth('owner')).json()
    assert isinstance(body['users'], list), 'the list must not break without a record'


def test_removing_a_person_drops_their_row_instead_of_leaving_it_disabled():
    # A disabled row that never disappears means the owner's list only grows,
    # and after a few months they cannot see who actually has access.
    import tempfile
    from cloud_api.policy import LocalPolicy
    directory = tempfile.TemporaryDirectory()
    policy = LocalPolicy(directory.name + '/p.sqlite3', [])
    policy.update(OWNER, 'gone-uid', True, 540, 5_400_000)
    assert any(row['uid'] == 'gone-uid' for row in policy.users())
    policy.forget('gone-uid')
    assert not any(row['uid'] == 'gone-uid' for row in policy.users())
    directory.cleanup()


def test_forgetting_a_person_never_erases_what_they_spent():
    import tempfile
    from cloud_api.policy import LocalPolicy
    directory = tempfile.TemporaryDirectory()
    policy = LocalPolicy(directory.name + '/p.sqlite3', [])
    policy.update(OWNER, 'spender', True, 540, 5_400_000)
    reservation = policy.reserve('spender', 'pilot:test/model', 10000)
    policy.settle(reservation, 7000)
    before = policy.spending()['estimated_spent_usd']
    policy.forget('spender')
    # Money already committed must keep counting against the shared total.
    assert policy.spending()['estimated_spent_usd'] == before
    directory.cleanup()
