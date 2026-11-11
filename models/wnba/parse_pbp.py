# %% Parse ESPN play-by-play: lineups, possessions, shots, per-player-game on-court counts
"""
Outputs (data/processed/wnba/):
  games.parquet          one row per game (teams, scores, date, season, type, OT periods)
  events.parquet         cleaned events with home/away on-court lineups and possession ids
  possessions.parquet    one row per possession with off/def five, points, four-factor counts
  shots.parquet          one row per FGA with zone, coordinates, outcome, shooter/assister/blocker, lineups
  player_games.parquet   per player-game: on-court seconds/possessions/opportunities + pbp counts + box
  recon.json             lineup reconciliation summary
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from models.wnba.common import PROC, RAW, SEASONS

VALID_TEAMS = {3, 5, 6, 8, 9, 11, 14, 16, 17, 18, 19, 20, 129689, 131935, 132052}
NO_PRESENCE = ("Technical", "ejection", "Timeout", "End ", "Challenge", "Review", "Delay", "Double Technical",
               "Too Many", "Flagrant Foul Type 2")


def period_len(p):
    return 600.0 if p <= 4 else 300.0


def period_start(p):
    return 600.0 * (p - 1) if p <= 4 else 2400.0 + 300.0 * (p - 5)


def zone_of(x, y, pts):
    """x,y raw ESPN coords (hoop ~ (25, 0)); returns zone index 0..4."""
    d = np.sqrt((x - 25.0) ** 2 + y ** 2)
    z = np.where(d < 4.0, 0, np.where(d < 14.0, 1, 2))
    z = np.where(pts == 3, np.where(y <= 9.0, 3, 4), z)
    return z, d


# %% load one season
def load_season(y):
    p = pd.read_parquet(RAW / f"play_by_play_{y}.parquet")
    b = pd.read_parquet(RAW / f"player_box_{y}.parquet")
    p = p[p.home_team_id.isin(VALID_TEAMS) & p.away_team_id.isin(VALID_TEAMS) & p.season_type.isin([2, 3])]
    b = b[b.team_id.isin(VALID_TEAMS) & b.game_id.isin(p.game_id.unique())]
    # older files: clear-path FTs typed 'Free_Throw_Clear_Path_1_of_2'; made FTs carry score_value 0 (2017-2021)
    tt = p.type_text.fillna("")
    odd = tt.str.startswith("Free_Throw")
    p.loc[odd, "type_text"] = "Free Throw - " + tt[odd].str.replace("Free_Throw_", "").str.replace("_", " ")
    is_ft = p.type_text.fillna("").str.startswith("Free Throw")
    p.loc[is_ft & p.scoring_play, "score_value"] = 1
    if "points_attempted" not in p:  # pre-2024 files: derive (99.9% agreement on 2026 where both exist)
        txt = p.text.fillna("")
        d = np.sqrt((p.coordinate_x_raw - 25) ** 2 + p.coordinate_y_raw ** 2)
        three = txt.str.contains("three point|3-pt|three pointer", case=False) | (p.scoring_play & (p.score_value == 3))
        three |= (d > 22.6) & (d < 60) & txt.str.contains("jump|shot", case=False)
        fga = p.shooting_play & ~p.type_text.fillna("").str.startswith("Free Throw")
        p["points_attempted"] = np.where(fga, np.where(three, 3, 2), np.where(p.shooting_play, 1, 0))
    return p, b


def is_last_ft(tt):
    m = tt.str.extract(r"(\d) of (\d)")
    return (m[0] == m[1]) & m[0].notna()


def classify(p):
    tt = p.type_text.fillna("")
    is_ft = tt.str.startswith("Free Throw")
    is_tech_ft = is_ft & tt.str.contains("Technical")
    is_fga = p.shooting_play & ~is_ft
    is_to = tt.str.contains("Turnover") & ~tt.str.contains("No Turnover")
    is_orb = tt == "Offensive Rebound"
    is_drb = tt == "Defensive Rebound"
    is_sub = tt == "Substitution"
    ft_last = is_ft & is_last_ft(tt)
    is_foul = tt.str.contains("Foul") & ~is_to
    return dict(is_ft=is_ft.values, is_tech_ft=is_tech_ft.values, is_fga=is_fga.values, is_to=is_to.values,
                is_orb=is_orb.values, is_drb=is_drb.values, is_sub=is_sub.values, ft_last=ft_last.values,
                is_foul=is_foul.values)


# %% per-game lineup reconstruction
def reconstruct_game(g, box_g, stats):
    """g: events of one game sorted. Returns arrays (n,5) home lineup ids, (n,5) away lineup ids."""
    home, away = int(g.home_team_id.iloc[0]), int(g.away_team_id.iloc[0])
    team_of = dict(zip(box_g.athlete_id.astype(int), box_g.team_id.astype(int)))
    mins = dict(zip(box_g.athlete_id.astype(int), box_g.minutes.fillna(0)))
    starters = {t: [int(a) for a in box_g[(box_g.team_id == t) & (box_g.starter == True)].athlete_id] for t in (home, away)}  # noqa: E712
    n = len(g)
    tt = g.type_text.fillna("").values
    a1 = g.athlete_id_1.fillna(-1).astype(np.int64).values
    a2 = g.athlete_id_2.fillna(-1).astype(np.int64).values
    a3 = g.athlete_id_3.fillna(-1).astype(np.int64).values
    per = g.period_number.values
    is_sub = tt == "Substitution"
    presence_ok = np.array([not any(k in t for k in NO_PRESENCE) for t in tt])
    # actors per event (ids that must be on court), keyed by team
    actors = []
    for i in range(n):
        acts = []
        if is_sub[i]:
            actors.append(acts)
            continue
        if presence_ok[i]:
            for a in (a1[i], a2[i], a3[i]):
                if a > 0 and a in team_of:
                    acts.append(a)
        actors.append(acts)
    out_h = np.full((n, 5), -1, dtype=np.int64)
    out_a = np.full((n, 5), -1, dtype=np.int64)
    prev_end = {home: [], away: []}
    for P in np.unique(per):
        idx = np.where(per == P)[0]
        # first appearance + type per player in this period
        first = {}
        appear = {}  # player -> list of (event index, kind) kind: 'in','out','act'
        for i in idx:
            if is_sub[i]:
                for a, kind in ((a1[i], "in"), (a2[i], "out")):
                    if a > 0:
                        appear.setdefault(a, []).append((i, kind))
                        first.setdefault(a, kind)
            else:
                for a in actors[i]:
                    appear.setdefault(a, []).append((i, "act"))
                    first.setdefault(a, "act")
        on = {}
        for t in (home, away):
            if P == 1 and len(starters[t]) == 5:
                s = list(starters[t])
            else:
                cand = [a for a, k in first.items() if team_of.get(a) == t and k != "in"]
                cand.sort(key=lambda a: appear[a][0][0])
                s = cand[:5]
                if len(s) < 5:
                    for a in prev_end[t] + sorted([a for a, tm in team_of.items() if tm == t], key=lambda a: -mins.get(a, 0)):
                        if len(s) >= 5:
                            break
                        if a not in s and first.get(a) != "in" and team_of.get(a) == t:
                            s.append(a)
                    stats["period_fill"] += 1
            on[t] = s
        stats["periods"] += 1

        def next_seen(a, i):
            for j, kind in appear.get(a, []):
                if j > i:
                    return (j, kind)
            return (10 ** 9, "none")

        def evict(t, i, keep=()):
            # remove the on-court player least likely to be on court: next appearance is a sub-in, else latest/never
            best, bkey = None, None
            for a in on[t]:
                if a in keep:
                    continue
                j, kind = next_seen(a, i)
                key = (1 if kind == "in" else 0, j)
                if bkey is None or key > bkey:
                    best, bkey = a, key
            if best is not None:
                on[t].remove(best)

        for i in idx:
            if is_sub[i]:
                pin, pout = a1[i], a2[i]
                t = team_of.get(pin, team_of.get(pout))
                if t is None:
                    t = int(g.team_id.iloc[i]) if not np.isnan(g.team_id.iloc[i]) else None
                if t in on:
                    if pout in on[t]:
                        on[t].remove(pout)
                    elif len(on[t]) >= 5:
                        stats["sub_out_missing"] += 1
                        evict(t, i, keep=(pin,))
                    if pin > 0 and pin not in on[t]:
                        on[t].append(pin)
                    while len(on[t]) > 5:
                        evict(t, i, keep=(pin,))
            else:
                for a in actors[i]:
                    t = team_of[a]
                    if a not in on[t]:
                        stats["phantom_fix"] += 1
                        if len(on[t]) >= 5:
                            evict(t, i, keep=tuple(x for x in actors[i]))
                        on[t].append(a)
            for t, arr in ((home, out_h), (away, out_a)):
                s = on[t][:5]
                arr[i, : len(s)] = s
        prev_end = {t: list(on[t]) for t in on}
    return out_h, out_a


# %% possessions from a cleaned game frame
def build(y, stats):
    p, b = load_season(y)
    p = p.sort_values(["game_id", "game_play_number"]).reset_index(drop=True)
    cl = classify(p)
    for k, v in cl.items():
        p[k] = v
    # dead-ball rebounds after non-final FT
    p["prev_type"] = p.groupby("game_id").type_text.shift(1).fillna("")
    prev_nonfinal_ft = p.prev_type.str.startswith("Free Throw") & ~(is_last_ft(p.prev_type) | p.prev_type.str.contains("Technical"))
    p["deadball_reb"] = (p.is_orb | p.is_drb) & prev_nonfinal_ft
    rem = p.clock_minutes * 60 + p.clock_seconds
    p["t"] = [period_start(q) for q in p.period_number] + (np.array([period_len(q) for q in p.period_number]) - rem.values)
    p["t"] = p["t"].clip(lower=0)
    H = np.full((len(p), 5), -1, dtype=np.int64)
    A = np.full((len(p), 5), -1, dtype=np.int64)
    gstart = p.groupby("game_id").indices
    for gid, ix in gstart.items():
        g = p.iloc[ix]
        bg = b[b.game_id == gid]
        if bg.empty:
            stats["no_box"] += 1
            continue
        h, a = reconstruct_game(g, bg, stats)
        H[ix] = h
        A[ix] = a
    for k in range(5):
        p[f"h{k}"] = H[:, k]
        p[f"a{k}"] = A[:, k]
    return p, b


def possessions(p):
    """Assign possession ids. Relevant events: FGA, non-tech FT, TO, live-ball rebounds (with team)."""
    rel = (p.is_fga | (p.is_ft & ~p.is_tech_ft) | p.is_to | ((p.is_orb | p.is_drb) & ~p.deadball_reb)) & p.team_id.notna()
    p["rel"] = rel
    r = p[rel].copy()
    r["off_team"] = r.team_id.astype(int)
    newp = (r.off_team != r.groupby("game_id").off_team.shift(1)) | (r.period_number != r.groupby("game_id").period_number.shift(1))
    r["poss_seq"] = newp.groupby(r.game_id).cumsum()
    p["poss_seq"] = np.nan
    p.loc[r.index, "poss_seq"] = r.poss_seq
    p["off_team"] = np.nan
    p.loc[r.index, "off_team"] = r.off_team
    # forward-fill within game so fouls/subs between events belong to the next possession is wrong;
    # we only need the relevant events for counting; non-relevant events keep NaN.
    return p, r


def summarise_possessions(p, r):
    r = r.copy()
    r["pts"] = np.where(r.scoring_play & (r.team_id == r.off_team), r.score_value, 0)
    r["fga"] = r.is_fga.astype(int)
    r["fgm"] = (r.is_fga & r.scoring_play).astype(int)
    r["fg3a"] = (r.is_fga & (r.points_attempted == 3)).astype(int)
    r["fg3m"] = (r.is_fga & r.scoring_play & (r.points_attempted == 3)).astype(int)
    r["fta"] = (r.is_ft & ~r.is_tech_ft).astype(int)
    r["ftm"] = (r.is_ft & ~r.is_tech_ft & r.scoring_play).astype(int)
    r["tov"] = r.is_to.astype(int)
    r["orb"] = r.is_orb.astype(int)
    r["ft_trip"] = (r.is_ft & ~r.is_tech_ft & r.type_text.str.contains("1 of")).astype(int)
    agg = r.groupby(["game_id", "poss_seq"]).agg(
        off_team=("off_team", "first"), period=("period_number", "first"), t_first=("t", "first"), t_end=("t", "last"),
        pts=("pts", "sum"), fga=("fga", "sum"), fgm=("fgm", "sum"), fg3a=("fg3a", "sum"), fg3m=("fg3m", "sum"),
        fta=("fta", "sum"), ftm=("ftm", "sum"), tov=("tov", "sum"), orb=("orb", "sum"), ft_trips=("ft_trip", "sum"),
        first_idx=("game_play_number", "idxmin"), home_team=("home_team_id", "first"), away_team=("away_team_id", "first"),
        hs=("home_score", "first"), as_=("away_score", "first"), season=("season", "first"), season_type=("season_type", "first"),
        date=("game_date", "first"),
    ).reset_index()
    # lineups at first relevant event of the possession
    lu = p.loc[agg.first_idx, [f"h{k}" for k in range(5)] + [f"a{k}" for k in range(5)]].values
    home_off = (agg.off_team == agg.home_team).values
    off5 = np.where(home_off[:, None], lu[:, :5], lu[:, 5:])
    def5 = np.where(home_off[:, None], lu[:, 5:], lu[:, :5])
    for k in range(5):
        agg[f"o{k}"] = off5[:, k]
        agg[f"d{k}"] = def5[:, k]
    agg["home_off"] = home_off
    agg["start_drb"] = p.loc[agg.first_idx, "is_drb"].values.astype(int)
    agg["start_tov_steal"] = 0
    agg["def_team"] = np.where(home_off, agg.away_team, agg.home_team)
    # start time = end of previous possession in the game (or period start)
    agg = agg.sort_values(["game_id", "poss_seq"]).reset_index(drop=True)
    prev_end = agg.groupby("game_id").t_end.shift(1)
    same_per = agg.period == agg.groupby("game_id").period.shift(1)
    pstart = np.array([period_start(q) for q in agg.period])
    agg["t_start"] = np.where(same_per, prev_end, pstart)
    agg["dur"] = (agg.t_end - agg.t_start).clip(lower=0)
    # empty possessions (only a rebound, e.g. heave at buzzer) are dropped
    agg["is_empty"] = (agg.fga + agg.fta + agg.tov) == 0
    # margin from offense perspective at possession start
    agg["margin"] = np.where(home_off, agg.hs - agg.as_, agg.as_ - agg.hs)
    agg["lineup_ok"] = (off5 > 0).all(1) & (def5 > 0).all(1)
    return agg.drop(columns=["first_idx"])


# %% shots
def shot_table(p):
    s = p[p.is_fga].copy()
    s["made"] = s.scoring_play.astype(int)
    s["pts3"] = (s.points_attempted == 3).astype(int)
    z, d = zone_of(s.coordinate_x_raw.values, s.coordinate_y_raw.values, s.points_attempted.values)
    s["zone"] = z
    s["dist"] = d
    s["ang"] = np.degrees(np.arctan2(np.abs(s.coordinate_x_raw - 25.0), np.maximum(s.coordinate_y_raw, 0.01)))
    txt = s.text.fillna("")
    s["assisted"] = (s.made == 1) & txt.str.contains("assists")
    s["assister"] = np.where(s.assisted, s.athlete_id_2, np.nan)
    s["blocked"] = txt.str.contains(" blocks ")
    s["blocker"] = np.where(s.blocked, s.athlete_id_2, np.nan)
    # putback / second-chance: previous relevant event an ORB by same team within 4 seconds
    prev = p.loc[p.rel].groupby("game_id")[["is_orb", "team_id", "t"]].shift(1)
    prev = prev.reindex(s.index)
    s["putback"] = (prev.is_orb.fillna(False).astype(bool) & (prev.team_id == s.team_id) & ((s.t - prev.t) <= 4)).astype(int)
    s["and1"] = 0
    # and-one: next relevant event a FT 1 of 1 by same player at same clock
    nxt = p.loc[p.rel].groupby("game_id")[["type_text", "athlete_id_1", "t"]].shift(-1).reindex(s.index)
    s["and1"] = ((s.made == 1) & (nxt.type_text == "Free Throw - 1 of 1") & (nxt.athlete_id_1 == s.athlete_id_1) & (nxt.t == s.t)).astype(int)
    tt = s.type_text.fillna("")
    s["shot_family"] = np.select(
        [tt.str.contains("Dunk"), tt.str.contains("Alley Oop"), tt.str.contains("Putback|Tip"), tt.str.contains("Layup|Finger Roll"),
         tt.str.contains("Hook"), tt.str.contains("Floating"), tt.str.contains("Step Back"), tt.str.contains("Pullup"),
         tt.str.contains("Fade|Turnaround"), tt.str.contains("Bank")],
        ["dunk", "alleyoop", "tip", "layup", "hook", "floater", "stepback", "pullup", "fade", "bank"], "jumper")
    keep = ["game_id", "season", "season_type", "game_date", "period_number", "t", "clock_minutes", "clock_seconds", "team_id",
            "athlete_id_1", "made", "pts3", "zone", "dist", "ang", "coordinate_x_raw", "coordinate_y_raw", "assisted", "assister",
            "blocked", "blocker", "putback", "and1", "shot_family", "type_text", "home_team_id", "away_team_id", "poss_seq"] + \
           [f"h{k}" for k in range(5)] + [f"a{k}" for k in range(5)]
    s = s[keep].rename(columns={"athlete_id_1": "shooter", "period_number": "period"})
    s["shooter"] = s.shooter.fillna(-1).astype(np.int64)
    return s


# %% per player-game on-court exposure and pbp counts
def player_games(p, poss, shots, b):
    rows = []
    # on-court seconds: sum over event intervals within periods
    p = p.copy()
    p["t_next"] = p.groupby(["game_id", "period_number"]).t.shift(-1)
    pend = np.array([period_start(q) + period_len(q) for q in p.period_number])
    p["t_next"] = p.t_next.fillna(pd.Series(pend, index=p.index))
    p["dt"] = (p.t_next - p.t).clip(lower=0)
    sec = []
    for side in ("h", "a"):
        for k in range(5):
            sec.append(p[["game_id", f"{side}{k}", "dt"]].rename(columns={f"{side}{k}": "pid"}))
    # also from period start to the first event (lineup of first event)
    first = p.groupby(["game_id", "period_number"]).head(1)
    first_dt = first.t - np.array([period_start(q) for q in first.period_number])
    for side in ("h", "a"):
        for k in range(5):
            sec.append(pd.DataFrame({"game_id": first.game_id.values, "pid": first[f"{side}{k}"].values, "dt": first_dt.values}))
    sec = pd.concat(sec).groupby(["game_id", "pid"]).dt.sum().rename("sec_on")

    pv = poss[~poss.is_empty & poss.lineup_ok]
    # offensive / defensive possessions and opportunities while on court
    pv = pv.assign(miss_fg=pv.fga - pv.fgm)
    off_cols = {"off_poss": ("one", "sum"), "team_fgm_on": ("fgm", "sum"), "team_fga_on": ("fga", "sum"), "team_pts_on": ("pts", "sum")}
    pv = pv.assign(one=1)
    o = pd.concat([pv[["game_id", f"o{k}", "one", "fgm", "fga", "pts", "tov", "fta"]].rename(columns={f"o{k}": "pid"}) for k in range(5)])
    o = o.groupby(["game_id", "pid"]).agg(off_poss=("one", "sum"), team_fgm_on=("fgm", "sum"), team_fga_on=("fga", "sum"),
                                         team_pts_on=("pts", "sum"), team_tov_on=("tov", "sum"), team_fta_on=("fta", "sum"))
    d = pd.concat([pv[["game_id", f"d{k}", "one", "fga", "fgm", "pts", "tov", "fg3a"]].rename(columns={f"d{k}": "pid"}) for k in range(5)])
    d = d.groupby(["game_id", "pid"]).agg(def_poss=("one", "sum"), opp_fga_on=("fga", "sum"), opp_fgm_on=("fgm", "sum"),
                                         opp_pts_on=("pts", "sum"), opp_tov_on=("tov", "sum"), opp_fg3a_on=("fg3a", "sum"))
    # rebound opportunities: missed FG or missed final FT followed by a live rebound event
    reb = p[(p.is_orb | p.is_drb) & ~p.deadball_reb & p.team_id.notna()].copy()
    home_reb = reb.team_id == reb.home_team_id
    # offense = team that missed: ORB -> rebounding team, DRB -> other team
    off_home = np.where(reb.is_orb, home_reb, ~home_reb)
    H = reb[[f"h{k}" for k in range(5)]].values
    A = reb[[f"a{k}" for k in range(5)]].values
    offL = np.where(off_home[:, None], H, A)
    defL = np.where(off_home[:, None], A, H)
    ro = pd.DataFrame({"game_id": np.repeat(reb.game_id.values, 5), "pid": offL.ravel(), "orb_opp": 1,
                       "team_orb_on": np.repeat(reb.is_orb.values.astype(int), 5)})
    rd = pd.DataFrame({"game_id": np.repeat(reb.game_id.values, 5), "pid": defL.ravel(), "drb_opp": 1,
                       "team_drb_on": np.repeat(reb.is_drb.values.astype(int), 5)})
    ro = ro.groupby(["game_id", "pid"]).sum()
    rd = rd.groupby(["game_id", "pid"]).sum()

    # individual counts from pbp
    ev = p
    ind = []
    s = shots
    for z in range(5):
        ind.append(s[s.zone == z].groupby(["game_id", "shooter"]).made.agg(["size", "sum"]).rename(
            columns={"size": f"fga_z{z}", "sum": f"fgm_z{z}"}).rename_axis(["game_id", "pid"]))
        ind.append(s[(s.zone == z) & s.assisted].groupby(["game_id", "shooter"]).size().rename(f"astd_z{z}").rename_axis(["game_id", "pid"]))
    ind.append(s.groupby(["game_id", "shooter"]).and1.sum().rename("and1").rename_axis(["game_id", "pid"]))
    ind.append(s.groupby(["game_id", "shooter"]).putback.sum().rename("putback_fga").rename_axis(["game_id", "pid"]))
    ind.append(s[s.assisted].groupby(["game_id", "assister"]).size().rename("ast").rename_axis(["game_id", "pid"]))
    ind.append(s[s.blocked].groupby(["game_id", "blocker"]).size().rename("blk").rename_axis(["game_id", "pid"]))
    ft = ev[ev.is_ft & ~ev.is_tech_ft]
    ind.append(ft.groupby(["game_id", "athlete_id_1"]).scoring_play.agg(["size", "sum"]).rename(
        columns={"size": "fta", "sum": "ftm"}).rename_axis(["game_id", "pid"]))
    trips = ft[ft.type_text.str.contains("1 of")]
    trips = trips.assign(n=trips.type_text.str.extract(r"of (\d)").astype(float)[0])
    ind.append(trips[trips.n == 1].groupby(["game_id", "athlete_id_1"]).size().rename("ft_trips1").rename_axis(["game_id", "pid"]))
    ind.append(trips[trips.n == 2].groupby(["game_id", "athlete_id_1"]).size().rename("ft_trips2").rename_axis(["game_id", "pid"]))
    ind.append(trips[trips.n == 3].groupby(["game_id", "athlete_id_1"]).size().rename("ft_trips3").rename_axis(["game_id", "pid"]))
    tech = ev[ev.is_tech_ft]
    ind.append(tech.groupby(["game_id", "athlete_id_1"]).scoring_play.agg(["size", "sum"]).rename(
        columns={"size": "tfta", "sum": "tftm"}).rename_axis(["game_id", "pid"]))
    to = ev[ev.is_to]
    ind.append(to.groupby(["game_id", "athlete_id_1"]).size().rename("tov").rename_axis(["game_id", "pid"]))
    stl = to[to.text.fillna("").str.contains("steals")]
    ind.append(stl.groupby(["game_id", "athlete_id_2"]).size().rename("stl").rename_axis(["game_id", "pid"]))
    lr = ev[(ev.is_orb | ev.is_drb) & ~ev.deadball_reb]
    ind.append(lr[lr.is_orb].groupby(["game_id", "athlete_id_1"]).size().rename("orb").rename_axis(["game_id", "pid"]))
    ind.append(lr[lr.is_drb].groupby(["game_id", "athlete_id_1"]).size().rename("drb").rename_axis(["game_id", "pid"]))
    fo = ev[ev.is_foul & ~ev.type_text.str.contains("Technical") & ~ev.type_text.str.contains("Offensive Foul")]
    ind.append(fo.groupby(["game_id", "athlete_id_1"]).size().rename("pf_def").rename_axis(["game_id", "pid"]))
    sf = ev[ev.type_text == "Shooting Foul"]
    ind.append(sf.groupby(["game_id", "athlete_id_1"]).size().rename("pf_shoot").rename_axis(["game_id", "pid"]))
    pieces = [sec, o, d, ro, rd] + [x if isinstance(x, pd.DataFrame) else x.to_frame() for x in ind]
    for i, x in enumerate(pieces):
        x = x.reset_index() if not isinstance(x.index, pd.RangeIndex) else x
        x["pid"] = x["pid"].astype(float).astype(np.int64) if "pid" in x else x
        pieces[i] = x.set_index(["game_id", "pid"])
    out = pd.concat(pieces, axis=1).fillna(0)
    out = out[out.index.get_level_values("pid") > 0].reset_index()
    # box columns
    bb = b.rename(columns={"athlete_id": "pid"})
    bb["pid"] = bb.pid.astype(np.int64)
    bcols = ["game_id", "pid", "athlete_display_name", "team_id", "opponent_team_id", "home_away", "minutes", "starter",
             "did_not_play", "points", "field_goals_made", "field_goals_attempted", "three_point_field_goals_made",
             "three_point_field_goals_attempted", "free_throws_made", "free_throws_attempted", "offensive_rebounds",
             "defensive_rebounds", "rebounds", "assists", "steals", "blocks", "turnovers", "fouls", "plus_minus",
             "athlete_position_abbreviation", "game_date", "season", "season_type"]
    out = bb[bcols].merge(out, on=["game_id", "pid"], how="outer")
    return out


# %% games table
def games_table(p, b):
    g = p.groupby("game_id").agg(season=("season", "first"), season_type=("season_type", "first"), date=("game_date", "first"),
                                 dt=("game_date_time", "first"),
                                 home=("home_team_id", "first"), away=("away_team_id", "first"),
                                 home_abbr=("home_team_abbrev", "first"), away_abbr=("away_team_abbrev", "first"),
                                 nper=("period_number", "max")).reset_index()
    tb = b.groupby(["game_id", "team_id"]).points.sum().unstack()
    g["home_pts"] = [tb.loc[r.game_id, r.home] if r.game_id in tb.index else np.nan for r in g.itertuples()]
    g["away_pts"] = [tb.loc[r.game_id, r.away] if r.game_id in tb.index else np.nan for r in g.itertuples()]
    return g


# %% main
def main(force=False):
    out_files = [PROC / f for f in ("possessions.parquet", "shots.parquet", "player_games.parquet", "games.parquet")]
    if all(f.exists() for f in out_files) and not force:
        print("parse_pbp: cached")
        return
    G, P, S, PG = [], [], [], []
    recon = {}
    for y in SEASONS:
        stats = dict(periods=0, period_fill=0, sub_out_missing=0, phantom_fix=0, no_box=0)
        p, b = build(y, stats)
        p, r = possessions(p)
        poss = summarise_possessions(p, r)
        shots = shot_table(p)
        pg = player_games(p, poss, shots, b)
        g = games_table(p, b)
        # schedule metadata: neutral site + scores for games lacking box
        sch = pd.read_parquet(RAW / f"wnba_schedule_{y}.parquet")[["game_id", "neutral_site", "venue_address_city", "notes_headline"]]
        g = g.merge(sch, on="game_id", how="left")
        # reconciliation
        m = pg[(pg.minutes > 0) & pg.sec_on.notna()]
        diff = (m.sec_on / 60 - m.minutes).abs()
        pv = poss[~poss.is_empty]
        recon[y] = dict(stats, games=int(g.shape[0]), possessions=int(len(pv)),
                        poss_lineup_ok=float(pv.lineup_ok.mean()),
                        player_games=int(len(m)), min_within_1=float((diff <= 1.0).mean()), min_within_2=float((diff <= 2.0).mean()),
                        min_mae=float(diff.mean()))
        G.append(g)
        P.append(poss)
        S.append(shots)
        PG.append(pg)
        print(y, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in recon[y].items()})
    pd.concat(G).to_parquet(PROC / "games.parquet")
    pd.concat(P).to_parquet(PROC / "possessions.parquet")
    pd.concat(S).to_parquet(PROC / "shots.parquet")
    pd.concat(PG).to_parquet(PROC / "player_games.parquet")
    (PROC / "recon.json").write_text(json.dumps(recon, indent=1))


if __name__ == "__main__":
    main(force="--force" in sys.argv)
