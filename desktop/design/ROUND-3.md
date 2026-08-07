# LinguaFusion — Round 3 build spec (2 themes + 5 features)

Companion to `THEMING.md`. This adds **two new themes** and **five new
features** to the app. Read `THEMING.md` first — it defines the `--lf-*` token
contract, the `.lf-*` helper classes, the `lf-*` layout hooks, and the motion
helpers (`M.enterScreen`, `M.revealResult`, `M.setRecording`, …). Everything
below reuses those. **Do not hardcode colors, fonts, radii, or shadows** — read
tokens so each new surface re-skins under all themes automatically.

Reference mockups live in `Transcription Looks.dc.html`, Round 3 (`#3a`–`#3h`).
Every string, layout, and state below is taken verbatim from those mockups — match them.

---

## PART A — Two new themes

These are pure additions to the existing theme framework: **one block in each of
`linguafusion-themes.css`, `linguafusion-structure.css`, `linguafusion-motion.css`,
and one row in `LF_THEMES` (`linguafusion-themes.js`).** No component rewrites.

### A1. `brutalist-web` — Brutalist (PC + Web set)

There is already a `brutalist` (Neo-Brutalist, *mobile*, cream/soft) theme. This
is a **distinct, harder desktop/web variant** — add it as a new id, do not
overwrite the existing one.

**Tokens (`linguafusion-themes.css`, `[data-theme="brutalist-web"]`):**
- `--lf-app-bg: #e8e4d8` (concrete off-white)
- `--lf-text: #111`  ·  `--lf-text-muted: #4a4a44`
- `--lf-accent: #f24405` (safety orange)  ·  `--lf-accent-2: #111`  ·  `--lf-on-accent: #111`
- `--lf-success: #111`
- `--lf-surface-bg: #e8e4d8`  ·  `--lf-surface-border: 3px solid #111`  ·  `--lf-surface-shadow: 6px 6px 0 #111`  ·  `--lf-surface-radius: 0`  ·  `--lf-backdrop: none`
- `--lf-panel-bg: #111`  ·  `--lf-panel-text: #e8e4d8`
- `--lf-xlate-bg: #111`  ·  `--lf-xlate-border: 3px solid #111`  ·  `--lf-xlate-text: #e8e4d8`  ·  `--lf-xlate-label: #f24405`
- `--lf-record-bg: #f24405`  ·  `--lf-record-radius: 0`  ·  `--lf-record-shadow: 6px 6px 0 #111`  ·  `--lf-record-glyph: #111`
- `--lf-chip-bg: #e8e4d8`  ·  `--lf-chip-border: 3px solid #111`  ·  `--lf-badge-bg: #f24405`  ·  `--lf-badge-text: #111`
- `--lf-wave-color: #111`
- `--lf-font-display: "Archivo", sans-serif`  ·  `--lf-font-body: "Archivo", sans-serif`  ·  `--lf-font-mono: "Space Mono", monospace`  ·  `--lf-heading-weight: 900`  ·  `--lf-label-font: var(--lf-font-mono)`  ·  `--lf-label-transform: uppercase`  ·  `--lf-label-spacing: .08em`

**Structure (`linguafusion-structure.css`, `[data-theme="brutalist-web"]`):**
same family as the existing `brutalist` rule — every `.lf-card`, `.lf-chip`,
`.lf-recorder`, `.lf-translation` gets `border:3px solid #111; border-radius:0;
box-shadow:6px 6px 0 #111`. Additionally, harder than the mobile one:
- `.lf-speech-controls` → 3 equal columns divided by `3px solid #111` (no gaps, shared borders — `border-collapse` look), last cell inverts to `background:#111;color:#e8e4d8`.
- `.lf-speech-head` → oversized display title (`font-size: clamp(32px,5vw,40px)`, weight 900, uppercase, `letter-spacing:-.03em`), with a full-height orange `● REC · OFFLINE` block pinned to its right edge.
- `.lf-result` → 2-column split; the translation column is the black `--lf-panel-bg` filled block.
- Labels use mono, orange, `// TRANSCRIPT — EN` / `// TRANSLATION — DE` styling (prefix `// ` via `::before`).

**Motion (`linguafusion-motion.css`):** hard stepped cuts — reuse the existing
`brutalist` motion tokens (`steps()` easing, no smoothing, `--lf-record-ring: none`).

**Registry row (`LF_THEMES`):**
```js
{ id:'brutalist-web', name:'Brutalist', group:'Playful', dark:false, platform:'pc',
  motion:'hard stepped cuts' }
```

