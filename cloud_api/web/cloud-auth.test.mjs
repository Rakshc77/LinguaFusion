import test from 'node:test';
import assert from 'node:assert/strict';
import { createCloudAuth } from './cloud-auth.mjs';
import { firebaseConfig } from './firebase-config.mjs';

function fixture() {
  const calls = [];
  const auth = { currentUser: null, async authStateReady() {} };
  const user = { uid: 'test-user', email: 'test@example.invalid', emailVerified: false,
    async getIdToken() { return 'test-token'; },
    async reload() { calls.push(['reload']); } };
  const sdk = {
    getApps: () => [],
    initializeApp(config, name) { calls.push(['initialize', config.projectId, name]); return {}; },
    getAuth: () => auth,
    browserLocalPersistence: 'local', browserSessionPersistence: 'session',
    async setPersistence(_, mode) { calls.push(['persistence', mode]); },
    async signInWithEmailAndPassword(_, email) { calls.push(['login', email]); auth.currentUser = user; return { user }; },
    async signOut() { auth.currentUser = null; },
    onAuthStateChanged(_, listener) { listener(auth.currentUser); return () => {}; },
    async createUserWithEmailAndPassword(_, email) { calls.push(['signup', email]); auth.currentUser = user; return { user }; },
    async sendEmailVerification(target) { calls.push(['verify-email', target.uid]); },
  };
  return { calls, auth, user, sdk, client: createCloudAuth(async () => sdk) };
}

test('configuration identifies the registered project and app', () => {
  assert.equal(firebaseConfig.projectId, 'linguafusion-f24fe');
  assert.equal(firebaseConfig.appId, '1:936319167298:web:bf4d9d2af28a85a9cd76db');
  assert.ok(Object.isFrozen(firebaseConfig));
});
test('offline construction does not load Firebase; blank login is rejected locally', async () => {
  let loads = 0;
  const client = createCloudAuth(async () => { loads++; });
  assert.equal(loads, 0);
  await assert.rejects(client.signIn('', ''), /Enter your email/);
  assert.equal(loads, 0);
});
test('session persistence by default, remember-me opt-in, identity-only result', async () => {
  const f = fixture();
  assert.deepEqual(await f.client.signIn(' test@example.invalid ', 'test-password'), { uid: 'test-user', email: 'test@example.invalid' });
  assert.deepEqual(f.calls[1], ['persistence', 'session']);
  await f.client.signIn('test@example.invalid', 'test-password', true);
  assert.ok(f.calls.some(call => call[0] === 'persistence' && call[1] === 'local'));
  assert.equal(f.calls.filter(call => call[0] === 'initialize').length, 1);
});
test('signed-out access fails and logout removes access', async () => {
  const f = fixture();
  await assert.rejects(f.client.authorizationHeader(), /Sign in/);
  await f.client.signIn('test@example.invalid', 'test-password');
  assert.deepEqual(await f.client.authorizationHeader(), { Authorization: 'Bearer test-token' });
  await f.client.signOut();
  await assert.rejects(f.client.authorizationHeader(), /Sign in/);
});
test('provider failures never expose raw credentials or errors', async () => {
  const f = fixture();
  f.sdk.signInWithEmailAndPassword = async () => { throw new Error('private-provider-error'); };
  await assert.rejects(f.client.signIn('test@example.invalid', 'test-password'), error => !error.message.includes('private-provider-error'));
});
test('failed SDK initialization can be retried', async () => {
  const f = fixture(); let tries = 0;
  const client = createCloudAuth(async () => { if (++tries === 1) throw new Error('network'); return f.sdk; });
  await assert.rejects(client.authorizationHeader(), /could not load/);
  await client.signIn('test@example.invalid', 'test-password');
  assert.equal(tries, 2);
});
test('logout during token refresh cannot return the old token', async () => {
  const f = fixture();
  await f.client.signIn('test@example.invalid', 'test-password');
  f.user.getIdToken = async () => { f.auth.currentUser = null; return 'old-token'; };
  await assert.rejects(f.client.authorizationHeader(), /session could not be refreshed/);
});
test('stalled setup fails instead of leaving disabled inputs forever', async () => {
  const client = createCloudAuth(() => new Promise(() => {}), 10);
  await assert.rejects(client.authorizationHeader(), /could not load/);
});
test('observer reports restored identity without exposing tokens', async () => {
  const f = fixture();
  await f.client.signIn('test@example.invalid', 'test-password');
  const stop = await f.client.observe(identity => assert.deepEqual(identity, { uid:'test-user', email:'test@example.invalid', emailVerified:false }));
  assert.equal(typeof stop, 'function');
});

test('sign-up creates the account and immediately sends a confirmation email', async () => {
  const f = fixture();
  const identity = await f.client.signUp(' new@example.invalid ', 'a-good-password');
  assert.deepEqual(identity, { uid: 'test-user', email: 'test@example.invalid', emailVerified: false });
  assert.ok(f.calls.some(c => c[0] === 'signup' && c[1] === 'new@example.invalid'), 'address is trimmed');
  assert.ok(f.calls.some(c => c[0] === 'verify-email'), 'a new account must be asked to confirm its address');
});

test('weak or missing sign-up details are rejected before Firebase loads', async () => {
  let loads = 0;
  const client = createCloudAuth(async () => { loads++; });
  await assert.rejects(client.signUp('', 'a-good-password'), /Enter your email/);
  await assert.rejects(client.signUp('a@b.invalid', 'short'), /at least 8 characters/);
  assert.equal(loads, 0, 'local validation must not require the network');
});

test('an already-registered address is reported as such, not as a generic failure', async () => {
  const f = fixture();
  f.sdk.createUserWithEmailAndPassword = async () => { throw { code: 'auth/email-already-in-use' }; };
  await assert.rejects(f.client.signUp('a@b.invalid', 'a-good-password'), /already has an account/);
});

test('verification state is re-read from the server, not trusted from cache', async () => {
  const f = fixture();
  await f.client.signIn('test@example.invalid', 'test-password');
  assert.equal(await f.client.refreshVerification(), false);
  assert.ok(f.calls.some(c => c[0] === 'reload'), 'must reload rather than reuse the cached flag');
  f.user.emailVerified = true;
  assert.equal(await f.client.refreshVerification(), true);
});

test('resending a confirmation requires a signed-in account', async () => {
  const f = fixture();
  await assert.rejects(f.client.sendVerification(), /Sign in first/);
  await f.client.signIn('test@example.invalid', 'test-password');
  await f.client.sendVerification();
  assert.ok(f.calls.filter(c => c[0] === 'verify-email').length >= 1);
});
