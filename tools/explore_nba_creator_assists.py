#!/usr/bin/env python3
"""Fixed, descriptive 2024-25 creator-absence assist screen; no price model.

Run prepare before the injury join, then evaluate once the fixed PDF acquisition
has finished. Raw reports and the prior-role manifest stay in ignored data/raw.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import unicodedata

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/nba-creator-assists"
SOURCE = ROOT / "data/raw/nba-source-feasibility"
DECLARATION = ROOT / "docs/nba-creator-assists-screen-declaration-2026-09-13.md"
DECLARATION_HASH = "6589cc9a2c58f8317488aa88fd17ec5ddd3c5359f8c5524fd0730ebc462400f3"
INPUTS = {
    "player_boxscores_2025.csv": "7371d222692fee1c083913d813b125f885c4e53b6f3daaecb7270299913e9716",
    "nba_stats_schedule_2024.csv": "ab5b7b5b978f0527a9e1ff4332b3e14d00c526964d2ea79b4d9f992f38eacb26",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def normalized(value):
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", text.lower())


def minutes(value):
    if pd.isna(value) or value == "":
        return 0.0
    parts = str(value).split(":")
    return float(parts[0]) + (float(parts[1]) / 60 if len(parts) == 2 else 0)


def inputs():
    assert digest(DECLARATION) == DECLARATION_HASH, "Declaration changed"
    for name, expected in INPUTS.items():
        assert digest(SOURCE / name) == expected, f"Input changed: {name}"
    schedule = pd.read_csv(SOURCE / "nba_stats_schedule_2024.csv", dtype={"game_id": str})
    schedule = schedule[schedule.game_id.str.startswith("00224")].copy()
    boxes = pd.read_csv(SOURCE / "player_boxscores_2025.csv", dtype={"game_id": str})
    boxes = boxes[boxes.game_id.str.startswith("00224")].copy()
    boxes["minutes_n"] = boxes.minutes.map(minutes)
    boxes["assists"] = boxes.assists.fillna(0).astype(int)
    assert not boxes.duplicated(["game_id", "person_id"]).any()
    assert len(schedule) == 2460 and schedule.game_id.nunique() == 1230
    groups = {(str(game), int(team)): b.set_index("person_id")
              for (game, team), b in boxes.groupby(["game_id", "team_id"])}
    complete = {}
    for row in schedule.itertuples():
        group = groups.get((row.game_id, int(row.team_id)))
        complete[row.game_id, int(row.team_id)] = (
            group is not None and int(group.assists.sum()) == int(row.ast)
            and abs(float(group.minutes_n.sum()) - float(row.min)) <= 1.0
        )
    return schedule, boxes, groups, complete


def player_value(group, player, column):
    return float(group.at[player, column]) if player in group.index else 0.0


def prepare():
    schedule, boxes, groups, complete = inputs()
    dates = dict(zip(schedule.game_id, schedule.game_date))
    boxes["game_date"] = boxes.game_id.map(dates)
    histories = {int(p): b[["game_date", "team_id"]].to_dict("records")
                 for p, b in boxes.groupby("person_id")}
    names = {int(r.person_id): f"{r.first_name} {r.family_name}"
             for r in boxes.itertuples()}
    roles, attrition = [], Counter()
    for team, games in schedule.groupby("team_id"):
        team = int(team)
        games = games.sort_values(["game_date", "game_id"])
        for current in games.itertuples():
            attrition["team_games"] += 1
            report_date = (datetime.fromisoformat(current.game_date) - timedelta(days=1)).date().isoformat()
            prior = games[games.game_date < report_date].tail(10)
            if len(prior) < 10:
                attrition["fewer_than_ten_prior_games"] += 1
                continue
            ids = list(prior.game_id)
            if not all(complete[gid, team] for gid in ids):
                attrition["incomplete_prior_boxscore"] += 1
                continue
            latest = groups[ids[-1], team]
            candidates = []
            first_date = str(prior.iloc[0].game_date)
            for player in latest.index:
                player = int(player)
                # Exclude report-day games here too: their completion time is unknown.
                if any(x["team_id"] != team and first_date <= x["game_date"] < report_date
                       for x in histories[player]):
                    continue
                prior_minutes = [player_value(groups[gid, team], player, "minutes_n") for gid in ids]
                if sum(m > 0 for m in prior_minutes) < 8 or sum(prior_minutes) / 10 < 20:
                    continue
                ast = sum(player_value(groups[gid, team], player, "assists") for gid in ids)
                candidates.append((ast, player))
            candidates.sort(key=lambda x: (-x[0], x[1]))
            if len(candidates) < 2 or candidates[0][0] < 50 or candidates[1][0] < 25:
                attrition["no_eligible_creator_secondary_pair"] += 1
                continue
            creator, secondary = candidates[0][1], candidates[1][1]
            controls = [gid for gid in ids if player_value(groups[gid, team], creator, "minutes_n") > 0]
            if len(controls) < 5:
                attrition["fewer_than_five_creator_present_controls"] += 1
                continue
            roles.append({
                "game_id": current.game_id, "game_date": current.game_date,
                "report_date": report_date, "team_id": team,
                "team": current.team_abbreviation, "creator_id": creator,
                "creator": names[creator], "secondary_id": secondary, "secondary": names[secondary],
                "prior_game_ids": ids, "control_game_ids": controls,
                "baseline_assists": float(np.mean([player_value(groups[gid, team], secondary, "assists") for gid in controls])),
                "baseline_minutes": float(np.mean([player_value(groups[gid, team], secondary, "minutes_n") for gid in controls])),
            })
    payload = {"prepared_at_utc": now(), "declaration_sha256": DECLARATION_HASH,
               "input_sha256": INPUTS, "attrition": dict(attrition), "roles": roles}
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / "prior-role-cohort.json"
    if path.exists():
        old = json.loads(path.read_text())
        assert old["roles"] == roles and old["attrition"] == dict(attrition), "Refusing changed role cohort"
        print(json.dumps({"roles": len(roles), "existing_cohort_sha256": digest(path)}))
    else:
        path.write_text(json.dumps(payload, indent=2) + "\n")
        print(json.dumps({"roles": len(roles), "prepared_at_utc": payload["prepared_at_utc"],
                          "cohort_sha256": digest(path), "attrition": dict(attrition)}))


def parse_report(text, team_names):
    """Read raw PDF text in source row order, preserving context across pages."""
    team_pattern = re.compile("|".join(re.escape(t) for t in sorted(team_names, key=len, reverse=True)))
    status_pattern = re.compile(r"\b(Out|Doubtful|Questionable|Probable|Available)\b")
    game_date = team = matchup = None
    rows, unsubmitted, diagnostics = {}, set(), Counter()
    page_numbers = re.findall(r"Page (\d+) of (\d+)", text)
    if not page_numbers or {int(p) for p, _ in page_numbers} != set(range(1, int(page_numbers[0][1]) + 1)):
        raise ValueError("Incomplete PDF page sequence")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("Injury Report:", "Page ", "Game Date")):
            continue
        date_match = re.match(r"(\d{2}/\d{2}/\d{4})\s+", line)
        if date_match:
            game_date = datetime.strptime(date_match[1], "%m/%d/%Y").date().isoformat()
            team = matchup = None
            line = line[date_match.end():]
        line = re.sub(r"^\d{2}:\d{2}\s+\(ET\)\s+", "", line)
        match = re.match(r"([A-Z]{3}@[A-Z]{3})\s+", line)
        if match:
            matchup = match[1]
            team = None
            line = line[match.end():]
        match = team_pattern.match(line)
        if match:
            team = int(team_names[match[0]])
            line = line[match.end():].strip()
        if "NOT YET SUBMITTED" in line:
            if team is not None and game_date is not None:
                unsubmitted.add((game_date, team))
            continue
        status = status_pattern.search(line)
        if not status:
            continue
        name = line[:status.start()].strip()
        if "," not in name:
            continue
        if game_date is None or team is None or matchup is None:
            diagnostics["status_rows_missing_context"] += 1
            continue
        key = (game_date, team, normalized(name))
        value = {"status": status[1], "matchup": matchup, "name": name}
        if key in rows and rows[key] != value:
            rows[key] = {"status": "Ambiguous", "matchup": matchup, "name": name}
            diagnostics["conflicting_status_rows"] += 1
        else:
            rows[key] = value
    diagnostics["parsed_player_rows"] = len(rows)
    diagnostics["unsubmitted_team_games"] = len(unsubmitted)
    return rows, unsubmitted, diagnostics


def evaluate():
    schedule, boxes, groups, complete = inputs()
    cohort_path = RAW / "prior-role-cohort.json"
    cohort = json.loads(cohort_path.read_text())
    assert cohort["declaration_sha256"] == DECLARATION_HASH
    manifest = json.loads((RAW / "injury-report-manifest.json").read_text())
    assert len(manifest["records"]) == 163, "Acquisition must finish before comparison"
    assert all(r["status"] in {"validated", "missing_archive_date", "failed"} for r in manifest["records"])
    teams = dict(zip(schedule.team_name, schedule.team_id))
    aliases = {int(r.person_id): normalized(f"{r.family_name}, {r.first_name}") for r in boxes.itertuples()}
    reports, parser_counts = {}, Counter()
    for record in manifest["records"]:
        if record["status"] != "validated":
            continue
        path = ROOT / record["pdf_path"]
        assert digest(path) == record["sha256"]
        assert len(record["header_issue_iso_local"]) == 1
        assert record["header_issue_iso_local"][0][:10] == record["selected_date"]
        text = (ROOT / record["text_path"]).read_text()
        rows, unsubmitted, diagnostics = parse_report(text, teams)
        reports[record["selected_date"]] = (rows, unsubmitted, record)
        parser_counts.update(diagnostics)
    attrition, exposed = Counter(), []
    for role in cohort["roles"]:
        attrition["prior_role_eligible"] += 1
        if role["report_date"] not in reports:
            attrition["missing_validated_preceding_day_report"] += 1
            continue
        rows, unsubmitted, record = reports[role["report_date"]]
        key = (role["game_date"], role["team_id"])
        if key in unsubmitted:
            attrition["team_not_yet_submitted"] += 1
            continue
        entry = rows.get((*key, aliases[role["creator_id"]]))
        if entry is None:
            attrition["creator_not_explicitly_listed_unknown_status"] += 1
            continue
        if role["team"] not in entry["matchup"].split("@"):
            attrition["ambiguous_matchup"] += 1
            continue
        if entry["status"] != "Out":
            attrition["creator_listed_" + entry["status"]] += 1
            continue
        secondary_entry = rows.get((*key, aliases[role["secondary_id"]]))
        if secondary_entry and secondary_entry["status"] in {"Out", "Doubtful", "Ambiguous"}:
            attrition["secondary_explicitly_out_doubtful_or_ambiguous"] += 1
            continue
        outcome_key = (role["game_id"], role["team_id"])
        if not complete[outcome_key]:
            attrition["incomplete_outcome_boxscore"] += 1
            continue
        group = groups[outcome_key]
        secondary = role["secondary_id"]
        assists = player_value(group, secondary, "assists")
        mins = player_value(group, secondary, "minutes_n")
        exposed.append({**role, "report_issue_local": record["header_issue_iso_local"][0],
                        "report_sha256": record["sha256"], "assists": assists, "minutes": mins,
                        "assist_difference": assists - role["baseline_assists"],
                        "minute_difference": mins - role["baseline_minutes"],
                        "secondary_report_status": secondary_entry["status"] if secondary_entry else "not listed; unknown",
                        "secondary_row_present": secondary in group.index,
                        "creator_actually_played": player_value(group, role["creator_id"], "minutes_n") > 0})
    n = len(exposed)
    if not n:
        raise ValueError("No exposures; investigate parser/source without modifying selection")
    frame = pd.DataFrame(exposed)
    delta = float(frame.assist_difference.mean())
    cluster = frame.groupby("team_id").assist_difference.agg(["sum", "count"])
    rng = np.random.default_rng(1729)
    draws = rng.integers(0, len(cluster), size=(5000, len(cluster)))
    boot = cluster["sum"].to_numpy()[draws].sum(axis=1) / cluster["count"].to_numpy()[draws].sum(axis=1)
    metrics = {
        "exposed_player_games": n, "teams": int(frame.team_id.nunique()),
        "secondary_players": int(frame.secondary_id.nunique()),
        "unique_baseline_player_games": len({(r["secondary_id"], g) for r in exposed for g in r["control_game_ids"]}),
        "mean_assists": float(frame.assists.mean()), "baseline_mean_assists": float(frame.baseline_assists.mean()),
        "mean_assist_difference": delta, "descriptive_team_cluster_95_interval": np.quantile(boot, [.025, .975]).tolist(),
        "mean_minutes": float(frame.minutes.mean()), "baseline_mean_minutes": float(frame.baseline_minutes.mean()),
        "assists_per_36": float(frame.assists.sum() * 36 / frame.minutes.sum()),
        "baseline_assists_per_36": float(frame.baseline_assists.sum() * 36 / frame.baseline_minutes.sum()),
        "secondary_zero_minute_games": int((frame.minutes == 0).sum()),
        "secondary_absent_rows_retained_zero": int((~frame.secondary_row_present).sum()),
        "creator_out_previous_day_but_actually_played": int(frame.creator_actually_played.sum()),
    }
    decision = "unresolved: fewer than 100 exposed player-games" if n < 100 else (
        "sport-side screen passed; no pricing evidence" if delta >= 1 else "sport-side screen failed: mean increase below one assist")
    result = {"generated_at_utc": now(), "declaration_sha256": DECLARATION_HASH,
              "prior_role_cohort_sha256": digest(cohort_path), "roles_prepared_at_utc": cohort["prepared_at_utc"],
              "input_sha256": INPUTS, "report_status_counts": dict(Counter(r["status"] for r in manifest["records"])),
              "role_attrition": cohort["attrition"], "exposure_attrition": dict(attrition),
              "parser_counts": dict(parser_counts), "metrics": metrics, "decision": decision,
              "observations": exposed, "source_manifest": manifest}
    target = ROOT / "reports/nba-creator-assists-2026-09-13.json"
    target.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"decision": decision, "metrics": metrics, "exposure_attrition": dict(attrition)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "evaluate"])
    args = parser.parse_args()
    prepare() if args.phase == "prepare" else evaluate()
