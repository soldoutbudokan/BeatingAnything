"""At most sixteen fixed, price-only history requests for three other books."""
import argparse
from datetime import datetime, timezone
import json

from tools.probe_first_basket_history import Client, HistoryNotFound, ProbeStopped, dump
from tools.validate_nba_first_score_2026 import ROOT, FORECASTS, digest

FORECAST_SHA = "354eeaaa23e6cf1534b43e910ac0198466c88384830ea6309ff5e9863130c8bf"
BOOKS = ("bet365", "draftkings", "pinnacle")
DECLARATION = ROOT / "docs/nba-first-score-reference-diagnostic-2026-09-19.md"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    if digest(FORECASTS) != FORECAST_SHA:
        raise ValueError("Original forecast file changed")
    fixtures = [{"fixture_id": f["fixture_id"], "start": f["start"], "decision": f["decision"]}
                for f in json.loads(FORECASTS.read_text())["forecasts"]]
    if len(fixtures) != 16 or len({f["fixture_id"] for f in fixtures}) != 16:
        raise ValueError("Original sixteen-game cohort changed")
    plan = {"purpose": __doc__, "forecast_sha256": FORECAST_SHA, "declaration_sha256": digest(DECLARATION),
            "bookmakers": BOOKS, "outcome_id": 112604, "max_requests": 16, "fixtures": fixtures}
    if not args.fetch:
        print(json.dumps(plan, indent=2))
        return
    output = ROOT / "data/raw/nba-first-score-reference-diagnostic" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    dump(output / "plan.json", plan)
    print(json.dumps({"output": str(output.relative_to(ROOT))}), flush=True)
    key = (ROOT / "state/credentials/oddspapi-api-key.txt").read_text().strip()
    client = Client(key, output, max_requests=16)
    rows = []
    result = {"status": "complete"}
    try:
        for fixture in fixtures:
            try:
                data = client.get("historical-odds", {"fixtureId": fixture["fixture_id"],
                    "bookmakers": ",".join(BOOKS), "outcomeId": 112604})
                if data.get("fixtureId") != fixture["fixture_id"] or not isinstance(data.get("bookmakers"), dict):
                    raise ProbeStopped("Response fixture/schema mismatch")
                row = {"fixture_id": fixture["fixture_id"], "status": "history_received", "books": sorted(data["bookmakers"])}
            except HistoryNotFound:
                row = {"fixture_id": fixture["fixture_id"], "status": "provider_explicit_no_history", "books": []}
            rows.append(row)
            dump(output / "coverage.json", rows)
            print(json.dumps({"completed": len(rows), "total": 16, "books": row["books"]}), flush=True)
    except ProbeStopped as error:
        result = {"status": "stopped", "reason": str(error)}
    result.update(requests=client.calls, completed=len(rows))
    dump(output / "result.json", result)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
