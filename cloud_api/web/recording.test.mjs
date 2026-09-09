import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { buildWav } from './wav.mjs';

// Execute the shipped recording handlers, not a duplicate implementation.
const source = readFileSync(new URL('./pilot.mjs', import.meta.url), 'utf8');
function harness(rate = 48000) {
  const elements = new Map();
  const pending = [];
  const streams = [];
  const contexts = [];
  const events = {};
  const requests = [];
  const $ = id => {
    if (!elements.has(id)) elements.set(id, { checked: true, textContent: '', addEventListener(type, fn) { this[type] = fn; } });
    return elements.get(id);
  };
  const node = () => ({ connect() {}, disconnect() {} });
  class AudioContext {
    constructor() { this.sampleRate = rate; this.state = 'running'; contexts.push(this); }
    createMediaStreamSource() { return node(); }
    createScriptProcessor() { return this.processor = node(); }
    createGain() { return { ...node(), gain: {} }; }
    async close() { this.closed = true; }
  }
  const sandbox = vm.createContext({ $, window: { AudioContext, location: {}, addEventListener: (type, fn) => events[type] = fn },
    document: { addEventListener() {} }, navigator: { mediaDevices: { getUserMedia() {
      return new Promise(resolve => pending.push(() => {
        const track = { stopped: false, stop() { this.stopped = true; } };
        streams.push(track); resolve({ getTracks: () => [track] });
      }));
    } } }, Float32Array, Uint8Array, Blob, FormData, setTimeout, atob,
    crypto: { randomUUID: () => 'test-request' }, buildWav, MAX_SECONDS: 60,
    api: { async request(path, body) { requests.push({ path, body }); return { text: 'Test' }; } },
    showSpending() {}, microphoneProblem: error => error.name });
  const stop = source.slice(source.indexOf('function stopCapture()'), source.indexOf('function clearPrivateText()'));
  const recording = source.slice(source.indexOf('async function openMicrophone()'), source.indexOf('// --- picture reading'));
  vm.runInContext(`let capture=null,captureStarting=false,captureGeneration=0,transcribing=false,nativeRecording=null,epoch=0;
    const ready={transcribe:true}; ${stop} ${recording}`, sandbox);
  return { $, sandbox, pending, streams, contexts, events, requests, click: () => $('recordToggle').click(),
    stop: () => vm.runInContext('stopCapture()', sandbox) };
}

test('rapid Start taps open only one microphone and Stop releases it', async () => {
  const h = harness(); const first = h.click(); await h.click();
  assert.equal(h.pending.length, 1);
  h.pending.shift()(); await first; h.stop();
  assert.equal(h.streams.filter(track => !track.stopped).length, 0);
  assert.equal(h.contexts[0].closed, true);
});
test('permission resolving after cancellation releases the late microphone', async () => {
  const h = harness(); const first = h.click(); h.stop();
  h.pending.shift()(); await first;
  assert.equal(h.streams[0].stopped, true); assert.equal(h.contexts.length, 0);
});
for (const rate of [44100, 48000]) test(`automatic cutoff produces exactly 60 seconds at ${rate}Hz`, async () => {
  const h = harness(rate); const first = h.click(); h.pending.shift()(); await first;
  for (let count = 0; count < Math.ceil(rate * 60 / 4096); count++) {
    h.contexts[0].processor.onaudioprocess({ inputBuffer: { getChannelData: () => new Float32Array(4096) } });
  }
  await Promise.resolve();
  assert.equal(h.requests.length, 1);
  const wav = h.requests[0].body.get('audio');
  assert.equal(wav.size, 44 + 16000 * 60 * 2);
  assert.equal(h.streams[0].stopped, true);
});
test('native APK starts no browser microphone; cancellation permits retry', async () => {
  const h = harness(); h.sandbox.window.LFNativeCloudRecording = true;
  await h.click(); assert.equal(h.pending.length, 0);
  assert.match(h.sandbox.window.location.href, /^linguafusion-record:\/\/capture\?id=/);
  await h.events['lf-native-recording']({ detail: { id: 'wrong-id', kind: 'cancel' } });
  await h.click(); assert.equal(h.requests.length, 0);
  await h.events['lf-native-recording']({ detail: { id: 'test-request', kind: 'cancel' } });
  assert.equal(h.$('speechStatus').textContent, 'Recording cancelled.');
  await h.click(); assert.match(h.$('speechStatus').textContent, /phone recording dialog/);
});
test('native result uploads WAV with consent and rejects stale callbacks', async () => {
  const h = harness(); h.sandbox.window.LFNativeCloudRecording = true;
  await h.click();
  const data = Buffer.from(buildWav([new Float32Array(16000)],16000)).toString('base64');
  await h.events['lf-native-recording']({ detail: { id: 'test-request', kind: 'audio', data } });
  assert.equal(h.requests.length, 1);
  assert.equal(h.requests[0].body.get('paid_consent'), 'true');
  await h.events['lf-native-recording']({ detail: { id: 'test-request', kind: 'audio', data } });
  assert.equal(h.requests.length, 1);
});
