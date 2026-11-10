"""Part 08: command line entry points (``python -m caddie <cmd>``).

Commands: fit, hole, solve, recommend, evaluate, export, all. ``recommend`` and
``evaluate`` belong to parts 06 and 07 and report that until those parts exist.

Paths default to the solver directory layout (``data/raw``, ``data/holes``, ``out``)
regardless of the current working directory. ``HOLE`` is 10, 11, 12 or ``toy``; the toy
hole is the 10 x 10 test fixture and uses its own one-club player.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from caddie.dispersion import Player, build_player
from caddie.export import (
    BUNDLE_FILES,
    bundle_dir,
    copy_to_app,
    read_bundle,
    read_player,
    write_bundle,
    write_player,
)
from caddie.geometry import Hole, build_hole, write_lie_png
from caddie.mdp import PENALTY_MODES, PenaltyMode
from caddie.putting import build_putting_table
from caddie.value_iteration import solve, write_value_png

log = logging.getLogger(__name__)

SOLVER_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUT = SOLVER_DIR / "out"
DEFAULT_APP_DATA = SOLVER_DIR.parent / "app" / "public" / "data"
DEFAULT_OSM = SOLVER_DIR / "data" / "raw" / "osm_stanford.geojson"
DEFAULT_SHOTS = SOLVER_DIR / "data" / "raw" / "shots.csv"
DEFAULT_PUTTING = SOLVER_DIR / "data" / "raw" / "putting.csv"
DEFAULT_HOLES_DIR = SOLVER_DIR / "data" / "holes"
DEFAULT_HANDICAP = 15  # root CLAUDE.md
REAL_HOLES = ("10", "11", "12")
TOY = "toy"


# --- loading --------------------------------------------------------------------------------


def _toy():
    """The test fixture hole and player, imported lazily so the package has no test import."""
    if str(SOLVER_DIR) not in sys.path:
        sys.path.insert(0, str(SOLVER_DIR))
    from tests.fixtures.toy_hole import toy_hole, toy_player

    return toy_hole(), toy_player()


def load_hole(label: str, args: argparse.Namespace) -> Hole:
    if label == TOY:
        hole, _ = _toy()
        return hole
    number = int(label)
    traced = (
        args.traced if args.traced else SOLVER_DIR / "data" / "raw" / f"traced_{number}.geojson"
    )
    return build_hole(
        number,
        Path(args.osm),
        Path(traced),
        holes_dir=Path(args.holes_dir),
        out_dir=Path(args.out),
    )


def load_player(label: str, player_path: Path) -> Player | None:
    """The player for ``label``; None (after an error log) when the file is missing."""
    if label == TOY:
        _, player = _toy()
        return player
    player_path = Path(player_path)
    if not player_path.exists():
        log.error("player file %s not found: run `fit` first or pass --player", player_path)
        return None
    return read_player(player_path)


# --- commands -------------------------------------------------------------------------------


def cmd_fit(args: argparse.Namespace) -> int:
    putting = build_putting_table(Path(args.putting))
    player = build_player(Path(args.shots), putting, args.handicap)
    write_player(player, Path(args.out))
    return 0


def cmd_hole(args: argparse.Namespace) -> int:
    hole = load_hole(args.hole, args)
    if args.hole == TOY:  # build_hole writes its own png; the toy needs one here
        write_lie_png(hole, Path(args.out) / f"{TOY}_lie.png")
    log.info("hole %s: %d x %d cells, par %d", args.hole, hole.rows, hole.cols, hole.par)
    return 0


def _solve_and_write(hole: Hole, player: Player, label: str, mode: PenaltyMode, args) -> None:
    t0 = time.perf_counter()
    solution = solve(
        hole,
        player,
        mode,
        K=args.K,
        tol=args.tol,
        max_sweeps=args.max_sweeps,
        seed=args.seed,
        log_every=args.log_every,
    )
    out = Path(args.out)
    write_bundle(solution, hole, player, out, label=label)
    write_value_png(solution, hole, out / f"{label}_{mode}_value.png")
    log.info(
        "hole %s %s: %d sweeps, residual %.4f, %.0f s",
        label,
        mode,
        solution.sweeps,
        solution.residual_history[-1] if solution.residual_history else float("nan"),
        time.perf_counter() - t0,
    )


def cmd_solve(args: argparse.Namespace) -> int:
    player = load_player(args.hole, args.player)
    if player is None:
        return 1
    hole = load_hole(args.hole, args)
    _solve_and_write(hole, player, args.hole, args.mode, args)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    d = bundle_dir(args.out, args.hole, args.mode)
    if not all((d / f).exists() for f in BUNDLE_FILES):
        log.info("no bundle at %s, solving first", d)
        code = cmd_solve(args)
        if code:
            return code
    meta, lie, value, *_ = read_bundle(d)
    log.info("bundle %s: hole %s %s, %d x %d", d, meta["hole"], meta["penalty_mode"], *lie.shape)
    if args.to_app:
        copy_to_app(Path(args.out), Path(args.app_dir))
    return 0


def cmd_not_yet(part: str):
    def run(args: argparse.Namespace) -> int:
        log.error("`%s` is implemented in part %s, which does not exist yet", args.cmd, part)
        return 1

    return run


def has_shot_rows(path: Path) -> bool:
    """True when ``shots.csv`` exists and holds at least one row below the header."""
    return path.exists() and len(path.read_text().splitlines()) > 1


def cmd_all(args: argparse.Namespace) -> int:
    holes = [h.strip() for h in args.holes.split(",") if h.strip()]
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    bad = [m for m in modes if m not in PENALTY_MODES]
    if bad:
        log.error("unknown modes %s; choose from %s", bad, list(PENALTY_MODES))
        return 1
    out = Path(args.out)
    real = [h for h in holes if h != TOY]
    if real:
        if has_shot_rows(Path(args.shots)):
            log.info("fitting player from %s", args.shots)
            cmd_fit(args)
        elif args.player is not None:
            log.info("no shot rows in %s: using %s", args.shots, args.player)
            player = load_player(real[0], args.player)
            if player is None:
                return 1
            write_player(player, out)
        elif not (out / "player.json").exists():
            log.error("no shot rows in %s and no %s: cannot solve real holes", args.shots, out)
            return 1
        player = read_player(out / "player.json")
    elif holes:  # toy only: the app's player.json is the toy player
        _, toy_player = _toy()
        write_player(toy_player, out)
    for label in holes:
        hole = load_hole(label, args)
        hole_player = player if label != TOY else _toy()[1]
        for mode in modes:
            _solve_and_write(hole, hole_player, label, mode, args)
    if args.to_app:
        copy_to_app(out, Path(args.app_dir))
    return 0


# --- parser ---------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    common.add_argument("-v", "--verbose", action="store_true", help="debug logging")

    hole_io = argparse.ArgumentParser(add_help=False)
    hole_io.add_argument("--osm", type=Path, default=DEFAULT_OSM)
    hole_io.add_argument("--traced", type=Path, default=None, help="traced_<hole>.geojson")
    hole_io.add_argument("--holes-dir", type=Path, default=DEFAULT_HOLES_DIR)

    solve_opts = argparse.ArgumentParser(add_help=False)
    solve_opts.add_argument("--K", type=int, default=200)
    solve_opts.add_argument("--tol", type=float, default=0.01)
    solve_opts.add_argument("--max-sweeps", type=int, default=100)
    solve_opts.add_argument("--seed", type=int, default=0)
    solve_opts.add_argument("--log-every", type=int, default=5)

    fit_opts = argparse.ArgumentParser(add_help=False)
    fit_opts.add_argument("--shots", type=Path, default=DEFAULT_SHOTS)
    fit_opts.add_argument("--putting", type=Path, default=DEFAULT_PUTTING)
    fit_opts.add_argument("--handicap", type=int, default=DEFAULT_HANDICAP)

    app_opts = argparse.ArgumentParser(add_help=False)
    app_opts.add_argument("--to-app", action="store_true", help="copy to app/public/data")
    app_opts.add_argument("--app-dir", type=Path, default=DEFAULT_APP_DATA)

    p = argparse.ArgumentParser(prog="python -m caddie", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("fit", parents=[common, fit_opts], help="fit player.json from shots")
    s.set_defaults(func=cmd_fit)

    s = sub.add_parser("hole", parents=[common, hole_io], help="build a hole and its lie png")
    s.add_argument("hole", choices=(*REAL_HOLES, TOY))
    s.set_defaults(func=cmd_hole)

    s = sub.add_parser("solve", parents=[common, hole_io, solve_opts], help="value iteration")
    s.add_argument("hole", choices=(*REAL_HOLES, TOY))
    s.add_argument("--mode", choices=PENALTY_MODES, required=True)
    s.add_argument("--player", type=Path, default=DEFAULT_OUT / "player.json")
    s.set_defaults(func=cmd_solve)

    s = sub.add_parser("recommend", parents=[common], help="part 06")
    s.add_argument("hole", choices=(*REAL_HOLES, TOY))
    s.add_argument("--x", type=float, required=True)
    s.add_argument("--y", type=float, required=True)
    s.add_argument("--lie", default=None)
    s.add_argument("--mode", choices=PENALTY_MODES, required=True)
    s.set_defaults(func=cmd_not_yet("06"))

    s = sub.add_parser("evaluate", parents=[common], help="part 07")
    s.add_argument("hole", choices=(*REAL_HOLES, TOY))
    s.add_argument("--mode", choices=PENALTY_MODES, required=True)
    s.add_argument("--n", type=int, default=2000)
    s.add_argument("--boot", type=int, default=50)
    s.set_defaults(func=cmd_not_yet("07"))

    s = sub.add_parser(
        "export", parents=[common, hole_io, solve_opts, app_opts], help="bundle for the app"
    )
    s.add_argument("hole", choices=(*REAL_HOLES, TOY))
    s.add_argument("--mode", choices=PENALTY_MODES, required=True)
    s.add_argument("--player", type=Path, default=DEFAULT_OUT / "player.json")
    s.set_defaults(func=cmd_export)

    s = sub.add_parser(
        "all",
        parents=[common, hole_io, solve_opts, fit_opts, app_opts],
        help="fit (if shots exist) + hole + solve + export for every hole and mode",
    )
    s.add_argument("--modes", default="drop,replay")
    s.add_argument("--holes", default="10,11,12")
    s.add_argument(
        "--player", type=Path, default=None, help="player.json to use when shots.csv has no rows"
    )
    s.set_defaults(func=cmd_all)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return int(args.func(args))
