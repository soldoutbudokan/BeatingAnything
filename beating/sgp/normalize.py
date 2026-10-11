"""Strict conversion of OpticOdds snapshots to a player-market inventory.

Market names are configuration, never a fuzzy match. Single prices are inventory
metadata, not SGP prices. Conflicting identities are quarantined for the whole
batch; an arbitrary first/last observation must not become a tradable quote.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import math
from typing import Any


_BOOKS = {"theScore": "thescore", "FanDuel": "fanduel"}
_STATS = {"R", "C", "S"}
_SIDES = {"over", "under", "at_least", "at_most"}
_PREGAME_STATUSES = {"unplayed", "scheduled", "not_started", "upcoming"}


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _number(value: Any) -> float | int:
    # Numeric strings can hide a changed provider schema; do not coerce them.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("expected a finite number")
    if not math.isfinite(value):
        raise ValueError("expected a finite number")
    return value


def _utc(value: Any) -> str:
    if isinstance(value, bool):
        raise ValueError("invalid timestamp")
    if isinstance(value, (float, int)):
        # OpticOdds source timestamps are Unix seconds, not milliseconds.
        instant = datetime.fromtimestamp(_number(value), tz=timezone.utc)
    elif isinstance(value, str):
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
    else:
        raise ValueError("invalid timestamp")
    return instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _market_map(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError("market_map must be a dictionary")
    for market, mapping in value.items():
        if not _text(market) or not isinstance(mapping, dict):
            raise ValueError("each exact market name needs a mapping")
        if not isinstance(mapping.get("stat"), str) or mapping["stat"] not in _STATS:
            raise ValueError(f"invalid stat mapping for {market!r}")
        if set(mapping) - {"stat", "side"}:
            raise ValueError(f"unsupported mapping fields for {market!r}")
        if "side" in mapping and (not isinstance(mapping["side"], str) or mapping["side"] not in _SIDES):
            raise ValueError(f"invalid side mapping for {market!r}")
    return value


def normalize_snapshots(
    snapshots: list[dict], *, market_map: dict, region: str,
    settlement: str, captured_at: str,
) -> dict:
    """Normalize raw ``{"data": [fixture, ...]}`` responses, failing closed.

    ``region`` and ``settlement`` are explicit operator attestations, not claims
    derived from provider names. ``captured_at`` is the collector receipt clock;
    every accepted leg must also have its own valid provider source clock.
    Coverage reports unsupported input and absent R/C/S markets for each book.
    Missing markets do not prevent retaining the available inventory.
    """
    if not isinstance(snapshots, list):
        raise ValueError("snapshots must be a list of raw response dictionaries")
    if not _text(region) or not _text(settlement):
        raise ValueError("region and settlement must be explicit nonempty strings")
    receipt_at = _utc(captured_at)
    mappings = _market_map(market_map)
    skipped: Counter[str] = Counter()
    unsupported_markets: Counter[str] = Counter()
    fixture_metadata: dict[str, tuple] = {}
    bad_fixtures: set[str] = set()
    player_names: dict[tuple, str] = {}
    bad_players: set[tuple] = set()
    legs: dict[tuple, tuple[tuple, dict]] = {}
    leg_receipts: dict[tuple, str] = {}
    bad_legs: set[tuple] = set()
    fixture_count = 0
    odds_count = 0

    for snapshot in snapshots:
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("data"), list):
            skipped["malformed_snapshot"] += 1
            continue
        snapshot_receipt = receipt_at
        if "collection" in snapshot:
            collection = snapshot["collection"]
            if not isinstance(collection, dict) or collection.get("complete") is not True:
                skipped["incomplete_snapshot"] += 1
                continue
            try:
                snapshot_receipt = _utc(collection.get("received_at"))
            except (ValueError, TypeError, OverflowError, OSError):
                skipped["invalid_receipt_time"] += 1
                continue
        for fixture in snapshot["data"]:
            fixture_count += 1
            if not isinstance(fixture, dict):
                skipped["malformed_fixture"] += 1
                continue
            raw_odds = fixture.get("odds")
            if isinstance(raw_odds, list):
                odds_count += len(raw_odds)
            event_id = fixture.get("id")
            league = fixture.get("league")
            league_id = league.get("id") if isinstance(league, dict) else None
            if not _text(event_id) or not isinstance(raw_odds, list):
                skipped["missing_fixture_identity_or_odds"] += 1
                if _text(event_id):
                    bad_fixtures.add(event_id)
                continue
            if not isinstance(league_id, str) or league_id not in {"nfl", "ncaaf"}:
                skipped["unsupported_league"] += 1
                bad_fixtures.add(event_id)
                continue
            status = fixture.get("status")
            if not isinstance(status, str) or status not in _PREGAME_STATUSES:
                skipped["not_confirmed_pregame"] += 1
                bad_fixtures.add(event_id)
                continue
            try:
                starts_at = _utc(fixture.get("start_date"))
            except (ValueError, TypeError, OverflowError, OSError):
                skipped["invalid_start_date"] += 1
                bad_fixtures.add(event_id)
                continue
            metadata = (league_id, starts_at)
            if event_id in fixture_metadata and fixture_metadata[event_id] != metadata:
                skipped["conflicting_fixture_identity"] += 1
                bad_fixtures.add(event_id)
                continue
            fixture_metadata[event_id] = metadata

            for odd in raw_odds:
                if not isinstance(odd, dict):
                    skipped["malformed_odd"] += 1
                    continue
                book_name = odd.get("sportsbook")
                if not isinstance(book_name, str) or book_name not in _BOOKS:
                    skipped["unsupported_sportsbook"] += 1
                    continue
                book = _BOOKS[book_name]
                selection_id = odd.get("id")
                player_id = odd.get("player_id")
                market_id = odd.get("market_id")
                player_name = odd.get("selection")
                if not all(_text(v) for v in (selection_id, player_id, market_id, player_name)):
                    skipped["missing_selection_identity"] += 1
                    # A malformed update for a known selection invalidates it.
                    if _text(selection_id):
                        bad_legs.add((event_id, book, selection_id))
                    continue
                leg_key = (event_id, book, selection_id)
                player_key = (event_id, player_id)
                if player_key in player_names and player_names[player_key] != player_name:
                    skipped["conflicting_player_identity"] += 1
                    bad_players.add(player_key)
                    continue
                player_names[player_key] = player_name

                def reject(reason: str) -> None:
                    skipped[reason] += 1
                    bad_legs.add(leg_key)

                odd_status = odd.get("status")
                if (odd.get("is_suspended") is True or odd.get("suspended") is True
                        or odd.get("is_active") is False or odd.get("active") is False
                        or (isinstance(odd_status, str)
                            and odd_status in {"suspended", "closed", "locked", "inactive"})):
                    reject("unavailable_selection")
                    continue
                market = odd.get("market")
                mapping = mappings.get(market) if isinstance(market, str) else None
                if mapping is None:
                    if isinstance(market, str):
                        unsupported_markets[market] += 1
                    reject("unmapped_market")
                    continue
                side = mapping.get("side", odd.get("selection_line"))
                # Only explicit mapping may introduce inclusive milestone sides.
                if (not isinstance(side, str)
                        or side not in (_SIDES if "side" in mapping else {"over", "under"})):
                    reject("unsupported_side")
                    continue
                try:
                    line = _number(odd.get("points"))
                    price = _number(odd.get("price"))
                    if abs(price) < 100:
                        raise ValueError("price must be American odds")
                    source_at = _utc(odd.get("timestamp"))
                except (ValueError, TypeError, OverflowError, OSError):
                    reject("invalid_line_price_or_source_time")
                    continue
                leg = {
                    "selection_id": selection_id, "market_id": market_id,
                    "stat": mapping["stat"], "side": side, "line": line,
                    "provider": {"fixture_id": event_id, "market": market, "name": odd.get("name")},
                    "source_at": source_at, "single_price": price,
                }
                observation = (player_key, leg)
                if leg_key in legs:
                    if legs[leg_key] == observation:
                        skipped["duplicate_identical_selection"] += 1
                        leg_receipts[leg_key] = min(leg_receipts[leg_key], snapshot_receipt,
                                                   key=datetime.fromisoformat)
                    else:
                        reject("conflicting_selection_identity")
                    continue
                legs[leg_key] = observation
                leg_receipts[leg_key] = snapshot_receipt

    boards: dict[tuple, dict] = {}
    quarantined = 0
    for (event_id, book, selection_id), (player_key, leg) in sorted(legs.items()):
        if (event_id in bad_fixtures or player_key in bad_players
                or (event_id, book, selection_id) in bad_legs):
            quarantined += 1
            continue
        if player_key not in boards:
            league, starts_at = fixture_metadata[event_id]
            boards[player_key] = {
                "event_id": event_id, "player_id": player_key[1],
                "player_name": player_names[player_key], "league": league,
                "region": region, "settlement": settlement,
                "starts_at": starts_at, "books": {},
            }
        book_inventory = boards[player_key]["books"].setdefault(book, {
            "sportsbook": next(name for name, normalized in _BOOKS.items() if normalized == book),
            "fixture_id": event_id,
            "captured_at": leg_receipts[(event_id, book, selection_id)], "legs": [],
        })
        book_inventory["captured_at"] = min(
            book_inventory["captured_at"], leg_receipts[(event_id, book, selection_id)],
            key=datetime.fromisoformat,
        )
        book_inventory["legs"].append(leg)
    missing_markets = []
    accepted_legs = 0
    for board in boards.values():
        for book in _BOOKS.values():
            book_legs = board["books"].get(book, {}).get("legs", [])
            accepted_legs += len(book_legs)
            missing = sorted(_STATS - {leg["stat"] for leg in book_legs})
            if missing:
                missing_markets.append({
                    "event_id": board["event_id"], "player_id": board["player_id"],
                    "book": book, "stats": missing,
                })
    return {
        "schema_version": 1, "mode": "live", "captured_at": receipt_at,
        "boards": list(boards.values()),
        "coverage": {
            "input_snapshots": len(snapshots), "input_fixtures": fixture_count,
            "input_odds": odds_count, "accepted_legs": accepted_legs,
            "boards": len(boards), "quarantined_legs": quarantined,
            "skipped": dict(sorted(skipped.items())),
            "unsupported_markets": dict(sorted(unsupported_markets.items())),
            "missing_markets": missing_markets,
        },
    }
