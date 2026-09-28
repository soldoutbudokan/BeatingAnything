#!/usr/bin/env python3
"""Rebuild the uncommitted NHL shot archive from its pinned public sources.

The container that produced the September 26 NHL work lost `data/raw/`. Every raw
price payload, boxscore, roster and schedule file is public and its SHA-256 was
committed, so this tool re-acquires them, verifies each byte-for-byte against the
committed pins, regenerates the two schedule projections and writes replacement
`manifest.json` / `outcomes/source_audit.json` files. Those two originals held
retrieval metadata and cannot be reproduced byte-for-byte; their original hashes
are recorded here and the replacements are deterministic (no timestamps), so the
downstream tools pin the replacement hashes instead.

No sporting values are read; only bytes, hashes and schedule metadata columns.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import urllib.parse
import urllib.request

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "data/raw/nhl-shot-archive-2026-09-26"
REPORT = ROOT / "reports/nhl-shot-archive-rebuild-2026-09-28"
REPO = "ldinan-git/sports-betting-ops"
COMMIT = "42cf1f81bc302642ddcc9e88ce2e98c1057bc74d"
SOURCE_DIR = "bet-ops/odds_api_responses/player_props/output/icehockey_nhl/player_props"
RECORDED_RAW = ROOT / "reports/nhl-goal-contract-coverage-2026-09-26.json"
RELEASES = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download"
ORIGINAL_MANIFEST = {"sha256": "869d4a6ddfd1473ece6e59a3aed023cedb6899b988fdb5cb6ede29c7b37552da", "bytes": 295384}
ORIGINAL_SOURCE_AUDIT = {"sha256": "0c41bde3a89269a4b0d827243306bb8b63518c8a3786854ca558a2007a19e906"}
# Pins recorded in reports/nhl-shot-outcome-source-2026-09-26.md and
# reports/nhl-powerplay-feature-feasibility-2026-09-26.json.
ASSETS = {
    "outcomes/player_box_2024.csv": ("nhl_player_boxscores/player_box_2024.csv", "889d439dae5b5a2e831496a3a0dcbea4d385883d68d55b70d55a554169ff6e74"),
    "outcomes/player_box_2025.csv": ("nhl_player_boxscores/player_box_2025.csv", "511f58b09996be6165c7ad2a0f475ac029f0206653ce4e11665e1ff8088516b0"),
    "outcomes/rosters_2024.csv": ("nhl_rosters/rosters_2024.csv", "0e70a12579b25af0532d00a0cf8bb5fda7d9eb33a23d76234ca26f2fff4ca4ba"),
    "outcomes/rosters_2025.csv": ("nhl_rosters/rosters_2025.csv", "cff04536329e7a7f3cdf9034786226e6644a7d222486eb70d4a799d12c1f80ba"),
    "outcomes/nhl_schedule_2025.csv": ("nhl_schedules/nhl_schedule_2025.csv", "017f89619c13857e8b7f2f52ccbf7c1ea20fcef46f5bc90de719ea12475d1e00"),
    "powerplay-feature-audit/nhl_schedule_2024.csv": ("nhl_schedules/nhl_schedule_2024.csv", "9292b99f8d5daf362a9e7316f3146fd677e5bafe99063f6fb759baa9383f8d07"),
}
PROJECTIONS = {
    "outcomes/schedule_2025_metadata.csv": ("outcomes/nhl_schedule_2025.csv", "320643ed83428e28671c7508c667026ab65c46b85bcf312d173c2b025d98e855"),
    "powerplay-feature-audit/schedule_2024_metadata.csv": ("powerplay-feature-audit/nhl_schedule_2024.csv", "59afa78de1b51e0ceb7bda66207896801fc080505a0ace27cc6ed41e6397b588"),
}
METADATA_COLUMNS = ["game_id", "season_full", "game_type", "game_date", "game_time", "home_team_abbr",
                    "away_team_abbr", "home_team_name", "away_team_name", "game_state", "venue", "season"]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=300) as response:
        return response.read()


def ensure(path: Path, expected: str, url: str, receipts: list, clone: Path | None = None) -> bytes:
    """Keep a verified local copy; otherwise copy from a local checkout or download."""
    if path.exists() and sha(path.read_bytes()) == expected:
        receipts.append({"path": str(path.relative_to(ROOT)), "action": "verified_existing", "sha256": expected})
        return path.read_bytes()
    data = None
    if clone is not None and (clone / path.name).exists():
        data = (clone / path.name).read_bytes()
        action = "copied_from_local_checkout"
    if data is None or sha(data) != expected:
        data = fetch(url)
        action = "downloaded"
    if sha(data) != expected:
        raise ValueError(f"Hash mismatch for {path.relative_to(ROOT)}: {sha(data)} != {expected}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    receipts.append({"path": str(path.relative_to(ROOT)), "action": action, "url": url, "sha256": expected,
                     "retrieved_at_utc": datetime.now(timezone.utc).isoformat()})
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clone-dir", type=Path, default=None,
                        help="Optional local checkout of the source directory at the pinned commit")
    args = parser.parse_args()
    receipts = []
    recorded = json.loads(RECORDED_RAW.read_text())["source_files"]
    if len(recorded) != 285:
        raise ValueError("Expected 285 committed raw pins")
    files = []
    for item in recorded:
        local = ROOT / item["path"]
        name = local.name
        upstream = f"{SOURCE_DIR}/{name}"
        url = f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/{urllib.parse.quote(upstream)}"
        data = ensure(local, item["sha256"], url, receipts, args.clone_dir)
        if len(data) != item["bytes"]:
            raise ValueError(f"Byte-count mismatch for {name}")
        files.append({"path": item["path"], "source_path": upstream, "sha256": item["sha256"], "bytes": item["bytes"]})
    for rel, (asset, expected) in ASSETS.items():
        ensure(ARCHIVE / rel, expected, f"{RELEASES}/{asset}", receipts)
    projections = {}
    for rel, (raw_rel, expected) in PROJECTIONS.items():
        frame = pd.read_csv(io.BytesIO((ARCHIVE / raw_rel).read_bytes()), dtype=str, keep_default_na=False)
        data = frame[METADATA_COLUMNS].to_csv(index=False, lineterminator="\r\n").encode()
        if sha(data) != expected:
            raise ValueError(f"Projection hash mismatch: {rel}")
        (ARCHIVE / rel).parent.mkdir(parents=True, exist_ok=True)
        (ARCHIVE / rel).write_bytes(data)
        projections[rel] = {"from": raw_rel, "columns": METADATA_COLUMNS, "line_terminator": "CRLF",
                            "rows": len(frame), "sha256": expected}
    manifest = {
        "source_repository": f"https://github.com/{REPO}", "source_commit": COMMIT, "source_directory": SOURCE_DIR,
        "rebuilt": "Deterministic replacement written by tools/rebuild_nhl_shot_archive.py after the uncommitted "
                   "data directory was lost; every file hash equals the pin committed on September 26, 2026.",
        "original_manifest": ORIGINAL_MANIFEST,
        "verification_reference": {"path": str(RECORDED_RAW.relative_to(ROOT)), "sha256": sha(RECORDED_RAW.read_bytes())},
        "files": files,
    }
    (ARCHIVE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    audit = {
        "rebuilt": "Deterministic replacement for the original outcomes/source_audit.json, whose GitHub release "
                   "metadata was not committed. Asset hashes equal the pins in "
                   "reports/nhl-shot-outcome-source-2026-09-26.md and the power-play feasibility report.",
        "original_source_audit": ORIGINAL_SOURCE_AUDIT,
        "publisher": "https://github.com/sportsdataverse/sportsdataverse-data",
        "assets": {rel: {"url": f"{RELEASES}/{asset}", "sha256": expected} for rel, (asset, expected) in ASSETS.items()},
        "projections": projections,
    }
    (ARCHIVE / "outcomes/source_audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    report = {
        "status": "rebuilt_and_verified", "rebuilt_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_price_files_verified": len(files), "assets_verified": len(ASSETS), "projections_verified": len(projections),
        "replacement_pins": {"manifest.json": sha((ARCHIVE / "manifest.json").read_bytes()),
                             "outcomes/source_audit.json": sha((ARCHIVE / "outcomes/source_audit.json").read_bytes())},
        "original_pins": {"manifest.json": ORIGINAL_MANIFEST, "outcomes/source_audit.json": ORIGINAL_SOURCE_AUDIT},
        "receipts": receipts,
        "sporting_values_read": False,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    REPORT.with_suffix(".md").write_text(
        "# NHL shot archive rebuild — September 28, 2026\n\n"
        "The uncommitted `data/raw/` directory was lost with the previous container. This rebuild re-acquires "
        f"all {len(files)} raw FanDuel/NHL price payloads from `{REPO}@{COMMIT[:7]}`, the six SportsDataverse "
        "boxscore/roster/schedule assets, and regenerates both schedule metadata projections. **Every file hash "
        "equals the pin committed on September 26.** Two derived files, `manifest.json` and "
        "`outcomes/source_audit.json`, held retrieval metadata that was never committed, so they are replaced by "
        "deterministic files whose original hashes are recorded inside them; the downstream tools now pin the "
        "replacements.\n\n"
        f"Replacement pins: manifest `{report['replacement_pins']['manifest.json']}`, source audit "
        f"`{report['replacement_pins']['outcomes/source_audit.json']}`. No sporting values were read. "
        "Receipts are in the companion JSON.\n")
    print(json.dumps({k: report[k] for k in ("status", "raw_price_files_verified", "assets_verified",
                                             "projections_verified", "replacement_pins")}, indent=2))


if __name__ == "__main__":
    main()
