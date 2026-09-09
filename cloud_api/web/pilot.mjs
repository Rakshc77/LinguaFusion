import { APP_VERSION, checkForUpdate, activateUpdate } from './updates.mjs';
import { createCloudAuth } from './cloud-auth.mjs';
import { createCloudClient } from './cloud-client.mjs';
import { PRONUNCIATION_LANGUAGES, pronunciationView, validateRequest } from './pronunciation.mjs';
import { buildWav, MAX_SECONDS } from './wav.mjs';
import { CLOUD_THEMES, LF_FONTS, applyFont, applyTheme, getFont, getTheme, applyMode, initAppearance } from './themes.mjs';

const $ = id => document.getElementById(id);
const auth = createCloudAuth();
const api = createCloudClient(auth);

let epoch = 0;
let signedIn = false;
let emailConfirmed = false;
let submitting = false;
let unsubscribe;
let translating = false;
let pronouncing = false;
let capture = null;
let captureStarting = false;
let captureGeneration = 0;
let transcribing = false;
let nativeRecording = null;
const ready = { translate: false, pronounce: false, transcribe: false, ocr: false };
let translationModels = [];
let translationLimit = 6000;
let pronunciationLimit = 2000;
let chosenModel = '';

function rememberedModel() {
  try { return localStorage.getItem('lf-translate-model') || ''; } catch { return ''; }
}
function rememberModel(id) {
  try { localStorage.setItem('lf-translate-model', id); } catch { /* nothing to remember with */ }
}

const languages = [['en', 'English'], ['de', 'German'], ['es', 'Spanish'],
                   ['hi', 'Hindi'], ['ar', 'Arabic'], ['or', 'Odia']];
for (const [value, text] of languages) { $('source').add(new Option(text, value)); $('target').add(new Option(text, value)); }
$('target').value = 'de';
for (const [value, text] of PRONUNCIATION_LANGUAGES) $('pronounceLanguage').add(new Option(text, value));

// Appearance first, so the chosen look is in place before anything is drawn.
initAppearance();
for (const theme of CLOUD_THEMES) $('themeChoice').add(new Option(theme.name, theme.id));
for (const font of LF_FONTS) $('fontChoice').add(new Option(font.name, font.id));
$('themeChoice').value = getTheme();
$('fontChoice').value = getFont();
function syncModeControl() {
  const mode = document.documentElement.dataset.mode;
  $('modeToggle').textContent = mode === 'dark' ? 'Night' : 'Day';
  $('modeToggle').setAttribute('aria-label', mode === 'dark' ? 'Switch to day mode' : 'Switch to night mode');
}
syncModeControl();
$('modeToggle').addEventListener('click', () => {
  applyMode(document.documentElement.dataset.mode === 'dark' ? 'light' : 'dark');
  syncModeControl();
});
$('themeChoice').addEventListener('change', () => applyTheme($('themeChoice').value));
$('fontChoice').addEventListener('change', () => applyFont($('fontChoice').value));

// The full Offline Android app marks the hosted page after it has loaded. The
// small Online-only wrapper never sets this flag, so it is never offered a mode
// it cannot run. The native app owns the offline screen and downloaded models.
function revealOfflineModeWhenAvailable(attempt = 0) {
  if (window.LFNativeOfflineMode === true) {
    $('goOffline').hidden = false;
    $('apkUpdateNote').hidden = false;
    // Only the app knows its own version, and only newer builds report it.
    // Older ones say nothing rather than showing a label that never resolves.
    const installed = window.LFNativeAppVersion;
    if (typeof installed === 'string' && /^[\w. ]{1,20}$/.test(installed)) {
      $('apkVersion').textContent = `Installed app · ${installed}. `;
    }
    return;
  }
  if (attempt < 24 && /;\s*wv\)/.test(navigator.userAgent)) {
    setTimeout(() => revealOfflineModeWhenAvailable(attempt + 1), 250);
  }
}
revealOfflineModeWhenAvailable();
$('goOffline').addEventListener('click', () => {
  if (updateActivityInProgress()) {
    status('Finish the current recording or processing before switching modes.');
    return;
  }
  // Fixed app route only: no server address, token or user-provided data enters
  // the native handoff. The Offline app recognizes this exact URI.
  window.location.assign('linguafusion-mode://offline');
});

// The installed app, as opposed to this page. The app intercepts the scheme,
// compares its own versionCode against what is published, and shows its own

// Status goes wherever the person is actually looking.
function status(message) {
  ($('workspace').hidden ? $('setupStatus') : $('status')).textContent = message;
}

// --- navigation --------------------------------------------------------------

function showView(id) {
  for (const view of document.querySelectorAll('.view')) view.hidden = view.id !== id;
  for (const item of document.querySelectorAll('.nav-item')) {
    const active = item.dataset.view === id;
    item.classList.toggle('active', active);
    item.setAttribute('aria-current', active ? 'page' : 'false');
  }
  window.scrollTo(0, 0);
}
for (const item of document.querySelectorAll('.nav-item')) {
  item.addEventListener('click', () => showView(item.dataset.view));
}

// --- shared helpers ----------------------------------------------------------

function showSpending(data) {
  $('spending').textContent = `This month (${data.month}): spent $${data.estimated_spent_usd}; `
    + `held $${data.unresolved_reserved_usd}; remaining $${data.remaining_usd} of $${data.budget_usd}.`;
}

async function copyText(value, label, target) {
  if (!value) return;
  try {
    await navigator.clipboard.writeText(value);
    target.textContent = `${label} copied.`;
    return;
  } catch { /* Clipboard API unavailable or refused; fall through. */ }
  const scratch = document.createElement('textarea');
  scratch.value = value;
  scratch.setAttribute('readonly', '');
  scratch.style.position = 'fixed';
  scratch.style.opacity = '0';
  document.body.append(scratch);
  scratch.select();
  try {
    target.textContent = document.execCommand('copy')
      ? `${label} copied.` : 'Copying is unavailable here. Select the text and copy it manually.';
  } catch {
    target.textContent = 'Copying is unavailable here. Select the text and copy it manually.';
  } finally {
    scratch.remove();
  }
}

function stopCapture() {
  captureGeneration++;
  nativeRecording = null;
  if (!capture) return;
  try { capture.processor.disconnect(); capture.source.disconnect(); } catch { /* already torn down */ }
  for (const track of capture.stream.getTracks()) track.stop();
  void capture.context.close().catch(() => {});
  capture = null;
  $('recordToggle').textContent = 'Start recording';
}

