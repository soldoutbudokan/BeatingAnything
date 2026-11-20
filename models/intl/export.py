"""Site exports for one format: players.json, teams.json (with simulated team ratings), venues.json, ids.json.

Usage: python -m models.intl.export odi|test
"""
# %% imports
import json
import pickle
import sys

import numpy as np
import pandas as pd

from models.intl.config import FORMATS, FULL_MEMBERS, META_RDA, ROLES_BAT, ROLES_BOWL, TYPES6
from models.intl.fit import load
from models.intl.ratings import load_people
from models.intl.simrun import run_jobs
from models.intl.team import build as build_teams

RATING_SIMS = 3000


def rnd(x, d=3):
    if isinstance(x, dict):
        return {k: rnd(v, d) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [rnd(v, d) for v in x]
    if isinstance(x, (float, np.floating)):
        return None if not np.isfinite(x) else round(float(x), d)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def dump(fmt, name, obj, d=3):
    (fmt.export / name).write_text(json.dumps(rnd(obj, d), separators=(",", ":"), allow_nan=False))


def display_names(ids, short):
    """Full names from cricketdata where it has them, cricsheet's scorecard names otherwise."""
    out = dict(short)
    if META_RDA.exists():
        import pyreadr
        m = list(pyreadr.read_r(str(META_RDA)).values())[0].dropna(subset=["cricsheet_id"]).drop_duplicates("cricsheet_id")
        full = m.set_index("cricsheet_id")["name"].dropna().to_dict()
        for i in ids:
            if i in full and isinstance(full[i], str) and len(full[i]) > 2:
                out[i] = full[i]
    return out


def raw_counts(d):
    cls = d["cls"].astype(str)
    faced = cls != "wide"
    out = (cls == "wicket") | ((cls == "runout") & (d["player_out"] == d["batter"]))
    brun = np.where(cls.isin(["r1", "r2", "r3", "r4", "r6", "noball", "runout"]), d["runs_bat"], 0)
    key = d["match_id"].astype(str) + "|" + d["inn"].astype(str)
    b = pd.DataFrame({"id": d["batter"], "faced": faced, "runs": brun, "out": out, "k": key}).groupby("id").agg(
        balls=("faced", "sum"), runs=("runs", "sum"), outs=("out", "sum"), inns=("k", "nunique"))
    legal = ~cls.isin(["wide", "noball"])
    w = pd.DataFrame({"id": d["bowler"], "legal": legal, "conc": d["runs_total"] - d["byes"], "wkt": cls == "wicket",
                      "m": d["match_id"]}).groupby("id").agg(balls=("legal", "sum"), conc=("conc", "sum"), wkts=("wkt", "sum"),
                                                              matches=("m", "nunique"))
    return b, w


def team_spec(t, lineup=None):
    lu = lineup or t["default"]
    return {"name": t["name"], "order": lu["order"], "plan": lu["plan"]}


def team_ratings(fmt, teams):
    """Every pair on neutral ground in the average full-member environment, default XIs."""
    names = sorted(teams)
    jobs = []
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            jobs.append({"id": f"{names[a]}|{names[b]}", "A": team_spec(teams[names[a]]), "B": team_spec(teams[names[b]]),
                         "opts": {"country": "_default", "home": None}, "n": RATING_SIMS, "seed": 1000 + len(jobs)})
    res = run_jobs(fmt.export / "sim_params.json", jobs)
    acc = {n: [] for n in names}
    pairs = []
    for j in jobs:
        a, b = j["id"].split("|")
        s = res[j["id"]]["summary"]
        pairs.append({"A": a, "B": b, "p_A": s["p_A"], "p_B": s["p_B"], "p_draw": s["p_draw"], "p_tie": s["p_tie"]})
        acc[a].append((b, s["p_A"], s["p_draw"], s["first"]["A"]["inn1_mean"] if s["first"]["A"] else None,
                       s["first"]["B"]["inn1_mean"] if s["first"]["B"] else None))
        acc[b].append((a, s["p_B"], s["p_draw"], s["first"]["B"]["inn1_mean"] if s["first"]["B"] else None,
                       s["first"]["A"]["inn1_mean"] if s["first"]["A"] else None))
    out = {}
    for n in names:
        rows = acc[n]
        fm = [r for r in rows if r[0] in FULL_MEMBERS] or rows
        mean = lambda rs, k: float(np.mean([r[k] for r in rs if r[k] is not None])) if rs else None
        out[n] = {"win_pct": mean(rows, 1), "draw_pct": mean(rows, 2), "win_pct_fm": mean(fm, 1), "draw_pct_fm": mean(fm, 2),
                  "bat_first_total": mean(fm, 3), "bowl_first_total": mean(fm, 4), "n_opponents": len(rows)}
        out[n]["net_runs"] = out[n]["bat_first_total"] - out[n]["bowl_first_total"]
    order = sorted(names, key=lambda n: -(out[n]["win_pct_fm"] + 0.5 * out[n]["draw_pct_fm"]))
    for k, n in enumerate(order):
        out[n]["rank"] = k + 1
    return out, pairs


def main(key):
    fmt = FORMATS[key]
    f = load(key)
    styles = pd.read_parquet(fmt.proc / "styles.parquet")
    with open(fmt.proc / "ratings.pkl", "rb") as fh:
        R = pickle.load(fh)
    short, people = load_people()
    pool = R["pool"]
    teams = build_teams(key)
    squad_ids = {s["id"] for t in teams.values() for s in t["squad"]}
    names = display_names(set(pool) | squad_ids, short)
    bat, bowl = R["bat"], R["bowl"]
    cur_team = {}
    for col, tcol in (("batter", "bat_team"), ("bowler", "bowl_team")):
        cur_team.update(f.groupby(col)[tcol].last().astype(str).to_dict())
    for t in teams.values():   # the squad listing wins (a player's latest side)
        for s in t["squad"]:
            cur_team[s["id"]] = t["name"]
    last_played = pd.concat([f.groupby(c)["date"].max() for c in ("batter", "non_striker", "bowler")]).groupby(level=0).max()
    car_b, car_w = raw_counts(f)
    rec_b, rec_w = raw_counts(f[f["date"] >= fmt.pool_since])
    hs = f.assign(r=np.where(f["cls"].astype(str).isin(["r1", "r2", "r3", "r4", "r6", "noball", "runout"]), f["runs_bat"], 0)) \
        .groupby(["batter", "match_id", "inn"])["r"].sum()
    hs_max = hs.groupby(level=0).max()
    hundreds = (hs >= 100).groupby(level=0).sum()
    fifties = ((hs >= 50) & (hs < 100)).groupby(level=0).sum()
    cb, cw = R["BAT_cov"], R["BOWL_cov"]
    proj = pd.Timestamp(R["proj_date"])
    BK = ("sr", "avg", "out_pct", "bnd_pct", "six_pct", "dot_pct", "rv100")
    WK = ("econ", "avg", "sr", "wkt_pct", "dot_pct", "bnd_pct", "rv_over")
    mixw = R["mix_bowl"]

    def bat_line(o):
        return {"inns": int(o["inns"]), "runs": int(o["runs"]), "balls": int(o["balls"]), "outs": int(o["outs"]),
                "avg": o["runs"] / o["outs"] if o["outs"] else None, "sr": 100 * o["runs"] / o["balls"] if o["balls"] else None}

    def bowl_line(o):
        return {"matches": int(o["matches"]), "balls": int(o["balls"]), "conc": int(o["conc"]), "wkts": int(o["wkts"]),
                "avg": o["conc"] / o["wkts"] if o["wkts"] else None, "econ": 6 * o["conc"] / o["balls"] if o["balls"] else None,
                "sr": o["balls"] / o["wkts"] if o["wkts"] else None}

    players = []
    for pid in pool:
        st = styles.loc[pid] if pid in styles.index else None
        dob = None if st is None or pd.isna(st["dob"]) else st["dob"]
        d = {"id": pid, "name": names.get(pid, pid), "short_name": short.get(pid, pid), "team": cur_team.get(pid),
             "bat_hand": None if st is None or pd.isna(st["bat_hand"]) else st["bat_hand"],
             "bowl_type": None if st is None or pd.isna(st["bowl_type"]) else st["bowl_type"],
             "bowl_group": None if st is None or pd.isna(st["bowl_group"]) else st["bowl_group"],
             "bowl_subtype": None if st is None else st["bowl_subtype"],
             "style_inferred": bool(st["style_inferred"]) if st is not None else False,
             "age": None if dob is None else round((proj - dob).days / 365.25, 1),
             "last_played": str(last_played[pid].date()) if pid in last_played.index else None,
             "in_squad": pid in squad_ids}
        if pid in bat.index:
            b = bat.loc[pid]
            blk = {s: {k: b[f"{s}_{k}"] for k in BK} for s in ("all", "p0", "p1", "p2", "pace", "spin", "home", "away")}
            blk["vs_avg"] = {s: {k: b[f"{s}_{k}"] - b[f"{s}_avg_{k}"] for k in ("sr", "avg", "out_pct", "rv100")}
                             for s in ("all", "p0", "p1", "p2", "pace", "spin", "home", "away")}
            blk["by_type"] = {t: {"sr": b[f"t_{t}_sr"], "avg": b[f"t_{t}_avg"], "out_pct": b[f"t_{t}_out_pct"],
                                  "d_avg": b[f"t_{t}_avg"] - b[f"t_{t}_avg_avg"], "d_sr": b[f"t_{t}_sr"] - b[f"t_{t}_avg_sr"]}
                              for t in TYPES6 if f"t_{t}_sr" in b.index and pd.notna(b[f"t_{t}_sr"])}
            blk["sd"] = {k: b["sd_" + k] for k in ("sr", "avg", "out_pct", "rv100")}
            if pid in cb.index:
                blk["role"] = ROLES_BAT[int(cb.loc[pid, "role"])]
                blk["pos"] = float(cb.loc[pid, "pos"])
            if pid in car_b.index:
                blk["career"] = dict(bat_line(car_b.loc[pid]), hs=int(hs_max.get(pid, 0)), hundreds=int(hundreds.get(pid, 0)),
                                     fifties=int(fifties.get(pid, 0)))
            if pid in rec_b.index:
                blk["recent"] = bat_line(rec_b.loc[pid])
            blk["inactive_factor"] = float(R["bat_inact"].get(pid, 1.0))
            d["bat"] = blk
        if pid in bowl.index and pid in car_w.index and car_w.loc[pid, "balls"] > 0:
            b = bowl.loc[pid]
            blk = {s: {k: b[f"{s}_{k}"] for k in WK} for s in ("all", "p0", "p1", "p2", "rhb", "lhb", "home", "away")}
            blk["vs_avg"] = {s: {k: b[f"{s}_{k}"] - b[f"{s}_avg_{k}"] for k in ("econ", "avg", "wkt_pct", "rv_over")}
                             for s in ("all", "p0", "p1", "p2", "rhb", "lhb", "home", "away")}
            blk["sd"] = {k: b["sd_" + k] for k in ("econ", "avg", "wkt_pct", "rv_over")}
            if pid in cw.index and pd.notna(cw.loc[pid, "role"]):
                blk["role"] = ROLES_BOWL[int(cw.loc[pid, "role"])]
                blk["overs_per_match"] = float(cw.loc[pid, "opm"])
            if pid in mixw.index and mixw.loc[pid].sum() > 0:
                blk["phase_mix"] = (mixw.loc[pid] / mixw.loc[pid].sum()).round(3).tolist()
            blk["career"] = bowl_line(car_w.loc[pid])
            if pid in rec_w.index:
                blk["recent"] = bowl_line(rec_w.loc[pid])
            d["bowl"] = blk
        players.append(d)
    dump(fmt, "players.json", {"players": players, "avg_bat": R["avg_bat"], "avg_bowl": R["avg_bowl"],
                               "phase_labels": list(fmt.phase_labels), "runs_per_wicket_ref": R["rpw"],
                               "ref_since": fmt.ref_since, "pool_since": fmt.pool_since})

    # ---------------- teams.json
    ratings, pairs = team_ratings(fmt, teams)
    rows = []
    for t in sorted(teams.values(), key=lambda x: ratings[x["name"]]["rank"]):
        for s in t["squad"]:
            s["name"] = names.get(s["id"], s["id"])
        rows.append(dict(t, rating=ratings[t["name"]]))
    dump(fmt, "teams.json", {"teams": rows, "pairs_neutral": pairs, "rating_sims": RATING_SIMS})

    # ---------------- venues.json
    ven = R["venues"]
    dump(fmt, "venues.json", {"venues": ven.to_dict(orient="records"), "countries": ven.attrs.get("countries", []),
                              "neutral_reference": ven.attrs.get("neutral", {})})

    # ---------------- ids.json: cricinfo id -> cricsheet id (announced XIs from the fixtures feed)
    want = set(pool) | squad_ids
    ids = {}
    for c in ("key_cricinfo", "key_cricinfo_2", "key_cricinfo_3"):
        sub = people[people["identifier"].isin(want) & people[c].notna()]
        ids.update(dict(zip(sub[c].astype(str), sub["identifier"])))
    dump(fmt, "ids.json", {"cricinfo": ids, "names": {i: names.get(i, i) for i in sorted(want)}})
    print(f"{key}: export players={len(players)} teams={len(rows)} venues={len(ven)} ids={len(ids)}")


if __name__ == "__main__":
    for k in (sys.argv[1:] or ["odi", "test"]):
        main(k)
