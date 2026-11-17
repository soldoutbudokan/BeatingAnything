# %% Process backtest: what would we have forecast with what we knew, and how did the market do?
"""
python -m models.wnba.process

A model is not what gets tested against a market: a process is. At decision time T before a game we hold
some information, project a lineup x from it, the lineup and the ratings give a forecast y, and y misses the
result by z. This module replays that chain for every game with a Kalshi game-winner market (May 2025 on)
and keeps each link, so the miss can be split into "we had the wrong lineup" and "the ratings were wrong".

Information tiers (what the lineup projection is allowed to know at T):
  box            box scores of games that had finished by T, nothing else. No injury report, no signings, no
                 rest news. P(active) comes from how many of the team's latest games the player missed,
                 with rates measured on earlier seasons only. This is the only tier that is fully
                 point-in-time for past seasons, because no injury-report archive exists for them.
  news           box + an availability report captured before T (ESPN injuries / transactions). Only exists
                 for games after forward capture started (models.wnba.snapshot); empty for 2025-26.
  oracle_active  told exactly who played; minutes shares still from earlier games. Upper bound on what
                 perfect availability news is worth.
  oracle_minutes told the minutes actually played. Includes in-game information; a ceiling, not a process.

Ratings are the walk-forward prior-informed RAPM (refitted on data before each of ten cut-offs a season).
Decision times: 24 h and 1 h before the ESPN tip. A game counts as known at T if it tipped at least 3 h earlier.

Outputs: data/markets/wnba/process_ledger.csv.gz    one row per game x decision time x tier
         data/markets/wnba/process_lineups.csv.gz   the projected lineup behind each row
         docs/models/wnba/data/market_test.json     summary
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd
from scipy.stats import norm

from models.wnba.common import EXPORT, PROC, ROOT, season_bounds, tau, write_json
from models.wnba.minutes import scale_to_total

OUT = ROOT / "data" / "markets" / "wnba"
DECISIONS_H = {"24h": 24.0, "1h": 1.0}
QUOTE_FOR = {"24h": ["24h"], "1h": ["1h", "10m", "tip"]}  # market quotes each decision time is scored against
GAME_KNOWN_AFTER_H = 3.0
LOOKBACK_GAMES = 5
HL_GAMES = 6.0
MARGIN_SD = 12.5        # residual SD of the walk-forward margin forecast on 2024 and earlier seasons
POSS = 78.0             # possessions per team game used to turn per-100 ratings into points
FEE = 0.07              # Kalshi taker fee per contract: FEE * price * (1 - price)
EDGE = 0.03             # bet when model probability beats the all-in price by this much
UNSEEN = (-1.0, -0.5)   # O, D of a player the ratings have never seen


# %% data
def load():
    games = pd.read_parquet(PROC / "games.parquet").reset_index(drop=True).dropna(subset=["home_pts"])
    games["tip"] = pd.to_datetime(games.dt, utc=True)
    games["tau"] = tau(games.season.values, games.date.values, season_bounds(games))
    pg = pd.read_parquet(PROC / "player_games.parquet")
    pg = pg[(pg.pid > 0) & pg.team_id.notna() & pg.game_id.isin(games.game_id)]
    pg = pg[["game_id", "pid", "team_id", "minutes"]].copy()
    pg["minutes"] = pg.minutes.fillna(0.0)
    pg["team_id"] = pg.team_id.astype(int)
    pg = pg.merge(games[["game_id", "tip", "season"]], on="game_id").sort_values("tip")
    return games, pg[pg.minutes > 0]


def active_rates(pg, games, before_season):
    """P(plays next team game | consecutive team games missed = 0, 1, 2+), from seasons before `before_season`."""
    d = pg[pg.season < before_season]
    g = games[games.season < before_season]
    tg = pd.concat([g[["game_id", "tip", "season"]].assign(team=g.home), g[["game_id", "tip", "season"]].assign(team=g.away)])
    n, k = np.zeros(3), np.zeros(3)
    for (team, season), t in tg.groupby(["team", "season"]):
        t = t.sort_values("tip")
        played = d[(d.team_id == team) & (d.season == season)].groupby("game_id").pid.apply(set).to_dict()
        seq = [played.get(x, set()) for x in t.game_id]
        for i in range(LOOKBACK_GAMES, len(seq)):
            pool = set().union(*seq[i - LOOKBACK_GAMES:i])
            for p in pool:
                miss = 0
                for j in range(i - 1, i - LOOKBACK_GAMES - 1, -1):
                    if p in seq[j]:
                        break
                    miss += 1
                b = min(miss, 2)
                n[b] += 1
                k[b] += p in seq[i]
    return (k + 1) / (n + 2)


# %% lineup projection
class Lineups:
    def __init__(self, games, pg):
        self.games, self.pg = games, pg
        self.by_team = {t: d for t, d in pg.groupby("team_id")}
        self.by_pid_last = pg.groupby("pid").tail(1).set_index("pid")
        self.team_games = {}
        for side in ("home", "away"):
            for t, d in games.groupby(side):
                self.team_games.setdefault(int(t), []).append(d[["game_id", "tip", "season"]])
        self.team_games = {t: pd.concat(v).sort_values("tip") for t, v in self.team_games.items()}
        self.prev_mpg = pg.groupby(["pid", "season"]).minutes.mean()
        self.rates = {}

    def role_minutes(self, team, season, T, pids):
        """Decayed mean minutes in games played for this team this season, one pseudo-game of last season's mpg."""
        d = self.by_team[team]
        d = d[(d.tip < T) & d.pid.isin(pids)]
        out = {}
        for p in pids:
            m = d[(d.pid == p) & (d.season == season)].minutes.values
            fb = self.prev_mpg.get((p, season - 1), 8.0)
            w = 0.5 ** ((len(m) - 1 - np.arange(len(m))) / HL_GAMES)
            out[p] = (float((w * m).sum()) + fb) / (float(w.sum()) + 1.0)
        return out

    def project(self, team, game, T, tier, news=None):
        """Projected minutes {pid: min} for `team` in `game`, knowing only what was known at T.
        news: optional {pid: P(active)} from an availability report captured before T (tier 'news')."""
        season = int(game.season)
        actual = self.pg[(self.pg.game_id == game.game_id) & (self.pg.team_id == team)]
        if tier == "oracle_minutes":
            m = dict(zip(actual.pid, actual.minutes))
            return _scaled(m), dict(cold=False)
        known = T - pd.Timedelta(hours=GAME_KNOWN_AFTER_H)
        tg = self.team_games[team]
        past = tg[(tg.tip < known) & (tg.season == season)]
        cold = len(past) == 0
        if tier == "oracle_active":
            pids = list(actual.pid)
            return _scaled(self.role_minutes(team, season, known, pids)), dict(cold=cold)
        if cold:  # first game of the season: last season's closing roster, if the team has one
            past = tg[(tg.tip < known)].tail(LOOKBACK_GAMES)
            if past.empty:
                return None, dict(cold=True)
        last = past.tail(LOOKBACK_GAMES)
        d = self.by_team[team]
        d = d[d.game_id.isin(last.game_id)]
        seq = [set(d[d.game_id == x].pid) for x in last.game_id]
        # drop players whose latest known game anywhere was for another team (traded / signed elsewhere)
        latest = self.pg[(self.pg.tip < known) & self.pg.pid.isin(d.pid.unique())].groupby("pid").tail(1)
        here = set(latest[latest.team_id == team].pid)
        if season not in self.rates:
            self.rates[season] = active_rates(self.pg, self.games, season)
        rate = self.rates[season]
        pact = {}
        for p in here:
            miss = 0
            for s in reversed(seq):
                if p in s:
                    break
                miss += 1
            pact[p] = float(rate[min(miss, 2)]) if not cold else float(rate[0])
        if news:
            pact.update({p: v for p, v in news.items() if p in pact})
            for p, v in news.items():  # a reported arrival we have never seen play here
                pact.setdefault(p, v)
        role = self.role_minutes(team, int(last.season.iloc[-1]) if cold else season, known, list(pact))
        return _scaled({p: role[p] * pact[p] for p in pact}), dict(cold=cold)