function clearPrivateText() {
  $('password').value = ''; $('newPassword').value = '';
  $('text').value = ''; $('result').textContent = 'Your translation will appear here.';
  $('paidConsent').checked = false;
  $('pronounceText').value = ''; $('pronounceConsent').checked = false;
  $('pronounceResult').hidden = true; $('pronounceStatus').textContent = '';
  $('pronounceNative').textContent = ''; $('pronounceRoman').textContent = '';
  $('transcript').textContent = ''; $('speechStatus').textContent = ''; $('speechConsent').checked = false;
  $('ocrResult').textContent = ''; $('ocrStatus').textContent = ''; $('ocrConsent').checked = false;
  $('ocrFile').value = '';
  $('reqName').value = ''; $('reqOrg').value = ''; $('accessStatus').textContent = '';
  $('ownerUsers').replaceChildren(); $('requestList').replaceChildren();
  $('ownerTotal').textContent = ''; $('policyUid').value = ''; $('spending').textContent = '';
  $('failureList').replaceChildren(); $('reviewDue').hidden = true; $('reviewNext').textContent = '';
  showAdvanced(false);
  stopCapture();
}

// --- capability gating -------------------------------------------------------

function applyReadiness() {
  const panes = [['translate', 'translatePane', 'translateUnavailable'],
                 ['pronounce', 'pronunciationPane', 'pronounceUnavailable'],
                 ['transcribe', 'speechPane', 'speechUnavailable'],
                 ['ocr', 'ocrPane', 'ocrUnavailable']];
  for (const [capability, pane, notice] of panes) {
    $(pane).hidden = !ready[capability];
    $(notice).hidden = ready[capability];
  }
  // The consent boxes live OUTSIDE the fieldsets they gate. Gating a fieldset on
  // a checkbox inside it disables that checkbox, which cannot then be ticked.
  $('translationFields').disabled = translating || !ready.translate || !$('paidConsent').checked;
  $('pronounceFields').disabled = pronouncing || !ready.pronounce;
  $('pronounce').disabled = pronouncing || !ready.pronounce || !$('pronounceConsent').checked;
}
$('paidConsent').addEventListener('change', applyReadiness);
$('pronounceConsent').addEventListener('change', applyReadiness);

// --- owner -------------------------------------------------------------------

function showAdvanced(open) {
  // Collapsed by default: it takes a raw UID and is easy to fill in wrongly.
  $('ownerPolicyForm').hidden = !open;
  $('toggleAdvanced').setAttribute('aria-expanded', String(Boolean(open)));
}
$('toggleAdvanced').addEventListener('click', () => showAdvanced($('ownerPolicyForm').hidden));

function line(parent, text, className) {
  const item = document.createElement('p');
  if (className) item.className = className;
  item.textContent = text;             // Requester-supplied: never innerHTML.
  parent.append(item);
  return item;
}

async function loadOwner() {
  const current = epoch;
  try {
    const data = await api.request('/owner/users');
    if (current !== epoch) return;
    $('ownerTotal').textContent = `Everyone this month: spent $${data.spending.estimated_spent_usd}; `
      + `held $${data.spending.unresolved_reserved_usd}.`;
    $('ownerUsers').replaceChildren();
    if (!data.users.length) { line($('ownerUsers'), 'Nobody has access yet.', 'hint'); return; }
    for (const user of data.users) {
      const row = document.createElement('div');
      row.className = 'person';
      line(row, user.name || 'Unnamed account', 'person-name');
      line(row, user.email || `UID ${user.uid}`, 'hint');
      if (user.organisation) line(row, user.organisation, 'hint');
      line(row, `${user.enabled ? 'Allowed' : 'No access'}${user.is_owner ? ' · owner' : ''}`,
           user.enabled ? 'tag ok' : 'tag off');
      line(row, `${user.attempts}/${user.monthly_limit} requests this month · `
        + `spent $${user.spending.estimated_spent_usd} · held $${user.spending.unresolved_reserved_usd} · `
        + `budget $${user.spending.budget_usd}`, 'hint');

      const edit = document.createElement('button');
      edit.type = 'button'; edit.className = 'secondary'; edit.textContent = 'Edit limits';
      edit.addEventListener('click', () => {
        showAdvanced(true);
        $('policyUid').value = user.uid;
        $('policyEnabled').checked = Boolean(user.enabled);
        $('policyRequests').value = user.monthly_limit;
        $('policyBudget').value = Number(user.spending.budget_usd).toFixed(2);
        $('policyUid').focus();
      });
      row.append(edit);

      if (!user.is_owner) {
        const remove = document.createElement('button');
        remove.type = 'button'; remove.className = 'danger'; remove.textContent = 'Remove';
        remove.addEventListener('click', () => confirmInPage(row,
          `Remove ${user.name || 'this account'}? Their access ends and their details are erased.`,
          'Remove', () => removeUser(user.uid)));
        row.append(remove);
      }
      $('ownerUsers').append(row);
    }
  } catch (error) { if (current === epoch) status(error.message); }
}

async function removeUser(uid) {
  const current = epoch;
  try {
    await api.request('/owner/users/' + uid, null, { method: 'DELETE' });
    if (current !== epoch) return;
    status('Access revoked and their details erased. Recorded charges stay in the ledger.');
    await loadOwner();
    await loadRequests();
  } catch (error) { if (current === epoch) status(error.message); }
}

async function loadRequests() {
  const current = epoch;
  try {
    const data = await api.request('/owner/requests?status=pending');
    if (current !== epoch) return;
    $('requestList').replaceChildren();
    if (!data.requests.length) { line($('requestList'), 'No requests waiting.', 'hint'); return; }
    for (const item of data.requests) {
      const row = document.createElement('div');
      row.className = 'person';
      line(row, item.name || 'Unnamed', 'person-name');
      line(row, item.email || '', 'hint');
      if (item.organisation) line(row, item.organisation, 'hint');
      line(row, `Asked ${String(item.requested_at || '').slice(0, 10)}`, 'hint');
      for (const [decision, label] of [['approved', 'Approve'], ['denied', 'Deny']]) {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = label;
        if (decision === 'denied') button.className = 'secondary';
        button.addEventListener('click', () => confirmInPage(row,
          `${label} ${item.name || 'this request'}?`, label,
          () => decideRequest(item.uid, decision)));
        row.append(button);
      }
      $('requestList').append(row);
    }
  } catch (error) { if (current === epoch) status(error.message); }
}

