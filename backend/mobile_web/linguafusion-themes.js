/* LinguaFusion appearance + typography registry.
   Look and font are intentionally independent. The PWA/native phone clients
   offer the seven phone looks; the PySide desktop app owns the nine PC looks. */

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

export const LF_THEMES_MOBILE = LF_THEMES.filter(theme => theme.platforms.includes("mobile"));
export const LF_THEMES_PC = LF_THEMES.filter(theme => theme.platforms.includes("pc"));

const THEME_STORAGE_KEY = "lf-theme";
const FONT_STORAGE_KEY = "lf-font";
const DEFAULT_THEMES = { mobile:"soft-ui", pc:"broadsheet", all:"broadsheet" };
const DEFAULT_FONT = "modern";

export function themesFor(platform) {
  return platform ? LF_THEMES.filter(theme => theme.platforms.includes(platform)) : LF_THEMES;
}

function storedValue(key) {
  try { return localStorage.getItem(key) || ""; }
  catch (_) { return ""; }
}

function persistValue(key, value) {
  try { localStorage.setItem(key, value); }
  catch (_) {}
}

export function getTheme(platform) {
  const list = themesFor(platform);
  const saved = storedValue(THEME_STORAGE_KEY);
  if (list.some(theme => theme.id === saved)) return saved;
  return DEFAULT_THEMES[platform || "all"] || DEFAULT_THEMES.all;
}

export function applyTheme(id, { platform } = {}) {
  const list = themesFor(platform);
  const fallback = DEFAULT_THEMES[platform || "all"] || DEFAULT_THEMES.all;
  const selected = list.find(theme => theme.id === id) || list.find(theme => theme.id === fallback) || list[0];
  const theme = selected || LF_THEMES[0];
  document.documentElement.dataset.theme = theme.id;
  const modeOverride = storedValue("lf-mode-override");
  const isDark = modeOverride ? (modeOverride === "dark") : theme.dark;
  document.documentElement.dataset.mode = isDark ? "dark" : "light";
  document.documentElement.style.colorScheme = isDark ? "dark" : "light";
  persistValue(THEME_STORAGE_KEY, theme.id);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = isDark ? "#070d18" : "#f5f7fb";
  try {
    window.LinguaFusionNative?.setSystemBarTheme?.(isDark);
  } catch {
    // The browser PWA and iOS wrapper do not expose the Android bridge.
  }
  document.dispatchEvent(new CustomEvent("lf-theme-change", { detail:{ id:theme.id, dark:isDark } }));
  return theme.id;
}

export function toggleMode() {
  const currentMode = document.documentElement.dataset.mode || "light";
  const newMode = currentMode === "dark" ? "light" : "dark";
  document.documentElement.dataset.mode = newMode;
  document.documentElement.style.colorScheme = newMode;
  persistValue("lf-mode-override", newMode);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = newMode === "dark" ? "#070d18" : "#f5f7fb";
  try {
    window.LinguaFusionNative?.setSystemBarTheme?.(newMode === "dark");
  } catch {}
  document.dispatchEvent(new CustomEvent("lf-mode-change", { detail:{ mode:newMode } }));
  return newMode;
}

export function initTheme(options = {}) {
  return applyTheme(getTheme(options.platform), options);
}

export function getFont() {
  const saved = storedValue(FONT_STORAGE_KEY);
  return LF_FONTS.some(font => font.id === saved) ? saved : DEFAULT_FONT;
}

export function applyFont(id) {
  const font = LF_FONTS.find(item => item.id === id) || LF_FONTS.find(item => item.id === DEFAULT_FONT);
  document.documentElement.dataset.font = font.id;
  persistValue(FONT_STORAGE_KEY, font.id);
  document.dispatchEvent(new CustomEvent("lf-font-change", { detail:{ id:font.id } }));
  return font.id;
}

export function initFont() {
  return applyFont(getFont());
}

function fillGroupedSelect(select, items) {
  select.innerHTML = "";
  const groups = {};
  items.forEach(item => (groups[item.group] ||= []).push(item));
  Object.entries(groups).forEach(([group, groupItems]) => {
    const optionGroup = document.createElement("optgroup");
    optionGroup.label = group;
    groupItems.forEach(item => {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = item.name;
      optionGroup.appendChild(option);
    });
    select.appendChild(optionGroup);
  });
  return select;
}

export function populateThemeSelect(select, { platform } = {}) {
  fillGroupedSelect(select, themesFor(platform));
  select.value = getTheme(platform);
  return select;
}

export function populateFontSelect(select) {
  fillGroupedSelect(select, LF_FONTS);
  select.value = getFont();
  return select;
}

export function picker(mountEl, { platform } = {}) {
  const select = populateThemeSelect(document.createElement("select"), { platform });
  select.addEventListener("change", () => applyTheme(select.value, { platform }));
  mountEl.appendChild(select);
  return select;
}

if (typeof window !== "undefined") {
  window.LinguaFusionThemes = {
    LF_THEMES, LF_THEMES_MOBILE, LF_THEMES_PC, LF_FONTS, themesFor,
    applyTheme, getTheme, initTheme, applyFont, getFont, initFont,
    populateThemeSelect, populateFontSelect, picker,
  };
}
