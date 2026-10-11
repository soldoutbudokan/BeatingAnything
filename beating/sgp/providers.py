"""Documented OpticOdds collection; never a sportsbook betting interface.

Schema sources (checked 2026-10-09):
https://developer.opticodds.com/reference/post_parlay-odds
https://developer.opticodds.com/reference/get_fixtures-odds
https://developer.opticodds.com/reference/get_fixtures-active

The SGP documentation lists theScore but not FanDuel. Ontario provenance and
redundant-leg fidelity require separate validation. The documented SGP response
has no source quote timestamp: ``received_at`` is only our receipt clock. Even
``status='priced'`` is research evidence, not a verified executable opportunity.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4


BASE_URL = "https://api.opticodds.com/api/v3"
SGP_SPORTSBOOKS = frozenset({
    "BetMGM", "BetMGM (UK)", "BetRivers", "Betsson", "Betway", "Bwin",
    "Caesars", "DraftKings", "Fanatics", "Ladbrokes (Australia)", "LeoVegas",
    "Midnite", "Novig", "Paddy Power", "Pointsbet (Australia)", "Prophet X",
    "Rimble", "Sportzino", "theScore", "Thunderpick", "Unibet",
    "Unibet (Australia)", "William Hill",
})
SAFE_HEADERS = frozenset({"date", "content-type", "last-modified", "retry-after",
                          "x-ratelimit-limit", "x-ratelimit-remaining"})


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class ProviderError(RuntimeError):
    """Sanitized transport/schema error; no credentials or response text."""


class RequestBudgetExceeded(ProviderError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_request(method, url, headers, body, timeout):
    """One documented request; no redirects, automatic retries, or credentials in URL."""
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except HTTPError as error:
        return error.code, dict(error.headers), error.read()


def _entry(entry):
    if not isinstance(entry, dict):
        raise ValueError("entries must contain objects")
    values = tuple(entry.get(key) for key in ("fixture_id", "market", "name"))
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("each entry requires fixture_id, market and name")
    return values


def _american(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and abs(value) >= 100)


def parse_parlay_response(value, sportsbook, entries):
    """Validate the exact leg multiset, retaining duplicates and never substituting AI.

    Book responses may reorder legs, but dropping one of two identical entries is
    a mismatch. Request order is retained by the caller for auditing/cache keys.
    """
    expected = Counter(_entry(item) for item in entries)
    result = {"status": "error", "american": None, "exact_legs_verified": False,
              "error": None, "source_timestamp": None,
              "source_freshness": "unverified", "jurisdiction": "unverified"}
    if not isinstance(value, dict):
        return {**result, "error": "invalid_response_schema"}
    data = value.get("data", value)  # documented combine-error example omits data
    if not isinstance(data, dict) or not isinstance(data.get(sportsbook), dict):
        return {**result, "error": "missing_requested_sportsbook"}
    book = data[sportsbook]
    if book.get("error") or book.get("missing_entries"):
        # Raw evidence retains provider diagnostics, not the normalized/public log.
        return {**result, "status": "unavailable", "error": "book_cannot_price_all_legs"}
    legs = book.get("legs")
    if not isinstance(legs, list):
        return {**result, "error": "missing_returned_legs"}
    try:
        actual = Counter(_entry(item) for item in legs)
    except ValueError:
        return {**result, "error": "invalid_returned_legs"}
    if actual != expected:
        return {**result, "error": "returned_legs_mismatch"}
    if not _american(book.get("price")):
        return {**result, "error": "invalid_american_price", "exact_legs_verified": True}
    return {**result, "status": "priced", "american": float(book["price"]),
            "exact_legs_verified": True}


class OpticOddsProvider:
    """Bounded client with raw evidence and transport injection for offline tests.

    No key means no requests. A response's HTTP Date is never used as the source
    quote clock. There is no AI fallback, and unsupported SGP books fail closed.
    Snapshot/discovery outputs remain provider dictionaries to avoid speculative
    mapping of milestone markets into over/under contracts.
    """

    def __init__(self, output, *, api_key=None, max_requests=100,
                 timeout=20, min_interval_seconds=0.5, transport=http_request,
                 clock=utc_now, sleeper=time.sleep, monotonic=time.monotonic):
        if type(max_requests) is not int or max_requests < 1:
            raise ValueError("max_requests must be a positive integer")
        if (not isinstance(timeout, (int, float)) or isinstance(timeout, bool)
                or not math.isfinite(timeout) or timeout <= 0):
            raise ValueError("timeout must be positive and finite")
        if (not isinstance(min_interval_seconds, (int, float))
                or isinstance(min_interval_seconds, bool)
                or not math.isfinite(min_interval_seconds)
                or not 0 <= min_interval_seconds <= 60):
            raise ValueError("min_interval_seconds must be between 0 and 60")
        if api_key is not None and (not isinstance(api_key, str) or not api_key.strip()):
            raise ValueError("api_key must be a nonempty string or None")
        self.output = Path(output)
        self.run_id = uuid4().hex
        self.raw_dir = self.output / self.run_id / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self._api_key = api_key
        self.max_requests, self.timeout = max_requests, timeout
        self.transport, self.clock = transport, clock
        self.min_interval_seconds = min_interval_seconds
        self.sleeper, self.monotonic = sleeper, monotonic
        self.requests = 0
        self._lock = threading.Lock()
        self._request_lock = threading.Lock()
        self._last_request_started = None
        self.stopped_reason = None

    def _fetch(self, method, path, *, params=(), payload=None):
        # One provider instance has one request stream: discovery, snapshots and
        # SGP pricing all share this pacing and denial boundary.
        with self._request_lock:
            return self._fetch_serial(method, path, params=params, payload=payload)

    def _fetch_serial(self, method, path, *, params=(), payload=None):
        if not self._api_key:
            raise ProviderError("missing_OPTICODDS_API_KEY: no request sent")
        # Paths are internal constants; auth is only sent to the fixed HTTPS host.
        if path not in {"/fixtures/active", "/fixtures/odds", "/parlay/odds"}:
            raise ValueError("unsupported provider endpoint")
        with self._lock:
            if self.stopped_reason:
                raise ProviderError("collection_stopped:" + self.stopped_reason)
            if self.requests >= self.max_requests:
                raise RequestBudgetExceeded("request_budget_exhausted")
            self.requests += 1
            request_number = self.requests
        url = BASE_URL + path + ("?" + urlencode(params, doseq=True) if params else "")
        headers = {"X-Api-Key": self._api_key, "Accept": "application/json",
                   "User-Agent": "BeatingAnything-SGP-research/0.1"}
        body = None
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode()
            headers["Content-Type"] = "application/json"
        if self._last_request_started is not None:
            delay = self.min_interval_seconds - (self.monotonic() - self._last_request_started)
            if delay > 0:
                self.sleeper(min(delay, 60))
        tick = self.monotonic()
        self._last_request_started = tick
        started = self.clock()
        status, response_headers, raw, error = None, {}, b"", None
        try:
            status, response_headers, raw = self.transport(
                method, url, headers, body, self.timeout)
        except Exception as exc:
            # urllib can also raise http.client.HTTPException or ValueError for
            # malformed responses/headers. Their messages may echo credentials.
            error = type(exc).__name__  # exception strings can contain credentials
        received = self.clock()
        if not isinstance(raw, bytes):
            raw, error = b"", "invalid_transport_body"
        if not isinstance(response_headers, dict):
            response_headers, error = {}, "invalid_transport_headers"
        if type(status) is not int and error is None:
            status, error = None, "invalid_http_status"
        # Auth errors can echo request headers; never persist a credential even then.
        safe_raw = raw.replace(self._api_key.encode(), b"[REDACTED]")
        raw_path = self.raw_dir / f"{request_number:06d}-{uuid4().hex}.json"
        safe_headers = {str(key).lower(): str(value).replace(self._api_key, "[REDACTED]")
                        for key, value in response_headers.items()
                        if str(key).lower() in SAFE_HEADERS}
        value = None
        if error is None:
            if not 200 <= status < 300:
                error = f"http_{status}"
            else:
                try:
                    value = json.loads(raw)
                except (ValueError, UnicodeError):
                    error = "invalid_json"
        if error:
            # Persist the stop before any evidence I/O, which can itself fail.
            with self._lock:
                self.stopped_reason = error
        raw_path.write_bytes(safe_raw)
        record = {"provider": "opticodds", "run_id": self.run_id,
                  "request_number": request_number, "method": method,
                  "url": url, "request_body": payload, "requested_at": started,
                  "received_at": received, "elapsed_seconds": self.monotonic() - tick,
                  "status": status, "error": error, "response_headers": safe_headers,
                  "raw_ref": str(raw_path.relative_to(self.output)),
                  "raw_sha256": hashlib.sha256(safe_raw).hexdigest(),
                  "raw_bytes": len(safe_raw), "credentials_redacted": safe_raw != raw}
        with self._lock:
            with (self.output / "requests.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, sort_keys=True) + "\n")
        if error:
            raise ProviderError(error)
        return value, record

    def quote(self, sportsbook, entries):
        if sportsbook not in SGP_SPORTSBOOKS:
            raise ProviderError("sgp_sportsbook_not_documented:" + str(sportsbook))
        if not isinstance(entries, (list, tuple)) or not 2 <= len(entries) <= 50:
            raise ValueError("SGP requires 2 to 50 entries")
        cleaned = [dict(zip(("fixture_id", "market", "name"), _entry(item)))
                   for item in entries]
        if len({item["fixture_id"] for item in cleaned}) != 1:
            raise ValueError("SGP entries must belong to one fixture")
        value, record = self._fetch("POST", "/parlay/odds",
                                   params=(("odds_format", "AMERICAN"),
                                           ("allow_missing_entries", "false")),
                                   payload={"sportsbooks": [sportsbook], "entries": cleaned})
        return {**parse_parlay_response(value, sportsbook, cleaned),
                "provider": "opticodds", "sportsbook": sportsbook, "entries": cleaned,
                "requested_at": record["requested_at"], "received_at": record["received_at"],
                "raw_ref": record["raw_ref"], "raw_sha256": record["raw_sha256"]}

    def discover_fixtures(self, leagues=("nfl",), *, start_after=None,
                          start_before=None, max_pages=50):
        if (not isinstance(leagues, (list, tuple)) or not leagues
                or any(league not in {"nfl", "ncaaf"} for league in leagues)):
            raise ValueError("leagues must contain nfl and/or ncaaf")
        if type(max_pages) is not int or max_pages < 1:
            raise ValueError("max_pages must be a positive integer")
        params = [("league", league) for league in leagues] + [("status", "unplayed")]
        if start_after is not None:
            params.append(("start_date_after", start_after))
        if start_before is not None:
            params.append(("start_date_before", start_before))
        fixtures, seen = [], set()
        for page in range(1, max_pages + 1):
            value, _ = self._fetch("GET", "/fixtures/active", params=params + [("page", page)])
            if (not isinstance(value, dict) or not isinstance(value.get("data"), list)
                    or type(value.get("has_more")) is not bool):
                raise ProviderError("invalid_fixture_page")
            for fixture in value["data"]:
                if not isinstance(fixture, dict) or not isinstance(fixture.get("id"), str):
                    raise ProviderError("invalid_fixture")
                if fixture["id"] not in seen:
                    seen.add(fixture["id"])
                    fixtures.append(fixture)
            if not value["has_more"]:
                return fixtures
        raise ProviderError("fixture_pagination_incomplete")

    def snapshot(self, fixture_ids, sportsbooks, markets=()):
        """One complete provider snapshot for the exact requested scope (<=5x5).

        Omitted odds mean unavailable only within this successful response's
        fixture/book/market scope. A failed or partially parsed fetch must never
        invalidate an entire league. Individual source ``timestamp`` fields are
        left intact; no collection timestamp replaces them.
        """
        for label, items in (("fixture_ids", fixture_ids), ("sportsbooks", sportsbooks)):
            if (not isinstance(items, (list, tuple)) or not 1 <= len(items) <= 5
                    or any(not isinstance(item, str) or not item for item in items)):
                raise ValueError(label + " requires 1 to 5 nonempty strings")
        if (not isinstance(markets, (list, tuple))
                or any(not isinstance(item, str) or not item for item in markets)):
            raise ValueError("markets must be a sequence of nonempty strings")
        params = ([("fixture_id", item) for item in fixture_ids]
                  + [("sportsbook", item) for item in sportsbooks]
                  + [("market", item) for item in markets] + [("odds_format", "AMERICAN")])
        value, record = self._fetch("GET", "/fixtures/odds", params=params)
        if not isinstance(value, dict) or not isinstance(value.get("data"), list):
            raise ProviderError("invalid_snapshot")
        for fixture in value["data"]:
            if (not isinstance(fixture, dict) or fixture.get("id") not in fixture_ids
                    or not isinstance(fixture.get("odds"), list)
                    or any(not isinstance(odd, dict) for odd in fixture["odds"])):
                raise ProviderError("invalid_snapshot_fixture")
        return {**value, "collection": {"provider": "opticodds", "complete": True,
                "fixture_ids": list(fixture_ids), "sportsbooks": list(sportsbooks),
                "markets": list(markets), "received_at": record["received_at"],
                "raw_ref": record["raw_ref"], "jurisdiction": "unverified"}}

    def snapshots(self, fixture_ids, sportsbooks, markets=()):
        """Batch the fixture and sportsbook inventory into documented 5x5 requests."""
        if not fixture_ids or not sportsbooks:
            raise ValueError("fixture_ids and sportsbooks must not be empty")
        return [self.snapshot(fixture_ids[i:i + 5], sportsbooks[j:j + 5], markets)
                for i in range(0, len(fixture_ids), 5)
                for j in range(0, len(sportsbooks), 5)]
