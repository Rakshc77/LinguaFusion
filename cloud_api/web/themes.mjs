/* Appearance and typography for the cloud app.

   The look and font lists are copied from backend/mobile_web so the cloud app
   offers the SAME named looks as the phone client. Keep them in step if that
   registry changes. Only the mobile looks are offered here: the nine PC looks
   belong to the PySide desktop app.

   Look and font are deliberately independent, and each is remembered
   separately, matching how the rest of LinguaFusion behaves.
*/

export const LF_THEMES = [
  // 9 Mobile / Phone looks
  { id:"soft-ui", name:"Soft UI", group:"Light", platforms:["mobile"], dark:false },
  { id:"sunset", name:"Sunset", group:"Playful", platforms:["mobile"], dark:false },
  { id:"brutalist", name:"Neo-Brutalist", group:"Playful", platforms:["mobile"], dark:false },
  { id:"warm-editorial", name:"Warm Editorial", group:"Editorial", platforms:["mobile"], dark:false },
  { id:"glass-dark", name:"Glass Dark", group:"Dark", platforms:["mobile"], dark:true },
  { id:"neon-arcade", name:"Neon Arcade", group:"Playful", platforms:["mobile"], dark:true },
  { id:"warm-minimal", name:"Warm Minimal", group:"Editorial", platforms:["mobile"], dark:false },
  { id:"bold-mono", name:"Bold Mono", group:"Playful", platforms:["mobile"], dark:false },
  { id:"nature-calm", name:"Nature Calm", group:"Light", platforms:["mobile"], dark:false },

  // 9 PC looks
  { id:"broadsheet", name:"Broadsheet", group:"Editorial", platforms:["pc"], dark:false },
  { id:"editorial-split", name:"Editorial Split", group:"Editorial", platforms:["pc"], dark:false },
  { id:"reading-room", name:"Reading Room", group:"Editorial", platforms:["pc"], dark:false },
  { id:"gallery", name:"Gallery", group:"Editorial", platforms:["pc"], dark:true },
  { id:"editorial-luxe", name:"Editorial Luxe", group:"Editorial", platforms:["pc"], dark:false },
  { id:"glass-dark", name:"Glass Dark", group:"Dark", platforms:["pc"], dark:true },
  { id:"aurora-glass", name:"Aurora Glass", group:"Dark", platforms:["pc"], dark:true },
  { id:"blueprint", name:"Technical Blueprint", group:"Utility", platforms:["pc"], dark:true },
  { id:"zen", name:"Zen Focus", group:"Dark", platforms:["pc"], dark:true },
];

export const LF_FONTS = [
  { id:"modern", name:"Modern Sans", group:"Sans" },
  { id:"friendly", name:"Friendly Rounded", group:"Sans" },
  { id:"accessible", name:"Accessibility Sans", group:"Sans" },
  { id:"editorial", name:"Editorial Serif", group:"Serif" },
  { id:"classic", name:"Classic Serif", group:"Serif" },
  { id:"technical", name:"Technical Mono", group:"Monospace" },
];

export const CLOUD_THEMES = LF_THEMES.filter(theme => theme.platforms.includes('mobile'));

const THEME_KEY = 'lf-theme';
const FONT_KEY = 'lf-font';
const DEFAULT_THEME = 'soft-ui';
const DEFAULT_FONT = 'modern';

function stored(key) {
  // Private windows and blocked site data make this throw, not return null.
  try { return localStorage.getItem(key) || ''; } catch { return ''; }
}

function persist(key, value) {
  try { localStorage.setItem(key, value); } catch { /* nothing to remember with */ }
}

export function getTheme() {
  const saved = stored(THEME_KEY);
  return CLOUD_THEMES.some(theme => theme.id === saved) ? saved : DEFAULT_THEME;
}

export function getFont() {
  const saved = stored(FONT_KEY);
  return LF_FONTS.some(font => font.id === saved) ? saved : DEFAULT_FONT;
}

export function applyTheme(id) {
  const theme = CLOUD_THEMES.find(entry => entry.id === id) || CLOUD_THEMES.find(entry => entry.id === DEFAULT_THEME);
  document.documentElement.dataset.theme = theme.id;
  document.documentElement.style.colorScheme = theme.dark ? 'dark' : 'light';
  persist(THEME_KEY, theme.id);
  return theme.id;
}

export function applyFont(id) {
  const font = LF_FONTS.find(entry => entry.id === id) || LF_FONTS.find(entry => entry.id === DEFAULT_FONT);
  document.documentElement.dataset.font = font.id;
  persist(FONT_KEY, font.id);
  return font.id;
}

/** Apply what was chosen last time, before first paint where possible. */
export function initAppearance() {
  return { theme: applyTheme(getTheme()), font: applyFont(getFont()) };
}