def _scaled(m):
    if not m:
        return None
    ids = list(m)
    v = scale_to_total(np.array([m[i] for i in ids], float))
    return dict(zip(ids, v))


# %% ratings at each cut-off (walk-forward)
def ratings_by_cut(seasons, step=0.1):
    from models.wnba import rapm
    rm = json.loads((PROC / "rapm_meta.json").read_text())
    c = rapm.prepare()
    poss, pidx, P = c["poss"], c["pidx"], c["P"]
    oc, dc = [f"o{k}" for k in range(5)], [f"d{k}" for k in range(5)]
    out = []
    for S in seasons:
        for tc in np.arange(S * 1.25, S * 1.25 + 1.0, step):
            b, _ = rapm.rating_at(c, tc, rm["H"], rm["H_feat"], rm["lam_prior"], rm.get("spm_alpha", 0.3))
            q = poss[(poss.tau < tc) & (poss.tau >= tc - 1.25)]
            wo = pd.Series(q[oc].values.ravel()).value_counts()
            wd = pd.Series(q[dc].values.ravel()).value_counts()
            O, D = pd.Series(b[:P], index=pidx), pd.Series(b[P:2 * P], index=pidx)
            seen = pd.Index(np.unique(q[oc + dc].values))
            O = (O - np.average(O.reindex(wo.index).fillna(0), weights=wo.values)).reindex(seen)
            D = (D - np.average(D.reindex(wd.index).fillna(0), weights=wd.values)).reindex(seen)
            out.append((tc, (O + D).to_dict()))
    return out


