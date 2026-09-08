"""Exact standard best-of-three tennis from constant service-game holds.

All sets use a seven-point, win-by-two tiebreak at 6-6. Initial server is
unknown with equal probability. Server order continues across set boundaries;
the tiebreak counts as one game for both total games and server alternation.
Service-point probabilities are constant independent Bernoulli probabilities
inferred from each hold rate and reused in the tiebreak. This is a structural
approximation, with no fatigue, within-match dependence or changing form.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math

import numpy as np
from scipy.optimize import brentq, least_squares


@dataclass(frozen=True)
class _SetLaw:
    # Index 0 is player one's win; index 1 is player two's win.
    player_one: tuple[float, ...]
    player_two: tuple[float, ...]
    tiebreak_probability: float


def _probability(value: float, name: str, *, strict: bool = False) -> float:
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 1 or (strict and value in (0, 1)):
        raise ValueError(f"{name} must be a {'strict ' if strict else ''}probability")
    return value


def game_hold_probability(serve_point_p: float) -> float:
    """Advantage scoring: win before deuce, or reach deuce then absorb."""
    p = _probability(serve_point_p, "serve_point_p")
    q = 1 - p
    before_deuce = p**4 * (1 + 4*q + 10*q*q)
    reach_deuce = 20 * p**3 * q**3
    return before_deuce + reach_deuce * p*p / (p*p + q*q)


@lru_cache(maxsize=50000)
def serve_point_probability(hold_p: float) -> float:
    """Invert the monotone advantage-game formula without approximation."""
    hold_p = _probability(hold_p, "hold_p")
    if hold_p in (0, 1):
        return hold_p
    return float(brentq(lambda p: game_hold_probability(p) - hold_p,
                        0.0, 1.0, xtol=1e-13, rtol=1e-13))


def tiebreak_win_probability(serve_point_p1: float, serve_point_p2: float,
                             first_server: int = 1) -> float:
    """Exact player-one tiebreak win probability, including unbounded deuce.

    From a tie at 6-6 or later, every next pair of points contains one serve
    from each player. Winning both has probability p1*(1-p2), losing both has
    probability (1-p1)*p2, and splitting returns to a tie. Consequently the
    exact absorption probability is win_both / (win_both + lose_both),
    independent of which of those two points is served first.
    """
    p1 = _probability(serve_point_p1, "serve_point_p1")
    p2 = _probability(serve_point_p2, "serve_point_p2")
    if first_server not in (1, 2):
        raise ValueError("first_server must be 1 or 2")
    win_both, lose_both = p1 * (1-p2), (1-p1) * p2
    if win_both + lose_both == 0:
        raise ValueError("Degenerate tiebreak does not absorb")
    deuce_win = win_both / (win_both + lose_both)
    state = np.zeros((7, 7), dtype=float)
    state[0, 0] = 1
    win_probability = 0.0
    # First point: first server. Points 2-3: opponent, 4-5: first server, etc.
    for points_played in range(12):
        server = first_server if ((points_played + 1) // 2) % 2 == 0 else 3-first_server
        win_point = p1 if server == 1 else 1-p2
        for score1 in range(max(0, points_played-6), min(6, points_played)+1):
            score2 = points_played-score1
            mass = state[score1, score2]
            if score1 == 6:
                win_probability += mass * win_point
            else:
                state[score1+1, score2] += mass * win_point
            if score2 < 6:
                state[score1, score2+1] += mass * (1-win_point)
            # A player-two seventh point absorbs into the losing outcome.
    return float(win_probability + state[6, 6] * deuce_win)


def _set_law(hold1: float, hold2: float, first_server: int, tiebreak_p: float) -> _SetLaw:
    state = np.zeros((7, 7), dtype=float)
    state[0, 0] = 1
    player_one = np.zeros(14, dtype=float)
    player_two = np.zeros(14, dtype=float)
    for games_played in range(12):
        server = first_server if games_played % 2 == 0 else 3-first_server
        win_game = hold1 if server == 1 else 1-hold2
        for games1 in range(max(0, games_played-6), min(6, games_played)+1):
            games2 = games_played-games1
            mass = state[games1, games2]
            if mass == 0:
                continue
            next1 = games1+1
            if next1 >= 6 and next1-games2 >= 2:
                player_one[games_played+1] += mass * win_game
            else:
                state[next1, games2] += mass * win_game
            next2 = games2+1
            if next2 >= 6 and next2-games1 >= 2:
                player_two[games_played+1] += mass * (1-win_game)
            else:
                state[games1, next2] += mass * (1-win_game)
    reaches_tiebreak = state[6, 6]
    player_one[13] = reaches_tiebreak * tiebreak_p
    player_two[13] = reaches_tiebreak * (1-tiebreak_p)
    return _SetLaw(tuple(player_one), tuple(player_two), float(reaches_tiebreak))


@lru_cache(maxsize=50000)
def _set_laws(hold1: float, hold2: float) -> tuple[_SetLaw, _SetLaw]:
    hold1 = _probability(hold1, "hold1", strict=True)
    hold2 = _probability(hold2, "hold2", strict=True)
    point1, point2 = serve_point_probability(hold1), serve_point_probability(hold2)
    return tuple(_set_law(hold1, hold2, server,
                          tiebreak_win_probability(point1, point2, server))
                 for server in (1, 2))


def _match_probability(laws: tuple[_SetLaw, _SetLaw]) -> float:
    """Small absorbing set/next-server chain used during numerical fitting."""
    state = {(0, 0, 1): .5, (0, 0, 2): .5}
    match_win = 0.0
    transitions = {}
    for server, law in enumerate(laws, start=1):
        for winner, probabilities in enumerate((law.player_one, law.player_two)):
            transitions[server, winner, 0] = sum(probabilities[::2])
            transitions[server, winner, 1] = sum(probabilities[1::2])
    for _ in range(3):
        next_state = {}
        for (wins1, wins2, server), mass in state.items():
            for winner in (0, 1):
                new1, new2 = wins1 + (winner == 0), wins2 + (winner == 1)
                for parity in (0, 1):
                    probability = mass * transitions[server, winner, parity]
                    if new1 == 2:
                        match_win += probability
                    elif new2 < 2:
                        next_server = server if parity == 0 else 3-server
                        key = new1, new2, next_server
                        next_state[key] = next_state.get(key, 0.0) + probability
        state = next_state
    return float(match_win)


def match_metrics(hold1: float, hold2: float) -> tuple[float, float]:
    """Return (player-one match win, first-set reaches 6-6), server averaged.

    This cheaper path is mathematically identical to match_distribution for
    these two statistics. Tiebreak rate means the set's probability of reaching
    6-6, not probability of at least one tiebreak anywhere in the match.
    """
    laws = _set_laws(float(hold1), float(hold2))
    return _match_probability(laws), sum(law.tiebreak_probability for law in laws)/2


def match_distribution(hold1: float, hold2: float) -> dict:
    """Return exact best-of-three statistics and a PMF indexed by total games.

    Keys: match_win_p, total_games_pmf (length 40, indices 0..39),
    over_21_5_p, set_tiebreak_p, player_one_win_games_pmf,
    player_two_win_games_pmf, hold1, hold2, serve_point_p1, serve_point_p2.
    Arrays are new copies and cannot alter the internal cached set laws.
    """
    hold1, hold2 = float(hold1), float(hold2)
    laws = _set_laws(hold1, hold2)
    state = {(0, 0, 1): np.array([.5]), (0, 0, 2): np.array([.5])}
    won = np.zeros((2, 40), dtype=float)
    transitions = {}
    for server, law in enumerate(laws, start=1):
        for winner, probabilities in enumerate((law.player_one, law.player_two)):
            for parity in (0, 1):
                kernel = np.array(probabilities)
                kernel[1-parity::2] = 0
                transitions[server, winner, parity] = kernel
    for _ in range(3):
        next_state = {}
        for (wins1, wins2, server), mass in state.items():
            for winner in (0, 1):
                new1, new2 = wins1 + (winner == 0), wins2 + (winner == 1)
                for parity in (0, 1):
                    weighted = np.convolve(mass, transitions[server, winner, parity])
                    if new1 == 2 or new2 == 2:
                        won[winner, :len(weighted)] += weighted
                    else:
                        next_server = server if parity == 0 else 3-server
                        key = new1, new2, next_server
                        if key not in next_state:
                            next_state[key] = np.zeros_like(weighted)
                        next_state[key] += weighted
        state = next_state
    total = won.sum(axis=0)
    if abs(total.sum()-1) > 1e-10 or np.min(total) < -1e-14:
        raise ArithmeticError("Tennis probability mass did not conserve")
    return {"hold1": hold1, "hold2": hold2,
            "serve_point_p1": serve_point_probability(hold1),
            "serve_point_p2": serve_point_probability(hold2),
            "match_win_p": float(won[0].sum()), "total_games_pmf": total,
            "player_one_win_games_pmf": won[0].copy(),
            "player_two_win_games_pmf": won[1].copy(),
            "over_21_5_p": float(total[22:].sum()),
            "set_tiebreak_p": sum(law.tiebreak_probability for law in laws)/2}


def fit_hold_probabilities(match_win_p: float, set_tiebreak_p: float) -> dict:
    """Fit the frozen two-target kernel; reject max absolute residual > .03.

    Rates have fixed bounds [.5, .995], initial guess [.75, .75] and all solver
    tolerances 1e-8. No odds, observed match outcome, or total-game outcome is
    read by the kernel. Callers construct the two pre-match targets.
    """
    target = np.array([_probability(match_win_p, "match_win_p"),
                       _probability(set_tiebreak_p, "set_tiebreak_p")])
    result = least_squares(lambda holds: np.asarray(match_metrics(*holds)) - target,
                           x0=np.array([.75, .75]), bounds=([.5, .5], [.995, .995]),
                           ftol=1e-8, xtol=1e-8, gtol=1e-8)
    if not result.success or not np.isfinite(result.x).all():
        raise ValueError("tennis_kernel_nonconvergent")
    residuals = np.asarray(match_metrics(*result.x)) - target
    max_error = float(np.abs(residuals).max())
    if not math.isfinite(max_error) or max_error > .03:
        raise ValueError("tennis_kernel_probability_mismatch")
    distribution = match_distribution(*result.x)
    return {"hold1": float(result.x[0]), "hold2": float(result.x[1]),
            "target_match_win_p": float(target[0]), "target_set_tiebreak_p": float(target[1]),
            "match_probability_residual": float(residuals[0]),
            "set_tiebreak_probability_residual": float(residuals[1]),
            "max_probability_error": max_error, "nfev": int(result.nfev),
            "distribution": distribution}
