#!/usr/bin/env python3
"""G5 cheap sport-side screen; offline, no odds, regression or fitted model.

Written before the comparison: 2024 warms history, 2025 is exploratory scoring.
Previous 20 complete rounds (minimum 10), all from events ending before this
event, estimate player ability relative to each historical round's field mean.
Current residual = score minus round field mean minus that frozen prior ability.
Compare R3 and R4 separately across fixed R1/R2 mean residual bins <=-2,
(-2,2), >=2. The primary contrast divides upper-minus-lower R3 residual by
upper-minus-lower early residual, standardized across events with both bins.
This is association, subject to cut selection and noisy ability estimates.
"""
from __future__ import annotations

# %% Inputs and rules fixed before comparison
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_NAMES = (
    "american express", "farmers insurance", "pebble beach", "rsm classic",
    "zurich classic", "presidents cup", "ryder cup", "barracuda",
    "tour championship", "q-school", "showdown", "hero world challenge",
)


def complete_score(r: dict) -> float | None:
    holes = r.get("linescores", [])
    score = r.get("value")
    if len(holes) != 18 or {h.get("period") for h in holes} != set(range(1, 19)):
        return None
    vals = [h.get("value") for h in holes]
    if not all(isinstance(v, (float, int)) and 1 <= v <= 20 and int(v) == v for v in vals):
        return None
    if not isinstance(score, (float, int)) or sum(vals) != score:
        return None
    return float(score)


