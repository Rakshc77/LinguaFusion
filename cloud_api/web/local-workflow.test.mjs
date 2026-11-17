import test from 'node:test';
import assert from 'node:assert/strict';
import { clearLocalHistory, historyEnabled, localHistory, recentPairs,
         rememberRecentPair, removeHistoryEntry, saveHistoryEntry,
         setHistoryEnabled } from './local-workflow.mjs';

function memory() {
  const values = new Map();
  return { getItem:key => values.get(key) ?? null, setItem:(key,value) => values.set(key,value),
    removeItem:key => values.delete(key) };
}

test('history preserves complete long source and result text', () => {
  const store = memory();
  setHistoryEnabled(store, true);
  const input = 'Grüße مرحبا नमस्ते ନମସ୍କାର '.repeat(1000);
  const output = 'Complete transcript. 😀 '.repeat(2000);
  saveHistoryEntry(store, {kind:'transcript', input, output}, 1, 'long');
  assert.equal(localHistory(store)[0].input, input);
  assert.equal(localHistory(store)[0].output, output);
});

test('storage failure retains previous history and never claims the new result was saved', () => {
  const store = memory();
  setHistoryEnabled(store, true);
  saveHistoryEntry(store, {output:'Previous result'}, 1, 'old');
  store.setItem = () => { throw new Error('Quota exceeded'); };
  const returned = saveHistoryEntry(store, {output:'Long result. '.repeat(1000)}, 2, 'new');
  assert.deepEqual(returned.map(item => item.id), ['old']);
  assert.deepEqual(localHistory(store).map(item => item.id), ['old']);
});

test('recent pairs are validated, deduplicated and capped at three', () => {
  const store = memory(); const sources = ['auto','en','de','fr']; const targets = ['en','de','fr'];
  rememberRecentPair(store,{source:'en',target:'de'},sources,targets);
  rememberRecentPair(store,{source:'de',target:'fr'},sources,targets);
  rememberRecentPair(store,{source:'auto',target:'en'},sources,targets);
  rememberRecentPair(store,{source:'fr',target:'de'},sources,targets);
  rememberRecentPair(store,{source:'fr',target:'de'},sources,targets);
  assert.deepEqual(recentPairs(store,sources,targets),[
    {source:'fr',target:'de'},{source:'auto',target:'en'},{source:'de',target:'fr'}]);
});

test('private history is opt-in, bounded and individually removable', () => {
  const store = memory();
  saveHistoryEntry(store,{kind:'translation',output:'secret'},1,'one');
  assert.deepEqual(localHistory(store),[]);
  assert.equal(historyEnabled(store),false);
  setHistoryEnabled(store,true);
  for (let index=0; index<14; index++) saveHistoryEntry(store,{kind:'translation',output:`result ${index}`},index,`id-${index}`);
  assert.equal(localHistory(store).length,12);
  removeHistoryEntry(store,'id-13');
  assert.equal(localHistory(store).some(entry => entry.id === 'id-13'),false);
  clearLocalHistory(store);
  assert.deepEqual(localHistory(store),[]);
});
