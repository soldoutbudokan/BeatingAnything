#!/usr/bin/env python3
"""Fixed exploratory NHL consensus; forecast freeze precedes this model's grading."""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import statistics

import numpy as np
import pandas as pd

from inventory_nhl_shot_consensus import parse_main_pairs, norm, stamp, REFERENCE_BOOKS

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT/"data/raw/nhl-shot-archive-2026-09-26"
SPORT = RAW/"outcomes"
PREDICTIONS = RAW/"consensus-forecasts.csv"
FREEZE = RAW/"consensus-forecast-freeze.json"
GRADED = RAW/"consensus-graded.csv"
OUT = ROOT/"reports/nhl-shot-consensus-2026-09-26"
CARD = ROOT/"docs/hypotheses/hockey-shots-crossbook-consensus.md"
DEBUG_GAME = 2024020345


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}


def forecast():
    if PREDICTIONS.exists() or FREEZE.exists():
        raise FileExistsError("Frozen predictions exist; do not overwrite this experiment")
    manifest_path = RAW/"manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["source_commit"] == "42cf1f81bc302642ddcc9e88ce2e98c1057bc74d" and len(manifest["files"]) == 285
    rosters = pd.concat([pd.read_csv(SPORT/f"rosters_{y}.csv", usecols=["full_name","player_id"]) for y in [2024,2025]])
    rosters["key"] = rosters.full_name.map(norm)
    identities = rosters.groupby("key").player_id.agg(lambda x: sorted(set(x)))
    games = pd.read_csv(SPORT/"schedule_2025_metadata.csv")
    games = games[games.game_type.eq("R")].copy()
    games["home_key"], games["away_key"] = games.home_team_name.map(norm), games.away_team_name.map(norm)
    games["start"] = pd.to_datetime(games.game_time, utc=True)
    rows, attrition, parser_issues, unknown_names, seen = [], Counter(), Counter(), Counter(), set()
    for info in manifest["files"]:
        path = ROOT/info["path"]
        assert sha(path) == info["sha256"] and path.stat().st_size == info["bytes"]
        raw = json.loads(path.read_text())
        if "bookmakers" not in raw:
            attrition["publisher_error_payload"] += 1
            continue
        assert raw["sport_key"] == "icehockey_nhl" and raw["id"] not in seen
        seen.add(raw["id"])
        provider = stamp(raw["commence_time"])
        matched = games[games.home_key.eq(norm(raw["home_team"])) & games.away_key.eq(norm(raw["away_team"])) &
                        ((games.start-provider).abs() <= pd.Timedelta(days=1))]
        if len(matched) != 1:
            attrition["fixture_unresolved"] += 1
            continue
        game = matched.iloc[0]
        if int(game.game_id) == DEBUG_GAME:
            attrition["original_debug_game_excluded"] += 1
            continue
        boundary = min(provider, game.start.to_pydatetime())
        books = parse_main_pairs(raw, parser_issues)
        if "fanduel" not in books:
            attrition["no_fanduel_main_market"] += 1
            continue
        fd = books["fanduel"]
        entry = fd["update"]
        if not boundary-timedelta(hours=72) <= entry < boundary:
            attrition["fd_update_outside_pregame_window"] += 1
            continue
        candidates = []
        for identity, p in fd["pairs"].items():
            if not .5 <= p["line"] <= 8.5 or p["line"] % 1 != .5:
                attrition["fd_line_outside_fixed_halfpoint_range"] += 1
                continue
            if not 0 <= p["overround"] <= .15:
                attrition["fd_overround_outside_fixed_range"] += 1
                continue
            q = (1/p["under_decimal"])/(1/p["over_decimal"]+1/p["under_decimal"])
            candidates.append((identity, p, q))
        candidates.sort(key=lambda x: (x[0][0],abs(x[2]-.5),x[1]["line"]))
        chosen_names = set()
        for identity, p, q in candidates:
            if identity[0] in chosen_names:
                attrition["extra_fd_main_line_same_player"] += 1
                continue
            chosen_names.add(identity[0])
            references = []
            for book_key in REFERENCE_BOOKS:
                b = books.get(book_key)
                if b is None or identity not in b["pairs"]:
                    continue
                ref = b["pairs"][identity]
                age = (entry-b["update"]).total_seconds()
                if not 0 <= age <= 300 or not 0 <= ref["overround"] <= .15:
                    continue
                ref_q = (1/ref["under_decimal"])/(1/ref["over_decimal"]+1/ref["under_decimal"])
                references.append({"book": book_key, "market_update": b["update"].isoformat(), "age_seconds": age,
                                   "q_under": ref_q, **ref})
            if len(references) < 3:
                attrition["fewer_than_3_fixed_timely_references"] += 1
                continue
            ids = identities.get(identity[0], [])
            if len(ids) != 1:
                attrition["player_identity_unresolved"] += 1
                unknown_names[p["name"]] += 1
                continue
            pred = statistics.median(r["q_under"] for r in references)
            rows.append({"game_id": int(game.game_id), "player_id": int(ids[0]), "player": p["name"],
                         "event_id": raw["id"], "source_file": path.name, "line": p["line"], "entry": entry.isoformat(),
                         "provider_start": provider.isoformat(), "independent_start": game.start.isoformat(), "boundary": boundary.isoformat(),
                         "period": "later_january" if boundary >= datetime(2025,1,1,tzinfo=timezone.utc) else "early_nov_dec",
                         "over_decimal": p["over_decimal"], "under_decimal": p["under_decimal"], "fd_overround": p["overround"],
                         "q_under": q, "p_under": pred, "reference_count": len(references),
                         "references_json": json.dumps(references, sort_keys=True, separators=(",",":"))})
    frame = pd.DataFrame(rows)
    assert len(frame) and not frame.duplicated(["game_id","player_id"]).any()
    frame["ev_under"] = frame.p_under*(1+.98*(frame.under_decimal-1))-1
    frame["ev_over"] = (1-frame.p_under)*(1+.98*(frame.over_decimal-1))-1
    frame["selected_side"] = ""
    for game_id, group in frame.groupby("game_id"):
        candidates = []
        for idx, r in group.iterrows():
            for side in ["Over","Under"]:
                key = side.lower()
                if 1.2 <= r[key+"_decimal"] <= 6 and r["ev_"+key] >= .03:
                    candidates.append((-r["ev_"+key],r.player,side,idx))
        if candidates:
            _, _, side, idx = sorted(candidates)[0]
            frame.loc[idx,"selected_side"] = side
    frame = frame.sort_values(["entry","game_id","player_id"])
    frame.to_csv(PREDICTIONS,index=False)
    metadata_sources = [SPORT/f"rosters_{y}.csv" for y in [2024,2025]] + [SPORT/"schedule_2025_metadata.csv"]
    meta = {"status": "frozen_before_this_model_grading; archive outcomes previously inspected", "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
            "code_and_declaration": [source(p) for p in [Path(__file__),ROOT/"tools/inventory_nhl_shot_consensus.py",CARD]],
            "forecasts": source(PREDICTIONS), "manifest": source(manifest_path),
            "price_sources": [source(ROOT/r["path"]) for r in manifest["files"]],
            "metadata_sources": [source(p) for p in metadata_sources], "outcome_sources_hash_only": [source(SPORT/"player_box_2025.csv")],
            "forecast_rows": len(frame), "games": int(frame.game_id.nunique()), "selections": int(frame.selected_side.ne("").sum()),
            "period_forecasts": frame.period.value_counts().to_dict(), "attrition": dict(attrition), "parser_issues": dict(parser_issues),
            "unrecognized_names": dict(unknown_names), "reference_books": list(REFERENCE_BOOKS)}
    FREEZE.write_text(json.dumps(meta,indent=2,allow_nan=False)+"\n")
    print(json.dumps({k:meta[k] for k in ["forecast_rows","games","selections","period_forecasts","attrition","unrecognized_names"]},indent=2))


