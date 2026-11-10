# Caddie: design reference

How the app should look and behave, what it borrows from existing golf apps and outdoor tools, and how the agent uses Impeccable to shape, build, and audit it. Read this before any work in `app/src/components/`. The root `CLAUDE.md` and `app/CLAUDE.md` still govern code; this file governs what the user sees.

## 1. Who this is for and when they look at it

Two moments, two postures.

- **At a desk (M1).** Diego or Hylton, laptop, exploring a hole: click around, watch the heatmap, run play-it-out, compare penalty modes. Dense information is fine. Mouse precision is available.
- **On the course (M2).** Phone in one hand, often gloved, in direct sun, between shots, 10 to 20 seconds of attention. The only things that matter are: where am I, how far to the pin, what club, where to aim, how many strokes from here. Everything else is one tap away or hidden.

Design for the second posture and let the first inherit it. A desk user can always read a phone layout; a golfer cannot operate a desk layout on the 11th fairway.

## 2. What the research says existing apps do

Full notes with sources are in `research_notes/Golf caddie app interface patterns/`. The patterns worth copying, and the ones to avoid:

**Copy**

1. **One map, one number hierarchy.** Arccos builds the whole hole screen around a tiltable, pinch-zoomable map with distance controls on the right edge and the plays-like number in a single accent colour; Hole19 auto-places a target on the front of the green at each hole change and keeps front/center/back in a pull-down tray. The map is the screen; numbers sit on it, not beside it. ([Arccos in-play](https://au.arccosgolf.com/blogs/community/navigating-the-new-in-play-experience), [Hole19](https://help.hole19golf.com/hc/en-us/articles/202618282))
2. **Draggable target with two distances.** Hole19 and GolfLogix show you-to-target and target-to-green as the target moves; Golfshot adds an orange Reset when the target has been dragged off its default. Our aim arrow is this target, chosen by the solver instead of the user, and the user should still be able to drag it to see what their own idea costs. ([GolfLogix review](https://pluggedingolf.com/2019-golflogix-gps-app-review/), [Golfshot guide](https://szuserguides.s3.amazonaws.com/en/golfshot-ios-user-guide.pdf))
3. **Dispersion as a shape, not a dot.** Shot Scope MyStrategy draws a cone centred on a movable target line with a scatter of the last 30 shots, and prints expected-score deltas by landing zone (water costs 1.2, 3-wood vs driver costs 0.4). Arccos AI Strategy draws green safe and red avoid zones around the green with an "xScore". Shot Pattern uses an arc for tee shots and a circle for approaches. Our 1-sigma ellipse at the end of the aim arrow is the same idea. ([MyStrategy review](https://pluggedingolf.com/shot-scope-mystrategy-review/), [Arccos AI Strategy](https://www.arccosgolf.com/blogs/community/introducing-arccos-ai-strategy-beta), [Shot Pattern](https://apps.apple.com/us/app/shot-pattern-golf-gps/id6447127454))
4. **Big numbers mode.** Garmin watches offer a layout with nothing but the yardage; Golfshot's watch auto-advances holes. On the course our panel should degrade to three large figures. ([Garmin S70 review](https://pluggedingolf.com/garmin-approach-s70-golf-smartwatch-review/))
5. **Three-state location button.** CalTopo and FATMAP use off / centred north-up / heading-up, and pan-to-unlock; CalTopo users report heading-up feels dizzying on foot. We fix the map tee-at-bottom (hole-up) instead of device-heading-up, which is stable and still reads naturally. ([CalTopo](https://blog.caltopo.com/2024/05/22/new-feature-heading-up/), [FATMAP](https://about.fatmap.com/journal-digest/lock-and-follow-mode-easy-navigation))

**Avoid**

- The recurring complaints across Golfshot, 18Birdies, Arccos, SwingU: battery drain from continuous GPS, slow GPS lock with drifting yardages, blank maps offline, too much phone-out time, poor sunlight legibility, paywall interruptions, multi-tap shot logging. ([2026 ranking roundup](https://unstar.app/blog/golfshot-18birdies-arccos-swingu-thegrint-hole19-golf-gps-apps-ranked-2026), [SwingU review](https://mygolfspy.com/we-tried-it/swingu-app-review/))
- Hiding the recommendation behind a settings toggle (18Birdies puts club recommendations under Tools > Settings). Ours is the point of the app; it is always on screen. ([18Birdies help](https://help.18birdies.com/article/660-true-distance-club-recommendations))
- Heatmaps nobody can read over grass. Schoolfield's strokes-to-go maps work because he uses a strong blue-lime-red ramp with a separate "penalty" map; Hacker News readers' confusion was about sampling artifacts, not colour. ([Wigs on the Green](https://golfcoursewiki.substack.com/p/i-spent-the-last-month-and-a-half), [HN thread](https://hn.nuxt.dev/item/47037568))

## 3. Visual direction

**One sentence.** A satellite photo of the hole with a quiet instrument panel laid over it; the only saturated colour is the recommendation.

**References.** FATMAP (now Strava) map styling: a written map key and fixed colour-ways so the terrain reads the same on every hole ([FATMAP map design](https://contra.com/p/s3FWsLsc-fatmap-now-strava-map-design)). Material's dark theme for the optional night mode ([Material dark theme](https://design.google/library/material-design-dark-theme)). Garmin's big-numbers posture for the on-course panel. Nothing from consumer golf apps' chrome; most of it is cluttered.

**Mode.** Light UI by default. NN/g's review of the legibility literature finds dark text on light wins for normal vision, with the advantage shrinking but not reversing in bright daylight, and DisplayMate's ambient-light testing shows reflections swamp dark backgrounds first ([NN/g dark mode](https://www.nngroup.com/articles/dark-mode/), [DisplayMate](https://displaymate.com/Smartphone_Brightness_ShootOut_1.htm)). The panel is near-white over the satellite image; dark mode is a user toggle for dusk, not the default.

### Tokens (CSS variables, mapped into Tailwind)

```css
:root {
  /* surfaces */
  --surface:        #FAFAF7;   /* panel over map */
  --surface-2:      #FFFFFF;
  --ink:            #111714;   /* primary text, 15.6:1 on surface */
  --ink-2:          #4B554F;   /* secondary text, 7.1:1 */
  --line:           #D7DAD5;
  /* the one accent: recommendation */
  --rec:            #0A7C3E;   /* arrow, club chip, expected strokes */
  --rec-ink:        #FFFFFF;
  /* terrain overlays (fixed on every hole, low opacity fills) */
  --t-fairway:      #7FBF6A;
  --t-rough:        #4F8A3F;
  --t-green:        #A8E08D;
  --t-bunker:       #E6D3A3;
  --t-water:        #4C9BE8;
  --t-ob:           #C8102E;
  --t-tee:          #DADADA;
  /* heatmap: 6-stop warm ramp, see section 5 */
  --h0: #1D2B53; --h1: #2E6F9E; --h2: #5FB89B; --h3: #E8D45A; --h4: #F08A24; --h5: #B3261E;
  /* status */
  --ok: #0A7C3E; --warn: #B8860B; --bad: #B3261E;
  --gps: #1A73E8;             /* position dot and accuracy circle, Google Maps convention */
}
:root[data-theme="dark"] {
  --surface: #121212; --surface-2: #1E1E1E; --ink: rgba(255,255,255,.87); --ink-2: rgba(255,255,255,.60); --line: #2A2A2A;
  --rec: #4CC38A; --rec-ink: #0B1F14;
}
```

Rules: `--rec` appears on at most three elements at once (arrow, club chip, expected-strokes figure). Terrain fills never exceed 35% opacity. No gradients on UI surfaces. Red is reserved for OB and the worst heatmap stop; never use it for buttons.

### Type

Inter for everything, with `font-variant-numeric: tabular-nums` on every number so digits do not jump as yardages change ([tabular nums](https://dev.to/alanwest/tabular-numbers-in-css-font-variant-numeric-vs-monospace-hacks-25cn)). Scale, in CSS px on a 390 px phone:

| Role | Size / weight | Where |
| --- | --- | --- |
| Hero number | 56 / 700 | distance to pin, on course |
| Big number | 32 / 600 | expected strokes, club |
| Label | 13 / 500, uppercase, 0.06em tracking | "TO PIN", "EXPECTED" |
| Body | 17 / 400 | panel text (Apple's default body size) |
| Caption | 13 / 400 | legends, GPS accuracy |

Minimum text size anywhere is 13 px; Apple's floor is 11 pt and we stay above it ([Apple HIG accessibility](https://developer.apple.com/design/human-interface-guidelines/accessibility)). No thin weights.

### Touch and layout

- Every tappable control is at least 48 x 48 CSS px with 8 px between neighbours (Material's minimum, above WCAG 2.2's 24 px and Apple's 44 pt) ([WCAG target size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)). Lie buttons and the GPS toggle are 56 px tall because they are pressed with a glove; Garmin's own glove guidance is "press firmly, one action at a time", so make each press unambiguous ([Garmin S6 manual](https://www8.garmin.com/manuals/webhelp/approachs6/EN-US/GUID-0A1CF020-3079-4907-999A-1D674C00AE64.html)).
- Primary actions live in the bottom third of the screen, reachable by the right thumb (49% of users hold one-handed, 67% of those right-thumbed) ([Hoober grip study](https://uxmatters.com/mt/archives/2013/02/how-do-users-really-hold-mobile-devices.php)).
- Safe areas: `viewport-fit=cover` and `env(safe-area-inset-*)` padding on the panel; `overscroll-behavior-y: contain` so dragging the map never triggers pull-to-refresh ([web.dev PWA design](https://web.dev/learn/pwa/app-design)).

## 4. Screens

### 4.1 Hole screen (the only screen)

Phone, portrait. From top to bottom:

1. **Top bar, 56 px.** Hole number (tap to pick 10, 11, 12), par and yardage from the selected tee as caption text, tee picker, penalty-mode picker as a three-segment control. On the course the two pickers collapse into an overflow menu.
2. **Map, fills the rest.** Satellite, rotated so the hole runs bottom to top. Terrain polygons at low opacity. Heatmap at 55% opacity, toggleable. Ball marker. Aim arrow from the ball with the 1-sigma ellipse at its end. Pin flag. GPS dot and accuracy circle when enabled. Right edge, stacked 48 px buttons: heatmap on/off, recenter, GPS on/off. Nothing else on the map.
3. **Caddie panel, bottom sheet.** Two heights.
   - **Collapsed (default on course), ~140 px:** three columns. Left: hero distance to pin in yards, label "TO PIN". Middle: club name as a `--rec` chip, label "CLUB". Right: expected strokes as a big number, label "EXPECTED", with the aim-at-pin baseline underneath in caption ("Pin with 7i: 3.9"). The lie row sits above the columns: four 56 px segments, Auto, Fairway, Rough, Bunker, the active one filled.
   - **Expanded (drag up or tap), ~60% of screen:** adds the aim description ("Aim 8 yards left of the pin"), the Play it out button, and after a run the animated sequence summary and the histogram.
4. **Status line, 24 px, bottom.** GPS accuracy in metres and a stale-fix warning, or "Offline, holes cached" when the service worker is serving.

Desktop is the same layout with the panel docked right as a 360 px column and the map taking the rest; nothing is redesigned.

### 4.2 States

| State | What the user sees |
| --- | --- |
| Loading bundle | Map with satellite only, panel skeleton, no spinner over the map |
| No ball placed | Panel reads "Tap the map or turn on GPS"; arrow hidden |
| Ball on green | Panel shows putts expected instead of a club; arrow hidden |
| Ball in water or OB | Panel shows the penalty rule in force and the drop position marker |
| GPS acquiring | Grey dot, "Finding you…" in the status line, panel keeps the last manual ball |
| GPS stale (> 10 s) | Dot outlined, accuracy circle dashed, status line amber |
| Offline | Status line "Offline"; everything else unchanged |
| Worker slow | Panel shows the grid recommendation immediately, replaces it with the rollout result when it arrives, no flicker (same layout, numbers update) |

### 4.3 Play it out

Pressing the button: the ball marker hops shot to shot at 600 ms per shot along a dashed path, the panel's club chip updates to the club just hit, and the sequence ends with the score for that run shown large. Then the histogram slides in under it: bars from par minus 2 to par plus 4, the mean marked, P(par + 3 or worse) as a caption. A second press replays with a new seed. Reset clears the path. This is the demo's centrepiece; it must read on a phone screen in a video.

## 5. Heatmap

- **Ramp.** A warm sequential ramp (dark blue to teal to yellow to orange to red, the `--h0` to `--h5` stops) rather than viridis. Barua's AutoCarto 2022 study tested colour ramps over aerial imagery and found viridis performed poorly while a warm "ironbow" ramp was read fastest and most accurately ([Barua 2022](https://cartogis.org/docs/autocarto/2022/docs/presentations/session6_barua_presentation.pdf)). Sequential, monotonic in lightness, no red-green pairing, per the Matplotlib colormap guidance ([Matplotlib colormaps](https://matplotlib.org/stable/users/explain/colors/colormaps.html)).
- **Domain.** Clamped to [par minus 1, par plus 3] strokes so the three holes share a scale and a colour means the same thing on each.
- **Opacity.** 55% over satellite. Terrain polygons drawn above the heatmap at 25% so fairway edges stay legible.
- **Legend.** A horizontal bar in the expanded panel, labelled in strokes at both ends and at par, never on the map itself.
- **Cells.** Draw cells as the 5 m squares they are; do not smooth. A blurred heatmap implies precision the model does not have.

## 6. Map behaviour

- Fixed orientation: hole runs bottom to top. No heading-up mode. Recenter button fits the hole's grid bounds.
- Pan and zoom free within the hole bounds plus 100 m; snapping back is a tap on recenter, never automatic.
- Tap anywhere in the grid places the ball. Drag the ball marker to move it. Tapping while GPS is following places the ball and pauses following for 10 s; the GPS button returns to following.
- The aim arrow is draggable too: dragging it recomputes expected strokes for the user's own aim (via the worker in M2, nearest-cell Q in M1) and shows "Your aim: 4.1, Caddie: 3.8" until released or reset.
- GPS dot and accuracy circle follow the Google Maps convention: solid dot with a translucent circle whose radius is the reported accuracy, grey dot when there is no fix ([Google Maps help](https://support.google.com/maps/answer/2839911?hl=en)). Note the Geolocation API's `accuracy` is a 68% confidence radius, not 95% ([MDN accuracy](https://developer.mozilla.org/en-US/docs/Web/API/GeolocationCoordinates/accuracy)).

## 7. Copy

- Clubs by the names on the sticks: "7 iron", "5 hybrid", "Sand wedge", "Driver". Partial wedges as "Sand wedge, 70 yd".
- Aim as the golfer would say it: "Aim 8 yards left of the pin", "Aim at the pin", "Lay up to 110".
- Strokes with one decimal: "3.8 expected". Never "value" or "utility" in the UI.
- Penalty modes named plainly: "Mulligan", "Drop", "Replay" with a one-line explanation in the picker.
- No exclamation marks, no coaching tone, no emoji.

## 8. Working with Impeccable

Impeccable is installed from the project root with `npx impeccable skills install` (or `/plugin marketplace add pbakaus/impeccable` in Claude Code). It writes and reads a root `DESIGN.md`; that file is generated from this document, not the other way round. Commands: [Impeccable README](https://cdn.jsdelivr.net/npm/impeccable@2.3.2/README.repo.md).

**Before part 10 (first UI code):**

1. `/impeccable init`. When it asks about the product and audience, answer from sections 1 and 3 of this file. When it offers to write `DESIGN.md`, let it, then reconcile: the tokens in section 3 win over anything it invented. Commit `PRODUCT.md` and `DESIGN.md` at the repo root.
2. `/impeccable shape` for the hole screen, pasting section 4.1 as the brief. Keep its plan if it matches; where it disagrees with this file, this file wins and the disagreement is noted in the PR.

**Per app part (10, 11, 13, 14):**

3. Build the slices as the part file says. Use `/impeccable craft` only for a component whose layout is not pinned down here (the histogram, the expanded panel), never for the map or the collapsed panel, which are specified.
4. After the part's last slice, before the PR: `/impeccable critique` on the screen, then `/impeccable audit`. Fix every audit item in the accessibility and responsiveness categories; log performance items as follow-ups unless they affect the map frame rate.
5. `/impeccable polish` once per milestone (after part 13 for M1, after part 14 for M2), not per part.

**Targeted commands, when a specific problem shows up:** `typeset` if numbers do not line up, `layout` if the panel feels crowded, `clarify` for copy that fails section 7, `adapt` after testing on a 375 px phone, `harden` before M2 for offline and stale-GPS states, `quieter` if an audit finds more than one accent colour on screen.

**Never run:** `bolder`, `delight`, `overdrive`, `animate` beyond the play-it-out hop. The surface is a satellite photo and an instrument panel; decoration competes with the only thing the golfer needs to read.

**Acceptance for any UI PR:** `/impeccable audit` reports no accessibility or responsiveness failures; every number uses tabular figures; `--rec` appears on at most three elements; every tappable control is at least 48 px; the collapsed panel is readable at arm's length on a phone in sunlight (test it outdoors once, really).

## 9. Open questions to settle on the first real screen

- Panel background: solid `--surface` or 92% with backdrop blur? Blur costs frames on older phones; decide after measuring on Diego's phone.
- Whether the heatmap defaults on or off on the course. On is better for the video; off is probably better for a golfer. Ship a remembered toggle and decide from use.
- Yards everywhere, including the status line's GPS accuracy? Accuracy in metres is what the API gives and what golfers do not think in; show it as "±6 yd".
