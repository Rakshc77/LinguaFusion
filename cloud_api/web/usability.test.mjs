import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('./pilot.mjs', import.meta.url), 'utf8');
function harness(saved) {
  const elements = new Map();
  const $ = id => {
    if (!elements.has(id)) elements.set(id, {value:'', addEventListener(event, fn) {this[event]=fn;}});
    return elements.get(id);
  };
  $('source').value = 'auto';
  let message = '';
  const context = vm.createContext({$, languages:[['en','English'],['de','German']],
    translating:false, status: value => { message=value; },
    localStorage:{getItem:()=>saved, setItem:(_, value)=>{saved=value;}}});
  vm.runInContext(source.slice(source.indexOf("$('target').value = 'de';"),
    source.indexOf('for (const [value, text] of PRONUNCIATION_LANGUAGES')), context);
  return {$, context, get saved(){return saved;}, get message(){return message;}};
}
test('swapping keeps input intact, remembers the pair and does not guess automatic detection', () => {
  const h = harness(null);
  h.$('text').value='Keep this text';
  h.$('swapLanguages').click();
  assert.match(h.message,/Choose a source/);
  h.$('source').value='en';
  h.$('swapLanguages').click();
  assert.equal(h.$('source').value,'de');
  assert.equal(h.$('target').value,'en');
  assert.equal(h.$('text').value,'Keep this text');
  assert.deepEqual(JSON.parse(h.saved),{source:'de',target:'en'});
  const next = harness(h.saved);
  assert.equal(next.$('source').value,'de');
  vm.runInContext('translating=true',next.context);
  next.$('swapLanguages').click();
  assert.equal(next.$('source').value,'de');
});
test('invalid stored language pairs fall back to automatic detection and German', () => {
  for (const saved of ['broken', '{"source":"xx","target":"en"}']) {
    const h = harness(saved);
    assert.equal(h.$('source').value,'auto');
    assert.equal(h.$('target').value,'de');
  }
});
