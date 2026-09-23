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

// The same appearance module the online app uses, copied into the APK. Look,
// day/night and typeface therefore behave identically in both modes and a
// choice made in one is the choice the other starts from.
import { CLOUD_THEMES, LF_FONTS, applyFont, applyTheme, applyMode,
         applyMotion, getFont, getMode, getMotion, getTheme, initAppearance } from './themes.mjs';
import { createReadAloudController } from './read-aloud.mjs';
import { clearLocalHistory, historyEnabled, localHistory, recentPairs,
         rememberRecentPair, removeHistoryEntry, saveHistoryEntry,
         setHistoryEnabled } from './local-workflow.mjs';
import { createToolTray } from './tool-tray.mjs';

const native = window.LinguaFusionOffline;
const $ = (id) => document.getElementById(id);

// The shared controller speaks to the cloud app through AndroidX WebMessage.
// This page is bundled and already has the smaller Offline bridge, so adapt
// only the same speak/stop messages to that trusted interface.
window.LinguaFusionReadAloud = {
  onmessage:null,
  postMessage(json) {
    let message;
    try { message = JSON.parse(json); } catch { return; }
    if (message.type === 'stop') native.stopReadAloud();
    else if (message.type === 'speak') native.readAloud(
      message.id, message.text, message.language, message.rate);
  },
};

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
let recordingTimer = null;
let conversationTurn = null;
const MAX_RECORDING_SECONDS = 1200;
let readRate = (() => {
  try {
    const value = Number(localStorage.getItem('lf-read-aloud-rate'));
    return [0.75, 1, 1.25].includes(value) ? value : 1;
  } catch { return 1; }
})();

const readTargets = [
  { id:'offline-transcript', button:'readTranscript', status:'speakReadStatus',
    text:() => $('transcript').textContent,
    language:() => $('transcript').dataset.readLanguage || ($('fromLang').value === 'auto' ? '' : $('fromLang').value) },
  { id:'offline-speech-translation', button:'readSpeechTranslation', status:'speakReadStatus',
    text:() => $('translation').textContent, language:() => $('toLang').value },
  { id:'offline-text-translation', button:'readTextResult', status:'translateReadStatus',
    text:() => $('textResult').textContent, language:() => $('textTo').value },
  { id:'offline-picture', button:'readPictureResult', status:'pictureReadStatus',
    text:() => $('readResult').textContent, language:() => $('pictureReadLanguage').value },
];
const readAloud = createReadAloudController({ scope:window, onState:event => {
  for (const target of readTargets) {
    const active = event.state === 'speaking' && event.id === target.id;
    $(target.button).textContent = active
      ? 'Stop'
      : target.id === 'offline-transcript' ? 'Read transcript aloud'
      : target.id === 'offline-speech-translation' ? 'Read translation aloud' : 'Read aloud';
    $(target.button).setAttribute('aria-pressed', String(active));
  }
  const target = readTargets.find(item => item.id === event.id);
  if (target) $(target.status).textContent = event.message;
}});

/* ---------- appearance ---------- */

