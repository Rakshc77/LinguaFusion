const LANGUAGES = new Set(['en', 'de', 'ar', 'es', 'fr', 'hi', 'or']);
const RATES = new Set([0.75, 1, 1.25]);
export const MAX_READ_ALOUD_CHARACTERS = 12000;

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

  function report(id, state, message) {
    if (state !== 'speaking' && active?.id === id) active = null;
    onState({ id, state, message });
  }

  function handleNativeMessage(event) {
    let value;
    try { value = JSON.parse(typeof event?.data === 'string' ? event.data : ''); }
    catch { return; }
    if (!value || value.id !== active?.id || !['speaking', 'done', 'stopped', 'error'].includes(value.state)) return;
    report(value.id, value.state, String(value.message || ''));
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
    const prepared = prepareReadAloudRequest(request);
    if (prepared.error) {
      onState({ id: String(request?.id || ''), state: 'error', message: prepared.error });
      return false;
    }
    if (active?.id === prepared.id) { stop(); return true; }
    stop();
    active = prepared;

    if (native && typeof native.postMessage === 'function') {
      try {
        native.postMessage(JSON.stringify({ type: 'speak', ...prepared }));
        report(prepared.id, 'speaking', 'Speaking with this phone’s voice…');
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

    const utterance = new Utterance(prepared.text);
    utterance.lang = prepared.language;
    utterance.rate = prepared.rate;
    const voice = matchingVoice(typeof synthesis.getVoices === 'function' ? synthesis.getVoices() : [], prepared.language);
    if (voice) utterance.voice = voice;
    utterance.onstart = () => {
      if (active?.id === prepared.id) report(prepared.id, 'speaking', 'Speaking with this device’s voice…');
    };
    utterance.onend = () => {
      if (active?.id === prepared.id) report(prepared.id, 'done', 'Finished.');
    };
    utterance.onerror = () => {
      if (active?.id === prepared.id) report(prepared.id, 'error', 'This device has no usable voice for that language.');
    };
    active.utterance = utterance;
    synthesis.cancel();
    synthesis.speak(utterance);
    report(prepared.id, 'speaking', 'Starting this device’s voice…');
    return true;
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
      return Boolean((native && typeof native.postMessage === 'function')
        || (synthesis && typeof synthesis.speak === 'function' && typeof Utterance === 'function'));
    },
  };
}
