# Design audit, 2026-11-10

`/impeccable audit` of `app/` at the end of part 13 slices 3 and 4 (branch `part/13-caddie-panel`), measured against `docs/design.md`. Evidence: the Impeccable detector over `app/src`, a source review of every component, and a dev-server pass at 1024 x 768 and at 375 x 812 (emulated, Chromium, mouse events only; touch gestures were not synthesised). Nothing was fixed in this pass.

## Health score

| # | Dimension | Score | Key finding |
| --- | --- | --- | --- |
| 1 | Accessibility | 2 | Every control is 28 to 29 px tall; the design floor is 48 px (56 px for lie buttons) |
| 2 | Performance | 3 | AimArrow rebuilds its GeoJSON on every store change, including each drag frame |
| 3 | Responsive design | 1 | At 375 px the panel stays docked right (240 px) and the map shrinks to 135 px |
| 4 | Theming | 1 | No tokens: Tailwind slate and emerald everywhere, dark only, viridis heatmap |
| 5 | Implementation integrity | 3 | Product-specific structure; one detector warning, arguably a false positive |
| **Total** | | **10/20** | **Acceptable: significant work needed** |

## Implementation integrity verdict

Pass. The screen is unmistakably this product: a rotated satellite map, a strokes-to-go heatmap, a ball marker, an aim arrow with a dispersion ellipse, and a caddie panel. Nothing is placeholder or decorative. The detector reported one item, `text-slate-900 on bg-emerald-500` on the active lie button (`LieButtons.tsx:23`): dark text on a mid green reads fine, so the contrast concern is a false positive, but the finding still matters for another reason (see P1 accent below).

## Executive summary

- Audit health score: 10/20 (Acceptable)
- Issues: 2 P0, 6 P1, 5 P2, 3 P3
- Top issues: no phone layout (panel docked right at 375 px, header wraps to three rows); touch targets at 28 to 29 px; no design tokens and a dark-only theme where the reference asks for light by default; the accent colour used on the lie buttons and the header instead of only the recommendation; viridis heatmap where the reference specifies the warm six-stop ramp.
- Next steps: `/impeccable adapt` for the bottom-sheet layout and targets, then `/impeccable colorize` to install the tokens and the heatmap ramp, then `/impeccable typeset` for Inter and tabular numerals, then `/impeccable clarify` for the copy rules, then `/impeccable polish`.

## Findings

### P0 Blocking

**[P0] No phone layout.** `App.tsx` `<main>`, `CaddiePanel.tsx` `<aside>`. At 375 px the panel keeps its desktop docking (240 px wide beside a 135 px map) and the header wraps to three rows (126 px tall), so the map is unusable on the course. `docs/design.md` 4.1 specifies a bottom sheet with a collapsed 140 px state and a 56 px top bar. Category: Responsive. WCAG 1.4.10 (reflow). Fix: bottom sheet below the map on narrow viewports, dock right only from 768 px. Command: `/impeccable adapt`.

**[P0] Touch targets below the floor.** `LieButtons.tsx` (28 px tall), `App.tsx` pickers (29 px), MapLibre controls (29 px). The reference requires 48 px minimum and 56 px for the lie row, pressed with a glove. WCAG 2.5.8 (24 px minimum) passes, but the product requirement fails. Category: Accessibility. Fix: 56 px lie segments with 8 px gaps, 48 px pickers and map buttons. Command: `/impeccable adapt`.

### P1 Major

**[P1] No design tokens.** All components use Tailwind palette classes (`bg-slate-900`, `text-emerald-300`, `border-slate-700`) and literal hex in `HoleMap.tsx` `LIE_COLOURS`, `BallMarker.tsx`, `AimArrow.tsx`, `heatmap.ts` `STOPS`. The reference defines `--surface`, `--ink`, `--rec`, the `--t-*` terrain set and the `--h0` to `--h5` ramp. Category: Theming. Fix: declare the tokens in `index.css` under `@theme` and reference them everywhere; terrain fills from `--t-*`. Command: `/impeccable colorize`.

