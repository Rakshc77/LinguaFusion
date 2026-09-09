import asyncio
import io
import sqlite3
import zipfile

import pytest
from fastapi import UploadFile, HTTPException

from backend.request_limits import RequestLimitsMiddleware
from scripts.storage_backup import create_backup, restore_backup, verify_backup


def test_streamed_limit_rejects_before_parser_and_releases_slot():
    async def run():
        calls = []
        async def app(scope, receive, send):
            calls.append(await receive())
        middleware = RequestLimitsMiddleware(app, max_bytes=4, max_uploads=1)
        scope = {'type': 'http', 'method': 'POST', 'headers': [(b'content-type', b'multipart/form-data')]}
        messages = iter([{'type': 'http.request', 'body': b'123', 'more_body': True}, {'type': 'http.request', 'body': b'45'}])
        sent = []
        async def receive():
            return next(messages)
        async def send(message):
            sent.append(message)
        await middleware(scope, receive, send)
        assert sent[0]['status'] == 413 and not calls and middleware._uploads == 0
        messages = iter([{'type': 'http.request', 'body': b'1234'}])
        await middleware(scope, receive, send)
        assert calls[0]['body'] == b'1234' and middleware._uploads == 0
    asyncio.run(run())


def test_upload_capacity_preserves_health_and_recovers_after_failure():
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        async def app(scope, receive, send):
            if scope['method'] == 'GET':
                return await send({'type': 'http.response.start', 'status': 200})
            entered.set()
            await release.wait()
            raise RuntimeError('test processor failure')
        middleware = RequestLimitsMiddleware(app, 10, max_uploads=1)
        sent = []
        async def receive():
            return {'type': 'http.request', 'body': b'ok'}
        async def send(message):
            sent.append(message)
        scope = {'type': 'http', 'method': 'POST', 'headers': [(b'content-type', b'multipart/form-data')]}
        first = asyncio.create_task(middleware(scope, receive, send))
        await entered.wait()
        await middleware(scope, receive, send)
        assert sent[0]['status'] == 429
        await middleware({**scope, 'method': 'GET'}, receive, send)
        assert sent[-1]['status'] == 200
        release.set()
        with pytest.raises(RuntimeError):
            await first
        assert middleware._uploads == 0
    asyncio.run(run())


def test_batch_limits(monkeypatch):
    import backend.server as server
    monkeypatch.setattr(server, 'MAX_UPLOAD_BYTES', 4)
    monkeypatch.setattr(server, 'MAX_BATCH_FILES', 2)
    def files(*values):
        return [UploadFile(filename='test.txt', file=io.BytesIO(value)) for value in values]
    assert server.read_batch_uploads(files(b'12', b'34')) == [('test.txt', b'12'), ('test.txt', b'34')]
    for batch in (files(b'12', b'345'), files(b'1', b'2', b'3')):
        with pytest.raises(HTTPException) as error:
            server.read_batch_uploads(batch)
        assert error.value.status_code == 413


def test_declared_length_timeout_and_disconnect_do_not_reach_parser():
    async def run():
        async def app(*args):
            raise AssertionError('Parser must not run')
        middleware = RequestLimitsMiddleware(app, 4, timeout_seconds=0.01)
        sent = []
        async def send(message):
            sent.append(message)
        async def slow_receive():
            await asyncio.sleep(1)
        scope = {'type': 'http', 'method': 'POST', 'headers': [(b'content-length', b'5')]}
        await middleware(scope, slow_receive, send)
        assert sent[0]['status'] == 413
        sent.clear()
        scope['headers'] = [(b'content-type', b'multipart/form-data')]
        await middleware(scope, slow_receive, send)
        assert sent[0]['status'] == 408 and middleware._uploads == 0
        async def disconnected():
            return {'type': 'http.disconnect'}
        sent.clear()
        await middleware(scope, disconnected, send)
        assert not sent and middleware._uploads == 0
    asyncio.run(run())


def test_backup_of_live_wal_database_and_restore(tmp_path):
    storage = tmp_path / 'storage'
    storage.mkdir()
    with sqlite3.connect(storage / 'notes.db') as database:
        database.execute('PRAGMA journal_mode=WAL')
        database.execute('CREATE TABLE notes (text TEXT)')
        database.execute("INSERT INTO notes VALUES ('private test note')")
        database.commit()
        (storage / 'key.txt').write_text('test-key')
        archive = create_backup(storage, tmp_path / 'backups')
    assert len(verify_backup(archive)['files']) == 2
    target = restore_backup(archive, tmp_path / 'recovered')
    with sqlite3.connect(target / 'notes.db') as database:
        assert database.execute('SELECT text FROM notes').fetchone()[0] == 'private test note'
    assert (target / 'key.txt').read_text() == 'test-key'
    with pytest.raises(FileExistsError):
        restore_backup(archive, target)
    with zipfile.ZipFile(archive, 'a') as damaged:
        damaged.writestr('../escape.txt', 'invalid')
    with pytest.raises(ValueError):
        restore_backup(archive, tmp_path / 'unsafe')
    assert not (tmp_path / 'unsafe').exists()