def interval(frame, column):
    if frame.empty:
        return {"n":0,"games":0,"mean":None,"game_bootstrap_95":None}
    g = frame.groupby("game_id")[column].agg(["sum","count"])
    ix = np.random.default_rng(1729).integers(len(g),size=(10000,len(g)))
    boot = g["sum"].to_numpy()[ix].sum(axis=1)/g["count"].to_numpy()[ix].sum(axis=1)
    return {"n":len(frame),"games":len(g),"mean":float(frame[column].mean()),"game_bootstrap_95":np.quantile(boot,[.025,.975]).tolist()}


def summarize(frame):
    known = frame[frame.settlement.eq("graded")].copy()
    y = (known.shots_on_goal < known.line).astype(float)
    for col in ["q_under","p_under"]:
        p = known[col]
        known[col+"_log_loss"] = -(y*np.log(p)+(1-y)*np.log1p(-p))
        known[col+"_brier"] = (p-y)**2
    known["log_loss_change"] = known.p_under_log_loss-known.q_under_log_loss
    known["brier_change"] = known.p_under_brier-known.q_under_brier
    selected = frame[frame.selected_side.fillna("").ne("")]
    settled = selected[selected.settlement.isin(["graded","void_zero_toi"])]
    unknown = selected[~selected.settlement.isin(["graded","void_zero_toi"])].copy()
    upper = sum(.98*(r[r.selected_side.lower()+"_decimal"]-1) for _,r in unknown.iterrows())
    n = len(selected)
    profit = float(settled.profit.sum())
    return {"forecasts":len(frame),"games":int(frame.game_id.nunique()),"graded":len(known),"statuses":frame.settlement.value_counts().to_dict(),
            "market_log_loss":float(known.q_under_log_loss.mean()) if len(known) else None,
            "model_log_loss":float(known.p_under_log_loss.mean()) if len(known) else None,
            "market_brier":float(known.q_under_brier.mean()) if len(known) else None,
            "model_brier":float(known.p_under_brier.mean()) if len(known) else None,
            "log_loss_change":interval(known,"log_loss_change"),"brier_change":interval(known,"brier_change"),
            "selections":n,"selection_statuses":selected.settlement.value_counts().to_dict(),"selected_under":int(selected.selected_side.eq("Under").sum()),
            "selected_over":int(selected.selected_side.eq("Over").sum()),"selected_wins":int((settled.profit>0).sum()),"selected_losses":int((settled.profit<0).sum()),
            "settled_units":profit,"settled_roi":interval(settled,"profit"),"full_cohort_roi_loss_bound":(profit-len(unknown))/n if n else None,
            "full_cohort_roi_void_bound":profit/n if n else None,"full_cohort_roi_win_bound":(profit+upper)/n if n else None,
            "mean_selected_model_ev":float(selected.selected_ev.mean()) if n else None}


