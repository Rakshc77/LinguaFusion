# LinguaFusion — Round 5 build spec (10 new themes)

Companion to `THEMING.md`. This adds **ten new themes** to the registry. Read
`THEMING.md` first — it defines the `--lf-*` token contract, the `.lf-*` helper
classes, the `lf-*` layout hooks, and the motion helpers. Everything below reuses
those. **Do not hardcode colors, fonts, radii, or shadows in components** — every
value lives in a theme's token block so each surface re-skins automatically.

Each theme is a **pure addition**: one block in each of `linguafusion-themes.css`,
`linguafusion-structure.css`, `linguafusion-motion.css`, plus one row in
`LF_THEMES` (`linguafusion-themes.js`). **No component rewrites.** Adding these
must not alter any existing theme.

Reference mockups live in `Transcription Looks.dc.html`:
`#3a`, `#4a`, `#4c`, `#5p1`, `#5p4`, `#5p5`, `#5m2`, `#5m3`, `#5m4`, `#5m5`.
Every color, font, layout, and string below is taken from those mockups — match them.

**Fonts** — add these families to the `@import` in `linguafusion-themes.css` (or
self-host WOFF2 for the offline build and drop the `@import`): **Newsreader,
Syne, Space Grotesk, JetBrains Mono, Bodoni Moda, Spectral, Unbounded, Cormorant
Garamond, Space Mono, Lora, Archivo, Big Shoulders Display**. (Several are already
loaded by earlier themes — de-dupe.)

The ten split across the two build sets exactly as the picker expects:

| Build set | New theme ids |
|-----------|---------------|
| **PC + Web** (`platform:'pc'`) | `brutalist-web`, `reading-room`, `gallery`, `aurora-glass`, `editorial-luxe`, `blueprint` |
| **Mobile** (`platform:'mobile'`) | `neon-arcade`, `warm-minimal`, `bold-mono`, `nature-calm` |

Rule of thumb for structure: if you only paste the token block and skip the
`linguafusion-structure.css` rule, the theme will re-color but keep the default
layout. **Each theme below MUST restructure** — that's the deliverable.

---

# PART A — PC + Web set (6 themes)

## A1. `brutalist-web` — Brutalist  (mockup `#3a`)

> **Already specified in `ROUND-3.md` §A1.** If you built Round 3, this theme
> exists — do not duplicate it; just confirm the `LF_THEMES` row is present.
> Repeated here so this spec is self-contained.

**Tokens (`[data-theme="brutalist-web"]`):**
- `--lf-app-bg:#e8e4d8` · `--lf-text:#111` · `--lf-text-muted:#4a4a44`
- `--lf-accent:#f24405` · `--lf-accent-2:#111` · `--lf-on-accent:#111` · `--lf-success:#111`
- `--lf-surface-bg:#e8e4d8` · `--lf-surface-border:3px solid #111` · `--lf-surface-shadow:6px 6px 0 #111` · `--lf-surface-radius:0` · `--lf-backdrop:none`
- `--lf-panel-bg:#111` · `--lf-panel-text:#e8e4d8`
- `--lf-xlate-bg:#111` · `--lf-xlate-border:3px solid #111` · `--lf-xlate-text:#e8e4d8` · `--lf-xlate-label:#f24405`
- `--lf-record-bg:#f24405` · `--lf-record-radius:0` · `--lf-record-shadow:6px 6px 0 #111` · `--lf-record-glyph:#111`
- `--lf-chip-bg:#e8e4d8` · `--lf-chip-border:3px solid #111` · `--lf-badge-bg:#f24405` · `--lf-badge-text:#111`
- `--lf-wave-color:#111`
- `--lf-font-display:"Archivo"` · `--lf-font-body:"Archivo"` · `--lf-font-mono:"Space Mono"` · `--lf-heading-weight:900` · `--lf-label-font:var(--lf-font-mono)` · `--lf-label-transform:uppercase` · `--lf-label-spacing:.08em`