function confirmInPage(row, question, label, action) {
  // NEVER window.confirm(): it returns false without showing anything in
  // installed PWAs, Android WebViews and pages where dialogs were suppressed,
  // which made these buttons silently do nothing at all.
  if (row.dataset.confirming === 'yes') return;
  row.dataset.confirming = 'yes';
  const bar = document.createElement('p');
  bar.className = 'confirm';
  bar.append(document.createTextNode(question + ' '));
  const yes = document.createElement('button');
  yes.type = 'button'; yes.textContent = `Yes, ${label.toLowerCase()}`;
  const no = document.createElement('button');
  no.type = 'button'; no.className = 'secondary'; no.textContent = 'Cancel';
  const dismiss = () => { bar.remove(); delete row.dataset.confirming; };
  yes.addEventListener('click', () => { dismiss(); void action(); });
  no.addEventListener('click', dismiss);
  bar.append(yes, no);
  row.append(bar);
  yes.focus();
}

async function decideRequest(uid, decision) {
  const current = epoch;
  const body = new FormData();
  body.set('decision', decision);
  try {
    await api.request('/owner/requests/' + uid, body);
    if (current !== epoch) return;
    status(`Request ${decision}. Their allowance was updated to match.`);
    await loadRequests();
    await loadOwner();
  } catch (error) { if (current === epoch) status(error.message); }
}

// The reminder is owner-only: caps.price_review is null for everyone else, so
// other people never see it and are never interrupted by it.
function showReview(review) {
  if (!review) { $('reviewDue').hidden = true; $('reviewNext').textContent = ''; return; }
  $('reviewDue').hidden = !review.due;
  $('reviewText').textContent = 'Time for the monthly check: review usage and provider prices. '
    + `Last checked ${review.last_reviewed}.`;
  $('reviewNext').textContent = review.due
    ? ''
    : `Prices last reviewed ${review.last_reviewed}. Next check due ${review.next_due}.`;
}

$('checkProviderSpend').addEventListener('click', loadProviderSpend);
$('reviewDone').addEventListener('click', async () => {
  const current = epoch;
  $('reviewDone').disabled = true;
  try {
    const result = await api.request('/owner/price-review', new FormData());
    if (current !== epoch) return;
    showReview(result);
    status(`Noted. Next check due ${result.next_due}.`);
  } catch (error) { if (current === epoch) status(error.message); }
  finally { $('reviewDone').disabled = false; }
});

/* The ledger's own number beside the provider's, because the useful fact is
   not either figure but the gap between them. Fetched on demand rather than
   with the page: it calls out to OpenRouter, and the owner page must load
   whether or not a provider is answering. */
async function loadProviderSpend() {
  const panel = $('providerSpend');
  const current = epoch;
  $('checkProviderSpend').disabled = true;
  panel.replaceChildren();
  line(panel, 'Asking the providers…', 'hint');
  try {
    const data = await api.request('/owner/provider-spend');
    if (current !== epoch) return;
    panel.replaceChildren();
    // Money at six decimal places is how the ledger stores it, not how anyone
    // reads it. Sub-cent amounts still need their digits, though, because most
    // of what this app spends is well under a cent.
    const money = (value) => {
      const amount = Number(value);
      if (!Number.isFinite(amount)) return String(value);
      if (amount === 0) return '$0.00';
      return amount < 0.01 ? `$${amount.toFixed(6)}` : `$${amount.toFixed(2)}`;
    };
    line(panel, `This app's ledger estimates ${money(data.ledger_estimate_usd)}` +
                (data.ledger_held_usd && Number(data.ledger_held_usd) > 0
                  ? `, plus ${money(data.ledger_held_usd)} still held` : ''), 'person-name');
    for (const item of data.providers) {
      const row = document.createElement('div');
      row.className = 'person';
      const who = item.name || item.provider;
      line(row, item.spent_usd === null || item.spent_usd === undefined
        ? `${who}: not available`
        : `${who}: ${money(item.spent_usd)} billed`, 'person-name');
      if (item.unavailable) line(row, item.unavailable, 'hint');
      // Links open in the browser, not in this app: the app has no business
      // holding a session for a billing console.
      const links = document.createElement('p');
      links.className = 'actions';
      for (const target of [item, item.also].filter(Boolean)) {
        const url = target.console || target.url;
        if (!url) continue;
        const link = document.createElement('a');
        link.href = url;
        link.target = '_blank';
        link.rel = 'noreferrer noopener';
        link.textContent = target.console_label || target.label || 'Open console';
        link.className = 'console-link';
        links.append(link);
      }
      if (links.childElementCount) row.append(links);
      panel.append(row);
    }
    line(panel, data.note, 'hint');
  } catch (error) {
    if (current !== epoch) return;
    panel.replaceChildren();
    line(panel, 'Could not read provider spend just now.', 'hint');
  } finally {
    $('checkProviderSpend').disabled = false;
  }
}

async function loadFailures() {
  const current = epoch;
  try {
    const data = await api.request('/owner/diagnostics');
    if (current !== epoch) return;
    $('failureList').replaceChildren();
    if (!data.recent_failures.length) {
      line($('failureList'), 'No provider failures recorded on this server.', 'hint');
    } else {
      for (const item of data.recent_failures) {
        const row = document.createElement('div');
        row.className = 'person';
        line(row, `${item.capability} · ${item.at.replace('T', ' ').replace('+00:00', ' UTC')}`, 'person-name');
        line(row, item.reason, 'hint');
        $('failureList').append(row);
      }
    }
    line($('failureList'), data.note, 'hint');
  } catch (error) { if (current === epoch) status(error.message); }
}
$('refreshFailures').addEventListener('click', () => void loadFailures());
$('refreshUsers').addEventListener('click', () => void loadOwner());
$('refreshRequests').addEventListener('click', () => void loadRequests());

$('ownerPolicyForm').addEventListener('submit', async event => {
  event.preventDefault();
  const current = epoch;
  const uid = $('policyUid').value.trim();
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(uid)) { status('Enter a valid Firebase UID.'); return; }
  $('savePolicy').disabled = true;
  const body = new FormData();
  body.set('enabled', String($('policyEnabled').checked));
  body.set('monthly_limit', $('policyRequests').value);
  body.set('monthly_budget_usd', $('policyBudget').value);
  try {
    await api.request('/owner/users/' + uid, body);
    if (current !== epoch) return;
    status('Saved.');
    await loadOwner();
    const spending = await api.request('/usage');
    if (current === epoch) showSpending(spending);
  } catch (error) { if (current === epoch) status(error.message); }
  finally { $('savePolicy').disabled = false; }
});

// --- access ------------------------------------------------------------------

