"""Finite, polite golf raw capture for exploration; no paper ledger or bets.

PGA operations follow pgatouR commit 74551e5bebc9e189781d75a88d57c68c87ec4860.
The PGA key below is that project's documented public frontend key, not an
account credential. The optional PGA_API_KEY environment override is never
written into request metadata. See docs/golf-collection.md for source limits.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import fcntl
import gzip
import hashlib
from html.parser import HTMLParser
import io
import json
import math
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4


HOSTS = {
    "pga_html": "https://www.pgatour.com",
    "pga_config": "https://orchestrator-config.pgatour.com",
    "pga_rest": "https://data-api.pgatour.com",
    "pga_graphql": "https://orchestrator.pgatour.com",
    "espn": "https://site.api.espn.com",
}
PUBLIC_PGA_KEY = "da2-gsrx5bibzbb4njvhl7t37wqyl4"
DEFAULTS = {
    "pga_pages": [], "api_enabled": False,
    "tournament_ids": [], "tours": ["R"], "cycles": 1,
    "interval_seconds": 300, "request_interval_seconds": 2,
    "max_requests": 240, "max_seconds": 1800, "timeout_seconds": 30,
    "max_tournaments": 3, "max_players_per_tournament": 180,
    "player_odds": True, "espn_state": False, "espn_dates": None,
}
SAFE_HEADERS = ("date", "content-type", "last-modified", "retry-after", "age",
                "cache-control", "etag")
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
PGA_TOURNAMENT_ID = re.compile(r"[RSHY]\d{7}\Z")


class NextDataParser(HTMLParser):
    """Read the public page's server-rendered state without executing scripts."""
    def __init__(self):
        super().__init__()
        self.in_state = False
        self.fragments = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("id") == "__NEXT_DATA__":
            self.in_state = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_state = False

    def handle_data(self, data):
        if self.in_state:
            self.fragments.append(data)


def parse_pga_html(raw):
    parser = NextDataParser()
    parser.feed(raw.decode("utf-8"))
    if not parser.fragments:
        raise ValueError("missing_public_page_state")
    return json.loads("".join(parser.fragments))