def net_rating(lineup, total):
    """Team net per 100 from projected minutes and player totals (O + D)."""
    return sum(m / 40.0 * total.get(p, UNSEEN[0] + UNSEEN[1]) for p, m in lineup.items())


# %% the ledger
def build(seasons=(2025, 2026), news_fn=None):
    games, pg = load()
    L = Lineups(games, pg)
    cuts = ratings_by_cut(seasons)
    hca = json.loads((PROC / "sim_params.json").read_text())["context"]["hca_pts"]
    mk = pd.read_csv(OUT / "kalshi_markets.csv.gz")
    qt = pd.read_csv(OUT / "kalshi_quotes.csv.gz")
    ml = mk[(mk.kind == "ml") & (mk.yes_is_home == True)].merge(qt, on="ticker")  # noqa: E712
    quotes = {(r.game_id, r.horizon): r for r in ml.itertuples()}
    rows, lrows = [], []
    for g in games[games.season.isin(seasons) & games.game_id.isin(ml.game_id)].itertuples():
        total = [t for tc, t in cuts if tc <= g.tau][-1]
        actual = {t: dict(zip(d.pid, d.minutes)) for t, d in pg[pg.game_id == g.game_id].groupby("team_id")}
        neutral = bool(g.neutral_site) if pd.notna(g.neutral_site) else False
        for dec, hrs in DECISIONS_H.items():
            T = g.tip - pd.Timedelta(hours=hrs)
            for tier in ("box", "news", "oracle_active", "oracle_minutes"):
                news = {t: (news_fn(g, t, T) if news_fn else None) for t in (g.home, g.away)}
                if tier == "news" and not any(news.values()):
                    continue
                lu, cold = {}, False
                for t in (g.home, g.away):
                    x, info = L.project(int(t), g, T, "box" if tier == "news" else tier, news[t] if tier == "news" else None)
                    lu[t] = x
                    cold |= info["cold"]
                if lu[g.home] is None or lu[g.away] is None:
                    continue
                mu = (net_rating(lu[g.home], total) - net_rating(lu[g.away], total)) * POSS / 100 + (0.0 if neutral else hca)
                # minutes handed to the wrong players, per team (0 = lineup exactly right, 200 = entirely wrong)
                mis = {t: 0.5 * sum(abs(lu[t].get(p, 0) - _scaled(actual[t]).get(p, 0)) for p in set(lu[t]) | set(actual[t])) for t in (g.home, g.away)}
                rec = dict(game_id=g.game_id, season=g.season, tip=g.tip, decision=dec, tier=tier, cold_start=cold,
                           pred_margin=mu, p_home=float(norm.cdf(mu / MARGIN_SD)), margin=g.home_pts - g.away_pts,
                           home_win=int(g.home_pts > g.away_pts), min_wrong_home=mis[g.home], min_wrong_away=mis[g.away])
                for h in QUOTE_FOR[dec]:
                    q = quotes.get((g.game_id, h))
                    for k in ("bid", "ask", "last", "age_min", "cum_vol"):
                        rec[f"{h}_{k}"] = getattr(q, k) if q is not None else np.nan
                rows.append(rec)
                for t in (g.home, g.away):
                    a = _scaled(actual[t])
                    for p in set(lu[t]) | set(a):
                        lrows.append((g.game_id, int(t), dec, tier, int(p), round(lu[t].get(p, 0.0), 2), round(a.get(p, 0.0), 2)))
    led = pd.DataFrame(rows)
    lin = pd.DataFrame(lrows, columns=["game_id", "team", "decision", "tier", "pid", "proj_min", "actual_min"])
    return led, lin


