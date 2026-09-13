"""One-use owner invitations grant exactly one verified account."""
import base64
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from cloud_api.invites import Invites, invite_url, public_record, qr_data_url, token_digest
from cloud_api.test_access_requests import (APPROVED_MONTHLY_BUDGET_MICRO,
                                             APPROVED_MONTHLY_LIMIT, OWNER,
                                             RecordingPolicy, STRANGER, auth, build)


class Snapshot:
    def __init__(self, data):
        self.data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self.data) if self.data is not None else None


class Document:
    def __init__(self, records, key):
        self.records, self.key = records, key

    def create(self, record):
        if self.key in self.records:
            raise RuntimeError('already exists')
        self.records[self.key] = dict(record)

    def get(self, timeout=None, transaction=None):
        return Snapshot(self.records.get(self.key))

    def update(self, changes):
        self.records[self.key].update(changes)


class Collection:
    def __init__(self, records, cap=None):
        self.records, self.cap = records, cap

    def document(self, key):
        return Document(self.records, key)

    def limit(self, count):
        return Collection(self.records, count)

    def stream(self, timeout=None):
        rows = list(self.records.values())[:self.cap]
        return [Snapshot(row) for row in rows]


class Transaction:
    def update(self, document, changes):
        document.update(changes)


class Client:
    def __init__(self):
        self.records = {}

    def collection(self, name):
        return Collection(self.records)

    def transaction(self):
        return Transaction()


def store():
    invitations = Invites('project', client=Client())
    invitations.firestore = SimpleNamespace(transactional=lambda function: function)
    return invitations


def test_tokens_are_hashed_and_qr_uses_a_fragment():
    invitations = store()
    created = invitations.create(OWNER, 24)
    assert created['url'].startswith('https://') and '#invite=' in created['url']
    assert created['token'] not in repr(invitations.client.records)
    assert created['id'] == token_digest(created['token'])
    assert base64.b64decode(created['qr'].split(',', 1)[1]).startswith(b'<svg')


def test_first_verified_account_owns_the_link_and_can_retry():
    invitations = store()
    created = invitations.create(OWNER)
    first = invitations.redeem(created['token'], STRANGER)
    assert first['used_by'] == STRANGER and first['retry'] is False
    assert invitations.redeem(created['token'], STRANGER)['retry'] is True
    with pytest.raises(HTTPException) as error:
        invitations.redeem(created['token'], 'other-uid')
    assert error.value.status_code == 410


def test_expired_and_revoked_links_fail_closed():
    invitations = store()
    expired = invitations.create(OWNER)
    invitations.client.records[expired['id']]['expires_at'] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with pytest.raises(HTTPException):
        invitations.redeem(expired['token'], STRANGER)

    revoked = invitations.create(OWNER)
    assert invitations.revoke(revoked['id'])['status'] == 'revoked'
    with pytest.raises(HTTPException):
        invitations.redeem(revoked['token'], STRANGER)


def test_owner_can_create_and_revoke_but_other_users_cannot():
    invitations = store()
    client, _, _ = build(invite_store=invitations)
    with client:
        forbidden = client.post('/owner/invites', headers=auth('stranger'), data={'expires_hours': 24})
        assert forbidden.status_code == 403
        created = client.post('/owner/invites', headers=auth('owner'), data={'expires_hours': 1})
        assert created.status_code == 200
        invite = created.json()['invite']
        assert client.get('/owner/invites', headers=auth('owner')).json()['invites'][0]['status'] == 'active'
        assert client.delete('/owner/invites/' + invite['id'], headers=auth('owner')).status_code == 200


def test_invited_request_is_approved_once_with_the_standard_allowance():
    invitations = store()
    created = invitations.create(OWNER)
    policy = RecordingPolicy([OWNER])
    client, policy, requests = build(policy=policy, invite_store=invitations)
    with client:
        joined = client.post('/access/request', headers=auth('stranger'), data={
            'name': 'Ada Lovelace', 'organisation': 'Acme', 'invite_token': created['token']})
        assert joined.status_code == 200 and joined.json()['status'] == 'approved'
        assert client.get('/capabilities', headers=auth('stranger')).status_code == 200
        second = client.post('/access/request', headers=auth('other'), data={
            'name': 'Other Person', 'organisation': 'Beta', 'invite_token': created['token']})
        assert second.status_code == 410
    assert policy.updates[-1] == (OWNER, STRANGER, True,
                                  APPROVED_MONTHLY_LIMIT, APPROVED_MONTHLY_BUDGET_MICRO)
    assert requests.get(STRANGER)['status'] == 'approved'
    assert requests.get('other-uid') is None


def test_bad_tokens_and_lifetimes_are_rejected():
    with pytest.raises(HTTPException):
        token_digest('short')
    with pytest.raises(HTTPException):
        store().create(OWNER, 0)
    with pytest.raises(HTTPException):
        store().create(OWNER, 169)
