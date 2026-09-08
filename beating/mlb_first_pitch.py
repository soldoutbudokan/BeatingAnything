"""Acquire official pitch-event timestamps to tighten historical prestart checks."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen


def first_pitch(document, game_pk):
    if document.get("gamePk") != game_pk:
        raise ValueError("Official pitch-feed identity mismatch")
    events = [event for play in document.get("liveData", {}).get("plays", {}).get("allPlays", [])
              for event in play.get("playEvents", []) if event.get("isPitch") and event.get("startTime")]
    times = []
    for event in events:
        stamp = datetime.fromisoformat(event["startTime"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("Official pitch timestamp lacks timezone")
        times.append(stamp.astimezone(timezone.utc))
    return min(times).isoformat() if times else None


def download(schedule_path, output, start, end):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    schedule = json.loads(Path(schedule_path).read_text())
    ids = sorted({g["gamePk"] for day in schedule["dates"] for g in day["games"]
                  if start <= g["officialDate"] <= end})
    def fetch(pk):
        uri = (f"https://statsapi.mlb.com/api/v1.1/game/{pk}/feed/live"
               "?fields=gamePk,liveData,plays,allPlays,playEvents,isPitch,startTime")
        path = output/f"{pk}.json"
        try:
            if not path.exists():
                with urlopen(uri, timeout=40) as response:
                    raw = response.read()
                value = json.loads(raw)
                first_pitch(value, pk)
                temporary = path.with_suffix(".tmp")
                temporary.write_bytes(raw)
                temporary.replace(path)
            raw = path.read_bytes()
            value = json.loads(raw)
            return {"game_pk": pk, "url": uri, "sha256": hashlib.sha256(raw).hexdigest(),
                    "first_pitch_at": first_pitch(value, pk), "status": "retrieved"}
        except Exception as exc:
            return {"game_pk": pk, "url": uri, "status": "failed", "error": str(exc)}
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(fetch, ids))
    report = {"observed_at": datetime.now(timezone.utc).isoformat(), "start": start, "end": end,
              "source": "Official MLB recorded pitch-event start times; retrospectively retrieved",
              "rows": rows}
    (output/"manifest.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({"games": len(rows), "with_first_pitch": sum(bool(r.get("first_pitch_at")) for r in rows),
                      "failed": sum(r["status"] == "failed" for r in rows)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schedule", default="data/raw/mlb-2026-f1/schedule_2026.json")
    parser.add_argument("--output", default="data/raw/mlb-2026-f1/first-pitch")
    parser.add_argument("--start", default="2026-09-01")
    parser.add_argument("--end", default="2026-09-08")
    args = parser.parse_args()
    download(args.schedule, args.output, args.start, args.end)
