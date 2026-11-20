"""meta.json: build stamp, data counts, adopted hyper-parameters, file sizes, simulator speed."""
# %% imports
import json
import pickle
import sys
import time
from datetime import datetime, timezone

import pandas as pd

from models.intl.config import FORMATS
from models.intl.simrun import run_jobs


def sim_speed(fmt):
    """Seconds per 1,000 simulated matches in node, single process (first fixture-like pairing of the top two sides)."""
    teams = json.loads((fmt.export / "teams.json").read_text())["teams"]
    a, b = teams[0], teams[1]
    spec = lambda t: {"name": t["name"], "order": t["default"]["order"], "plan": t["default"]["plan"]}
    n = 1000 if fmt.key == "test" else 4000
    t = time.time()
    res = run_jobs(fmt.export / "sim_params.json", [{"id": "speed", "A": spec(a), "B": spec(b), "n": n, "opts": {"country": "_default"}}], procs=1)
    return round((time.time() - t) * 1000 / n, 2), res["speed"]["summary"]["n"]


def main(key):
    fmt = FORMATS[key]
    m = pd.read_parquet(fmt.proc / "matches.parquet")
    with open(fmt.proc / "model.pkl", "rb") as fh:
        MD = pickle.load(fh)
    players = json.loads((fmt.export / "players.json").read_text())["players"]
    sch = fmt.export / "schedule.json"
    fixtures = json.loads(sch.read_text()) if sch.exists() else {"fixtures": []}
    secs, _ = sim_speed(fmt)
    files = {str(p.relative_to(fmt.export)): p.stat().st_size for p in sorted(fmt.export.rglob("*")) if p.is_file() and p.name != "meta.json"}
    meta = {
        "build_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "format": fmt.name,
        "data_source": f"cricsheet.org {fmt.zip_name} (men's {fmt.match_type} matches, ball by ball) + register/people.csv; fixtures from ESPN",
        "data_cutoff": str(m["date"].max().date()),
        "n_players": len(players),
        "counts": {"matches": int(len(m)), "matches_excluded_shortened": int(m["reduced"].sum()), "deliveries_modelled": int(MD["n"]),
                   "first_match": str(m["date"].min().date()), "teams": sorted(set(m["team1"]) | set(m["team2"])),
                   "fixtures": len(fixtures["fixtures"]), "fixtures_modelled": sum(1 for f in fixtures["fixtures"] if f.get("modelled"))},
        "model": {"half_life_years": MD["half_life"], "penalties": MD["lam"], "lbfgs_iterations": MD["iters"],
                  "n_coefficients": int(MD["p"]) * 10, "ref_date": MD["ref_date"]},
        "sim": {"engine": "docs/models/cricket/sim.js (one engine: browser and build)", "node_sec_per_1000_matches": secs},
        "schedule_generated_utc": fixtures.get("generated_utc"),
        "files_bytes": files, "total_bytes": int(sum(files.values())),
    }
    (fmt.export / "meta.json").write_text(json.dumps(meta, indent=1))
    print(f"{key}: meta total export {meta['total_bytes'] / 1e6:.2f} MB, sim {secs}s per 1,000 matches")


if __name__ == "__main__":
    for k in (sys.argv[1:] or ["odi", "test"]):
        main(k)
