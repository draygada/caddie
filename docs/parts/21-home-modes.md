# Part 21: home page and two modes

Branch `part/21-home-modes`. Scope: `app/src/App.tsx`, `app/src/components/Home.tsx`, `app/src/components/HoleScreen.tsx`, `app/src/components/GpsBadge.tsx`, `app/src/components/HoleMap.tsx`, `app/src/components/CaddiePanel.tsx`, `app/src/hooks/useGps.ts`, the `screen` field in `app/src/store.ts`, their tests. Depends on parts 13, 14, 15.

## Purpose

The app has grown two jobs that share one screen: exploring a hole at a desk, and playing it with GPS. A GPS toggle, a Hit button, a learn switch and a Play it out button all on one panel is too much for either job. This part adds a home page that asks which job the user is doing, and gives each one a screen with only its own controls. GPS stops being a toggle: it is on in Play and absent in Simulate.

This supersedes the GPS toggle button of part 14 and section 4.1 of `docs/design.md` ("the only screen").

## The three screens

| Screen | For | Has | Does not have |
| --- | --- | --- | --- |
| **Home** | Choosing | Two large cards: "Simulate a hole" and "Play with GPS" | A map |
| **Simulate** | The desk: any hole, any spot | Hole, tee and penalty-mode pickers, tap or drag to place the ball, recommendation, aim text, Play it out | GPS, shot logging, the learn switch |
| **Play** | The course | GPS always on, accuracy circle, recommendation, Hit and finish buttons, "Ball here?", the learn switch, export | A GPS toggle, Play it out |

- **Home is always the first screen.** `screen` is not persisted. Tapping "Play with GPS" is the user gesture iOS Safari needs before it hands out a position, which is the job the toggle used to do.
- **A way back.** Both hole screens have a Home button at the left of the top bar. Leaving Play stops the GPS watch.
- **Tapping the map still moves the ball in Play.** It is the manual correction part 14's follow rule already allows (GPS writes are held for 10 s after it).
- **GPS refused or unavailable in Play.** The panel says so in plain words with a "Try again" button (a fresh gesture) and a line that Simulate works without location. The rest of the panel still works from a tapped ball.
- **The bundle keeps loading on Home**, so the hole and its satellite tiles are cached before the user picks a mode.

## The lie is always detected

The lie row of part 11 (Auto, Fairway, Rough, Bunker) is removed from both modes. The lie is always read off the map at the ball, and the panel shows it as one read-only line, "Ball is in the fairway". `lieOverride` stays in the store, always null, so nothing downstream changes; `LieButtons.tsx` is deleted. To correct a wrong lie the player moves the ball. This supersedes slice 5 of part 11 and the lie row in `docs/design.md` section 4.1.

## No heatmap in the app

The strokes-to-go heatmap layer, its toggle button on the map and its legend in the panel are removed from both modes. The map shows the satellite image, the terrain outlines, the ball, the aim and the pin. `lib/heatmap.ts` stays, unused by the app, so the layer can return; the solver still writes its own heatmap figures. This supersedes the heatmap slices of part 10 and `docs/design.md` section 5 for the app.

## Setup before the hole, and no top bar

Choosing a mode on Home opens a second step that asks two things: the starting hole (10, 11 or 12, nothing else) and the tees. "Start" opens the hole screen. The toy hole is no longer offered in the app.

The top bar is removed from the hole screen, so the hole and the tees cannot be changed in the middle of a hole. Everything it carried moves or goes:

| Was in the top bar | Now |
| --- | --- |
| Hole, par, yardage, tees | One read-only line at the top of the bottom panel: "Hole 11 · Par 4 · 342 yd · Black tees" |
| Hole picker, tee picker | The setup step only |
| Penalty-mode control | Removed; the app always uses Drop, the rule on a real course. Mulligan and Replay remain solver modes |
| Home button | "End round" in the expanded panel |
| Theme toggle | Home |

The expanded panel also has "Next hole", which loads the next of 10, 11, 12 with the same tees and is absent on hole 12. If the chosen hole has no bundle yet, the setup step says so and Start is disabled.

## Interfaces

```ts
// store.ts
export type Screen = 'home' | 'simulate' | 'play'
// State gains: screen: Screen (default 'home'); setScreen: (s: Screen) => void

// useGps.ts
export function useGps(enabled: boolean, attempt?: number): void   // a new `attempt` restarts the watch

// GpsBadge.tsx
export function GpsLayer({ map }: { map: MLMap })   // the accuracy circle only; the toggle button is removed
export function GpsStatusText()

// Home.tsx
export const MODES_ON_HOME: { screen: 'simulate' | 'play'; title: string; body: string }[]
export function Home()

// HoleScreen.tsx
export function panelParts(screen: 'simulate' | 'play'): { logger: boolean; learn: boolean; playItOut: boolean; gps: boolean }
export function HoleScreen({ screen }: { screen: 'simulate' | 'play' })
```

## Slices

1. **Screen in the store.** `screen` and `setScreen`; default `'home'`; not in the persisted part. Test.
2. **Home.** The two cards, 56 px or taller targets in the lower half of a phone screen, the app name and one line of what it is. Test the card list and copy.
3. **Hole screen split.** `App.tsx` renders Home or `HoleScreen`; the top bar gains the Home button; `panelParts` decides what the panel and the map show per mode. Test `panelParts` and that Simulate never starts a GPS watch.
4. **GPS always on in Play.** `GpsBadge` becomes `GpsLayer`; the watch starts on entering Play and stops on leaving; the refused state and "Try again". Test with the fake geolocation.

## Done when

On a phone: Home shows two cards; Simulate has no GPS control and no Hit button; Play asks for location once, follows the player, and has no GPS toggle; Home from either returns to the cards.

## Pitfalls

- Do not persist `screen`: a reload into Play would start the watch without a gesture.
- The status line under the map is for Play only; in Simulate it would only ever read "GPS off".
- Simulate uses the stored player and the grid recommendation, as before; the rollout worker runs in Play (and wherever the learn switch is on).
