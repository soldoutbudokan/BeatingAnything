"""Recheck the September 23 birdie lead using observed Under rows only.

Exploratory source/return diagnostic, not a new holdout. No missing side is
created, no price is inferred from an implied-probability column, and both
plain-birdie and birdie-or-better settlement definitions remain visible.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ODDS = ROOT / "data/raw/golf-historical-price-search-2026-09-19/alpha/data/odds.csv"
HISTORY = ROOT / "data/raw/golf-birdie-recheck-2026-09-26/historical_rounds_all.csv"
OUTPUT = ROOT / "reports/golf-birdie-recheck-2026-09-26.json"
DETAIL = ROOT / "data/raw/golf-birdie-recheck-2026-09-26/under-diagnostic.csv"
PIN = "5508f6f35830f09d0b1e0c06abed0b2b489dde04"


def fold(s):
    s = unicodedata.normalize("NFKD", str(s).replace("ø", "o"))
    return re.sub(r"[^a-z0-9]", "", s.encode("ascii", "ignore").decode().lower())


# Name/event aliases are identity repairs, shared across years and outcomes.
EVENT_ALIASES = {
    "usmasters": "masterstournament", "themasters": "masterstournament",
    "theusopen": "usopen", "memorialtournament": "thememorialtournamentpresentedbyworkday",
    "arnoldpalmerinvitational": "arnoldpalmerinvitationalpresentedbymastercard",
    "canadianopen": "rbccanadianopen", "mexicoopen": "mexicoopenatvidanta",
    "mexicoopenatvidantaworld": "mexicoopenatvidanta",
    "rocketclassic": "rocketmortgageclassic",
}
NAME_ALIASES = {
    "rmcllroy": "rmcilroy", "sjager": "sjaeger", "sjim": "sungjaeim",
    "shkim": "seonghyeonkim", "swkim": "siwookim", "bhan": "byeonghunan",
    "khlee": "kyounghoonlee", "camyoung": "cameronyoung",
    "mattfitzpatrick": "matthewfitzpatrick",
}


def event_name(s):
    k = fold(re.sub(r"\s+20\d\d$", "", str(s)))
    return EVENT_ALIASES.get(k, k)


def name_parts(s):
    s = str(s)
    if "," in s:
        last, first = s.split(",", 1)
        s = first.strip() + " " + last.strip()
    return s.split()


def name_matches(odds, historical):
    a, b = name_parts(odds), name_parts(historical)
    full_a = NAME_ALIASES.get(fold(" ".join(a)), fold(" ".join(a)))
    full_b = NAME_ALIASES.get(fold(" ".join(b)), fold(" ".join(b)))
    if full_a == full_b:
        return True
    # Compare the full historical surname, including Van Rooyen. Full given
    # names cannot degrade to a first-initial match. Abbreviations must be
    # explicit and uniquely match inside the event/round below.
    if "," not in str(historical):
        return False
    last, first = str(historical).split(",", 1)
    initials = "".join(fold(p)[0] for p in first.split() if fold(p))
    last, first = fold(last), fold(first)
    if not full_a.endswith(last) or "." not in str(odds):
        return False
    given = full_a[:-len(last)]
    return bool(given) and (first.startswith(given) or given == initials)


def decimal(american):
    a = np.asarray(american, dtype=float)
    if np.any(~np.isfinite(a)) or np.any(np.abs(a) < 100):
        raise ValueError("Invalid American price")
    return np.where(a > 0, 1 + a / 100, 1 + 100 / np.abs(a))


def source(path, blob):
    body = path.read_bytes()
    actual = hashlib.sha1(b"blob " + str(len(body)).encode() + b"\0" + body).hexdigest()
    if actual != blob:
        raise ValueError(f"Pinned source mismatch: {path}")
    return {"path": str(path.relative_to(ROOT)), "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(), "git_blob": actual}


def summarize(frame, stat, price):
    known = frame[frame[stat].notna()].copy()
    if known.empty:
        return {"offered": len(frame), "graded": 0}
    delta = known[stat] - known.line
    dec = decimal(known[price])
    profits = np.where(delta < 0, dec - 1, np.where(delta > 0, -1, 0))
    known["profit"] = profits
    known["win"] = delta < 0
    # Event blocks retain dependence across golfers, rounds and alternate lines.
    blocks = known.groupby(["year", "event_id"])["profit"].agg(["sum", "count"])
    rng = np.random.default_rng(1729)
    boot = rng.integers(len(blocks), size=(10000, len(blocks)))
    returns = blocks["sum"].to_numpy()[boot].sum(axis=1) / blocks["count"].to_numpy()[boot].sum(axis=1)
    missing = len(frame) - len(known)
    decisions = (delta != 0).sum()
    return {
        "offered": len(frame), "graded": len(known), "missing": missing,
        "events": len(blocks), "wins": int((delta < 0).sum()),
        "losses": int((delta > 0).sum()), "pushes": int((delta == 0).sum()),
        "win_rate_excluding_pushes": float((delta < 0).sum() / decisions) if decisions else None,
        "units": float(profits.sum()), "roi_all_graded_stakes": float(profits.mean()),
        "roi_event_bootstrap_95pct_exploratory": np.quantile(returns, [.025, .975]).tolist(),
        "roi_missing_all_losses": float((profits.sum() - missing) / len(frame)),
        "mean_decimal_price": float(dec.mean()),
        "mean_break_even_conditional_on_no_push": float((1 / dec).mean()),
        "by_year": {str(int(y)): {"n": len(g), "units": float(g.profit.sum()),
                     "roi": float(g.profit.mean())} for y, g in known.groupby("year")},
    }


def main():
    sources = [source(ODDS, "104ab16b9657800309f45d8e102132b835e70459"),
               source(HISTORY, "f71c0a71490542179633e3da556b4e7996646167")]
    h = pd.read_csv(HISTORY)
    h = h[h.tour == "pga"].copy()
    h["event_key"] = h.event_name.map(event_name)
    h["holes"] = h[["birdies", "eagles_or_better", "pars", "bogies", "doubles_or_worse"]].sum(axis=1, min_count=5)
    odds = pd.read_csv(ODDS)
    b = odds[odds.MARKET_TYPE.isin(["GOLF:FT:CTBIR", "GOLF:FT:ROUNDNUMBIRDIES"])].copy()
    b["year"] = pd.to_datetime(b.EVENT_START_TIME_UTC, utc=True).dt.year
    b["event_key"] = b.COMPETITION.map(event_name)
    b["round_num"] = (b.SPORT_EVENT.str.extract(r"Round\s*(\d)", expand=False)
                        .fillna(b.MARKET_NAME.str.extract(r"Round\s*(\d)", expand=False))).astype(int)
    b["player"] = b.MARKET_NAME.str.replace(r"\s*-?\s*(?:Round\s*\d+\s*)?Total Birdies.*$", "", regex=True).str.strip()
    b["line"] = b.SELECTION.str.extract(r"([\d.]+)$", expand=False).astype(float)
    b["side"] = b.SELECTION.str.split().str[0]
    # A revised tee time is not another bet. Four Masters contracts have two
    # start times but the same instrument ID and identical opening/closing odds.
    key = ["year", "event_key", "round_num", "player", "line", "side"]
    pricecols = ["OPENING_AMERICAN_ODDS", "CLOSING_AMERICAN_ODDS"]
    conflicts = b.groupby(key)[pricecols].nunique().gt(1).any(axis=1)
    if any(k[-1] == "Under" for k in conflicts[conflicts].index):
        raise ValueError("Conflicting Under prices; cannot choose an advantageous row")
    # Four 2026 Over groups have conflicting close columns. Exclude every
    # conflicting group; none supplies an Under in this diagnostic.
    clean = b.set_index(key).loc[lambda x: ~x.index.isin(conflicts[conflicts].index)].reset_index()
    unique = clean.drop_duplicates(key)
    board_key = key[:-1]
    over = unique[unique.side == "Over"][board_key + pricecols].rename(
        columns={p: "over_" + p for p in pricecols})
    under = unique[unique.side == "Under"].merge(over, on=board_key, how="left", validate="one_to_one")
    inventory = {"raw_birdie_rows": len(b), "distinct_side_rows": len(unique),
                 "distinct_observed_unders": len(under), "conflicting_price_groups": int(conflicts.sum()),
                 "years": b.groupby("year").size().to_dict()}
    records = []
    for _, u in under.iterrows():
        pool = h[(h.year == u.year) & (h.event_key == u.event_key) & (h.round_num == u.round_num)]
        pool = pool[pool.player_name.map(lambda name: name_matches(u.player, name))]
        rec = u.to_dict()
        rec.update({"join_status": "missing" if not len(pool) else "ambiguous",
                    "actual_birdies": np.nan, "actual_birdies_or_better": np.nan,
                    "event_id": np.nan, "dg_id": np.nan})
        if len(pool) == 1:
            row = pool.iloc[0]
            days_to_end = (pd.Timestamp(row.event_completed, tz="UTC") -
                           pd.Timestamp(u.EVENT_START_TIME_UTC).floor("D")).days
            rec.update({"event_id": row.event_id, "dg_id": row.dg_id,
                        "matched_player": row.player_name, "matched_event": row.event_name,
                        "days_to_event_end": days_to_end, "holes": row.holes,
                        "join_status": "fixture_date_mismatch" if not 0 <= days_to_end <= 6 else
                                       "complete" if row.holes == 18 else "incomplete_counts"})
            if rec["join_status"] == "complete":
                rec["actual_birdies"] = row.birdies
                rec["actual_birdies_or_better"] = row.birdies + row.eagles_or_better
        records.append(rec)
    frame = pd.DataFrame(records)
    inventory["join_status"] = frame.join_status.value_counts().to_dict()
    inventory["join_status_by_year"] = {str(y): g.join_status.value_counts().to_dict() for y, g in frame.groupby("year")}
    # Strict old-period diagnostic; 2026 is separately displayed, never quietly
    # added to the original three-year result or called an untouched holdout.
    cohorts = {"2023_2025_observed_unders": frame[frame.year <= 2025],
               "2026_observed_unders": frame[frame.year == 2026],
               "2023_2025_paired_boards": frame[(frame.year <= 2025) & frame.over_OPENING_AMERICAN_ODDS.notna()],
               "2026_paired_boards": frame[(frame.year == 2026) & frame.over_OPENING_AMERICAN_ODDS.notna()]}
    results = {}
    for cohort, f in cohorts.items():
        results[cohort] = {stat: {price: summarize(f, stat, price) for price in pricecols}
                           for stat in ["actual_birdies", "actual_birdies_or_better"]}
    DETAIL.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(DETAIL, index=False)
    report = {"status": "exploratory recheck; no verified executable closing prices or edge",
              "source_repository_commit": PIN, "sources": sources, "inventory": inventory,
              "results": results, "detail_path": str(DETAIL.relative_to(ROOT)),
              "limitations": ["The original 863-line script was not retained; this is a new transparent diagnostic, not exact reproduction.",
              "Actual observed Under rows only; absent Under prices are never synthesized from Over prices.",
              "Original pre-2026 Hard Rock settlement definition remains unverified; both definitions reported.",
              "Opening and closing quote times absent. Closing columns appear de-vigged and are not certified executable prices.",
              "No model selection or untouched holdout; all intervals exploratory and uncorrected for past searches.",
              "Historical outcome feed is a third-party retrospective export; incomplete holes remain unresolved.",
              "Multiple lines and player rounds are not independent bets; bootstrap clusters whole events."]}
    OUTPUT.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