async function checkAccess() {
  const current = ++epoch;
  api.cancel();
  $('checkAccess').disabled = true;
  try {
    const caps = await api.request('/capabilities');
    if (current !== epoch) return;
    for (const key of Object.keys(ready)) ready[key] = caps.pilot?.[key] === true;

    translationLimit = Number(caps.max_text_characters) || translationLimit;
    pronunciationLimit = Number(caps.max_pronunciation_characters) || pronunciationLimit;
    $('text').maxLength = translationLimit;
    $('pronounceText').maxLength = pronunciationLimit;
    updateTextCount();
    translationModels = caps.translation_models || [];
    const remembered = rememberedModel();
    chosenModel = translationModels.some(model => model.id === remembered)
      ? remembered
      : (caps.default_translation_model || translationModels[0]?.id || '');
    $('modelCaveat').textContent = caps.model_guidance_is_measured
      ? ''
      : 'These notes are the models’ general reputations, not measurements taken on your own text. '
        + 'If a language matters to you, try both on the same passage and keep the better one.';
    renderModels();

    // Approved: the setup text has done its job and only gets in the way now.
    $('onboarding').hidden = true;
    $('workspace').hidden = false;
    $('pageFooter').hidden = true;
    $('ownerPanel').hidden = !caps.is_owner;
    // Fetched only when asked: it calls out to a provider.
    applyReadiness();

    const spending = await api.request('/usage');
    if (current !== epoch) return;
    showSpending(spending);
    status('Ready.');
    showReview(caps.price_review);
    if (caps.is_owner) { await loadOwner(); await loadRequests(); await loadFailures(); }
  } catch (error) {
    if (current !== epoch) return;
    if (error.status === 403) {
      // Signed in but not approved: the one error with a next step.
      $('workspace').hidden = true;
      $('onboarding').hidden = false;
      $('accessRequest').hidden = false;
      $('accessFields').disabled = !emailConfirmed;
      if (emailConfirmed) {
        void loadOwnRequest();
        status('Your account is not approved yet. Send the owner a request below.');
      } else {
        $('accessStatus').textContent = 'Confirm your email address first, then send your request.';
        status('Confirm your email address to continue.');
      }
    } else {
      status(error.message);
    }
  } finally {
    if (current === epoch) $('checkAccess').disabled = false;
  }
}

function renderModels() {
  $('modelList').replaceChildren();
  for (const model of translationModels) {
    const card = document.createElement('div');
    card.className = 'person model' + (model.id === chosenModel ? ' chosen' : '');

    const choose = document.createElement('button');
    choose.type = 'button';
    choose.className = model.id === chosenModel ? '' : 'secondary';
    choose.textContent = model.id === chosenModel ? 'In use' : 'Use this one';
    choose.disabled = model.id === chosenModel;
    choose.addEventListener('click', () => {
      chosenModel = model.id;
      rememberModel(model.id);
      renderModels();
      status(`Translation will use ${model.name}.`);
    });

    line(card, model.name, 'person-name');
    line(card, model.note || '', 'hint');
    if (model.best_for) line(card, `Better for: ${model.best_for}`, 'hint');
    if (model.weaker_at) line(card, `Weaker at: ${model.weaker_at}`, 'hint');
    if (model.observed) line(card, `Seen here: ${model.observed}`, 'hint');
    line(card, `Speed: ${model.speed || '—'} · Cost per request: ${model.cost || '—'}`, 'hint');
    card.append(choose);
    $('modelList').append(card);
  }
  const chosen = translationModels.find(model => model.id === chosenModel);
  $('translateModelNote').textContent = chosen
    ? `Using ${chosen.name}. ${chosen.note || ''} Change it under Model.`
    : 'No translation model is available.';
}

async function loadOwnRequest() {
  try {
    const mine = await api.request('/access/request');
    if (mine.status === 'pending') {
      $('accessStatus').textContent = 'Your request is waiting for the owner to decide.';
      $('accessFields').disabled = true;
    } else if (mine.status === 'denied') {
      $('accessStatus').textContent = 'The owner declined this request. Contact them before resending.';
    }
  } catch { /* No existing request, or unavailable; leave the form usable. */ }
}

$('accessForm').addEventListener('submit', async event => {
  event.preventDefault();
  const current = epoch;
  const name = $('reqName').value.trim();
  const organisation = $('reqOrg').value.trim();
  if (!name || !organisation) { $('accessStatus').textContent = 'Enter your name and organisation.'; return; }
  const body = new FormData();
  body.set('name', name); body.set('organisation', organisation);
  $('accessFields').disabled = true;
  $('accessStatus').textContent = 'Sending your request…';
  try {
    const result = await api.request('/access/request', body);
    if (current !== epoch) return;
    $('accessStatus').textContent = result.message || 'Your request was sent.';
  } catch (error) {
    if (current === epoch) { $('accessStatus').textContent = error.message; $('accessFields').disabled = false; }
  }
});

// --- sign in / up ------------------------------------------------------------

async function setup() {
  $('retryLoad').hidden = true;
  $('loginFields').disabled = true;
  status('Loading secure sign-in…');
  try {
    unsubscribe?.();
    unsubscribe = await auth.observe(user => {
      ++epoch; api.cancel(); clearPrivateText();
      translating = false; pronouncing = false;
      for (const key of Object.keys(ready)) ready[key] = false;
      signedIn = Boolean(user);
      emailConfirmed = user?.emailVerified === true;

      $('workspace').hidden = true;
      $('onboarding').hidden = false;
      $('pageFooter').hidden = false;
      $('loginForm').hidden = signedIn;
      $('signUpForm').hidden = true;
      $('accessRequest').hidden = true;
      // Not gated on confirmation: an account approved before confirmation
      // existed (the owner's included) must not be locked out of its own app.
      $('verifyEmail').hidden = !signedIn || emailConfirmed;
      $('verifyAddress').textContent = user?.email || '';
      $('signedInAs').hidden = !signedIn;
      $('signedInAs').textContent = signedIn ? `Signed in as ${user.email}` : '';
      $('onboardingSignOut').hidden = !signedIn;
      $('accountName').textContent = user?.email || '';
      $('accountEmail').textContent = user?.email || '';
      // Installed already, or signed in: the download offer is just clutter.
      $('androidOffer').hidden = signedIn || isInstalled();

      if (signedIn) void checkAccess();
      else status('Sign in, or create an account, to get started.');
    });
    $('loginFields').disabled = false;
  } catch {
    status('Secure sign-in could not load. Check your connection, then retry.');
    $('retryLoad').hidden = false;
  }
}
$('retryLoad').addEventListener('click', setup);