# %% grading
def mid(d, h):
    b, a = d[f"{h}_bid"], d[f"{h}_ask"]
    m = (b + a) / 2
    return m.where(b.notna() & a.notna() & (a - b <= 0.10), d[f"{h}_last"])


def logloss(p, y):
    p = np.clip(p, 0.01, 0.99)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def boot(x, n=2000, seed=5):
    x = np.asarray(x, float)
    if len(x) < 5:
        return [None, None]
    r = np.random.default_rng(seed)
    m = x[r.integers(0, len(x), (n, len(x)))].mean(1)
    return [float(np.quantile(m, 0.025)), float(np.quantile(m, 0.975))]


def bets(d, h):
    """Flat one-contract bets at the quoted ask (YES home) or 1 - bid (NO home) when the model beats the
    all-in price by EDGE. Returns per-bet profit and cost."""
    p, b, a, y = d.p_home.values, d[f"{h}_bid"].values, d[f"{h}_ask"].values, d.home_win.values
    out = []
    for i in range(len(d)):
        if np.isfinite(a[i]) and p[i] - a[i] - FEE * a[i] * (1 - a[i]) > EDGE:
            cost = a[i] + FEE * a[i] * (1 - a[i])
            out.append((y[i] - cost, cost))
        elif np.isfinite(b[i]) and (1 - p[i]) - (1 - b[i]) - FEE * b[i] * (1 - b[i]) > EDGE:
            cost = (1 - b[i]) + FEE * b[i] * (1 - b[i])
            out.append(((1 - y[i]) - cost, cost))
    return np.array(out).reshape(-1, 2)


