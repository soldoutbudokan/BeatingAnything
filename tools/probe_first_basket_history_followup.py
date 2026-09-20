"""Fixed later-date OddsPapi coverage check after user-confirmed prop access."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from tools.probe_first_basket_history import (
    ROOT, Client, ProbeStopped, choose_fixtures, dump, first_score_markets, history_inventory,
)


PLAN = {
    "purpose": "Source coverage after screenshots show both books' pregame/player-prop access; no outcome grading",
    "windows": [
        {"from": "2026-04-12T00:00:00Z", "to": "2026-04-15T00:00:00Z", "max_fixtures": 1},
        {"from": "2026-05-12T00:00:00Z", "to": "2026-05-15T00:00:00Z", "max_fixtures": 1},
        {"from": "2026-06-04T00:00:00Z", "to": "2026-06-07T00:00:00Z", "max_fixtures": 1},
    ],
    "selection": "First NBA fixture by zoned start and ID per half-open window, without price/availability/outcome filtering; freeze all selections before histories; no replacement for empty windows",
    "bookmakers": ["fanduel", "betmgm"],
    "max_requests": 6,
    "max_documented_quota_requests": 3,
    "fixture_cooldown_seconds": 2.1,
    "history_cooldown_seconds": 5.1,
    "catalog_path": "data/raw/oddspapi-first-basket-probe/20260920T005127890957Z/02-markets.json",
    "catalog_sha256": "708586be12d725cf8dabdb0f61c47b88237db8eabad7bfb59ceadab33b173c15",
}


def catalog_inventory(history, catalog):
    lookup = {str(row["marketId"]): row for row in catalog}
    rows = []
    for book, data in history["bookmakers"].items():
        markets = data.get("markets", {})
        unknown = sorted(set(markets) - set(lookup))
        rows.append({
            "bookmaker": book, "market_count": len(markets), "unknown_market_ids": unknown,
            "player_prop_market_count": sum(lookup.get(mid, {}).get("playerProp") is True for mid in markets),
            "market_types": dict(Counter(lookup.get(mid, {}).get("marketType", "unknown") for mid in markets)),
            "nonzero_player_ids": len({pid for market in markets.values()
                for outcome in market.get("outcomes", {}).values()
                for pid in outcome.get("players", {}) if pid != "0"}),
        })
    return rows


def run(client, catalog, wait=time.sleep):
    selected, window_counts = [], []
    for index, window in enumerate(PLAN["windows"]):
        if index:
            wait(PLAN["fixture_cooldown_seconds"])
        response = client.get("fixtures", {"sportId": 11, "from": window["from"], "to": window["to"]})
        fixtures = choose_fixtures(response, window)
        selected.extend(fixtures)
        window_counts.append({**window, "selected_count": len(fixtures)})
    if len({r["fixtureId"] for r in selected}) != len(selected):
        raise ProbeStopped("Duplicate fixture across windows")
    dump(client.output / "selected-fixtures.json", {"windows": window_counts,
        "fixtures": [{k: r.get(k) for k in ("fixtureId", "startTime", "participant1Name", "participant2Name", "tournamentSlug")}
                     for r in selected]})
    coverage = []
    candidates = first_score_markets(catalog)
    dump(client.output / "candidate-markets.json", candidates)
    for fixture in selected:
        history = client.get("historical-odds", {"fixtureId": fixture["fixtureId"], "bookmakers": ",".join(PLAN["bookmakers"])})
        row = history_inventory(history, fixture, candidates)
        row["all_market_coverage"] = catalog_inventory(history, catalog)
        coverage.append(row)
        dump(client.output / "coverage.json", coverage)
    return {"status": "source_probe_complete", "requests": client.calls, "fixtures_probed": len(selected), "coverage": coverage}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--api-key-file", type=Path, default=ROOT / "state/credentials/oddspapi-api-key.txt")
    args = parser.parse_args()
    if not args.fetch:
        print(json.dumps(PLAN, indent=2))
        return
    key = args.api_key_file.read_text().strip()
    if not key:
        parser.exit(2, "Missing key; no requests made.\n")
    body = (ROOT / PLAN["catalog_path"]).read_bytes()
    if hashlib.sha256(body).hexdigest() != PLAN["catalog_sha256"]:
        parser.exit(2, "Cached catalog hash mismatch; no requests made.\n")
    catalog = json.loads(body)
    output = ROOT / "data/raw/oddspapi-first-basket-followup" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    dump(output / "plan.json", PLAN)
    client = Client(key, output)
    try:
        result = run(client, catalog)
    except ProbeStopped as error:
        result = {"status": "stopped", "reason": str(error), "requests": client.calls}
    except Exception:
        result = {"status": "stopped", "reason": "Unexpected schema or local failure; inspect retained response", "requests": client.calls}
    dump(output / "result.json", result)
    print(json.dumps({"output": str(output.relative_to(ROOT)), "status": result["status"], "requests": client.calls}))


if __name__ == "__main__":
    main()