$('loginForm').addEventListener('submit', async event => {
  event.preventDefault();
  if (submitting) return;
  submitting = true; $('loginFields').disabled = true;
  status('Signing in…');
  try { await auth.signIn($('email').value, $('password').value, $('remember').checked); }
  catch (error) { status(error.message); }
  finally { $('password').value = ''; submitting = false; $('loginFields').disabled = false; }
});

$('showSignUp').addEventListener('click', () => { $('loginForm').hidden = true; $('signUpForm').hidden = false; $('newEmail').focus(); });
$('showSignIn').addEventListener('click', () => { $('signUpForm').hidden = true; $('loginForm').hidden = false; $('email').focus(); });

$('signUpForm').addEventListener('submit', async event => {
  event.preventDefault();
  if (submitting) return;
  submitting = true; $('signUpFields').disabled = true;
  status('Creating your account…');
  try {
    await auth.signUp($('newEmail').value, $('newPassword').value, true);
    status('Account created. Check your email for the confirmation link.');
  } catch (error) { status(error.message); }
  finally { $('newPassword').value = ''; submitting = false; $('signUpFields').disabled = false; }
});

$('resendVerification').addEventListener('click', async () => {
  $('resendVerification').disabled = true;
  try {
    await auth.sendVerification();
    $('verifyStatus').textContent = 'Sent. Check your inbox, and your spam folder.';
  } catch (error) { $('verifyStatus').textContent = error.message; }
  finally { setTimeout(() => { $('resendVerification').disabled = false; }, 15000); }
});

$('verifyContinue').addEventListener('click', async () => {
  $('verifyContinue').disabled = true;
  $('verifyStatus').textContent = 'Checking…';
  try {
    // Firebase caches this flag, so ask the server rather than trusting it.
    emailConfirmed = await auth.refreshVerification();
    if (emailConfirmed) { $('verifyEmail').hidden = true; $('verifyStatus').textContent = ''; void checkAccess(); }
    else $('verifyStatus').textContent = 'Not confirmed yet. Open the link in the email, then try again.';
  } catch (error) { $('verifyStatus').textContent = error.message; }
  finally { $('verifyContinue').disabled = false; }
});

async function signOut() {
  ++epoch; api.cancel(); clearPrivateText();
  try { await auth.signOut(); status('Signed out.'); }
  catch { status('Sign-out could not complete. Please retry before leaving this device.'); }
}
$('signOut').addEventListener('click', () => void signOut());
$('onboardingSignOut').addEventListener('click', () => void signOut());
$('checkAccess').addEventListener('click', () => { if (signedIn) void checkAccess(); });

// --- translate ---------------------------------------------------------------

$('translateForm').addEventListener('submit', async event => {
  event.preventDefault();
  if (!signedIn || $('translationFields').disabled) return;
  if (!$('text').value.trim()) { status('Enter some text to translate.'); return; }
  const current = epoch;
  const body = new FormData();
  body.set('text', $('text').value);
  body.set('target_lang', $('target').value);
  body.set('model', chosenModel);
  body.set('paid_consent', String($('paidConsent').checked));
  translating = true; applyReadiness();
  $('result').textContent = 'Translating…'; status('Translating…');
  try {
    const result = await api.request('/api/translate', body);
    if (current !== epoch) return;
    if (result.ok !== true || typeof result.translated_text !== 'string') throw new Error('Unexpected response.');
    $('result').textContent = result.translated_text;
    status('Translation complete.');
    if (result.spending) showSpending(result.spending);
  } catch (error) {
    if (current === epoch) { $('result').textContent = 'No translation returned.'; status(error.message); }
  } finally { translating = false; if (current === epoch) applyReadiness(); }
});

// --- pronunciation -----------------------------------------------------------

$('copyNative').addEventListener('click', () => void copyText($('pronounceNative').textContent, 'Original text', $('pronounceStatus')));
$('copyRoman').addEventListener('click', () => void copyText($('pronounceRoman').textContent, 'Pronunciation', $('pronounceStatus')));

$('pronounceForm').addEventListener('submit', async event => {
  event.preventDefault();
  if (!signedIn || $('pronounce').disabled) return;
  const language = $('pronounceLanguage').value;
  const check = validateRequest($('pronounceText').value, language);
  if (!check.ok) { $('pronounceStatus').textContent = check.message; return; }
  const current = epoch;
  const body = new FormData();
  body.set('text', check.text); body.set('language', language);
  body.set('paid_consent', String($('pronounceConsent').checked));
  pronouncing = true; applyReadiness();
  $('pronounceResult').hidden = true;
  $('pronounceStatus').textContent = 'Requesting a pronunciation guide…';
  try {
    const result = await api.request('/api/pronounce', body);
    if (current !== epoch) return;
    const view = pronunciationView(check.text, language, result);
    if (!view.ok) { $('pronounceStatus').textContent = view.message; return; }
    $('pronounceNotice').textContent = view.notice;
    $('pronounceNative').textContent = view.native;
    $('pronounceNative').lang = view.language;
    $('pronounceRoman').textContent = view.romanized;
    $('pronounceResult').hidden = false;
    $('pronounceStatus').textContent = `Approximate ${view.languageName} pronunciation. The original is unchanged.`;
    if (result.spending) showSpending(result.spending);
  } catch (error) { if (current === epoch) $('pronounceStatus').textContent = error.message; }
  finally { pronouncing = false; if (current === epoch) applyReadiness(); }
});

// --- speech ------------------------------------------------------------------

$('copyTranscript').addEventListener('click', () => void copyText($('transcript').textContent, 'Transcript', $('speechStatus')));

/** Say which microphone problem actually happened.
 *  One catch-all "Microphone unavailable" told someone who had already granted
 *  permission to go and grant permission, which is worse than saying nothing. */
/* Added to the Home Screen on iPhone, Safari has a long-standing bug where the
   microphone works on the first launch and then fails when the app is reopened.
   Nothing in the page can fix it, so when the conditions match, the failure is
   named and a way round it offered rather than left looking like a broken app. */
function isIosStandalone() {
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  return ios && window.navigator.standalone === true;
}

function microphoneProblem(error) {
  if (isIosStandalone()) {
    return 'On iPhone, recording often stops working once this app has been reopened '
      + 'from the Home Screen — a long-standing Safari bug, not a fault here. '
      + 'Open the same address in Safari itself to record, or close the app fully '
      + 'and open it again. Translating, reading pictures and Say it are unaffected.';
  }
  switch (error?.name) {
    case 'NotAllowedError':
      return 'Microphone access is blocked for this app. Allow it in your browser or phone settings — '
        + 'granting it once elsewhere is not enough — then try again.';
    case 'NotFoundError': case 'OverconstrainedError':
      return 'No usable microphone was found on this device.';
    case 'NotReadableError':
      return 'The microphone could not be opened. It was tried twice, including with plain settings. '
        + 'Close anything else that records — a call, an assistant, a recorder, another browser tab — '
        + 'or restart the phone, which clears a stuck audio service.';
    case 'SecurityError':
      return 'Recording is blocked on this connection. It needs a secure https address.';
    case 'AbortError':
      return 'The microphone stopped unexpectedly. Try again.';
    default:
      return `The microphone could not start (${error?.name || 'unknown error'}).`;
  }
}