def grade(led):
    S = dict(n_games=int(led.game_id.nunique()), seasons=sorted(int(s) for s in led.season.unique()),
             settings=dict(margin_sd=MARGIN_SD, poss=POSS, fee=FEE, edge=EDGE, game_known_after_h=GAME_KNOWN_AFTER_H))
    table = []
    for dec in DECISIONS_H:
        for h in QUOTE_FOR[dec]:
            base = led[(led.decision == dec) & (led.tier == "box")].set_index("game_id")
            m = mid(base, h)
            ok = m.notna() & (m > 0) & (m < 1)
            for tier in ("box", "news", "oracle_active", "oracle_minutes"):
                d = led[(led.decision == dec) & (led.tier == tier)].set_index("game_id")
                d = d[d.index.isin(ok[ok].index)]
                if len(d) < 20:
                    continue
                mm, y = m.reindex(d.index).values, d.home_win.values
                lm, lk = logloss(d.p_home.values, y), logloss(mm, y)
                bt = bets(d, h)
                rec = dict(decision=dec, quote=h, tier=tier, n=int(len(d)),
                           logloss_model=float(lm.mean()), logloss_market=float(lk.mean()), logloss_diff=float((lm - lk).mean()),
                           logloss_diff_ci=boot(lm - lk), brier_model=float(((d.p_home - y) ** 2).mean()),
                           brier_market=float(((mm - y) ** 2).mean()), margin_rmse=float(np.sqrt(((d.margin - d.pred_margin) ** 2).mean())),
                           corr_model_market=float(np.corrcoef(d.p_home, mm)[0, 1]),
                           spread_cents=float(100 * (d[f"{h}_ask"] - d[f"{h}_bid"]).median()), quote_age_min=float(d[f"{h}_age_min"].median()),
                           n_bets=int(len(bt)))
                if len(bt):
                    rec.update(profit_per_bet=float(bt[:, 0].mean()), roi=float(bt[:, 0].sum() / bt[:, 1].sum()), profit_ci=boot(bt[:, 0]))
                table.append(rec)
    S["vs_market"] = table
    # by season: Kalshi's 2025 books were thin (median 0.1m contracts a game against 1.3m in 2026)
    bs = []
    for season, ls in led.groupby("season"):
        for dec, h in (("24h", "24h"), ("1h", "tip")):
            base = ls[(ls.decision == dec) & (ls.tier == "box")].set_index("game_id")
            m = mid(base, h)
            ok = m.notna() & (m > 0) & (m < 1)
            for tier in ("box", "oracle_active"):
                d = ls[(ls.decision == dec) & (ls.tier == tier)].set_index("game_id")
                d = d[d.index.isin(ok[ok].index)]
                if len(d) < 20:
                    continue
                mm, y = m.reindex(d.index).values, d.home_win.values
                lm, lk = logloss(d.p_home.values, y), logloss(mm, y)
                bt = bets(d, h)
                bs.append(dict(season=int(season), decision=dec, quote=h, tier=tier, n=int(len(d)), logloss_model=float(lm.mean()),
                               logloss_market=float(lk.mean()), logloss_diff=float((lm - lk).mean()), logloss_diff_ci=boot(lm - lk),
                               n_bets=int(len(bt)), roi=float(bt[:, 0].sum() / bt[:, 1].sum()) if len(bt) else None,
                               profit_ci=boot(bt[:, 0]) if len(bt) else None))
    S["vs_market_by_season"] = bs
    # where the miss comes from: lineup information vs ratings
    w = led[led.decision == "1h"].pivot(index="game_id", columns="tier", values="pred_margin")
    y = led[led.decision == "1h"].drop_duplicates("game_id").set_index("game_id").margin
    w = w.dropna(subset=["box", "oracle_active", "oracle_minutes"])
    y = y.reindex(w.index)
    mse = {t: float(((y - w[t]) ** 2).mean()) for t in ("box", "oracle_active", "oracle_minutes")}
    b = led[(led.decision == "1h") & (led.tier == "box")].set_index("game_id").reindex(w.index)
    wrong = b.min_wrong_home + b.min_wrong_away
    S["decomposition_1h"] = dict(
        n=int(len(w)), mse=mse, rmse={k: float(np.sqrt(v)) for k, v in mse.items()},
        mse_from_not_knowing_who_plays=mse["box"] - mse["oracle_active"],
        mse_from_minutes_given_who_plays=mse["oracle_active"] - mse["oracle_minutes"],
        mse_left_with_perfect_lineup=mse["oracle_minutes"],
        lineup_shift_sd_pts=float((w.oracle_active - w.box).std()),
        minutes_wrong_per_game_median=float(wrong.median()), minutes_wrong_per_game_p90=float(wrong.quantile(0.9)),
        note="1 h before tip. box = box scores only; oracle_active = told who played; oracle_minutes = told the minutes.")
    # does the market's last-day move line up with the lineup news we lacked?
    a = led[(led.decision == "24h") & (led.tier == "box")].set_index("game_id")
    z = led[(led.decision == "1h") & (led.tier == "box")].set_index("game_id")
    mv = (mid(z, "tip") - mid(a, "24h")).reindex(w.index)
    ls = pd.Series(norm.cdf(w.oracle_active / MARGIN_SD) - norm.cdf(w.box / MARGIN_SD), index=w.index)
    ok = mv.notna() & ls.notna()
    S["market_move_vs_lineup_news"] = dict(
        n=int(ok.sum()), market_move_sd=float(mv[ok].std()), our_lineup_gap_sd=float(ls[ok].std()),
        corr=float(np.corrcoef(mv[ok], ls[ok])[0, 1]),
        note="market move = home win price at tip minus 24 h before; lineup gap = our win probability if told who played minus our box-only one")
    # the worst lineup misses, to read
    S["by_minutes_wrong"] = []
    bb = b.assign(wrong=wrong, err=(y - w.box).abs(), err_o=(y - w.oracle_active).abs())
    for lo, hi in ((0, 20), (20, 40), (40, 70), (70, 400)):
        x = bb[(bb.wrong >= lo) & (bb.wrong < hi)]
        if len(x):
            S["by_minutes_wrong"].append(dict(minutes_wrong=f"{lo}-{hi}", n=int(len(x)), abs_err_box=float(x.err.mean()), abs_err_told_who_played=float(x.err_o.mean())))
    return S


def main(regrade=False):
    if regrade:  # re-score the saved ledger without rebuilding it
        S = grade(pd.read_csv(OUT / "process_ledger.csv.gz"))
        write_json(EXPORT / "market_test.json", S, digits=4)
        return S
    led, lin = build()
    OUT.mkdir(parents=True, exist_ok=True)
    led.assign(tip=led.tip.astype(str)).round(4).to_csv(OUT / "process_ledger.csv.gz", index=False)
    lin.to_csv(OUT / "process_lineups.csv.gz", index=False)
    S = grade(led)
    write_json(EXPORT / "market_test.json", S, digits=4)
    for r in S["vs_market"]:
        print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items() if k not in ("brier_model", "brier_market")})
    print(json.dumps(S["decomposition_1h"], default=float)[:900])
    print(S["market_move_vs_lineup_news"], S["by_minutes_wrong"])


if __name__ == "__main__":
    main(regrade="--regrade" in sys.argv)
