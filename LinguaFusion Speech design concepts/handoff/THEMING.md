# LinguaFusion — Theming & Motion Framework

A drop-in system to build the 16 shortlisted looks into LinguaFusion as
switchable **themes**. It generalizes the existing *Settings → Appearance*
toggle (Focus Light "A" / Night Studio "C") into a registry of 16.

Everything is driven by **CSS custom properties** (`--lf-*`). Switch the whole
app by setting one attribute:

```html
<html data-theme="amber-studio">
```

No component rewrites required — you map the tokens onto the components you
already have, or adopt the optional `.lf-*` helper classes.

---

## Files

| File | What it is |
|------|-----------|
| `linguafusion-themes.css` | Token contract + 16 theme blocks + optional `.lf-*` helper classes. Imports the Google Fonts the themes use. |
| `linguafusion-structure.css` | **Per-theme layout** — grids, prompts, rails, columns, single-column focus. This is what makes each theme a distinct *design*, not just a palette. Must load **after** themes.css. |
| `linguafusion-motion.css` | Motion tokens per theme + keyframe library + utility classes (`.lf-screen-enter`, `.lf-import-enter`, `.lf-export-exit`, `.lf-result`, `.lf-recording`). Honors `prefers-reduced-motion`. |
| `linguafusion-themes.js` | `LF_THEMES` registry, `applyTheme()`, `initTheme()`, `getTheme()`, and a `picker()` builder for the Settings dropdown. Persists to `localStorage["lf-theme"]`. |
| `linguafusion-motion.js` | Re-trigger helpers: `enterScreen`, `exitScreen`, `importIn`, `exportOut`, `revealResult`, `setRecording`, `setWaveLive`, `buildWave`. |

---

## Integration (3 steps)

**1. Load the stylesheets + init the theme early** (before first paint, to avoid a flash). **Order matters** — structure must win over skin:

```html
<link rel="stylesheet" href="linguafusion-themes.css">
<link rel="stylesheet" href="linguafusion-structure.css">
<link rel="stylesheet" href="linguafusion-motion.css">
<script type="module">
  import { initTheme } from './linguafusion-themes.js';
  initTheme();               // restores the saved theme onto <html data-theme>
</script>
```

**2. Make components read tokens AND wear the structural hooks.**
- Add the **layout hook classes** to the Speech screen so `linguafusion-structure.css` can reshape it per theme: `lf-speech` (root), `lf-signature` (empty prompt/masthead slot), `lf-speech-head`, `lf-speech-controls`, `lf-recorder`, `lf-result`. Without these, structural themes fall back to color-only. Then either:
- **Adopt the helpers** — add `.lf-card`, `.lf-record`, `.lf-translation`, `.lf-badge`, `.lf-chip`, `.lf-label`, `.lf-heading`, `.lf-wave` to the relevant nodes (see reference markup below); or
- **Map onto your own components** — e.g. your card = `background:var(--lf-surface-bg); border:var(--lf-surface-border); box-shadow:var(--lf-surface-shadow); border-radius:var(--lf-surface-radius); backdrop-filter:var(--lf-backdrop);`

**3. Wire the picker** into *Settings → Appearance* (replaces the A/C switch).
The themes are split into two build sets — pass the platform so each build shows
only its set:

```js
import { picker } from './linguafusion-themes.js';
picker(document.querySelector('#lf-theme-picker'), { platform: 'mobile' }); // Android build — 7 themes
picker(document.querySelector('#lf-theme-picker'), { platform: 'pc' });     // desktop + web build — 9 themes
// picker(el)  with no platform shows all 16
```

That's it. Every screen — Translate, Reader, Speech, OCR, Notes, Access,
Settings — re-skins from the same tokens. **Themes are platform-agnostic**:
the Android, desktop, and web builds share one theme set; only the OS chrome
(status bar / title bar / browser frame) differs.

---

## Token contract

Every theme sets all of these (full-value tokens hold complete CSS strings so
glass/neumorphic/brutalist can fully describe themselves).