**[P1] Dark theme only, light required by default.** `App.tsx` root is `bg-slate-900 text-slate-100` with no light variant and no `data-theme` switch. The reference (section 3, Mode) asks for a near-white panel over the satellite image by default and dark as a user toggle. Category: Theming. Fix: light tokens on `:root`, dark under `:root[data-theme="dark"]`, a toggle in the overflow menu. Command: `/impeccable colorize`.

**[P1] Accent colour spent on the wrong elements.** Emerald appears on the header recommendation line (`App.tsx`), the expected-strokes figure (`CaddiePanel.tsx`), and the active lie button (`LieButtons.tsx:23`), while the aim arrow and ellipse are white (`AimArrow.tsx` `ARROW_COLOUR`). The reference reserves `--rec` for exactly the arrow, the club chip and the expected-strokes figure, at most three at once. Category: Theming. Fix: arrow and club chip take `--rec`; lie buttons use `--ink` on `--surface-2` with a filled neutral for the active segment; drop the header duplicate. Command: `/impeccable quieter`.

**[P1] Heatmap ramp is viridis.** `heatmap.ts` `STOPS` is the viridis sequence. The reference (section 5) specifies the warm ramp `#1D2B53, #2E6F9E, #5FB89B, #E8D45A, #F08A24, #B3261E`, citing Barua 2022 on legibility over aerial imagery. Category: Theming. Fix: replace the stops with the `--h0` to `--h5` values; the domain `[par - 1, par + 3]` is already right. Command: `/impeccable colorize`.

**[P1] Terrain fills off the fixed colour-way.** `HoleMap.tsx` `LIE_COLOURS` uses Tailwind-adjacent hexes; the reference fixes `--t-fairway #7FBF6A`, `--t-water #4C9BE8`, `--t-ob #C8102E` and so on, so terrain reads the same on every hole. Fill opacity 0.18 is within the 35 percent ceiling. Category: Theming. Fix: read the `--t-*` tokens. Command: `/impeccable colorize`.

**[P1] Typeface and numerals.** Computed font is the system stack; the reference specifies Inter with `font-variant-numeric: tabular-nums` on every number so yardages do not jump. No element has tabular figures. Text sizes present are 12, 14, 18 and 36 px; the reference's scale is 13 caption and label, 17 body, 32 big number, 56 hero, with 13 px as the floor (the 12 px MapLibre control text is below it). Category: Accessibility and theming. Fix: load Inter, set the scale as tokens, `tabular-nums` on the number elements. Command: `/impeccable typeset`.

### P2 Minor

**[P2] Copy does not follow the reference.** `CaddiePanel.tsx` prints `driver` (lower case club id) and `Aim 4 deg left of pin`; `App.tsx` header prints `driver at -4 deg · 4.46 strokes` and `ball 80.0, 55.0 m`. Section 7 wants display names (`Driver`, `7 iron`, `Sand wedge, 70 yd`), aim in yards (`Aim 8 yards left of the pin`), strokes with one decimal and no internal coordinates. Note that yards-left needs the carry: `carry * tan(dir)`, which `AimArrow.aimGeometry` already computes. Category: Implementation integrity. Command: `/impeccable clarify`.

**[P2] Missing phone viewport directives.** `index.html` has `width=device-width, initial-scale=1.0` only; no `viewport-fit=cover`, no `env(safe-area-inset-*)` padding, no `overscroll-behavior-y: contain`, so dragging the map on a phone can trigger pull-to-refresh and the panel can sit under the home indicator. Category: Responsive. Command: `/impeccable adapt`.

**[P2] AimArrow recomputes on every store change.** `AimArrow.tsx` effect depends on bundle, player, ball, lieOverride and recommendation and rebuilds the GeoJSON and calls `setData` each time; during a marker drag the store only updates on `dragend`, so this is bounded today, but part 12's worker will update the recommendation per drag frame. Category: Performance. Fix: memoise the geometry on the inputs and skip `setData` when unchanged. Command: `/impeccable optimize`.