/** Open the microphone, working around two common Android refusals.
 *
 *  A stream still held from an earlier attempt makes Android refuse the next
 *  one with NotReadableError, which reads as "another app is using it" when the
 *  culprit is this page. And several devices reject the tuned constraints and
 *  report THAT as NotReadableError too, rather than as a constraint error, so a
 *  plain request is tried before giving up.
 */
async function openMicrophone() {
  const attempts = [
    { audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } },
    { audio: true },
  ];
  let failure;
  for (const constraints of attempts) {
    try {
      return await navigator.mediaDevices.getUserMedia(constraints);
    } catch (error) {
      failure = error;
      // Permission and security refusals will not change on a retry.
      if (error?.name === 'NotAllowedError' || error?.name === 'SecurityError') break;
      $('speechStatus').textContent = 'The microphone refused those settings. Trying a simpler request…';
      await new Promise(resolve => setTimeout(resolve, 400));
    }
  }
  throw failure;
}

$('recordToggle').addEventListener('click', async () => {
  if (captureStarting || transcribing || nativeRecording) return;
  if (capture) { await finishRecording(); return; }
  if (!ready.transcribe) return;
  if (!$('speechConsent').checked) { $('speechStatus').textContent = 'Confirm paid API use before recording.'; return; }

  if (window.LFNativeCloudRecording === true) {
    const id = crypto.randomUUID();
    nativeRecording = { id, epoch };
    $('speechStatus').textContent = 'Use the phone recording dialog. Cancel discards the audio.';
    window.location.href = `linguafusion-record://capture?id=${id}`;
    return;
  }

  if (!navigator.mediaDevices?.getUserMedia) {
    $('speechStatus').textContent = 'This browser cannot record audio. It needs a secure https address '
      + 'and a recent browser; an old Android WebView will not work.';
    return;
  }
  let stream;
  let context;
  stopCapture();
  const generation = captureGeneration;
  captureStarting = true;
  try {
    stream = await openMicrophone();
  } catch (error) {
    if (generation === captureGeneration) $('speechStatus').textContent = microphoneProblem(error);
    captureStarting = false;
    return;
  }
  if (generation !== captureGeneration) {
    for (const track of stream.getTracks()) track.stop();
    captureStarting = false;
    return;
  }
  try {
    context = new (window.AudioContext || window.webkitAudioContext)();
    // Android creates contexts suspended. Without this the graph is connected
    // and the microphone is live, but onaudioprocess never fires and the
    // recording silently stays empty.
    if (context.state === 'suspended') await context.resume();
    if (generation !== captureGeneration) {
      for (const track of stream.getTracks()) track.stop();
      await context.close();
      return;
    }
    const source = context.createMediaStreamSource(stream);
    // ScriptProcessor is deprecated but is the only node available across every
    // browser this targets, including older Android WebViews.
    const processor = context.createScriptProcessor(4096, 1, 1);
    const chunks = [];
    let frames = 0;
    processor.onaudioprocess = event => {
      const input = event.inputBuffer.getChannelData(0);
      const remaining = Math.max(0, Math.floor(MAX_SECONDS * context.sampleRate) - frames);
      const chunk = Float32Array.from(input.subarray(0, remaining));
      chunks.push(chunk);
      frames += chunk.length;
      const seconds = frames / context.sampleRate;
      $('speechStatus').textContent = `Recording… ${seconds.toFixed(0)}s of ${MAX_SECONDS}s`;
      if (seconds >= MAX_SECONDS) void finishRecording();
    };
    source.connect(processor);
    // Route into a muted gain node: some browsers never fire the callback for a
    // processor with no destination, and connecting to the speakers would echo.
    const silent = context.createGain();
    silent.gain.value = 0;
    processor.connect(silent);
    silent.connect(context.destination);
    capture = { stream, context, source, processor, chunks };
    $('recordToggle').textContent = 'Stop and transcribe';
    $('speechStatus').textContent = 'Recording…';
  } catch (error) {
    // The microphone opened but the audio graph did not. Release it rather than
    // leaving the recording indicator lit with nothing listening.
    for (const track of stream.getTracks()) track.stop();
    if (context) void context.close().catch(() => {});
    $('speechStatus').textContent = `Recording could not start on this device (${error?.name || 'unknown error'}). `
      + 'Opening the website in Chrome usually works.';
  } finally { captureStarting = false; }
});

window.addEventListener('lf-native-recording', async event => {
  const pending = nativeRecording;
  if (!pending || pending.id !== event.detail?.id || pending.epoch !== epoch) return;
  nativeRecording = null;
  const { kind, data } = event.detail;
  if (kind === 'cancel') { $('speechStatus').textContent = 'Recording cancelled.'; return; }
  if (kind !== 'audio') { $('speechStatus').textContent = String(data || 'Recording failed.'); return; }
  try {
    if (typeof data !== 'string' || data.length > 2_600_100) throw new Error('Recording is too large.');
    const bytes = Uint8Array.from(atob(data), char => char.charCodeAt(0));
    await transcribeRecording(bytes);
  } catch { $('speechStatus').textContent = 'Could not read the phone recording. Please try again.'; }
});
window.addEventListener('pagehide', stopCapture);
document.addEventListener('visibilitychange', () => {
  // Native permission/dialog lifecycle is managed by Android itself.
  if (document.hidden && !nativeRecording) stopCapture();
});

async function finishRecording() {
  if (!capture) return;
  const { chunks, context } = capture;
  const rate = context.sampleRate;
  const merged = new Float32Array(chunks.reduce((total, chunk) => total + chunk.length, 0));
  let offset = 0;
  for (const chunk of chunks) { merged.set(chunk, offset); offset += chunk.length; }
  stopCapture();
  if (!merged.length) { $('speechStatus').textContent = 'Nothing was recorded.'; return; }

  let audio;
  try { audio = buildWav([merged], rate); }
  catch (error) { $('speechStatus').textContent = error.message; return; }

  await transcribeRecording(audio);
}

