# Shared fixtures

Both halves test against these files so the Python and TypeScript implementations cannot drift.

| File | Produced by | Consumed by | Contents |
| --- | --- | --- | --- |
| `geo_points.json` | part 01 slice 2 (hand-check three points on hole 11 in geojson.io) | part 01, part 09 | `{"hole": 11, "origin": {...}, "rotation_deg": ..., "points": [{"lon":..., "lat":..., "x":..., "y":...}, x3]}` |
| `shot_samples.json` | part 06 slice 5 | part 12 slice 2 | `{"seed": 42, "uniforms": [u1, u2, u3], "club": {...}, "from": [25, 25], "dir_deg": 10, "mode": "replay", "landings": [[x, y], x20]}` |
| `stats_updates.json` | part 02 slice 8 | part 15 (stretch) | driver prior, 5 observations, ClubStats after each |
| `toy_bundle/` | part 08 slice 5 | part 09 onward | copy of `app/public/data/toy/drop/` for reference |

Rule: a fixture is written by exactly one part and never edited by hand afterward. If it needs to change, re-run the producing slice and commit the result with a message that says why.