### A2. `kiosk` — Kiosk / signage (both sets, but flag it)

Public-terminal look: near-black, one enormous tap target, room-legible type. Add
to **both** build sets but mark it kiosk-only in the picker subtitle (it's meant
for a mounted/shared device, not personal use).

**Tokens (`[data-theme="kiosk"]`):**
- `--lf-app-bg: #0a0a0a`  ·  `--lf-text: #fff`  ·  `--lf-text-muted: #7a7a7a`
- `--lf-accent: #ffe14d`  ·  `--lf-accent-2: #ffe14d`  ·  `--lf-on-accent: #0a0a0a`  ·  `--lf-success: #ffe14d`
- `--lf-surface-bg: #0a0a0a`  ·  `--lf-surface-border: none`  ·  `--lf-surface-shadow: none`  ·  `--lf-surface-radius: 0`
- `--lf-panel-bg: #0a0a0a`  ·  `--lf-panel-text: #ffe14d`
- `--lf-xlate-bg: transparent`  ·  `--lf-xlate-text: #ffe14d`  ·  `--lf-xlate-label: #ffe14d`
- `--lf-record-bg: #ffe14d`  ·  `--lf-record-radius: 50%`  ·  `--lf-record-shadow: 0 0 40px rgba(255,225,77,.35)`  ·  `--lf-record-glyph: #0a0a0a`
- `--lf-badge-bg: #ffe14d`  ·  `--lf-badge-text: #0a0a0a`
- `--lf-wave-color: #ffe14d`
- `--lf-font-display: "Archivo", sans-serif`  ·  `--lf-heading-weight: 800`  ·  labels uppercase, `.1em`.

**Structure (`[data-theme="kiosk"]`):** this is the big one — kiosk changes the
whole layout for legibility:
- `.lf-speech-head` → hide muted metadata; keep only brand + a pill `● LISTENING`.
- `.lf-speech-controls` → collapse to a single large `EN→DE` readout (top-right), no dropdown chrome.
- `.lf-result` → single centered stack, source then translation, each with a small uppercase label and **huge** text (`font-size: clamp(28px,4.5vw,34px)`, weight 800, `line-height:1.1`), a `4px` divider between them.
- `.lf-recorder` → pinned to the bottom as a bar with a `3px solid` top rule: an **84px** circular record button, a wide waveform scaled `1.3×`, and the `EN→DE` label at `font-size:30px`.
- All hit targets ≥ 72px. No hover-only affordances (touch terminal).

**Registry row:**
```js
{ id:'kiosk', name:'Kiosk / signage', group:'Utility', dark:true, platform:'all',
  kiosk:true, motion:'instant, high-contrast' }
```
In `picker()`, when `theme.kiosk` is true, render the subtitle "Public terminal —
huge type, shared device".

**Acceptance for Part A:** switch to `brutalist-web` and `kiosk`; confirm each
restructures layout (not color alone), all text meets WCAG AA on its background
(`#111` on `#e8e4d8` and `#fff`/`#ffe14d` on `#0a0a0a` all pass), and nothing is
clipped. Adding these must not alter any existing theme.

---

## PART B — Five features

These need **new markup + state + logic**, not token blocks. Each is written to
be theme-aware (reads `--lf-*`) so it works under all 18 themes. Build each as
its own module/component. Keep the exact copy from the mockups for parity, then
replace with live data.

---

### B1. Bilingual PDF export  (mockup `#3c`)

**What:** an export format that renders the current session as a clean,
paginated, side-by-side EN↔target transcript with timestamps and speaker turns —
generated **on-device** (no network).

**Where:** add to the existing export menu next to `.srt` / `.txt`. The Speech
screen (and Translate/Reader/Notes with transcript history) gets an
`Export as ▾` control listing: **Bilingual PDF**, `.srt`, `.txt`.

**Data model** — the session is an array of turns:
```ts
type Turn = {
  t: number;          // start seconds → format mm:ss
  speaker: number;    // 1-based; may be null if diarization off
  source: string;     // recognized text
  target: string;     // translated text
};
type Session = { date: ISOString; sourceLang: string; targetLang: string;
                 durationSec: number; turns: Turn[] };
```

**Document layout (per page, Letter/A4, portrait):**
- Header: brand mark (文 in a `--lf-text` rounded square) + "LinguaFusion", right-aligned "SESSION TRANSCRIPT" in muted caps, under a `2px solid var(--lf-text)` rule.
- Meta row (muted 10px, `1px` bottom rule): `{date} · {time}` · `{Source} → {Target}` · `Duration {mm:ss}`.
- Body: for each turn — a small accent-colored caps line `mm:ss · SPEAKER {n}`, then the source line (`--lf-text`), then the target line (muted + italic).
- Footer (`1px` top rule, 9px muted): left "Generated offline · no data sent", right "Page {n} / {total}".

