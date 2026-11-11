"""Part 16: benchmark the shot-selection approaches against each other.

Cases (``tests/fixtures/benchmark_cases.json``) name a hole, a player, a start point, a
penalty mode and expectations; approaches (``caddie.approaches``) are policy factories.
Every approach plays every case on paired draws, and the metrics, the expectation checks
and the ranking go under ``out/benchmark/``. A failed expectation is a finding, not an
error.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from caddie.dispersion import Player
from caddie.export import BUNDLE_FILES, bundle_dir, read_bundle, read_player
from caddie.geometry import Hole
from caddie.mdp import DIRECTIONS_DEG, Lie, PenaltyMode
from caddie.value_iteration import Solution, solve

log = logging.getLogger(__name__)

SOLVER_DIR = Path(__file__).resolve().parents[1]
CASES_PATH = SOLVER_DIR / "tests" / "fixtures" / "benchmark_cases.json"
LIE_BY_NAME = {"tee": Lie.TEE, "fairway": Lie.FAIRWAY, "rough": Lie.ROUGH, "bunker": Lie.BUNKER}

# --- slice 1: cases ------------------------------------------------------------------------------


@dataclass
class Case:
    id: str
    hole: Hole
    player: Player
    start: tuple[float, float, Lie]
    mode: PenaltyMode
    n: int
    expect: list[dict]
    solution: Solution | None
    hole_key: str = ""  # "toy", "open_straight", "11", ... for file names and the solution cache
    extras: dict = field(default_factory=dict)  # e.g. brute-force value for a band expectation


def _fixtures():
    """The test fixture modules, imported lazily so the package has no test import."""
    if str(SOLVER_DIR) not in sys.path:
        sys.path.insert(0, str(SOLVER_DIR))
    from tests.fixtures import benchmark_holes, toy_hole

    return benchmark_holes, toy_hole


def _build_hole(spec: dict, out_dir: Path) -> tuple[Hole, Solution | None, str, str, bool]:
    """``(hole, solution or None, hole_key, mode-independent label, is_real)``."""
    bh, th = _fixtures()
    if "number" in spec:
        return None, None, str(spec["number"]), str(spec["number"]), True  # type: ignore[return-value]
    builder = spec.get("builder")
    args = spec.get("args", {})
    if builder == "toy":
        return th.toy_hole(), None, "toy", "toy", False
    if builder not in bh.HOLE_BUILDERS:
        raise ValueError(f"unknown hole builder {builder!r}")
    key = builder + ("" if not args else "_" + "_".join(f"{k}{v}" for k, v in sorted(args.items())))
    return bh.HOLE_BUILDERS[builder](**args), None, key, builder, False


def _build_player(spec: dict, out_dir: Path) -> Player:
    bh, th = _fixtures()
    builder = spec.get("builder")
    args = spec.get("args", {})
    if builder == "toy":
        return th.toy_player()
    if builder == "file":
        path = Path(spec.get("path", out_dir / "player.json"))
        if not path.exists():
            raise FileNotFoundError(path)
        return read_player(path)
    if builder not in bh.PLAYER_BUILDERS:
        raise ValueError(f"unknown player builder {builder!r}")
    return bh.PLAYER_BUILDERS[builder](**args)


def _hole_from_bundle(meta: dict, lie: np.ndarray) -> Hole:
    from caddie.cli import hole_from_bundle  # part 08 owns the bundle to Hole mapping

    return hole_from_bundle(meta, lie)


def _load_real(number: str, mode: PenaltyMode, out_dir: Path) -> tuple[Hole, Solution] | None:
    d = bundle_dir(out_dir, number, mode)
    if not all((d / f).exists() for f in BUNDLE_FILES):
        return None
    meta, lie, value, club, direction = read_bundle(d)
    hole = _hole_from_bundle(meta, lie)
    sol = Solution(
        hole=hole.number,
        mode=mode,
        U=value.reshape(-1).astype(np.float32),
        club=club.reshape(-1),
        dir=direction.reshape(-1),
        sweeps=0,
    )
    return hole, sol


def _start(spec: dict | None, hole: Hole) -> tuple[float, float, Lie]:
    if not spec:
        return (float(hole.tee_xy[0]), float(hole.tee_xy[1]), Lie.TEE)
    lie = LIE_BY_NAME[spec.get("lie", "fairway")]
    if "short_of_pin_m" in spec:
        d = float(spec["short_of_pin_m"])
        tx, ty = hole.tee_xy
        px, py = hole.pin_xy
        length = float(np.hypot(px - tx, py - ty))
        return (px + (tx - px) * d / length, py + (ty - py) * d / length, lie)
    return (float(spec["x"]), float(spec["y"]), lie)


def cached_solution(
    hole: Hole, player: Player, mode: PenaltyMode, key: str, out_dir: Path, K: int = 200
) -> Solution:
    """Solve a synthetic hole once and keep the grids under ``out/benchmark/solutions/``."""
    cache = Path(out_dir) / "benchmark" / "solutions" / f"{key}_{mode}.npz"
    if cache.exists():
        z = np.load(cache)
        return Solution(
            hole=hole.number,
            mode=mode,
            U=z["U"],
            club=z["club"],
            dir=z["dir"],
            sweeps=int(z["sweeps"]),
        )
    log.info("solving %s %s for the benchmark", key, mode)
    sol = solve(hole, player, mode, K=K)
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez(cache, U=sol.U, club=sol.club, dir=sol.dir, sweeps=sol.sweeps)
    return sol


def load_cases(
    path: Path = CASES_PATH,
    out_dir: Path = SOLVER_DIR / "out",
    ids: list[str] | None = None,
    solve_missing: bool = True,
    solve_fn: Callable[..., Solution] = cached_solution,
) -> list[Case]:
    """Every runnable case in the fixture: synthetic holes built, real bundles loaded.

    A real hole without a bundle under ``out_dir`` is skipped with a log line. Synthetic
    holes are solved on demand (cached) when ``solve_missing``; otherwise ``solution`` is
    None and the caller solves. Unknown builders raise.
    """
    specs = json.loads(Path(path).read_text())
    out_dir = Path(out_dir)
    cases: list[Case] = []
    for spec in specs:
        if ids is not None and spec["id"] not in ids:
            continue
        mode: PenaltyMode = spec["mode"]
        hole, sol, key, _label, real = _build_hole(spec["hole"], out_dir)
        if real:
            loaded = _load_real(key, mode, out_dir)
            if loaded is None:
                log.warning("case %s skipped: no bundle for hole %s %s", spec["id"], key, mode)
                continue
            hole, sol = loaded
        try:
            player = _build_player(spec["player"], out_dir)
        except FileNotFoundError as e:
            log.warning("case %s skipped: player file %s missing", spec["id"], e)
            continue
        if sol is None and solve_missing:
            sol = solve_fn(hole, player, mode, key, out_dir)
        cases.append(
            Case(
                id=spec["id"],
                hole=hole,
                player=player,
                start=_start(spec.get("start"), hole),
                mode=mode,
                n=int(spec["n"]),
                expect=list(spec["expect"]),
                solution=sol,
                hole_key=key,
            )
        )
    return cases


# --- slice 5: point simulator ------------------------------------------------------------------

MAX_POINT_SHOTS = 40


def simulate_points(
    hole: Hole,
    player: Player,
    policy: Callable[[float, float, Lie], tuple[str, float]],
    mode: PenaltyMode,
    n: int,
    seed: int,
    start: tuple[float, float, Lie],
) -> tuple[np.ndarray, float]:
    """Continuous play: ``n`` plays from ``start`` under a point policy (club name, aim deg).

    Each shot lands through :func:`caddie.online.shots_from_point` with one draw; the draws
    for every (play, shot) come from ``seed`` up front, so two policies see the same ones.
    A play ends when the ball rests on the green, adding E[putts] from the resting point,
    or after ``MAX_POINT_SHOTS``. Returns ``(strokes, seconds spent deciding)``.
    """
    import time

    from caddie.mdp import Draws, locate
    from caddie.online import shots_from_point

    rng = np.random.default_rng(seed)
    normals = rng.standard_normal((MAX_POINT_SHOTS, n, 3))
    uniforms = rng.random((MAX_POINT_SHOTS, n))
    strokes = np.zeros(n)
    decide_s = 0.0
    px, py = hole.pin_xy
    for k in range(n):
        x, y, lie = float(start[0]), float(start[1]), Lie(start[2])
        for shot in range(MAX_POINT_SHOTS):
            t0 = time.perf_counter()
            club_name, dir_deg = policy(x, y, lie)
            decide_s += time.perf_counter() - t0
            club = player.clubs[club_name]
            draws = Draws(
                theta=normals[shot, k, 0:1],
                z=normals[shot, k, 1:2],
                u=uniforms[shot, k : k + 1],
                roll=normals[shot, k, 2:3],
            )
            nx, ny, cost = shots_from_point(hole, player, x, y, lie, club, dir_deg, draws, mode)
            x, y = float(nx[0]), float(ny[0])
            strokes[k] += float(cost[0])
            _, code, _ = locate(hole, np.array([x]), np.array([y]))
            lie = Lie(int(code[0]))
            if lie == Lie.GREEN:
                strokes[k] += float(np.asarray(player.putting(np.hypot(x - px, y - py))))
                break
        else:
            log.warning("play %d did not hole out in %d shots", k, MAX_POINT_SHOTS)
    return strokes, decide_s


# --- slice 4: run a case on the cell simulator --------------------------------------------------

BLOWUP_OVER_PAR = 3


def _timed(policy: Callable, clock: dict) -> Callable:
    """Wrap a policy so the seconds spent inside it accumulate in ``clock["s"]``."""
    import time

    def wrapped(*args):
        t0 = time.perf_counter()
        try:
            return policy(*args)
        finally:
            clock["s"] += time.perf_counter() - t0
            clock["n"] += 1

    return wrapped


def _build(approach, case: Case, seed: int, settings: dict | None = None):
    """``(policy, build_s)`` for one approach on one case, or None when not implemented."""
    import time

    from caddie.approaches import memoise_policy

    t0 = time.perf_counter()
    try:
        policy = approach.build(
            case.hole, case.player, case.solution, case.mode, **(settings or {})
        )
    except NotImplementedError as e:
        log.info("%s", e)
        return None
    build_s = time.perf_counter() - t0
    if approach.memoise:
        policy = memoise_policy(case.hole, policy)
    return policy, build_s


def _build_point(approach, case: Case, seed: int, settings: dict | None = None):
    """``(point policy, index policy, build_s)`` or None when the approach has no point form."""
    import time

    from caddie.approaches import policy_from_point

    if approach.point is None:
        return None
    t0 = time.perf_counter()
    try:
        point = approach.point(case.hole, case.player, case.solution, case.mode, **(settings or {}))
    except NotImplementedError as e:
        log.info("%s", e)
        return None
    return point, policy_from_point(case.player, point), time.perf_counter() - t0


def _decisions_at(case: Case, policy, points: dict[str, tuple[float, float, Lie]]) -> dict:
    out = {}
    for name, (x, y, lie) in points.items():
        ci, di = policy(x, y, lie)
        out[name] = {"club": case.player.club_order[ci], "dir_deg": float(DIRECTIONS_DEG[di])}
    return out


def _action_points(case: Case) -> dict[str, tuple[float, float, Lie]]:
    points = {"start": case.start}
    for e in case.expect:
        at = e.get("at")
        if isinstance(at, list):
            points[str(at)] = (float(at[0]), float(at[1]), LIE_BY_NAME[at[2]])
    return points


def run_case(
    case: Case,
    approaches: list[str],
    seed: int = 0,
    simulator: str = "cell",
    check: bool = True,
    settings: dict[str, dict] | None = None,
) -> dict:
    """Metrics per approach on one case, paired draws, expectations checked.

    ``approaches`` that raise ``NotImplementedError`` are listed under ``not_run``.
    ``grid`` is the reference for ``se_vs_grid`` and ``disagreement``; when it is not among
    the approaches those are NaN.
    """
    from caddie.approaches import APPROACHES
    from caddie.evaluate import disagreement, simulate

    if simulator not in ("cell", "point"):
        raise ValueError(f"unknown simulator {simulator!r}")
    results: dict[str, dict] = {}
    strokes: dict[str, np.ndarray] = {}
    decisions: dict[str, dict] = {}
    not_run: list[str] = []
    points = _action_points(case)
    for name in approaches:
        approach = APPROACHES[name]
        clock = {"s": 0.0, "n": 0}
        if simulator == "cell":
            built = _build(approach, case, seed, (settings or {}).get(name))
            if built is None:
                not_run.append(name)
                continue
            policy, build_s = built
            s = simulate(
                case.hole,
                case.player,
                _timed(policy, clock),
                case.mode,
                n=case.n,
                seed=seed,
                start=case.start,
            )
        else:
            built = _build_point(approach, case, seed, (settings or {}).get(name))
            if built is None:
                not_run.append(name)
                continue
            point, policy, build_s = built
            s, clock["s"] = simulate_points(
                case.hole, case.player, point, case.mode, case.n, seed, case.start
            )
            clock["n"] = int(np.rint(s.sum() - 1.5 * s.size)) if s.size else 0  # about one per shot
        strokes[name] = s
        decisions[name] = _decisions_at(case, policy, points)
        results[name] = {
            "mean_strokes": float(s.mean()),
            "std_strokes": float(s.std(ddof=1)) if s.size > 1 else 0.0,
            "p_blowup": float(np.mean(s >= case.hole.par + BLOWUP_OVER_PAR)),
            "histogram": {
                int(v): int(k)
                for v, k in zip(*np.unique(np.rint(s).astype(int), return_counts=True), strict=True)
            },
            "build_s": build_s,
            "decide_s": clock["s"],
            "decide_ms_per_shot": 1000.0 * clock["s"] / max(clock["n"], 1),
            "disagreement": (
                disagreement(case.hole, case.solution, policy)
                if case.solution is not None and name != "grid"
                else (0.0 if name == "grid" else float("nan"))
            ),
            "passed": [],
            "failed": [],
        }
        log.info(
            "case %s %s: mean %.3f sd %.3f blowup %.3f build %.1fs decide %.1fs",
            case.id,
            name,
            results[name]["mean_strokes"],
            results[name]["std_strokes"],
            results[name]["p_blowup"],
            build_s,
            clock["s"],
        )
    if results:
        best = min(m["mean_strokes"] for m in results.values())
        ref = strokes.get("grid")
        for name, m in results.items():
            m["regret"] = m["mean_strokes"] - best
            if ref is None:
                m["se_vs_grid"] = float("nan")
            else:
                d = strokes[name] - ref
                m["se_vs_grid"] = float(d.std(ddof=1) / np.sqrt(d.size)) if d.size > 1 else 0.0
    result = {
        "case": case.id,
        "hole": case.hole_key,
        "mode": case.mode,
        "par": case.hole.par,
        "n": case.n,
        "seed": seed,
        "simulator": simulator,
        "start": [case.start[0], case.start[1], case.start[2].name.lower()],
        "approaches": results,
        "decisions": decisions,
        "not_run": not_run,
        "passed": [],
        "failed": [],
        "skipped": [],
    }
    if check:
        passed, failed, skipped = check_expectations(case, result)
        result["passed"], result["failed"], result["skipped"] = passed, failed, skipped
        for e_id, who in _attribution(case, passed, result):
            result["approaches"][who]["passed"].append(e_id)
        for f in failed:
            for who in f.get("approaches", []):
                if who in result["approaches"]:
                    result["approaches"][who]["failed"].append(f["id"])
    return result


def _expect_id(e: dict) -> str:
    if "id" in e:
        return e["id"]
    parts = [e["kind"]] + [str(e[k]) for k in ("approach", "a", "b", "lower", "upper") if k in e]
    return "-".join(parts)


def _involved(e: dict) -> list[str]:
    return [e[k] for k in ("approach", "a", "b", "lower", "upper") if k in e]


def _attribution(case: Case, passed: list[str], result: dict):
    for e in case.expect:
        e_id = _expect_id(e)
        if e_id not in passed:
            continue
        for who in _involved(e):
            if who in result["approaches"]:
                yield e_id, who


def _band_bounds(case: Case, e: dict, result: dict) -> tuple[float, float]:
    lo, hi = e.get("lo", -np.inf), e.get("hi", np.inf)
    if e.get("around") == "tee_value":
        if case.solution is None:
            raise ValueError("band around tee_value needs a solution")
        from caddie.approaches import cell_index

        u = float(case.solution.U[cell_index(case.hole, case.start[0], case.start[1])])
        return u - float(e["within"]), u + float(e["within"])
    if isinstance(hi, str) and hi.startswith("brute_force_plus_"):
        plus = float(hi[len("brute_force_plus_") :])
        if "brute_force" not in case.extras:
            _bh, th = _fixtures()
            case.extras["brute_force"] = th.brute_force_value_at_tee(case.mode)
        hi = case.extras["brute_force"] + plus
    return float(lo), float(hi)


def _expand(e: dict, who: list[str]) -> list[dict]:
    """A ``"*"`` approach stands for every approach that ran (minus the comparison partner)."""
    key = next((k for k in ("approach", "a") if e.get(k) == "*"), None)
    if key is None:
        return [e]
    other = e.get("b")
    out = []
    for name in who:
        if name == other:
            continue
        copy = dict(e)
        copy[key] = name
        copy["id"] = f"{_expect_id(e)}:{name}"
        out.append(copy)
    return out


def check_expectations(case: Case, result: dict) -> tuple[list[str], list[dict], list[dict]]:
    """``(passed ids, failed records, skipped records)`` for the case's expectations.

    A record is ``{"id", "kind", "approaches", "measured", ...}``; skipped means an approach
    the expectation names did not run. Every check uses the paired standard error.
    """
    metrics = result["approaches"]
    decisions = result["decisions"]
    ran = list(metrics)
    passed: list[str] = []
    failed: list[dict] = []
    skipped: list[dict] = []
    for raw in case.expect:
        for e in _expand(raw, ran):
            e_id = _expect_id(e)
            who = _involved(e)
            if e.get("dir_deg_min") in ran or e.get("dir_deg_max") in ran:
                who = who + [v for v in (e.get("dir_deg_min"), e.get("dir_deg_max")) if v in ran]
            missing = [w for w in who if w not in metrics]
            if missing:
                skipped.append(
                    {"id": e_id, "kind": e["kind"], "approaches": who, "missing": missing}
                )
                continue
            ok, measured = _check_one(case, e, metrics, decisions, result)
            if ok:
                passed.append(e_id)
            else:
                failed.append(
                    {"id": e_id, "kind": e["kind"], "approaches": who, "measured": measured}
                )
    return passed, failed, skipped


def _se(metrics: dict, a: str, b: str) -> float:
    """Paired standard error between two approaches; both are paired with grid, so use the
    larger of the two as a conservative bound unless one of them is grid."""
    if a == "grid":
        return metrics[b]["se_vs_grid"]
    if b == "grid":
        return metrics[a]["se_vs_grid"]
    return float(np.nanmax([metrics[a]["se_vs_grid"], metrics[b]["se_vs_grid"], 0.0]))


def _check_one(case: Case, e: dict, metrics: dict, decisions: dict, result: dict):
    kind = e["kind"]
    if kind == "order":
        lo, up = e["lower"], e["upper"]
        ml, mu = metrics[lo]["mean_strokes"], metrics[up]["mean_strokes"]
        se = _se(metrics, lo, up)
        margin = float(e.get("by_at_least", 0.0))
        return ml <= mu - margin + se, {lo: ml, up: mu, "se": se, "by_at_least": margin}
    if kind == "close":
        a, b = e["a"], e["b"]
        ma, mb = metrics[a]["mean_strokes"], metrics[b]["mean_strokes"]
        se = _se(metrics, a, b)
        return abs(ma - mb) <= float(e["within"]) + se, {a: ma, b: mb, "se": se}
    if kind == "blowup_order":
        lo, up = e["lower"], e["upper"]
        pl, pu = metrics[lo]["p_blowup"], metrics[up]["p_blowup"]
        return pl <= pu, {lo: pl, up: pu}
    if kind == "band":
        who = e["approach"]
        lo, hi = _band_bounds(case, e, result)
        m = metrics[who]["mean_strokes"]
        return lo <= m <= hi, {who: m, "lo": lo, "hi": hi}
    if kind == "action":
        who = e["approach"]
        at = e.get("at", "start")
        key = at if isinstance(at, str) else str(at)
        d = decisions[who][key]
        ok = True
        if "club" in e:
            ok &= d["club"] == e["club"]
        if "club_not" in e:
            ok &= d["club"] != e["club_not"]
        for bound, cmp in (
            ("dir_deg_min", lambda v, b: v >= b),
            ("dir_deg_max", lambda v, b: v <= b),
        ):
            if bound in e:
                ref = e[bound]
                value = decisions[ref][key]["dir_deg"] if isinstance(ref, str) else float(ref)
                ok &= cmp(d["dir_deg"], value)
        return bool(ok), {who: d}
    raise ValueError(f"unknown expectation kind {kind!r}")
