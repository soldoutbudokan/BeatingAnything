#!/usr/bin/env python3
"""Fixed garbage-time reception screen. No odds, fit, or betting action.

Participation: FTN Data via nflverse, CC BY-SA 4.0. Published derived rows
retain this attribution/license. PBP: nflverse/nflfastR, CC BY 4.0.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.request

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/nfl-garbage-receptions"
DECL = ROOT / "docs/nfl-garbage-receptions-declaration-2026-09-13.md"
DECL_HASH = "46fa89e3dbd4b38a8e23e02f608c438b743571a1d491b188b0d0aca547ab72f4"
OUT = ROOT / "reports/nfl-garbage-receptions-2026-09-13.json"
PART_PINS = {
    2023: "ad01aeb4045ee19a4f086ff38b52b14c8f427d3401e529c3078a4545921650a9",
    2024: "b1f436a98b2a7759eb4ed1181e072a35c2666f9aeb356a49c943d28d6be6b0b9",
    2025: "59069adfee7b0f464befba8a5e8be331e523633cc6a7ab403d37bcbcdfbe66ac",
}
PBP_PINS = {
    2023: "4649804ee0f0a40b41e51ec75a1ce921949d7fab5459213488656b92f78560e8",
    2024: "23370d5d10f8104d80d46a1fc5e61f4f6f5a3263fe96fe2dd629913cfcb08c06",
    2025: "2f135887790a013fd004e609e37096bb4816d5cc80b9f19122e1bad478961978",
}
COLS = ["game_id", "play_id", "season", "season_type", "game_date",
        "posteam", "fixed_drive", "qtr", "quarter_seconds_remaining",
        "yardline_100", "down", "play_type", "score_differential",
        "receiver_player_id", "receiver_player_name", "air_yards",
        "complete_pass", "two_point_attempt"]
PART_COLS = ["nflverse_game_id", "play_id", "possession_team",
             "offense_players", "offense_positions", "n_offense"]
STRATA = ["receiver", "season", "clock_bin", "field_bin"]


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def source(path, pin, url, download):
    if not path.exists() and download:
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=120) as response:
            path.write_bytes(response.read())
    digest = sha(path)
    if digest != pin:
        raise ValueError(f"Changed source: {path}; do not replace the pinned study")
    return {"url": url, "sha256": digest, "bytes": path.stat().st_size}


def load(download):
    assert sha(DECL) == DECL_HASH, "Pre-comparison declaration changed"
    frames, parts, sources = [], [], []
    for season in PART_PINS:
        bp = ROOT / f"data/raw/nfl-wind-kicks/play_by_play_{season}.csv.gz"
        pp = RAW / f"pbp_participation_{season}.csv"
        sources.append(source(bp, PBP_PINS[season],
            f"https://github.com/nflverse/nflverse-data/releases/download/pbp/{bp.name}", download))
        sources.append(source(pp, PART_PINS[season],
            f"https://github.com/nflverse/nflverse-data/releases/download/pbp_participation/{pp.name}", download))
        b = pd.read_csv(bp, usecols=COLS, low_memory=False)
        assert set(b.season.unique()) == {season}
        assert not b.duplicated(["game_id", "play_id"]).any()
        p = pd.read_csv(pp, usecols=PART_COLS, low_memory=False).rename(
            columns={"nflverse_game_id": "game_id"})
        assert not p.duplicated(["game_id", "play_id"]).any()
        frames.append(b.loc[b.season_type.eq("REG")])
        parts.append(p)
    return pd.concat(frames, ignore_index=True), pd.concat(parts, ignore_index=True), sources


def snap_mask(df):
    return (df.play_type.isin(["pass", "run", "qb_kneel", "qb_spike"])
            & df.down.notna() & ~df.two_point_attempt.eq(1) & df.posteam.notna())


def lineup(row):
    if pd.isna(row.offense_players) or pd.isna(row.offense_positions):
        return None
    ids = row.offense_players.split(";")
    positions = row.offense_positions.split(";")
    if (row.n_offense != 11 or len(ids) != 11 or len(set(ids)) != 11
            or len(positions) != 11 or not all(re.fullmatch(r"00-\d{7}", s) for s in ids)):
        return None
    return dict(zip(ids, positions))


def prepare(pbp, part, sources):
    cohort_path = RAW / "frozen-cohort.json"
    if cohort_path.exists():
        raise FileExistsError("Frozen cohort exists; evaluate it without rewriting the declaration/cohort")
    snaps = pbp.loc[snap_mask(pbp)].sort_values(["game_id", "play_id"])
    keys = ["game_id", "posteam", "fixed_drive"]
    first = snaps.groupby(keys, sort=False).head(1)
    possible = first.loc[first.qtr.eq(4) & first.quarter_seconds_remaining.ge(360)]
    possible = possible.loc[possible.score_differential.le(-17)
                            | possible.score_differential.abs().le(8)]
    coverage = {"regular_season_games": int(pbp.game_id.nunique()),
                "regular_season_games_by_year": {str(k): int(v) for k,v in pbp.groupby('season').game_id.nunique().items()},
                "scrimmage_snaps": len(snaps), "candidate_drive_starts": len(possible)}
    joins = possible.merge(part, on=["game_id", "play_id"], how="left", validate="one_to_one", indicator=True)
    coverage["candidate_starts_missing_participation"] = int(joins._merge.ne("both").sum())
    # Team spelling is the same in these publishers; reject rather than guess on mismatch.
    valid = joins._merge.eq("both") & joins.posteam.eq(joins.possession_team)
    coverage["candidate_starts_team_mismatch"] = int((joins._merge.eq("both") & ~valid).sum())
    joins = joins.loc[valid].sort_values(["game_id", "play_id"])
    targets = snaps.loc[snaps.play_type.eq("pass") & snaps.receiver_player_id.notna()]
    role_totals = targets.groupby(["game_id", "posteam", "receiver_player_id"]).agg(
        targets=("air_yards", "size"), observed=("air_yards", "count"), depth_sum=("air_yards", "sum"))
    team_games = snaps.groupby(["season", "posteam", "game_id"]).game_date.first().reset_index()
    prior = {}
    roles = {}
    for (season, team), games in team_games.groupby(["season", "posteam"]):
        games = games.sort_values(["game_date", "game_id"])
        for row in games.itertuples():
            previous = games.loc[games.game_date.lt(row.game_date)].tail(3)
            if len(previous) < 3:
                continue
            prior[(row.game_id, team)] = previous.game_id.tolist()
            blocks = []
            for gid in previous.game_id:
                try:
                    blocks.append(role_totals.loc[(gid, team)])
                except KeyError:
                    pass
            if not blocks:
                continue
            combined = pd.concat(blocks).reset_index().groupby("receiver_player_id").agg(
                targets=("targets", "sum"), observed=("observed", "sum"),
                depth_sum=("depth_sum", "sum"), target_games=("targets", "size"))
            selected = combined.loc[combined.observed.ge(10) & combined.observed.div(combined.targets).ge(.9)
                                    & combined.depth_sum.div(combined.observed).le(8)
                                    & combined.target_games.ge(2)]
            roles[(row.game_id, team)] = selected.to_dict("index")
    rows, seen, skipped = [], set(), Counter()
    for row in joins.itertuples():
        people = lineup(row)
        if people is None:
            skipped["invalid_lineup"] += 1
            continue
        if pd.isna(row.yardline_100) or not 0 <= row.yardline_100 <= 100:
            skipped["missing_or_invalid_field_position"] += 1
            continue
        role = roles.get((row.game_id, row.posteam), {})
        if (row.game_id, row.posteam) not in prior:
            skipped["fewer_than_three_prior_team_games"] += 1
            continue
        selected = [(pid, pos) for pid, pos in people.items() if pos in {"WR", "TE", "RB", "FB"} and pid in role]
        if not selected:
            skipped["no_qualifying_active_short_target_receiver"] += 1
        for pid, pos in selected:
            if (row.game_id, pid) in seen:
                skipped["later_player_game_trigger"] += 1
                continue
            seen.add((row.game_id, pid))
            stats = role[pid]
            rows.append({"game_id": row.game_id, "season": int(row.season), "game_date": row.game_date,
                         "team": row.posteam, "receiver": pid, "position": pos,
                         "trigger_play_id": int(row.play_id), "fixed_drive": int(row.fixed_drive),
                         "clock_seconds": int(row.quarter_seconds_remaining),
                         "clock_bin": int(row.quarter_seconds_remaining // 180),
                         "yardline_100": float(row.yardline_100), "field_bin": int(row.yardline_100 // 20),
                         "score_differential": int(row.score_differential),
                         "exposed": bool(row.score_differential <= -17),
                         "prior_games": prior[(row.game_id, row.posteam)],
                         "prior_targets": int(stats["targets"]), "prior_depth_observations": int(stats["observed"]),
                         "prior_mean_depth": stats["depth_sum"] / stats["observed"],
                         "prior_target_games": int(stats["target_games"])})
    coverage["skipped"] = dict(skipped)
    coverage["frozen_receiver_games"] = len(rows)
    coverage["exposed_receiver_games_before_matching"] = sum(r["exposed"] for r in rows)
    frozen = {"prepared_at": now(), "declaration_sha256": DECL_HASH, "sources": sources,
              "coverage": coverage, "rows": rows}
    dump(cohort_path, frozen)
    dump(RAW / "freeze.json", {"prepared_at": frozen["prepared_at"], "cohort_sha256": sha(cohort_path)})
    print(json.dumps({"phase": "frozen_before_outcome_comparison", "sha256": sha(cohort_path), "coverage": coverage}))


def outcomes(pbp, rows):
    snaps = pbp.loc[snap_mask(pbp) & pbp.qtr.le(4)]
    groups = {key: value for key, value in snaps.groupby(["game_id", "posteam"])}
    result = []
    for row in rows:
        block = groups[(row["game_id"], row["team"])]
        remain = block.loc[block.play_id.gt(row["trigger_play_id"])]
        catches = remain.complete_pass.eq(1) & remain.receiver_player_id.eq(row["receiver"])
        result.append({**row, "remaining_team_snaps": len(remain), "remaining_receptions": int(catches.sum())})
    return pd.DataFrame(result)


def compare(rows):
    control = rows.loc[~rows.exposed].copy()
    agg = control.groupby(STRATA).agg(control_windows=("game_id", "size"),
        control_snaps=("remaining_team_snaps", "sum"), control_catches=("remaining_receptions", "sum"))
    agg["control_rate"] = agg.control_catches / agg.control_snaps
    agg["control_mean_catches"] = agg.control_catches / agg.control_windows
    agg["control_mean_snaps"] = agg.control_snaps / agg.control_windows
    exposed = rows.loc[rows.exposed].merge(agg.reset_index(), on=STRATA, how="left", validate="many_to_one")
    matched = exposed.loc[exposed.control_rate.notna()].copy()
    matched["expected_catches_at_control_rate"] = matched.remaining_team_snaps * matched.control_rate
    # Same player appears only once per game, so no control can share that exposure's game.
    keys = matched[STRATA].drop_duplicates()
    used_control = control.merge(keys, on=STRATA, how="inner", validate="many_to_one")
    obs = float(matched.remaining_receptions.sum())
    snaps = int(matched.remaining_team_snaps.sum())
    expected = float(matched.expected_catches_at_control_rate.sum())
    relative = obs / expected - 1 if expected else None
    summary = {"matched_exposures": len(matched), "matched_exposed_games": int(matched.game_id.nunique()),
        "matched_receivers": int(matched.receiver.nunique()), "unique_matched_control_windows": len(used_control),
        "unique_matched_control_games": int(used_control.game_id.nunique()),
        "unmatched_exposures": len(exposed) - len(matched), "exposed_receptions": int(obs),
        "exposed_team_snap_denominator": snaps, "control_rate_expected_receptions": expected,
        "exposed_rate": obs/snaps if snaps else None, "standardized_control_rate": expected/snaps if snaps else None,
        "relative_increase": relative,
        "exposed_mean_remaining_receptions": float(matched.remaining_receptions.mean()) if len(matched) else None,
        "exposed_mean_remaining_team_snaps": float(matched.remaining_team_snaps.mean()) if len(matched) else None,
        "standardized_control_mean_receptions": float(matched.control_mean_catches.mean()) if len(matched) else None,
        "standardized_control_mean_team_snaps": float(matched.control_mean_snaps.mean()) if len(matched) else None,
        "matched_zero_remaining_snap_windows": int(matched.remaining_team_snaps.eq(0).sum()),
        "matched_zero_remaining_catch_windows": int(matched.remaining_receptions.eq(0).sum()),
        "top_receiver_exposure_counts": {k:int(v) for k,v in matched.receiver.value_counts().head(10).items()}}
    game = matched.groupby("game_id")[["remaining_receptions", "expected_catches_at_control_rate"]].sum().to_numpy()
    rng = np.random.default_rng(20260913)
    draws = []
    if len(game):
        for _ in range(2000):
            totals = game[rng.integers(0, len(game), len(game))].sum(axis=0)
            if totals[1] > 0:
                draws.append(totals[0]/totals[1]-1)
    summary["descriptive_fixed_control_game_bootstrap_95_interval"] = np.quantile(draws, [.025,.975]).tolist() if draws else None
    summary["decision"] = ("unresolved_insufficient_matched_exposures" if len(matched) < 200 or relative is None
                            else "sport_side_screen_pass" if relative >= .2 else "sport_side_screen_fail")
    by_year = []
    for season in PART_PINS:
        y = matched.loc[matched.season.eq(season)]
        n = int(y.remaining_team_snaps.sum())
        r = int(y.remaining_receptions.sum())
        e = float(y.expected_catches_at_control_rate.sum())
        by_year.append({"season": season, "exposures": len(y), "games": int(y.game_id.nunique()),
                        "receptions": r, "team_snaps": n, "standardized_expected_catches": e,
                        "relative_increase": r/e-1 if e else None})
    summary["by_year"] = by_year
    return summary, matched, agg.reset_index()


def evaluate(pbp, sources):
    frozen_path = RAW / "frozen-cohort.json"
    freeze = json.loads((RAW / "freeze.json").read_text())
    assert sha(frozen_path) == freeze["cohort_sha256"]
    frozen = json.loads(frozen_path.read_text())
    assert frozen["declaration_sha256"] == DECL_HASH and frozen["sources"] == sources
    rows = outcomes(pbp, frozen["rows"])
    assert not rows.duplicated(["receiver", "game_id"]).any()
    summary, matched, controls = compare(rows)
    report = {"evaluated_at": now(), "prepared_at": frozen["prepared_at"],
        "declaration_sha256": DECL_HASH, "frozen_cohort_sha256": freeze["cohort_sha256"],
        "attribution": "Participation and derived rows: FTN Data via nflverse, CC BY-SA 4.0; PBP: nflverse/nflfastR, CC BY 4.0",
        "sources": sources, "coverage": frozen["coverage"], "summary": summary,
        "limitations": ["Retrospective snap lineup is not timely pre-snap knowledge; trigger-play outcome excluded.",
            "Selected players remain in all-team-snap denominators after substitutions.",
            "Fixed-control bootstrap omits control estimation uncertainty and repeated-player dependence across games.",
            "Clock/field bins are coarse; deficit, opponent, QB changes and player selection can confound the comparison.",
            "No live FanDuel market, price or posting latency was observed; this is not a betting edge."],
        "rows": rows.to_dict("records"), "matched_exposures": matched.to_dict("records"),
        "control_strata": json.loads(controls.to_json(orient="records"))}
    dump(OUT, report)
    print(json.dumps(summary, indent=2))


def self_test():
    base = {"game_id":"g", "posteam":"T", "qtr":4, "two_point_attempt":0,
            "down":1, "play_type":"pass", "receiver_player_id":"p", "complete_pass":1}
    pbp = pd.DataFrame([{**base,"play_id":1}, {**base,"play_id":2},
        {**base,"play_id":3,"receiver_player_id":"other"},
        {**base,"play_id":4,"play_type":"no_play"}, {**base,"play_id":5,"qtr":5},
        {**base,"play_id":6,"two_point_attempt":1},
        {**base,"play_id":7,"play_type":"qb_kneel","complete_pass":0}])
    row = {"game_id":"g","team":"T","receiver":"p","trigger_play_id":1}
    r = outcomes(pbp,[row]).iloc[0]
    assert r.remaining_team_snaps == 3 and r.remaining_receptions == 1
    assert outcomes(pbp,[{**row,"trigger_play_id":8}]).iloc[0].remaining_team_snaps == 0
    ids = [f"00-{i:07d}" for i in range(11)]
    record = pd.Series({"offense_players":";".join(ids),"offense_positions":";".join(["WR"]*11),"n_offense":11})
    assert len(lineup(record)) == 11
    record.offense_players = ";".join(ids[:-1]+[ids[0]])
    assert lineup(record) is None
    print("Four state/lineup checks passed")


def source_check(pbp, part):
    """Post-screen source consistency diagnostic; never repairs or reselects rows."""
    completed = pbp.loc[snap_mask(pbp) & pbp.complete_pass.eq(1)].merge(
        part, on=["game_id", "play_id"], how="left", validate="one_to_one")
    present = completed.offense_players.notna()
    available = completed.loc[present]
    bad = available.loc[[pid not in ids.split(";") for pid, ids in
                         zip(available.receiver_player_id, available.offense_players)]]
    rows = pd.DataFrame(json.loads(OUT.read_text())["rows"])
    triggers = set(zip(rows.game_id, rows.trigger_play_id))
    selected_catch_windows = []
    for b in bad.itertuples():
        affected = rows.loc[rows.game_id.eq(b.game_id) & rows.team.eq(b.posteam)
                            & rows.trigger_play_id.lt(b.play_id) & rows.receiver.eq(b.receiver_player_id)]
        selected_catch_windows.extend(affected[["game_id", "receiver", "exposed"]].to_dict("records"))
    result = {"checked_at": now(), "primary_report_sha256": sha(OUT),
        "completed_reception_rows": len(completed), "missing_participation_rows": int((~present).sum()),
        "completed_receiver_missing_from_lineup": len(bad),
        "discordant_rows_at_frozen_trigger": sum((b.game_id,b.play_id) in triggers for b in bad.itertuples()),
        "selected_receiver_catch_windows_affected": selected_catch_windows,
        "rows": bad[["game_id","play_id","receiver_player_id","receiver_player_name"]].to_dict("records"),
        "frozen_windows_in_discordant_games": rows.loc[rows.game_id.isin(bad.game_id)][
            ["game_id","receiver","exposed"]].to_dict("records"),
        "interpretation": "No repair or outcome re-selection. Zero direct selected-catch overlap does not rule out omitted eligible receivers or incorrect identity at other snaps in these games.",
        "attribution": "FTN Data via nflverse, CC BY-SA 4.0; nflverse/nflfastR PBP, CC BY 4.0"}
    dump(ROOT / "reports/nfl-garbage-receptions-source-check-2026-09-13.json", result)
    print(json.dumps({k:v for k,v in result.items() if k not in {"rows","frozen_windows_in_discordant_games"}}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--source-check", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    if args.prepare or args.evaluate or args.source_check:
        if args.prepare and args.evaluate:
            parser.error("Freeze cohort and evaluate in separate calls")
        pbp, part, sources = load(args.download)
        if args.prepare:
            prepare(pbp, part, sources)
        elif args.evaluate:
            evaluate(pbp, sources)
        if args.source_check:
            source_check(pbp, part)
