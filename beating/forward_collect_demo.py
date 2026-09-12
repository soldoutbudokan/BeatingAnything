"""Deliberately synthetic offline responses. Never use as research evidence."""
import json
from urllib.parse import parse_qs, urlsplit


def demo_get(url, timeout):
    parsed = urlsplit(url)
    event = {"id": "SYNTHETIC-ODDS-EVENT", "sport_key": "baseball_mlb",
             "commence_time": "2020-01-01T12:00:00Z", "home_team": "SYNTHETIC HOME",
             "away_team": "SYNTHETIC AWAY", "synthetic": True}
    markets = [
        {"key": "h2h", "last_update": "2020-01-01T12:05:01Z",
         "outcomes": [{"name": "SYNTHETIC HOME", "price": 1.91},
                      {"name": "SYNTHETIC AWAY", "price": 1.97}]},
        {"key": "alternate_totals", "last_update": "2020-01-01T12:04:50Z",
         "outcomes": [{"name": "Over", "point": 7.5, "price": 1.8},
                      {"name": "Under", "point": 7.5, "price": 2.1},
                      {"name": "Over", "point": 10.5, "price": 3.1},
                      {"name": "Under", "point": 10.5, "price": 1.4}]},
        {"key": "batter_hits", "last_update": "2020-01-01T12:05:02Z",
         "outcomes": [{"name": "Over", "description": "SYNTHETIC BATTER",
                       "point": 1.5, "price": 2.5},
                      {"name": "Under", "description": "SYNTHETIC BATTER",
                       "point": 1.5, "price": 1.5}]},
    ]
    used = 0
    if parsed.path.endswith("/schedule"):
        value = {"synthetic": True, "dates": [{"games": [
            {"gamePk": 999999, "status": {"abstractGameState": "Live"}}]}]}
    elif parsed.path.endswith("/feed/live"):
        value = {"synthetic": True, "gamePk": 999999,
                 "metaData": {"timeStamp": "20200101_120504"},
                 "liveData": {"plays": {"currentPlay": {"about": {
                     "startTime": "2020-01-01T12:04:59Z", "endTime": "2020-01-01T12:05:03Z"}}}}}
    elif parsed.path.endswith("/events"):
        value = [event]
    elif parsed.path.endswith("/markets"):
        value = {**event, "bookmakers": [{"key": book,
                 "markets": [{"key": m["key"], "last_update": m["last_update"]} for m in markets]}
                 for book in ("fanduel", "pinnacle")]}
        used = 1
    elif parsed.path.endswith("/odds"):
        selected = parse_qs(parsed.query)["markets"][0].split(",")
        value = {**event, "bookmakers": [{"key": book, "markets": [
                 market for market in markets if market["key"] in selected]}
                 for book in ("fanduel", "pinnacle")]}
        used = len(selected)
    else:
        raise ValueError("Unsupported synthetic demo endpoint")
    headers = {"Date": "Wed, 01 Jan 2020 12:05:05 GMT", "Content-Type": "application/json",
               "x-requests-last": str(used), "x-requests-remaining": "99999"}
    return 200, headers, (json.dumps(value, indent=2) + "\n").encode()