**Structure:** `.lf-speech-head` oversized uppercase display (`clamp(32px,5vw,40px)`,
900, `letter-spacing:-.03em`) with a full-height orange `● REC · OFFLINE` block
pinned right. `.lf-speech-controls` = 3 equal columns sharing `3px solid #111`
borders, last cell inverts to `#111`/`#e8e4d8`. `.lf-result` = 2-column split, the
translation column filled `--lf-panel-bg` (black). Labels are mono, orange,
prefixed `// ` via `::before` (`// TRANSCRIPT — EN`).

**Motion:** hard stepped cuts (`steps()` easing, no smoothing); `--lf-record-ring:none`.

**Registry row:**
```js
{ id:'brutalist-web', name:'Brutalist', group:'Playful', dark:false, platform:'pc', motion:'hard stepped cuts' }
```

---

## A2. `reading-room` — Reading room  (mockup `#4a`)

A literary text page: warm ivory, a book-style masthead with rules, a single wide
reading column with **marginal timestamps** in the left gutter. Body is a text
serif; translation is the same serif in italic, muted.

**Tokens (`[data-theme="reading-room"]`):**
- `--lf-app-bg:#f7f3ea` · `--lf-text:#2a2119` · `--lf-text-muted:#6a5d4a`
- `--lf-accent:#b04a2f` (terracotta — timestamps/rec) · `--lf-accent-2:#5b3a52` (plum) · `--lf-on-accent:#f7f3ea` · `--lf-success:#5c7a3f`
- `--lf-surface-bg:#f7f3ea` · `--lf-surface-border:1px solid #e0d7c3` · `--lf-surface-shadow:none` · `--lf-surface-radius:0` · `--lf-backdrop:none`
- `--lf-panel-bg:#efe8d6` · `--lf-panel-text:#5b3a52`
- `--lf-xlate-bg:transparent` · `--lf-xlate-border:none` · `--lf-xlate-text:#6a5d4a` (rendered italic) · `--lf-xlate-label:#b04a2f`
- `--lf-record-bg:#b04a2f` · `--lf-record-radius:50%` · `--lf-record-shadow:none` · `--lf-record-glyph:#f7f3ea`
- `--lf-chip-bg:transparent` · `--lf-chip-border:1px solid #e0d7c3` · `--lf-badge-bg:transparent` · `--lf-badge-text:#9a8f78`
- `--lf-wave-color:#5b3a52`
- `--lf-font-display:"Newsreader"` · `--lf-font-body:"Newsreader"` · `--lf-font-mono:"IBM Plex Mono"` · `--lf-heading-weight:400` · `--lf-label-font:"Newsreader"` · `--lf-label-transform:uppercase` · `--lf-label-spacing:.34em`

