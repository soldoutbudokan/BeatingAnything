"""Early-payout value scanner.

A book that pays a pre-game moneyline as a win once the team leads by a set margin
(bet365: NFL/NCAAF 17, NBA 20, soccer 2; FanDuel: soccer 2) adds the chance that the
team reaches that lead and still fails to win. For each game:

    p      = fair win probability, de-vigged from the sharpest prices available
    extra  = P(reach the lead and not win), looked up from config/early_payout_curves.json
    EV     = book decimal odds * (p + extra) - 1

A row is playable when EV clears rules.min_ev and passes the sanity gates.

    BETTINGPROS_API_KEY=... python -m beating.early_payout scan

Writes live/early-payout/picks.json and appends new playable rows to
live/early-payout/history.csv. Places no bets.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/early_payout.json"
CURVES = ROOT / "config/early_payout_curves.json"
LIVE = ROOT / "live/early-payout"
API = "https://api.bettingpros.com/v3"
ET = ZoneInfo("America/New_York")
HISTORY_FIELDS = ["seen_utc", "key", "sport", "start_utc", "matchup", "team", "book", "american",
                  "fair_p", "fair_source", "extra", "ev", "stake"]


# ---------------------------------------------------------------- pricing ----

def american_to_decimal(a: float) -> float:
    return 1 + (100 / -a if a < 0 else a / 100)


def decimal_to_american(d: float) -> int:
    return round(100 * (d - 1)) if d >= 2 else round(-100 / (d - 1))


def devig(decimals: list[float]) -> list[float]:
    """Proportional (multiplicative) vig removal."""
    implied = [1 / d for d in decimals]
    total = sum(implied)
    return [x / total for x in implied]


def extra_for(p: float, points: list[dict]) -> float:
    """Linear interpolation of the payout curve; shrinks toward 0 outside the fitted range."""
    ps, es = [q["p"] for q in points], [q["extra"] for q in points]
    if p <= ps[0]:
        return es[0] * p / ps[0]
    if p >= ps[-1]:
        return es[-1] * (1 - p) / (1 - ps[-1])
    for i in range(1, len(ps)):
        if p <= ps[i]:
            w = (p - ps[i - 1]) / (ps[i] - ps[i - 1])
            return es[i - 1] + w * (es[i] - es[i - 1])
    return es[-1]


def expected_value(decimal: float, p: float, extra: float) -> float:
    return decimal * (p + extra) - 1


def kelly_stake(decimal: float, p: float, extra: float, rules: dict) -> float:
    """Fractional Kelly on the payout-adjusted win probability, capped."""
    q = min(p + extra, 1.0)
    f = (decimal * q - 1) / (decimal - 1)
    frac = max(0.0, min(rules["kelly_fraction"] * f, rules["max_stake_fraction"]))
    return round(frac * rules["bankroll"], 2)


# ----------------------------------------------------------- BettingPros ----

def api_key() -> str:
    key = os.environ.get("BETTINGPROS_API_KEY", "").strip()
    if not key:
        raise SystemExit("BETTINGPROS_API_KEY is not set; no requests made.")
    return key


def get(path: str, params: dict, key: str, tries: int = 4) -> dict:
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"x-api-key": key, "User-Agent": "Mozilla/5.0"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.load(r)
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(2 ** attempt)  # the offers endpoint intermittently 504s


def fetch_events(sport: str, days: int, key: str, now: datetime) -> list[dict]:
    events = {}
    for i in range(days):
        day = (now.astimezone(ET) + timedelta(days=i)).strftime("%Y-%m-%d")
        for e in get("events", {"sport": sport, "date": day}, key).get("events", []):
            events[e["id"]] = e
    return list(events.values())


def fetch_offer(sport: str, market: int, event_id: int, key: str) -> dict | None:
    offers = get("offers", {"sport": sport, "market_id": market, "event_id": event_id}, key).get("offers", [])
    return offers[0] if offers else None


# --------------------------------------------------------------- parsing ----

def parse_time(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def selection_key(sel: dict) -> str:
    if sel.get("participant"):
        return str(sel["participant"])
    text = f"{sel.get('selection', '')} {sel.get('label', '')}".lower()
    return "draw" if "draw" in text or "tie" in text else (sel.get("label") or "?")


def book_quotes(offer: dict) -> tuple[dict, dict]:
    """{book_id: {selection_key: quote}} and {selection_key: label}; main active lines only."""
    quotes, labels = {}, {}
    for sel in offer.get("selections", []):
        k = selection_key(sel)
        labels[k] = sel.get("label") or k
        for b in sel.get("books", []):
            lines = [ln for ln in b.get("lines", []) if ln.get("active", True) and not ln.get("is_off") and ln.get("cost")]
            main = [ln for ln in lines if ln.get("main")] or lines
            if main:
                ln = main[0]
                quotes.setdefault(b["id"], {})[k] = {"american": ln["cost"], "updated": ln.get("updated"), "link": ln.get("link")}
    return quotes, labels


def complete_devig(quotes: dict, keys: list[str], band: list[float]) -> list[float] | None:
    if any(k not in quotes for k in keys):
        return None
    dec = [american_to_decimal(quotes[k]["american"]) for k in keys]
    overround = sum(1 / d for d in dec)
    return devig(dec) if band[0] <= overround <= band[1] else None


def fair_probabilities(quotes: dict, keys: list[str], cfg: dict, exclude: int) -> tuple[dict | None, str]:
    """Pinnacle if quoted; else median of exchanges; else median of other sportsbooks."""
    bp, band = cfg["bettingpros"], cfg["rules"]["vig_band"]
    pin = bp["books"]["pinnacle"]
    if pin != exclude and pin in quotes:
        p = complete_devig(quotes[pin], keys, band)
        if p:
            return dict(zip(keys, p)), "pinnacle"
    for label, ids in (("exchanges", bp["exchanges"].values()), ("books", bp["books"].values())):
        sets = [complete_devig(quotes[i], keys, band) for i in ids if i in quotes and i != exclude]
        sets = [s for s in sets if s]
        if sets:
            med = [statistics.median(s[j] for s in sets) for j in range(len(keys))]
            total = sum(med)
            return {k: m / total for k, m in zip(keys, med)}, f"{label} ({len(sets)})"
    return None, "none"


def evaluate(event: dict, offer: dict, sport: str, cfg: dict, curves: dict, now: datetime) -> list[dict]:
    quotes, labels = book_quotes(offer)
    keys = sorted(labels, key=lambda k: (k == "draw", k))
    need = 3 if sport == "SOCCER" else 2
    if len(keys) != need:
        return []
    start = parse_time(event["scheduled"])
    books, rules = cfg["bettingpros"]["books"], cfg["rules"]
    home, away = event.get("home"), event.get("visitor")
    matchup = f"{labels.get(str(away), away)} @ {labels.get(str(home), home)}"
    rows = []
    for book, sports in cfg["promos"].items():
        if sport not in sports or book not in books or books[book] not in quotes:
            continue
        bid = books[book]
        fair, source = fair_probabilities(quotes, keys, cfg, exclude=bid)
        for k in keys:
            if k == "draw" or k not in quotes[bid]:
                continue
            q = quotes[bid][k]
            dec = american_to_decimal(q["american"])
            flags = []
            age = (now - parse_time(q["updated"])).total_seconds() / 60 if q.get("updated") else None
            if age is not None and age > rules["max_quote_age_minutes"]:
                flags.append("STALE_QUOTE")
            if start <= now:
                flags.append("STARTED")
            row = {"key": f"{event['id']}|{book}|{k}", "event_id": event["id"], "sport": sport,
                   "start_utc": start.isoformat(), "matchup": matchup, "team": labels[k], "book": book,
                   "american": q["american"], "decimal": round(dec, 4), "link": q.get("link"),
                   "quote_age_min": None if age is None else round(age), "fair_source": source}
            if fair is None:
                rows.append({**row, "flags": flags + ["NO_FAIR"], "play": False})
                continue
            p = fair[k]
            ex = extra_for(p, curves[sport]["points"])
            ev = expected_value(dec, p, ex)
            if ev > rules["max_ev"]:
                flags.append("SUSPECT_EV")  # large claims are usually a stale or mismatched quote
            row.update({"fair_p": round(p, 4), "fair_american": decimal_to_american(1 / p), "extra": round(ex, 4),
                        "ev": round(ev, 4), "ev_without_payout": round(dec * p - 1, 4),
                        "breakeven_american": decimal_to_american(1 / (p + ex)),
                        "stake": kelly_stake(dec, p, ex, rules), "flags": flags,
                        "play": ev >= rules["min_ev"] and not flags})
            rows.append(row)
    return rows


# ------------------------------------------------------------------ scan ----

def scan(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cfg, curves = json.loads(CONFIG.read_text()), json.loads(CURVES.read_text())["sports"]
    key, bp = api_key(), cfg["bettingpros"]
    sports = sorted({s for promo in cfg["promos"].values() for s in promo if s in curves})
    rows, errors, counts = [], [], {}
    for sport in sports:
        try:
            events = [e for e in fetch_events(sport, bp["days_ahead"], key, now) if parse_time(e["scheduled"]) > now]
        except Exception as exc:
            errors.append(f"{sport} events: {exc}")
            continue
        counts[sport] = len(events)

        def one(e, sport=sport):
            try:
                offer = fetch_offer(sport, bp["moneyline_market"][sport], e["id"], key)
                return evaluate(e, offer, sport, cfg, curves, now) if offer else []
            except Exception as exc:
                errors.append(f"{sport} {e['id']}: {exc}")
                return []

        with ThreadPoolExecutor(6) as pool:
            for r in pool.map(one, events):
                rows.extend(r)
    rows.sort(key=lambda r: (not r["play"], -(r.get("ev") or -9)))
    return {"generated_utc": now.isoformat(timespec="seconds"), "events": counts, "errors": errors, "rows": rows}


def write(result: dict) -> list[dict]:
    """Write picks.json; append playable rows to history.csv. Returns plays not on the previous sheet."""
    LIVE.mkdir(parents=True, exist_ok=True)
    picks = LIVE / "picks.json"
    before = set()
    if picks.exists():
        before = {r["key"] for r in json.loads(picks.read_text()).get("rows", []) if r.get("play")}
    plays = [r for r in result["rows"] if r["play"]]
    new = [r for r in plays if r["key"] not in before]
    result["new_keys"] = [r["key"] for r in new]
    picks.write_text(json.dumps(result, indent=1) + "\n")
    hist = LIVE / "history.csv"
    last_price = {}
    if hist.exists():
        with hist.open() as fh:
            for h in csv.DictReader(fh):
                last_price[h["key"]] = h["american"]
    fresh = [r for r in plays if last_price.get(r["key"]) != str(r["american"])]  # log a key again only when its price moves
    if fresh:
        new_file = not hist.exists()
        with hist.open("a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=HISTORY_FIELDS, extrasaction="ignore")
            if new_file:
                w.writeheader()
            for r in fresh:
                w.writerow({**r, "seen_utc": result["generated_utc"]})
    return new


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=["scan"])
    ap.parse_args(argv)
    result = scan()
    new = write(result)
    plays = [r for r in result["rows"] if r["play"]]
    print(f"events {result['events']} | rows {len(result['rows'])} | playable {len(plays)} | new {len(new)} | errors {len(result['errors'])}")
    for r in new:
        print(f"NEW  {r['sport']:<6} {r['team']:<24} {r['book']:<8} {r['american']:>+5}  fair {r['fair_american']:>+5}  "
              f"EV {r['ev']:+.1%}  stake {r['stake']}  {r['matchup']}  {r['start_utc']}")
    for e in result["errors"][:10]:
        print("ERROR", e, file=sys.stderr)


if __name__ == "__main__":
    main()
