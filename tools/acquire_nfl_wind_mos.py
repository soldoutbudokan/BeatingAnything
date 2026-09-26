"""Bounded public IEM GFS MOS acquisition; never reads football outcomes.

One request per explicit station, no automatic retries, two transfers at most.
Original bodies, request/receipt times, headers, errors and hashes are retained.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/raw/nfl-wind-revisions-2026-09-26/mos"
START, END = "2025-08-28T00:00Z", "2026-01-06T00:00Z"


def now():
    return datetime.now(timezone.utc).isoformat()


def acquire(station):
    if not re.fullmatch(r"K[A-Z0-9]{3}", station):
        raise ValueError("Expected explicit four-character CONUS station")
    OUT.mkdir(parents=True, exist_ok=True)
    body_path = OUT / (station + ".json")
    receipt_path = OUT / (station + ".receipt.json")
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        assert body_path.exists() and hashlib.sha256(body_path.read_bytes()).hexdigest() == receipt["sha256"]
        return {"station": station, "status": "retained", "http_status": receipt["http_status"], "rows": receipt.get("rows")}
    if body_path.exists():
        raise FileExistsError("Unreceipted body exists; do not overwrite")
    url = "https://mesonet.agron.iastate.edu/cgi-bin/request/mos.py?" + urlencode({
        "station": station, "model": "GFS", "sts": START, "ets": END, "format": "json"})
    receipt = {"station": station, "model": "GFS", "url": url, "requested_at_utc": now(),
               "runtime_start": START, "runtime_end": END}
    try:
        with urlopen(Request(url, headers={"User-Agent": "BeatingAnything-research/1.0"}), timeout=55) as response:
            body = response.read()
            receipt.update(http_status=response.status, headers=dict(response.headers))
    except HTTPError as exc:
        body = exc.read()
        receipt.update(http_status=exc.code, headers=dict(exc.headers), error=str(exc))
    except Exception as exc:
        body = b""
        receipt.update(http_status=None, error=repr(exc))
    receipt.update(received_at_utc=now(), bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
    body_path.write_bytes(body)
    if receipt["http_status"] == 200:
        try:
            data = json.loads(body)
            if not isinstance(data, list):
                raise ValueError("Expected list")
            if any(r.get("station") != station or r.get("model") != "GFS" for r in data):
                raise ValueError("Wrong station/model")
            receipt.update(rows=len(data), runs=len({r["runtime"] for r in data}),
                           first_run=min((r["runtime"] for r in data), default=None),
                           last_run=max((r["runtime"] for r in data), default=None))
        except Exception as exc:
            receipt["parse_error"] = repr(exc)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    return {k: receipt.get(k) for k in ["station", "http_status", "rows", "runs", "bytes", "error", "parse_error"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stations", nargs="+")
    args = parser.parse_args()
    stations = sorted(set(args.stations))
    if len(stations) > 32:
        raise ValueError("Bounded acquisition: at most32 stations")
    with ThreadPoolExecutor(max_workers=2) as pool:
        for record in pool.map(acquire, stations):
            print(json.dumps(record), flush=True)
