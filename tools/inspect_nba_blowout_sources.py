#!/usr/bin/env python3
"""Inspect pinned source coverage only; no blowout/remaining-minutes comparison."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/nba-blowout-source"
INPUTS = [
    ("nba_play_by_play_2025.csv.gz", "nba_stats_pbp", "534ceac1914ec3b38b51594748fcbddd34f3183a3c47dcf1c04ae53bbe04bcd1"),
    ("nba_lineups_2025.csv.gz", "nba_stats_game_lineups", "ff90b4e040664812ae741ef02718575ed826e3ac7cb7da7df63385842f5fef0d"),
]


def minute_check(p, l, player_cols):
    """Fixed source check, declared before minute differences: first six games
    by schedule date/game ID; all players within two seconds or source not ready.
    No margin, bench-role or outcome-effect selection occurs here.
    """
    bp = ROOT / "data/raw/nba-source-feasibility/player_boxscores_2025.csv"
    sp = ROOT / "data/raw/nba-source-feasibility/nba_stats_schedule_2024.csv"
    assert hashlib.sha256(bp.read_bytes()).hexdigest() == "7371d222692fee1c083913d813b125f885c4e53b6f3daaecb7270299913e9716"
    assert hashlib.sha256(sp.read_bytes()).hexdigest() == "ab5b7b5b978f0527a9e1ff4332b3e14d00c526964d2ea79b4d9f992f38eacb26"
    b = pd.read_csv(bp, dtype={"game_id":str}, low_memory=False)
    s = pd.read_csv(sp, dtype={"game_id":str}, low_memory=False)
    s = s.loc[s.game_id.str.startswith("00224")].sort_values(["game_date","game_id"]).drop_duplicates("game_id")
    games = s.game_id.head(6).tolist()
    checks = []
    for gid in games:
        idx = p.index[p.game_id.eq(gid)]
        pg = p.loc[idx].sort_values("order_index")
        lg = l.loc[pg.index]
        # NBA regulation periods are 720 seconds; each overtime is 300.
        elapsed = np.where(pg.period.le(4), (pg.period-1)*720 + 720-pg.seconds_remaining,
                           2880+(pg.period-5)*300+300-pg.seconds_remaining)
        delta = np.diff(np.append(elapsed, elapsed[-1]))
        totals = {}
        for lineup, seconds in zip(lg[player_cols].to_numpy(), delta):
            for pid in lineup:
                if pd.notna(pid):
                    totals[int(pid)] = totals.get(int(pid),0) + float(seconds)
        box = b.loc[b.game_id.eq(gid)]
        errors = []
        ids = set(box.person_id.astype(int))
        for row in box.itertuples():
            if pd.isna(row.minutes):
                seconds = 0
            else:
                mm, ss = row.minutes.split(":")
                seconds = int(mm)*60 + float(ss)
            derived = totals.get(int(row.person_id),0)
            if abs(derived-seconds) > 2:
                errors.append({"person_id":int(row.person_id),"box_seconds":seconds,
                               "lineup_seconds":derived,"difference_seconds":derived-seconds})
        checks.append({"game_id":gid,"player_box_rows":len(box),"negative_intervals":int((delta<0).sum()),
            "elapsed_end":float(elapsed[-1]), "unknown_lineup_player_ids":sorted(set(totals)-ids),
            "players_outside_two_second_tolerance":len(errors),"errors":errors})
    return {"definition":"First six regular-season games by schedule date/game ID; lineup following each event carries the interval to the next event; <=2-second player-level tolerance. No alternative alignment tried after the result.",
        "boxscore_sha256":hashlib.sha256(bp.read_bytes()).hexdigest(),
        "schedule_sha256":hashlib.sha256(sp.read_bytes()).hexdigest(),"games":checks,
        "ready_under_fixed_source_check":all(not x['errors'] and not x['negative_intervals'] and not x['unknown_lineup_player_ids'] for x in checks)}


def main(download):
    frames, sources = [], []
    for name, tag, pin in INPUTS:
        path = RAW / name
        url = f"https://github.com/sportsdataverse/sportsdataverse-data/releases/download/{tag}/{name}"
        if not path.exists() and download:
            RAW.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(url, timeout=120) as r:
                path.write_bytes(r.read())
        with path.open("rb") as f:
            digest = hashlib.file_digest(f, "sha256").hexdigest()
        assert digest == pin, "Publisher source changed; do not silently substitute"
        df = pd.read_csv(path, dtype={"game_id": str}, low_memory=False)
        reg = df.loc[df.game_id.str.startswith("00224")].copy()
        sources.append({"url": url, "sha256": digest, "bytes": path.stat().st_size,
            "rows": len(df), "games": int(df.game_id.nunique()), "regular_season_rows": len(reg),
            "regular_season_games": int(reg.game_id.nunique()), "columns": list(df.columns),
            "duplicate_game_action_keys": int(reg.duplicated(["game_id", "action_number"]).sum()),
            "exact_duplicate_rows": int(reg.duplicated().sum())})
        frames.append(reg)
    p, l = frames
    player_cols = [f"{side}_player_{i}" for side in ["home","away"] for i in range(1,6)]
    p, l = p.reset_index(drop=True), l.reset_index(drop=True)
    key_cols = ["game_id","action_number","period"]
    aligned = len(p) == len(l) and p[key_cols].equals(l[key_cols])
    # action_number repeats for shot/block and turnover/steal records. An initial
    # one-to-one key join correctly failed. Check the full publisher row sequence
    # explicitly; never silently join many-to-many or discard distinct events.
    good = l[player_cols].notna().all(axis=1) & l[player_cols].nunique(axis=1).eq(10) & l[player_cols].gt(0).all(axis=1)
    pbp_ids = [f"{side}_player_{i}" for side in ["off","def"] for i in range(1,6)]
    equal_sets = (np.sort(p[pbp_ids].to_numpy(),axis=1) == np.sort(l[player_cols].to_numpy(),axis=1)).all(axis=1) if aligned else None
    out = {"checked_at": datetime.now(timezone.utc).isoformat(), "sources": sources,
        "regular_season_game_sets_equal": set(p.game_id) == set(l.game_id),
        "publisher_game_action_period_row_sequences_equal": aligned,
        "pbp_duplicate_game_order_index_keys": int(p.duplicated(["game_id","order_index"]).sum()),
        "joined_rows_not_ten_distinct_player_ids": int((~good).sum()),
        "row_aligned_pbp_lineup_player_set_disagreements": int((~equal_sets).sum()) if aligned else None,
        "nonidentical_lineup_rows_sharing_game_action_key": int(l.drop_duplicates().duplicated(["game_id","action_number"]).sum()),
        "regular_season_substitution_events": int(p.is_substitution.sum()),
        "regular_season_missing_clock": int(p.seconds_remaining.isna().sum()),
        "fixed_six_game_minute_check": minute_check(p,l,player_cols) if aligned else None,
        "result": "Source coverage only. action_number is not a unique event key. Publisher-derived lineups require identity, event-order and integrated-minute validation against box scores before any conditional comparison.",
        "attribution": "NBA Stats-derived data distributed and processed by SportsDataverse; raw publisher files not redistributed."}
    target = ROOT / "reports/nba-blowout-source-check-2026-09-13.json"
    target.write_text(json.dumps(out, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k:v for k,v in out.items() if k != "sources"}, indent=2))
    print(json.dumps([{k:v for k,v in s.items() if k!='columns'} for s in sources], indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    main(parser.parse_args().download)
