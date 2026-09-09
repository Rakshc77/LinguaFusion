/* Appearance and typography for the cloud app.

   Two looks, each with a day and a night mode. Look, mode and typeface are
   three independent choices, each remembered separately on this device —
   which is how the rest of LinguaFusion behaves, and it means picking a look
   never silently changes someone's brightness or their font.

   The shared theme sheet still defines the older phone and PC looks, because
   the PySide desktop app and the phone client read the same file. They are
   deliberately not listed here: this client offers what it has designed and
   checked, and nothing else.
*/

export const CLOUD_THEMES = [
  { id: 'studio', name: 'Studio',
    blurb: 'Parchment and terracotta by day, sunset rose and plum at night.' },
  { id: 'minimal', name: 'Minimal',
    blurb: 'Monochrome, in both modes.' },
];

export const LF_MODES = [
  { id: 'light', name: 'Day' },
  { id: 'dark', name: 'Night' },
];

export const LF_FONTS = [
  { id:"modern", name:"Modern Sans", group:"Sans" },
  { id:"friendly", name:"Friendly Rounded", group:"Sans" },
  { id:"accessible", name:"Accessibility Sans", group:"Sans" },
  { id:"editorial", name:"Editorial Serif", group:"Serif" },
  { id:"classic", name:"Classic Serif", group:"Serif" },
  { id:"technical", name:"Technical Mono", group:"Monospace" },
];

const THEME_KEY = 'lf-theme';
const MODE_KEY = 'lf-mode';
const FONT_KEY = 'lf-font';
const DEFAULT_THEME = 'studio';
const DEFAULT_FONT = 'modern';

function stored(key) {
  // Private windows and blocked site data make this throw, not return null.
  try { return localStorage.getItem(key) || ''; } catch { return ''; }
}

function persist(key, value) {
  try { localStorage.setItem(key, value); } catch { /* nothing to remember with */ }
}

/** What the device itself prefers, used until someone chooses for themselves. */
function deviceMode() {
  try {
    return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  } catch { return 'light'; }
}

export function getTheme() {
  const saved = stored(THEME_KEY);
  return CLOUD_THEMES.some(theme => theme.id === saved) ? saved : DEFAULT_THEME;
}

export function getMode() {
  const saved = stored(MODE_KEY);
  return LF_MODES.some(mode => mode.id === saved) ? saved : deviceMode();
}

export function getFont() {
  const saved = stored(FONT_KEY);
  return LF_FONTS.some(font => font.id === saved) ? saved : DEFAULT_FONT;
}

export function applyTheme(id) {
  const theme = CLOUD_THEMES.find(entry => entry.id === id)
    || CLOUD_THEMES.find(entry => entry.id === DEFAULT_THEME);
  document.documentElement.dataset.theme = theme.id;
  persist(THEME_KEY, theme.id);
  return theme.id;
}

export function applyMode(id) {
  const mode = LF_MODES.find(entry => entry.id === id) ? id : deviceMode();
  document.documentElement.dataset.mode = mode;
  // Tell the browser too, so its own form controls, scrollbars and any
  // built-in UI match the mode the person picked rather than the device's.
  document.documentElement.style.colorScheme = mode;
  persist(MODE_KEY, mode);
  return mode;
}

export function applyFont(id) {
  const font = LF_FONTS.find(entry => entry.id === id) || LF_FONTS.find(entry => entry.id === DEFAULT_FONT);
  document.documentElement.dataset.font = font.id;
  persist(FONT_KEY, font.id);
  return font.id;
}

/** Apply what was chosen last time, before first paint where possible. */
export function initAppearance() {
  return {
    theme: applyTheme(getTheme()),
    mode: applyMode(getMode()),
    font: applyFont(getFont()),
  };
}
