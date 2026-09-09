"""Lifetime, combined test allowance. Deliberately independent of monthly UI budgets.

After cutover this ledger is CLOSED. Its balance is carried into the managed
cloud ledger as prior_reserved, and further local reservations are refused --
otherwise the local file and the cloud document would each permit another US$5.
"""
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


class TestBudget:
    __test__ = False

    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS test_allowance (id INTEGER PRIMARY KEY CHECK(id=1), micro_usd INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS test_requests (id TEXT PRIMARY KEY, provider TEXT NOT NULL, reserved INTEGER NOT NULL, actual INTEGER)')
            # Explicit user approval: USD 5 combined, not per service or month.
            db.execute('INSERT OR IGNORE INTO test_allowance VALUES (1,5000000)')
            db.execute('CREATE TABLE IF NOT EXISTS cutover (id INTEGER PRIMARY KEY CHECK(id=1), at TEXT NOT NULL, note TEXT)')

    def carry_forward_micro(self):
        """Everything this ledger has committed: recorded costs AND unresolved
        holds. An unresolved hold may still be billed, so it must be carried
        forward as spent, never treated as available again."""
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute('SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM test_requests').fetchone()[0]

    def cutover_at(self):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute('SELECT at FROM cutover WHERE id=1').fetchone()
        return row[0] if row else None

    def mark_cutover(self, note=''):
        """Close this ledger. Idempotent: an existing mark is returned unchanged
        so a retried cutover cannot reopen local spending."""
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT at FROM cutover WHERE id=1').fetchone()
            if row:
                return row[0]
            at = datetime.now(timezone.utc).isoformat()
            db.execute('INSERT INTO cutover VALUES (1,?,?)', (at, str(note)[:500]))
            return at

    def clear_cutover(self):
        """Administrative rollback for a cutover that did NOT complete. Only ever
        valid while the managed cloud ledger does not exist; the caller must
        prove that. Reopening local spending alongside a live cloud ledger would
        grant a second US$5."""
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute('DELETE FROM cutover WHERE id=1')

    def reserve(self, provider, maximum_micro):
        if provider not in {'openrouter', 'groq', 'google_vision'}:
            raise ValueError('Provider outside approved test scope')
        if type(maximum_micro) is not int or maximum_micro <= 0:
            raise ValueError('A positive maximum charge is required')
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            # Checked inside the transaction so a concurrent cutover cannot be
            # overtaken by an in-flight reservation.
            if db.execute('SELECT 1 FROM cutover WHERE id=1').fetchone():
                raise ValueError('Local paid testing closed at cutover; the managed cloud ledger holds the remaining allowance')
            budget = db.execute('SELECT micro_usd FROM test_allowance WHERE id=1').fetchone()[0]
            used = db.execute('SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM test_requests').fetchone()[0]
            if used + maximum_micro > budget:
                raise ValueError('Combined USD 5 test budget exhausted')
            request_id = uuid.uuid4().hex
            db.execute('INSERT INTO test_requests VALUES (?,?,?,NULL)', (request_id, provider, maximum_micro))
            return request_id

    def settle(self, request_id, actual_micro):
        # Timeouts or missing billing keep the original hold, across restarts.
        if actual_micro is None:
            return
        if type(actual_micro) is not int or actual_micro < 0:
            raise ValueError('Invalid cost')
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE test_requests SET actual=? WHERE id=? AND actual IS NULL', (actual_micro, request_id))

    def summary(self):
        """Keep unknown charges distinct from zero dollars confirmed billed."""
        with closing(sqlite3.connect(self.path)) as db:
            limit = db.execute('SELECT micro_usd FROM test_allowance WHERE id=1').fetchone()[0]
            rows = db.execute('SELECT provider,COUNT(*),SUM(COALESCE(actual,0)),SUM(CASE WHEN actual IS NULL THEN reserved ELSE 0 END),SUM(CASE WHEN actual IS NULL THEN 1 ELSE 0 END) FROM test_requests GROUP BY provider').fetchall()
        held = sum(r[3] for r in rows)
        recorded = sum(r[2] for r in rows)
        return {'limit_micro_usd': limit, 'reserved_micro_usd': held, 'cutover_at': self.cutover_at(),
                'recorded_micro_usd': recorded, 'unreconciled_requests': sum(r[4] for r in rows),
                'remaining_micro_usd': max(0, limit-held-recorded),
                'providers': [{'provider': r[0], 'requests': r[1], 'recorded_micro_usd': r[2], 'reserved_micro_usd': r[3]} for r in rows]}
