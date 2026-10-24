"""Team-level match baselines for judging the ball-by-ball simulator.

Elo per (format family, gender) over the matches table, updated in date order, so the
rating used for a match only reflects earlier results. A home term applies when the
venue's country is the team's country (internationals) or when the team played at
least 30% of its previous matches at the venue (franchise and domestic sides). Ties
score half; no-results and abandoned matches do not update ratings. Tests use a
three-way law: the draw probability is the pre-match draw rate of the venue's region
over the previous six years, and the remaining mass is split by the Elo expectation.
These are deliberately simple, transparent comparators, not competitors.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
import math

import numpy as np
import pandas as pd


@dataclass
class EloConfig:
    k: float = 24.0
    home: float = 60.0
    initial: float = 1500.0
    new_team_offset: float = -100.0
    draw_window_years: float = 6.0


@dataclass
class _State:
    rating: dict = field(default_factory=dict)
    venue_counts: dict = field(default_factory=lambda: defaultdict(Counter))
    team_counts: Counter = field(default_factory=Counter)
    draws: dict = field(default_factory=lambda: defaultdict(deque))


def _expect(diff: float) -> float:
    return 1.0 / (1.0 + 10 ** (-diff / 400.0))


def _is_home(team: str, venue_id: str, venue_country: str | None, team_type: str, st: _State) -> bool:
    if team_type == "international":
        return bool(venue_country) and team.lower() == str(venue_country).lower()
    n = st.team_counts[team]
    return n >= 5 and st.venue_counts[team][venue_id] / n >= 0.3


def elo_forecasts(matches: pd.DataFrame, venues: pd.DataFrame | None = None,
                  cfg: EloConfig | None = None) -> pd.DataFrame:
    """Pre-match forecasts for every row of `matches` (sorted by start_date internally).

    Returns match_id, p_team1 (decisive probability, ties as half), p_draw (Tests), and
    the three-way p1/pd/p2 for Tests."""
    cfg = cfg or EloConfig()
    country = {} if venues is None else dict(zip(venues.venue_id, venues.country))
    region = {} if venues is None else dict(zip(venues.venue_id, venues.region))
    states: dict[tuple, _State] = defaultdict(_State)
    rows = []
    order = matches.sort_values(["start_date", "match_id"])
    for m in order.itertuples(index=False):
        st = states[(m.fmt, m.gender)]
        t1, t2 = m.team1, m.team2
        r1 = st.rating.get(t1, cfg.initial + cfg.new_team_offset)
        r2 = st.rating.get(t2, cfg.initial + cfg.new_team_offset)
        vc = country.get(m.venue_id)
        h1 = _is_home(t1, m.venue_id, vc, m.team_type, st)
        h2 = _is_home(t2, m.venue_id, vc, m.team_type, st)
        diff = r1 - r2 + cfg.home * (int(h1) - int(h2))
        e1 = _expect(diff)
        p_draw = 0.0
        if m.fmt == "TEST":
            q = st.draws[region.get(m.venue_id, "other")]
            cutoff = pd.Timestamp(m.start_date) - pd.Timedelta(days=365.25 * cfg.draw_window_years)
            while q and q[0][0] < cutoff:
                q.popleft()
            p_draw = (sum(d for _, d in q) + 2) / (len(q) + 8) if q else 0.25
        rows.append({"match_id": m.match_id, "p_team1": e1, "p_draw": p_draw,
                     "p1": (1 - p_draw) * e1, "p2": (1 - p_draw) * (1 - e1),
                     "elo_team1": r1, "elo_team2": r2, "home1": h1, "home2": h2})
        if m.result in ("win", "tie", "draw"):
            s1 = 1.0 if (m.result == "win" and m.winner == t1) else 0.0 if m.result == "win" else 0.5
            if m.fmt == "TEST" and m.result == "draw":
                s1 = 0.5
            st.rating[t1] = r1 + cfg.k * (s1 - e1)
            st.rating[t2] = r2 - cfg.k * (s1 - e1)
            if m.fmt == "TEST":
                st.draws[region.get(m.venue_id, "other")].append((pd.Timestamp(m.start_date), float(m.result == "draw")))
        if m.result != "no_result":
            for t in (t1, t2):
                st.team_counts[t] += 1
                st.venue_counts[t][m.venue_id] += 1
    return pd.DataFrame(rows)


def scores(p: np.ndarray, y: np.ndarray) -> dict[str, float]:
    """Binary log loss and Brier for probabilities p of outcome y in {0, 0.5, 1}."""
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, float)
    ll = -(y * np.log(p) + (1 - y) * np.log(1 - p))
    return {"n": int(len(y)), "log_loss": float(ll.mean()), "brier": float(((p - y) ** 2).mean())}


def three_way_log_loss(p1: np.ndarray, pd_: np.ndarray, p2: np.ndarray, outcome: np.ndarray) -> float:
    """outcome: 0 team1 win, 1 draw, 2 team2 win (ties excluded by the caller)."""
    probs = np.column_stack([p1, pd_, p2])
    probs = np.clip(probs, 1e-6, 1)
    probs /= probs.sum(1, keepdims=True)
    return float(-np.log(probs[np.arange(len(outcome)), outcome]).mean())


def logit(p: float) -> float:
    p = min(max(p, 1e-9), 1 - 1e-9)
    return math.log(p / (1 - p))
