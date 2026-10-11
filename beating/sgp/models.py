"""Validated inventories and stable, exact-selection quote identities."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math

BOOKS = {"thescore": "theScore", "fanduel": "FanDuel"}
CELLS = ("OO", "OU", "UO", "UU")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO string with timezone")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return result


def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def scope(board, book):
    return {k: board[k] for k in ("event_id", "player_id", "league", "region", "settlement")} | {"book": book}


def leg_identity(leg):
    # Provider labels/IDs and ordered leg identities are deliberately preserved.
    return {k: leg[k] for k in ("selection_id", "market_id", "stat", "side", "line", "provider")}


def book_revision(inventory):
    # Clock-only updates do not invalidate every SGP. A line, ID, status, or
    # single-price change does. TTL still expires SGPs without board movement.
    return digest({"fixture_id": inventory["fixture_id"], "sportsbook": inventory["sportsbook"],
                   "source_revision": inventory.get("source_revision"),
                   "legs": sorted([leg_identity(leg) | {"single_price": leg.get("single_price")}
                                   for leg in inventory["legs"]], key=lambda x: x["selection_id"])})


def validate_manifest(value):
    if value.get("schema_version") != 1 or value.get("mode") not in ("live", "historical"):
        raise ValueError("expected schema_version 1 and mode live/historical")
    captured = timestamp(value.get("captured_at"))
    if not isinstance(value.get("boards"), list):
        raise ValueError("boards must be a list")
    seen = set()
    for board in value["boards"]:
        for key in ("event_id", "player_id", "player_name", "league", "region", "settlement"):
            text(board.get(key), key)
        if board["league"] not in ("nfl", "ncaaf"):
            raise ValueError("only nfl/ncaaf inventories supported")
        if value["mode"] == "live" or board.get("starts_at") is not None:
            timestamp(board.get("starts_at"))
        if not isinstance(board.get("books"), dict):
            raise ValueError("books must be a mapping")
        for book, inventory in board["books"].items():
            if book not in BOOKS or inventory.get("sportsbook") != BOOKS[book]:
                raise ValueError("unsupported or mismatched sportsbook identity")
            if (inventory.get("status", "active") not in ("active", "available", "open")
                    or inventory.get("is_active") is False or inventory.get("is_suspended") is True):
                raise ValueError("inactive inventory must not be offered for pricing")
            key = digest(scope(board, book))
            if key in seen:
                raise ValueError("duplicate event/player/book scope")
            seen.add(key)
            text(inventory.get("fixture_id"), "fixture_id")
            if timestamp(inventory.get("captured_at")) > captured:
                raise ValueError("inventory capture cannot exceed manifest capture")
            if not isinstance(inventory.get("legs"), list):
                raise ValueError("inventory legs must be a list")
            ids = set()
            for leg in inventory["legs"]:
                if (leg.get("status", "active") not in ("active", "available", "open")
                        or leg.get("is_active") is False or leg.get("is_suspended") is True):
                    raise ValueError("inactive selections must be removed from the new inventory")
                for field in ("selection_id", "market_id"):
                    text(leg.get(field), field)
                if leg["selection_id"] in ids:
                    raise ValueError("duplicate selection ID in inventory")
                ids.add(leg["selection_id"])
                if leg.get("stat") not in ("S", "R", "C"):
                    raise ValueError("unknown stat")
                if leg.get("side") not in ("over", "under", "at_least", "at_most"):
                    raise ValueError("unknown selection side")
                leg["line"] = number(leg.get("line"), "line")
                provider = leg.get("provider")
                if not isinstance(provider, dict) or set(provider) != {"fixture_id", "market", "name"}:
                    raise ValueError("provider entry requires exact fixture_id/market/name")
                for field in provider:
                    text(provider[field], "provider " + field)
                if provider["fixture_id"] != inventory["fixture_id"]:
                    raise ValueError("provider fixture does not match book inventory")
                if leg.get("source_at") is not None:
                    timestamp(leg["source_at"])
                if leg.get("single_price") is not None:
                    number(leg["single_price"], "single_price")
    return value


def quote_request(board, book, legs, *, purpose):
    inventory = board["books"][book]
    identity = scope(board, book) | {
        "sportsbook": inventory["sportsbook"],
        "fixture_id": inventory["fixture_id"], "revision": book_revision(inventory),
        "legs": [leg_identity(leg) for leg in legs],
    }
    return identity | {"key": digest(identity), "scope_key": digest(scope(board, book)),
                       "purpose": purpose, "inventory_captured_at": inventory["captured_at"]}


def validate_request(request):
    identity = {k: request[k] for k in ("event_id", "player_id", "league", "region", "settlement",
                "book", "sportsbook", "fixture_id", "revision", "legs")}
    if digest(identity) != request["key"]:
        raise ValueError("capture request key does not match exact selections")
    return request
