"""meta.json: build info, data counts, hyper-parameters, file sizes, parity/speed."""
# %% imports
import json
import pickle
from datetime import datetime, timezone

import pandas as pd

from models.ipl.config import EXPORT, PROC


def main():
    m = pd.read_parquet(PROC / "matches.parquet")
    b = pd.read_parquet(PROC / "balls.parquet", columns=["comp", "date", "super_over", "reduced"])
    with open(PROC / "model.pkl", "rb") as fh:
        MD = pickle.load(fh)
    parity = json.loads((PROC / "parity.json").read_text()) if (PROC / "parity.json").exists() else {}
    st = pickle.load(open(PROC / "export_state.pkl", "rb")) if (PROC / "export_state.pkl").exists() else {}
    styles = pd.read_parquet(PROC / "styles.parquet")
    by_comp = m.groupby("comp").agg(matches=("match_id", "size"), first=("date", "min"), last=("date", "max"))
    balls_comp = b.groupby("comp", observed=True).size()
    files = {str(p.relative_to(EXPORT)): p.stat().st_size for p in sorted(EXPORT.rglob("*")) if p.is_file()}
    mfiles = sorted(k for k in files if k.startswith("matchups/"))
    meta = {
        "build_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_source": "cricsheet.org all_male_json.zip (men's T20 / IT20, 20-over matches) + register/people.csv",
        "data_cutoff": str(m["date"].max().date()),
        "ipl_latest_season": int(m.loc[m["comp"] == "IPL", "date"].dt.year.max()),
        "ipl_last_match": str(m.loc[m["comp"] == "IPL", "date"].max().date()),
        "counts": {"matches": int(len(m)), "deliveries": int(len(b)),
                   "deliveries_modelled": int(MD["n"]),
                   "matches_reduced_or_dls_excluded": int(m["reduced"].sum()),
                   "by_comp": {c: {"matches": int(r["matches"]), "deliveries": int(balls_comp.get(c, 0)),
                                   "first": str(r["first"].date()), "last": str(r["last"].date())}
                               for c, r in by_comp.iterrows()}},
        "model": {"half_life_years": MD["half_life"], "penalties": MD["lam"], "lbfgs_iterations": MD["iters"],
                  "n_coefficients": int(MD["p"]) * 10, "ref_date": MD["ref_date"]},
        "styles": {"players_with_style": int(len(styles)), "bowling_group_inferred": int(styles["style_inferred"].sum())},
        "sim": {"python_sec_per_10k": parity.get("py_sec_per_10k"), "js_node_sec_per_10k": parity.get("js_sec_per_10k_node"),
                "parity": {k: parity.get(k) for k in ("comparisons", "max_abs_z", "share_abs_z_gt_2", "mean_abs_z", "pass")},
                "runs_to_win_prob": st.get("slope"), "runs_to_win_prob_detail": st.get("runs_to_wp"),
                "match_shock": (json.loads((EXPORT / "sim_params.json").read_text()).get("match_shock") or {}).get("sd")},
        "files_bytes": files, "total_bytes": int(sum(files.values())),
        "matchups": {"files": mfiles, "index": "matchups/index.json"},
    }
    (EXPORT / "meta.json").write_text(json.dumps(meta, indent=1))
    print(f"meta: total export {meta['total_bytes'] / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
