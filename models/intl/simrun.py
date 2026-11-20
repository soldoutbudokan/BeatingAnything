"""Run simulation jobs through the JavaScript engine under node (models/intl/sim_cli.js), in parallel."""
# %% imports
import json
import subprocess
import tempfile
from pathlib import Path

from models.intl.config import ROOT

CLI = ROOT / "models" / "intl" / "sim_cli.js"


def run_jobs(params_path, jobs, procs=4):
    """jobs: list of {id, A, B, opts, n, seed, hists}. Returns {id: result}; ids must be unique."""
    if not jobs:
        return {}
    procs = max(1, min(procs, len(jobs)))
    chunks = [jobs[k::procs] for k in range(procs)]
    with tempfile.TemporaryDirectory() as td:
        running = []
        for k, ch in enumerate(chunks):
            jp, op = Path(td) / f"jobs{k}.json", Path(td) / f"out{k}.json"
            jp.write_text(json.dumps({"params": str(params_path), "jobs": ch}))
            running.append((subprocess.Popen(["node", str(CLI), str(jp), str(op)]), op))
        out, secs = {}, 0.0
        for pr, op in running:
            if pr.wait() != 0:
                raise RuntimeError("sim_cli.js failed")
            res = json.loads(op.read_text())
            secs = max(secs, res["secs"])
            for r in res["results"]:
                out[r["id"]] = r
    return out
