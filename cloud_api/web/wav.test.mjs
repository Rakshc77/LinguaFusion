import test from 'node:test';
import assert from 'node:assert/strict';
import { buildWav, describeWav, encodeWav, resample, toMono, MAX_SECONDS, TARGET_SAMPLE_RATE } from './wav.mjs';

function tone(seconds, rate, frequency = 440) {
  const samples = new Float32Array(Math.round(seconds * rate));
  for (let i = 0; i < samples.length; i++) samples[i] = Math.sin(2 * Math.PI * frequency * i / rate);
  return samples;
}

test('the encoded header is exactly what the adapter validates', () => {
  const wav = encodeWav(tone(1, TARGET_SAMPLE_RATE), TARGET_SAMPLE_RATE);
  const header = describeWav(wav);
  assert.equal(header.riff, 'RIFF');
  assert.equal(header.wave, 'WAVE');
  assert.equal(header.format, 1, 'must be uncompressed PCM');
  assert.equal(header.channels, 1, 'the adapter accepts mono only');
  assert.equal(header.bitsPerSample, 16, 'the adapter requires 16-bit samples');
  assert.equal(header.sampleRate, TARGET_SAMPLE_RATE);
  // The adapter checks that the data length matches the frame count exactly.
  assert.equal(header.dataBytes, TARGET_SAMPLE_RATE * 2);
  assert.equal(header.totalBytes, 44 + header.dataBytes);
});

test('a browser rate is resampled into the accepted range', () => {
  // 48000 Hz is what most laptops actually capture at.
  const wav = buildWav([tone(2, 48000)], 48000);
  const header = describeWav(wav);
  assert.equal(header.sampleRate, TARGET_SAMPLE_RATE);
  assert.equal(header.dataBytes, 2 * TARGET_SAMPLE_RATE * 2, 'two seconds of 16-bit mono');
  assert.ok(header.sampleRate >= 8000 && header.sampleRate <= 48000);
});

test('stereo input is mixed down rather than truncated', () => {
  const left = Float32Array.from([1, 1, 1, 1]);
  const right = Float32Array.from([-1, -1, -1, -1]);
  assert.deepEqual(Array.from(toMono([left, right])), [0, 0, 0, 0]);
  assert.equal(describeWav(buildWav([left, right], 16000)).channels, 1);
});

test('samples beyond full scale are clamped, not wrapped', () => {
  // Wrapping would turn a loud passage into a burst of noise.
  const wav = encodeWav(Float32Array.from([2, -2, 0]), 16000);
  const view = new DataView(wav.buffer);
  assert.equal(view.getInt16(44, true), 32767);
  assert.equal(view.getInt16(46, true), -32767);
  assert.equal(view.getInt16(48, true), 0);
});

test('empty and over-long recordings are refused before upload', () => {
  assert.throws(() => encodeWav(new Float32Array(0), 16000), /no audio/);
  const tooLong = new Float32Array((MAX_SECONDS + 1) * 16000);
  assert.throws(() => encodeWav(tooLong, 16000), /60 seconds/);
});

test('a rate outside the accepted range is refused', () => {
  assert.throws(() => encodeWav(tone(0.1, 4000), 4000), /between 8000 and 48000/);
  assert.throws(() => encodeWav(tone(0.1, 96000), 96000), /between 8000 and 48000/);
});

test('a full-length recording stays inside the upload limit', () => {
  const wav = buildWav([tone(MAX_SECONDS, 48000)], 48000);
  assert.ok(wav.length <= 4_000_000, `60s produced ${wav.length} bytes`);
  assert.equal(describeWav(wav).dataBytes, MAX_SECONDS * TARGET_SAMPLE_RATE * 2);
});

test('resampling preserves duration and rejects nonsense rates', () => {
  assert.equal(resample(tone(1, 44100), 44100, 16000).length, 16000);
  assert.equal(resample(tone(1, 16000), 16000, 16000).length, 16000);
  assert.throws(() => resample(tone(1, 16000), 0, 16000), /positive/);
});
