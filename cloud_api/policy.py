"""Transactional LOCAL pilot policies. Not a Cloud Run persistence backend."""
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException


class LocalPolicy:
    # Per-user limits only. The shared lifetime allowance is held in a
    # separate TestBudget file, which must therefore still be consulted.
    enforces_lifetime_ceiling = False

    def __init__(self, path, seed_uids=(), monthly_limit=100):
        self.path = str(Path(path).resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS users (uid TEXT PRIMARY KEY, enabled INTEGER NOT NULL, monthly_limit INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS usage (uid TEXT, month TEXT, attempts INTEGER NOT NULL, PRIMARY KEY(uid,month))')
            db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, actor TEXT, target TEXT, enabled INTEGER, monthly_limit INTEGER, at TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS budgets (uid TEXT PRIMARY KEY, micro_usd INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS charges (id TEXT PRIMARY KEY, uid TEXT, month TEXT, model TEXT, reserved INTEGER NOT NULL, actual INTEGER, state TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS budget_events (id INTEGER PRIMARY KEY, actor TEXT, target TEXT, micro_usd INTEGER, at TEXT)')
            for uid in seed_uids:
                db.execute('INSERT OR IGNORE INTO users VALUES (?,1,?)', (uid, monthly_limit))

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def require_access(self, uid):
        with closing(self.connect()) as db:
            row = db.execute('SELECT enabled FROM users WHERE uid=?', (uid,)).fetchone()
        if row is None or not row['enabled']:
            raise HTTPException(403, 'Cloud access has not been approved by the owner.')

    def reserve(self, uid, model=None, reserved_micro=0):
        # Count before dispatch. Failures/timeouts keep their reservation because
        # the provider may have processed the request. Never refund automatically.
        month = datetime.now(timezone.utc).strftime('%Y-%m')
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM users WHERE uid=?', (uid,)).fetchone()
            if row is None or not row['enabled']:
                raise HTTPException(403, 'Cloud access has been disabled.')
            db.execute('INSERT OR IGNORE INTO usage VALUES (?,?,0)', (uid, month))
            used = db.execute('SELECT attempts FROM usage WHERE uid=? AND month=?', (uid, month)).fetchone()[0]
            if used >= row['monthly_limit']:
                raise HTTPException(429, 'Your monthly cloud request allowance is exhausted.')
            reservation = None
            if model is not None:
                if type(reserved_micro) is not int or reserved_micro <= 0:
                    raise HTTPException(503, 'A valid cost reservation is required.')
                budget = db.execute('SELECT micro_usd FROM budgets WHERE uid=?', (uid,)).fetchone()
                consumed = db.execute('SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM charges WHERE uid=? AND month=?', (uid, month)).fetchone()[0]
                if budget is None or consumed + reserved_micro > budget[0]:
                    raise HTTPException(429, 'Your remaining monthly API budget cannot cover this request.')
                reservation = uuid.uuid4().hex
                db.execute('INSERT INTO charges VALUES (?,?,?,?,?,NULL,?)', (reservation, uid, month, model, reserved_micro, 'unresolved'))
            db.execute('UPDATE usage SET attempts=attempts+1 WHERE uid=? AND month=?', (uid, month))
            return reservation

    def settle(self, reservation, actual):
        if actual is None:
            return
        if type(actual) is not int or actual < 0:
            raise ValueError('Invalid recorded cost')
        with closing(self.connect()) as db, db:
            db.execute('UPDATE charges SET actual=?,state=? WHERE id=? AND actual IS NULL', (actual, 'usage_estimate', reservation))

    def spending(self, uid=None):
        from cloud_api.models import usd
        month = datetime.now(timezone.utc).strftime('%Y-%m')
        with closing(self.connect()) as db:
            query = 'SELECT model,SUM(COALESCE(actual,0)) AS known,SUM(CASE WHEN actual IS NULL THEN reserved ELSE 0 END) AS held,COUNT(*) AS attempts FROM charges WHERE month=?'
            args = [month]
            if uid is not None:
                query += ' AND uid=?'
                args.append(uid)
            rows = db.execute(query + ' GROUP BY model', args).fetchall()
            budget = db.execute('SELECT micro_usd FROM budgets WHERE uid=?', (uid,)).fetchone() if uid else None
        known, held = sum(r['known'] for r in rows), sum(r['held'] for r in rows)
        return {'month': month, 'currency': 'USD', 'estimated_spent_usd': usd(known),
                'unresolved_reserved_usd': usd(held), 'budget_usd': usd(budget[0] if budget else 0) if uid else None,
                'remaining_usd': usd(max(0, (budget[0] if budget else 0)-known-held)) if uid else None,
                'models': [dict(model=r['model'], attempts=r['attempts'], estimated_spent_usd=usd(r['known']), unresolved_reserved_usd=usd(r['held'])) for r in rows],
                'invoice_verified': False, 'excludes': 'Hosting, taxes, electricity, external API use and provider billing adjustments.'}

    def forget(self, uid):
        """Drop a person's entry entirely. Charges are deliberately kept: money
        already committed cannot be un-spent by deleting who spent it."""
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM users WHERE uid=?', (uid,))
            db.execute('DELETE FROM usage WHERE uid=?', (uid,))
            db.execute('DELETE FROM budgets WHERE uid=?', (uid,))

    def users(self):
        month = datetime.now(timezone.utc).strftime('%Y-%m')
        with closing(self.connect()) as db:
            rows = db.execute('SELECT u.uid,u.enabled,u.monthly_limit,COALESCE(q.attempts,0) AS attempts FROM users u LEFT JOIN usage q ON u.uid=q.uid AND q.month=? ORDER BY u.uid LIMIT 1000', (month,)).fetchall()
        return [dict(row) for row in rows]

    def update(self, actor, uid, enabled, monthly_limit, budget=None):
        if not uid.strip() or len(uid) > 128 or not 0 <= monthly_limit <= 10000:
            raise HTTPException(422, 'Invalid user policy.')
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO users VALUES (?,?,?) ON CONFLICT(uid) DO UPDATE SET enabled=excluded.enabled,monthly_limit=excluded.monthly_limit', (uid, int(enabled), monthly_limit))
            db.execute('INSERT INTO events(actor,target,enabled,monthly_limit,at) VALUES (?,?,?,?,?)', (actor, uid, int(enabled), monthly_limit, datetime.now(timezone.utc).isoformat()))
            if budget is not None:
                if type(budget) is not int or not 0 <= budget <= 1_000_000_000:
                    raise HTTPException(422, 'Invalid budget.')
                db.execute('INSERT INTO budgets VALUES (?,?) ON CONFLICT(uid) DO UPDATE SET micro_usd=excluded.micro_usd', (uid, budget))
                db.execute('INSERT INTO budget_events(actor,target,micro_usd,at) VALUES (?,?,?,?)', (actor, uid, budget, datetime.now(timezone.utc).isoformat()))
