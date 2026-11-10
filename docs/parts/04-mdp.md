# Part 04: mdp.py

Branch `part/04-mdp`. Scope: `solver/caddie/mdp.py`, `solver/tests/test_mdp.py`, `solver/tests/fixtures/toy_hole.py`.

## Purpose

The MDP (Ch 7.1): state and action spaces, the generative transition in two stages (land, then roll), terrain rules per `penalty_mode`, the reward, and the precomputed landing offset tables that value iteration and the online step both use.

## Definitions

- State: `(r, c, lie)`; stored as the flat cell index `i = r * cols + c` plus the lie code from `hole.lie`. The lie is a function of the cell except where the online step overrides it, so the grid value `U[i]` is "value from cell i with its own lie".
- Action: `(club_idx, dir_idx)`. `directions_deg = np.arange(-90, 91, 2)` relative to the bearing from the cell to the pin, `b = atan2(pin_x - x, pin_y - y)`. Direction d in degrees means the aim unit vector is `(sin(b + d), cos(b + d))`; the offset tables are sampled for `b = 0` and `step_batch` rotates them by each cell's `b`.
- Reward: -1 per shot; an extra -1 when `penalty_mode != "mulligan"` and the landing is water or OB.
- Terminal: green cells. `U_terminal[i] = -putting(dist(cell i, pin))`.

## Interfaces

```python
class Lie(IntEnum): OUT=0; TEE=1; FAIRWAY=2; ROUGH=3; BUNKER=4; GREEN=5; WATER=6; OB=7

PenaltyMode = Literal["mulligan", "drop", "replay"]

@dataclass
class Draws:
    # fixed quasi-random draws shared by every cell and sweep
    theta: np.ndarray     # (K,) standard normal
    x: np.ndarray         # (K,) mixture draw X per the model, generated with p per club at sample time
    roll: np.ndarray      # (K,) standard normal

def make_draws(K: int, seed: int = 0) -> Draws
    # scipy.stats.qmc.Halton(d=3, scramble=True, seed) -> inverse-CDF to normals; X mixture uses a 4th Halton dim for the component choice

def landing_offsets(club: ClubParams, lie_mult: dict, draws: Draws, dir_deg: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]
    # returns (dx, dy, roll_m) each (K,), in grid meters, for one (club, lie, direction)
    # carry = club.mu_c * lie_mult["carry"] * (1 + club.sigma_d * lie_mult["sigma"] * X)
    # theta = club.sigma_theta_deg * lie_mult["sigma"] * draws.theta
    # dx, dy = carry * sin(dir + theta), carry * cos(dir + theta)
    # roll_m = (club.mu_r + club.sigma_r * draws.roll) * lie_mult["roll"]  (roll is scaled again by the LANDING lie in step())

@dataclass
class OffsetTables:
    # precomputed for every (club, from_lie, dir): dx, dy, roll arrays of shape (n_clubs, n_lies, n_dirs, K)
    dx: np.ndarray; dy: np.ndarray; roll: np.ndarray

def build_offset_tables(player: Player, draws: Draws) -> OffsetTables

def apply_roll(landing_lie: np.ndarray, roll_m: np.ndarray, player: Player) -> np.ndarray
    # roll scaled by the landing lie's multiplier: fairway/tee 1.0, rough 0.5, bunker 0.0, green 1.0 (ball runs on the green), water/ob 0.0

def step_batch(hole: Hole, player: Player, from_idx: np.ndarray, from_lie: np.ndarray, club_idx: int, dir_idx: int, tables: OffsetTables, mode: PenaltyMode) -> tuple[np.ndarray, np.ndarray]
    # vectorized over cells: from_idx (N,) -> next_idx (N, K), reward (N, K)
    # 1. landing xy = cell centre + (dx, dy)[club, from_lie, dir]
    # 2. clip to grid; landing cell outside the grid or lie OUT counts as OB
    # 3. landing lie = hole.lie[landing]
    # 4. final xy = landing + aim_unit * apply_roll(landing lie); final cell and lie
    # 5. terrain rule on the FINAL cell:
    #    water: mulligan -> next = from_idx, r = -1 ; drop -> next = hole.drop_index[final], r = -2 ; replay -> next = from_idx, r = -2
    #    ob or outside: mulligan -> next = from_idx, r = -1 ; drop -> next = nearest in-grid non-water cell to final, r = -2 ; replay -> next = from_idx, r = -2
    #    otherwise: next = final, r = -1

def terminal_values(hole: Hole, putting: PuttingTable) -> np.ndarray
    # (rows*cols,) : -E[putts](dist to pin) on green cells, NaN elsewhere

def candidate_actions(hole: Hole, player: Player, from_xy) -> np.ndarray
    # (optional pruning) clubs whose mu_c <= 1.3 * distance to pin; all 91 directions
```

## Toy hole fixture

`tests/fixtures/toy_hole.py` builds the 10 x 10 hole described in `solver/CLAUDE.md` as a `Hole`, a one-club `Player`, and a flat putting table, and exposes `brute_force_value_at_tee(mode, n=20000, rng)` which plays the hole with the policy "aim at the pin with test7i" and returns the mean strokes. That number is not optimal, only a sanity ceiling: value iteration must do at least as well.

## Slices

1. **Lie enum, directions, draws.** `make_draws(200)` returns arrays of length 200 with mean within 0.1 of 0 and std within 0.1 of 1 for theta and roll; X has mean below 0.
2. **Landing offsets.** For dir 0 with sigma_theta -> 0 and sigma_d -> 0, all (dx, dy) equal (0, mu_c). For dir 90, equal (mu_c, 0).
3. **Offset tables.** Shape `(n_clubs, 5, 91, K)`; rough entries have larger spread than fairway entries for the same club.
4. **step_batch, no hazards.** On an all-fairway 10 x 10 grid, a shot from the tee row with the toy club lands in rows 4 to 6 for 95% of draws and never returns reward other than -1.
5. **Terrain rules.** Place water at row 7. For each mode, from a cell at row 5 aiming at the pin: mulligan returns from_idx with -1 for every draw that lands in water; drop returns a cell at row <= 7 with -2; replay returns from_idx with -2. OB column behaves the same way with the OB rule.
6. **Terminal values.** Green cells get negative values increasing in magnitude with distance; others NaN.
7. **Brute-force fixture.** `brute_force_value_at_tee("replay")` between 3 and 6 strokes, deterministic for a fixed seed.

## Done when

`uv run pytest tests/test_mdp.py` green, and a notebook or script plots 200 landing points for driver from the hole 11 tee over the lie grid and they look like a golf shot pattern (long axis along the aim).

## Pitfalls

- Roll direction is along the aim unit vector, not along the actual flight direction; close enough at these angles and far simpler.
- Index clipping: use `np.clip` on r and c separately, then test `hole.lie == OUT` to catch the corridor edge; do not rely on wraparound.
- Keep K as a trailing axis everywhere so numpy broadcasting works without transposes.
