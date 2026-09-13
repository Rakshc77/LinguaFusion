import test from 'node:test';
import assert from 'node:assert/strict';
import { createCloudClient } from './cloud-client.mjs';
const auth = { async authorizationHeader() { return { Authorization: 'Bearer fake' }; } };
test('only same-origin fixed endpoints can receive identity', async () => {
  let calls = 0;
  const client = createCloudClient(auth, async (url, options) => {
    calls++; assert.equal(url, '/capabilities'); assert.equal(options.redirect, 'error');
    assert.equal(options.credentials, 'omit');
    return new Response('{"mode":"cloud-pilot"}', { status:200 });
  });
  await assert.rejects(client.request('https://example.invalid/translate'), /Unsupported/);
  assert.equal(calls, 0);
  assert.equal((await client.request('/capabilities')).mode, 'cloud-pilot');
});
test('owner invitation routes are fixed and malformed identifiers stay blocked', async () => {
  const calls = [];
  const client = createCloudClient(auth, async (url, options) => {
    calls.push([url, options.method]);
    return new Response('{"ok":true,"invites":[]}', { status:200 });
  });
  await client.request('/owner/invites');
  await client.request('/owner/invites', new FormData());
  await client.request('/owner/invites/' + 'a'.repeat(64), null, { method:'DELETE' });
  await assert.rejects(client.request('/owner/invites/not-a-digest'), /Unsupported/);
  await assert.rejects(client.request('/owner/invites/' + 'a'.repeat(64) + '?leak=1'), /Unsupported/);
  assert.deepEqual(calls, [
    ['/owner/invites', 'GET'], ['/owner/invites', 'POST'],
    ['/owner/invites/' + 'a'.repeat(64), 'DELETE'],
  ]);
});
test('a spent or expired invitation has a useful message', async () => {
  const client = createCloudClient(auth, async () => new Response('', { status:410 }));
  await assert.rejects(client.request('/access/request', new FormData()), /no longer available/);
});
test('server error text is never displayed', async () => {
  const client = createCloudClient(auth, async () => new Response('private details', { status:403 }));
  await assert.rejects(client.request('/capabilities'), /not been approved/);
});
test('deadline also bounds a stalled token refresh', async () => {
  const client = createCloudClient({ authorizationHeader: () => new Promise(() => {}) }, () => { throw new Error('must not fetch'); }, 10);
  await assert.rejects(client.request('/capabilities'), /timed out/);
});
test('logout during identity retrieval prevents any request', async () => {
  let resolveToken;
  const client = createCloudClient({ authorizationHeader: () => new Promise(resolve => { resolveToken = resolve; }) }, () => { throw new Error('must not fetch'); });
  const request = client.request('/capabilities');
  client.cancel(); resolveToken({ Authorization:'Bearer stale' });
  await assert.rejects(request, /stopped|canceled/);
});
test('late response after logout is discarded', async () => {
  let resolveResponse;
  const client = createCloudClient(auth, () => new Promise(resolve => { resolveResponse = resolve; }));
  const request = client.request('/translate', new FormData());
  await new Promise(resolve => setImmediate(resolve));
  client.cancel();
  resolveResponse(new Response('{"translated_text":"stale"}'));
  await assert.rejects(request, /stopped|canceled/);
});
