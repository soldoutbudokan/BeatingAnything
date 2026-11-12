"""JS-vs-Python simulator parity: same params and lineups, independent RNG streams; compare within MC error."""
# %% imports
import json
import subprocess
import time

import numpy as np

from models.ipl.config import EXPORT, PROC, ROOT
from models.ipl.sim import Params, sim_match, summarize

N = 20000


def main():
    P = Params.load()
    teams = {t["name"]: t for t in json.loads((EXPORT / "teams.json").read_text())["teams"]}
    names = sorted(teams)
    pairs = [(names[0], names[1]), (names[2], names[3]), (names[4], names[5]), (names[6], names[7]), (names[8], names[9])]
    cases = []
    t_py = []
    py = []
    for k, (a, b) in enumerate(pairs):
        A = {"name": a, "order": teams[a]["order"], "plan": teams[a]["plan"]}
        B = {"name": b, "order": teams[b]["order"], "plan": teams[b]["plan"]}
        v = teams[a]["home_venue"]
        t = time.time()
        s = summarize(sim_match(P, A, B, v, n=N, seed=k + 1), A, B)
        t_py.append((time.time() - t) * 10000 / N)
        cases.append({"A": A, "B": B, "venue": v, "n": N})
        py.append(s)
    ref = PROC / "parity_py.json"
    ref.write_text(json.dumps({"cases": cases}))
    out = PROC / "parity_js.json"
    subprocess.run(["node", str(ROOT / "models/ipl/parity.js"), str(ref), str(out)], check=True)
    js = json.loads(out.read_text())
    rows = []
    worst = 0.0
    for c, s_py, s_js in zip(cases, py, js["cases"]):
        def cmp(label, a, b, sd):
            nonlocal worst
            se = sd * np.sqrt(2.0 / N)
            z = (a - b) / se if se > 0 else 0.0
            worst = max(worst, abs(z))
            rows.append({"case": f"{c['A']['name']} v {c['B']['name']}", "metric": label, "py": a, "js": b, "z": z})
        p = s_py["p_win_A"]
        cmp("p_win_A", p, s_js["p_win_A"], np.sqrt(p * (1 - p)))
        for side in ("A", "B"):
            cmp(f"{side} total_mean", s_py[side]["total_mean"], s_js[side]["total_mean"], s_py[side]["total_sd"])
            cmp(f"{side} wkts_mean", s_py[side]["wkts_mean"], s_js[side]["wkts_mean"], 2.0)
            cmp(f"{side} sixes_mean", s_py[side]["sixes_mean"], s_js[side]["sixes_mean"], 3.0)
            cmp(f"{side} pp_mean", s_py[side]["pp_mean"], s_js[side]["pp_mean"], 15.0)
            # per-player runs for the top 4 batters (T20 individual scores are roughly exponential: sd ~ mean)
            for pid in c[side]["order"][:4]:
                a, b = s_py[side]["players"][pid]["runs_mean"], s_js[side]["players"][pid]["runs_mean"]
                cmp(f"{side} {pid} runs_mean", a, b, max(a, 5.0))
            for pl in c[side]["plan"][:3]:
                pid = pl["id"]
                a, b = s_py[side]["players"][pid]["wkts_mean"], s_js[side]["players"][pid]["wkts_mean"]
                cmp(f"{side} {pid} wkts_mean", a, b, 0.9)
    zs = np.array([r["z"] for r in rows])
    res = {"n_sims_each": N, "cases": len(cases), "comparisons": len(rows), "max_abs_z": float(np.abs(zs).max()),
           "share_abs_z_gt_2": float(np.mean(np.abs(zs) > 2)), "mean_abs_z": float(np.mean(np.abs(zs))),
           "py_sec_per_10k": float(np.mean(t_py)), "js_sec_per_10k_node": float(np.median(js["timings"])),
           "rows": rows, "pass": bool(np.abs(zs).max() < 4.5 and np.mean(np.abs(zs) > 2) < 0.12)}
    (PROC / "parity.json").write_text(json.dumps(res, indent=1))
    print(f"parity: {len(rows)} comparisons, max|z|={res['max_abs_z']:.2f}, share|z|>2={res['share_abs_z_gt_2']:.3f}, "
          f"py {res['py_sec_per_10k']:.2f}s/10k, js {res['js_sec_per_10k_node']:.2f}s/10k, pass={res['pass']}")
    return res


if __name__ == "__main__":
    main()
