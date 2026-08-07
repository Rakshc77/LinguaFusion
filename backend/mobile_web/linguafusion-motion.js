/* ============================================================
   LinguaFusion — Motion helpers
   Tiny, framework-agnostic re-trigger utilities for the classes
   in linguafusion-motion.css. CSS does the actual animating;
   these just (re)apply classes at the right moment and clean up.

     import * as M from './linguafusion-motion.js';
     M.enterScreen(speechEl);                 // route/tab change
     M.exitScreen(oldEl, () => oldEl.remove());
     M.importIn(dropCardEl);                   // file imported
     M.exportOut(rowEl, () => toast('Saved')); // export tapped
     M.revealResult(transcriptContainerEl);    // new lines arrived
     M.setRecording(recordBtnEl, true);        // start/stop mic
     M.setWaveLive(waveEl, true);              // animate bars
   ============================================================ */

const MOTION_STORAGE_KEY = "lf-motion";
const MOTION_MODES = new Set(["system", "full", "reduced", "off"]);

export function getMotionMode() {
  try {
    const saved = localStorage.getItem(MOTION_STORAGE_KEY);
    return MOTION_MODES.has(saved) ? saved : "system";
  } catch {
    return "system";
  }
}

export function applyMotionMode(mode) {
  const selected = MOTION_MODES.has(mode) ? mode : "system";
  document.documentElement.dataset.motion = selected;
  try {
    localStorage.setItem(MOTION_STORAGE_KEY, selected);
  } catch {
    // Storage can be unavailable in locked-down embedded browsers.
  }
  return selected;
}

export function initMotionMode() {
  return applyMotionMode(getMotionMode());
}

export function motionIsReduced() {
  const mode = document.documentElement.dataset.motion || getMotionMode();
  if (mode === "off" || mode === "reduced") return true;
  if (mode === "full") return false;
  return typeof matchMedia !== "undefined" &&
    matchMedia("(prefers-reduced-motion: reduce)").matches;
}

const REDUCED = () => motionIsReduced();

/* force the browser to restart a CSS animation by toggling the class */
function retrigger(el, cls) {
  if (!el) return;
  el.classList.remove(cls);
  void el.offsetWidth; // reflow
  el.classList.add(cls);
}

function once(el, cb) {
  if (!el || !cb) return;
  if (REDUCED()) { cb(); return; }
  const done = (e) => {
    if (e.target !== el) return;
    el.removeEventListener('animationend', done);
    cb();
  };
  el.addEventListener('animationend', done);
}

/* --- screen / route transitions --- */
export function enterScreen(el)         { retrigger(el, 'lf-screen-enter'); }
export function enterRail(el)           { retrigger(el, 'lf-screen-enter--rail'); }
export function exitScreen(el, cb)      { retrigger(el, 'lf-screen-exit'); once(el, cb); }

/* --- import / export --- */
export function importIn(el)            { retrigger(el, 'lf-import-enter'); }
export function exportOut(el, cb)       { retrigger(el, 'lf-export-exit'); once(el, cb); }

/* --- live transcription result ---
   Add the container once; call after appending new line nodes so the
   stagger replays across current children. */
export function revealResult(container) {
  if (!container) return;
  container.classList.add('lf-result');
  container.querySelectorAll(':scope > *').forEach((child) => {
    child.style.animation = 'none';
    void child.offsetWidth;
    child.style.animation = '';
  });
}

/* --- recording state on the mic button --- */
export function setRecording(btn, on) {
  if (!btn) return;
  btn.classList.toggle('lf-recording', !!on);
}

/* --- animate the waveform bars while capturing --- */
export function setWaveLive(waveEl, on) {
  if (!waveEl) return;
  waveEl.classList.toggle('is-live', !!on);
}

/* Build a waveform bar row that themes can style + animate.
   buildWave(el, 32) -> injects <span class="lf-wave-bar"> bars. */
export function buildWave(mountEl, count = 32) {
  if (!mountEl) return;
  mountEl.classList.add('lf-wave');
  const H = [7,13,20,10,27,15,33,22,9,18,29,12,24,11,31,16,8,21,28,14,10,23,19,12,26,9,15,30,13,7,17,25];
  mountEl.innerHTML = '';
  for (let i = 0; i < count; i++) {
    const b = document.createElement('span');
    b.className = 'lf-wave-bar';
    b.style.height = Math.max(3, H[i % H.length]) + 'px';
    mountEl.appendChild(b);
  }
}

if (typeof window !== 'undefined') {
  window.LinguaFusionMotion = {
    enterScreen, enterRail, exitScreen, importIn, exportOut,
    revealResult, setRecording, setWaveLive, buildWave,
    getMotionMode, applyMotionMode, initMotionMode, motionIsReduced,
  };
}