| Group | Tokens |
|-------|--------|
| Palette | `--lf-app-bg` · `--lf-text` · `--lf-text-muted` · `--lf-accent` · `--lf-accent-2` · `--lf-on-accent` · `--lf-success` |
| Surface | `--lf-surface-bg` · `--lf-surface-border` · `--lf-surface-shadow` · `--lf-surface-radius` · `--lf-backdrop` |
| Secondary panel | `--lf-panel-bg` · `--lf-panel-text` *(dark rail / filled container)* |
| Translation pane | `--lf-xlate-bg` · `--lf-xlate-border` · `--lf-xlate-text` · `--lf-xlate-label` |
| Record button | `--lf-record-bg` · `--lf-record-radius` · `--lf-record-shadow` · `--lf-record-glyph` |
| Chips / badge | `--lf-chip-bg` · `--lf-chip-border` · `--lf-badge-bg` · `--lf-badge-text` |
| Waveform | `--lf-wave-color` |
| Type | `--lf-font-display` · `--lf-font-body` · `--lf-font-mono` · `--lf-heading-weight` · `--lf-label-font` · `--lf-label-transform` · `--lf-label-spacing` |
| Motion | `--lf-ease` · `--lf-dur-fast` · `--lf-dur` · `--lf-dur-slow` · `--lf-stagger` · `--lf-record-ring` · `--lf-anim-screen-in` · `--lf-anim-screen-out` · `--lf-anim-rail` · `--lf-anim-import` · `--lf-anim-export` · `--lf-anim-result` · `--lf-anim-record` |

---

## Motion — event playbook

The motion tokens are pre-tuned per theme; the same call feels native everywhere.

| Event | What to do | Result |
|-------|-----------|--------|
| **Screen / tab switch** | on the incoming screen root: `M.enterScreen(el)`; on the outgoing: `M.exitScreen(old, cb)` | themed transition (fade-up, wipe, blur-in, spring, cut…) |
| **Import** (Import Audio / file drop) | `M.importIn(cardEl)` when the file lands | file "drops" into place |
| **Export** (.srt / Save Note) | `M.exportOut(rowEl, () => toast())` | row flies out, then your success toast |
| **Live result** (transcript/translation lines) | wrap lines in a container; after appending, `M.revealResult(container)` | each line reveals staggered (`--lf-stagger`); terminal types, glass blurs in |
| **Recording** | `M.setRecording(recordBtn, true/false)` | mic pulses / breathes / glows per theme |
| **Waveform activity** | `M.buildWave(waveEl, 32)` once, then `M.setWaveLive(waveEl, true/false)` | bars oscillate while capturing |

All motion is auto-disabled under `prefers-reduced-motion` (the record button
falls back to a static outline).

---

## Theme catalog

The 16 themes are split into two build sets. All themes technically work on any
platform; these sets are what each build **offers** in Settings. Import them via
`LF_THEMES_MOBILE`, `LF_THEMES_PC`, or `themesFor('mobile'|'pc')`.

### 📱 Mobile app (Android) — 7 themes

| id | Name | Group | Mode | Motion personality |
|----|------|-------|------|--------------------|
| `soft-ui` | Soft UI | Light | ☀ | slow gentle scale, breathing mic |
| `candy` | Candy | Playful | ☀ | bouncy spring overshoot |
| `material` | Material Expressive | Playful | ☀ | shared-axis slide (emphasized easing) |
| `sunset` | Sunset | Playful | ☀ | content sheet slides up |
| `brutalist` | Neo-Brutalist | Playful | ☀ | hard stepped cuts, no smoothing |
| `warm-editorial` | Warm Editorial | Editorial | ☀ | slow literary cross-fade |
| `glass-dark` | Glass Dark | Dark | 🌙 | blur-in, cyan glow |

### 🖥 PC app + Web — 9 themes

| id | Name | Group | Mode | Motion personality |
|----|------|-------|------|--------------------|
| `focus-light` | Focus Light | Light | ☀ | calm fade-up, soft pulse |
| `frosted-native` | Frosted Native | Light | ☀ | macOS soft scale/spring |
| `swiss` | Swiss | Editorial | ☀ | precise clip-path wipe |
| `broadsheet` | Broadsheet | Editorial | ☀ | page-settle fade + subtle scale |
| `editorial-split` | Editorial Split | Editorial | ☀ | panes slide from opposite sides |
| `glass-aurora` | Glass Aurora | Dark | 🌙 | blur-in, glowing mic |
| `amber-studio` | Amber Studio | Dark | 🌙 | dim-to-lit, amber glow |
| `terminal` | Local-first Terminal | Dark | 🌙 | typewriter reveal, caret blink |
| `zen` | Zen Focus | Dark | 🌙 | very slow breathing fades |

### Structural signatures — now shipped as CSS

