"""Durable, transactional controls for a SMALL cloud pilot.

One server-only document serializes allowance decisions across instances. This
deliberately caps the pilot at 50 users / 1,000 reservations; it fails closed
instead of growing past Firestore's document limit. No user content is stored.
Initialization is an explicit administrative action, never a startup side effect.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from cloud_api.models import usd


def month_now():
    return datetime.now(timezone.utc).strftime('%Y-%m')


# Shared lifetime ceiling, in micro-USD. Set to approximately EUR 5 at the
# owner's instruction (2026-09-08). The ledger counts USD while the billing
# account is EUR, so the euro figure drifts with the exchange rate -- this is an
# approximation, never an exact euro guarantee.
CEILING_MICRO = 5_400_000


def new_state(owner_uid, prior_reserved_micro):
    if not isinstance(owner_uid, str) or not owner_uid.strip() or len(owner_uid) > 128:
        raise ValueError('A verified owner UID is required')
    if type(prior_reserved_micro) is not int or not 0 <= prior_reserved_micro <= CEILING_MICRO:
        raise ValueError('Carry forward the existing test reservations')
    return {'version': 1, 'ceiling': CEILING_MICRO, 'prior_reserved': prior_reserved_micro,
            'users': {uid_key(owner_uid): {'uid': owner_uid, 'enabled': True,
                       'monthly_limit': 100, 'budget': 0, 'months': {}}},
            'charges': {}, 'events': []}


def uid_key(uid):
    return hashlib.sha256(uid.encode('utf-8')).hexdigest()


class FirestorePolicy:
    storage = 'firestore-pilot'
    # reserve() checks prior_reserved + every charge against the ceiling in
    # the same transaction, so this policy IS the lifetime ledger.
    enforces_lifetime_ceiling = True

    def __init__(self, project, database='(default)', client=None):
        from google.cloud import firestore
        self.client = client or firestore.Client(project=project, database=database)
        self.document = self.client.collection('linguafusion_private').document('pilot_policy_v1')

    def _read(self):
        try:
            data = self.document.get(timeout=10).to_dict()
            self._validate(data)
            return data
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, 'Cloud access controls are temporarily unavailable.') from None

    @staticmethod
    def _validate(data):
        if not isinstance(data, dict) or data.get('version') != 1:
            raise HTTPException(503, 'Cloud access controls require initialization.')
        if len(json.dumps(data, ensure_ascii=True).encode()) > 700_000:
            raise HTTPException(503, 'The pilot ledger requires maintenance.')

    def _mutate(self, operation):
        from google.cloud import firestore

        @firestore.transactional
        def commit(transaction):
            state = self.document.get(transaction=transaction, timeout=10).to_dict()
            self._validate(state)
            result = operation(state)
            self._validate(state)
            transaction.set(self.document, state)
            return result

        try:
            return commit(self.client.transaction(max_attempts=5))
        except HTTPException:
            raise
        except Exception:
            # Uncertain commit: never dispatch a provider request afterwards.
            raise HTTPException(503, 'Cloud access controls are temporarily unavailable.') from None

    @staticmethod
    def _user(state, uid):
        row = state['users'].get(uid_key(uid))
        if not row or row['uid'] != uid or not row['enabled']:
            raise HTTPException(403, 'Cloud access has not been approved by the owner.')
        return row

    def require_access(self, uid):
        self._user(self._read(), uid)

    def reserve(self, uid, model=None, reserved_micro=0):
        month = month_now()
        reservation = uuid.uuid4().hex

        def operation(state):
            row = self._user(state, uid)
            used = row['months'].get(month, 0)
            if used >= row['monthly_limit']:
                raise HTTPException(429, 'Your monthly cloud request allowance is exhausted.')
            if len(state['charges']) >= 1000 or len(row['months']) >= 24 and month not in row['months']:
                raise HTTPException(503, 'The pilot ledger requires maintenance.')
            if model is not None:
                if not isinstance(model, str) or len(model) > 128 or type(reserved_micro) is not int or reserved_micro <= 0:
                    raise HTTPException(503, 'A valid cost reservation is required.')
                charges = state['charges'].values()
                consumed = sum(c['reserved'] if c['actual'] is None else c['actual']
                               for c in charges if c['uid'] == uid and c['month'] == month)
                total = state['prior_reserved'] + sum(c['reserved'] if c['actual'] is None else c['actual'] for c in charges)
                if consumed + reserved_micro > row['budget']:
                    raise HTTPException(429, 'Your remaining monthly API budget cannot cover this request.')
                if total + reserved_micro > state['ceiling']:
                    raise HTTPException(429, 'The shared pilot API allowance is exhausted.')
                state['charges'][reservation] = {'uid': uid, 'month': month, 'model': model,
                                                 'reserved': reserved_micro, 'actual': None}
            row['months'][month] = used + 1
            return reservation if model is not None else None
        return self._mutate(operation)

    def settle(self, reservation, actual):
        if actual is None:
            return
        if type(actual) is not int or actual < 0:
            raise ValueError('Invalid recorded cost')

        def operation(state):
            charge = state['charges'].get(reservation)
            if charge and charge['actual'] is None:
                charge['actual'] = actual
        self._mutate(operation)

    def update(self, actor, uid, enabled, monthly_limit, budget=None):
        if not isinstance(uid, str) or not uid.strip() or len(uid) > 128 or type(monthly_limit) is not int or not 0 <= monthly_limit <= 10000:
            raise HTTPException(422, 'Invalid user policy.')
        if budget is not None and (type(budget) is not int or not 0 <= budget <= 1_000_000_000):
            raise HTTPException(422, 'Invalid budget.')
        at = datetime.now(timezone.utc).isoformat()

        def operation(state):
            key = uid_key(uid)
            if len(state['events']) >= 1000 or key not in state['users'] and len(state['users']) >= 50:
                raise HTTPException(503, 'The pilot ledger requires maintenance.')
            row = state['users'].setdefault(key, {'uid': uid, 'budget': 0, 'months': {}})
            row.update(enabled=bool(enabled), monthly_limit=monthly_limit)
            if budget is not None:
                row['budget'] = budget
            state['events'].append({'actor': actor, 'uid': uid, 'enabled': bool(enabled),
                                    'limit': monthly_limit, 'budget': budget, 'at': at})
        self._mutate(operation)

    def forget(self, uid):
        """Drop a person's entry entirely.

        Their recorded charges stay in the ledger on purpose: money already
        committed cannot be un-spent by deleting whoever spent it, and the
        lifetime total must keep counting it.
        """
        def operation(state):
            state['users'].pop(uid_key(uid), None)
        self._mutate(operation)

    def users(self):
        month = month_now()
        return [dict(uid=r['uid'], enabled=int(r['enabled']), monthly_limit=r['monthly_limit'],
                     attempts=r['months'].get(month, 0))
                for r in sorted(self._read()['users'].values(), key=lambda r: r['uid'])]

    def spending(self, uid=None):
        state, month = self._read(), month_now()
        groups = {}
        for charge in state['charges'].values():
            if charge['month'] != month or uid is not None and charge['uid'] != uid:
                continue
            group = groups.setdefault(charge['model'], {'known': 0, 'held': 0, 'attempts': 0})
            group['attempts'] += 1
            if charge['actual'] is None:
                group['held'] += charge['reserved']
            else:
                group['known'] += charge['actual']
        known, held = sum(g['known'] for g in groups.values()), sum(g['held'] for g in groups.values())
        budget = state['users'].get(uid_key(uid), {}).get('budget', 0) if uid else None
        return {'month': month, 'currency': 'USD', 'estimated_spent_usd': usd(known),
                'unresolved_reserved_usd': usd(held), 'budget_usd': usd(budget) if uid else None,
                'remaining_usd': usd(max(0, budget-known-held)) if uid else None,
                'models': [dict(model=model, attempts=g['attempts'], estimated_spent_usd=usd(g['known']),
                                unresolved_reserved_usd=usd(g['held'])) for model, g in sorted(groups.items())],
                'invoice_verified': False,
                'excludes': 'Hosting, taxes, electricity, external API use and provider billing adjustments.'}
