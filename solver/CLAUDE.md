# solver/ rules

Python 3.12, managed with uv. Read the root `CLAUDE.md` first.

## Setup

```
cd solver
uv sync
uv run pytest
uv run python -m caddie solve 11 --mode drop
```

Dependencies: numpy, scipy, shapely, pyproj, matplotlib, pytest. Add numba only if `value_iteration.py` exceeds 10 s per sweep on hole 12 and say so in the PR.

## Conventions

- Package is `caddie/`. One module per part file. No module imports from a later part number.
- All distances in meters, angles in degrees at the API boundary and radians inside functions. Direction 0 is the pin bearing; positive is to the golfer's right.
- Arrays are `np.ndarray` with shape `(rows, cols)`. Index `[r, c]`. Cell `(r, c)` centre is `x = (c + 0.5) * cell_m`, `y = (r + 0.5) * cell_m`.
- Lie codes are the integers in the root data contract. Use the `Lie` IntEnum from `mdp.py`; never raw ints in other modules.
- Randomness: every function that samples takes `rng: np.random.Generator` or a precomputed draw array. No global seeds. Halton draws come from `scipy.stats.qmc.Halton`.
- Type hints everywhere. Dataclasses for records (`Hole`, `ClubParams`, `Player`, `Solution`). No pandas; CSV via `numpy.genfromtxt` or the csv module.
- Logging via `logging`, not print. The CLI sets the level.
- Tests live in `solver/tests/`, one file per module, named `test_<module>.py`. The toy hole fixture is `tests/fixtures/toy_hole.py` (10 x 10, built in part 04).

## Data layout

```
solver/data/raw/osm_stanford.geojson     Overpass export, relation 3570691, committed
solver/data/raw/shots.csv                committed once collected
solver/data/raw/putting.csv              committed
solver/data/holes/{10,11,12}.geojson     merged OSM + hand traced, committed
solver/out/                              gitignored; export.py copies to ../app/public/data/
```

## The toy hole (used by every test from part 04 on)

10 rows x 10 cols, cell 5 m. Row 0 is the tee row, pin at cell (9, 5). Fairway everywhere except: bunker at (5, 4), (5, 5); water at rows 7, cols 0 to 3; ob at col 9. Green = cells within 7.5 m of the pin. One club `test7i` with mu_c 25 m, sigma_theta 4 deg, sigma_d 0.05, p 0.05, mu_r 2, sigma_r 1. Putting table: 1.5 putts everywhere. The expected value at the tee under `replay` mode is computed once by brute-force simulation in the fixture and asserted to within 0.05 strokes by value iteration.

## Definition of done per part

All slices committed, `uv run pytest` green, `uv run ruff check` clean, and the part's "Done when" line in its file satisfied with the command shown there.
