"""Manual, bounded price-only acquisition of the fixed final regular-season month."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.parse

from tools.probe_first_basket_history import BASE, ROOT, Client, ProbeStopped, HistoryNotFound, choose_fixtures, dump, first_score_markets, history_inventory
from tools.probe_first_basket_history_followup import PLAN as SOURCE_PLAN

PLAN = {
    "purpose": "Price-only first-score source inventory; no forecasting or outcome grading",
    "windows": [
        {"from": "2026-03-15T00:00:00Z", "to": "2026-03-24T00:00:00Z", "max_fixtures": 300},
        {"from": "2026-03-24T00:00:00Z", "to": "2026-04-02T00:00:00Z", "max_fixtures": 300},
        {"from": "2026-04-02T00:00:00Z", "to": "2026-04-11T00:00:00Z", "max_fixtures": 300},
        {"from": "2026-04-11T00:00:00Z", "to": "2026-04-13T00:00:00Z", "max_fixtures": 300},
    ],
    "selection": "Every exact NBA fixture in half-open windows, sorted by start/ID; no odds/status/outcome filter; freeze before histories",
    "max_fixtures": 300, "max_requests": 304, "max_documented_quota_requests": 4,
    "bookmakers": ["fanduel", "betmgm"], "outcome_id": 112604,
    "fixture_cooldown_seconds": 2.1, "history_cooldown_seconds": 5.1,
    "catalog_path": SOURCE_PLAN["catalog_path"], "catalog_sha256": SOURCE_PLAN["catalog_sha256"],
}


def missing_history(fixture):
    return {"fixture_id": fixture["fixtureId"], "start_time": fixture["startTime"],
            "status": "provider_explicit_no_history", "first_score_market_coverage": [],
            "qualified_replication": False}


def resume_history(output, catalog):
    saved_plan = json.loads((output / "plan.json").read_text())
    if any(saved_plan.get(k) != v for k, v in PLAN.items()):
        raise ProbeStopped("Resume plan mismatch")
    fixtures = json.loads((output / "selected-fixtures.json").read_text())
    coverage = []
    expected_fixtures = []
    candidates = first_score_markets(catalog)
    receipts = sorted(output.glob("[0-9]*-*.meta.json"), key=lambda path: int(path.name.split("-")[0]))
    cooldown_rejections = 0
    for number, path in enumerate(receipts, 1):
        if int(path.name.split("-")[0]) != number:
            raise ProbeStopped("Noncontiguous acquisition receipts")
        meta = json.loads(path.read_text())
        body_path = path.with_name(path.name.replace(".meta.json", ".json"))
        body = body_path.read_bytes()
        if (not meta.get("body_retained") or hashlib.sha256(body).hexdigest() != meta.get("sha256")
                or len(body) != meta.get("bytes")):
            raise ProbeStopped("Resume response hash mismatch")
        data = json.loads(body)
        if number <= 4:
            window = PLAN["windows"][number - 1]
            expected_url = BASE + "fixtures?" + urllib.parse.urlencode({"sportId": 11, "from": window["from"], "to": window["to"]})
            if (meta.get("status") != 200 or "-fixtures." not in path.name
                    or meta.get("url_without_credential") != expected_url):
                raise ProbeStopped("Invalid original fixture receipt")
            expected_fixtures.extend(choose_fixtures(data, window))
            continue
        fixture = fixtures[len(coverage)]
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(meta["url_without_credential"]).query)
        if (query != {"fixtureId": [fixture["fixtureId"]], "bookmakers": ["fanduel,betmgm"], "outcomeId": ["112604"]}
                or "-historical-odds." not in path.name):
            raise ProbeStopped("Resume history identity mismatch")
        if meta.get("status") == 200:
            coverage.append(history_inventory(data, fixture, candidates))
        elif (meta.get("status") == 404 and data.get("error", {}).get("code") == "NOT_FOUND"
              and data.get("error", {}).get("message") == "No historical odds found for the specified filters."):
            coverage.append(missing_history(fixture))
        elif (meta.get("status") == 429 and data.get("error", {}).get("code") == "RATE_LIMITED"
              and isinstance(data.get("error", {}).get("retryMs"), (int, float))
              and 0 <= data["error"]["retryMs"] <= 5000):
            cooldown_rejections += 1
            if cooldown_rejections > 1:
                raise ProbeStopped("Repeated rate-limit rejection; manual review required")
        else:
            raise ProbeStopped("Cannot resume after a non-absence HTTP error")
    expected_fixtures.sort(key=lambda row: (row["startTime"], row["fixtureId"]))
    fields = ("fixtureId", "startTime", "participant1Name", "participant2Name", "participant1Id", "participant2Id", "tournamentSlug", "externalProviders")
    if fixtures != [{k: f.get(k) for k in fields} for f in expected_fixtures]:
        raise ProbeStopped("Frozen fixture selection differs from verified source lists")
    return fixtures, coverage, len(receipts)


def run(client, catalog, wait=time.sleep, fixtures=None, coverage=None):
    if fixtures is None:
        fixtures = []
        for index, window in enumerate(PLAN["windows"]):
            if index:
                wait(PLAN["fixture_cooldown_seconds"])
            response = client.get("fixtures", {"sportId": 11, "from": window["from"], "to": window["to"]})
            # A truncation cap must never silently choose a subset of a larger window.
            if sum(r.get("sportId") == 11 and r.get("tournamentSlug") == "nba" for r in response) > 300:
                raise ProbeStopped("Fixture window exceeds declared cap")
            fixtures.extend(choose_fixtures(response, window))
    fixtures.sort(key=lambda row: (row["startTime"], row["fixtureId"]))
    if len(fixtures) > PLAN["max_fixtures"] or len({f["fixtureId"] for f in fixtures}) != len(fixtures):
        raise ProbeStopped("Duplicate fixture or cohort exceeds declared cap")
    if not (client.output / "selected-fixtures.json").exists():
        dump(client.output / "selected-fixtures.json", [{k: f.get(k) for k in
            ("fixtureId", "startTime", "participant1Name", "participant2Name", "participant1Id", "participant2Id", "tournamentSlug", "externalProviders")}
            for f in fixtures])
    coverage = [] if coverage is None else coverage
    counts = Counter(entry["bookmaker"] for row in coverage for entry in row["first_score_market_coverage"]
                     if entry["counts"].get("active_pregame_entries", 0))
    candidates = first_score_markets(catalog)
    for index in range(len(coverage), len(fixtures)):
        fixture = fixtures[index]
        try:
            history = client.get("historical-odds", {"fixtureId": fixture["fixtureId"],
                "bookmakers": ",".join(PLAN["bookmakers"]), "outcomeId": PLAN["outcome_id"]})
            row = history_inventory(history, fixture, candidates)
        except HistoryNotFound:
            row = missing_history(fixture)
        coverage.append(row)
        for entry in row["first_score_market_coverage"]:
            if entry["counts"].get("active_pregame_entries", 0):
                counts[entry["bookmaker"]] += 1
        dump(client.output / "coverage.json", coverage)
        dump(client.output / "progress.json", {"completed": index + 1, "total": len(fixtures),
            "requests": client.calls, "games_with_active_pregame_first_score": dict(counts)})
        if (index + 1) % 10 == 0 or index + 1 == len(fixtures):
            print(json.dumps({"completed": index + 1, "total": len(fixtures), "coverage_games": dict(counts)}), flush=True)
    return {"status": "acquisition_complete", "fixtures": len(fixtures), "requests": client.calls,
            "games_with_active_pregame_first_score": dict(counts)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--resume", type=Path, help="Continue a verified frozen cohort without repeating completed requests")
    args = parser.parse_args()
    if not args.fetch:
        print(json.dumps(PLAN, indent=2))
        return
    body = (ROOT / PLAN["catalog_path"]).read_bytes()
    if hashlib.sha256(body).hexdigest() != PLAN["catalog_sha256"]:
        parser.exit(2, "Catalog hash mismatch; no requests made.\n")
    catalog = json.loads(body)
    key = (ROOT / "state/credentials/oddspapi-api-key.txt").read_text().strip()
    if not key:
        parser.exit(2, "Missing key; no requests made.\n")
    output = args.resume or ROOT / "data/raw/nba-first-score-2026-prices" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if not args.resume:
        output.mkdir(parents=True, exist_ok=False)
        dump(output / "plan.json", {**PLAN, "declared_at": datetime.now(timezone.utc).isoformat(),
             "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    else:
        output = output.resolve()
    client = Client(key, output, max_requests=PLAN["max_requests"])
    print(json.dumps({"output": str(output.relative_to(ROOT))}), flush=True)
    try:
        fixtures, coverage = None, None
        if args.resume:
            fixtures, coverage, client.calls = resume_history(output, catalog)
            previous = output / "result.json"
            if previous.exists():
                dump(output / f"prior-stop-{client.calls}.json", json.loads(previous.read_text()))
            dump(output / f"resume-{client.calls}.json", {"resumed_at": datetime.now(timezone.utc).isoformat(),
                 "completed_receipts": client.calls, "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 "selected_fixtures_sha256": hashlib.sha256((output / "selected-fixtures.json").read_bytes()).hexdigest(),
                 "policy": "Exact NOT_FOUND retained as absence; at most one recorded RATE_LIMITED retry after required cooldown; successful requests never repeated"})
            time.sleep(PLAN["history_cooldown_seconds"])
        result = run(client, catalog, fixtures=fixtures, coverage=coverage)
    except ProbeStopped as error:
        result = {"status": "stopped", "reason": str(error), "requests": client.calls}
    except Exception:
        result = {"status": "stopped", "reason": "Unexpected schema or local failure; inspect retained response", "requests": client.calls}
    dump(output / "result.json", result)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
