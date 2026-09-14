import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createReadAloudController, normaliseReadLanguage, prepareReadAloudRequest } from './read-aloud.mjs';

test('requests validate result id, language, speed, emptiness and length', () => {
  assert.equal(normaliseReadLanguage('AR-SA'), 'ar');
  assert.equal(normaliseReadLanguage('unknown'), '');
  assert.deepEqual(prepareReadAloudRequest({ id:'translation', text:' Hallo ', language:'de-DE', rate:1 }), {
    id:'translation', text:'Hallo', language:'de', rate:1,
  });
  assert.match(prepareReadAloudRequest({ id:'bad id', text:'Hello', language:'en', rate:1 }).error, /cannot/);
  assert.match(prepareReadAloudRequest({ id:'x', text:' ', language:'en', rate:1 }).error, /nothing/);
  assert.match(prepareReadAloudRequest({ id:'x', text:'Hello', language:'xx', rate:1 }).error, /language/);
  assert.match(prepareReadAloudRequest({ id:'x', text:'Hello', language:'en', rate:2 }).error, /speed/);
  assert.match(prepareReadAloudRequest({ id:'x', text:'a'.repeat(12001), language:'en', rate:1 }).error, /12,000/);
});

function browserHarness() {
  const states = [];
  const spoken = [];
  class Utterance { constructor(text) { this.text = text; } }
  const synthesis = {
    cancelled:0,
    voices:[
      { lang:'de-DE', localService:false, default:true, name:'Network German' },
      { lang:'de', localService:true, default:false, name:'Local German' },
    ],
    getVoices() { return this.voices; },
    cancel() { this.cancelled++; },
    speak(value) { spoken.push(value); },
  };
  const controller = createReadAloudController({
    scope:{ speechSynthesis:synthesis, SpeechSynthesisUtterance:Utterance },
    onState:value => states.push(value),
  });
  return { controller, synthesis, states, spoken };
}

test('browser speech chooses a matching local voice and finishes once', () => {
  const h = browserHarness();
  assert.equal(h.controller.read({ id:'translation', text:'Guten Tag', language:'de', rate:1.25 }), true);
  assert.equal(h.spoken.length, 1);
  assert.equal(h.spoken[0].voice.name, 'Local German');
  assert.equal(h.spoken[0].lang, 'de');
  assert.equal(h.spoken[0].rate, 1.25);
  h.spoken[0].onend();
  assert.equal(h.controller.activeId, '');
  assert.equal(h.states.at(-1).state, 'done');
});

test('only one browser utterance is active and the same button toggles stop', () => {
  const h = browserHarness();
  h.controller.read({ id:'one', text:'One', language:'en', rate:1 });
  h.controller.read({ id:'two', text:'Two', language:'en', rate:1 });
  assert.equal(h.states.some(value => value.id === 'one' && value.state === 'stopped'), true);
  assert.equal(h.controller.activeId, 'two');
  h.controller.read({ id:'two', text:'Two', language:'en', rate:1 });
  assert.equal(h.controller.activeId, '');
  assert.equal(h.states.at(-1).state, 'stopped');
});

test('native messages carry only the validated narrow speech contract', () => {
  const sent = [];
  const states = [];
  const native = { postMessage:value => sent.push(JSON.parse(value)), onmessage:null };
  const controller = createReadAloudController({ scope:{ LinguaFusionReadAloud:native }, onState:value => states.push(value) });
  controller.read({ id:'ocr', text:'Bonjour', language:'fr', rate:0.75, ignored:'secret' });
  assert.deepEqual(sent.at(-1), { type:'speak', id:'ocr', text:'Bonjour', language:'fr', rate:0.75 });
  native.onmessage({ data:JSON.stringify({ id:'wrong', state:'done' }) });
  assert.equal(controller.activeId, 'ocr');
  native.onmessage({ data:JSON.stringify({ id:'ocr', state:'done', message:'Finished.' }) });
  assert.equal(controller.activeId, '');
  assert.equal(states.at(-1).message, 'Finished.');
});

test('unavailable speech fails honestly without throwing', () => {
  const states = [];
  const controller = createReadAloudController({ scope:{}, onState:value => states.push(value) });
  assert.equal(controller.available, false);
  assert.equal(controller.read({ id:'ocr', text:'Hello', language:'en', rate:1 }), false);
  assert.match(states.at(-1).message, /unavailable/);
});

test('all three online results expose the shared local action without a paid API route', () => {
  const page = readFileSync(new URL('./index.html', import.meta.url), 'utf8');
  const app = readFileSync(new URL('./pilot.mjs', import.meta.url), 'utf8');
  for (const id of ['readTranscript', 'readTranslation', 'readOcr']) {
    assert.match(page, new RegExp(`id="${id}"`));
  }
  assert.match(app, /createReadAloudController/);
  assert.match(app, /readAloud\.read/);
  assert.doesNotMatch(app, /api\.request\([^\n]*read.?aloud/i);
  const cleanup = app.slice(app.indexOf('function clearPrivateText()'), app.indexOf('// --- capability gating'));
  assert.match(cleanup, /readAloud\.stop/);
});
