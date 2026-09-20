"""One manual two-request NBA capture; no predictions, alerts, or scheduling."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://api.oddspapi.io/v4/odds-by-tournaments"
BOOKS = ("fanduel", "betmgm")
MAX_BYTES = 32 * 1024 * 1024
PLAN = {"purpose": __doc__, "tournament_id": 132, "bookmakers": BOOKS,
        "target_market_id": "112604", "max_requests": 2, "documented_quota_requests": 2,
        "request_spacing_after_receipt_seconds": 1.1, "timeout_seconds": 30,
        "max_response_bytes": MAX_BYTES, "retry": False}


class CaptureStopped(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def transport(url):
    request = urllib.request.Request(url, headers={"User-Agent": "BeatingAnything-source-probe", "Accept": "application/json"})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
            return response.status, response.headers.get("Date"), response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get("Date"), error.read(MAX_BYTES + 1)


def fetch(book, key, output, get=transport):
    if book not in BOOKS or not key.strip():
        raise CaptureStopped("Invalid bookmaker or empty key; no request made")
    # The actual API rejects the documentation's plural `bookmakers` parameter.
    params = {"tournamentIds": "132", "bookmaker": book, "verbosity": 3, "language": "en"}
    meta = {"bookmaker": book, "url_without_credential": BASE + "?" + urllib.parse.urlencode(params),
            "request_started_at": now(), "source_verified": False}
    url = BASE + "?" + urllib.parse.urlencode({**params, "apiKey": key.strip()})
    tick = time.monotonic()
    try:
        status, http_date, body = get(url)
    except Exception as error:
        meta.update(transport_failure_type=type(error).__name__, response_received_at=now())
        dump(output / f"{book}.meta.json", meta)
        raise CaptureStopped("Transport failure; no retry") from None
    forms = (key.strip(), urllib.parse.quote(key.strip(), safe=""), urllib.parse.quote_plus(key.strip()), json.dumps(key.strip())[1:-1])
    echo = any(s.encode() in body or s in (http_date or "") for s in forms)
    retained = len(body) <= MAX_BYTES and not echo
    meta.update(status=status, response_received_at=now(), elapsed_seconds=time.monotonic()-tick,
                http_date=None if echo else http_date, bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), body_retained=retained)
    if retained:
        (output / f"{book}.json").write_bytes(body)
    else:
        meta["body_omission_reason"] = "credential_echo" if echo else "response_size_limit"
    dump(output / f"{book}.meta.json", meta)
    if not retained or status != 200:
        raise CaptureStopped("Response rejected or HTTP failure; no retry")
    try:
        return json.loads(body), meta
    except (ValueError, UnicodeError):
        raise CaptureStopped("Invalid JSON; no retry") from None


def inventory(data, book):
    if not isinstance(data, list):
        raise CaptureStopped("Unrecognized current-odds shape")
    fixtures, prices, targets = [], [], []
    seen = set()
    for fixture in data:
        if (fixture.get("sportId") != 11 or fixture.get("tournamentId") != 132 or fixture.get("tournamentSlug") != "nba"
                or not fixture.get("fixtureId") or fixture["fixtureId"] in seen):
            raise CaptureStopped("Unexpected league or duplicate/missing fixture identity")
        seen.add(fixture["fixtureId"])
        books = fixture.get("bookmakerOdds", {})
        if set(books) - {book}:
            raise CaptureStopped("Unexpected bookmaker in single-book response")
        fixtures.append({k: fixture.get(k) for k in ("fixtureId", "startTime", "statusId", "statusName", "participant1Name", "participant2Name")})
        b = books.get(book, {})
        for mid, market in b.get("markets", {}).items():
            for oid, outcome in market.get("outcomes", {}).items():
                for pid, row in outcome.get("players", {}).items():
                    flags_open = (b.get("bookmakerIsActive") is True and b.get("suspended") is False
                                  and market.get("marketActive") is True and row.get("active") is True)
                    record = {"fixture_id": fixture["fixtureId"], "bookmaker": book, "market_id": str(mid),
                        "outcome_id": str(oid), "provider_player_id": str(pid), "player_name": row.get("playerName"),
                        "decimal": row.get("price"), "bookmaker_fixture_id": b.get("bookmakerFixtureId"),
                        "fixture_path": b.get("fixturePath"), "bookmaker_market_id": market.get("bookmakerMarketId"),
                        "bookmaker_outcome_id": row.get("bookmakerOutcomeId"), "betslip": row.get("betslip"),
                        "bookmaker_is_active": b.get("bookmakerIsActive"), "book_suspended": b.get("suspended"),
                        "market_active": market.get("marketActive"), "selection_active": row.get("active"),
                        "all_provider_open_flags": flags_open,
                        "provider_changed_at": row.get("changedAt"), "bookmaker_changed_at": row.get("bookmakerChangedAt"),
                        "source_verified": False}
                    prices.append(record)
                    if str(mid) == PLAN["target_market_id"]:
                        targets.append(record)
    counts = Counter(r["market_id"] for r in prices)
    return {"bookmaker": book, "fixtures": fixtures, "fixture_count": len(fixtures), "selection_count": len(prices),
        "selection_counts_by_market": dict(counts), "target_selection_count": len(targets), "target_selections": targets,
        "provider_changed_at_present": sum(r["provider_changed_at"] is not None for r in prices),
        "bookmaker_changed_at_present": sum(r["bookmaker_changed_at"] is not None for r in prices),
        "selection_active_inside_inactive_market": sum(r["selection_active"] is True and r["market_active"] is False for r in prices),
        "source_verified": False, "prices": prices}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="Make exactly one request per book, stopping on the first failure")
    args = parser.parse_args()
    if not args.fetch:
        print(json.dumps(PLAN, indent=2))
        return
    key = (ROOT / "state/credentials/oddspapi-api-key.txt").read_text().strip()
    if not key:
        parser.exit(2, "Empty local API key; no request made.\n")
    output = ROOT / "data/raw/nba-first-score-current-capture" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:12])
    output.mkdir(parents=True, exist_ok=False)
    dump(output / "plan.json", {**PLAN, "created_at": now()})
    summary = {"output": str(output.relative_to(ROOT)), "status": "complete", "requests": 0, "books": {}}
    try:
        for i, book in enumerate(BOOKS):
            if i:
                time.sleep(PLAN["request_spacing_after_receipt_seconds"])
            summary["requests"] += 1
            data, receipt = fetch(book, key, output)
            result = inventory(data, book)
            dump(output / f"{book}-inventory.json", {**result, "receipt": receipt})
            summary["books"][book] = {k: v for k, v in result.items() if k not in ("prices", "fixtures", "target_selections")}
    except CaptureStopped as error:
        summary.update(status="stopped", reason=str(error))
    except (AttributeError, KeyError, TypeError, ValueError):
        summary.update(status="stopped", reason="Unexpected response schema; inspect retained body, no retry")
    dump(output / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    if summary["status"] != "complete":
        parser.exit(2)


if __name__ == "__main__":
    main()
