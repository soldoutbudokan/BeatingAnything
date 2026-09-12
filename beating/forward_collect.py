"""Bounded raw market acquisition. No predictions, alerts, or wagering.

The Odds API documents only provider-supported markets, not the entire FanDuel
board. Every response is retained before parsing; no quote or status filtering.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

HOSTS = {"the_odds_api": "https://api.the-odds-api.com",
         "mlb_statsapi": "https://statsapi.mlb.com"}
BOOKMAKERS = ("fanduel", "pinnacle")
DEFAULTS = {"sports": ["*"], "cycles": 1, "interval_seconds": 180,
            "max_requests": 500, "max_credits": 100, "market_batch_size": 20,
            "timeout_seconds": 30, "mlb_game_state": False}
SAFE_HEADERS = ("date", "content-type", "last-modified", "retry-after",
                "x-requests-last", "x-requests-used", "x-requests-remaining")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class StopCollection(Exception):
    """A request/credit cap or terminal source failure stops this process."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_get(url, timeout):
    """An ordinary documented GET, with no redirects or retry on denial."""
    opener = build_opener(NoRedirect())
    request = Request(url, headers={"User-Agent": "BeatingAnything-research/0.1",
                                    "Accept": "application/json"})
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except HTTPError as error:
        # Error bytes are evidence too; do not print a URL containing apiKey.
        return error.code, dict(error.headers), error.read()


def source_clocks(value, provider):
    """Index clocks without replacing missing source times with local times."""
    if not isinstance(value, dict):
        return {}
    if provider == "mlb_statsapi":
        current = value.get("liveData", {}).get("plays", {}).get("currentPlay", {})
        about = current.get("about", {})
        return {"mlb_game_pk": value.get("gamePk"),
                "feed_time_stamp": value.get("metaData", {}).get("timeStamp"),
                "current_play_start_time": about.get("startTime"),
                "current_play_end_time": about.get("endTime"),
                "odds_event_id": None, "join_status": "unmapped"}
    clocks = []
    for book in value.get("bookmakers", []):
        for market in book.get("markets", []):
            clocks.append({"bookmaker": book.get("key"), "market": market.get("key"),
                           "bookmaker_last_update": book.get("last_update"),
                           "market_last_update": market.get("last_update")})
    return {"odds_event_id": value.get("id"),
            "commence_time": value.get("commence_time"),
            "provider_snapshot_at": value.get("timestamp"),
            "market_clocks": clocks, "mlb_game_pk": None,
            "join_status": "unmapped"}


