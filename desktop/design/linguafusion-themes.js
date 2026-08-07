/* ============================================================
   LinguaFusion — Theme registry + switcher
   Framework-agnostic. Works with plain JS, React, Electron,
   Tauri, or an Android WebView. No dependencies.

   USAGE
     import { LF_THEMES, applyTheme, initTheme } from './linguafusion-themes.js';
     initTheme();                 // restore saved theme on boot
     applyTheme('amber-studio');  // switch at runtime (persists)

   It sets  <html data-theme="…">  and remembers the choice in
   localStorage under "lf-theme".
   ============================================================ */

/* `platforms` lists where a theme is OFFERED. 'mobile' = Android phone;
   'pc' = desktop app + web. Every theme still WORKS everywhere — this
   only controls which set the Settings picker shows per build. */
export const LF_THEMES = [
  // id                name                     group        platforms        dark
  { id:'soft-ui',         name:'Soft UI',              group:'Light',     platforms:['mobile'],       dark:false },
  { id:'candy',           name:'Candy',                group:'Playful',   platforms:['mobile'],       dark:false },
  { id:'material',        name:'Material Expressive',  group:'Playful',   platforms:['mobile'],       dark:false },
  { id:'sunset',          name:'Sunset',               group:'Playful',   platforms:['mobile'],       dark:false },
  { id:'brutalist',       name:'Neo-Brutalist',        group:'Playful',   platforms:['mobile'],       dark:false },
  { id:'warm-editorial',  name:'Warm Editorial',       group:'Editorial', platforms:['mobile'],       dark:false },
  { id:'glass-dark',      name:'Glass Dark',           group:'Dark',      platforms:['mobile'],       dark:true  },

  { id:'focus-light',     name:'Focus Light',          group:'Light',     platforms:['pc'],           dark:false },
  { id:'frosted-native',  name:'Frosted Native',       group:'Light',     platforms:['pc'],           dark:false },
  { id:'swiss',           name:'Swiss',                group:'Editorial', platforms:['pc'],           dark:false },
  { id:'broadsheet',      name:'Broadsheet',           group:'Editorial', platforms:['pc'],           dark:false },
  { id:'editorial-split', name:'Editorial Split',      group:'Editorial', platforms:['pc'],           dark:false },
  { id:'glass-aurora',    name:'Glass Aurora',         group:'Dark',      platforms:['pc'],           dark:true  },
  { id:'amber-studio',    name:'Amber Studio',         group:'Dark',      platforms:['pc'],           dark:true  },
  { id:'terminal',        name:'Local-first Terminal', group:'Dark',      platforms:['pc'],           dark:true  },
  { id:'zen',             name:'Zen Focus',            group:'Dark',      platforms:['pc'],           dark:true  },
];

/* Convenience subsets */
export const LF_THEMES_MOBILE = LF_THEMES.filter(t => t.platforms.includes('mobile'));
export const LF_THEMES_PC     = LF_THEMES.filter(t => t.platforms.includes('pc'));
export function themesFor(platform) {
  return platform ? LF_THEMES.filter(t => t.platforms.includes(platform)) : LF_THEMES;
}

const STORAGE_KEY = 'lf-theme';
const DEFAULT_THEME = 'focus-light';

export function applyTheme(id) {
  const theme = LF_THEMES.find(t => t.id === id) ? id : DEFAULT_THEME;
  document.documentElement.setAttribute('data-theme', theme);
  document.documentElement.style.colorScheme =
    LF_THEMES.find(t => t.id === theme)?.dark ? 'dark' : 'light';
  try { localStorage.setItem(STORAGE_KEY, theme); } catch (_) {}
  document.dispatchEvent(new CustomEvent('lf-theme-change', { detail: { id: theme } }));
  return theme;
}

export function getTheme() {
  try { return localStorage.getItem(STORAGE_KEY) || DEFAULT_THEME; }
  catch (_) { return DEFAULT_THEME; }
}

export function initTheme() {
  return applyTheme(getTheme());
}

/* Optional: build a <select> theme picker for Settings > Appearance.
   picker(el)                    -> all 16 themes
   picker(el, { platform:'mobile' }) -> Mobile build set (7)
   picker(el, { platform:'pc' })     -> PC build set (9) */
export function picker(mountEl, { platform } = {}) {
  const list = themesFor(platform);
  const sel = document.createElement('select');
  const groups = {};
  list.forEach(t => (groups[t.group] ||= []).push(t));
  Object.entries(groups).forEach(([group, items]) => {
    const og = document.createElement('optgroup');
    og.label = group;
    items.forEach(t => {
      const o = document.createElement('option');
      o.value = t.id;
      o.textContent = t.name;
      og.appendChild(o);
    });
    sel.appendChild(og);
  });
  sel.value = list.find(t => t.id === getTheme()) ? getTheme() : list[0].id;
  sel.addEventListener('change', () => applyTheme(sel.value));
  mountEl.appendChild(sel);
  return sel;
}

/* CommonJS / global fallbacks for non-module environments */
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { LF_THEMES, LF_THEMES_MOBILE, LF_THEMES_PC, themesFor, applyTheme, getTheme, initTheme, picker };
}
if (typeof window !== 'undefined') {
  window.LinguaFusionThemes = { LF_THEMES, LF_THEMES_MOBILE, LF_THEMES_PC, themesFor, applyTheme, getTheme, initTheme, picker };
}
