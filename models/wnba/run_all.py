# %% One-command pipeline: python -m models.wnba.run_all [--force] [--refresh] [--from STEP]
"""Steps run in order; each caches its output in data/processed/wnba and is skipped when present.
--force rebuilds every step, --from STEP rebuilds STEP and everything after it, --refresh re-downloads
the current season and ESPN rosters (implies --force)."""
from __future__ import annotations

import importlib
import sys
import time

STEPS = ["download", "parse_pbp", "shot_model", "rosters", "rapm", "skills", "minutes", "context", "params", "game_effects",
         "export", "diagnostics", "parity"]


def main(argv):
    force = "--force" in argv or "--refresh" in argv
    start = None
    if "--from" in argv:
        start = argv[argv.index("--from") + 1]
    on = start is None
    for step in STEPS:
        if step == start:
            on = True
        mod = importlib.import_module(f"models.wnba.{step}")
        t = time.time()
        if step == "download":
            mod.main(refresh="--refresh" in argv)
        elif step == "parity":
            import shutil
            import subprocess
            mod.main()
            if shutil.which("node"):
                from models.wnba.common import ROOT
                subprocess.run(["node", str(ROOT / "models/wnba/parity_check.js")], check=False)
        else:
            mod.main(force=force or (start is not None and on))
        print(f"  [{step}] {time.time() - t:.1f}s")


if __name__ == "__main__":
    main(sys.argv[1:])
