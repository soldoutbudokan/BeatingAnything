#!/usr/bin/env python3
"""Bounded OddsPapi coverage probe. No forecasts, wagers or scheduled requests."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://api.oddspapi.io/v4/"
MAX_BYTES = 32 * 1024 * 1024
PLAN = {"provider": "OddsPapi", "from": "2026-03-02T00:00:00Z", "to": "2026-03-05T00:00:00Z",
        "sport_id": 11, "fixture_selection": "first three NBA fixtures ordered by start and ID, without outcome or price filtering",
        "max_fixtures": 3, "max_requests": 6, "max_documented_quota_requests": 3,
        "bookmakers": ["fanduel", "betmgm"], "history_cooldown_seconds": 5.1,
        "purpose": "Source coverage only; catalog inclusion does not establish actual first-basket prices or settlement equivalence"}


def stamp():
    return datetime.now(timezone.utc).isoformat()


def dump(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + "\n")


def zoned(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Unzoned clock")
    return parsed


class ProbeStopped(Exception):
    """Messages are controlled constants; never include credential-bearing URLs."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, key, output, opener=None, wait=time.sleep):
        if not key.strip():
            raise ProbeStopped("Missing API key; no requests made")
        self.key, self.output = key.strip(), output
        self.opener = opener or urllib.request.build_opener(NoRedirect())
        self.wait, self.calls, self.last_history = wait, 0, None

    def get(self, endpoint, params):
        if endpoint not in ("bookmakers", "markets", "fixtures", "historical-odds") or self.calls >= PLAN["max_requests"]:
            raise ProbeStopped("Endpoint or request budget exceeded")
        if any("key" in k.lower() for k in params):
            raise ProbeStopped("Credential must only come from private key input")
        if endpoint == "historical-odds" and self.last_history is not None:
            delay = PLAN["history_cooldown_seconds"] - (time.monotonic() - self.last_history)
            if delay > 0:
                self.wait(delay)
        if endpoint == "historical-odds":
            self.last_history = time.monotonic()
        self.calls += 1
        public_url = BASE + endpoint + "?" + urllib.parse.urlencode(params)
        url = BASE + endpoint + "?" + urllib.parse.urlencode({**params, "apiKey": self.key})
        request = urllib.request.Request(url, headers={"User-Agent": "BeatingAnything-source-probe", "Accept": "application/json"})
        received_headers = {}
        started = stamp()
        try:
            with self.opener.open(request, timeout=30) as response:
                status = response.status
                body = response.read(MAX_BYTES + 1)
                received_headers = {k: response.headers[k] for k in ("Date", "Content-Type", "ETag") if k in response.headers}
        except urllib.error.HTTPError as error:
            status, body = error.code, error.read(MAX_BYTES + 1)
        except Exception as error:
            dump(self.output / f"{self.calls:02d}-{endpoint}.meta.json", {
                "url_without_credential": public_url, "started_at": started, "received_at": stamp(),
                "transport_failure_type": type(error).__name__})
            raise ProbeStopped("Transport failed; no retry performed") from None
        meta = {"url_without_credential": public_url, "started_at": started, "received_at": stamp(),
                "status": status, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(), "headers": received_headers}
        sensitive_forms = (self.key, urllib.parse.quote(self.key, safe=""), urllib.parse.quote_plus(self.key),
                           json.dumps(self.key)[1:-1])
        secret_in_body = any(value.encode() in body for value in sensitive_forms)
        secret_in_headers = any(value in json.dumps(received_headers) for value in sensitive_forms)
        if secret_in_headers:
            meta["headers"] = {"omitted": "credential_echo"}
        oversized = len(body) > MAX_BYTES
        meta["body_retained"] = not secret_in_body and not oversized
        if not meta["body_retained"]:
            meta["body_omission_reason"] = "credential_echo" if secret_in_body else "response_size_limit"
        else:
            (self.output / f"{self.calls:02d}-{endpoint}.json").write_bytes(body)
        dump(self.output / f"{self.calls:02d}-{endpoint}.meta.json", meta)
        if secret_in_body or secret_in_headers or oversized:
            raise ProbeStopped("Response exceeded limit or echoed credential; stopped")
        if status != 200:
            raise ProbeStopped(f"HTTP {status}; no retry or alternate route performed")
        try:
            return json.loads(body)
        except (ValueError, UnicodeDecodeError):
            raise ProbeStopped("Response is not JSON; stopped") from None


