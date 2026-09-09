/* The offline app.
 *
 * Talks to Java through window.LinguaFusionOffline, which only exists for this
 * page -- it ships inside the APK. The cloud page deliberately has no such
 * interface.
 *
 * Java is asynchronous but a JavascriptInterface method cannot return a
 * promise, so slow calls take a request id and Java calls window.LF.resolve()
 * back with the answer. That plumbing is wrapped in ask() so the rest of this
 * file reads as ordinary async code.
 */
'use strict';

const native = window.LinguaFusionOffline;
const $ = (id) => document.getElementById(id);

/* ---------- the request/response bridge ---------- */

const pending = new Map();
let nextRequest = 0;

window.LF = {
  resolve(id, json) {
    let payload;
    try { payload = JSON.parse(json); } catch { payload = { error: 'The phone sent back something unreadable.' }; }
    // Progress updates arrive on "<id>:progress" and do not settle anything.
    if (id.endsWith(':progress')) {
      const handler = pending.get(id.slice(0, -':progress'.length));
      if (handler && handler.onProgress) handler.onProgress(payload);
      return;
    }
    const handler = pending.get(id);
    if (!handler) return;
    pending.delete(id);
    handler.resolve(payload);
  },
};

function ask(method, onProgress, ...args) {
  return new Promise((resolve) => {
    const id = 'r' + (++nextRequest);
    pending.set(id, { resolve, onProgress });
    try {
      native[method](id, ...args);
    } catch (failure) {
      pending.delete(id);
      resolve({ error: String(failure && failure.message ? failure.message : failure) });
    }
  });
}

/* ---------- state ---------- */

let state = { languages: [], models: [], installedPacks: new Set() };
let recording = false;
let busy = false;

/* ---------- appearance ---------- */

function applyMode(mode) {
  document.documentElement.dataset.mode = mode;
  $('modeToggle').textContent = mode === 'dark' ? '◐ Night' : '◐ Day';
  try { localStorage.setItem('offline-mode', mode); } catch { /* private mode */ }
}