async function transcribeRecording(audio) {
  if (transcribing || !ready.transcribe || !$('speechConsent').checked) return;
  const current = epoch;
  transcribing = true;

  $('speechStatus').textContent = 'Transcribing…';
  $('transcript').textContent = '';
  const body = new FormData();
  body.set('audio', new Blob([audio], { type: 'audio/wav' }), 'recording.wav');
  body.set('paid_consent', String($('speechConsent').checked));
  try {
    const result = await api.request('/api/transcribe', body);
    if (current !== epoch) return;
    // Empty text is a legitimate result for silence, never "corrected".
    $('transcript').textContent = result.text || '';
    $('speechStatus').textContent = result.text ? 'Done.' : 'No speech was detected in that recording.';
    if (result.spending) showSpending(result.spending);
  } catch (error) { if (current === epoch) $('speechStatus').textContent = error.message; }
  finally { transcribing = false; }
}

// --- picture reading ---------------------------------------------------------

$('copyOcr').addEventListener('click', () => void copyText($('ocrResult').textContent, 'Text', $('ocrStatus')));

$('runOcr').addEventListener('click', async () => {
  if (!ready.ocr) return;
  const file = $('ocrFile').files?.[0];
  if (!file) { $('ocrStatus').textContent = 'Choose a picture first.'; return; }
  if (!['image/png', 'image/jpeg'].includes(file.type)) { $('ocrStatus').textContent = 'Use a PNG or JPEG image.'; return; }
  if (file.size > 4_000_000) { $('ocrStatus').textContent = 'That image is larger than 4 MB.'; return; }
  if (!$('ocrConsent').checked) { $('ocrStatus').textContent = 'Confirm paid API use first.'; return; }
  const current = epoch;
  $('runOcr').disabled = true;
  $('ocrStatus').textContent = 'Reading…';
  $('ocrResult').textContent = '';
  const body = new FormData();
  body.set('image', file, file.name || 'image');
  body.set('paid_consent', String($('ocrConsent').checked));
  try {
    const result = await api.request('/api/ocr', body);
    if (current !== epoch) return;
    $('ocrResult').textContent = result.text || '';
    const layout = result.layout || {};
    // Offer CSV only when columns were actually detected: a CSV of prose is one
    // quoted cell per line, which is worse than the text.
    fillFormats($('ocrFormat'), layout.looks_tabular ? ['csv', 'txt', 'md'] : ['txt', 'md']);
    $('ocrLayoutNote').textContent = !layout.preserved ? ''
      : layout.looks_tabular
        ? `Columns kept as they appeared (${layout.columns} across, ${layout.lines} lines). Download as .csv for a spreadsheet.`
        : `Line breaks kept as they appeared (${layout.lines} lines).`;
    $('ocrStatus').textContent = result.text ? 'Done.' : 'No text was found in that picture.';
    if (result.spending) showSpending(result.spending);
  } catch (error) { if (current === epoch) $('ocrStatus').textContent = error.message; }
  finally { if (current === epoch) $('runOcr').disabled = false; }
});


// --- export -----------------------------------------------------------------

const NEWLINE = String.fromCharCode(10);
const TAB = String.fromCharCode(9);
const CRLF = String.fromCharCode(13, 10);

const FORMATS = {
  txt: { label: 'Plain text (.txt)', mime: 'text/plain' },
  md: { label: 'Markdown (.md)', mime: 'text/markdown' },
  csv: { label: 'Table (.csv)', mime: 'text/csv' },
};

function fillFormats(select, formats) {
  select.replaceChildren();
  for (const key of formats) select.add(new Option(FORMATS[key].label, key));
}

/** Tab-separated OCR columns become real CSV cells, quoted properly. */
function toCsv(text) {
  return text.split(NEWLINE).map(row => row.split(TAB)
    .map(cell => `"${cell.replace(/"/g, '""')}"`).join(',')).join(CRLF);
}

function asMarkdown(title, text) {
  return '# ' + title + NEWLINE + NEWLINE + text + NEWLINE;
}

function isWebView() {
  return / wv[;)]/.test(navigator.userAgent);
}

function download(name, format, title, text) {
  if (!text || !text.trim()) { status('There is nothing to download yet.'); return; }
  const body = format === 'csv' ? toCsv(text) : format === 'md' ? asMarkdown(title, text) : text;
  const filename = `${name}.${format}`;
  try {
    const link = document.createElement('a');
    link.download = filename;
    if (isWebView()) {
      // Android WebView never fires its download listener for blob: URLs, so a
      // data: URL is used there instead; the wrapper decodes and saves it.
      link.href = `data:${FORMATS[format].mime};charset=utf-8;base64,`
        + btoa(String.fromCharCode(...new TextEncoder().encode(body)));
    } else {
      link.href = URL.createObjectURL(new Blob([body], { type: `${FORMATS[format].mime};charset=utf-8` }));
    }
    document.body.append(link);
    link.click();
    link.remove();
    if (link.href.startsWith('blob:')) setTimeout(() => URL.revokeObjectURL(link.href), 10000);
    status(`Saved ${filename}.`);
  } catch {
    status('This device would not save the file. Copy the text instead.');
  }
}

// --- moving text between views ----------------------------------------------

const PRONOUNCEABLE = new Set(['hi', 'ar', 'or']);

function sendToTranslate(text) {
  if (!text || !text.trim()) { status('There is nothing to send yet.'); return; }
  if (!ready.translate) { status('Translation is not switched on for this account.'); return; }
  $('text').value = text.slice(0, translationLimit);
  updateTextCount();
  showView('viewTranslate');
  status(text.length > translationLimit
    ? `Sent the first ${translationLimit} characters; the rest did not fit.`
    : 'Sent to Translate. Confirm paid use, then translate.');
}

function sendToPronounce(text, language) {
  if (!text || !text.trim()) { status('There is nothing to send yet.'); return; }
  if (!ready.pronounce) { status('Pronunciation is not switched on for this account.'); return; }
  $('pronounceText').value = text.slice(0, pronunciationLimit);
  if (language && PRONOUNCEABLE.has(language)) $('pronounceLanguage').value = language;
  showView('viewSay');
  status('Sent to Say it. Choose the language, confirm paid use, then continue.');
}

function updateTextCount() {
  const used = $('text').value.length;
  const left = translationLimit - used;
  $('textCount').textContent = left <= 0
    ? `Character limit reached (${translationLimit}). Anything beyond this will not be translated — split the text and run it twice.`
    : `${used} of ${translationLimit} characters. Text leaves your device when you select Translate.`;
  $('textCount').classList.toggle('warn', left <= 0);
}
$('text').addEventListener('input', updateTextCount);

