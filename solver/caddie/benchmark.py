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
from caddie.mdp import Lie, PenaltyMode
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
