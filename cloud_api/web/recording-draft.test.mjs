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