**Implementation:** generate the PDF **client-side, offline** — do NOT call a
service. Use the app's existing PDF path if any; otherwise bundle `pdf-lib` (or
`jspdf`) locally. Paginate turns: measure and break so a turn never splits across
pages; repeat header + footer on each page; compute `Page n / total` after
layout. Fonts embedded from the self-hosted WOFF2/TTF already in the app (Inter +
one italic for the target line). File name: `linguafusion-{yyyy-mm-dd}-{hhmm}.pdf`.

**Motion / feedback:** on tap, `M.exportOut(exportRow, () => showToast('Saved
{filename}'))`. Disable the menu item while rendering; show a small spinner if
> 300 ms.

**Edge cases:** no turns → item disabled. Diarization off → omit `· SPEAKER n`,
keep timestamp. Very long turn → wraps, still no mid-turn page break. RTL target
language → set `dir="rtl"` on the target line.

**Acceptance:** export a ≥ 3-turn session; open the PDF; confirm side-by-side
EN/target, correct timestamps & speaker labels, header/footer on every page,
accurate page count, no clipping, no network request fired.

---

### B2. Formality tiers  (mockup `#3d`)

**What:** every translation is offered in **three registers — Casual / Neutral /
Formal**. User picks the one the moment needs; selection is remembered.

**Where:** the translation result. Mobile = full pane (mockup `#3d`); desktop/web
= inline under the translation card. Also expose a default in Settings
("Preferred register: Casual / Neutral / Formal", default **Neutral**).

**Data:** request three variants from the local model per translation:
```ts
type Registered = { casual: string; neutral: string; formal: string };
```
Prompt the local LLM to return all three in one call (JSON) to avoid 3 round
trips. Cache per source line.

**UI (theme-aware, from mockup):**
- "You said" card with the source line.
- A 3-segment control: `Casual` · `Neutral` · `Formal`. Selected segment fills with `--lf-accent` / `--lf-on-accent`; others `--lf-chip-bg`.
- Three stacked cards, one per register, each with a small caps label. The **selected** card is fully opaque with a `1.5px solid var(--lf-accent)` border + accent label and a `✓`; the other two are dimmed (`opacity:.55`) but still readable/tappable.
- Footer: primary button `Use {Register}` (fills `--lf-accent`) + a `↺` regenerate button.

**Register labels are color-coded** (independent of theme accent, kept subtle):
casual → success/green, neutral → accent, formal → violet `#8a5cf6`. Keep these
as three fixed hues; they read as a scale.

**Behavior:** tapping a segment or a card selects that register and updates the
"active" translation used everywhere else (copy, export, TTS). Selection persists
per session and seeds from the Settings default. `↺` re-requests variants.

**Edge cases:** model returns identical strings for two registers → de-dupe
display, show "same as Neutral" note rather than a duplicate card. Model fails →
fall back to a single translation, hide the tier UI for that line.

