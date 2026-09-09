"""Access requests from people who want to use the cloud pilot.

Deliberately a SEPARATE Firestore collection from the policy ledger. The ledger
is a single size-bounded document that must hold no personal content; this holds
names, emails and organisations, which are personal data and need their own
storage, their own access control and their own deletion path.

Only the backend service account touches this collection. The published
Firestore rules deny every client read and write, so nothing here is reachable
from a browser or phone even with a valid sign-in.

Email addresses are NEVER taken from the request body. They come from the
verified Firebase token, so a requester cannot claim someone else's address.

Data kept is the minimum needed to decide: who is asking, how to reach them,
and who they are with. No postal address, no phone number.
"""
from datetime import datetime, timezone

from fastapi import HTTPException

COLLECTION = 'linguafusion_access_requests'
MAX_STORED_REQUESTS = 200
STATUSES = ('pending', 'approved', 'denied')


def _clean(value, label, limit):
    if not isinstance(value, str):
        raise HTTPException(422, f'{label} is required.')
    text = ' '.join(value.split())
    if not text:
        raise HTTPException(422, f'{label} is required.')
    if len(text) > limit:
        raise HTTPException(422, f'{label} must be {limit} characters or fewer.')
    # Control characters would corrupt the owner's console rendering.
    if any(ord(character) < 32 for character in text):
        raise HTTPException(422, f'{label} contains invalid characters.')
    return text


class AccessRequests:
    def __init__(self, project, database='(default)', client=None):
        from google.cloud import firestore
        self.client = client or firestore.Client(project=project, database=database)
        self.collection = self.client.collection(COLLECTION)

    def _document(self, uid):
        return self.collection.document(uid)

    def submit(self, uid, email, name, organisation):
        """Record or update one person's pending request.

        An already-approved user is not reset to pending by re-submitting, so a
        resubmission cannot be used to disturb a decision the owner has made.
        """
        name = _clean(name, 'Name', 120)
        organisation = _clean(organisation, 'Organisation', 120)
        if not isinstance(email, str) or '@' not in email or len(email) > 254:
            raise HTTPException(422, 'A verified email address is required.')

        existing = self._document(uid).get(timeout=10)
        current = existing.to_dict() if existing.exists else None
        if current and current.get('status') == 'approved':
            return dict(current, unchanged=True)
        if current is None:
            # Bound the store; failing closed beats unbounded personal data.
            if len(list(self.collection.limit(MAX_STORED_REQUESTS + 1).stream(timeout=20))) > MAX_STORED_REQUESTS:
                raise HTTPException(503, 'Access requests are temporarily closed.')

        record = {
            'uid': uid,
            'email': email,
            'name': name,
            'organisation': organisation,
            'status': 'pending',
            'requested_at': datetime.now(timezone.utc).isoformat(),
            'decided_at': None,
            'decided_by': None,
        }
        self._document(uid).set(record)
        return record

    def get(self, uid):
        snapshot = self._document(uid).get(timeout=10)
        return snapshot.to_dict() if snapshot.exists else None

    def list(self, status=None, limit=100):
        query = self.collection
        if status is not None:
            if status not in STATUSES:
                raise HTTPException(422, 'Unknown request status.')
            from google.cloud.firestore_v1.base_query import FieldFilter
            query = query.where(filter=FieldFilter('status', '==', status))
        rows = [document.to_dict() for document in query.limit(limit).stream(timeout=20)]
        rows.sort(key=lambda row: row.get('requested_at', ''), reverse=True)
        return rows

    def decide(self, uid, status, decided_by):
        if status not in ('approved', 'denied'):
            raise HTTPException(422, 'A decision must be approved or denied.')
        snapshot = self._document(uid).get(timeout=10)
        if not snapshot.exists:
            raise HTTPException(404, 'No such access request.')
        self._document(uid).update({
            'status': status,
            'decided_at': datetime.now(timezone.utc).isoformat(),
            'decided_by': decided_by,
        })
        return self.get(uid)

    def delete(self, uid):
        """Erase someone's personal data. Their policy entry is separate and is
        revoked through the owner console, not here."""
        self._document(uid).delete()
