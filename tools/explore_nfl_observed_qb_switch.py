#!/usr/bin/env python3
"""Fixed QB-switch target-usage exploration; no odds, fitted model or betting.

Derived participation rows: FTN Data via nflverse, CC BY-SA 4.0.
PBP: nflverse/nflfastR, CC BY 4.0.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
import pandas as pd

from explore_nfl_garbage_receptions import (
    ROOT, PBP_PINS, PART_PINS, PART_COLS, source, sha, now, dump,
    snap_mask, lineup,
)

DECL = ROOT / "docs/nfl-observed-qb-switch-declaration-2026-09-13.md"
DECL_HASH = "06c7d97d3691bc70e2d96b30da2bb58717440e61773840ddb86c4baa567753e3"
RAW = ROOT / "data/raw/nfl-observed-qb-switch"
OUT = ROOT / "reports/nfl-observed-qb-switch-2026-09-13.json"
COLS = ["game_id", "play_id", "season", "season_type", "game_date", "posteam",
        "qtr", "game_seconds_remaining", "down", "play_type", "score_differential",
        "receiver_player_id", "air_yards", "complete_pass", "two_point_attempt"]
STRATA = ["team", "season", "quarter", "score_band"]


def load(download=False):
    assert sha(DECL) == DECL_HASH, "Pre-comparison declaration changed"
    bs, ps, sources = [], [], []
    for season in PBP_PINS:
        bp = ROOT / f"data/raw/nfl-wind-kicks/play_by_play_{season}.csv.gz"
        pp = ROOT / f"data/raw/nfl-garbage-receptions/pbp_participation_{season}.csv"
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
        bs.append(b.loc[b.season_type.eq("REG")])
        ps.append(p)
    return pd.concat(bs, ignore_index=True), pd.concat(ps, ignore_index=True), sources


def make_snaps(pbp, part):
    snaps = pbp.loc[snap_mask(pbp) & pbp.qtr.le(4)].sort_values(["game_id", "play_id"])
    joined = snaps.merge(part, on=["game_id", "play_id"], how="left", validate="one_to_one", indicator=True)
    people, qbs, status = [], [], Counter()
    for r in joined.itertuples():
        if r.posteam != r.possession_team:
            persons = None
            status["missing_or_mismatched_participation_team"] += 1
        else:
            persons = lineup(r)
            if persons is None:
                status["invalid_eleven_player_lineup"] += 1
        qb_list = [pid for pid, pos in persons.items() if pos == "QB"] if persons else []
        if persons:
            status[f"valid_lineup_with_{len(qb_list)}_qbs"] += 1
        people.append(persons)
        qbs.append(qb_list[0] if len(qb_list) == 1 else None)
    joined["people"] = people
    joined["sole_qb"] = qbs
    return joined.sort_values(["game_id", "play_id"]), dict(status)


def roles_before_game(snaps):
    targets = snaps.loc[snaps.play_type.eq("pass") & snaps.receiver_player_id.notna()]
    totals = targets.groupby(["game_id", "posteam", "receiver_player_id"]).agg(
        targets=("air_yards", "size"), observed=("air_yards", "count"), depth_sum=("air_yards", "sum"))
    games = snaps.groupby(["season", "posteam", "game_id"]).game_date.first().reset_index()
    prior, roles = {}, {}
    for (_, team), block in games.groupby(["season", "posteam"]):
        block = block.sort_values(["game_date", "game_id"])
        for r in block.itertuples():
            previous = block.loc[block.game_date.lt(r.game_date)].tail(3)
            if len(previous) != 3:
                continue
            key = (r.game_id, team)
            prior[key] = previous.game_id.tolist()
            pieces = []
            for gid in previous.game_id:
                try:
                    pieces.append(totals.loc[(gid, team)])
                except KeyError:
                    pass
            if not pieces:
                roles[key] = {}
                continue
            agg = pd.concat(pieces).reset_index().groupby("receiver_player_id").agg(
                targets=("targets", "sum"), observed=("observed", "sum"),
                depth_sum=("depth_sum", "sum"), target_games=("targets", "size"))
            eligible = agg.loc[agg.observed.ge(10) & agg.observed.div(agg.targets).ge(.9)
                               & agg.depth_sum.div(agg.observed).le(8) & agg.target_games.ge(2)]
            roles[key] = eligible.to_dict("index")
    return prior, roles


def score_band(value):
    return ("trailing_17plus" if value <= -17 else "trailing_9to16" if value < -8
            else "within_8" if value <= 8 else "leading_9to16" if value <= 16 else "leading_17plus")


def prepare(pbp, part, sources):
    cohort_path = RAW / "frozen-cohort.json"
    if cohort_path.exists():
        raise FileExistsError("Cohort already frozen; evaluate it without replacing it")
    snaps, status = make_snaps(pbp, part)
    prior, roles = roles_before_game(snaps)
    rows, skipped = [], Counter()
    for (gid, team), block in snaps.groupby(["game_id", "posteam"], sort=False):
        block = block.reset_index(drop=True)
        exposure_seen, control_seen = False, set()
        records = list(block.itertuples())
        for i in range(10, len(records)):
            r = records[i]
            qbs = [p.sole_qb for p in records[i-10:i]]
            if r.sole_qb is None or any(q is None for q in qbs) or len(set(qbs)) != 1:
                skipped["no_ten_consecutive_verified_same_qb_snaps"] += 1
                continue
            if pd.isna(r.game_seconds_remaining) or r.game_seconds_remaining < 300 or pd.isna(r.score_differential):
                skipped["clock_below_300_or_missing_clock_score"] += 1
                continue
            exposed = r.sole_qb != qbs[0]
            band = score_band(r.score_differential)
            control_key = (r.qtr, band)
            if exposed:
                if exposure_seen:
                    skipped["later_qualifying_qb_change"] += 1
                    continue
                exposure_seen = True
                skipped["first_qb_changes_before_receiver_eligibility"] += 1
            elif control_key in control_seen:
                continue
            if (gid, team) not in prior:
                skipped[f"{'exposed' if exposed else 'control'}_fewer_than_three_prior_games"] += 1
                continue
            role = roles[(gid, team)]
            selected = sorted(pid for pid, pos in r.people.items() if pos in {"WR", "TE", "RB", "FB"} and pid in role)
            if not selected:
                skipped[f"{'exposed' if exposed else 'control'}_empty_short_receiver_pool"] += 1
                continue
            if not exposed:
                control_seen.add(control_key)
            player_roles = [{"receiver": pid, "position": r.people[pid],
                "prior_targets": int(role[pid]["targets"]),
                "prior_observed_air_yards": int(role[pid]["observed"]),
                "prior_target_games": int(role[pid]["target_games"]),
                "prior_mean_air_yards": role[pid]["depth_sum"] / role[pid]["observed"]} for pid in selected]
            rows.append({"game_id": gid, "team": team, "season": int(r.season),
                "game_date": r.game_date, "trigger_play_id": int(r.play_id), "quarter": int(r.qtr),
                "clock_seconds": int(r.game_seconds_remaining), "score_differential": int(r.score_differential),
                "score_band": band, "exposed": exposed, "previous_qb": qbs[0], "observed_qb": r.sole_qb,
                "prior_games": prior[(gid, team)], "receivers": selected, "receiver_roles": player_roles,
                "pre_play_ids": [int(p.play_id) for p in records[i-10:i]]})
    assert len({(r["game_id"], r["team"]) for r in rows if r["exposed"]}) == sum(r["exposed"] for r in rows)
    coverage = {"regular_season_games": int(pbp.game_id.nunique()),
        "games_by_year": {str(k): int(v) for k,v in pbp.groupby("season").game_id.nunique().items()},
        "regulation_team_snaps": len(snaps), "participation_status": status, "selection_counts": dict(skipped),
        "frozen_windows": len(rows), "exposed_windows": sum(r["exposed"] for r in rows),
        "control_windows": sum(not r["exposed"] for r in rows)}
    result = {"prepared_at": now(), "declaration_sha256": DECL_HASH, "sources": sources,
              "coverage": coverage, "rows": rows}
    dump(cohort_path, result)
    dump(RAW / "freeze.json", {"prepared_at": result["prepared_at"], "cohort_sha256": sha(cohort_path)})
    print(json.dumps({"phase": "frozen_before_outcome_comparison", "cohort_sha256": sha(cohort_path),
                      "coverage": coverage}, indent=2))


def window_values(block, receivers):
    targets = block.play_type.eq("pass") & block.receiver_player_id.isin(receivers)
    return {"snaps": len(block), "targets": int(targets.sum()),
            "receptions": int((targets & block.complete_pass.eq(1)).sum())}


def outcomes(snaps, rows):
    groups = {k: b for k, b in snaps.groupby(["game_id", "posteam"])}
    result = []
    for row in rows:
        b = groups[(row["game_id"], row["team"])]
        pre = b.loc[b.play_id.lt(row["trigger_play_id"])].tail(10)
        post = b.loc[b.play_id.gt(row["trigger_play_id"])].head(10)
        assert pre.play_id.astype(int).tolist() == row["pre_play_ids"]
        values = {f"{period}_{k}": v for period, frame in [("pre", pre), ("post", post)]
                  for k,v in window_values(frame, row["receivers"]).items()}
        result.append({**row, **values, "post_play_ids": post.play_id.astype(int).tolist(),
            "post_same_observed_qb_snaps": int(post.sole_qb.eq(row["observed_qb"]).sum()),
            "post_previous_qb_snaps": int(post.sole_qb.eq(row["previous_qb"]).sum()),
            "post_unknown_or_other_qb_snaps": int((~post.sole_qb.isin([row["observed_qb"], row["previous_qb"]])).sum())})
    return result


def effect(totals):
    before, after, before_expected, after_expected = totals
    if min(before, before_expected, after_expected) <= 0:
        return None
    # Exposure pre/post snap denominators cancel against their standardized controls.
    return after / before / (after_expected / before_expected) - 1


def compare(rows):
    controls = [r for r in rows if not r["exposed"]]
    exposures = [r for r in rows if r["exposed"]]
    control_lookup = {}
    for r in controls:
        key = tuple(r[k] for k in STRATA)
        control_lookup.setdefault(key, []).append(r)
    matched, unmatched, used_control = [], [], set()
    for r in exposures:
        cs = [c for c in control_lookup.get(tuple(r[k] for k in STRATA), []) if c["game_id"] != r["game_id"]]
        counts = {f"{p}_{k}": sum(c[f"{p}_{k}"] for c in cs)
                  for p in ["pre", "post"] for k in ["targets", "snaps", "receptions"]}
        if not cs or counts["pre_snaps"] == 0 or counts["post_snaps"] == 0:
            unmatched.append({"game_id": r["game_id"], "team": r["team"],
                              "reason": "no_other_game_controls_or_zero_control_snap_denominator"})
            continue
        values = {}
        for p in ["pre", "post"]:
            for k in ["targets", "receptions"]:
                rate = counts[f"{p}_{k}"] / counts[f"{p}_snaps"]
                values[f"control_{p}_{k}_rate"] = rate
                values[f"expected_{p}_{k}"] = rate * r[f"{p}_snaps"]
        matched.append({**r, **values, "control_windows": len(cs),
                        "control_keys": [[c["game_id"], c["trigger_play_id"]] for c in cs]})
        used_control.update((c["game_id"], c["trigger_play_id"]) for c in cs)
    sums = {f"{p}_{k}": sum(r[f"{p}_{k}"] for r in matched)
            for p in ["pre", "post"] for k in ["targets", "snaps", "receptions"]}
    sums.update({f"expected_{p}_{k}": sum(r[f"expected_{p}_{k}"] for r in matched)
                 for p in ["pre", "post"] for k in ["targets", "receptions"]})
    rates = {}
    for p in ["pre", "post"]:
        for k in ["targets", "receptions"]:
            rates[f"exposed_{p}_{k}_rate"] = sums[f"{p}_{k}"] / sums[f"{p}_snaps"] if sums[f"{p}_snaps"] else None
            rates[f"standardized_control_{p}_{k}_rate"] = sums[f"expected_{p}_{k}"] / sums[f"{p}_snaps"] if sums[f"{p}_snaps"] else None
    value = effect([sums["pre_targets"], sums["post_targets"],
                    sums["expected_pre_targets"], sums["expected_post_targets"]])
    totals = {}
    for r in matched:
        totals.setdefault(r["game_id"], np.zeros(4))
        totals[r["game_id"]] += [r["pre_targets"], r["post_targets"], r["expected_pre_targets"], r["expected_post_targets"]]
    a = np.array(list(totals.values()))
    rng, draws = np.random.default_rng(20260913), []
    if len(a):
        for _ in range(2000):
            e = effect(a[rng.integers(0, len(a), len(a))].sum(axis=0))
            if e is not None:
                draws.append(e)
    by_year = []
    for season in PBP_PINS:
        y = [r for r in matched if r["season"] == season]
        v = [sum(r[k] for r in y) for k in ["pre_targets", "post_targets", "expected_pre_targets", "expected_post_targets"]]
        by_year.append({"season": season, "matched_exposures": len(y), "adjusted_relative_change": effect(v)})
    summary = {"decision": "unresolved_insufficient_sample" if len(matched) < 100 else
               "unresolved_zero_rate_denominator" if value is None else
               "sport_side_screen_pass" if value >= .2 else "sport_side_screen_fail",
        "matched_exposures": len(matched), "unmatched_exposures": len(unmatched),
        "matched_games": len(totals), "unique_control_windows": len(used_control),
        "unique_control_games": len({g for g, _ in used_control}),
        "adjusted_relative_target_rate_change": value, **sums, **rates,
        "descriptive_fixed_control_game_bootstrap_95_interval": np.quantile(draws, [.025, .975]).tolist() if draws else None,
        "matched_post_windows_with_zero_targets": sum(r["post_targets"] == 0 for r in matched),
        "matched_post_windows_with_fewer_than_ten_snaps": sum(r["post_snaps"] < 10 for r in matched),
        "matched_post_same_observed_qb_snaps": sum(r["post_same_observed_qb_snaps"] for r in matched),
        "matched_post_previous_qb_snaps": sum(r["post_previous_qb_snaps"] for r in matched),
        "matched_post_unknown_or_other_qb_snaps": sum(r["post_unknown_or_other_qb_snaps"] for r in matched),
        "top_receiver_exposure_counts": dict(Counter(p for r in matched for p in r["receivers"]).most_common(10)),
        "by_year": by_year}
    return summary, matched, unmatched


def known_disagreements(rows):
    path = ROOT / "reports/nfl-garbage-receptions-source-check-2026-09-13.json"
    known = json.loads(path.read_text())
    bad = known["rows"]
    affected = []
    for r in rows:
        in_game = [b for b in bad if b["game_id"] == r["game_id"]]
        if not in_game:
            continue
        affected.append({"game_id": r["game_id"], "team": r["team"], "trigger_play_id": r["trigger_play_id"],
            "exposed": r["exposed"],
            "discordant_trigger": any(b["play_id"] == r["trigger_play_id"] for b in in_game),
            "pre_window_discordant_plays": [b["play_id"] for b in in_game if b["play_id"] in r["pre_play_ids"]],
            "post_window_discordant_plays": [b["play_id"] for b in in_game if b["play_id"] in r["post_play_ids"]],
            "selected_pool_discordant_catches": [b["play_id"] for b in in_game if b["receiver_player_id"] in r["receivers"]
                and b["play_id"] in r["pre_play_ids"] + r["post_play_ids"]]})
    return {"diagnostic_source_sha256": sha(path), "known_discordant_completion_rows": len(bad),
            "affected_frozen_windows": affected, "repairs_or_game_exclusions": 0,
            "interpretation": "Retained known source disagreement. Absence of direct counted-catch overlap does not rule out omitted players or other incorrect identities."}


def evaluate(pbp, part, sources):
    frozen_path = RAW / "frozen-cohort.json"
    freeze = json.loads((RAW / "freeze.json").read_text())
    assert sha(frozen_path) == freeze["cohort_sha256"]
    frozen = json.loads(frozen_path.read_text())
    assert frozen["declaration_sha256"] == DECL_HASH and frozen["sources"] == sources
    snaps, _ = make_snaps(pbp, part)
    rows = outcomes(snaps, frozen["rows"])
    summary, matched, unmatched = compare(rows)
    all_outcomes_path = RAW / "all-window-outcomes.json"
    dump(all_outcomes_path, rows)
    result = {"evaluated_at": now(), "prepared_at": frozen["prepared_at"],
        "declaration_sha256": DECL_HASH, "frozen_cohort_sha256": freeze["cohort_sha256"],
        "sources": sources, "attribution": "FTN Data via nflverse, CC BY-SA 4.0; nflverse/nflfastR PBP, CC BY 4.0",
        "coverage": frozen["coverage"], "summary": summary,
        "known_source_disagreements": known_disagreements(rows),
        "limitations": ["Observed historical sole-QB change is not an injury diagnosis, pregame starter announcement, or proof of timely live availability.",
            "Trigger-play outcomes excluded; subsequent QB returns and all receiver substitutions remain.",
            "Matching controls team, season, quarter and broad score band; field position, opponents, change reason, receiver mix and pre-trigger trends remain uncontrolled.",
            "Short pools use prior-game role and current participation, not subsequent targets or catches.",
            "The descriptive bootstrap holds controls fixed and omits repeated-team dependence.",
            "Known participation/completion identity disagreements remain without repairs or selective game exclusion.",
            "No FanDuel price, executable quote, settlement comparison, return or betting edge is established."],
        "all_window_outcomes_sha256": sha(all_outcomes_path),
        "all_window_outcomes_local_path": str(all_outcomes_path.relative_to(ROOT)),
        "published_row_scope": "All exposure windows and matched control identities/rates; complete control-window outcomes are reproducible from pinned inputs and retained in the ignored local cache.",
        "exposure_windows": [r for r in rows if r["exposed"]],
        "matched_exposures": matched, "unmatched_exposures": unmatched}
    dump(OUT, result)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--evaluate", action="store_true")
    args = parser.parse_args()
    b, p, sources = load(args.download)
    if args.prepare:
        prepare(b, p, sources)
    else:
        evaluate(b, p, sources)
