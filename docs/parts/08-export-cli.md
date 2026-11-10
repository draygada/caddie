# Part 08: export.py and cli.py

Branch `part/08-export-cli`. Scope: `solver/caddie/export.py`, `solver/caddie/cli.py`, `solver/caddie/__main__.py`, `solver/tests/test_export.py`.

## Purpose

Write the data bundle the app consumes, exactly per the root contract, and provide the command line entry points used by every other part's "Done when".

## Interfaces

```python
def write_bundle(solution: Solution, hole: Hole, player: Player, out_dir: Path) -> None
    # out_dir/<hole>/<mode>/{meta.json, lie.u8, value.f32, club.u8, dir.u8}
    # value.f32 holds strokes-to-go (positive), float32 little-endian, NaN on OUT
    # meta.json fields exactly as the root contract; polygons in grid meters, simplified with shapely .simplify(1.0)

def write_player(player: Player, out_dir: Path) -> None     # out_dir/player.json

def read_bundle(dir: Path) -> tuple[dict, np.ndarray, np.ndarray, np.ndarray, np.ndarray]   # for tests and evaluate.py

def copy_to_app(out_dir: Path, app_data_dir: Path = Path("../app/public/data")) -> None
```

CLI (`python -m caddie <cmd>`):

```
fit        --shots PATH --putting PATH --handicap N --out PATH
hole       HOLE                                  # build_hole + lie png
solve      HOLE --mode {mulligan,drop,replay} [--K 200] [--tol 0.01] [--player PATH]
recommend  HOLE --x --y [--lie] --mode
evaluate   HOLE --mode [--n 2000] [--boot 50]
export     HOLE --mode [--to-app]
all        --modes drop,replay --holes 10,11,12 --to-app      # fit (if shots exist) + hole + solve + export for every pair
```

## Slices

1. **write_bundle round trip.** Toy solution written and read back; arrays equal; `meta.json` has every contract key and `len(directions_deg) == 91`.
2. **Byte layout.** `value.f32` file size is `rows * cols * 4`; first float read with `struct.unpack("<f")` equals `U[0]`.
3. **CLI.** `fit`, `hole`, `solve`, `export` subcommands wired with argparse; `solve` logs residual every 5 sweeps; exit code 1 with a message if the player file is missing.
4. **all and copy_to_app.** `all --holes toy --modes drop` populates `app/public/data/toy/drop/`.
5. **Fixture bundle for the app.** Commit `app/public/data/toy/drop/` and `app/public/data/player.json` from the toy hole so part 09 has data before real holes exist.

## Done when

`uv run python -m caddie all --holes 10 --modes drop --to-app` leaves five files in `app/public/data/10/drop/` and `npm run dev` in the app (part 10 onward) can load them.
