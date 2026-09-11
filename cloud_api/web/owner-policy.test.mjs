import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('./pilot.mjs', import.meta.url), 'utf8');
const handler = source.slice(
  source.indexOf("$('ownerPolicyForm').addEventListener('submit'"),
  source.indexOf('// --- access'));

function harness({failSave = false, failUsage = false} = {}) {
  const elements = new Map();
  const $ = id => {
    if (!elements.has(id)) elements.set(id, {
      value: '', checked: false, disabled: false, hidden: false,
      textContent: '', attributes: new Map(),
      addEventListener(name, fn) { this[name] = fn; },
      setAttribute(name, value) { this.attributes.set(name, value); },
      removeAttribute(name) { this.attributes.delete(name); },
    });
    return elements.get(id);
  };
  $('policyUid').value = 'friend_uid';
  $('policyEnabled').checked = true;
  $('policyRequests').value = '42';
  $('policyBudget').value = '1.25';
  const requests = [];
  let collapsed = false;
  let ownerLoads = 0;
  let globalStatus = '';
  class TestFormData {
    constructor() { this.values = new Map(); }
    set(name, value) { this.values.set(name, value); }
  }
  const api = {async request(path, body) {
    requests.push({path, body});
    if (path.startsWith('/owner/users/') && failSave) throw new Error('Save failed safely.');
    if (path === '/usage' && failUsage) throw new Error('Totals unavailable.');
    return path === '/usage' ? {month:'2026-09', estimated_spent_usd:'0.00',
      unresolved_reserved_usd:'0.00', remaining_usd:'1.25', budget_usd:'1.25'} : {};
  }};
  const context = vm.createContext({$, epoch:1, api, FormData:TestFormData,
    showAdvanced: open => { collapsed = !open; },
    loadOwner: async () => { ownerLoads++; },
    showSpending: () => {}, status: value => { globalStatus = value; }});
  vm.runInContext(handler, context);
  return {$, requests, submit: () => $('ownerPolicyForm').submit({preventDefault(){}}),
    get collapsed(){return collapsed;}, get ownerLoads(){return ownerLoads;},
    get globalStatus(){return globalStatus;}};
}

test('successful policy save gives local feedback, collapses and refreshes', async () => {
  const h = harness();
  await h.submit();
  assert.equal(h.collapsed, true);
  assert.match(h.$('policyStatus').textContent, /Policy saved/);
  assert.equal(h.$('savePolicy').disabled, false);
  assert.equal(h.$('savePolicy').textContent, 'Save user policy');
  assert.equal(h.$('ownerPolicyForm').attributes.has('aria-busy'), false);
  assert.equal(h.ownerLoads, 1);
  assert.equal(h.requests[0].path, '/owner/users/friend_uid');
  assert.deepEqual(Object.fromEntries(h.requests[0].body.values), {
    enabled:'true', monthly_limit:'42', monthly_budget_usd:'1.25'});
});

test('failed policy save stays open and reports the error beside the editor', async () => {
  const h = harness({failSave:true});
  await h.submit();
  assert.equal(h.collapsed, false);
  assert.equal(h.$('policyStatus').textContent, 'Save failed safely.');
  assert.equal(h.$('savePolicy').disabled, false);
  assert.equal(h.ownerLoads, 0);
});

test('a totals refresh failure does not disguise a committed policy', async () => {
  const h = harness({failUsage:true});
  await h.submit();
  assert.equal(h.collapsed, true);
  assert.match(h.$('policyStatus').textContent, /Policy saved/);
  assert.match(h.globalStatus, /Policy saved/);
});