`linguafusion-structure.css` encodes these as real `[data-theme="…"]` layout
rules, so they apply automatically **once the markup wears the hook classes**
(`lf-speech`, `lf-signature`, `lf-speech-head`, `lf-speech-controls`,
`lf-recorder`, `lf-result`). What each does:

- **`swiss`** — controls become a 3-column hairline grid; result splits into two
  columns with a center rule; everything squares off.
- **`broadsheet`** — `lf-signature` renders a centered dateline + double rule;
  header centers; result flows in newspaper columns.
- **`terminal`** — `lf-signature` renders the `$ stt --lang auto …` prompt;
  result panels get the green/amber command-log borders.
- **`editorial-split`** — the linear DOM reflows (via grid areas) into a large
  editorial pane + a dark control rail holding chips/timer/mic.
- **`zen`** — header and controls hide; recorder + result center in one column;
  the waveform scales up as the hero.
- **`brutalist`** — every block gets a 3px border + hard offset shadow, no radius.
- **`sunset`** — header/controls sit on the gradient in white; result becomes a
  white sheet with a large top radius.
- **`glass-aurora` / `glass-dark`** — panels gain an inner top highlight for depth
  (backdrop-blur comes from the tokens).

Apply the same six hook classes to the other screens (Translate, Reader, OCR,
Notes) and the structural rules extend there too.

---

## Reference markup — the Speech screen with helper classes

Minimal, token-driven; drop your real state/handlers in. Works under every theme.

```html
<main class="lf-app lf-speech lf-screen-enter" id="screen-speech">
  <div class="lf-signature" aria-hidden="true"></div><!-- prompt/masthead slot -->

  <header class="lf-speech-head" style="padding:16px 22px">
    <h1 class="lf-heading" style="font-size:20px">Speech</h1>
    <span class="lf-badge">● Offline ready</span>
  </header>

  <!-- language controls -->
  <section class="lf-speech-controls" style="padding:0 22px 14px">
    <div class="lf-chip"><div class="lf-label">STT</div><div>Auto</div></div>
    <div class="lf-chip"><div class="lf-label">Translate to</div><div>German</div></div>
  </section>

  <!-- recorder -->
  <section class="lf-card lf-recorder" style="margin:0 22px;padding:16px">
    <button class="lf-record" style="width:56px;height:56px" aria-label="Record">
      <span class="lf-record-glyph"></span>
    </button>
    <div class="lf-heading" style="font-size:24px;font-variant-numeric:tabular-nums">00:42</div>
    <div class="lf-wave" id="wave" style="flex:1"></div>
  </section>

  <!-- live result: staggered reveal -->
  <section class="lf-result" style="padding:16px 22px">
    <div class="lf-card" style="padding:14px">
      <div class="lf-label">Transcript</div>
      <p>Let's begin — can everyone hear me clearly?</p>
    </div>
    <div class="lf-translation" style="padding:14px">
      <div class="lf-label">Translation · DE</div>
      <p>Fangen wir an — können mich alle deutlich hören?</p>
    </div>
  </section>
</main>
```

```js
import * as M from './linguafusion-motion.js';
const wave = document.getElementById('wave');
M.buildWave(wave, 32);

// start recording
M.setRecording(document.querySelector('.lf-record'), true);
M.setWaveLive(wave, true);

// a new transcript line arrived
transcriptEl.appendChild(lineNode);
M.revealResult(document.querySelector('.lf-result'));

// user exported subtitles
M.exportOut(exportRow, () => showToast('Saved subtitles.srt'));
```

---

## Notes for the build

- **Fonts** are pulled via `@import` in `linguafusion-themes.css`. If the app
  runs offline (it does — Ollama/local), self-host these WOFF2 files instead and
  drop the `@import`: Inter, DM Sans, Fraunces, Instrument Serif, IBM Plex Mono,
  Archivo, Sora.
- **`color-scheme`** is set automatically by `applyTheme()` (dark themes flagged
  in `LF_THEMES`) so native form controls and scrollbars match.
- **Adding a theme later** = one `[data-theme="…"]` block in each CSS file + one
  row in `LF_THEMES`. Nothing else changes.
- **Per-platform chrome**: keep your existing Android bottom tab bar / desktop
  sidebar / web frame; they inherit `--lf-app-bg`, `--lf-text`, `--lf-accent`,
  and can use `--lf-panel-bg` for the sidebar surface.

---
