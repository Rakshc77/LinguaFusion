"""Owner-created, one-use invitations for the hosted LinguaFusion app.

Only a hash of each bearer token is stored. The token travels in the URL
fragment, so browsers do not send it in HTTP requests, access logs or referrers.
Redemption is transactional and idempotent for the first verified account: a
retry can finish granting access after a transient failure, but a second account
can never use the same link.
"""
import base64
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException


COLLECTION = 'linguafusion_one_time_invites'
PUBLIC_APP_URL = 'https://linguafusion-cloud-pilot-jl77ipbeua-ey.a.run.app/pilot/'
MAX_INVITES = 200
TOKEN_PATTERN = re.compile(r'^[A-Za-z0-9_-]{20,256}$')


def _now():
    return datetime.now(timezone.utc)


def _iso(value):
    return value.astimezone(timezone.utc).isoformat()


def _parse(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)
        except ValueError:
            pass
    raise HTTPException(410, 'This invitation is no longer available.')


def token_digest(token):
    if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
        raise HTTPException(410, 'This invitation is no longer available.')
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def invite_url(token):
    token_digest(token)  # validate before placing it in a shareable address
    return f'{PUBLIC_APP_URL}#invite={token}'


def qr_data_url(url):
    """Return a dependency-light SVG QR as a data URL for an authenticated UI."""
    import qrcode
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4)
    code.add_data(url)
    code.make(fit=True)
    grid = code.get_matrix()
    side = len(grid)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {side} {side}" '
             'shape-rendering="crispEdges"><rect width="100%" height="100%" fill="white"/>']
    path = []
    for y, row in enumerate(grid):
        for x, dark in enumerate(row):
            if dark:
                path.append(f'M{x} {y}h1v1h-1z')
    parts.append(f'<path d="{"".join(path)}" fill="black"/></svg>')
    encoded = base64.b64encode(''.join(parts).encode('utf-8')).decode('ascii')
    return 'data:image/svg+xml;base64,' + encoded


def public_record(record, now=None):
    now = now or _now()
    if record.get('used_at'):
        status = 'used'
    elif record.get('revoked_at'):
        status = 'revoked'
    elif _parse(record.get('expires_at')) <= now:
        status = 'expired'
    else:
        status = 'active'
    return {key: record.get(key) for key in ('id', 'created_at', 'expires_at', 'used_at', 'revoked_at')} | {
        'status': status,
    }


class Invites:
    def __init__(self, project, database='(default)', client=None):
        from google.cloud import firestore
        self.firestore = firestore
        self.client = client or firestore.Client(project=project, database=database)
        self.collection = self.client.collection(COLLECTION)

    def create(self, created_by, expires_hours=24):
        try:
            hours = int(expires_hours)
        except (TypeError, ValueError):
            raise HTTPException(422, 'Choose a valid invitation lifetime.') from None
        if not 1 <= hours <= 168:
            raise HTTPException(422, 'Invitations may last from 1 hour to 7 days.')
        if len(list(self.collection.limit(MAX_INVITES + 1).stream(timeout=20))) > MAX_INVITES:
            raise HTTPException(503, 'Too many invitation records. Remove old invitations first.')

        token = secrets.token_urlsafe(24)
        identifier = token_digest(token)
        now = _now()
        record = {
            'id': identifier,
            'created_by': created_by,
            'created_at': _iso(now),
            'expires_at': _iso(now + timedelta(hours=hours)),
            'used_at': None,
            'used_by': None,
            'revoked_at': None,
        }
        self.collection.document(identifier).create(record)
        url = invite_url(token)
        return public_record(record, now) | {'token': token, 'url': url, 'qr': qr_data_url(url)}

    def list(self, limit=100):
        records = [snapshot.to_dict() for snapshot in self.collection.limit(limit).stream(timeout=20)]
        records.sort(key=lambda row: row.get('created_at', ''), reverse=True)
        return [public_record(record) for record in records]

    def redeem(self, token, uid):
        identifier = token_digest(token)
        reference = self.collection.document(identifier)
        transaction = self.client.transaction()

        @self.firestore.transactional
        def consume(current_transaction):
            snapshot = reference.get(transaction=current_transaction)
            if not snapshot.exists:
                raise HTTPException(410, 'This invitation is no longer available.')
            record = snapshot.to_dict()
            # Idempotence lets the first account finish a grant after a network
            # failure without opening the link to anybody else.
            if record.get('used_by') == uid:
                return record | {'retry': True}
            if (record.get('used_at') or record.get('revoked_at')
                    or _parse(record.get('expires_at')) <= _now()):
                raise HTTPException(410, 'This invitation is no longer available.')
            used_at = _iso(_now())
            current_transaction.update(reference, {'used_at': used_at, 'used_by': uid})
            return record | {'used_at': used_at, 'used_by': uid, 'retry': False}

        return consume(transaction)

    def revoke(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch(r'[0-9a-f]{64}', identifier):
            raise HTTPException(404, 'No such invitation.')
        reference = self.collection.document(identifier)
        snapshot = reference.get(timeout=10)
        if not snapshot.exists:
            raise HTTPException(404, 'No such invitation.')
        record = snapshot.to_dict()
        if record.get('used_at'):
            raise HTTPException(409, 'A used invitation cannot be revoked.')
        reference.update({'revoked_at': _iso(_now())})
        return public_record(reference.get(timeout=10).to_dict())
