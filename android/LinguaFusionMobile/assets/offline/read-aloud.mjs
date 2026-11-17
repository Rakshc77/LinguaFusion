const LANGUAGES = new Set(['en', 'de', 'ar', 'es', 'fr', 'hi', 'or']);
const RATES = new Set([0.75, 1, 1.25]);
export const MAX_READ_ALOUD_CHARACTERS = 120000;

// Keep every character, including surrogate pairs, when splitting long results.
export function splitReadAloudText(text, maximum = 1000) {
  if (!Number.isInteger(maximum) || maximum < 2) throw new RangeError('Invalid speech chunk size.');
  const chunks = [];
  for (let start = 0; start < text.length;) {
    let end = Math.min(start + maximum, text.length);
    if (end < text.length) {
      for (let at = end; at > start + maximum / 2; at--) {
        if (/\s/u.test(text[at - 1])) { end = at; break; }
      }
      if (/[\uD800-\uDBFF]/u.test(text[end - 1]) && /[\uDC00-\uDFFF]/u.test(text[end])) end--;
    }
    chunks.push(text.slice(start, end));
    start = end;
  }
  return chunks;
}

export function normaliseReadLanguage(value) {
  const language = String(value || '').trim().toLowerCase().split(/[-_]/, 1)[0];
  return LANGUAGES.has(language) ? language : '';
}

export function prepareReadAloudRequest(request) {
  const id = String(request?.id || '');
  const text = String(request?.text || '').trim();
  const language = normaliseReadLanguage(request?.language);
  const rate = Number(request?.rate);
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(id)) return { error: 'This result cannot be read aloud.' };
  if (!text) return { error: 'There is nothing to read aloud yet.' };
  if (text.length > MAX_READ_ALOUD_CHARACTERS) {
    return { error: `Read aloud supports up to ${MAX_READ_ALOUD_CHARACTERS.toLocaleString()} characters at a time.` };
  }
  if (!language) return { error: 'Choose the language this text is written in.' };
  if (!RATES.has(rate)) return { error: 'Choose a supported reading speed.' };
  return { id, text, language, rate };
}

function matchingVoice(voices, language) {
  const matches = voices.filter(voice => normaliseReadLanguage(voice.lang) === language);
  return matches.find(voice => voice.localService === true) || matches.find(voice => voice.default) || matches[0] || null;
}

/**
 * One app-wide speech controller. The hosted Android app supplies a narrowly
 * origin-scoped WebMessage object; ordinary browsers use the Web Speech API.
 * No LinguaFusion API request is made by either route.
 */
export function createReadAloudController({ scope = globalThis, onState = () => {} } = {}) {
  const native = scope.LinguaFusionReadAloud;
  const synthesis = scope.speechSynthesis;
  const Utterance = scope.SpeechSynthesisUtterance;
  let active = null;
  let disposed = false;
  let generation = 0;

  function report(id, state, message) {
    if (state !== 'speaking' && active?.id === id) active = null;
    onState({ id, state, message });
  }

  function handleNativeMessage(event) {
    let value;
    try { value = JSON.parse(typeof event?.data === 'string' ? event.data : ''); }
    catch { return; }
    if (!active || !value || value.id !== active.wireId || !['speaking', 'done', 'stopped', 'error'].includes(value.state)) return;
    if (value.state === 'done') advance(active);
    else report(active.id, value.state, String(value.message || ''));
  }
  if (native && typeof native.postMessage === 'function') native.onmessage = handleNativeMessage;

  function stop({ quiet = false } = {}) {
    const previous = active;
    active = null;
    if (native && typeof native.postMessage === 'function') {
      try { native.postMessage(JSON.stringify({ type: 'stop' })); } catch { /* already unavailable */ }
    } else if (synthesis && typeof synthesis.cancel === 'function') {
      synthesis.cancel();
    }
    if (previous && !quiet) onState({ id: previous.id, state: 'stopped', message: 'Stopped.' });
  }

  function read(request) {
    if (disposed) return false;
    const prepared = prepareReadAloudRequest(request);
    if (prepared.error) {
      onState({ id: String(request?.id || ''), state: 'error', message: prepared.error });
      return false;
    }
    if (active?.id === prepared.id) { stop(); return true; }
    stop();
    active = { ...prepared, token: ++generation, index: 0,
      chunks: splitReadAloudText(prepared.text,
        native && typeof native.postMessage === 'function' ? 2000 : 1000) };

    if (native && typeof native.postMessage === 'function') {
      try {
        speakChunk(active);
        return true;
      } catch {
        active = null;
        report(prepared.id, 'error', 'This phone could not start Read Aloud.');
        return false;
      }
    }

    if (!synthesis || typeof synthesis.speak !== 'function' || typeof Utterance !== 'function') {
      active = null;
      report(prepared.id, 'error', 'Read Aloud is unavailable in this browser.');
      return false;
    }

    try { speakChunk(active); }
    catch {
      report(prepared.id, 'error', 'This device could not start Read Aloud.');
      return false;
    }
    return true;
  }

  function advance(session) {
    if (active !== session) return;
    session.index++;
    if (session.index === session.chunks.length) { report(session.id, 'done', 'Finished.'); return; }
    try { speakChunk(session); }
    catch { report(session.id, 'error', 'Read Aloud could not continue. Try again.'); }
  }

  function speakChunk(session) {
    const index = session.index;
    const message = session.chunks.length > 1
      ? `Reading section ${index + 1} of ${session.chunks.length}.`
      : "Speaking with this device's voice.";
    if (native && typeof native.postMessage === 'function') {
      // 2,000-character sections also fit the native JSON size guard even
      // when each character requires a six-character JSON escape. IDs reject
      // delayed replies from cancelled sections or restarts of the same result.
      session.wireId = `lf-${session.token}-${index}`;
      report(session.id, 'speaking', message);
      native.postMessage(JSON.stringify({ type:'speak', id:session.wireId,
        text:session.chunks[index], language:session.language, rate:session.rate }));
      return;
    }
    const utterance = new Utterance(session.chunks[index]);
    utterance.lang = session.language;
    utterance.rate = session.rate;
    const voice = matchingVoice(typeof synthesis.getVoices === 'function' ? synthesis.getVoices() : [], session.language);
    if (voice) utterance.voice = voice;
    const current = () => active === session && session.utterance === utterance;
    utterance.onstart = () => { if (current()) report(session.id, 'speaking', message); };
    utterance.onend = () => { if (current()) advance(session); };
    utterance.onerror = () => {
      if (current()) report(session.id, 'error', 'This device has no usable voice for that language.');
    };
    session.utterance = utterance;
    report(session.id, 'speaking', message);
    synthesis.speak(utterance);
  }

  function dispose() {
    if (disposed) return;
    disposed = true;
    stop({ quiet: true });
    if (native && native.onmessage === handleNativeMessage) native.onmessage = null;
  }

  return {
    read,
    stop,
    dispose,
    get activeId() { return active?.id || ''; },
    get available() {
      return !disposed && Boolean((native && typeof native.postMessage === 'function')
        || (synthesis && typeof synthesis.speak === 'function' && typeof Utterance === 'function'));
    },
  };
}