**Structure:** `.lf-signature` renders a **centered masthead** — a tracked
all-caps kicker ("LIVE TRANSLATION · OFFLINE"), a large serif title ("Session
Transcript", ~30px/400), and an italic subline, bracketed top & bottom by `1px`
rules. `.lf-speech-controls` collapse into that masthead line (no chip chrome).
`.lf-result` becomes a **single reading column**: each turn is a row with a fixed
`42px` right-aligned gutter holding the timestamp (in `--lf-accent`), then the
source line (serif, ~20px/1.5) and the translation line beneath (serif italic,
~16px/1.5, `--lf-text-muted`). Recorder is a slim footer: timer (serif ~26px) +
waveform + italic "recording…".

**Motion:** slow literary cross-fade; `revealResult` fades lines in gently
(no slide). `--lf-record-ring:none` (a quiet dot). Reuse `warm-editorial` timing.

**Registry row:**
```js
{ id:'reading-room', name:'Reading room', group:'Editorial', dark:false, platform:'pc', motion:'slow literary cross-fade' }
```

---

## A3. `gallery` — Gallery  (mockup `#4c`)

Avant-garde display type on a near-black canvas with one electric-lime accent.
Asymmetric: a thin left rail with a vertical `EN → DE` label + glowing dot, and a
big left-aligned type block with a short accent underline between source and
translation.

**Tokens (`[data-theme="gallery"]`):**
- `--lf-app-bg:#0e0e10` · `--lf-text:#f2f2ee` · `--lf-text-muted:#5f5f63`
- `--lf-accent:#d8ff3d` · `--lf-accent-2:#d8ff3d` · `--lf-on-accent:#0e0e10` · `--lf-success:#d8ff3d`
- `--lf-surface-bg:#0e0e10` · `--lf-surface-border:1px solid #262628` · `--lf-surface-shadow:none` · `--lf-surface-radius:0` · `--lf-backdrop:none`
- `--lf-panel-bg:#161618` · `--lf-panel-text:#6a6a6e`
- `--lf-xlate-bg:transparent` · `--lf-xlate-border:none` · `--lf-xlate-text:#d8ff3d` · `--lf-xlate-label:#5f5f63`
- `--lf-record-bg:#d8ff3d` · `--lf-record-radius:50%` · `--lf-record-shadow:0 0 16px rgba(216,255,61,.6)` · `--lf-record-glyph:#0e0e10`
- `--lf-chip-bg:transparent` · `--lf-chip-border:1px solid #262628` · `--lf-badge-bg:#d8ff3d` · `--lf-badge-text:#0e0e10`
- `--lf-wave-color:#d8ff3d`
- `--lf-font-display:"Syne"` · `--lf-font-body:"Syne"` · `--lf-font-mono:"Space Mono"` · `--lf-heading-weight:800` · `--lf-label-font:"Syne"` · `--lf-label-transform:uppercase` · `--lf-label-spacing:.2em`

**Structure:** reflow `.lf-speech` into a grid = a **64px left rail** + main
column. Rail: `1px` right border, a vertical `writing-mode:vertical-rl` accent
label (`EN → DE`) top, a glowing accent dot bottom. Main column centers
vertically: a small tracked caps caption ("Now speaking"), a huge display heading
(`~34px/1.05`, weight 800, `-.01em`) for the source, a `56×3px` accent rule, then
the translation in `--lf-accent` (`~26px/1.15`, weight 700). Timer (Syne ~26px) +
waveform sit under it. Big type + generous negative space is the point.

**Motion:** heading + rule scale/fade in on result (`transform:scale(.96→1)` +
fade, theme `--lf-ease`); mic glows. Honors reduced-motion (static).

**Registry row:**
```js
{ id:'gallery', name:'Gallery', group:'Editorial', dark:true, platform:'pc', motion:'display scale-in, glow mic' }
```

---

## A4. `aurora-glass` — Aurora glass  (mockup `#5p1`)

Frosted glass panels floating over a soft aurora gradient; teal light. Depth from
backdrop-blur + a subtle inner top highlight (like `glass-aurora`).

**Tokens (`[data-theme="aurora-glass"]`):**
- `--lf-app-bg:radial-gradient(90% 120% at 15% 0%,#1c3a4a 0%,#0c1018 55%),radial-gradient(80% 100% at 100% 100%,#2a2350 0%,transparent 60%)` (on a `#0c1018` base) · `--lf-text:#eef3fb` · `--lf-text-muted:#8aa0c8`
- `--lf-accent:#2dd4bf` · `--lf-accent-2:#3b82f6` · `--lf-on-accent:#05201c` · `--lf-success:#7ff0e0`
- `--lf-surface-bg:rgba(255,255,255,.06)` · `--lf-surface-border:1px solid rgba(255,255,255,.12)` · `--lf-surface-shadow:none` · `--lf-surface-radius:18px` · `--lf-backdrop:blur(12px)`
- `--lf-panel-bg:#121826` · `--lf-panel-text:#7c8bb0`
- `--lf-xlate-bg:linear-gradient(135deg,rgba(45,212,191,.18),rgba(59,130,246,.14))` · `--lf-xlate-border:1px solid rgba(45,212,191,.35)` · `--lf-xlate-text:#eafbf7` · `--lf-xlate-label:#7ff0e0`
- `--lf-record-bg:linear-gradient(135deg,#2dd4bf,#3b82f6)` · `--lf-record-radius:50%` · `--lf-record-shadow:0 8px 24px -6px rgba(45,212,191,.5)` · `--lf-record-glyph:#fff`
- `--lf-chip-bg:rgba(255,255,255,.05)` · `--lf-chip-border:1px solid rgba(255,255,255,.1)` · `--lf-badge-bg:rgba(45,212,191,.14)` · `--lf-badge-text:#7ff0e0`
- `--lf-wave-color:#2dd4bf`
- `--lf-font-display:"Space Grotesk"` · `--lf-font-body:"Space Grotesk"` · `--lf-font-mono:"JetBrains Mono"` · `--lf-heading-weight:600` · `--lf-label-transform:uppercase` · `--lf-label-spacing:.1em`

**Structure:** standard vertical stack, but every panel is a **glass card**
(`--lf-surface-*` + `backdrop-filter:var(--lf-backdrop)`) with a `1px` inner top
highlight (`box-shadow:inset 0 1px 0 rgba(255,255,255,.18)`). Source card uses the
plain glass surface; translation card uses the teal→blue `--lf-xlate-bg` gradient
+ accent border. The recorder is its **own** glass pill (not merged into a header):
gradient mic circle + timer + waveform.

**Motion:** blur-in on screen enter (`filter:blur(8px)→0` + fade); mic breathes/
glows; result lines blur-in staggered. Reuse `glass-aurora` motion tokens.

**Registry row:**
```js
{ id:'aurora-glass', name:'Aurora Glass', group:'Dark', dark:true, platform:'pc', motion:'blur-in, glowing mic' }
```

---

## A5. `editorial-luxe` — Editorial luxe  (mockup `#5p4`)

High-fashion editorial: warm ivory, a Bodoni display masthead, Spectral body, gold
hairlines, a two-column source/translation split with a center rule.

**Tokens (`[data-theme="editorial-luxe"]`):**
- `--lf-app-bg:#f4efe4` · `--lf-text:#2a2118` · `--lf-text-muted:#9c8a63`
- `--lf-accent:#9c7a3c` (gold) · `--lf-accent-2:#7a5f2a` · `--lf-on-accent:#f4efe4` · `--lf-success:#7a8a4a`
- `--lf-surface-bg:transparent` · `--lf-surface-border:none` · `--lf-surface-shadow:none` · `--lf-surface-radius:0` · `--lf-backdrop:none` (layout uses `1px solid #ddd2ba` hairline dividers, not cards)
- `--lf-panel-bg:#ece5d4` · `--lf-panel-text:#7a5f2a`
- `--lf-xlate-bg:transparent` · `--lf-xlate-border:none` · `--lf-xlate-text:#4a3f2c` (rendered italic) · `--lf-xlate-label:#9c7a3c`
- `--lf-record-bg:#9c7a3c` · `--lf-record-radius:50%` · `--lf-record-shadow:none` · `--lf-record-glyph:#f4efe4`
- `--lf-chip-bg:transparent` · `--lf-chip-border:1px solid #ddd2ba` · `--lf-badge-bg:transparent` · `--lf-badge-text:#9c7a3c`
- `--lf-wave-color:#9c7a3c`
- `--lf-font-display:"Bodoni Moda"` · `--lf-font-body:"Spectral"` · `--lf-font-mono:"IBM Plex Mono"` · `--lf-heading-weight:500` · `--lf-label-font:"Spectral"` · `--lf-label-transform:uppercase` · `--lf-label-spacing:.12em`

**Structure:** `.lf-signature` = a **centered masthead** — Bodoni title ("Speech",
~30px/500) over a tracked Spectral caps kicker ("LIVE TRANSLATION · OFFLINE"),
under a `1px` bottom rule. `.lf-result` = **two columns** (English | Deutsch) with
a full-height `1px` center hairline; each column has a gold tracked-caps label,
source in Bodoni (~25px/500), translation in Bodoni **italic**, muted. Footer:
Bodoni timer + waveform + italic "recording". No card chrome — dividers only.

**Motion:** slow literary cross-fade / page-settle (subtle fade + `scale(.99→1)`).
`--lf-record-ring:none`.

**Registry row:**
```js
{ id:'editorial-luxe', name:'Editorial Luxe', group:'Editorial', dark:false, platform:'pc', motion:'page-settle fade' }
```

---

## A6. `blueprint` — Blueprint  (mockup `#5p5`)

Technical drafting sheet: navy field with a fine cyan grid, mono callouts +
grotesk body, bordered boxes with a small label tab (dimension-callout style).

**Tokens (`[data-theme="blueprint"]`):**
- `--lf-app-bg:#0a1830` · `--lf-text:#eaf4ff` · `--lf-text-muted:#5f8fbf`
- `--lf-accent:#5fd0ff` · `--lf-accent-2:#7fb8e6` · `--lf-on-accent:#06223d` · `--lf-success:#5fd0ff`
- `--lf-surface-bg:transparent` · `--lf-surface-border:1px solid #2a4a75` · `--lf-surface-shadow:none` · `--lf-surface-radius:0` · `--lf-backdrop:none`
- `--lf-panel-bg:#0d2140` · `--lf-panel-text:#7fb8e6`
- `--lf-xlate-bg:transparent` · `--lf-xlate-border:1px solid #2a4a75` · `--lf-xlate-text:#9fd0f5` · `--lf-xlate-label:#5fd0ff`
- `--lf-record-bg:#5fd0ff` · `--lf-record-radius:2px` · `--lf-record-shadow:none` · `--lf-record-glyph:#06223d`
- `--lf-chip-bg:transparent` · `--lf-chip-border:1px solid #2a4a75` · `--lf-badge-bg:transparent` · `--lf-badge-text:#5fd0ff`
- `--lf-wave-color:#5fd0ff`
- `--lf-font-display:"Space Grotesk"` · `--lf-font-body:"Space Grotesk"` · `--lf-font-mono:"JetBrains Mono"` · `--lf-heading-weight:600` · `--lf-label-font:"JetBrains Mono"` · `--lf-label-transform:uppercase` · `--lf-label-spacing:.1em`

**Structure:** `.lf-speech` gets a **drafting-grid background** via
`background-image:linear-gradient(rgba(95,208,255,.06) 1px,transparent 1px),
linear-gradient(90deg,rgba(95,208,255,.06) 1px,transparent 1px);
background-size:26px 26px`. A top row of mono coordinate labels (`SRC ⌀ EN` ·
`SCALE 1:1` · `TGT ⌀ DE`). Source & translation are each a **bordered box** with a
small mono label tab overlapping the top border (`position:absolute;top:-7px` with
the field bg behind it — `EN` / `DE`). A `1px dashed` divider sits above the
footer; footer = mono timer + waveform + `● REC`.

**Motion:** precise — clip-path/wipe reveal (reuse `swiss`) or terminal-style; mic
is a hard state, `--lf-record-ring:none`.

**Registry row:**
```js
{ id:'blueprint', name:'Blueprint', group:'Utility', dark:true, platform:'pc', motion:'precise clip wipe' }
```

---

# PART B — Mobile set (4 themes)

## B1. `neon-arcade` — Neon arcade  (mockup `#5m2`)

Synthwave: deep purple-black radial field, Unbounded display, neon **cyan** source
outline + neon **magenta** translation outline, glowing mic.

**Tokens (`[data-theme="neon-arcade"]`):**
- `--lf-app-bg:radial-gradient(120% 70% at 50% 100%,#1a0730 0%,#0a0612 60%)` (base `#0a0612`) · `--lf-text:#eafcff` · `--lf-text-muted:#8a7ab0`
- `--lf-accent:#ff2fb0` (magenta) · `--lf-accent-2:#22d3ee` (cyan) · `--lf-on-accent:#0a0612` · `--lf-success:#22d3ee`
- `--lf-surface-bg:transparent` · `--lf-surface-border:1.5px solid rgba(34,211,238,.5)` · `--lf-surface-shadow:0 0 18px -4px rgba(34,211,238,.4), inset 0 0 18px -8px rgba(34,211,238,.4)` · `--lf-surface-radius:14px` · `--lf-backdrop:none`
- `--lf-panel-bg:#140826` · `--lf-panel-text:#22d3ee`
- `--lf-xlate-bg:transparent` · `--lf-xlate-border:1.5px solid rgba(255,47,176,.6)` · `--lf-xlate-text:#ffe6f6` · `--lf-xlate-label:#ff2fb0` (its glow: `box-shadow:0 0 18px -4px rgba(255,47,176,.45), inset 0 0 18px -8px rgba(255,47,176,.4)`)
- `--lf-record-bg:#ff2fb0` · `--lf-record-radius:50%` · `--lf-record-shadow:0 0 26px rgba(255,47,176,.7)` · `--lf-record-glyph:#0a0612`
- `--lf-chip-bg:transparent` · `--lf-chip-border:1px solid rgba(34,211,238,.5)` · `--lf-badge-bg:transparent` · `--lf-badge-text:#22d3ee` (badge outline = cyan `1px`, add in structure)
- `--lf-wave-color:#ff2fb0`
- `--lf-font-display:"Unbounded"` · `--lf-font-body:"Unbounded"` · `--lf-font-mono:"Space Mono"` · `--lf-heading-weight:600` · `--lf-label-transform:uppercase` · `--lf-label-spacing:.12em`

**Structure:** dark radial field; source & translation are **neon-outlined cards**
(source uses `--lf-surface-*` cyan glow, translation uses the magenta `--lf-xlate-*`
glow). Heading and brand get a text glow (`text-shadow:0 0 14px` in accent). Mic
is a magenta disc with a strong outer glow. Keep Unbounded sizes modest (it's wide)
— ~15–16px body so lines don't overflow the 300px phone.

**Motion:** glow pulse on the mic + neon flicker-in (opacity blur-in) on result.
Reduced-motion → steady glow, no flicker.

**Registry row:**
```js
{ id:'neon-arcade', name:'Neon Arcade', group:'Playful', dark:true, platform:'mobile', motion:'neon glow pulse' }
```

---

## B2. `warm-minimal` — Warm minimal  (mockup `#5m3`)

Airy cream, terracotta accent, everything centered with generous whitespace; a
high-contrast old-style serif. Calm and quiet.

**Tokens (`[data-theme="warm-minimal"]`):**
- `--lf-app-bg:#f5f0e8` · `--lf-text:#2c2620` · `--lf-text-muted:#a89a86`
- `--lf-accent:#b0563a` (terracotta) · `--lf-accent-2:#b0563a` · `--lf-on-accent:#f5f0e8` · `--lf-success:#7a8a4a`
- `--lf-surface-bg:transparent` · `--lf-surface-border:none` · `--lf-surface-shadow:none` · `--lf-surface-radius:0` · `--lf-backdrop:none` (hairline dividers only)
- `--lf-panel-bg:transparent` · `--lf-panel-text:#b0563a`
- `--lf-xlate-bg:transparent` · `--lf-xlate-border:none` · `--lf-xlate-text:#5c5346` (rendered italic) · `--lf-xlate-label:#b0563a`
- `--lf-record-bg:transparent` · `--lf-record-radius:50%` · `--lf-record-shadow:none` · `--lf-record-glyph:#b0563a` (button is a `1px solid var(--lf-accent)` outline circle — set the border in structure)
- `--lf-chip-bg:transparent` · `--lf-chip-border:1px solid #e0d7c3` · `--lf-badge-bg:transparent` · `--lf-badge-text:#b0563a`
- `--lf-wave-color:#b0563a`
- `--lf-font-display:"Cormorant Garamond"` · `--lf-font-body:"Cormorant Garamond"` · `--lf-font-mono:"IBM Plex Mono"` · `--lf-heading-weight:500` · `--lf-label-font:"Cormorant Garamond"` · `--lf-label-transform:uppercase` · `--lf-label-spacing:.24em`

**Structure:** `.lf-speech` becomes a **single centered column**, text-centered
throughout. Top: a tracked caps brand mark. Middle (vertically centered): a caps
"You said" label + source serif (~26px/500), a `30×1px` accent divider, a caps
"Deutsch" label + translation serif **italic** (~24px), muted. Bottom (centered):
waveform, then a `1px` accent **outline** mic circle, then a tracked
"00:42 · recording" caption. `.lf-speech-head`/`.lf-speech-controls` are hidden —
this is a zen-like reading view.

**Motion:** very slow breathing fades (reuse `zen`). Mic outline pulses softly.

**Registry row:**
```js
{ id:'warm-minimal', name:'Warm Minimal', group:'Editorial', dark:false, platform:'mobile', motion:'slow breathing fade' }
```

---

## B3. `bold-mono` — Bold mono  (mockup `#5m4`)

Hard monospace brutalism, scaled for one hand: `2px` black rules, zero rounding,
the translation is a full-bleed **inverted** black block.

**Tokens (`[data-theme="bold-mono"]`):**
- `--lf-app-bg:#fff` · `--lf-text:#000` · `--lf-text-muted:#555`
- `--lf-accent:#000` · `--lf-accent-2:#000` · `--lf-on-accent:#fff` · `--lf-success:#000`
- `--lf-surface-bg:#fff` · `--lf-surface-border:2px solid #000` · `--lf-surface-shadow:none` · `--lf-surface-radius:0` · `--lf-backdrop:none`
- `--lf-panel-bg:#000` · `--lf-panel-text:#fff`
- `--lf-xlate-bg:#000` · `--lf-xlate-border:2px solid #000` · `--lf-xlate-text:#fff` · `--lf-xlate-label:#fff`
- `--lf-record-bg:#000` · `--lf-record-radius:0` · `--lf-record-shadow:none` · `--lf-record-glyph:#fff`
- `--lf-chip-bg:#fff` · `--lf-chip-border:2px solid #000` · `--lf-badge-bg:#000` · `--lf-badge-text:#fff`
- `--lf-wave-color:#000`
- `--lf-font-display:"Space Mono"` · `--lf-font-body:"Space Mono"` · `--lf-font-mono:"Space Mono"` · `--lf-heading-weight:700` · `--lf-label-font:"Space Mono"` · `--lf-label-transform:uppercase` · `--lf-label-spacing:.08em`

**Structure:** full-bleed stacked split. Header row = mono `LINGUAFUSION` +
inverted `● REC` badge, under a `2px` bottom rule. Body = two equal-height blocks
divided by `2px` rules: the **EN** block (white, `// EN` label + source ~18px mono)
and the **DE** block filled `--lf-panel-bg` black (`// DE` label + translation
~17px mono, white). Footer (`2px` top rule) = square black mic + mono timer +
waveform. Labels prefixed `// ` via `::before`. No radius anywhere.

**Motion:** hard stepped cuts (reuse `brutalist`); `--lf-record-ring:none`.

**Registry row:**
```js
{ id:'bold-mono', name:'Bold Mono', group:'Playful', dark:false, platform:'mobile', motion:'hard stepped cuts' }
```

---

## B4. `nature-calm` — Nature calm  (mockup `#5m5`)

Soft sage, organic rounding, gentle greens; a warm humanist serif. The translation
card is a filled sage block.

**Tokens (`[data-theme="nature-calm"]`):**
- `--lf-app-bg:#eef2ea` · `--lf-text:#2f3d2c` · `--lf-text-muted:#8ba085`
- `--lf-accent:#4a6b4a` (sage) · `--lf-accent-2:#4a6b4a` · `--lf-on-accent:#eef4ea` · `--lf-success:#4a6b4a`
- `--lf-surface-bg:#f7faf5` · `--lf-surface-border:none` · `--lf-surface-shadow:none` · `--lf-surface-radius:20px` · `--lf-backdrop:none`
- `--lf-panel-bg:#4a6b4a` · `--lf-panel-text:#eef4ea`
- `--lf-xlate-bg:#4a6b4a` · `--lf-xlate-border:none` · `--lf-xlate-text:#eef4ea` (rendered italic) · `--lf-xlate-label:#c4d6bf`
- `--lf-record-bg:#4a6b4a` · `--lf-record-radius:50%` · `--lf-record-shadow:0 8px 20px -6px rgba(74,107,74,.55)` · `--lf-record-glyph:#eef2ea`
- `--lf-chip-bg:#dde7d8` · `--lf-chip-border:none` · `--lf-badge-bg:#dde7d8` · `--lf-badge-text:#4a6b4a`
- `--lf-wave-color:#17604a`
- `--lf-font-display:"Lora"` · `--lf-font-body:"Lora"` · `--lf-font-mono:"IBM Plex Mono"` · `--lf-heading-weight:600` · `--lf-label-font:"Lora"` · `--lf-label-transform:uppercase` · `--lf-label-spacing:.08em`

**Structure:** standard soft stack. Header = Lora "Speech" + a rounded `● offline`
badge. Source card is the light `--lf-surface-bg` (radius 20px); translation card
is the filled sage `--lf-xlate-bg` with an italic translation. Recorder = filled
sage mic circle (soft shadow) + Lora timer + waveform. Everything rounded and
airy; no hard edges.

**Motion:** gentle slow scale + soft mic breathing (reuse `soft-ui`).

**Registry row:**
```js
{ id:'nature-calm', name:'Nature Calm', group:'Light', dark:false, platform:'mobile', motion:'gentle scale, breathing mic' }
```

---

## Build order & global acceptance

These are all additive and independent. Suggested order (fast → involved):

1. **Token blocks first** — paste all ten `[data-theme]` blocks into
   `linguafusion-themes.css` and the ten `LF_THEMES` rows. Add the fonts to the
   `@import`. At this point every theme should re-**color** the app.
2. **Structure rules** — add the ten `[data-theme]` blocks to
   `linguafusion-structure.css`. This is the real work: each theme must
   **restructure** the Speech screen (and the shared hook classes carry it to
   Translate/Reader/OCR/Notes). Verify against the mockup:
   - `brutalist-web` → 3-col hairline controls + 2-col result, black translation column.
   - `reading-room` → centered masthead + single reading column with marginal timestamps.
   - `gallery` → left rail (vertical label + dot) + big display column with accent rule.
   - `aurora-glass` → glass cards over the aurora, recorder as its own glass pill.
   - `editorial-luxe` → centered Bodoni masthead + two-column source/translation with center rule.
   - `blueprint` → drafting-grid bg + label-tab bordered boxes + coordinate row.
   - `neon-arcade` → neon-outlined cards (cyan source / magenta translation), glowing mic.
   - `warm-minimal` → single centered column, header/controls hidden, outline mic.
   - `bold-mono` → full-bleed EN/DE split, DE block inverted, 2px rules, no radius.
   - `nature-calm` → soft rounded stack, filled sage translation card.
3. **Motion blocks** — add per-theme motion tokens to `linguafusion-motion.css`
   (reuse the personalities noted per theme). Confirm `M.enterScreen`,
   `M.revealResult`, `M.setRecording`, `M.setWaveLive` feel native under each.

**Global acceptance (run once at the end):**
- All themes (existing + these 10) switch cleanly via `data-theme`; the picker
  shows the 6 new PC themes in the `pc` build and the 4 new mobile themes in the
  `mobile` build.
- Each new theme changes **layout + type + color**, not color alone — compare to
  its mockup (`#3a`, `#4a`, `#4c`, `#5p1`, `#5p4`, `#5p5`, `#5m2`, `#5m3`, `#5m4`,
  `#5m5`).
- Every component reads `--lf-*` — grep the diff for hardcoded hex / px fonts /
  shadows and remove them.
- All new text meets WCAG AA contrast on its surface (watch: `neon-arcade` body on
  the dark field, `warm-minimal` muted terracotta, `gallery` muted `#5f5f63`).
- `color-scheme` follows the `dark` flag (`gallery`, `aurora-glass`, `blueprint`,
  `neon-arcade` are dark).
- Nothing clipped or overflowing at mobile (360–430px) and desktop (≥1024px).
  Unbounded (`neon-arcade`) and Bodoni display (`editorial-luxe`) are wide — check
  wrapping.
- `prefers-reduced-motion` honored (no flicker/pulse/count animations).

---
