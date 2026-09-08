import test from 'node:test';
import assert from 'node:assert/strict';
import { pronunciationView, validateRequest, MAX_PRONUNCIATION_CHARACTERS } from './pronunciation.mjs';

const HINDI = 'नमस्ते';
const ARABIC = 'مرحبا';

function reply(overrides = {}) {
  return { ok: true, native: HINDI, romanized: 'Namaste', language: 'hi', approximate: true,
           notice: 'Approximate pronunciation, not an English translation.', ...overrides };
}

test('a valid guide keeps the native text and is marked approximate', () => {
  const view = pronunciationView(HINDI, 'hi', reply());
  assert.equal(view.ok, true);
  assert.equal(view.native, HINDI, 'native text must survive untouched');
  assert.equal(view.romanized, 'Namaste');
  assert.equal(view.languageName, 'Hindi');
  assert.match(view.notice, /not an English translation/);
});

test('a response that rewrote the source is discarded', () => {
  // The model translating instead of transliterating is the failure this pane
  // exists to avoid showing.
  const view = pronunciationView(HINDI, 'hi', reply({ native: 'Hello' }));
  assert.equal(view.ok, false);
  assert.match(view.message, /did not match your text/);
});

test('a guide still in native script is discarded', () => {
  const view = pronunciationView(HINDI, 'hi', reply({ romanized: HINDI }));
  assert.equal(view.ok, false);
  assert.match(view.message, /not in Latin script/);
});

test('a guide that drops the approximate flag is discarded', () => {
  assert.equal(pronunciationView(HINDI, 'hi', reply({ approximate: false })).ok, false);
  assert.equal(pronunciationView(HINDI, 'hi', reply({ approximate: undefined })).ok, false);
});

test('a guide for a different language is discarded', () => {
  const view = pronunciationView(ARABIC, 'ar', reply({ native: ARABIC, language: 'hi' }));
  assert.equal(view.ok, false);
  assert.match(view.message, /language/);
});

test('an empty or failed response never renders a pane', () => {
  assert.equal(pronunciationView(HINDI, 'hi', reply({ romanized: '   ' })).ok, false);
  assert.equal(pronunciationView(HINDI, 'hi', { ok: false }).ok, false);
  assert.equal(pronunciationView(HINDI, 'hi', null).ok, false);
});

test('accents and hyphens in a guide are accepted', () => {
  const view = pronunciationView(HINDI, 'hi', reply({ romanized: 'na-más-te, ji!' }));
  assert.equal(view.ok, true);
  assert.equal(view.romanized, 'na-más-te, ji!');
});

test('a missing notice falls back to the approximate warning', () => {
  const view = pronunciationView(HINDI, 'hi', reply({ notice: '' }));
  assert.equal(view.ok, true);
  assert.match(view.notice, /Approximate pronunciation/);
});

test('requests are bounded and limited to the supported languages', () => {
  assert.equal(validateRequest('   ', 'hi').ok, false);
  assert.equal(validateRequest(HINDI, 'en').ok, false);
  assert.equal(validateRequest(HINDI, 'de').ok, false);
  assert.equal(validateRequest('x'.repeat(MAX_PRONUNCIATION_CHARACTERS + 1), 'hi').ok, false);
  assert.deepEqual(validateRequest(`  ${HINDI}  `, 'hi'), { ok: true, text: HINDI });
  for (const language of ['hi', 'ar', 'or']) {
    assert.equal(validateRequest(HINDI, language).ok, true);
  }
});
