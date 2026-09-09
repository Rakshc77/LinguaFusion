# LinguaFusion cloud UI — approved design

Updated September 9, 2026. Applies to `cloud_api/web`, including its Android
WebView. The native Windows application and PC-paired web UI are separate.

| Look | Background | Foreground | Accent |
| --- | --- | --- | --- |
| Studio day | #f4efe4 parchment | #2b2622 brown ink | #b04a2f terracotta |
| Studio night | #1a1015 plum | #fce8ec | #f24e7a Sunset rose |
| Minimal day | #fafafa | #181818 | #202020 |
| Minimal night | #121212 | #f4f4f4 | #f4f4f4 |

Studio day inherits the old Warm Editorial combination. Secondary text is
darkened for readability. Studio night uses dark text on its rose button for
contrast. Minimal uses flat neutral surfaces without decorative shadows.

Only two themes; Day/Night is a separate setting. Store `lf-theme`, `lf-mode`
and `lf-font` independently. Legacy themes migrate without losing selected
brightness or font. “Match the look” is the new-install font default; existing
explicit font preferences are retained. Use only local/system font stacks.

Keep all six feature destinations and real copy/export actions. Use consistent
inline SVG line icons, visible keyboard focus, wrapping actions, 44px or larger
action targets and opaque bottom navigation with safe-area clearance.
Translation consent must remain outside the fieldset it enables.

The reviewed images are concepts, not runtime screenshots. Production retains
paid consent wording, real download format controls, and feature availability
gating. Offline controls must not imply an available engine before implementation.

Implementation: `themes.mjs`, `linguafusion-themes.css`, `pilot.css`, `index.html`
and appearance wiring in `pilot.mjs`. Cache version: `linguafusion-cloud-v3-appearance`.
