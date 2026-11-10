# Part 02: dispersion.py

Branch `part/02-dispersion`. Scope: `solver/caddie/dispersion.py`, `solver/tests/test_dispersion.py`, `solver/data/raw/shots.csv` (schema only until collected).

## Purpose

Fit per-club shot distributions from simulator data, interpolate unsampled clubs, and write `player.json`. Carry, direction, and roll are fit by conjugate Bayesian updating from a skill-band prior (Ch 4.2) so the same update rule can later absorb on-course shots; the mishit rate p is fit by maximum likelihood (Ch 4.1) because it has no conjugate form worth the trouble.

## Model

Per club, independent components:

- Direction: theta ~ N(0, sigma_theta^2), degrees.
- Carry: c = mu_c (1 + sigma_d X), X ~ (1 - p) N(0, 1) + p N(-2, 1). Mishit mean fixed at -2.
- Roll: r = total - carry ~ N(mu_r, sigma_r^2).

Log-likelihood of carry for one shot with z = (c / mu_c - 1) / sigma_d (used only to fit p, with mu_c and sigma_d held at their posterior means):

```
log[ (1 - p) phi(z) + p phi(z + 2) ] - log(sigma_d mu_c)
```

## Conjugate updates (Ch 4.2)

Carry and roll: Normal with unknown mean and variance, Normal-Inverse-Gamma prior with state `(m, kappa, alpha, beta)`. One observation `x`:

```
kappa' = kappa + 1
m'     = (kappa m + x) / kappa'
alpha' = alpha + 1/2
beta'  = beta + kappa (x - m)^2 / (2 kappa')
```

Posterior mean of the mean is `m`; posterior mean of the variance is `beta / (alpha - 1)`. Carry's `sigma_d` is reported as `sqrt(var) / m`.

Direction: Normal with mean 0 and unknown variance, Inverse-Gamma prior `(alpha, beta)`. One observation theta (degrees):

```
alpha' = alpha + 1/2
beta'  = beta + theta^2 / 2
```

Priors per club from Broadie and Ko skill bands, worth `kappa = 5` pseudo-shots (`alpha = 2.5`): carry `m` from `NOMINAL_CARRY` scaled to the player's driver estimate, `beta` so the prior variance matches `sigma_d = 0.08`; direction prior variance matching 7 degrees (15 hcp); roll `m = 0.08 mu_c`, variance matching 6 m. The 50 to 100 sim shots dominate these priors; they exist so the stretch goal has a valid starting state and so a club with few shots does not collapse to zero variance.

## Inputs

Canonical `shots.csv` with header `club,carry_m,total_m,lateral_m,lie,date`. `lie` in {tee, mat, rough}: driver rows are `tee`, everything else `mat` or `rough`. Clubs sampled: `driver, 5h, 7i, 9i, sw`. Rough rows exist for `7i` only.

The raw source is an STMax launch monitor export. Slice 1 includes `scripts/stmax_to_shots.py` that converts it to the canonical CSV. Two things are unknown until the first export is in hand and must be asked, not guessed:

- **Column names and units** for carry, total, and offline/lateral in the STMax export. Open the file, list the headers, and confirm the mapping with Diego before writing the converter.
- **Lateral sign convention.** Before converting any data, ask Diego: in the STMax export, is a positive offline value a shot that finished to the RIGHT of the target line as the golfer stands? The canonical CSV uses positive = right. Flip the sign in the converter if STMax differs. Record the answer in a comment at the top of the converter.

## Outputs

```python
@dataclass
class NIG:  # Normal-Inverse-Gamma state
    m: float; kappa: float; alpha: float; beta: float

@dataclass
class IG:   # Inverse-Gamma state for a zero-mean variance
    alpha: float; beta: float

@dataclass
class ClubStats:
    n: int; carry: NIG; theta: IG; roll: NIG

@dataclass
class ClubParams:
    mu_c: float; sigma_theta_deg: float; sigma_d: float; p: float; mu_r: float; sigma_r: float; sampled: bool
    stats: ClubStats | None       # None for interpolated clubs

@dataclass
class Player:
    handicap: int
    clubs: dict[str, ClubParams]
    club_order: list[str]
    lie: dict[str, dict[str, float]]      # multipliers per lie: carry, sigma, roll
    putting: PuttingTable                 # from part 03
```

## Interfaces