# Small selections of fields from the public client's observed GraphQL schema.
QUERIES = {
    "Tournaments": """query Tournaments($ids: [ID!]) {
      tournaments(ids: $ids) { id tournamentName tournamentLocation
        tournamentStatus currentRound timezone seasonYear displayDate formatType
        country state city features
        events { id eventName leaderboardId }
        courses { id courseName courseCode hostCourse scoringLevel } }
    }""",
    "Field": """query Field($fieldId: ID!, $includeWithdrawn: Boolean) {
      field(id: $fieldId, includeWithdrawn: $includeWithdrawn) {
        id tournamentName lastUpdated message
        players { id firstName lastName displayName amateur qualifier alternate
          withdrawn status owgr rankingPoints }
        alternates { id firstName lastName displayName amateur qualifier alternate
          withdrawn status owgr rankingPoints } }
    }""",
    "LeaderboardCompressedV3": """query LeaderboardCompressedV3($leaderboardCompressedV3Id: ID!) {
      leaderboardCompressedV3(id: $leaderboardCompressedV3Id) { id payload }
    }""",
    "TeeTimesCompressedV2": """query TeeTimesCompressedV2($teeTimesCompressedV2Id: ID!) {
      teeTimesCompressedV2(id: $teeTimesCompressedV2Id) { id payload }
    }""",
    "oddsToWinCompressed": """query oddsToWinCompressed($tournamentId: ID!) {
      oddsToWinCompressed(oddsToWinId: $tournamentId) { id payload }
    }""",
    "Weather": """query Weather($tournamentId: ID!) {
      weather(tournamentId: $tournamentId) { title accessibilityText
        hourly { title condition windDirection windSpeedKPH windSpeedMPH humidity
          precipitation temperature { ... on StandardWeatherTemp { tempC tempF }
            ... on RangeWeatherTemp { minTempC minTempF maxTempC maxTempF } } }
        daily { title condition windDirection windSpeedKPH windSpeedMPH humidity
          precipitation temperature { ... on StandardWeatherTemp { tempC tempF }
            ... on RangeWeatherTemp { minTempC minTempF maxTempC maxTempF } } } }
    }""",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


class StopCollection(Exception):
    """A session's request or elapsed-time cap has been reached."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_request(method, url, body, headers, timeout):
    """One ordinary request. No redirects, retries, cookies or browser disguise."""
    request = Request(url, data=body, method=method, headers=headers)
    opener = build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        return error.code, dict(error.headers), error.read(MAX_RESPONSE_BYTES + 1)


def decode_payloads(value):
    """Expand the public API's base64+gzip payloads; the wire bytes stay intact."""
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            if key == "payload" and isinstance(child, str) and child:
                packed = base64.b64decode(child, validate=True)
                with gzip.GzipFile(fileobj=io.BytesIO(packed)) as stream:
                    expanded = stream.read(MAX_RESPONSE_BYTES + 1)
                if len(expanded) > MAX_RESPONSE_BYTES:
                    raise ValueError("decoded_payload_too_large")
                result[key] = json.loads(expanded)
            else:
                result[key] = decode_payloads(child)
        return result
    if isinstance(value, list):
        return [decode_payloads(child) for child in value]
    return value


def walk(value, path="$", inherited_books=()):
    if isinstance(value, dict):
        books = []
        book_declared = False
        for key, child in value.items():
            if re.sub(r"[^a-z]", "", key.lower()) in {"book", "bookmaker", "sportsbook"}:
                book_declared = True
                if isinstance(child, str) and child.strip():
                    books.append(child)
                elif isinstance(child, dict):
                    books.extend(str(child[k]) for k in ("key", "name", "title")
                                 if isinstance(child.get(k), (str, int)))
        books = tuple(dict.fromkeys(books)) if book_declared else inherited_books
        for key, child in value.items():
            child_path = f"{path}.{key}"
            yield child_path, key, child, books, value
            yield from walk(child, child_path, books)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, f"{path}[{index}]", inherited_books)


def fanduel_selection_link(price_object, price_path, books):
    """Recognize the observed REST schema's selection URL in this object only.

    A selection link is separate evidence from publisher book declarations.
    We never follow the link or infer it from a parent, sibling or catalog.
    """
    url = price_object.get("url")
    if not isinstance(url, str) or re.search(r"\s|[\x00-\x1f\x7f]", url):
        return None
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname != "account.sportsbook.fanduel.com"
                or parsed.port not in (None, 443) or parsed.username is not None
                or parsed.password is not None or parsed.fragment
                or parsed.path != "/sportsbook/addToBetslip"):
            return None
        query = parse_qs(parsed.query, keep_blank_values=True)
    except ValueError:
        return None
    market, selection = query.get("marketId", []), query.get("selectionId", [])
    if (len(market) != 1 or len(selection) != 1
            or re.fullmatch(r"[1-9][0-9]*\.[0-9]+", market[0]) is None
            or re.fullmatch(r"[1-9][0-9]*", selection[0]) is None):
        return None
    status = "attributed"
    for key, child in price_object.items():
        normalized = re.sub(r"[^a-z]", "", key.lower())
        if normalized in {"marketid", "optionid"} and str(child) != market[0]:
            status = "market_id_mismatch"
        if normalized == "selectionid" and str(child) != selection[0]:
            status = "selection_id_mismatch"
    if any(re.sub(r"[^a-z]", "", book.lower()) != "fanduel" for book in books):
        status = "conflicting_book_labels"
    return {"path": price_path.rsplit(".", 1)[0] + ".url", "url": url,
            "market_id": market[0], "selection_id": selection[0], "status": status}