def first_score_markets(catalog):
    if not isinstance(catalog, list):
        raise ProbeStopped("Unexpected market catalog shape")
    return [r for r in catalog if r.get("sportId") == 11 and r.get("playerProp") is True
            and re.fullmatch(r"(?:player )?first (?:basket|points?|field goal|fg)(?: scorer)?",
                             " ".join(r.get("marketName", "").lower().split()))]


def choose_fixtures(fixtures, plan=PLAN):
    if not isinstance(fixtures, list):
        raise ProbeStopped("Unexpected fixture list shape")
    nba = [r for r in fixtures if r.get("sportId") == 11 and r.get("tournamentSlug") == "nba"]
    if len({r.get("fixtureId") for r in nba}) != len(nba):
        raise ProbeStopped("Duplicate NBA fixture identifiers")
    try:
        # The API includes fixtures exactly at `to`; our fixed cohort excludes them.
        if any(not r.get("fixtureId") or not zoned(plan["from"]) <= zoned(r["startTime"]) <= zoned(plan["to"]) for r in nba):
            raise ProbeStopped("NBA fixture outside requested interval")
        nba = [r for r in nba if zoned(r["startTime"]) < zoned(plan["to"])]
        return sorted(nba, key=lambda r: (zoned(r["startTime"]), r["fixtureId"]))[:plan["max_fixtures"]]
    except (KeyError, TypeError, ValueError):
        raise ProbeStopped("Missing or invalid fixture identity/clock") from None


def history_inventory(response, fixture, catalog):
    if not isinstance(response, dict) or response.get("fixtureId") != fixture["fixtureId"] or not isinstance(response.get("bookmakers"), dict):
        raise ProbeStopped("Historical response fixture/shape mismatch")
    wanted = {str(r["marketId"]): r for r in catalog}
    rows = []
    for book, bdata in response["bookmakers"].items():
        for mid, market in bdata.get("markets", {}).items():
            if mid not in wanted:
                continue
            counts, players = Counter(), set()
            for outcome in market.get("outcomes", {}).values():
                for player, entries in outcome.get("players", {}).items():
                    if not isinstance(entries, list):
                        raise ProbeStopped("Unexpected historical player timeline shape")
                    if player == "0":
                        counts["team_or_unidentified_timeline"] += 1
                        continue
                    for entry in entries:
                        counts["entries"] += 1
                        try:
                            created = zoned(entry["createdAt"])
                            price = float(entry["price"])
                            if not math.isfinite(price) or price <= 1:
                                raise ValueError("Invalid price")
                            counts["valid_price_and_zoned_history_clock"] += 1
                            if created < zoned(fixture["startTime"]):
                                counts["pregame_entries"] += 1
                                if entry.get("active") is True:
                                    counts["active_pregame_entries"] += 1
                                    players.add(player)
                        except (KeyError, ValueError, TypeError):
                            counts["invalid_price_or_clock"] += 1
            rows.append({"bookmaker": book, "market_id": mid, "market_name": wanted[mid]["marketName"],
                         "counts": dict(counts), "players_with_active_pregame_entry": len(players)})
    return {"fixture_id": fixture["fixtureId"], "start_time": fixture["startTime"],
            "returned_bookmakers": sorted(response["bookmakers"]), "first_score_market_coverage": rows,
            "clock_semantics": "createdAt is provider history-entry creation, not established bookmaker update time",
            "qualified_replication": False}


