"""One-command pipeline: python -m models.ipl.run_all [--force] [--retune] [--skip-download]

Steps are cached on output files; --force rebuilds everything downstream of the download,
--retune re-runs the half-life / shrinkage search (slow: ~1 h on 4 cores).
"""
# %% imports
import subprocess
import sys
import time
import urllib.request

from models.ipl.config import ALL_ZIP, EXPORT, PEOPLE, PROC, ROOT

URLS = {ALL_ZIP: "https://cricsheet.org/downloads/all_male_json.zip",
        PEOPLE: "https://cricsheet.org/register/people.csv"}


def step(name, outputs, fn, force=False, inputs=()):
    newest_in = max([p.stat().st_mtime for p in inputs if p.exists()] or [0])
    if not force and all(o.exists() for o in outputs) and min(o.stat().st_mtime for o in outputs) >= newest_in:
        print(f"[cached] {name}")
        return
    t = time.time()
    print(f"[run] {name}")
    fn()
    print(f"[done] {name} {time.time() - t:.0f}s")


def main():
    args = set(sys.argv[1:])
    force = "--force" in args
    if "--skip-download" not in args:
        for path, url in URLS.items():
            if force or not path.exists():
                print(f"[download] {url}")
                urllib.request.urlretrieve(url, path)
    from models.ipl import (diagnostics, export, final_fit, holdout, ingest, parity, prep, ratings, tune, tune_r2, tune_r3, wp)
    step("ingest", [PROC / "balls.parquet", PROC / "matches.parquet"], ingest.main, force, [ALL_ZIP])
    step("prep", [PROC / "frame.parquet"], prep.build, force, [PROC / "balls.parquet"])
    if "--retune" in args or not (PROC / "tuning.json").exists():
        tune.run([(H, {}) for H in (4.0, 2.5, 6.0)] + tune.null_baseline())
        tune.run(tune.stage2_grid())
        tune.run(tune.stage3_grid())
        tune.run(tune.stage3_converged())
        tune_r2.tune.OUT = PROC / "tuning_r2.json"; tune.run(tune_r2.GRID)
        tune.OUT = PROC / "tuning_r3.json"; tune.run(tune_r3.GRID)
    step("final fit", [PROC / "model.pkl"], final_fit.main, force, [PROC / "frame.parquet", PROC / "tuning.json"])
    step("holdout model", [PROC / "model_holdout.pkl", PROC / "holdout_pred.parquet"], holdout.main, force,
         [PROC / "frame.parquet"])
    step("win probability", [PROC / "wpa.pkl"], wp.main, force, [PROC / "frame.parquet"])
    step("ratings + sim params", [PROC / "ratings.pkl", EXPORT / "sim_params.json"], ratings.main, force, [PROC / "model.pkl"])
    step("teams, value, matchups, exports", [EXPORT / "players.json", EXPORT / "matchups.json"], export.main, force,
         [PROC / "ratings.pkl", PROC / "wpa.pkl"])
    step("diagnostics", [EXPORT / "diagnostics.json"], diagnostics.main, force, [EXPORT / "sim_params.json"])
    step("parity", [PROC / "parity.json"], parity.main, force, [EXPORT / "sim_params.json", ROOT / "docs/models/ipl/sim.js"])
    from models.ipl import meta
    meta.main()


if __name__ == "__main__":
    main()