def payload_inventory(value, *, odds=False):
    """Index clocks, explicit book labels and direct selection-link evidence.

    An event time is not an update time; HTTP Date is not a bookmaker clock.
    Quote observations are raw price fields, not unique markets or bet records.
    """
    clocks, labels, quotes, unvalidated = [], [], [], []
    update_keys = {"timestamp", "lastupdated", "lastupdate", "updatedat", "updated",
                   "updatetime", "lastmodified", "generatedat", "issuedat", "issuetime"}
    event_keys = {"teetime", "starttime", "endtime", "date", "startdate", "enddate",
                  "displaydate", "forecasttime", "validtime"}
    for path, key, child, books, parent in walk(value):
        normalized = re.sub(r"[^a-z]", "", key.lower())
        if normalized == "dataupdatedat" and isinstance(child, (str, int, float)):
            clocks.append({"path": path, "value": child, "kind": "page_cache_update"})
        if normalized in update_keys | event_keys and isinstance(child, (str, int, float)):
            clocks.append({"path": path, "value": child,
                           "kind": "source_update" if normalized in update_keys else "event_or_forecast"})
        if normalized in {"book", "bookmaker", "sportsbook"} and child is not None:
            labels.append({"path": path, "value": child})
        if odds and normalized in {"oddsvalue", "americanodds", "decimalodds", "odds"}:
            # Empty data and a marketing/book-partner label are never quotes.
            text = str(child).strip()
            if not isinstance(child, bool) and re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
                number = float(text)
                valid = math.isfinite(number) and (
                    normalized == "decimalodds" and number > 1
                    or normalized == "americanodds" and abs(number) >= 100 and number.is_integer()
                    or normalized == "oddsvalue" and text.startswith(("+", "-"))
                    and abs(number) >= 100 and number.is_integer())
                observation = {"path": path, "value": child, "book_labels": list(books)}
                if valid:
                    link = fanduel_selection_link(parent, path, books)
                    if link is not None:
                        observation["fanduel_selection_link"] = link
                    quotes.append(observation)
                else:
                    unvalidated.append({**observation, "reason": "ambiguous_format_or_invalid_price"})
    return {"source_clocks": clocks, "book_labels": labels,
            "quote_observations": quotes,
            "unvalidated_price_fields": unvalidated,
            "quote_status": ("price_fields_observed" if quotes else "no_quotes") if odds else "not_an_odds_request"}


def player_ids(value):
    ids = set()
    for _, key, child, _, _ in walk(value):
        if key in {"players", "alternates"} and isinstance(child, list):
            for item in child:
                if isinstance(item, dict):
                    player = item.get("player", item)
                    identifier = player.get("id", player.get("playerId")) if isinstance(player, dict) else None
                    if str(identifier).isdigit():
                        ids.add(str(identifier))
    return sorted(ids, key=int)


def retry_not_before(headers, received_at):
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        seconds = float(value)
        if not math.isfinite(seconds) or seconds < 0:
            return None
        return (datetime.fromisoformat(received_at) + timedelta(seconds=seconds)).isoformat()
    except (ValueError, OverflowError):
        try:
            return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            return None