def cached_catalogs(source, output):
    """Reuse verified pre-price responses after a local parsing stop."""
    if json.loads((source / "plan.json").read_text()) != PLAN:
        raise ProbeStopped("Cached catalog plan differs from the fixed probe")
    if list(source.glob("*-historical-odds*")):
        raise ProbeStopped("Cannot resume catalogs after a historical request")
    catalogs, receipts = {}, []
    requests = [("bookmakers", {}), ("markets", {"language": "en"}),
                ("fixtures", {"sportId": 11, "from": PLAN["from"], "to": PLAN["to"]})]
    for number, (endpoint, params) in enumerate(requests, 1):
        path = source / f"{number:02d}-{endpoint}.json"
        body = path.read_bytes()
        meta = json.loads(path.with_suffix(".meta.json").read_text())
        expected_url = BASE + endpoint + "?" + urllib.parse.urlencode(params)
        digest = hashlib.sha256(body).hexdigest()
        if (meta.get("status") != 200 or meta.get("body_retained") is not True
                or meta.get("url_without_credential") != expected_url
                or meta.get("bytes") != len(body) or meta.get("sha256") != digest):
            raise ProbeStopped("Cached catalog receipt or body mismatch")
        catalogs[endpoint] = json.loads(body)
        receipts.append({"path": str(path.resolve()), "sha256": digest,
                         "original_received_at": meta["received_at"]})
    dump(output / "resumed-catalogs.json", {"source": str(source.resolve()),
         "reused_requests": len(requests), "receipts": receipts})
    return catalogs


def run(client, catalogs=None):
    def catalog(endpoint, params):
        return catalogs[endpoint] if catalogs is not None else client.get(endpoint, params)

    books = catalog("bookmakers", {})
    if not isinstance(books, list):
        raise ProbeStopped("Unexpected bookmaker catalog shape")
    available = {b.get("slug") for b in books}
    selected_books = [b for b in PLAN["bookmakers"] if b in available]
    if "fanduel" not in selected_books:
        raise ProbeStopped("FanDuel absent from provider bookmaker catalog")
    markets = first_score_markets(catalog("markets", {"language": "en"}))
    dump(client.output / "candidate-markets.json", markets)
    if not markets:
        raise ProbeStopped("No first-score player market in basketball catalog")
    fixtures = choose_fixtures(catalog("fixtures", {"sportId": 11, "from": PLAN["from"], "to": PLAN["to"]}))
    # Fixture selection is fixed before any historical-price response is requested.
    dump(client.output / "selected-fixtures.json", [{k: r.get(k) for k in
         ("fixtureId", "startTime", "participant1Name", "participant2Name", "tournamentSlug")} for r in fixtures])
    results = []
    for fixture in fixtures:
        history = client.get("historical-odds", {"fixtureId": fixture["fixtureId"], "bookmakers": ",".join(selected_books)})
        results.append(history_inventory(history, fixture, markets))
        dump(client.output / "coverage.json", {"selected_books": selected_books, "fixtures": results})
    return {"selected_books": selected_books, "fixtures_probed": len(fixtures), "requests": client.calls,
            "status": "source_probe_complete", "coverage": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="Perform at most six authenticated read-only requests")
    parser.add_argument("--api-key-file", type=Path, help="Private local file; the key is never a CLI value")
    parser.add_argument("--resume-catalogs", type=Path, help="Reuse three verified catalogs from a stopped pre-history run")
    args = parser.parse_args()
    if not args.fetch:
        print(json.dumps({"mode": "dry_run_no_network", **PLAN}, indent=2))
        return
    key = args.api_key_file.read_text().strip() if args.api_key_file else os.environ.get("ODDSPAPI_API_KEY", "").strip()
    if not key:
        parser.exit(2, "ODDSPAPI_API_KEY or --api-key-file is required; no requests made.\n")
    output = ROOT / "data/raw/oddspapi-first-basket-probe" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    dump(output / "plan.json", PLAN)
    client = Client(key, output)
    reused_requests = 0
    try:
        catalogs = cached_catalogs(args.resume_catalogs, output) if args.resume_catalogs else None
        if catalogs is not None:
            client.calls = reused_requests = 3
        result = run(client, catalogs)
    except ProbeStopped as error:
        result = {"status": "stopped", "reason": str(error), "requests": client.calls}
    except Exception:
        result = {"status": "stopped", "reason": "Unexpected schema or local failure; inspect retained response", "requests": client.calls}
    result.update({"reused_requests": reused_requests, "new_requests": client.calls - reused_requests})
    dump(output / "result.json", result)
    print(json.dumps({"output": str(output.relative_to(ROOT)), "status": result["status"], "requests": client.calls}, indent=2))


if __name__ == "__main__":
    main()
