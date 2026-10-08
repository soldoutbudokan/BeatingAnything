"""Extract the requested S-over/R-under cases from preserved raw UI observations.

No probabilities are imputed for unmatched or incomplete reference partitions.
This frozen prior inventory intentionally does not ingest later live sweep files.
"""
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = [
    "sgp-research/continued-observations.json",
    "sgp-research/bijan-observations.json",
    "sgp-research/holani-observations.json",
    "sgp-research/gibbs-observations.json",
    "mlb_scan_future_nfl.json",
]
ORDER = ["OO", "OU", "UO", "UU"]


def decimal(american):
    return 1 + american / 100 if american > 0 else 1 + 100 / -american


def devig(prices):
    q = [1 / decimal(prices[c]) for c in ORDER]
    total = sum(q)
    lo, hi = 0.0, 100.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if sum(v**mid for v in q) > 1:
            lo = mid
        else:
            hi = mid
    exponent = (lo + hi) / 2
    additive = [v - (total - 1) / 4 for v in q]
    return {
        "raw_implied_sum": total,
        "power_exponent": exponent,
        "proportional": dict(zip(ORDER, [v / total for v in q])),
        "power": dict(zip(ORDER, [v**exponent for v in q])),
        "additive": dict(zip(ORDER, additive)) if min(additive) >= 0 and max(additive) <= 1 else None,
    }


def text(record):
    return record.get("slip", record.get("snapshot", "")).replace("\\n", "\n")


def stamp(record):
    return record.get("captured_at", record.get("at"))


def score_legs(s):
    legs = []
    for block in s.split("Remove selection\n")[1:]:
        m = re.match(r"(Over|Under)\n(-?\d+(?:\.\d+)?)\n(?:(?:[+-]\d+|Even)\n)?\n(.+?) Total (Rushing \+ Receiving|Rushing|Receiving) Yards", block)
        if m:
            side, line, player, market = m.groups()
        else:
            m = re.match(r"(\d+)\+\n(?:(?:[+-]\d+|Even)\n)?\n(.+?) Total (Rushing \+ Receiving|Rushing|Receiving) Yards", block)
            if not m:
                continue
            line, player, market = m.groups()
            side = "at_least"
        legs.append({"player": player, "market": {"Rushing + Receiving": "S", "Rushing": "R", "Receiving": "C"}[market], "side": side.lower(), "line": float(line)})
    return legs


def fd_legs(s):
    legs = []
    pat = r'generic "Selection \d+ of \d+, (.+?) (Over|Under) (-?\d+(?:\.\d+)?), (.+?) - (Rushing \+ Receiving|Rushing|Receiving) Yds"'
    for player, side, line, repeated_player, market in re.findall(pat, s):
        assert player == repeated_player
        legs.append({"player": player, "market": {"Rushing + Receiving": "S", "Rushing": "R", "Receiving": "C"}[market], "side": side.lower(), "line": float(line)})
    return legs


def canonical(player):
    return player.replace(" Sr.", "")


def reference_relation(s_score, r_score, s_fd, r_fd):
    # Events use integer yardage, so compare their actual winning thresholds.
    a, b, c, d = math.floor(s_score) + 1, math.ceil(r_score) - 1, math.floor(s_fd) + 1, math.ceil(r_fd) - 1
    if (a, b) == (c, d):
        return "exact"
    if c >= a and d <= b:
        return "subset"
    if c <= a and d >= b:
        return "superset"
    return "incomparable"


