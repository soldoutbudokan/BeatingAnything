"""Console sanity report: top players by value, phase specialists, team ratings, export sizes."""
# %% imports
import json

import pandas as pd

from models.ipl.config import EXPORT


def main(n=15):
    P = json.loads((EXPORT / "players.json").read_text())
    rows = []
    for p in P["players"]:
        b, w = p.get("bat") or {}, p.get("bowl") or {}
        ob = b.get("obs_2024") or {}
        ow = w.get("obs_2024") or {}
        rows.append(dict(name=p["name"], team=(p["team"] or "")[:12], bat_varp=(b.get("value") or {}).get("varp_runs"),
                         bowl_varp=(w.get("value") or {}).get("varp_runs"), sr=b.get("all", {}).get("sr"), avg=b.get("all", {}).get("avg"),
                         rv100=b.get("all", {}).get("rv100"), d_sr=b.get("death", {}).get("sr"), pp_sr=b.get("pp", {}).get("sr"),
                         sd_sr=(b.get("sd") or {}).get("sr"), slot=(b.get("value") or {}).get("slot"),
                         balls24=ob.get("balls"), osr=ob.get("sr"), rae=ob.get("rae100"),
                         econ=w.get("all", {}).get("econ"), wkt=w.get("all", {}).get("wkt_pct"), pp_e=w.get("pp", {}).get("econ"),
                         de_e=w.get("death", {}).get("econ"), sd_e=(w.get("sd") or {}).get("econ"), wballs24=ow.get("balls"),
                         oecon=ow.get("econ"), saved=ow.get("runs_saved")))
    d = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    r = lambda x: x.round(2)
    print("TOP BATTERS by bat VARP (runs/match)")
    print(r(d.sort_values("bat_varp", ascending=False).head(n)[["name", "team", "slot", "bat_varp", "sr", "avg", "rv100", "pp_sr", "d_sr", "sd_sr", "balls24", "osr", "rae"]]).to_string(index=False))
    print("\nTOP BOWLERS by bowl VARP (runs/4 overs)")
    print(r(d.sort_values("bowl_varp", ascending=False).head(n)[["name", "team", "bowl_varp", "econ", "wkt", "pp_e", "de_e", "sd_e", "wballs24", "oecon", "saved"]]).to_string(index=False))
    dd = d[d["wballs24"].fillna(0) >= 200]
    print("\nBEST DEATH ECONOMY (>=200 balls since 2024)")
    print(r(dd.sort_values("de_e").head(10)[["name", "team", "de_e", "econ", "wkt", "oecon"]]).to_string(index=False))
    print("\nBEST POWERPLAY ECONOMY")
    print(r(dd.sort_values("pp_e").head(10)[["name", "team", "pp_e", "econ", "wkt"]]).to_string(index=False))
    db = d[d["balls24"].fillna(0) >= 200]
    print("\nBEST DEATH SR (batters >=200 balls since 2024)")
    print(r(db.sort_values("d_sr", ascending=False).head(10)[["name", "team", "d_sr", "sr", "avg", "osr"]]).to_string(index=False))
    print("\nBEST POWERPLAY SR")
    print(r(db.sort_values("pp_sr", ascending=False).head(10)[["name", "team", "pp_sr", "sr", "avg", "osr"]]).to_string(index=False))
    T = json.loads((EXPORT / "teams.json").read_text())
    print("\nTEAMS")
    for t in sorted(T["teams"], key=lambda t: t["rating"]["rank"]):
        rt = t["rating"]
        print(f"{rt['rank']:2d} {t['short']:5s} neutral win {rt['win_pct_neutral']:.3f}  h/a {rt['win_pct_home_away']:.3f}  "
              f"for {rt['runs_for']:.1f} against {rt['runs_against']:.1f}  XI VARP {rt['xi_varp']:.1f}")
    return d


if __name__ == "__main__":
    main()