function showMode(mode) {
  const night = applyMode(mode) === 'dark';
  $('modeToggle').textContent = night ? 'Night' : 'Day';
  $('modeToggle').setAttribute('aria-label',
    night ? 'Switch to day mode' : 'Switch to night mode');
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

function revealResult(element) {
  element.classList.remove('result-reveal');
  void element.offsetWidth;
  element.classList.add('result-reveal');
}

function setProcessing(button, active) {
  button.classList.toggle('is-processing', Boolean(active));
  button.setAttribute('aria-busy', String(Boolean(active)));
}

function copy(text, status) {
  if (!text) { say(status, 'There is nothing to copy yet.'); return; }
  // A WebView over file:// has no clipboard API, so fall back to the old way.
  navigator.clipboard?.writeText(text).then(
    () => say(status, 'Copied.'),
    () => say(status, 'This phone would not let the app copy that.'));
}

async function share(text, title, status) {
  if (!text) { say(status, 'There is nothing to share yet.'); return; }
  if (navigator.share) {
    try { await navigator.share({title:`LinguaFusion · ${title}`,text}); say(status,'Shared.'); return; }
    catch (error) { if (error?.name === 'AbortError') { say(status,'Sharing cancelled.'); return; } }
  }
  copy(text,status); say(status,'Sharing is unavailable here. Copied instead.');
}

function rememberOfflineResult(entry) {
  saveHistoryEntry(localStorage,entry,Date.now(),`${Date.now()}-${Math.random().toString(36).slice(2,8)}`);
  renderOfflineHistory();
}

function restoreOfflineHistory(entry) {
  if (entry.kind === 'translation') {
    $('sourceText').value=entry.input; $('textResult').textContent=entry.output;
    if (entry.source) $('textFrom').value=entry.source; if (entry.target) $('textTo').value=entry.target;
    show('viewTranslate');
  } else if (entry.kind === 'transcript') { $('transcript').textContent=entry.output; show('viewSpeak'); }
  else if (entry.kind === 'ocr') { $('readResult').textContent=entry.output; show('viewRead'); }
  else if (entry.kind === 'pronunciation') { $('sayText').value=entry.input; $('sayResult').textContent=entry.output; show('viewSay'); }
}

function renderOfflineHistory() {
  const entries=localHistory(localStorage); const list=$('offlineHistoryList'); list.replaceChildren();
  for (const entry of entries) {
    const card=document.createElement('article'); card.className='history-item';
    const title=document.createElement('strong'); title.textContent=entry.title;
    const preview=document.createElement('p'); preview.textContent=entry.output.slice(0,180);
    const actions=document.createElement('div'); actions.className='actions';
    for (const [label,action] of [['Open',()=>restoreOfflineHistory(entry)],['Copy',()=>copy(entry.output,'offlineHistoryStatus')],['Delete',()=>{removeHistoryEntry(localStorage,entry.id);renderOfflineHistory();}]]) {
      const button=document.createElement('button'); button.type='button'; button.className='secondary'; button.textContent=label; button.onclick=action; actions.append(button);
    }
    card.append(title,preview,actions); list.append(card);
  }
  $('offlineClearHistory').disabled=!entries.length;
  if (!entries.length) { const empty=document.createElement('p'); empty.className='hint'; empty.textContent=historyEnabled(localStorage)?'New results will appear here.':'History is off.'; list.append(empty); }
}

function updateConversationControls() {
  if (!state.languages.length) return;
  const a = nameOf($('conversationLangA').value);
  const b = nameOf($('conversationLangB').value);
  const active = recording || busy;
  const aButton = $('conversationRecordA');
  const bButton = $('conversationRecordB');
  aButton.querySelector('strong').textContent = conversationTurn?.side === 'a' && active ? 'Stop and translate' : `Speak ${a}`;
  bButton.querySelector('strong').textContent = conversationTurn?.side === 'b' && active ? 'Stop and translate' : `Speak ${b}`;
  aButton.classList.toggle('is-recording', conversationTurn?.side === 'a' && recording);
  bButton.classList.toggle('is-recording', conversationTurn?.side === 'b' && recording);
  aButton.disabled = !state.transcriptionSupported || (active && conversationTurn?.side !== 'a');
  bButton.disabled = !state.transcriptionSupported || (active && conversationTurn?.side !== 'b');
}

function appendConversationTurn(turn, original, translated) {
  $('conversationLog').querySelector('.conversation-empty')?.remove();
  const card=document.createElement('article'); card.className='conversation-turn'; card.dataset.speaker=turn.side;
  const head=document.createElement('header');
  const person=document.createElement('strong'); person.textContent=turn.side==='a'?'Person A':'Person B';
  const route=document.createElement('span'); route.textContent=`${nameOf(turn.source)} → ${nameOf(turn.target)}`;
  head.append(person,route);
  const source=document.createElement('p'); source.className='conversation-original'; source.lang=turn.source; source.textContent=original;
  const translation=document.createElement('p'); translation.className='conversation-translation'; translation.lang=turn.target; translation.textContent=translated;
  card.append(head,source,translation); $('conversationLog').append(card); card.scrollIntoView({block:'nearest'});
}

async function conversationRecord(side) {
  if (conversationTurn && conversationTurn.side !== side) return;
  if (!conversationTurn) {
    const source=$(side==='a'?'conversationLangA':'conversationLangB').value;
    const target=$(side==='a'?'conversationLangB':'conversationLangA').value;
    if (source===target) { say('conversationStatus','Choose two different languages first.'); return; }
    conversationTurn={side,source,target};
    $('fromLang').value=source; $('toLang').value=target; $('alsoTranslate').checked=true;
    say('conversationStatus',`Listening to ${side==='a'?'Person A':'Person B'}…`);
  }
  updateConversationControls();
  await toggleRecording();
  updateConversationControls();
}

function updatePivotWarning() {
  const from = $('fromLang').value;
  const to = $('toLang').value;
  const pivots = from !== 'auto' && from !== 'en' && to !== 'en' && from !== to;
  $('pivotWarn').hidden = !(pivots && $('alsoTranslate').checked);
}

/* ---------- Speak ---------- */

async function toggleRecording(reason = 'manual') {
  if (busy) return;
  if (!recording) {
    readAloud.stop();
    const failure = native.startRecording();
    if (failure) { say('speakStatus', failure); return; }
    recording = true;
    $('record').textContent = 'Stop and transcribe';
    $('record').classList.add('is-recording');
    document.querySelector('.record-caption').textContent = 'Listening · tap to finish';
    navigator.vibrate?.(30);
    const started=Date.now();
    recordingTimer=setInterval(()=>{
      const seconds=Math.floor((Date.now()-started)/1000);
      document.querySelector('.record-caption').textContent=`Listening · ${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')} / 20:00`;
      document.querySelector('.record-stage').style.setProperty('--record-level',`${Math.min(100,(seconds/MAX_RECORDING_SECONDS)*100)}%`);
      if (seconds >= MAX_RECORDING_SECONDS) void toggleRecording('limit');
    },1000);
    say('speakStatus', 'Recording… speak now.');
    updateConversationControls();
    return;
  }

  recording = false;
  clearInterval(recordingTimer); recordingTimer=null;
  document.querySelector('.record-stage').style.setProperty('--record-level','0%');
  navigator.vibrate?.([20,40,20]);
  busy = true;
  $('record').classList.remove('is-recording');
  setProcessing($('record'), true);
  readAloud.stop();
  $('record').disabled = true;
  $('record').textContent = 'Working…';
  document.querySelector('.record-caption').textContent = 'Turning speech into text…';
  say('speakStatus', reason === 'silence'
    ? 'One minute of silence detected. Transcribing on this phone…'
    : reason === 'limit'
      ? 'Twenty-minute limit reached. Transcribing on this phone…'
      : 'Transcribing on this phone. This can take a while.');
  if (!conversationTurn) {
    $('transcript').textContent = '';
    $('translationWrap').hidden = true;
  } else {
    say('conversationStatus', reason === 'silence'
      ? 'One minute of silence detected. Preparing this turn…'
      : reason === 'limit' ? 'Twenty-minute limit reached. Preparing this turn…' : 'Transcribing and translating this turn…');
  }

  const result = await ask('stopAndProcess', null,
    $('fromLang').value, $('toLang').value, $('alsoTranslate').checked);

  busy = false;
  $('record').disabled = false;
  $('record').textContent = 'Start recording';
  document.querySelector('.record-caption').textContent = 'Tap to start · up to 20 minutes';
  setProcessing($('record'), false);

  if (result.error) {
    say('speakStatus', result.error);
    if (conversationTurn) say('conversationStatus', result.error);
    conversationTurn=null; updateConversationControls(); return;
  }

  if (conversationTurn) {
    const turn=conversationTurn;
    if (result.transcript && result.translation) {
      appendConversationTurn(turn,result.transcript,result.translation);
      rememberOfflineResult({kind:'translation',title:'Conversation',input:result.transcript,output:result.translation,
        source:turn.source,target:turn.target});
      say('conversationStatus','Turn translated. Pass the phone to the other person.');
    } else if (result.translationError) say('conversationStatus',result.translationError);
    else say('conversationStatus','No speech was detected in that turn.');
    conversationTurn=null; updateConversationControls();
    return;
  }

  $('transcript').textContent = result.transcript || '';
  if (result.transcript) revealResult($('transcript'));
  if (result.transcript) rememberOfflineResult({kind:'transcript',title:'Transcript',output:result.transcript});
  $('transcript').dataset.readLanguage = result.spokenLanguage || result.detected || '';
  const detected = result.detected
    ? ` Heard ${nameOf(result.detected) || result.detected}.` : '';
  say('speakStatus', `Done — ${result.seconds ?? '?'} seconds.${detected}`);

  if (result.translation) {
    $('translationWrap').hidden = false;
    $('translation').textContent = result.translation;
    $('translation').lang = $('toLang').value;
    revealResult($('translation'));
    rememberOfflineResult({kind:'translation',title:'Translation',input:result.transcript||'',output:result.translation,target:$('toLang').value});
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
  setProcessing($('translate'), true);
  readAloud.stop();
  say('translateStatus', 'Translating on this phone…');
  const result = await ask('translateText', null, text, $('textFrom').value, $('textTo').value);
  $('translate').disabled = false;
  setProcessing($('translate'), false);
  if (result.error) { say('translateStatus', result.error); $('textResult').textContent = ''; return; }
  $('textResult').textContent = result.translation || '';
  $('textResult').lang = $('textTo').value;
  if (result.translation) revealResult($('textResult'));
  if (result.translation) {
    rememberRecentPair(localStorage,{source:$('textFrom').value,target:$('textTo').value},
      state.languages.map(item=>item.code),state.languages.map(item=>item.code));
    renderOfflinePairs();
    rememberOfflineResult({kind:'translation',title:'Translation',input:text,output:result.translation,source:$('textFrom').value,target:$('textTo').value});
  }
  say('translateStatus', result.pivoted
    ? 'Done. This pair goes through English, so it is rougher than usual.'
    : 'Done.');
}

/* ---------- Read ---------- */

async function readPicture() {
  $('readPicture').disabled = true;
  setProcessing($('readPicture'), true);
  readAloud.stop();
  say('readStatus', 'Choose a picture…');
  const result = await ask('readPicture', null);
  $('readPicture').disabled = false;
  setProcessing($('readPicture'), false);
  if (result.cancelled) { say('readStatus', ''); return; }
  if (result.error) { say('readStatus', result.error); $('readResult').textContent = ''; return; }
  $('readResult').textContent = result.text || '';
  if (result.text) revealResult($('readResult'));
  if (result.text) rememberOfflineResult({kind:'ocr',title:'Picture text',output:result.text});
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
  setProcessing($('romanize'), true);
  say('sayStatus', 'Working…');
  const result = await ask('romanize', null, text, $('sayLang').value);
  $('romanize').disabled = false;
  setProcessing($('romanize'), false);
  if (result.error) { say('sayStatus', result.error); $('sayResult').textContent = ''; return; }
  $('sayResult').textContent = result.romanized || '';
  if (result.romanized) revealResult($('sayResult'));
  if (result.romanized) rememberOfflineResult({kind:'pronunciation',title:'Pronunciation guide',input:text,output:result.romanized,language:$('sayLang').value});
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

function renderOfflinePairs() {
  const valid=state.languages.map(item=>item.code);
  const pairs=recentPairs(localStorage,valid,valid); $('offlineRecentPairs').hidden=!pairs.length;
  $('offlineRecentPairButtons').replaceChildren(...pairs.map(pair=>{
    const button=document.createElement('button'); button.type='button'; button.className='recent-pair secondary';
    button.textContent=`${nameOf(pair.source)} → ${nameOf(pair.target)}`;
    button.onclick=()=>{ $('textFrom').value=pair.source; $('textTo').value=pair.target; };
    return button;
  }));
}

/* ---------- updates ---------- */

async function checkForUpdate() {
  $('checkUpdate').disabled = true;
  say('updateStatus', 'Checking…');
  const result = await ask('checkForUpdate', null);
  $('checkUpdate').disabled = false;
  if (result.available) {
    // The app puts its own dialog up; this line is for anyone who dismisses it.
    say('updateStatus', `Version ${result.versionName} is available (${result.megabytes} MB). `
      + 'Nothing installs until you confirm.');
  } else {
    // A failed check and being current are indistinguishable from here, so do
    // not claim to be up to date.
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
  fill($('pictureReadLanguage'), state.languages, { selected:$('pictureReadLanguage').value || 'en' });
  const conversationA=$('conversationLangA').value || $('conversationLangA').dataset.preferred || 'en';
  const conversationB=$('conversationLangB').value || $('conversationLangB').dataset.preferred || 'de';
  fill($('conversationLangA'), state.languages, { selected:conversationA });
  fill($('conversationLangB'), state.languages, { selected:conversationB });

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
      + 'Arabic script needs the Online app.';
  }
  renderModels();
  updatePivotWarning();
  renderOfflinePairs();

  const packs = await ask('listTranslationLanguages', null);
  state.installedPacks = new Set(packs.installed || []);
  renderPacks();
  updateConversationControls();
}

function show(view) {
  readAloud.stop({ quiet:true });
  for (const section of ['viewSpeak', 'viewTranslate', 'viewRead', 'viewSay', 'viewConversation', 'viewStorage']) {
    const element = $(section);
    const active = section === view;
    element.hidden = !active;
    element.classList.remove('view-enter');
    if (active) {
      void element.offsetWidth;
      element.classList.add('view-enter');
    }
  }
  for (const button of document.querySelectorAll('nav button')) {
    const here = button.dataset.view === view;
    button.classList.toggle('active', here);
    button.setAttribute('aria-current', String(here));
  }
}

function start() {
  initAppearance();
  showMode(getMode());
  for (const theme of CLOUD_THEMES) $('themeChoice').add(new Option(theme.name, theme.id));
  for (const font of LF_FONTS) $('fontChoice').add(new Option(font.name, font.id));
  $('themeChoice').value = getTheme();
  $('fontChoice').value = getFont();
  $('reduceMotion').checked = getMotion() === 'balanced';
  $('motionStatus').textContent = $('reduceMotion').checked ? 'Balanced motion' : 'Lively motion';
  $('themeChoice').onchange = () => applyTheme($('themeChoice').value);
  $('fontChoice').onchange = () => applyFont($('fontChoice').value);
  $('reduceMotion').onchange = () => {
    const balanced = $('reduceMotion').checked;
    applyMotion(balanced ? 'balanced' : 'lively');
    $('motionStatus').textContent = balanced ? 'Balanced motion' : 'Lively motion';
  };
  $('modeToggle').onclick = () => showMode(getMode() === 'dark' ? 'light' : 'dark');
  $('leave').onclick = () => native.leaveOfflineMode();

  try {
    const pair=JSON.parse(localStorage.getItem('lf-conversation-languages-v1'));
    if (pair) {
      $('conversationLangA').dataset.preferred=pair.a||'en';
      $('conversationLangB').dataset.preferred=pair.b||'de';
    }
  } catch { /* keep the defaults */ }
  for (const id of ['conversationLangA','conversationLangB']) {
    $(id).onchange=()=>{
      try { localStorage.setItem('lf-conversation-languages-v1',JSON.stringify({a:$('conversationLangA').value,b:$('conversationLangB').value})); }
      catch { /* optional */ }
      updateConversationControls();
    };
  }
  $('conversationSwap').onclick=()=>{
    const a=$('conversationLangA').value; $('conversationLangA').value=$('conversationLangB').value; $('conversationLangB').value=a;
    $('conversationLangA').onchange();
  };
  $('conversationRecordA').onclick=()=>void conversationRecord('a');
  $('conversationRecordB').onclick=()=>void conversationRecord('b');
  $('clearConversation').onclick=()=>{
    const empty=document.createElement('p'); empty.className='conversation-empty'; empty.textContent='Choose who is speaking, then tap their microphone.';
    $('conversationLog').replaceChildren(empty); say('conversationStatus','Conversation cleared from this screen.');
  };

  createToolTray({document,storage:localStorage,onAction:tool=>{
    if (tool==='conversation') { show('viewConversation'); updateConversationControls(); }
    else if (tool==='import') { show('viewRead'); say('readStatus','Choose a picture to read on this phone.'); }
    else if (tool==='history'||tool==='saved') {
      show('viewStorage');
      setTimeout(()=>document.querySelector('.history-settings')?.scrollIntoView({block:'start'}),0);
      say('offlineHistoryStatus',tool==='saved'?'Saved results stay only on this phone.':'Your recent on-device results are shown here.');
    }
  }});

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
  $('shareTranscript').onclick = () => void share($('transcript').textContent,'Transcript','speakStatus');
  $('copyTranslation').onclick = () => copy($('translation').textContent, 'speakStatus');
  $('copyText').onclick = () => copy($('textResult').textContent, 'translateStatus');
  $('shareText').onclick = () => void share($('textResult').textContent,'Translation','translateStatus');
  $('readPicture').onclick = readPicture;
  $('sendReadToTranslate').onclick = sendReadToTranslate;
  $('copyRead').onclick = () => copy($('readResult').textContent, 'readStatus');
  $('shareRead').onclick = () => void share($('readResult').textContent,'Picture text','readStatus');
  $('romanize').onclick = romanize;
  $('copySay').onclick = () => copy($('sayResult').textContent, 'sayStatus');
  $('shareSay').onclick = () => void share($('sayResult').textContent,'Pronunciation guide','sayStatus');
  $('offlineSaveHistory').checked=historyEnabled(localStorage);
  $('offlineSaveHistory').onchange=()=>{setHistoryEnabled(localStorage,$('offlineSaveHistory').checked);renderOfflineHistory();};
  $('offlineClearHistory').onclick=()=>{clearLocalHistory(localStorage);renderOfflineHistory();say('offlineHistoryStatus','Private history cleared.');};
  renderOfflineHistory();
  $('checkUpdate').onclick = checkForUpdate;

  for (const id of ['speechReadRate', 'textReadRate', 'pictureReadRate']) {
    for (const [value, text] of [[0.75, '0.75×'], [1, '1×'], [1.25, '1.25×']]) $(id).add(new Option(text, String(value)));
    $(id).value = String(readRate);
    $(id).onchange = () => {
      const value = Number($(id).value);
      if (![0.75, 1, 1.25].includes(value)) return;
      readRate = value;
      for (const other of ['speechReadRate', 'textReadRate', 'pictureReadRate']) $(other).value = String(value);
      try { localStorage.setItem('lf-read-aloud-rate', String(value)); } catch { /* optional */ }
    };
  }
  for (const target of readTargets) {
    $(target.button).onclick = () => readAloud.read({
      id:target.id, text:target.text(), language:target.language(), rate:readRate,
    });
  }

  window.addEventListener('pagehide', () => readAloud.stop({ quiet:true }));
  window.addEventListener('lf-native-recording-stop', event => {
    if (recording && !busy) void toggleRecording(event.detail?.reason || 'limit');
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) readAloud.stop({ quiet:true });
  });

  refresh();
}

if (!native) {
  document.body.innerHTML =
    '<main><h2>Offline mode is unavailable</h2>' +
    '<p>This page has to run inside the LinguaFusion app.</p></main>';
} else {
  start();
}
