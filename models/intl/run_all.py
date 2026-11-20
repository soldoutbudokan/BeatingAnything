"""One-command pipeline for the Test and ODI models.

    python -m models.intl.run_all [odi] [test] [--force] [--retune] [--skip-download] [--skip-schedule]

Steps are cached on their output files; --force rebuilds everything downstream of the download and --retune
re-runs the walk-forward search (slow: about 1.5 hours a format on 4 cores). The adopted configuration is
models/intl/static/hyper_<format>.json; a retune only refreshes the evidence shown under Diagnostics, unless that
file is deleted first (`python -m models.intl.tune <format> adopt` writes it from the search).

Needs numpy, pandas, scipy, numba, scikit-learn, pyarrow, pyreadr (not in requirements-lock.txt: use a
virtualenv) and node on the PATH for the simulator.
"""
# %% imports
import sys
import time
import urllib.request

from models.intl.config import FORMATS, META_RDA, PEOPLE

META_URL = "https://raw.githubusercontent.com/robjhyndman/cricketdata/master/data/player_meta.rda"


def step(name, outputs, fn, force=False, inputs=()):
    newest_in = max([p.stat().st_mtime for p in inputs if p.exists()] or [0])
    if not force and all(o.exists() for o in outputs) and min(o.stat().st_mtime for o in outputs) >= newest_in:
        print(f"[cached] {name}")
        return
    t = time.time()
    print(f"[run] {name}", flush=True)
    fn()
    print(f"[done] {name} {time.time() - t:.0f}s", flush=True)


def main(argv):
    keys = [a for a in argv if a in FORMATS] or ["odi", "test"]
    force, args = "--force" in argv, set(argv)
    if "--skip-download" not in args:
        urls = {PEOPLE: "https://cricsheet.org/register/people.csv", META_RDA: META_URL}
        urls.update({FORMATS[k].zip: f"https://cricsheet.org/downloads/{FORMATS[k].zip_name}" for k in ("odi", "test")})
        for path, url in urls.items():
            if force or not path.exists():
                print(f"[download] {url}")
                path.parent.mkdir(parents=True, exist_ok=True)
                urllib.request.urlretrieve(url, path)
    from models.intl import diagnostics, export, final_fit, holdout, ingest, meta, method, prep, ratings, schedule, tune
    # both formats are ingested first: each one's priors read the other's record
    for k in ("odi", "test"):
        fmt = FORMATS[k]
        step(f"{k}: ingest", [fmt.proc / "balls.parquet", fmt.proc / "matches.parquet"], lambda k=k: ingest.main(k), force, [fmt.zip])
    for k in ("odi", "test"):
        fmt = FORMATS[k]
        other = FORMATS["test" if k == "odi" else "odi"]
        step(f"{k}: model frame", [fmt.proc / "frame.parquet"], lambda k=k: prep.build(k), force,
             [fmt.proc / "balls.parquet", other.proc / "balls.parquet"])
    for k in keys:
        fmt = FORMATS[k]
        ex, pr = fmt.export, fmt.proc
        if "--retune" in args or not (pr / "tuning_r1.json").exists():
            for rnd in (1, 2):
                tune.run(k, rnd)
            if not (final_fit.STATIC / f"hyper_{k}.json").exists():
                tune.adopt(k)   # a tracked hyper file is never overwritten: delete it to adopt a new search
        step(f"{k}: final fit", [pr / "model.pkl"], lambda k=k: final_fit.main(k), force, [pr / "frame.parquet", final_fit.STATIC / f"hyper_{k}.json"])
        step(f"{k}: walk-forward holdout", [pr / "holdout_eta.npz"], lambda k=k: holdout.main(k), force, [pr / "frame.parquet", final_fit.STATIC / f"hyper_{k}.json"])
        step(f"{k}: ratings + sim params", [pr / "ratings.pkl", ex / "sim_params.json"], lambda k=k: ratings.main(k), force,
             [pr / "model.pkl", pr / "holdout_eta.npz"])
        step(f"{k}: players, teams, grounds", [ex / "players.json", ex / "teams.json", ex / "venues.json", ex / "ids.json"],
             lambda k=k: export.main(k), force, [pr / "ratings.pkl"])
        step(f"{k}: diagnostics", [ex / "diagnostics.json"], lambda k=k: diagnostics.main(k), force, [ex / "sim_params.json", ex / "teams.json"])
    if "--skip-schedule" not in args:
        schedule.main(keys)
    for k in keys:
        method.main(k)
        meta.main(k)


if __name__ == "__main__":
    main(sys.argv[1:])