function storedMode() {
  try {
    const saved = localStorage.getItem('offline-mode');
    if (saved === 'dark' || saved === 'light') return saved;
  } catch { /* private mode */ }
  return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/* ---------- helpers ---------- */

function fill(select, entries, { includeAuto = false, selected = '' } = {}) {
  select.textContent = '';
  if (includeAuto) select.add(new Option('Detect automatically', 'auto'));
  for (const language of entries) {
    select.add(new Option(`${language.name} — ${language.nativeName}`, language.code));
  }
  if (selected) select.value = selected;
}

function say(element, message) {
  $(element).textContent = message || '';
}

function copy(text, status) {
  if (!text) { say(status, 'There is nothing to copy yet.'); return; }
  // A WebView over file:// has no clipboard API, so fall back to the old way.
  navigator.clipboard?.writeText(text).then(
    () => say(status, 'Copied.'),
    () => say(status, 'This phone would not let the app copy that.'));
}

function updatePivotWarning() {
  const from = $('fromLang').value;
  const to = $('toLang').value;
  const pivots = from !== 'auto' && from !== 'en' && to !== 'en' && from !== to;
  $('pivotWarn').hidden = !(pivots && $('alsoTranslate').checked);
}

/* ---------- Speak ---------- */

async function toggleRecording() {
  if (busy) return;
  if (!recording) {
    const failure = native.startRecording();
    if (failure) { say('speakStatus', failure); return; }
    recording = true;
    $('record').textContent = 'Stop and transcribe';
    say('speakStatus', 'Recording… speak now.');
    return;
  }

  recording = false;
  busy = true;
  $('record').disabled = true;
  $('record').textContent = 'Working…';
  say('speakStatus', 'Transcribing on this phone. This can take a while.');
  $('transcript').textContent = '';
  $('translationWrap').hidden = true;

  const result = await ask('stopAndProcess', null,
    $('fromLang').value, $('toLang').value, $('alsoTranslate').checked);

  busy = false;
  $('record').disabled = false;
  $('record').textContent = 'Start recording';

  if (result.error) { say('speakStatus', result.error); return; }

  $('transcript').textContent = result.transcript || '';
  const detected = result.detected
    ? ` Heard ${nameOf(result.detected) || result.detected}.` : '';
  say('speakStatus', `Done — ${result.seconds ?? '?'} seconds.${detected}`);

  if (result.translation) {
    $('translationWrap').hidden = false;
    $('translation').textContent = result.translation;
  } else if (result.translationError) {
    say('speakStatus', `${result.error || 'Transcribed.'} ${result.translationError}`);
  }
}

function nameOf(code) {
  const found = state.languages.find((language) => language.code === code);
  return found ? found.name : '';
}

/* ---------- Translate ---------- */

async function translateTyped() {
  const text = $('sourceText').value.trim();
  if (!text) { say('translateStatus', 'Type something to translate.'); return; }
  $('translate').disabled = true;
  say('translateStatus', 'Translating on this phone…');
  const result = await ask('translateText', null, text, $('textFrom').value, $('textTo').value);
  $('translate').disabled = false;
  if (result.error) { say('translateStatus', result.error); $('textResult').textContent = ''; return; }
  $('textResult').textContent = result.translation || '';
  say('translateStatus', result.pivoted
    ? 'Done. This pair goes through English, so it is rougher than usual.'
    : 'Done.');
}

/* ---------- Read ---------- */

async function readPicture() {
  $('readPicture').disabled = true;
  say('readStatus', 'Choose a picture…');
  const result = await ask('readPicture', null);
  $('readPicture').disabled = false;
  if (result.cancelled) { say('readStatus', ''); return; }
  if (result.error) { say('readStatus', result.error); $('readResult').textContent = ''; return; }
  $('readResult').textContent = result.text || '';
  say('readStatus', 'Read on this phone.');
}

function sendReadToTranslate() {
  const text = $('readResult').textContent;
  if (!text) { say('readStatus', 'Read a picture first.'); return; }
  $('sourceText').value = text;
  show('viewTranslate');
  say('translateStatus', 'Brought over from the picture. Choose the languages and translate.');
}

/* ---------- Say it ---------- */

async function romanize() {
  const text = $('sayText').value.trim();
  if (!text) { say('sayStatus', 'Paste some text first.'); return; }
  $('romanize').disabled = true;
  say('sayStatus', 'Working…');
  const result = await ask('romanize', null, text, $('sayLang').value);
  $('romanize').disabled = false;
  if (result.error) { say('sayStatus', result.error); $('sayResult').textContent = ''; return; }
  $('sayResult').textContent = result.romanized || '';
  say('sayStatus', 'Done.');
}

/* ---------- Storage ---------- */

function renderModels() {
  const container = $('models');
  container.textContent = '';
  for (const model of state.models) {
    const card = document.createElement('div');
    card.className = 'model' + (model.id === state.chosenModel ? ' chosen' : '');

    const title = document.createElement('p');
    title.style.margin = '0 0 4px';
    title.innerHTML = '';
    const name = document.createElement('strong');
    name.textContent = model.name;
    title.append(name, ` — ${model.megabytes} MB`);
    if (model.id === state.recommendedModel) {
      const tag = document.createElement('span');
      tag.className = 'tag';
      tag.textContent = '  recommended';
      title.append(tag);
    }
    card.append(title);

    const good = document.createElement('p');
    good.className = 'hint';
    good.style.margin = '0';
    good.textContent = model.bestFor;
    const bad = document.createElement('p');
    bad.className = 'hint';
    bad.style.margin = '2px 0 0';
    bad.textContent = model.tradeOff;
    card.append(good, bad);

    const bar = document.createElement('div');
    bar.className = 'bar';
    bar.hidden = true;
    const fillBar = document.createElement('i');
    bar.append(fillBar);
    card.append(bar);

    const row = document.createElement('div');
    row.className = 'row';
    row.style.marginTop = '12px';

    if (model.installed) {
      if (model.id !== state.chosenModel) {
        const use = document.createElement('button');
        use.className = 'slim';
        use.textContent = 'Use this one';
        use.onclick = () => { native.chooseModel(model.id); refresh(); };
        row.append(use);
      } else {
        const tag = document.createElement('span');
        tag.className = 'tag';
        tag.textContent = 'In use';
        row.append(tag);
      }
      const remove = document.createElement('button');
      remove.className = 'slim secondary';
      remove.textContent = 'Remove';
      remove.onclick = async () => {
        remove.disabled = true;
        const result = await ask('removeModel', null, model.id);
        say('storageStatus', result.error || `${model.name} removed.`);
        refresh();
      };
      row.append(remove);
    } else {
      const get = document.createElement('button');
      get.className = 'slim';
      const resuming = model.partialBytes > 0;
      get.textContent = resuming
        ? `Resume (${Math.round(model.partialBytes / 1e6)} of ${model.megabytes} MB)`
        : `Download ${model.megabytes} MB`;
      get.onclick = async () => {
        get.disabled = true;
        bar.hidden = false;
        say('storageStatus', `Downloading ${model.name}. You can leave this screen.`);
        const result = await ask('downloadModel', (progress) => {
          const share = progress.total ? (progress.done / progress.total) * 100 : 0;
          fillBar.style.width = `${share.toFixed(1)}%`;
        }, model.id);
        bar.hidden = true;
        say('storageStatus', result.error || `${model.name} is ready.`);
        refresh();
      };
      row.append(get);
    }
    card.append(row);
    container.append(card);
  }
}

function renderPacks() {
  const container = $('packs');
  container.textContent = '';
  for (const language of state.languages) {
    const installed = state.installedPacks.has(language.code);
    const card = document.createElement('div');
    card.className = 'model';

    const title = document.createElement('p');
    title.style.margin = '0';
    const name = document.createElement('strong');
    name.textContent = language.name;
    title.append(name, ` — ${language.nativeName}`);
    card.append(title);

    const status = document.createElement('p');
    status.className = 'hint';
    status.style.margin = '2px 0 0';
    status.textContent = installed ? 'Downloaded.' : 'Not downloaded.';
    card.append(status);

    const action = document.createElement('button');
    action.className = 'slim' + (installed ? ' secondary' : '');
    action.style.marginTop = '10px';
    if (installed && language.code === 'en') {
      action.disabled = true;
      action.textContent = 'Required';
    } else if (installed) {
      action.textContent = 'Remove';
      action.onclick = async () => {
        action.disabled = true;
        const result = await ask('removeTranslationLanguage', null, language.code);
        say('storageStatus', result.error || `${language.name} removed.`);
        refresh();
      };
    } else {
      action.textContent = 'Download';
      action.onclick = async () => {
        action.disabled = true;
        say('storageStatus', `Downloading ${language.name}…`);
        const result = await ask('downloadTranslationLanguage', null, language.code, false);
        say('storageStatus', result.error || `${language.name} is ready.`);
        refresh();
      };
    }
    card.append(action);
    container.append(card);
  }
}

/* ---------- updates ---------- */

async function checkForUpdate() {
  $('checkUpdate').disabled = true;
  say('updateStatus', 'Checking…');
  const result = await ask('checkForUpdate', null);
  $('checkUpdate').disabled = false;
  if (result.available) {
    // The app puts its own dialog up; this line is for anyone who dismisses it.
    say('updateStatus', `Version ${result.versionName} is available (${result.megabytes} MB).`);
  } else {
    // A failed check is indistinguishable from being current, so say the
    // thing that is true either way rather than claiming to be up to date.
    say('updateStatus', 'Nothing newer was offered. If you are offline, try again on a connection.');
  }
}

/* ---------- wiring ---------- */

async function refresh() {
  const described = JSON.parse(native.describe());
  state = { ...state, ...described };
  state.installedPacks = new Set(state.installedPacks || []);

  fill($('fromLang'), state.languages, { includeAuto: true, selected: state.sourceLanguage });
  fill($('toLang'), state.languages, { selected: state.targetLanguage });
  fill($('textFrom'), state.languages, { selected: state.sourceLanguage === 'auto' ? 'en' : state.sourceLanguage });
  fill($('textTo'), state.languages, { selected: state.targetLanguage });

  if (!state.transcriptionSupported) {
    $('record').disabled = true;
    say('speakStatus', 'This phone cannot run offline transcription. Translation still works.');
  }

  fill($('sayLang'), state.romanizeLanguages || []);
  if (!state.romanizeSupported) {
    $('sayLimits').hidden = false;
    $('romanize').disabled = true;
  }
  // Name the languages that can actually be read, rather than leaving someone
  // to photograph Arabic and get an empty box.
  const readable = (state.readableLanguages || [])
    .map((code) => nameOf(code)).filter(Boolean);
  if (readable.length) {
    $('readLimits').textContent =
      `Offline this reads Latin letters only, so ${readable.join(', ')}. `
      + 'Arabic script needs the cloud.';
  }
  renderModels();
  updatePivotWarning();

  const packs = await ask('listTranslationLanguages', null);
  state.installedPacks = new Set(packs.installed || []);
  renderPacks();
}

function show(view) {
  for (const section of ['viewSpeak', 'viewTranslate', 'viewRead', 'viewSay', 'viewStorage']) {
    $(section).hidden = section !== view;
  }
  for (const button of document.querySelectorAll('nav button')) {
    button.setAttribute('aria-current', String(button.dataset.view === view));
  }
}

function start() {
  applyMode(storedMode());
  $('modeToggle').onclick = () =>
    applyMode(document.documentElement.dataset.mode === 'dark' ? 'light' : 'dark');
  $('leave').onclick = () => native.leaveOfflineMode();

  for (const button of document.querySelectorAll('nav button')) {
    button.onclick = () => show(button.dataset.view);
  }

  $('record').onclick = toggleRecording;
  $('translate').onclick = translateTyped;
  $('alsoTranslate').onchange = updatePivotWarning;
  for (const id of ['fromLang', 'toLang']) {
    $(id).onchange = () => {
      native.rememberLanguages($('fromLang').value, $('toLang').value);
      updatePivotWarning();
    };
  }
  $('copyTranscript').onclick = () => copy($('transcript').textContent, 'speakStatus');
  $('copyTranslation').onclick = () => copy($('translation').textContent, 'speakStatus');
  $('copyText').onclick = () => copy($('textResult').textContent, 'translateStatus');
  $('readPicture').onclick = readPicture;
  $('sendReadToTranslate').onclick = sendReadToTranslate;
  $('copyRead').onclick = () => copy($('readResult').textContent, 'readStatus');
  $('romanize').onclick = romanize;
  $('copySay').onclick = () => copy($('sayResult').textContent, 'sayStatus');
  $('checkUpdate').onclick = checkForUpdate;

  refresh();
}

if (!native) {
  document.body.innerHTML =
    '<main><h2>Offline mode is unavailable</h2>' +
    '<p>This page has to run inside the LinguaFusion app.</p></main>';
} else {
  start();
}