def main():
    score_rows, fd_rows, exclusions = [], [], []
    source_hashes = {}
    for filename in SOURCES:
        path = ROOT / filename
        source_hashes[filename] = hashlib.sha256(path.read_bytes()).hexdigest()
        data = json.loads(path.read_text())
        for key in ["score", "fanduel", "observations"]:
            for index, record in enumerate(data.get(key, [])):
                s = text(record)
                source = {"file": filename, "array": key, "index": index, "observed_at": stamp(record), "label": record.get("case", record.get("test", record.get("cell")))}
                if s.startswith("Betslip"):
                    legs = score_legs(s)
                    combined = next((x for x in legs if x["market"] == "S" and x["side"] == "over"), None)
                    rushing = next((x for x in legs if x["market"] == "R" and x["side"] == "under"), None)
                    if not combined or not rushing or combined["player"] != rushing["player"]:
                        continue
                    event = s.split("Remove selection\n")[0].strip().splitlines()[-1]
                    price = re.search(r"\nPARLAY\n([+-]\d+)\n", s)
                    row = {"player": canonical(combined["player"]), "score_display_player": combined["player"], "event": event, "score_S_line": combined["line"], "score_R_line": rushing["line"], "receiving_implied_minimum": math.floor(combined["line"]) + 1 - (math.ceil(rushing["line"]) - 1), "legs": legs, "american": int(price.group(1)) if price else None, "source": source, "score_url": record.get("url")}
                    if filename == "mlb_scan_future_nfl.json" and index == 34:
                        row["exclusion_reason"] = "Transitional stale +823 quote after removing C10+; later settled main-only +514 supersedes it."
                        exclusions.append(row)
                    elif price is None:
                        row["exclusion_reason"] = "No valid parlay quote: builder rejected this combination."
                        exclusions.append(row)
                    else:
                        score_rows.append(row)
                else:
                    legs = fd_legs(s)
                    if len(legs) != 2 or {x["market"] for x in legs} != {"S", "R"}:
                        continue
                    price = re.search(r'Same Game Parlay, (.+?), ([+-]\d+) Odds\.', s)
                    if not price:
                        continue
                    by_market = {x["market"]: x for x in legs}
                    assert len({x["player"] for x in legs}) == 1
                    fd_rows.append({"player": canonical(legs[0]["player"]), "event": price.group(1), "S_line": by_market["S"]["line"], "R_line": by_market["R"]["line"], "cell": by_market["S"]["side"][0].upper() + by_market["R"]["side"][0].upper(), "american": int(price.group(2)), "source": source, "url": record.get("url")})

    # This saved single quote has no complementary cells and opposite threshold changes.
    filename = "sgp-research/closest-javonte-reference.json"
    record = json.loads((ROOT / filename).read_text())
    source_hashes[filename] = hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()
    s = text(record)
    legs = fd_legs(s)
    by_market = {x["market"]: x for x in legs}
    price = re.search(r'Same Game Parlay, (.+?), ([+-]\d+) Odds\.', s)
    fd_rows.append({"player": "Javonte Williams", "event": price.group(1), "S_line": by_market["S"]["line"], "R_line": by_market["R"]["line"], "cell": "OU", "american": int(price.group(2)), "source": {"file": filename, "array": None, "index": None, "observed_at": stamp(record), "label": record["case"]}, "url": None})

    groups = defaultdict(list)
    for row in score_rows:
        groups[(row["player"], row["event"], row["score_S_line"], row["score_R_line"])].append(row)
    result = []
    preserved_urls = {}
    for filename, player in [("sgp-research/sf-sea-scout.json", "George Holani"), ("sgp-research/det-ari-scout.json", "Jahmyr Gibbs")]:
        data = json.loads((ROOT / filename).read_text())
        preserved_urls[player] = {"score": data["score_url"], "fanduel": data["fd_url"], "provenance": filename}
        source_hashes[filename] = hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()
    jones_setup = json.loads((ROOT / "mlb_scan_future_nfl.json").read_text())["observations"][42]
    preserved_urls["Aaron Jones"] = {"score": jones_setup["score_url"], "fanduel": jones_setup["FD_url"], "provenance": "mlb_scan_future_nfl.json#/observations/42"}
    for (player, event, s_line, r_line), captures in groups.items():
        references = [x for x in fd_rows if x["player"] == player and x["event"] == event]
        partitions = defaultdict(list)
        for ref in references:
            partitions[(ref["S_line"], ref["R_line"])].append(ref)
        assert len(partitions) <= 1, "Explicit temporal partition choice needed"
        reference = None
        models = None
        relation = None
        if partitions:
            (s_fd, r_fd), refs = next(iter(partitions.items()))
            cells = {c: [x for x in refs if x["cell"] == c] for c in ORDER}
            for cell in cells.values():
                assert len({x["american"] for x in cell}) <= 1, "Reference moved: cannot mix snapshots"
            complete = all(cells.values())
            relation = reference_relation(s_line, r_line, s_fd, r_fd)
            models = devig({c: rows[0]["american"] for c, rows in cells.items()}) if complete else None
            reference = {"book": "FanDuel", "S_line": s_fd, "R_line": r_fd, "relation_to_score_target": relation, "complete_raw_quartet": complete, "cells": cells, "models": models}
        variants = {}
        for row in captures:
            extras = [x for x in row["legs"] if not (x["market"] == "S" and x["side"] == "over" and x["line"] == s_line) and not (x["market"] == "R" and x["side"] == "under" and x["line"] == r_line)]
            for leg in extras:
                threshold = math.floor(leg["line"]) + 1 if leg["side"] == "over" else leg["line"]
                implied = row["receiving_implied_minimum"] if leg["market"] == "C" else math.floor(s_line) + 1 if leg["market"] == "S" else None
                assert leg["side"] in ("over", "at_least") and implied is not None and threshold <= implied, (row, leg)
            key = (json.dumps(extras, sort_keys=True), row["american"])
            if key not in variants:
                estimates = None
                if models and relation != "incomparable":
                    estimates = {method: decimal(row["american"]) * models[method]["OU"] - 1 if models[method] else None for method in ["proportional", "power", "additive"]}
                variants[key] = {"extra_legs": extras, "all_extra_legs_strictly_redundant": True, "american": row["american"], "decimal": decimal(row["american"]), "legs": row["legs"], "observations": [], "ev": estimates, "ev_type": {"exact": "estimate", "subset": "lower_bound", "superset": "upper_bound"}.get(relation) if estimates else None}
            variants[key]["observations"].append(row["source"])
        baseline = next(v for v in variants.values() if not v["extra_legs"])
        for variant in variants.values():
            variant["gross_payout_change_vs_baseline"] = variant["decimal"] / baseline["decimal"] - 1
        urls = preserved_urls.get(player, {"score": next((x["score_url"] for x in captures if x["score_url"]), None), "fanduel": next((x["url"] for x in references if x["url"]), None), "provenance": "quote captures if present; missing URLs remain null"})
        result.append({"player": player, "event": event, "urls": urls, "score_S_line": s_line, "score_R_line": r_line, "receiving_implied_minimum": captures[0]["receiving_implied_minimum"], "reference": reference, "variants": list(variants.values())})

    lloyd = next(x for x in result if x["player"] == "MarShawn Lloyd")
    lloyd["reference"]["summary_only_unverified_OU"] = {"american": 692, "source": "mlb_scan_future_nfl.json#/lloyd_reference", "reason_not_used": "The only raw OU snapshot (observations[29]) is suspended and has no quote. Structured summary reports +692 without a retained settled raw OU snapshot or timestamp. Recapture required."}
    lloyd["reference"]["summary_only_sensitivity"] = devig({"OO": 113, "OU": 692, "UO": 684, "UU": 112})
    tuten = next(x for x in result if x["player"] == "Bhayshul Tuten")
    tuten["reference_gap"] = "No preserved FanDuel rushing+receiving/rushing partition. Its saved S/C quartet concerns a different target and cannot devig this S/R event."
    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "All preserved theScore rushing+receiving OVER/rushing UNDER target captures in the listed prior source files; every distinct observed valid odds/leg variant, including baselines and reductions. This is prior tested coverage, not every currently available market.",
        "reference_book": "FanDuel",
        "formulas": {"american_to_decimal": "1+a/100 if a>0 else 1+100/abs(a)", "q": "q_i=1/decimal_i", "additive": "p_i=q_i-(sum(q)-1)/4; invalid if any p outside [0,1]", "power": "p_i=q_i**k; choose k so sum(q_i**k)=1", "ev": "Score_decimal*p_OU-1", "relation": "For differing thresholds, only exact matches give an EV estimate. FD subset gives lower bound; superset gives upper bound; incomparable gives no bound."},
        "assumptions": ["All four FD cells form the same exhaustive non-push half-yard partition and share settlement conditions.", "Scores and FD references were sequential quotes, not synchronized or accepted wagers.", "Identical full-game statistical definitions, participation conditions, and normal completed-game settlement are assumed; no promotional or Bet Protect value is included.", "Model-based lower bounds below zero do not establish that the wider Score event is negative EV."],
        "source_sha256": source_hashes,
        "players": result,
        "excluded_target_captures": exclusions,
        "other_scope_exclusions": ["Passing+rushing/passing-under cases (Jalon Daniels and Dak Prescott)", "Rushing-under/receiving-under, S-over/receiving-under, S-under targets", "MLB/NHL/WNBA cases and NFL team totals", "Contaminated continued-observations.json score[12] was a team-total test with an unrelated MLB leg, outside this target scope."],
    }
    output = ROOT / "sgp-research/sgp_inventory_prior.json"
    output.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {output}: {len(result)} players, {sum(len(p['variants']) for p in result)} valid variants, {len(exclusions)} excluded target captures")
    for player in result:
        best = max(player["variants"], key=lambda x: x["decimal"])
        print(player["player"], "best", best["american"], "EV", best["ev"], "type", best["ev_type"])


if __name__ == "__main__":
    main()
