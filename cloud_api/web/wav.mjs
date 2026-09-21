// Turn captured audio into the exact format the backend accepts.
//
// MediaRecorder produces WebM/Opus, which the transcription adapter rejects.
// It requires a complete mono 16-bit PCM WAV, 8000-48000 Hz, at most five
// minutes and 10 MB. A recording session may be longer, so the client keeps
// compact 16 kHz PCM in memory and splits it into independently validated
// five-minute uploads before anything leaves the device.

export const TARGET_SAMPLE_RATE = 16000;
export const MAX_RECORDING_SECONDS = 1200;
export const SILENCE_SECONDS = 60;
// Deliberately conservative: failing to auto-stop in a noisy room is safer
// than cutting off a quiet speaker.
export const VOICE_RMS_THRESHOLD = 0.008;
export const MAX_SECONDS = 300;
export const MAX_BYTES = 10_000_000;

/**
 * Resample by linear interpolation. Good enough for speech, and far better
 * than dropping samples, which introduces aliasing that hurts recognition.
 */
export function resample(samples, fromRate, toRate) {
  if (!(fromRate > 0) || !(toRate > 0)) throw new Error('Sample rates must be positive.');
  if (fromRate === toRate) return Float32Array.from(samples);
  const ratio = fromRate / toRate;
  const length = Math.floor(samples.length / ratio);
  const output = new Float32Array(length);
  for (let i = 0; i < length; i++) {
    const position = i * ratio;
    const left = Math.floor(position);
    const right = Math.min(left + 1, samples.length - 1);
    const weight = position - left;
    output[i] = samples[left] * (1 - weight) + samples[right] * weight;
  }
  return output;
}

/** Average channels down to mono; the adapter refuses anything else. */
export function toMono(channels) {
  if (!channels.length) return new Float32Array(0);
  if (channels.length === 1) return Float32Array.from(channels[0]);
  const length = Math.min(...channels.map(c => c.length));
  const output = new Float32Array(length);
  for (let i = 0; i < length; i++) {
    let sum = 0;
    for (const channel of channels) sum += channel[i];
    output[i] = sum / channels.length;
  }
  return output;
}

function validateRate(sampleRate) {
  if (!Number.isFinite(sampleRate) || sampleRate < 8000 || sampleRate > 48000) {
    throw new Error('Sample rate must be between 8000 and 48000 Hz.');
  }
}

/** Convert captured floats to compact 16-bit PCM at the target rate. */
export function toPcm16(samples, sourceRate, targetRate = TARGET_SAMPLE_RATE) {
  validateRate(sourceRate);
  validateRate(targetRate);
  const converted = resample(samples, sourceRate, targetRate);
  const pcm = new Int16Array(converted.length);
  for (let i = 0; i < converted.length; i++) {
    const sample = Math.max(-1, Math.min(1, converted[i]));
    pcm[i] = Math.round(sample * 32767);
  }
  return pcm;
}

/** Encode mono 16-bit PCM as a complete WAV file. */
export function encodePcm16(pcm, sampleRate) {
  validateRate(sampleRate);
  const frames = pcm.length;
  if (frames === 0) throw new Error('There is no audio to send.');
  if (frames > MAX_SECONDS * sampleRate) throw new Error(`Uploads are limited to ${MAX_SECONDS} seconds each.`);

  const dataBytes = frames * 2;
  const buffer = new ArrayBuffer(44 + dataBytes);
  const view = new DataView(buffer);
  const ascii = (offset, text) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };

  ascii(0, 'RIFF');
  view.setUint32(4, 36 + dataBytes, true);
  ascii(8, 'WAVE');
  ascii(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  ascii(36, 'data');
  view.setUint32(40, dataBytes, true);
  for (let i = 0; i < frames; i++) view.setInt16(44 + i * 2, pcm[i], true);

  const bytes = new Uint8Array(buffer);
  if (bytes.length > MAX_BYTES) throw new Error('That recording part is too large to send.');
  return bytes;
}

/** Encode mono float samples as a complete 16-bit PCM WAV file. */
export function encodeWav(samples, sampleRate) {
  validateRate(sampleRate);
  const frames = samples.length;
  if (frames === 0) throw new Error('There is no audio to send.');
  if (frames > MAX_SECONDS * sampleRate) throw new Error(`Recordings are limited to ${MAX_SECONDS} seconds.`);
  return encodePcm16(toPcm16(samples, sampleRate, sampleRate), sampleRate);
}

/** Full pipeline: captured channels at any rate -> a WAV the backend accepts. */
export function buildWav(channels, sourceRate, targetRate = TARGET_SAMPLE_RATE) {
  return encodeWav(resample(toMono(channels), sourceRate, targetRate), targetRate);
}

/** Split a complete session into provider-safe WAV parts without one huge WAV. */
export function segmentPcm16(chunks, sampleRate = TARGET_SAMPLE_RATE) {
  validateRate(sampleRate);
  const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  if (!total) throw new Error('There is no audio to send.');
  if (total > MAX_RECORDING_SECONDS * sampleRate) {
    throw new Error(`Recording sessions are limited to ${MAX_RECORDING_SECONDS} seconds.`);
  }
  const partFrames = MAX_SECONDS * sampleRate;
  const parts = [];
  let chunkIndex = 0;
  let chunkOffset = 0;
  let remaining = total;
  while (remaining > 0) {
    const pcm = new Int16Array(Math.min(partFrames, remaining));
    let offset = 0;
    while (offset < pcm.length) {
      const chunk = chunks[chunkIndex];
      const count = Math.min(pcm.length - offset, chunk.length - chunkOffset);
      pcm.set(chunk.subarray(chunkOffset, chunkOffset + count), offset);
      offset += count;
      chunkOffset += count;
      if (chunkOffset === chunk.length) { chunkIndex++; chunkOffset = 0; }
    }
    parts.push(encodePcm16(pcm, sampleRate));
    remaining -= pcm.length;
  }
  return parts;
}

/** Read the header back, so tests and callers can assert what was produced. */
export function describeWav(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const text = (offset, length) => String.fromCharCode(
    ...Array.from({ length }, (_, i) => view.getUint8(offset + i)));
  return {
    riff: text(0, 4),
    wave: text(8, 4),
    format: view.getUint16(20, true),
    channels: view.getUint16(22, true),
    sampleRate: view.getUint32(24, true),
    bitsPerSample: view.getUint16(34, true),
    dataBytes: view.getUint32(40, true),
    totalBytes: bytes.length,
  };
}
