import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { buildWav, segmentPcm16, toMono, toPcm16, MAX_RECORDING_SECONDS,
         MAX_SECONDS, SILENCE_SECONDS, TARGET_SAMPLE_RATE, VOICE_RMS_THRESHOLD } from './wav.mjs';

// Execute the shipped recording handlers, not a duplicate implementation.
const source = readFileSync(new URL('./pilot.mjs', import.meta.url), 'utf8');
function harness(rate = 48000, native = false) {
  const elements = new Map();
  const pending = [];
  const streams = [];
  const contexts = [];
  const events = {};
  const requests = [];
  const $ = id => {
    if (!elements.has(id)) elements.set(id, {
      checked: true, textContent: '', hidden: true, value: '',
      style: { setProperty() {} }, closest() { return this; },
      classList: { add() {}, remove() {}, toggle() {} },
      setAttribute() {},
      addEventListener(type, fn) { this[type] = fn; },
    });
    return elements.get(id);
  };
  const node = () => ({ connect() {}, disconnect() {} });
  class AudioContext {
    constructor() { this.sampleRate = rate; this.state = 'running'; contexts.push(this); }
    createMediaStreamSource() { return node(); }
    createScriptProcessor() { return this.processor = node(); }
    createGain() { return { ...node(), gain: {} }; }
    async decodeAudioData() {
      const samples = new Float32Array(44100).fill(0.1);
      return { duration:1, numberOfChannels:2, sampleRate:44100, getChannelData:() => samples };
    }
    async close() { this.closed = true; }
  }
  const nativeWav = buildWav([new Float32Array(16000).fill(0.1)],16000);
  const nativeAudio = native ? { onmessage:null, postMessage(value) {
    const request = JSON.parse(value);
    const packet = nativeWav.subarray(request.offset);
    this.onmessage?.({ data:JSON.stringify({ id:request.id, part:request.part, offset:request.offset,
      data:Buffer.from(packet).toString('base64'), nextOffset:nativeWav.length, done:true }) });
  } } : undefined;
  const sandbox = vm.createContext({ $, window: { AudioContext, location: {}, LinguaFusionNativeAudio:nativeAudio,
      addEventListener: (type, fn) => events[type] = fn },
    document: { addEventListener() {} }, navigator: { mediaDevices: { getUserMedia() {
      return new Promise(resolve => pending.push(() => {
        const track = { stopped: false, muted:false, listeners:{}, stop() { this.stopped = true; },
          addEventListener(type, fn) { this.listeners[type] = fn; } };
        streams.push(track); resolve({ getTracks: () => [track] });
      }));
    } } }, Float32Array, Uint8Array, Blob, FormData, setTimeout, atob,
    crypto: { randomUUID: () => 'test-request' }, buildWav, segmentPcm16, toMono, toPcm16,
    MAX_RECORDING_SECONDS, MAX_SECONDS, SILENCE_SECONDS, TARGET_SAMPLE_RATE, VOICE_RMS_THRESHOLD,
    readAloud: { stop() {} },
    api: { async request(path, body) { requests.push({ path, body }); return { text: 'Test' }; } },
    showSpending() {}, revealResult() {}, rememberResult() {}, setProcessing() {}, haptic() {}, formatClock:value => String(value),
    microphoneProblem: error => error.name, isIosDevice: () => false,
    isIosStandalone: () => false, clearTimeout });
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
test('Cancel recording clears microphone feedback and never uploads audio', async () => {
  const h = harness(); const first = h.click(); h.pending.shift()(); await first;
  assert.equal(h.$('recordingFeedback').hidden, false);
  h.contexts[0].processor.onaudioprocess({ inputBuffer: { getChannelData: () => new Float32Array(4096).fill(0.1) } });
  assert.ok(h.$('microphoneLevel').value > 0);
  h.$('cancelRecording').click();
  assert.equal(h.streams[0].stopped, true);
  assert.equal(h.contexts[0].closed, true);
  assert.equal(h.$('recordingFeedback').hidden, true);
  assert.equal(h.$('microphoneLevel').value, 0);
  assert.equal(h.requests.length, 0);
  assert.match(h.$('speechStatus').textContent, /No audio was sent/);
});
test('an ended iPhone microphone exposes retry and saved-recording recovery', async () => {
  const h = harness(); const first = h.click(); h.pending.shift()(); await first;
  h.streams[0].listeners.ended();
  assert.equal(h.streams[0].stopped, true);
  assert.equal(h.$('recordingRecovery').hidden, false);
  assert.match(h.$('speechStatus').textContent, /interrupted/);
});
test('a saved Voice Memo is decoded locally and uploaded as strict WAV', async () => {
  const h = harness();
  h.$('speechAudioFile').files = [{ name:'memo.m4a', size:1024, arrayBuffer:async () => new ArrayBuffer(8) }];
  await h.$('speechAudioFile').change();
  assert.equal(h.requests.length, 1);
  assert.equal(h.requests[0].path, '/api/transcribe');
  assert.equal(h.requests[0].body.get('audio').type, 'audio/wav');
  assert.equal(h.contexts[0].closed, true);
  assert.equal(h.$('speechAudioFile').value, '');
});
for (const rate of [44100, 48000]) test(`automatic cutoff produces four safe parts from twenty minutes at ${rate}Hz`, async () => {
  const h = harness(rate); const first = h.click(); h.pending.shift()(); await first;
  for (let count = 0; count < Math.ceil(rate * MAX_RECORDING_SECONDS / 4096); count++) {
    h.contexts[0].processor.onaudioprocess({ inputBuffer: { getChannelData: () => new Float32Array(4096).fill(0.1) } });
  }
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(h.requests.length, 4);
  const fullPartBytes = 44 + 16000 * MAX_SECONDS * 2;
  for (const request of h.requests.slice(0, 3)) assert.equal(request.body.get('audio').size, fullPartBytes);
  assert.ok(h.requests[3].body.get('audio').size > fullPartBytes * 0.99);
  assert.ok(h.requests[3].body.get('audio').size <= fullPartBytes);
  assert.equal(h.streams[0].stopped, true);
});
test('one continuous minute without detected speech stops and sends what was captured', async () => {
  const h = harness(48000); const first = h.click(); h.pending.shift()(); await first;
  for (let count = 0; count < Math.ceil(48000 * SILENCE_SECONDS / 4096); count++) {
    h.contexts[0].processor.onaudioprocess({ inputBuffer: { getChannelData: () => new Float32Array(4096) } });
  }
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(h.requests.length, 1);
  assert.equal(h.streams[0].stopped, true);
  assert.match(h.$('speechStatus').textContent, /Done|No speech/);
});
test('native APK starts no browser microphone; cancellation permits retry', async () => {
  const h = harness(48000, true); h.sandbox.window.LFNativeCloudRecording = true;
  await h.click(); assert.equal(h.pending.length, 0);
  assert.match(h.sandbox.window.location.href, /^linguafusion-record:\/\/capture\?id=/);
  await h.click(); assert.match(h.sandbox.window.location.href, /^linguafusion-record:\/\/stop\?id=/);
  await h.events['lf-native-recording']({ detail: { id: 'wrong-id', kind: 'cancel' } });
  await h.events['lf-native-recording']({ detail: { id: 'test-request', kind: 'cancel' } });
  assert.equal(h.$('speechStatus').textContent, 'Recording cancelled.');
  await h.click(); assert.match(h.$('speechStatus').textContent, /silence for one minute/);
});
test('native result streams through the origin-scoped bridge and rejects stale callbacks', async () => {
  const h = harness(48000, true); h.sandbox.window.LFNativeCloudRecording = true;
  await h.click();
  await h.events['lf-native-recording']({ detail: { id: 'test-request', kind: 'ready', total:1 } });
  assert.equal(h.requests.length, 1);
  assert.equal(h.requests[0].body.get('paid_consent'), 'true');
  await h.events['lf-native-recording']({ detail: { id: 'test-request', kind: 'ready', total:1 } });
  assert.equal(h.requests.length, 1);
});