class Collector:
    def __init__(self, output, config=None, *, transport=http_request,
                 clock=utc_now, monotonic=time.monotonic, sleep=time.sleep, api_key=None):
        config = {} if config is None else config
        if not isinstance(config, dict) or set(config) - set(DEFAULTS):
            raise ValueError("configuration contains unknown keys or is not an object")
        self.config = {**DEFAULTS, **config}
        bounds = {"cycles": (1, 288), "max_requests": (1, 5000),
                  "max_tournaments": (1, 10), "max_players_per_tournament": (0, 200)}
        for key, (minimum, maximum) in bounds.items():
            if type(self.config[key]) is not int or not minimum <= self.config[key] <= maximum:
                raise ValueError(f"{key} must be an integer in [{minimum}, {maximum}]")
        bounds = {"interval_seconds": (60, 86400), "request_interval_seconds": (1, 60),
                  "max_seconds": (1, 86400), "timeout_seconds": (1, 60)}
        for key, (minimum, maximum) in bounds.items():
            number = self.config[key]
            if (isinstance(number, bool) or not isinstance(number, (int, float))
                    or not math.isfinite(number) or not minimum <= number <= maximum):
                raise ValueError(f"{key} must be finite and in [{minimum}, {maximum}]")
        for key in ("player_odds", "espn_state", "api_enabled"):
            if type(self.config[key]) is not bool:
                raise ValueError(f"{key} must be a boolean")
        ids, tours = self.config["tournament_ids"], self.config["tours"]
        if not isinstance(ids, list) or any(not isinstance(x, str) or not PGA_TOURNAMENT_ID.fullmatch(x) for x in ids):
            raise ValueError("tournament_ids must contain observed IDs such as R2026027")
        if not isinstance(tours, list) or not tours or any(x not in {"R", "S", "H", "Y"} for x in tours):
            raise ValueError("tours must contain R, S, H or Y")
        dates = self.config["espn_dates"]
        if dates is not None and (not isinstance(dates, str) or not re.fullmatch(r"\d{8}(?:-\d{8})?", dates)):
            raise ValueError("espn_dates must be YYYYMMDD or YYYYMMDD-YYYYMMDD")
        pages = self.config["pga_pages"]
        if not isinstance(pages, list) or len(pages) > 30:
            raise ValueError("pga_pages must be a list of at most 30 observed public PGA URLs")
        for page in pages:
            parts = urlsplit(page) if isinstance(page, str) else None
            if (parts is None or parts.scheme != "https" or parts.netloc != "www.pgatour.com"
                    or parts.query or parts.fragment or not re.fullmatch(
                        r"/tournaments/\d{4}/[a-z0-9-]+/[RSHY]\d{7}/(?:odds|tee-times|leaderboard|field)", parts.path)):
                raise ValueError("pga_pages require observed https://www.pgatour.com tournament tab URLs")
        if not self.config["api_enabled"] and not pages and not self.config["espn_state"]:
            raise ValueError("at least one public page, PGA API or ESPN state source must be enabled")
        self.output = Path(output)
        self.run_id = uuid4().hex
        self.raw_dir = self.output / self.run_id / "raw"
        self.raw_dir.mkdir(parents=True)
        self.transport, self.clock, self.monotonic, self.sleep = transport, clock, monotonic, sleep
        self.api_key = api_key or os.environ.get("PGA_API_KEY") or PUBLIC_PGA_KEY
        self.requests = self.failures = self.completed_cycles = 0
        self.price_fields = self.fanduel_price_fields = self.odds_responses = self.unvalidated_price_fields = 0
        self.fanduel_selection_link_price_fields = 0
        self.disabled_sources, self.disabled_operations = {}, set()
        self.active_sources = ({"pga_html"} if pages else set()) | ({"espn"} if self.config["espn_state"] else set())
        if self.config["api_enabled"]:
            self.active_sources.update({"pga_rest", "pga_graphql"})
            if not self.config["tournament_ids"]:
                self.active_sources.add("pga_config")
        self.started_at, self.started_tick = self.clock(), self.monotonic()
        self.last_request_tick = None
        self.record("run_start", config=self.config, exploratory_only=True,
                    pga_query_source_commit="74551e5bebc9e189781d75a88d57c68c87ec4860")

    def record(self, kind, **fields):
        row = {"kind": kind, "run_id": self.run_id, "recorded_at": self.clock(), **fields}
        with (self.output / "index.jsonl").open("ab") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.write(json_bytes(row))
            stream.flush()
            fcntl.flock(stream, fcntl.LOCK_UN)
        return row

    def save(self, name, raw):
        path = self.raw_dir / name
        with path.open("xb") as stream:
            stream.write(raw)
        return {"file": str(path.relative_to(self.output)), "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest()}

    def check_caps(self):
        if self.requests >= self.config["max_requests"]:
            raise StopCollection("request_cap")
        if self.monotonic() - self.started_tick >= self.config["max_seconds"]:
            raise StopCollection("elapsed_time_cap")

    def pause(self, seconds):
        if self.monotonic() - self.started_tick + seconds >= self.config["max_seconds"]:
            raise StopCollection("elapsed_time_cap")
        self.sleep(seconds)

    def fetch(self, provider, path, *, operation=None, variables=None, params=None,
              context=None, odds=False):
        if provider in self.disabled_sources or operation in self.disabled_operations:
            self.record("request_skipped", provider=provider, operation=operation,
                        context=context or {}, reason=self.disabled_sources.get(provider, "operation_disabled"))
            return None
        self.check_caps()
        if self.last_request_tick is not None:
            remaining = self.config["request_interval_seconds"] - (self.monotonic() - self.last_request_tick)
            if remaining > 0:
                self.pause(remaining)
        self.check_caps()
        url = HOSTS[provider] + path + ("?" + urlencode(params) if params else "")
        headers = {"User-Agent": "BeatingAnything-golf-research/0.1",
                   "Accept": "application/json"}
        body, method = None, "GET"
        if operation:
            body = json_bytes({"operationName": operation, "query": QUERIES[operation],
                               "variables": variables or {}})
            method = "POST"
            headers.update({"Content-Type": "application/json", "x-api-key": self.api_key,
                            "x-pgat-platform": "web", "Origin": "https://www.pgatour.com",
                            "Referer": "https://www.pgatour.com/"})
        self.requests += 1
        number = f"{self.requests:06d}"
        request = self.save(number + ".request.json", json_bytes({
            "method": method, "url": url, "operation": operation,
            "headers": {key: value for key, value in headers.items() if key != "x-api-key"},
            "public_frontend_key_supplied": bool(operation),
            "body": json.loads(body) if body else None,
        }))
        started, tick = self.clock(), self.monotonic()
        self.last_request_tick = tick
        timeout = min(self.config["timeout_seconds"], self.config["max_seconds"] - (tick - self.started_tick))
        if timeout <= 0:
            raise StopCollection("elapsed_time_cap")
        status, response_headers, raw, error = None, {}, b"", None
        try:
            status, response_headers, raw = self.transport(method, url, body, headers, timeout)
        except (URLError, OSError, TimeoutError) as exc:
            error = type(exc).__name__  # Exception text can leak a URL or credentials.
        received, elapsed = self.clock(), self.monotonic() - tick
        response = self.save(number + ".body", raw)
        normalized = {key.lower(): str(value) for key, value in response_headers.items()}
        response_headers = {key: normalized[key] for key in SAFE_HEADERS if key in normalized}
        parsed, decoded, decoded_file = None, None, None
        if len(raw) > MAX_RESPONSE_BYTES:
            error = "response_size_cap_truncated"
        if error is None:
            try:
                parsed = parse_pga_html(raw) if provider == "pga_html" else json.loads(raw)
                decoded = decode_payloads(parsed) if operation else parsed
                if operation or provider == "pga_html":
                    decoded_file = self.save(number + ".decoded.json", json_bytes(decoded))
            except (ValueError, UnicodeError, OSError, EOFError, RecursionError):
                error = "invalid_json_or_compressed_payload"
        if status is not None and not 200 <= status < 300:
            error = f"http_{status}"
        graphql_errors = parsed.get("errors") if isinstance(parsed, dict) else None
        if graphql_errors:
            error = error or "graphql_errors"
        inventory = payload_inventory(decoded, odds=odds)
        if error and odds:
            inventory["quote_status"] = "request_failed"
            inventory["quote_observations"] = []
        self.record("response", provider=provider, operation=operation, source_url=url,
                    context=context or {}, request=request, response=response,
                    decoded=decoded_file, status=status, error=error,
                    collector_request_started_at=started, collector_response_received_at=received,
                    elapsed_seconds=elapsed, timeout_seconds=timeout,
                    provider_http_date=response_headers.get("date"),
                    response_headers=response_headers, **inventory)
        if provider == "pga_html" and isinstance(decoded, dict):
            queries = decoded.get("props", {}).get("pageProps", {}).get("dehydratedState", {}).get("queries", [])
            self.record("public_page_inventory", source_url=url, context=context or {},
                        queries=[{"query_key": query.get("queryKey"),
                                  "page_cache_updated_at": query.get("state", {}).get("dataUpdatedAt"),
                                  "data_present": query.get("state", {}).get("data") is not None}
                                 for query in queries if isinstance(query, dict)],
                        book_attribution="explicit book fields from price ancestors and separate direct selection-link evidence; generic partner links are configuration only")
        if error:
            self.failures += 1
            # Retry-After is recorded, but a 429 always disables this source for
            # the rest of the run. No next cycle can probe a denial again.
            if error == "graphql_errors" and not any(
                    token in json.dumps(graphql_errors).lower()
                    for token in ("unauthoriz", "forbidden", "access denied", "rate limit", "captcha")):
                self.disabled_operations.add(operation)
            else:
                self.disabled_sources[provider] = error
                self.record("source_disabled", provider=provider, reason=error,
                            retry_not_before=retry_not_before(response_headers, received),
                            retry_policy="no further requests to this source in this run")
            if self.monotonic() - self.started_tick >= self.config["max_seconds"]:
                raise StopCollection("elapsed_time_cap")
            return None
        if odds:
            self.odds_responses += 1
            self.price_fields += len(inventory["quote_observations"])
            self.unvalidated_price_fields += len(inventory["unvalidated_price_fields"])
            self.fanduel_price_fields += sum(
                bool(quote["book_labels"]) and all(
                    re.sub(r"[^a-z]", "", book.lower()) == "fanduel" for book in quote["book_labels"])
                for quote in inventory["quote_observations"])
            self.fanduel_selection_link_price_fields += sum(
                quote.get("fanduel_selection_link", {}).get("status") == "attributed"
                for quote in inventory["quote_observations"])
        if self.monotonic() - self.started_tick >= self.config["max_seconds"]:
            raise StopCollection("elapsed_time_cap")
        return decoded

    def graphql(self, operation, variables, context, *, odds=False):
        return self.fetch("pga_graphql", "/graphql", operation=operation,
                          variables=variables, context=context, odds=odds)

    def collect_cycle(self, cycle):
        for page in self.config["pga_pages"]:
            self.fetch("pga_html", urlsplit(page).path,
                       context={"cycle": cycle, "role": "public_tournament_page"},
                       odds=page.endswith("/odds"))
        selected = list(dict.fromkeys(self.config["tournament_ids"]))
        if self.config["api_enabled"] and not selected:
            config = self.fetch("pga_config", "/web-config", context={"cycle": cycle})
            defaults = config.get("defaultTournaments", {}) if isinstance(config, dict) else {}
            for tour in self.config["tours"]:
                for item in defaults.get(tour, []) or []:
                    identifier = item.get("id") if isinstance(item, dict) else None
                    if isinstance(identifier, str) and PGA_TOURNAMENT_ID.fullmatch(identifier):
                        selected.append(identifier)
        selected = list(dict.fromkeys(selected))
        chosen = selected[:self.config["max_tournaments"]]
        self.record("tournament_inventory", cycle=cycle, selected=chosen,
                    omitted_by_cap=selected[len(chosen):],
                    selection="explicit" if self.config["tournament_ids"] else "provider_default_tournaments")
        if self.config["espn_state"]:
            self.fetch("espn", "/apis/site/v2/sports/golf/pga/scoreboard",
                       params={"dates": self.config["espn_dates"]} if self.config["espn_dates"] else None,
                       context={"cycle": cycle, "role": "independent_golf_state", "pga_id_join": "unmapped"})
        if not self.config["api_enabled"]:
            return
        self.fetch("pga_rest", "/odds/interactivity", context={"cycle": cycle, "role": "partner_config_only"})
        for tournament in chosen:
            context = {"cycle": cycle, "tournament_id": tournament}
            catalog = self.fetch("pga_rest", f"/odds/tournament/{tournament}", context=context, odds=True)
            self.graphql("Tournaments", {"ids": [tournament]}, context)
            field = self.graphql("Field", {"fieldId": tournament, "includeWithdrawn": True}, context)
            board = self.graphql("LeaderboardCompressedV3", {"leaderboardCompressedV3Id": tournament}, context)
            tees = self.graphql("TeeTimesCompressedV2", {"teeTimesCompressedV2Id": tournament}, context)
            outright = self.graphql("oddsToWinCompressed", {"tournamentId": tournament}, context, odds=True)
            self.graphql("Weather", {"tournamentId": tournament}, context)
            if self.config["player_odds"]:
                if not isinstance(catalog, dict) or not catalog.get("availableMarkets"):
                    self.record("player_odds_inventory", **context, player_ids=[], omitted_by_cap=[],
                                reason="no_available_markets" if isinstance(catalog, dict) else "catalog_unavailable")
                    continue
                players = sorted(set(player_ids(field) + player_ids(board) + player_ids(tees) + player_ids(outright)), key=int)
                allowed = players[:self.config["max_players_per_tournament"]]
                self.record("player_odds_inventory", **context, player_ids=allowed,
                            omitted_by_cap=players[len(allowed):],
                            coverage="per-player markets exposed by PGA provider; not complete sportsbook board")
                for player in allowed:
                    self.fetch("pga_rest", f"/odds/tournament/{tournament}/player/{player}",
                               context={**context, "player_id": player}, odds=True)

    def run(self):
        reason = "cycles_complete"
        try:
            for cycle in range(1, self.config["cycles"] + 1):
                self.check_caps()
                self.collect_cycle(cycle)
                self.completed_cycles += 1
                if cycle < self.config["cycles"]:
                    if self.active_sources <= set(self.disabled_sources):
                        reason = "all_sources_disabled"
                        break
                    self.pause(self.config["interval_seconds"])
        except StopCollection as exc:
            reason = str(exc)
        except KeyboardInterrupt:
            reason = "interrupted"
        except (KeyError, TypeError, AttributeError) as exc:
            reason = "unexpected_schema:" + type(exc).__name__
        summary = self.record("run_end", stop_reason=reason, requests=self.requests,
                              cycles_completed=self.completed_cycles, failures=self.failures,
                              started_at=self.started_at, disabled_sources=self.disabled_sources,
                              disabled_operations=sorted(self.disabled_operations),
                              successful_odds_responses=self.odds_responses,
                              price_field_observations=self.price_fields,
                              unvalidated_price_field_observations=self.unvalidated_price_fields,
                              explicitly_fanduel_price_field_observations=self.fanduel_price_fields,
                              fanduel_selection_link_price_field_observations=self.fanduel_selection_link_price_fields,
                              quote_status="price_fields_observed" if self.price_fields else "no_quotes",
                              exploratory_only=True, ledger_entries_created=0,
                              alerts_enabled=False, wagers_enabled=False)
        with (self.output / self.run_id / "summary.json").open("xb") as stream:
            stream.write(json_bytes(summary))
        return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/raw/golf-forward"))
    parser.add_argument("--tournaments", help="Comma-separated observed PGA tournament IDs; omit to discover")
    parser.add_argument("--cycles", type=int)
    parser.add_argument("--max-requests", type=int)
    parser.add_argument("--max-seconds", type=float)
    parser.add_argument("--interval-seconds", type=float)
    parser.add_argument("--max-players-per-tournament", type=int)
    parser.add_argument("--espn-dates", help="YYYYMMDD or YYYYMMDD-YYYYMMDD")
    parser.add_argument("--no-player-odds", action="store_true")
    parser.add_argument("--api", action="store_true", help="Opt into the public client's PGA REST/GraphQL sources")
    args = parser.parse_args(argv)
    try:
        config = json.loads(args.config.read_text()) if args.config else {}
        if not isinstance(config, dict):
            raise ValueError("configuration must be an object")
        for key in ("cycles", "max_requests", "max_seconds", "interval_seconds", "max_players_per_tournament", "espn_dates"):
            if getattr(args, key) is not None:
                config[key] = getattr(args, key)
        if args.tournaments is not None:
            config["tournament_ids"] = args.tournaments.split(",")
        if args.no_player_odds:
            config["player_odds"] = False
        if args.api:
            config["api_enabled"] = True
        collector = Collector(args.output, config)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    summary = collector.run()
    print(json.dumps(summary, indent=2))
    return 0 if summary["stop_reason"] == "cycles_complete" and not summary["failures"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