**[P2] Header duplicates the panel.** `App.tsx` shows the club, direction and strokes in the top bar as well as in the panel, with the raw ball coordinates. The reference's top bar holds hole, par and yardage, tee and mode only. Category: Implementation integrity. Command: `/impeccable distill`.

**[P2] States not designed.** No loading skeleton (map and panel appear empty, then fill), no "ball on green" putts figure (the panel says "No shot from here"), no water or OB state, and the `No ball` copy says "Click the map" where the reference says "Tap the map or turn on GPS". Section 4.2 lists eight states. Category: Implementation integrity. Command: `/impeccable harden`.

### P3 Polish

**[P3] `lie` label not associated.** `LieButtons.tsx` renders a visual `lie` span; the group has `aria-label="Lie"`, so screen readers are fine, but the span is noise. Fold it into the group label or make it the visible legend of a `fieldset`. Category: Accessibility. Command: `/impeccable polish`.

**[P3] Ball marker accessible name.** The MapLibre marker exposes `button "Map marker"`. Name it `Ball` with its yardage to the pin. Category: Accessibility. Command: `/impeccable polish`.

**[P3] Reduced motion.** Only MapLibre's stylesheet carries a `prefers-reduced-motion` rule. Nothing in the app animates yet; when part 13's play-it-out hop lands it needs a reduced-motion path that still steps the ball shot to shot. Category: Accessibility. Command: `/impeccable animate` (within the hop only; the reference forbids other motion).

## Patterns

- Colour is chosen per component from the Tailwind palette rather than from a token set, in all six components. Installing the reference tokens once fixes most of the theming findings together.
- The layout was built desktop first (part 10 and 11 slices were checked at 1024 px). The reference asks for the phone layout first with desktop inheriting it.

## Positive findings

- Semantic landmarks are present: `header`, `main`, `aside` with a label, a `group` with a label; one `h1`; `lang="en"`; real `button` elements with `aria-pressed` on the toggles; `label` wraps each `select`.
- Contrast on the current dark surface is strong: secondary text `slate-400` on `slate-900` is about 7:1.
- The heatmap is drawn as 5 m cells with nearest resampling, as section 5 requires; terrain fills sit at 18 percent, under the 35 percent cap; the map is fixed hole-up with a fit-to-grid on load.
- The aim arrow already carries the 1 sigma ellipse the reference calls for, and no decoration competes with the map.
- No horizontal overflow at 375 px; the page itself does not scroll.

## Recommended actions

1. **[P0] `/impeccable adapt`**: bottom-sheet panel with collapsed and expanded heights, 56 px top bar, 56 px lie segments, 48 px pickers and map buttons, `viewport-fit=cover`, safe-area padding, `overscroll-behavior-y: contain`.
2. **[P1] `/impeccable colorize`**: install the section 3 tokens in `index.css`, light by default with the dark set under `data-theme`, the warm heatmap ramp, the fixed terrain colour-way.
3. **[P1] `/impeccable quieter`**: `--rec` on the arrow, club chip and expected-strokes figure only; neutral lie buttons; no accent in the header.
4. **[P1] `/impeccable typeset`**: Inter, the five-role type scale, tabular numerals on every number, 13 px floor.
5. **[P2] `/impeccable clarify`**: club display names, aim in yards, one-decimal strokes, no coordinates in the UI.
6. **[P2] `/impeccable harden`**: the eight states in section 4.2.
7. **[P2] `/impeccable optimize`**: memoise AimArrow geometry before the worker lands.
8. **[P3] `/impeccable polish`**: labels, marker name, reduced-motion path for the hop.

Not run: `/impeccable init` (writes `PRODUCT.md`) and the `DESIGN.md` generation that section 8 of the reference calls for; both are a separate step.
