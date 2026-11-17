import test from 'node:test';
import assert from 'node:assert/strict';
import { createRecordingDraftStore } from './recording-draft.mjs';

test('unfinished audio remains available in memory when IndexedDB is unavailable', async () => {
  const store = createRecordingDraftStore();
  const draft = { uid:'one', createdAt:Date.now(), parts:[new Blob(['audio'])], texts:[null] };
  assert.equal(await store.save(draft), false);
  assert.equal(await store.load('one'), draft);
  assert.equal(await store.load('another-account'), null);
  await store.remove('one');
  assert.equal(await store.load('one'), null);
});

test('expired audio drafts are removed', async () => {
  const store = createRecordingDraftStore();
  await store.save({ uid:'expired', createdAt:Date.now() - 25 * 60 * 60 * 1000,
    parts:[new Blob(['audio'])], texts:[null] });
  assert.equal(await store.load('expired'), null);
});

test('draft persistence waits for transaction commit, not request success', async () => {
  const previous = globalThis.indexedDB;
  let tx, request, closed = false;
  globalThis.indexedDB = {open() {
    const opening = {};
    queueMicrotask(() => {
      opening.result = {
        close() { closed = true; },
        transaction() {
          tx = { objectStore:() => ({put() { request = {}; return request; }}) };
          return tx;
        },
      };
      opening.onsuccess();
    });
    return opening;
  }};
  try {
    const store = createRecordingDraftStore();
    let settled = false;
    const saving = store.save({uid:'commit',createdAt:Date.now(),parts:[new Blob(['audio'])],texts:[null]})
      .then(value => { settled = true; return value; });
    await new Promise(setImmediate);
    request.result = 'account:commit';
    request.onsuccess?.();
    await new Promise(setImmediate);
    assert.equal(settled, false);
    tx.oncomplete();
    assert.equal(await saving, true);
    assert.equal(closed, true);
  } finally { globalThis.indexedDB = previous; }
});

test('a transaction aborted after request success reports memory-only recovery', async () => {
  const previous = globalThis.indexedDB;
  let tx, request;
  globalThis.indexedDB = {open() {
    const opening = {};
    queueMicrotask(() => {
      opening.result = {close() {}, transaction() {
        tx = {objectStore:() => ({put() { request = {}; return request; }})};
        return tx;
      }};
      opening.onsuccess();
    });
    return opening;
  }};
  const store = createRecordingDraftStore();
  const draft = {uid:'aborted',createdAt:Date.now(),parts:[new Blob(['audio'])],texts:[null]};
  try {
    const saving = store.save(draft);
    await new Promise(setImmediate);
    request.onsuccess?.();
    tx.error = new Error('Quota exceeded');
    tx.onabort();
    assert.equal(await saving, false);
  } finally { globalThis.indexedDB = previous; }
  assert.equal(await store.load('aborted'), draft);
  store.forgetMemory();
});
