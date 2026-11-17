# Roadmap to the final demo

Written 2026-11-16. Parts 01 to 13 and 16 are merged. What is left, in build order, with what each one lets us do.

| Order | Part | What it gives us | Needs from us |
| --- | --- | --- | --- |
| 1 | 14 GPS, PWA, deploy | The app on a phone at a public URL, working offline on the course | A Vercel account linked to the repo (you create it) |
| 2 | 17 Trees and tee-only driver | The solver aims around trees and stops recommending driver off the fairway | A look at the tree overlay against the satellite view |
| 3 | 18 Club-only baselines | A true "best club, fixed aim" baseline and the club versus aim split of the gain | Nothing |
| 4 | 15 Shot logging and learning | Hit button, logged shots, distributions that update from on-course shots | Play a hole with it |
| 5 | 19 Real data and full solve | Our own player, all three holes in all three modes, the numbers for the video | The STMax CSV export and two answers about it |
| 6 | 20 Robustness benchmark | Which method holds up when the player model is slightly wrong | Nothing |

Parts 14 and 17 come first because they are what make an on-course test meaningful: the phone needs the app, and a policy that aims through trees is not worth testing. Part 19 waits on data but its converter slice can run as soon as the first export exists; its solve slices run after 17 so we solve once with trees.

## Launch monitor data

Per shot: club, carry, total, offline (lateral) and date. Shot counts: 50 each with SW, 9i, 7i, 5-hybrid and 100 drivers off a tee. Keep the mishits. Export everything the STMax gives (spin, launch and descent angles, smash factor); the model does not use them today, but the raw export is kept in case it does later.

Two questions to answer with the first export: the units of carry, total and offline, and whether positive offline means right of the target as the golfer stands.

## Follow-ups not scheduled

- Loft exemption for trees (a high shot clears a tree near the tee or the green).
- Cross-entropy aim search and the goal objective (P(score <= par)), from part 16.
- Wind as a few fixed scenarios.