```python
def load_shots(path: Path) -> dict[str, np.ndarray]
    # club -> structured array (carry_m, total_m, lateral_m, lie)

def prior_for(club: str, handicap: int, driver_mu_hint: float) -> ClubStats
    # Broadie-Ko skill-band prior as described above, kappa = 5

def update_nig(s: NIG, x: float) -> NIG
def update_ig(s: IG, theta: float) -> IG
def update_club_stats(stats: ClubStats, carry: float, total: float, lateral: float) -> ClubStats
    # theta = degrees(arctan2(lateral, carry)); carry -> s.carry; (total - carry) -> s.roll; n += 1
    # this exact function is what the stretch goal calls once per on-course shot

def params_from_stats(stats: ClubStats) -> tuple[float, float, float, float, float]
    # (mu_c, sigma_theta_deg, sigma_d, mu_r, sigma_r) as posterior means

def fit_p(carry: np.ndarray, mu_c: float, sigma_d: float, p_bounds=(0.02, 0.25)) -> float
    # scipy.optimize.minimize_scalar(method="bounded") on the negative mixture log-likelihood with mu_c, sigma_d fixed

def fit_club(club: str, shots: np.ndarray, handicap: int, driver_mu_hint: float) -> ClubParams
    # prior_for -> fold every shot through update_club_stats -> params_from_stats -> fit_p

def fit_rough_multipliers(mat7i: ClubParams, rough_shots: np.ndarray) -> dict[str, float]
    # carry = mu_c_rough / mu_c_mat; sigma = mean of the two sigma ratios; roll = mu_r_rough / mu_r_mat clipped to [0, 1]
    # falls back to the defaults in the root contract if fewer than 15 rough shots

NOMINAL_CARRY = {"driver": None, "3w": 0.92, "5h": None, "6i": 1.08, "7i": None, "8i": 0.92, "9i": None, "pw": 0.90, "sw": None, "sw70": 0.78, "sw50": 0.56, "sw30": 0.33}
    # None = sampled; others are ratios to the nearest sampled club below in the bag (3w to driver, 6i to 7i, 8i to 7i, pw to 9i, swXX to sw)

def interpolate_clubs(sampled: dict[str, ClubParams]) -> dict[str, ClubParams]
    # mu_c from NOMINAL_CARRY ratios; every other parameter linear in mu_c between the two nearest sampled clubs, clamped at the ends
    # partial wedges: copy sw with mu_c scaled and sigma_theta, sigma_d multiplied by 1.2

def build_player(shots_path: Path, putting: PuttingTable, handicap: int) -> Player
def write_player_json(player: Player, path: Path) -> None
```

## Slices

1. **Loader, schema, and STMax converter.** `load_shots` on a 10-row fixture CSV. Test: clubs present, dtypes numeric, lateral can be negative. `scripts/stmax_to_shots.py` written only after the two questions above are answered; test it on the first real export with a 5-row golden file.
2. **Conjugate updates.** `update_nig` on 200 draws from N(215, 15^2) starting from the driver prior: posterior mean within 2 m, posterior std within 2 m. `update_ig` on 200 draws with sigma 6 deg: within 0.6 deg. Order of updates does not change the result (fold in two orders, compare to 1e-9).
3. **Prior sanity.** With zero shots, `params_from_stats(prior_for("7i", 15, 215))` gives mu_c between 120 and 160 m and sigma_theta between 5 and 9 deg. With 50 shots, the prior moves the posterior mean by under 3% versus the plain sample mean.
4. **p by MLE and `fit_club`.** Synthetic 60 shots from the mixture with p = 0.1: p within [0.03, 0.2]; 60 shots with p = 0 land at the lower bound without error. `fit_club` round-trips synthetic data; `stats.n` equals the row count.
5. **Rough multipliers.** Synthetic rough set with carry 0.88x; recovered carry multiplier within 0.03. Fewer than 15 rows returns defaults.
6. **Interpolation.** Given sampled driver/5h/7i/9i/sw, output has all 12 clubs, mu_c strictly decreasing in `club_order`, no NaN.
7. **player.json.** Matches the root contract schema exactly, including the `stats` block per sampled club and `null` for interpolated ones (test by loading and checking keys). Write a sample from synthetic data to `solver/out/player.sample.json`.
8. **Fixture for the TS port.** `docs/fixtures/stats_updates.json`: the driver prior, 5 observations `(carry, total, lateral)`, and the `ClubStats` after each. The stretch goal's `learn.ts` reproduces these to 1e-9.

## Done when

`uv run python -m caddie fit --shots data/raw/shots.csv --out out/player.json` runs on the fixture CSV and the JSON validates. On real data, every sampled sigma_theta is between 3 and 12 degrees and p between 0.02 and 0.25; if not, print a warning naming the club.

## Pitfalls

- Lateral sign convention: positive = right of target line as the golfer sees it. Record it that way on the sim.
- `arctan2(lateral, carry)` not `lateral / carry`; shanks make the ratio blow up.
- Do not fit the mishit mean. With 50 shots it is not identifiable.
- The conjugate carry model is a single normal; the mishit component lives only in p. That is deliberate: sim shots that are fat still update the carry posterior and slightly widen it, which is acceptable at 50 shots, and keeps the on-course update a one-liner.
