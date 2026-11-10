# Caddie

A personalized golf caddie for Stanford Golf Course holes 10, 11, 12. Hole play is modelled as a Markov decision process: a Python solver computes the optimal club and aim from every position offline, and a TypeScript web app shows the result on a map, first on desktop and then on a phone with GPS.

CS 238 final project, Diego Raygada and Hylton Harvey.

## Layout

- `solver/` Python 3.12 (uv): geometry, dispersion fit, MDP, value iteration, online rollout, evaluation, export.
- `app/` TypeScript (Vite, React, MapLibre GL, Tailwind, Zustand): map, heatmap, caddie panel, play-it-out, GPS and PWA.
- `docs/parts/` one spec per unit of work, built in the order listed in `CLAUDE.md`.
- `docs/fixtures/` shared fixtures that keep the Python and TypeScript halves in agreement.

Read `CLAUDE.md` for the rules, frozen decisions, data contract and build order.