def grade():
    meta = json.loads(FREEZE.read_text())
    pinned = meta["code_and_declaration"]+[meta["forecasts"],meta["manifest"]]+meta["price_sources"]+meta["metadata_sources"]+meta["outcome_sources_hash_only"]
    for r in pinned:
        assert sha(ROOT/r["path"]) == r["sha256"], "Frozen input changed: "+r["path"]
    frame = pd.read_csv(PREDICTIONS)
    boxes = pd.read_csv(SPORT/"player_box_2025.csv",usecols=["game_id","player_id","shots_on_goal","toi"])
    assert not boxes.duplicated(["game_id","player_id"]).any()
    frame = frame.merge(boxes,on=["game_id","player_id"],how="left",validate="one_to_one")
    frame["settlement"] = "unknown_no_box_row"
    valid = frame.shots_on_goal.notna() & frame.shots_on_goal.ge(0) & frame.shots_on_goal.mod(1).eq(0)
    toi = frame.toi.astype(str).str.extract(r"^(\d+):(\d{2})$").apply(pd.to_numeric,errors="coerce")
    seconds = toi[0]*60+toi[1]
    frame.loc[valid & seconds.gt(0),"settlement"] = "graded"
    frame.loc[valid & seconds.eq(0),"settlement"] = "void_zero_toi"
    frame.loc[frame.shots_on_goal.notna() & ~valid,"settlement"] = "unknown_invalid_count"
    frame.loc[valid & seconds.isna(),"settlement"] = "unknown_participation_time"
    frame["profit"], frame["selected_ev"] = np.nan, np.nan
    for idx,r in frame.iterrows():
        if pd.isna(r.selected_side) or not r.selected_side:
            continue
        key = r.selected_side.lower()
        frame.loc[idx,"selected_ev"] = r["ev_"+key]
        if r.settlement == "void_zero_toi":
            frame.loc[idx,"profit"] = 0.
        elif r.settlement == "graded":
            assert r.shots_on_goal != r.line
            win = r.shots_on_goal < r.line if key == "under" else r.shots_on_goal > r.line
            frame.loc[idx,"profit"] = .98*(r[key+"_decimal"]-1) if win else -1.
    frame.to_csv(GRADED,index=False)
    report = {"status":"exploratory; previously inspected archive; no executable edge established", "specification":str(CARD.relative_to(ROOT)),
              "freeze":source(FREEZE),"frozen_at_utc":meta["frozen_at_utc"],"graded_at_utc":datetime.now(timezone.utc).isoformat(),"graded_artifact":source(GRADED),
              "forecast_inventory":{k:meta[k] for k in ["forecast_rows","games","selections","period_forecasts","attrition","unrecognized_names"]},
              "pooled":summarize(frame),"periods":{k:summarize(g) for k,g in frame.groupby("period")},
              "limitations":["Archive outcomes were previously inspected for the completed dispersion test; January is diagnostic, not untouched validation.",
                             "Distinct operators do not establish statistically independent forecast errors or absence of common pricing suppliers.",
                             "Market-update order lacks original receipt/capture and executable-price evidence.",
                             "Global roster names supply identity only, not contemporaneous participation; unresolved grades and selections remain retained.",
                             "Full-game shots including overtime and void for confirmed zero ice time are assumptions; exact historic jurisdiction and terms unverified.",
                             "Source covers33 irregular dates; intervals are whole-game resamples uncorrected for prior hypothesis searches.",
                             "No weights, reference pool, age cutoff, lines or EV threshold retuned after this result."]}
    OUT.with_suffix(".json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    s = report["pooled"]
    def percent(value):
        return "undefined" if value is None else f"{value:+.2%}"
    lines = ["# NHL fixed shots consensus — September 26, 2026","",
             f"**Exploratory result: {s['graded']:,} of {s['forecasts']:,} forecasts grade; {s['selections']} bets were selected.** All predictions and selections were frozen before this model's grading, but the archive's outcomes were already inspected in the dispersion test. This is not a new holdout or proof of an executable edge.","",
             f"Normalized FanDuel log loss is {s['market_log_loss']:.6f}; fixed consensus loss is {s['model_log_loss']:.6f}. Paired change {s['log_loss_change']['mean']:+.6f}, game-bootstrap 95% {s['log_loss_change']['game_bootstrap_95']}. Brier loss changes {s['market_brier']:.6f} → {s['model_brier']:.6f}; paired change {s['brier_change']['mean']:+.6f}.","",
             f"Selected settled bets: {s['selected_wins']} wins / {s['selected_losses']} losses, {s['settled_units']:+.4f} units after a 2% net-winnings haircut. Graded/void ROI is {percent(s['settled_roi']['mean'])}. Full selected-cohort unresolved loss/void/win bounds are {percent(s['full_cohort_roi_loss_bound'])} / {percent(s['full_cohort_roi_void_bound'])} / {percent(s['full_cohort_roi_win_bound'])}. Selection statuses: `{s['selection_statuses']}`. Every unresolved selection stays in these bounds.","",
             "| UTC-start diagnostic period | Forecasts / graded | Log-loss change | Selected / wins / losses | Settled units | Full-cohort loss–win ROI bounds |","| --- | ---: | ---: | ---: | ---: | ---: |"]
    for name,r in report["periods"].items():
        lines.append(f"| {name} | {r['forecasts']} / {r['graded']} | {r['log_loss_change']['mean']:+.6f} | {r['selections']} / {r['selected_wins']} / {r['selected_losses']} | {r['settled_units']:+.4f} | {percent(r['full_cohort_roi_loss_bound'])} to {percent(r['full_cohort_roi_win_bound'])} |")
    lines += ["","The fixed forecast is the median normalized Under probability from at least three of DraftKings, BetMGM, ESPN BET and Hard Rock Bet, at the exact FanDuel main player/line. Each reference update is no later than FanDuel and at most 300 seconds earlier. Full [declaration](../docs/hypotheses/hockey-shots-crossbook-consensus.md) specifies margin, identity, fixture, entry, line and exposure rules. There is no sporting-history minimum. At most one bet per game clears +3% EV after costs; ties follow the declared order.","",
              f"Forecast file SHA-256: `{meta['forecasts']['sha256']}`. Grading verifies the frozen declaration, both code dependencies, prices, identities, schedule, outcomes and predictions. Full attrition, paired intervals and selected exposure are in the adjacent JSON; retained per-row predictions and settlements remain local under `data/raw/nhl-shot-archive-2026-09-26/`.","",
              "Market updates lack receipt/execution proof. Exact historical participation and jurisdiction terms remain unverified. Distinct book keys do not demonstrate independent errors. January and pooled intervals are exploratory and uncorrected for prior searches; do not change the pool, threshold or model in response. No wager, alert or schedule.","",
              "Reproduce grading with `state/runtime/research-venv/bin/python tools/explore_nhl_shot_consensus.py --phase grade`; the forecast phase refuses overwrite.",""]
    OUT.with_suffix(".md").write_text("\n".join(lines))
    print(json.dumps({"pooled":report["pooled"],"periods":report["periods"]},indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase",choices=["forecast","grade"],required=True)
    args = parser.parse_args()
    forecast() if args.phase == "forecast" else grade()