**Acceptance:** translate a line; see three distinct German variants matching the
mockup register examples (Casual "…hört ihr mich alle gut?", Neutral "…können
mich alle gut hören?", Formal "Lassen Sie uns beginnen — können Sie mich alle gut
hören?"); switch registers and confirm the chosen one propagates to export/copy;
default respects Settings.

---

### B3. Auto-detect language reveal  (mockup `#3e`)

**What:** the app detects the spoken language automatically and shows a
**confident, animated lock-on** — a big language badge + confidence % — instead
of making the user pick.

**Where:** replaces the "STT: Auto" state at the start of capture. When STT is set
to Auto and speech begins, run detection on the first ~1–2 s of audio, then reveal.

**States (drive with a small state machine):**
1. `listening` — waveform active, caption "Listening…", no language yet.
2. `locked` — detection confident (≥ threshold, e.g. 0.85): animate the reveal.
3. `low-confidence` — below threshold: show the top guess with a "Tap to confirm" affordance instead of auto-locking.

**Reveal UI (from mockup):**
- Caption caps "LANGUAGE LOCKED".
- A 150px circle with a soft accent ring + glow (`box-shadow: 0 0 60px -10px` accent), containing the ISO code big (e.g. `ES`, 40px) and the language name under it (`Spanish`).
- A confidence meter: a track + fill sized to the percent, with the number (`98%`) in `--lf-success`.
- Live waveform below.
- A result card: source line then translated line (e.g. "Hola a todos, ¿me escuchan bien?" / "Hallo zusammen, hört ihr mich gut?").
- Sub-caption "Detected automatically · tap to override".

**Motion:** on lock, scale the badge from `.9→1` with the theme's result easing +
count the confidence number up 0→N over `--lf-dur`. Reuse `M.revealResult` for the
card. Respect `prefers-reduced-motion` (no count-up; static badge).

**Behavior:** "tap to override" opens the language list with the detected one
pre-highlighted. Detected language sets the STT source and drives translation
direction. Persist the last detected language as the new "Auto" hint.

**Edge cases:** silence / undetectable → stay in `listening`, no false lock.
Mixed languages → show the dominant one + a small "multiple detected" hint.

**Acceptance:** with STT=Auto, speak a non-default language; within ~2 s see the
lock-on badge with ISO code, language name, and a confidence % ≥ threshold; the
translation direction updates automatically; "tap to override" works; below
threshold shows the confirm affordance instead of auto-locking.

---

### B4. Conversation mode  (mockup `#3f`)

**What:** a **face-to-face** mode. Lay the phone flat on a table between two
people; the screen splits in half and the **top half is rotated 180°** so the
person across from you reads their language right-way-up.

**Where:** a new capture mode on the Speech screen (entry point: a "Conversation"
button/segment near the mic). Primarily mobile; on desktop it's a two-column
side-by-side (no rotation).

**Layout (mobile, from mockup):**
- **Top pane** — `transform: rotate(180deg)`; belongs to the person across the table ("THEM"). Shows their language label (e.g. English), their last utterance large, and its translation into your language smaller/muted below.
- **Center pivot bar** — a mic button (accent, glowing) flanked by two hairline gradient rules. This is the shared control; it does not rotate.
- **Bottom pane** — upright, yours ("YOU"). Your language label (e.g. Deutsch), your last utterance large, its translation into their language below.

**Behavior:**
- Two languages configured: **your language** and **their language**. The app auto-routes each recognized utterance to the correct pane by detected language (reuse B3 detection) and writes the translation into the opposite pane.
- Tapping the mic captures the next utterance; a subtle indicator shows which side is currently "speaking". Optionally auto-switch on detected language so neither person taps.
- Each pane shows only the **latest** exchange by default (big, glanceable); a swipe/scroll within a pane reveals history (history in that pane must also honor the rotation).
- Speaker labels: `THEM` (top), `YOU` (bottom), each with its language in accent caps.

**Theme-aware:** panes read `--lf-app-bg`/`--lf-surface-*`; labels use
`--lf-accent` (top) and `--lf-success` (bottom) to distinguish sides; the pivot
mic uses `--lf-record-*`.

**Edge cases:** both people same language → collapse to one upright pane with a
note. Rotation must not break tap targets — hit-test in rotated space (the top
mic-adjacent controls still tap correctly). Landscape/tablet → fall back to
left/right split, no rotation. Keep-awake while in conversation mode.

**Acceptance:** enter Conversation mode on a phone; the top pane renders rotated
180° and readable from across the table; speaking in either language populates
the correct pane with the utterance and the opposite pane with its translation;
the center mic works; exiting returns to the normal Speech screen.

---

### B5. Ambient ticker  (mockup `#3g`)

**What:** a **glanceable, always-listening** widget that quietly translates
overheard speech into a running one-line ticker — for travel and meetings. Older
lines fade; the current line is prominent.

**Where:** two surfaces from the same engine —
1. an **in-app Ambient panel** (a mode on the Speech screen, minimal chrome), and
2. a **home-screen / lock-screen widget** (Android App Widget; on desktop/web a
   compact always-on-top mini-window or a menu-bar/tray popover).

**UI (from mockup):**
- Rounded translucent card (`--lf-surface-*` + backdrop blur where the theme allows).
- Header: a pulsing green dot + "Ambient translate", right side "listening quietly · {SRC}→{TGT}".
- Ticker body: a short stack of recent translated lines — the **two older** lines dimmed (`rgba(...,.35)` and `.55`), the **current** line full-strength and larger (16px). New lines push in at the bottom; oldest scrolls out.
- A tiny live waveform + "now" label on the current line.

**Behavior:**
- Continuous, low-power listening; translate in near-real-time; show **only translations** (source hidden by default to stay glanceable — long-press/tap a line to reveal source).
- "Quietly" = no chimes, no full-screen takeover; it's a passive read-out.
- Cap the visible history to ~3 lines; keep a longer scrollback on tap-to-expand.
- Clear privacy affordance: the pulsing dot = actively listening; one tap pauses. Never persist audio; only keep the rolling text buffer in memory unless the user saves.

**Battery / perf:** debounce translation to phrase boundaries (don't translate
every partial token); throttle waveform to ~15 fps; suspend when screen off unless
the user pinned the widget.

**Edge cases:** no speech for N seconds → dim to an idle "listening quietly…"
state. Very fast speech → queue lines, never drop the current one. Widget tap →
opens the full Ambient panel in-app.

**Acceptance:** start Ambient mode; speak/play foreign speech nearby; see a
running ticker of translated lines with the current line prominent and older ones
faded; the listening dot pulses; tap-to-pause stops capture; the widget surface
mirrors the in-app panel.

---

### B6. Capture mode: push-to-talk vs continuous  (mockup `#3h`)

**What:** promote capture mode from a buried setting to a **first-class screen
state**. A segmented control switches between **Push-to-talk** and **Continuous**,
and the whole recorder area changes to show which is armed.

**Where:** the Speech screen recorder region.

**UI (from mockup):**
- A 2-segment control at the top of the recorder: `Push-to-talk` | `Continuous`. Selected segment fills `--lf-accent`/`--lf-on-accent`.
- **Push-to-talk state:** caption "Hold to speak · release to translate"; a large (~172px) circular button. While held it enters a **HOLDING** state — scales up slightly, gains a thick accent ring (`box-shadow: 0 0 0 10px accent-16%, 0 0 60px accent`), glyph + "HOLDING" label; waveform active only while held. On release → translate.
- A secondary info card below describes the *other* mode: an `∞` glyph + "Continuous mode — Hands-free: keeps listening & translating until you stop it." Tapping it (or the segment) switches.
- **Continuous state (mirror):** the big button becomes a toggle (Start/Stop); caption "Listening continuously · tap to stop"; the info card describes Push-to-talk instead.

**Behavior:**
- PTT: `pointerdown` starts capture + `M.setRecording(btn,true)` + `M.setWaveLive(wave,true)`; `pointerup`/`pointerleave`/`pointercancel` stops and fires translation. Prevent context-menu/scroll while holding.
- Continuous: tap toggles a persistent recording session; explicit Stop required.
- Remember the last-used mode per platform (`localStorage["lf-capture-mode"]`).
- Keyboard (desktop): Space = hold-to-talk in PTT mode; Space = toggle in Continuous.

**Theme-aware:** button uses `--lf-record-bg/-radius/-shadow/-glyph`; ring color
from `--lf-accent`; the "HOLDING" pulse uses the theme's `--lf-record-ring`
(brutalist/kiosk = no ring, hard state).

**Edge cases:** PTT released after < ~250 ms → treat as tap, show "Hold to speak"
hint, don't fire an empty translation. Mic permission denied → both modes show a
"Grant microphone access" state. Switching mode mid-capture stops the current
capture cleanly.

**Acceptance:** toggle the segmented control and confirm the recorder restructures
between the two states (button size/label/caption + which info card shows);
press-and-hold captures only while held and translates on release; continuous
toggles a persistent session; last mode is remembered; Space-key behavior matches
per mode.

---

## Build order & global acceptance

Suggested order (independent, but this minimizes rework):
1. **A1 + A2** themes (fast, isolated — validates the token pipeline still holds).
2. **B6 capture mode** (touches the recorder other features build on).
3. **B3 auto-detect** (its detection is reused by B4 conversation mode).
4. **B4 conversation mode**, **B2 formality tiers**, **B1 PDF export**, **B5 ambient**.

**Global acceptance (run once at the end):**
- All 18 themes still switch cleanly; the 2 new themes restructure layout, not just color.
- Every new surface reads `--lf-*` tokens — grep the diff for hardcoded hex/px fonts/shadows and remove them (exception: the 3 fixed register hues in B2 and the 180° rotation in B4).
- All new text meets WCAG AA contrast on its surface under every theme.
- No network requests from any feature (offline app): PDF, detection, translation, registers all run local.
- Nothing clipped or overlapping at mobile (360–430px) and desktop (≥ 1024px) widths.
- `prefers-reduced-motion` honored on B3 reveal, B6 holding pulse, B5 ticker.
- Compare each built feature against its Round-3 mockup (`#3a`–`#3h`) — layout, copy, and states must match before calling it done.

---
