/* Cloud and Android appearance: two looks, independent mode and typeface. */
export const CLOUD_THEMES = [
  { id:"studio", name:"Studio" },
  { id:"minimal", name:"Minimal" },
];
export const LF_THEMES = CLOUD_THEMES;
export const LF_FONTS = [
  { id:"modern", name:"Modern Sans", group:"Sans" },
  { id:"friendly", name:"Friendly Rounded", group:"Sans" },
  { id:"accessible", name:"Accessibility Sans", group:"Sans" },
  { id:"editorial", name:"Editorial Serif", group:"Serif" },
  { id:"classic", name:"Classic Serif", group:"Serif" },
  { id:"technical", name:"Technical Mono", group:"Monospace" },
];


const THEME_KEY = 'lf-theme';
const FONT_KEY = 'lf-font';
const MODE_KEY = 'lf-mode';
const LEGACY_DARK = ['glass-dark', 'neon-arcade', 'aurora-glass', 'gallery', 'zen', 'blueprint'];
function stored(key) {
  try { return localStorage.getItem(key) || ''; } catch { return ''; }
}
function persist(key, value) {
  try { localStorage.setItem(key, value); } catch { /* session-only appearance */ }
}
export function getTheme() {
  const saved = stored(THEME_KEY);
  if (CLOUD_THEMES.some(theme => theme.id === saved)) return saved;
  return ['warm-minimal', 'bold-mono', 'zen'].includes(saved) ? 'minimal' : 'studio';
}
export function getMode() {
  const saved = stored(MODE_KEY);
  if (['light', 'dark'].includes(saved)) return saved;
  const current = document.documentElement.dataset.mode;
  if (['light', 'dark'].includes(current)) return current;
  // Preserve the old selected look's brightness during migration.
  return LEGACY_DARK.includes(stored(THEME_KEY)) ? 'dark' : 'light';
}
export function getFont() {
  const saved = stored(FONT_KEY);
  return LF_FONTS.some(font => font.id === saved) ? saved : 'modern';
}
export function applyMode(mode) {
  const selected = mode === 'dark' ? 'dark' : 'light';
  document.documentElement.dataset.mode = selected;
  document.documentElement.style.colorScheme = selected;
  persist(MODE_KEY, selected);
  const minimal = document.documentElement.dataset.theme === 'minimal';
  const color = selected === 'dark' ? (minimal ? '#121212' : '#1a1015') : (minimal ? '#fafafa' : '#f4efe4');
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = color;
  return selected;
}
export function applyTheme(id) {
  const selected = CLOUD_THEMES.some(theme => theme.id === id) ? id : 'studio';
  const mode = getMode();
  document.documentElement.dataset.theme = selected;
  persist(THEME_KEY, selected);
  applyMode(mode);
  return selected;
}
export function applyFont(id) {
  const selected = LF_FONTS.some(font => font.id === id) ? id : 'modern';
  document.documentElement.dataset.font = selected;
  persist(FONT_KEY, selected);
  return selected;
}
export function initAppearance() {
  const mode = getMode();
  const theme = applyTheme(getTheme());
  return { theme, mode: applyMode(mode), font: applyFont(getFont()) };
}
