# %% Player bios + end-of-2026 rosters
"""
Roster rule: a player's team is the last team she appeared for (box score, minutes > 0 or listed) in the
2026 season (regular season + playoffs). ESPN's current (off-season) roster endpoint supplies age, birth
date, height and position, and a flag for whether the player is on that team's ESPN roster today.
Players on an ESPN roster with no 2026 appearance are added to that team (no default minutes).
Players who played in 2025 but not in 2026 and are on no ESPN roster are kept as free agents (team None)
so the site can add them to lineups.
Output: data/processed/wnba/players_bio.parquet, teams.parquet
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from models.wnba.common import CURRENT_SEASON, CUTOFF_DATE, PROC, RAW

CUR = CURRENT_SEASON


def espn_rosters():
    rows = []
    for f in sorted(RAW.glob("espn_roster_*.json")):
        d = json.loads(f.read_text())
        tid = int(d["team"]["id"])
        for a in d.get("athletes", []):
            rows.append(dict(pid=int(a["id"]), espn_name=a.get("displayName"), espn_team=tid, height_in=a.get("height"),
                             weight_lb=a.get("weight"), age_espn=a.get("age"), dob=a.get("dateOfBirth"),
                             espn_pos=(a.get("position") or {}).get("abbreviation"),
                             experience=(a.get("experience") or {}).get("years"),
                             status=(a.get("status") or {}).get("type"), jersey=a.get("jersey")))
    return pd.DataFrame(rows)


def main(force=False):
    out = PROC / "players_bio.parquet"
    if out.exists() and not force:
        print("rosters: cached")
        return
    pg = pd.read_parquet(PROC / "player_games.parquet")
    pg = pg[pg.pid > 0 & pg.team_id.notna()]
    games = pd.read_parquet(PROC / "games.parquet")
    pg = pg.merge(games[["game_id", "dt"]], on="game_id", how="left")
    played = pg[(pg.minutes.fillna(0) > 0)]
    last = played.sort_values("dt").groupby("pid").tail(1).set_index("pid")
    bio = pd.DataFrame(index=last.index)
    bio["name"] = last.athlete_display_name
    bio["last_season"] = last.season.astype(int)
    bio["last_team"] = last.team_id.astype(int)
    bio["box_pos"] = played.groupby("pid").athlete_position_abbreviation.agg(lambda s: s.dropna().iloc[-1] if s.notna().any() else None)
    bio["first_season"] = played.groupby("pid").season.min().astype(int)
    bio["career_games"] = played.groupby("pid").size()
    e = espn_rosters().set_index("pid")
    bio = bio.join(e, how="outer")
    bio["name"] = bio.name.fillna(bio.espn_name)
    bio["pos"] = bio.espn_pos.fillna(bio.box_pos).fillna("F")
    bio["pos_group"] = bio.pos.str[0].map({"G": "G", "F": "F", "C": "C"}).fillna("F")
    # team assignment
    cur_team = np.where(bio.last_season == CUR, bio.last_team, np.nan)
    bio["team"] = pd.Series(cur_team, index=bio.index)
    bio.loc[bio.team.isna() & bio.espn_team.notna(), "team"] = bio.espn_team
    bio["roster_source"] = np.where(bio.last_season == CUR, "last_2026_team",
                                    np.where(bio.espn_team.notna(), "espn_current_roster", "free_agent"))
    bio["on_espn_roster"] = bio.espn_team.notna()
    bio["espn_team_differs"] = bio.espn_team.notna() & (bio.last_season == CUR) & (bio.espn_team != bio.last_team)
    # age at cut-off
    dob = pd.to_datetime(bio.dob, utc=True, errors="coerce").dt.tz_localize(None)
    bio["dob"] = dob
    bio["age"] = ((pd.Timestamp(CUTOFF_DATE) - dob).dt.days / 365.25).round(2)
    # impute missing age from first WNBA season in the data (rookie ~22.8); 2017 starters are left-censored
    bio["age_imputed"] = bio.age.isna()
    fs = bio.first_season.fillna(CUR + 1)
    bio.loc[bio.age_imputed, "age"] = np.where(fs[bio.age_imputed] <= 2017, 31.0, 22.8 + (CUR + 0.9 - fs[bio.age_imputed]))
    bio["height_imputed"] = bio.height_in.isna()
    pos_h = {"G": 70.5, "F": 74.5, "C": 77.2}
    bio.loc[bio.height_imputed, "height_in"] = bio.loc[bio.height_imputed, "pos"].str[0].map(pos_h).fillna(74.5)
    # keep: 2026 players, ESPN-rostered, and 2025 players (recent free agents)
    keep = (bio.last_season >= CUR - 1) | bio.on_espn_roster
    bio = bio[keep].copy()
    bio.loc[bio.roster_source == "free_agent", "team"] = np.nan
    bio.index.name = "pid"
    bio = bio.reset_index()
    bio["team"] = bio.team.astype("Int64")
    bio.to_parquet(out)
    # teams table (current-season teams in the data)
    g = games[(games.season == CUR)]
    t = pd.concat([g[["home", "home_abbr"]].set_axis(["team_id", "abbr"], axis=1), g[["away", "away_abbr"]].set_axis(["team_id", "abbr"], axis=1)])
    t = t.drop_duplicates("team_id")
    tb = pd.read_parquet(RAW / f"team_box_{CUR}.parquet")[["team_id", "team_display_name", "team_color", "team_alternate_color", "team_logo"]].drop_duplicates("team_id")
    t = t.merge(tb, on="team_id", how="left")
    espn_ids = {int(x["team"]["id"]) for x in json.loads((RAW / "espn_teams.json").read_text())["sports"][0]["leagues"][0]["teams"]}
    t["in_espn_team_list"] = t.team_id.isin(espn_ids)
    t.to_parquet(PROC / "teams.parquet")
    print(f"rosters: {len(bio)} players ({(bio.roster_source != 'free_agent').sum()} rostered), {len(t)} teams; "
          f"age known {bio.age.notna().mean():.0%}")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
