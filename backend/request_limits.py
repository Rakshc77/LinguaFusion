"""Bound bodies before multipart parsing, and bound concurrent uploads."""
import asyncio
import tempfile
import threading

from starlette.responses import JSONResponse


class RequestLimitsMiddleware:
    def __init__(self, app, max_bytes, max_uploads=4, timeout_seconds=120, path_limits=None):
        self.app = app
        self.max_bytes = max_bytes
        # Exact-path overrides for routes that legitimately carry audio or images.
        # Anything not listed keeps the smaller default; a larger cap is never
        # inferred from a prefix, so a new path cannot silently inherit one.
        self.path_limits = dict(path_limits or {})
        if any(type(v) is not int or v <= 0 for v in self.path_limits.values()):
            raise ValueError('Each path limit must be a positive byte count')
        self.max_uploads = max_uploads
        self.timeout_seconds = timeout_seconds
        self._uploads = 0
        self._lock = threading.Lock()

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] not in {'POST', 'PUT', 'PATCH'}:
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        # Match on the raw path before routing, so the cap applies to the same
        # bytes the parser would otherwise buffer.
        max_bytes = self.path_limits.get(scope.get('path', ''), self.max_bytes)

        async def reject(status, detail):
            response = JSONResponse({'detail': detail}, status_code=status,
                                    headers={'Retry-After': '5'} if status == 429 else None)
            await response(scope, receive, send)

        try:
            length = int(headers.get(b'content-length', b'0'))
            if length < 0:
                raise ValueError()
        except ValueError:
            return await reject(400, 'Invalid Content-Length.')
        if length > max_bytes:
            return await reject(413, 'Request is too large. Send fewer or smaller files.')
        is_upload = headers.get(b'content-type', b'').lower().startswith(b'multipart/')
        acquired = False
        if is_upload:
            with self._lock:
                if self._uploads < self.max_uploads:
                    self._uploads += 1
                    acquired = True
            if not acquired:
                return await reject(429, 'Uploads are busy. Please try again shortly.')
        try:
            # Roll larger bodies to disk; never accumulate an unbounded byte string.
            with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as body:
                total = 0
                deadline = asyncio.get_running_loop().time() + self.timeout_seconds
                while True:
                    remaining = deadline - asyncio.get_running_loop().time()
                    try:
                        message = await asyncio.wait_for(receive(), timeout=max(0, remaining))
                    except asyncio.TimeoutError:
                        return await reject(408, 'Upload timed out. Please try again.')
                    if message['type'] == 'http.disconnect':
                        return
                    chunk = message.get('body', b'')
                    total += len(chunk)
                    if total > max_bytes:
                        return await reject(413, 'Request is too large. Send fewer or smaller files.')
                    await asyncio.to_thread(body.write, chunk)
                    if not message.get('more_body', False):
                        break
                body.seek(0)
                replayed = 0

                async def replay():
                    nonlocal replayed
                    if replayed >= total and replayed != -1:
                        if total == 0:
                            replayed = -1
                            return {'type': 'http.request', 'body': b'', 'more_body': False}
                        return await receive()
                    if replayed == -1:
                        return await receive()
                    data = await asyncio.to_thread(body.read, 1024 * 1024)
                    replayed += len(data)
                    return {'type': 'http.request', 'body': data, 'more_body': replayed < total}

                await self.app(scope, replay, send)
        finally:
            if acquired:
                with self._lock:
                    self._uploads -= 1