class Collector:
    def __init__(self, output, config, *, api_key=None, transport=http_get,
                 synthetic=False, clock=utc_now):
        self.config = {**DEFAULTS, **config}
        for key in ("cycles", "max_requests", "max_credits", "market_batch_size"):
            if type(self.config[key]) is not int or self.config[key] < 1:
                raise ValueError(f"{key} must be a positive integer")
        for key in ("interval_seconds", "timeout_seconds"):
            if not isinstance(self.config[key], (int, float)) or self.config[key] <= 0:
                raise ValueError(f"{key} must be positive")
        sports = self.config["sports"]
        if not isinstance(sports, list) or not sports or any(not isinstance(s, str) or not s for s in sports):
            raise ValueError("sports must be a nonempty list of sport keys, or ['*']")
        if "*" in sports and sports != ["*"]:
            raise ValueError("wildcard sports must be ['*']")
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.run_id = uuid4().hex
        self.raw_dir = self.output / self.run_id / "raw"
        self.raw_dir.mkdir(parents=True)
        self.api_key, self.transport = api_key, transport
        self.synthetic, self.clock = synthetic, clock
        self.requests = self.credits_reserved = self.credits_reported = 0
        self.provider_credits_remaining = None
        self.odds_responses = self.mlb_feed_responses = self.failures = 0
        self.completed_cycles = 0
        self.started_at = clock()
        self.record("run_start", config=self.config, synthetic=synthetic)

    def record(self, kind, **fields):
        row = {"kind": kind, "run_id": self.run_id,
               "recorded_at": self.clock(), **fields}
        with (self.output / "index.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
        return row

    def fetch(self, provider, path, params=None, *, credit_upper=0, context=None):
        if self.requests >= self.config["max_requests"]:
            raise StopCollection("request_cap")
        if self.credits_reserved + credit_upper > self.config["max_credits"]:
            raise StopCollection("credit_cap: next request would exceed session allowance")
        if (provider == "the_odds_api" and self.provider_credits_remaining is not None
                and credit_upper > self.provider_credits_remaining):
            raise StopCollection("provider_credit_balance_below_next_request")
        if provider == "the_odds_api" and not self.api_key and not self.synthetic:
            raise StopCollection("missing_ODDS_API_KEY: no live odds requested")
        params = dict(params or {})
        public_url = HOSTS[provider] + path
        if params:
            public_url += "?" + urlencode(params)
        if provider == "the_odds_api":
            params["apiKey"] = self.api_key or "SYNTHETIC-NOT-A-KEY"
        url = HOSTS[provider] + path + ("?" + urlencode(params) if params else "")
        self.requests += 1
        # Reserve the maximum before sending: timeout can have consumed credits.
        self.credits_reserved += credit_upper
        started, tick = self.clock(), time.monotonic()
        status, headers, raw, error = None, {}, b"", None
        try:
            status, headers, raw = self.transport(url, self.config["timeout_seconds"])
        except (URLError, OSError, TimeoutError) as exc:
            error = type(exc).__name__  # exception text can contain the key
        ended, elapsed = self.clock(), time.monotonic() - tick
        normalized = {key.lower(): str(value) for key, value in headers.items()}
        headers = {key: normalized[key] for key in SAFE_HEADERS if key in normalized}
        name = f"{self.requests:06d}-{uuid4().hex}.body"
        raw_path = self.raw_dir / name
        raw_path.write_bytes(raw)
        value = None
        if error is None:
            try:
                value = json.loads(raw)
            except (ValueError, UnicodeError):
                error = "invalid_json"
        if status is not None and not 200 <= status < 300:
            error = f"http_{status}"
        try:
            clocks = source_clocks(value, provider)
        except (AttributeError, TypeError):
            clocks = {}
            error = error or "unexpected_schema"
        if provider == "the_odds_api":
            try:
                self.credits_reported += max(0, int(headers.get("x-requests-last", "0")))
                if "x-requests-remaining" in headers:
                    self.provider_credits_remaining = int(headers["x-requests-remaining"])
            except ValueError:
                pass
        self.record("response", provider=provider, source_url=public_url,
                    context=context or {}, synthetic=self.synthetic,
                    collector_request_started_at=started, collector_response_received_at=ended,
                    elapsed_seconds=elapsed, provider_http_date=headers.get("date"),
                    response_headers=headers, status=status, error=error,
                    raw_file=str(raw_path.relative_to(self.output)), raw_bytes=len(raw),
                    raw_sha256=hashlib.sha256(raw).hexdigest(), clocks=clocks,
                    credits_reserved_for_request=credit_upper)
        if error:
            self.failures += 1
            # All failures stop this bounded run. Never repeatedly poll a denial.
            raise StopCollection(error)
        if provider == "the_odds_api" and path.endswith("/odds"):
            self.odds_responses += 1
        if provider == "mlb_statsapi" and path.endswith("/feed/live"):
            self.mlb_feed_responses += 1
        return value

    def collect_odds(self, cycle):
        sports = self.config["sports"]
        if sports == ["*"]:
            listing = self.fetch("the_odds_api", "/v4/sports")
            if not isinstance(listing, list):
                raise StopCollection("sports_schema: expected list")
            # Futures-only sport keys do not fit this game-by-game collector.
            sports = [sport["key"] for sport in listing
                      if sport.get("active") and not sport.get("has_outrights")]
            self.record("sports_selection", cycle=cycle, selected=sports,
                        omitted_outright_sports=[sport["key"] for sport in listing
                                                if sport.get("active") and sport.get("has_outrights")])
        events = []
        # Discover all chosen sports before spending market credits. No time or
        # live-status filter: events endpoint includes pregame and in-play events.
        for sport in sports:
            listing = self.fetch("the_odds_api", f"/v4/sports/{quote(sport, safe='')}/events")
            if not isinstance(listing, list):
                raise StopCollection("events_schema: expected list")
            events.extend((sport, event["id"]) for event in listing)
        # A small cap must not always give the first sport all available credits.
        # The run id and cycle reproduce this acquisition order; odds stay raw.
        random.Random(f"{self.run_id}:{cycle}").shuffle(events)
        self.record("cycle_inventory", cycle=cycle, sports=sports,
                    events_discovered=len(events), bookmakers=list(BOOKMAKERS),
                    event_order=events, order_seed=f"{self.run_id}:{cycle}")
        for sport, event_id in events:
            prefix = f"/v4/sports/{quote(sport, safe='')}/events/{quote(event_id, safe='')}"
            params = {"bookmakers": ",".join(BOOKMAKERS), "dateFormat": "iso"}
            context = {"cycle": cycle, "sport": sport, "event_id": event_id}
            markets = self.fetch("the_odds_api", prefix + "/markets", params,
                                 credit_upper=1, context=context)
            if not isinstance(markets, dict) or "bookmakers" not in markets:
                raise StopCollection("markets_schema: expected bookmakers")
            keys = sorted({market["key"] for book in markets["bookmakers"]
                           if book["key"] in BOOKMAKERS for market in book["markets"]})
            self.record("market_inventory", **context, market_keys=keys,
                        coverage="recently seen provider markets; not full sportsbook coverage")
            width = self.config["market_batch_size"]
            for offset in range(0, len(keys), width):
                batch = keys[offset:offset + width]
                self.fetch("the_odds_api", prefix + "/odds",
                           {**params, "markets": ",".join(batch), "oddsFormat": "decimal",
                            "includeSids": "true", "includeLinks": "true"},
                           credit_upper=len(batch), context={**context, "markets_requested": batch})

    def collect_mlb(self, cycle):
        # Include yesterday for late US games across UTC midnight.
        from datetime import timedelta
        today = datetime.fromisoformat(self.clock()).date()
        schedule = self.fetch("mlb_statsapi", "/api/v1/schedule",
                              {"sportId": 1, "startDate": str(today - timedelta(days=1)),
                               "endDate": str(today)})
        if not isinstance(schedule, dict) or "dates" not in schedule:
            raise StopCollection("mlb_schedule_schema")
        games = {game["gamePk"] for day in schedule["dates"] for game in day["games"]
                 if game.get("status", {}).get("abstractGameState") != "Final"}
        self.record("mlb_inventory", cycle=cycle, game_pks=sorted(games), join_status="unmapped")
        for game_pk in sorted(games):
            self.fetch("mlb_statsapi", f"/api/v1.1/game/{game_pk}/feed/live",
                       context={"cycle": cycle, "game_pk": game_pk, "odds_event_id": None})

    def run(self, *, mlb_only=False, sleep=time.sleep):
        reason = "cycles_complete"
        try:
            for cycle in range(1, self.config["cycles"] + 1):
                if mlb_only or self.config["mlb_game_state"]:
                    self.collect_mlb(cycle)
                if not mlb_only:
                    self.collect_odds(cycle)
                self.completed_cycles += 1
                if cycle < self.config["cycles"]:
                    sleep(self.config["interval_seconds"])
        except StopCollection as error:
            reason = str(error)
        except (KeyError, TypeError, AttributeError) as error:
            reason = f"unexpected_schema:{type(error).__name__}"
        except KeyboardInterrupt:
            reason = "interrupted"
        summary = self.record("run_end", stop_reason=reason,
                              synthetic=self.synthetic, started_at=self.started_at,
                              requests=self.requests, credit_upper_reserved=self.credits_reserved,
                              credits_reported=self.credits_reported,
                              provider_credits_remaining=self.provider_credits_remaining,
                              cycles_completed=self.completed_cycles, failures=self.failures,
                              odds_responses=self.odds_responses,
                              mlb_feed_responses=self.mlb_feed_responses,
                              real_odds_responses=0 if self.synthetic else self.odds_responses,
                              alerts_enabled=False, wagers_enabled=False)
        (self.output / self.run_id / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sports", help="Comma-separated provider sport keys, or *")
    parser.add_argument("--cycles", type=int)
    parser.add_argument("--interval-seconds", type=float)
    parser.add_argument("--max-credits", type=int)
    parser.add_argument("--max-requests", type=int)
    parser.add_argument("--mlb-game-state", action="store_true")
    parser.add_argument("--mlb-only", action="store_true", help="Official game state only; no odds key needed")
    parser.add_argument("--demo", action="store_true", help="Synthetic offline demonstration; zero network requests")
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text()) if args.config else {}
    if not isinstance(config, dict) or set(config) - set(DEFAULTS):
        parser.error("config must be an object containing only documented configuration keys")
    for key in ("cycles", "interval_seconds", "max_credits", "max_requests"):
        value = getattr(args, key)
        if value is not None:
            config[key] = value
    if args.sports:
        config["sports"] = args.sports.split(",")
    if args.mlb_game_state:
        config["mlb_game_state"] = True
    transport = http_get
    if args.demo:
        from beating.forward_collect_demo import demo_get
        transport = demo_get
        config["sports"] = ["baseball_mlb"]
        config["mlb_game_state"] = True
        config["cycles"] = 1
    elif not args.mlb_only and not os.environ.get("ODDS_API_KEY"):
        parser.error("ODDS_API_KEY is absent; no live odds collected. Use --demo for synthetic data or --mlb-only.")
    output = args.output or Path("data/raw/forward-demo" if args.demo else "data/raw/forward-markets")
    try:
        collector = Collector(output, config, api_key=os.environ.get("ODDS_API_KEY"),
                              transport=transport, synthetic=args.demo)
    except ValueError as error:
        parser.error(str(error))
    summary = collector.run(mlb_only=args.mlb_only)
    print(json.dumps(summary, indent=2))
    return 0 if summary["stop_reason"] == "cycles_complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
