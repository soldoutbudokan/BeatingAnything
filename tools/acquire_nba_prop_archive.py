#!/usr/bin/env python3
"""Acquire pinned public NBA quote originals without evaluating bets or outcomes."""
import argparse
import csv
import hashlib
import json
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/nba-consensus-price"
REPOSITORY = "devlincorrigan/nba-props-threshold-app"
COMMIT = "233dbbc86b9c6e13df04d4e8b063581b3aa15abb"
PREFIX = "data/historical_points/"
MAPPING = "data/game_event_bijection.csv"
EXPECTED_FILES = 3394
EXPECTED_BYTES = 397273601


def now():
    return datetime.now(timezone.utc).isoformat()


def download_once(url, path, fetch):
    if path.exists():
        return
    if not fetch:
        raise FileNotFoundError(f"{path}: supply --fetch for the pinned public source")
    started = now()
    temporary = path.with_suffix(path.suffix + ".part")
    # No retry/fallback route: an access denial must be investigated separately.
    with urlopen(url, timeout=120) as response, temporary.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    temporary.rename(path)
    path.with_suffix(path.suffix + ".acquisition.json").write_text(json.dumps({
        "url": url, "request_started_utc": started, "response_complete_utc": now(),
    }, indent=2) + "\n")


def digest(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "git_blob_sha": hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    tree_path = RAW / "source_tree.json"
    tree_url = f"https://api.github.com/repos/{REPOSITORY}/git/trees/{COMMIT}?recursive=1"
    download_once(tree_url, tree_path, args.fetch)
    tree = json.loads(tree_path.read_text())
    if tree.get("truncated"):
        raise ValueError("Source tree is truncated")
    inventory = {item["path"]: item for item in tree["tree"] if item["type"] == "blob"
                 and ((item["path"].startswith(PREFIX) and item["path"].endswith(".json"))
                      or item["path"] == MAPPING)}
    quote_inventory = [item for name, item in inventory.items() if name != MAPPING]
    assert len(quote_inventory) == EXPECTED_FILES
    assert sum(item["size"] for item in quote_inventory) == EXPECTED_BYTES
    archive_path = RAW / f"source-{COMMIT}.tar.gz"
    archive_url = f"https://codeload.github.com/{REPOSITORY}/tar.gz/{COMMIT}"
    download_once(archive_url, archive_path, args.fetch)
    selected, seen = [], set()
    (RAW / "archive").mkdir(exist_ok=True)
    # Read selected regular members only; never extract arbitrary publisher paths.
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive:
            pieces = PurePosixPath(member.name).parts
            name = "/".join(pieces[1:])
            if name not in inventory:
                continue
            if not member.isfile() or name in seen:
                raise ValueError(f"Invalid or duplicate selected member: {name}")
            seen.add(name)
            with archive.extractfile(member) as handle:
                data = handle.read()
            hashes = digest(data)
            expected = inventory[name]
            if hashes["git_blob_sha"] != expected["sha"] or hashes["bytes"] != expected["size"]:
                raise ValueError(f"Pinned Git blob mismatch: {name}")
            local = RAW / ("game_event_bijection.csv" if name == MAPPING else "archive/" + PurePosixPath(name).name)
            if local.exists() and local.read_bytes() != data:
                raise ValueError(f"Existing original differs: {local}")
            if not local.exists():
                local.write_bytes(data)
            row = {"source_path": name, "local_path": str(local.relative_to(ROOT)), **hashes}
            if name != MAPPING:
                obj = json.loads(data)
                event = obj["data"]
                row.update(event_id=event["id"], source_snapshot_utc=obj["timestamp"],
                           reported_start_utc=event["commence_time"], home_team=event["home_team"],
                           away_team=event["away_team"])
            selected.append(row)
    if seen != set(inventory):
        raise ValueError(f"Missing originals: {set(inventory) - seen}")
    quotes = [row for row in selected if row["source_path"] != MAPPING]
    with (RAW / "game_event_bijection.csv").open(newline="") as handle:
        mapping_rows = list(csv.DictReader(handle))
    acquisition_path = archive_path.with_suffix(archive_path.suffix + ".acquisition.json")
    report = {
        "repository": REPOSITORY, "commit": COMMIT, "verified_utc": now(),
        "purpose": "Original-source acquisition and identity/clock inventory only; no odds disparities or outcomes inspected.",
        "source_tree": {"url": tree_url, **digest(tree_path.read_bytes()), "truncated": False},
        "archive": {"url": archive_url, **digest(archive_path.read_bytes()),
                    "acquisition": json.loads(acquisition_path.read_text()) if acquisition_path.exists() else None},
        "summary": {"quote_files": len(quotes), "quote_bytes": sum(row["bytes"] for row in quotes),
                    "distinct_event_ids": len({row["event_id"] for row in quotes}),
                    "snapshot_range_utc": [min(row["source_snapshot_utc"] for row in quotes), max(row["source_snapshot_utc"] for row in quotes)],
                    "reported_start_range_utc": [min(row["reported_start_utc"] for row in quotes), max(row["reported_start_utc"] for row in quotes)],
                    "mapping_rows": len(mapping_rows), "mapping_columns": list(mapping_rows[0])},
        "files": sorted(selected, key=lambda row: row["source_path"]),
    }
    output = RAW / "acquisition_manifest.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"manifest": str(output.relative_to(ROOT)), **report["summary"]}, indent=2))


if __name__ == "__main__":
    main()