$('transcriptToTranslate').addEventListener('click', () => sendToTranslate($('transcript').textContent));
$('ocrToTranslate').addEventListener('click', () => sendToTranslate($('ocrResult').textContent));
$('ocrToSay').addEventListener('click', () => sendToPronounce($('ocrResult').textContent));
$('translationToSay').addEventListener('click', () => sendToPronounce($('result').textContent, $('target').value));
$('copyTranslation').addEventListener('click', () => void copyText($('result').textContent, 'Translation', $('status')));

$('downloadTranscript').addEventListener('click',
  () => download('transcript', $('transcriptFormat').value, 'Transcript', $('transcript').textContent));
$('downloadTranslation').addEventListener('click',
  () => download('translation', $('translationFormat').value, 'Translation', $('result').textContent));
$('downloadOcr').addEventListener('click',
  () => download('page-text', $('ocrFormat').value, 'Text from a picture', $('ocrResult').textContent));
$('downloadPronounce').addEventListener('click', () => download(
  'pronunciation', $('pronounceFormat').value, 'Pronunciation',
  $('pronounceNative').textContent + NEWLINE + NEWLINE + $('pronounceRoman').textContent));

fillFormats($('transcriptFormat'), ['txt', 'md']);
fillFormats($('translationFormat'), ['txt', 'md']);
fillFormats($('ocrFormat'), ['txt', 'md']);
fillFormats($('pronounceFormat'), ['txt', 'md']);

// Online-interface updates use public release metadata, never a paid API.
$('appVersion').textContent = APP_VERSION;
let offeredUpdate = null;
let updateBusy = false;
// The app answers its own check here. Only it knows whether the installed
// build is current, so the page waits to be told rather than claiming.
let interfaceUpToDate = true;
let awaitingApp = null;

/* Older builds intercept the check but cannot report back -- reporting only
   arrived in 1.12. Waiting for an answer they will never send left the status
   stuck on "Checking the app" forever, which is worse than not asking. So the
   wait is bounded, and the fallback says what is actually known rather than
   guessing a verdict. */
function stopAwaitingApp() {
  if (awaitingApp === null) return false;
  clearTimeout(awaitingApp);
  awaitingApp = null;
  return true;
}

function awaitAppAnswer() {
  stopAwaitingApp();
  awaitingApp = setTimeout(() => {
    awaitingApp = null;
    $('updateStatus').textContent =
      `Interface ${APP_VERSION} is current. This app build cannot report on `
      + 'itself, so if no update box appeared there is nothing waiting.';
  }, 6000);
}

window.LFNativeUpdateResult = (json) => {
  stopAwaitingApp();
  let answer;
  try { answer = JSON.parse(json); } catch { return; }
  if (answer.available) {
    // The app raises its own dialog; this is for anyone who dismisses it.
    $('updateStatus').textContent =
      `A new app version is available: ${answer.versionName} (${answer.megabytes} MB). `
      + 'Nothing installs until you confirm.';
    return;
  }
  $('updateStatus').textContent = interfaceUpToDate
    ? `You’re up to date. Interface ${APP_VERSION}, app ${window.LFNativeAppVersion || 'installed'}.`
    : $('updateStatus').textContent;
};

$('checkUpdates').addEventListener('click', async () => {
  if (updateBusy) return;
  updateBusy = true;
  $('checkUpdates').disabled = true;
  $('updateOffer').hidden = true;
  offeredUpdate = null;
  $('updateStatus').textContent = 'Checking for updates…';
  // Inside the app there are two things that can be out of date: this
  // interface, and the installed app carrying the offline engines. One button
  // asks about both. The app answers in its own dialog, and only when asked --
  // it never interrupts on launch.
  if (window.LFNativeOfflineMode === true) {
    awaitAppAnswer();
    window.location.assign('linguafusion-update://check');
  }
  try {
    const result = await checkForUpdate();
    offeredUpdate = result.available ? result : null;
    $('updateOffer').hidden = !result.available;
    // Scope it. This checked the interface; inside the app the installed app
    // is checked separately and answers through LFNativeUpdateResult below.
    interfaceUpToDate = !result.available;
    $('updateStatus').textContent = result.available
      ? `A new interface is available: version ${result.version}.`
      : (window.LFNativeOfflineMode === true
          ? `Interface ${APP_VERSION} is current. Checking the app…`
          : `You’re up to date. Version ${APP_VERSION}.`);
  } catch {
    stopAwaitingApp();
    $('updateStatus').textContent = 'Could not check for updates. Check your internet connection and try again.';
  } finally { updateBusy = false; $('checkUpdates').disabled = false; }
});
function updateActivityInProgress() {
  return capture || captureStarting || nativeRecording || transcribing || translating || pronouncing || submitting || $('runOcr').disabled;
}
$('applyUpdate').addEventListener('click', async () => {
  if (updateBusy || !offeredUpdate) return;
  if (updateActivityInProgress()) {
    $('updateStatus').textContent = 'Finish the current recording or processing before updating.';
    return;
  }
  updateBusy = true;
  $('applyUpdate').disabled = true;
  $('checkUpdates').disabled = true;
  $('updateStatus').textContent = 'Preparing the update…';
  try {
    await activateUpdate();
    if (updateActivityInProgress()) {
      $('updateStatus').textContent = 'Finish the current recording or processing before updating.';
      updateBusy = false;
      $('applyUpdate').disabled = false;
      $('checkUpdates').disabled = false;
      return;
    }
    window.location.reload();
  } catch {
    $('updateStatus').textContent = 'The update could not be prepared. Your work is still here. Try again.';
    updateBusy = false;
    $('applyUpdate').disabled = false;
    $('checkUpdates').disabled = false;
  }
});

// --- Android offer and offline shell -----------------------------------------

function isInstalled() {
  return window.matchMedia?.('(display-mode: standalone)').matches === true
    || window.navigator.standalone === true
    || / wv[;)]/.test(navigator.userAgent);   // Android WebView: already the app.
}

void (async () => {
  if (isInstalled()) return;
  try {
    const response = await fetch('/pilot/android-app.json', { cache: 'no-store' });
    if (!response.ok) return;
    const details = await response.json();
    if (!/^[a-f0-9]{64}$/.test(details.sha256 || '')) return;
    $('androidFingerprint').textContent = `SHA-256 ${details.sha256}`;
    $('androidDownload').textContent = `Download for Android (${Math.round((details.bytes || 0) / 1024)} KB)`;
    if (!signedIn) $('androidOffer').hidden = false;
  } catch { /* No Android build published; the website is the whole product. */ }
})();

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/pilot/sw.js', { scope: '/pilot/' }).catch(() => {});
  });
}

void setup();
