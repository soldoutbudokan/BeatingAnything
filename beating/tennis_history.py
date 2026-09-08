"""Frozen N2/N3 score-history features; no collection or outcome fitting.

Dates are source-local Europe/Prague dates. A date ends at the next local
midnight; its scores become available 48 elapsed hours after that instant.
At decision t, availability is inclusive (available_at <= t). Played-history
windows are (t - 365 days, t] and (t - 7 days, t], measured by date-end instants
in UTC, with the same availability gate. Elo uses all available history.

Stable player/event IDs are used verbatim. Records alone cannot establish
source coverage: a missing player history is not evidence of a player's debut.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
import math
from typing import Iterable
from zoneinfo import ZoneInfo

from .tennis_kernel import fit_hold_probabilities


def _identity(value, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be a nonempty stable string ID without surrounding whitespace")
    return value


def _instant(value: str | datetime) -> datetime:
    instant = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("decision_at must include a timezone")
    return instant.astimezone(timezone.utc)


def date_end_and_availability(value: str, timezone_name: str = "Europe/Prague") -> tuple[datetime, datetime]:
    """Return UTC (next local midnight, next local midnight + 48 hours)."""
    if not isinstance(value, str):
        raise ValueError("date must be an ISO local date")
    day = date.fromisoformat(value)
    if day.isoformat() != value:
        raise ValueError("date must be YYYY-MM-DD")
    end = datetime.combine(day + timedelta(days=1), time(), ZoneInfo(timezone_name)).astimezone(timezone.utc)
    return end, end + timedelta(hours=48)


def completed_set(score: tuple[int, int]) -> bool:
    high, low = max(score), min(score)
    return (high == 6 and 0 <= low <= 4) or (high == 7 and low in (5, 6))


def _complete_match(sets: tuple[tuple[int, int], ...]) -> bool:
    if len(sets) not in (2, 3) or not all(completed_set(score) for score in sets):
        return False
    wins = [0, 0]
    for index, (one, two) in enumerate(sets):
        wins[int(two > one)] += 1
        if max(wins) == 2:
            return index == len(sets) - 1
    return False


def elo_set_probability(rating1: float, rating2: float) -> float:
    # Stable logistic form of 1 / (1 + 10**(-(R1-R2)/400)).
    z = math.log(10) * (rating1 - rating2) / 400
    if z >= 0:
        return 1 / (1 + math.exp(-z))
    exponent = math.exp(z)
    return exponent / (1 + exponent)


@dataclass(frozen=True)
class _Record:
    event_id: str
    player1: str
    player2: str
    date_end: datetime
    available_at: datetime
    sets: tuple[tuple[int, int], ...]
    completed: bool

    @property
    def recognized_sets(self) -> tuple[tuple[int, int], ...]:
        return tuple(score for score in self.sets if completed_set(score))

    @property
    def workload_games(self) -> int:
        return sum(sum(score) for score in self.sets) if self.completed and _complete_match(self.sets) else 0


@dataclass
class _Timeline:
    available: list[datetime] = field(default_factory=list)
    date_ends: list[datetime] = field(default_factory=list)
    ratings: list[float] = field(default_factory=list)
    sets: list[int] = field(default_factory=lambda: [0])
    tiebreaks: list[int] = field(default_factory=lambda: [0])
    games: list[int] = field(default_factory=lambda: [0])

    def append(self, record: _Record, rating: float) -> None:
        recognized = record.recognized_sets
        self.available.append(record.available_at)
        self.date_ends.append(record.date_end)
        self.ratings.append(rating)
        self.sets.append(self.sets[-1] + len(recognized))
        self.tiebreaks.append(self.tiebreaks[-1] + sum(sorted(score) == [6, 7] for score in recognized))
        self.games.append(self.games[-1] + record.workload_games)


def _update_elo(ratings: dict[str, float], record: _Record) -> None:
    one, two = record.player1, record.player2
    for score1, score2 in record.recognized_sets:
        rating1, rating2 = ratings.get(one, 1500.0), ratings.get(two, 1500.0)
        change = 16 * (int(score1 > score2) - elo_set_probability(rating1, rating2))
        ratings[one], ratings[two] = rating1 + change, rating2 - change


class History:
    """Immutable input snapshot with chronological, query-order-independent features.

    Each record has event_id/date/player1/player2/sets/completed. `completed`
    means a normal completed best-of-three match, not a retirement. Workload
    additionally requires a conventional two-set-win score sequence. Recognized
    sets from noncompleted or ambiguous matches still update Elo/tiebreak rates.
    Exact duplicate event records are counted once; conflicting duplicates fail.
    """

    def __init__(self, records: Iterable[dict], timezone_name: str = "Europe/Prague"):
        self.timezone_name = timezone_name
        ZoneInfo(timezone_name)
        self._events: dict[str, _Record] = {}
        for value in records:
            event_id = _identity(value.get("event_id"), "event_id")
            player1, player2 = (_identity(value.get(key), key) for key in ("player1", "player2"))
            if player1 == player2:
                raise ValueError("player IDs must differ")
            if type(value.get("completed")) is not bool:
                raise ValueError("completed must be boolean")
            if not isinstance(value.get("sets"), (list, tuple)):
                raise ValueError("sets must be a sequence of game-score pairs")
            scores = []
            for score in value["sets"]:
                if not isinstance(score, (list, tuple)) or len(score) != 2 or any(type(n) is not int or n < 0 for n in score):
                    raise ValueError("set games must be nonnegative integer pairs")
                scores.append(tuple(score))
            end, available = date_end_and_availability(value["date"], timezone_name)
            record = _Record(event_id, player1, player2, end, available, tuple(scores), value["completed"])
            if event_id in self._events and self._events[event_id] != record:
                raise ValueError(f"conflicting history for event_id {event_id}; do not revise first-write history")
            self._events[event_id] = record
        self._records = sorted(self._events.values(), key=lambda record: (record.available_at, record.event_id))
        self._available = [record.available_at for record in self._records]
        self._players: dict[str, _Timeline] = {}
        ratings: dict[str, float] = {}
        for record in self._records:
            _update_elo(ratings, record)
            for player in (record.player1, record.player2):
                self._players.setdefault(player, _Timeline()).append(record, ratings.get(player, 1500.0))

    def _summary(self, player: str, decision: datetime, excluded: _Record | None) -> dict:
        timeline = self._players.get(player, _Timeline())
        upper = bisect_right(timeline.available, decision)
        lower365 = min(upper, bisect_right(timeline.date_ends, decision - timedelta(days=365)))
        lower7 = min(upper, bisect_right(timeline.date_ends, decision - timedelta(days=7)))
        lifetime = timeline.sets[upper]
        recent_sets = lifetime - timeline.sets[lower365]
        tiebreaks = timeline.tiebreaks[upper] - timeline.tiebreaks[lower365]
        games = timeline.games[upper] - timeline.games[lower7]
        events = upper
        if excluded and player in (excluded.player1, excluded.player2):
            recognized = excluded.recognized_sets
            events -= 1
            lifetime -= len(recognized)
            if excluded.date_end > decision - timedelta(days=365):
                recent_sets -= len(recognized)
                tiebreaks -= sum(sorted(score) == [6, 7] for score in recognized)
            if excluded.date_end > decision - timedelta(days=7):
                games -= excluded.workload_games
        return {"player_id": player, "elo": timeline.ratings[upper - 1] if upper else 1500.0,
                "lifetime_completed_sets": lifetime, "available_history_events": events,
                "completed_sets_365d": recent_sets, "tiebreak_sets_365d": tiebreaks,
                "shrunk_tiebreak_rate_365d": (tiebreaks + 50 * .12) / (recent_sets + 50),
                "completed_match_games_7d": games, "missing_history": recent_sets == 0,
                "missing_elo_history": lifetime == 0, "coverage_status": "unknown"}

    def features(self, player1: str, player2: str, event_id: str, decision_at: str | datetime) -> dict:
        player1, player2 = _identity(player1, "player1"), _identity(player2, "player2")
        if player1 == player2:
            raise ValueError("player IDs must differ")
        event_id = _identity(event_id, "event_id")
        decision = _instant(decision_at)
        current = self._events.get(event_id)
        excluded = current if current and current.available_at <= decision else None
        one, two = (self._summary(player, decision, excluded) for player in (player1, player2))
        if excluded:
            # Removing a set can change later opponents' ratings too; replay the
            # full available prefix, rather than subtracting this match's delta.
            ratings: dict[str, float] = {}
            for record in self._records[:bisect_right(self._available, decision)]:
                if record.event_id != event_id:
                    _update_elo(ratings, record)
            one["elo"], two["elo"] = ratings.get(player1, 1500.0), ratings.get(player2, 1500.0)
        set_p = elo_set_probability(one["elo"], two["elo"])
        games1, games2 = one["completed_match_games_7d"], two["completed_match_games_7d"]
        return {"event_id": event_id, "decision_at": decision.isoformat(),
                "feature_version": "tennis_score_history_n2_n3_v1", "source_timezone": self.timezone_name,
                "player1_history": one, "player2_history": two,
                "set_tiebreak_p": (one["shrunk_tiebreak_rate_365d"] + two["shrunk_tiebreak_rate_365d"]) / 2,
                "elo_set_win_p": set_p, "elo_match_win_p": 3 * set_p**2 - 2 * set_p**3,
                "workload_total": min(games1 + games2, 240) / 60,
                "workload_difference": min(abs(games1 - games2), 120) / 60,
                "current_event_history_excluded": current is not None,
                "current_event_history_inconsistency": excluded is not None}


def fit_n2(summary: dict, market_match_p: float) -> dict:
    """Fit N2 using a separately validated synchronized no-vig match quote."""
    return fit_hold_probabilities(market_match_p, summary["set_tiebreak_p"])


def fit_n3(summary: dict) -> dict:
    """Fit N3 using only the independent prior-history Elo match target."""
    return fit_hold_probabilities(summary["elo_match_win_p"], summary["set_tiebreak_p"])