def iso_date(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# %% Reconstruct prior-only ability, retaining absent later outcomes
def prepare(events: list[dict]) -> tuple[list[dict], dict]:
    history = defaultdict(list)
    rows, excluded = [], []
    counts = Counter()
    for e in sorted(events, key=lambda e: (e["date"], e["id"])):
        reason = next((s for s in EXCLUDED_NAMES if s in e["name"].lower()), None)
        if reason:
            excluded.append({"id": e["id"], "name": e["name"], "reason": reason})
            continue
        if len(e.get("competitions", [])) != 1 or not e.get("status", {}).get("type", {}).get("completed"):
            excluded.append({"id": e["id"], "name": e["name"], "reason": "not one completed competition"})
            continue
        players = e["competitions"][0]["competitors"]
        scores = {}
        for p in players:
            if p.get("type") != "athlete":
                continue
            rs = {}
            for r in p.get("linescores", []):
                period = r.get("period")
                if period not in range(1, 5):
                    continue  # playoff holes never become a fifth round
                value = complete_score(r)
                if value is None:
                    counts["incomplete_or_inconsistent_rounds"] += 1
                else:
                    if period in rs:
                        raise ValueError("duplicate player round")
                    rs[period] = value
            if p["id"] in scores:
                raise ValueError("duplicate event player")
            scores[p["id"]] = rs
        means = {r: mean(s[r] for s in scores.values() if r in s)
                 for r in range(1, 5) if any(r in s for s in scores.values())}
        if len(means) != 4:
            excluded.append({"id": e["id"], "name": e["name"], "reason": "not four scored rounds"})
            continue
        start, end = iso_date(e["date"]), iso_date(e["endDate"])
        if end < start:
            raise ValueError("event date order")
        counts[f"events_{start.year}"] += 1
        for pid, rs in scores.items():
            prior = sorted((x for x in history[pid] if x[0] < start), key=lambda x: (x[0], x[1], x[2]))[-20:]
            if start.year == 2025:
                counts["player_events_2025"] += 1
                if len(prior) < 10:
                    counts["insufficient_prior_rounds"] += 1
                elif not {1, 2} <= rs.keys():
                    counts["missing_complete_early_rounds"] += 1
                else:
                    ability = mean(x[3] for x in prior)
                    early = mean(rs[r] - means[r] - ability for r in (1, 2))
                    rows.append({
                        "event_id": e["id"], "event_name": e["name"],
                        "event_start": e["date"], "player_id": pid,
                        "prior_rounds": len(prior), "latest_prior_end": prior[-1][0].isoformat(),
                        "prior_ability": ability, "early_residual": early,
                        "bin": "low" if early <= -2 else "high" if early >= 2 else "middle",
                        "round3_residual": rs[3] - means[3] - ability if 3 in rs else None,
                        "round4_residual": rs[4] - means[4] - ability if 4 in rs else None,
                    })
            for r, score in rs.items():
                history[pid].append((end, e["id"], r, score - means[r]))
    return rows, {"counts": dict(counts), "excluded_events": excluded}


# %% Fixed contrasts; no tuned bins, subgroups or threshold search
def compare(rows: list[dict], later: str) -> dict:
    eligible = [r for r in rows if r[later] is not None]
    bins = {}
    for b in ("low", "middle", "high"):
        rr = [r for r in rows if r["bin"] == b]
        complete = [r for r in rr if r[later] is not None]
        bins[b] = {"early_eligible": len(rr), "later_observed": len(complete),
                   "later_missing": len(rr) - len(complete),
                   "early_mean": mean(r["early_residual"] for r in complete) if complete else None,
                   "later_mean": mean(r[later] for r in complete) if complete else None}
    strata = []
    for eid in sorted({r["event_id"] for r in eligible}):
        lo = [r for r in eligible if r["event_id"] == eid and r["bin"] == "low"]
        hi = [r for r in eligible if r["event_id"] == eid and r["bin"] == "high"]
        if not lo or not hi:
            continue
        strata.append({"event_id": eid, "low": len(lo), "high": len(hi),
                       "weight": len(lo) * len(hi) / (len(lo) + len(hi)),
                       "early_gap": mean(r["early_residual"] for r in hi) - mean(r["early_residual"] for r in lo),
                       "later_gap": mean(r[later] for r in hi) - mean(r[later] for r in lo)})
    total = sum(s["weight"] for s in strata)
    early_gap = sum(s["weight"] * s["early_gap"] for s in strata) / total if total else None
    later_gap = sum(s["weight"] * s["later_gap"] for s in strata) / total if total else None
    ratio = later_gap / early_gap if early_gap else None
    matched_players = sum(s["low"] + s["high"] for s in strata)
    enough = matched_players >= 200 and len(strata) >= 15
    return {"bins": bins, "matched_player_events": matched_players,
            "matched_events": len(strata), "early_gap": early_gap, "later_gap": later_gap,
            "contrast_per_early_stroke": ratio,
            "status": "unresolved: sample below gate" if not enough else
                      "sport-side effect: investigate prices" if ratio >= .1 else "sport-side dead at fixed screen",
            "event_contrasts": strata}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "data/raw/golf-sport")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/golf-weekend-screen-2026-09-14")
    args = parser.parse_args()
    events, sources = [], []
    for year in (2024, 2025):
        p = args.source_dir / f"scoreboard-{year}.json"
        raw = p.read_bytes()
        data = json.loads(raw)
        if any(e["season"]["year"] != year for e in data["events"]):
            raise ValueError("unexpected source year")
        events.extend(data["events"])
        sources.append({"path": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(raw).hexdigest(),
                        "url": f"https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates={year}"})
    rows, attrition = prepare(events)
    results = {k: compare(rows, k) for k in ("round3_residual", "round4_residual")}
    row_path = args.source_dir / "screen-weekend-rows.json"
    row_bytes = (json.dumps(rows, indent=2) + "\n").encode()
    row_path.write_bytes(row_bytes)
    result = {"card": "G5", "scope": "exploratory 2025, 2024 history warmup; no prices",
              "sources": sources, "attrition": attrition, "results": results,
              "derived_rows": {"file": str(row_path.relative_to(ROOT)), "count": len(rows),
                               "sha256": hashlib.sha256(row_bytes).hexdigest()},
              "fanduel_price_test": None}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n")
    lines = ["# G5 weekend information screen — September 14, 2026", "",
             f"**Primary round-three result: {results['round3_residual']['status']}.** No FanDuel prices were tested.", "",
             "The [prewritten card](../docs/hypotheses/golf-weekend-state.md) uses previous-20-round ability (minimum 10), fixed ±2-stroke early-residual bins, and a 0.1-stroke-per-stroke screen. The script specifies event exclusions and within-event standardization before comparison. 2024 supplies history; 2025 is inspected exploration, not untouched confirmation.", "",
             "| Later round | Matched player-events | Events | Early gap | Later gap | Later/early |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for k, v in results.items():
        f = lambda x: f"{x:.4f}" if x is not None else "unknown"
        lines.append(f"| {k} | {v['matched_player_events']} | {v['matched_events']} | {f(v['early_gap'])} | {f(v['later_gap'])} | {f(v['contrast_per_early_stroke'])} |")
    lines += ["", "## Interpretation and limits", "",
              "Low means better-than-prior early scoring; high means worse. Differences are calculated within events and weighted by n_low × n_high / (n_low + n_high). Both later rounds are reported; round three is primary. A positive contrast can reflect a noisy prior skill estimate as well as event-specific state. It does not establish motivation, causation, or book mispricing.", "",
              "Current scores are centered on their round's completed-score field mean; this is an outcome normalization, not a pre-round predictor. Every player's ability uses only events ending before the new event's recorded start. Field strengths vary and survivors change after the cut. Players missing later scores are retained in attrition, not scored as zero: the comparison is conditional on observed complete later rounds, so cut/withdrawal selection can bias it. No timestamped live trigger is reconstructed from these retrospective feeds.", "",
              "Excluded: named multi-course rotations, team/match-play/Stableford events, TOUR Championship, Q-School, exhibition and Hero fields; events without four complete scored rounds. Playoff holes and incomplete/mismatched hole sums are excluded uniformly. The script does not revisit the earlier Sunday-variance card.", "",
              f"Full denominators, bin counts, missing later scores, per-event contrasts and source hashes are in [{args.output.name}.json]({args.output.name}.json). Sources: [ESPN 2024](https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates=2024), [ESPN 2025](https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates=2025).", "",
              "Reproduce: `state/runtime/research-venv/bin/python tools/explore_golf_weekend.py`. Raw publisher responses stay local and ignored."]
    args.output.with_suffix(".md").write_text("\n".join(lines) + "\n")
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != 'event_contrasts'} for k, v in results.items()}, indent=2))


if __name__ == "__main__":
    main()
