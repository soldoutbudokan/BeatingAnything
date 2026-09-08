"""Observe explicit FanDuel moneylines from Covers' ordinary public HTML.

These are unverified aggregator observations for paper research, never certified
executable sportsbook prices. The source line-change time is not a heartbeat.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from lxml import html as html_parser

from beating.odds import TEAM_IDS, american_to_decimal

URL = "https://www.covers.com/sport/baseball/mlb/odds"


def _utc(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("A timezone is required")
    return result.astimezone(timezone.utc)


def _event_start(value: str) -> datetime:
    # The publisher uses month-day-year, despite the schema.org ISO convention.
    try:
        return datetime.strptime(value, "%m-%d-%YT%H:%M:%S%z").astimezone(timezone.utc)
    except ValueError:
        return _utc(value)


def parse_page(html: str, observed_at: str, source_uri: str, schedule: dict):
    now = _utc(observed_at)
    tree = html_parser.fromstring(html)
    tables = tree.xpath('//table[@id="moneyline-table"]')
    if len(tables) != 1:
        raise ValueError("Expected one full-game moneyline table")
    events = {}
    for script in tree.xpath('//script[@type="application/ld+json"]/text()'):
        try:
            event = json.loads(script)
        except (ValueError, TypeError):
            continue
        if isinstance(event, dict) and event.get("@type") == "SportsEvent":
            event_id = str(event.get("identifier", "")).rsplit("-", 1)[-1]
            if event_id in events:
                raise ValueError("Duplicate structured event identity")
            events[event_id] = event
    updated_raw = tree.xpath('//*[contains(@class,"__updatedDate")]/text()')
    updated_at = None
    if updated_raw:
        text = updated_raw[0].strip()
        stamp = re.fullmatch(r"Last updated (.+) ET", text)
        if stamp:
            local = datetime.strptime(stamp.group(1), "%b %d, %Y, %I:%M %p")
            updated_at = local.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
    index = defaultdict(dict)
    for day in schedule.get("dates", []):
        for game in day.get("games", []):
            key = (game.get("officialDate", day["date"]),
                   game["teams"]["away"]["team"]["id"],
                   game["teams"]["home"]["team"]["id"])
            index[key][game["gamePk"]] = game
    skipped = Counter(); quotes = []; seen = set()
    digest = hashlib.sha256(html.encode()).hexdigest()
    cells = tables[0].xpath('.//*[@data-book="FanDuel"]')
    # Page time verifies only a refreshed aggregator page, not bookmaker execution.
    page_fresh = updated_at is not None and -120 <= (now - updated_at).total_seconds() <= 900
    for cell in cells:
        source_id = cell.get("data-game")
        event = events.get(source_id)
        if not event:
            skipped["missing_structured_event_metadata"] += 1; continue
        if not page_fresh:
            skipped["missing_or_old_page_update_time"] += 1; continue
        if event.get("eventStatus") != "https://schema.org/EventScheduled":
            skipped["not_scheduled_in_source"] += 1; continue
        try:
            starts = _event_start(event["startDate"])
            away_abbr = event["awayTeam"]["name"].split()[0]
            home_abbr = event["homeTeam"]["name"].split()[0]
            away_id, home_id = TEAM_IDS[away_abbr], TEAM_IDS[home_abbr]
        except (ValueError, KeyError, IndexError):
            skipped["unrecognized_event_identity"] += 1; continue
        if starts <= now:
            skipped["event_already_started"] += 1; continue
        day = starts.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        matches = list(index.get((day, away_id, home_id), {}).values())
        if len(matches) != 1:
            skipped["ambiguous_or_missing_mlb_schedule_match"] += 1; continue
        game = matches[0]
        if game.get("gameType") != "R" or game.get("doubleHeader", "N") != "N":
            skipped["not_unambiguous_regular_season"] += 1; continue
        if game.get("status", {}).get("abstractGameState") != "Preview" or game.get("rescheduleDate"):
            skipped["not_pregame_in_mlb_schedule"] += 1; continue
        official_start = _utc(game["gameDate"])
        if official_start <= now or abs((official_start - starts).total_seconds()) > 300:
            skipped["start_time_mismatch"] += 1; continue
        # td[data-type] incorrectly says spread for moneyline cells; require table
        # identity and moneyline anchors, then parse exactly one side of each pair.
        prices = {}
        try:
            for side in ("home", "away"):
                values = cell.xpath(f'.//div[contains(@class,"{side}-cell")]//a[contains(@class,"moneyline")]//span[contains(@class,"__american")]/text()')
                if len(values) != 1:
                    raise ValueError("Missing or ambiguous paired quote")
                prices[side] = int(values[0].strip().replace("−", "-"))
            dec_home = american_to_decimal(prices["home"])
            dec_away = american_to_decimal(prices["away"])
            if not 1 <= 1 / dec_home + 1 / dec_away <= 1.25:
                raise ValueError("Implausible paired market")
        except (ValueError, TypeError):
            skipped["invalid_or_incomplete_moneyline_pair"] += 1; continue
        event_id = f'mlb:{game["gamePk"]}'
        if event_id in seen:
            raise ValueError("Duplicate matched FanDuel event")
        seen.add(event_id)
        line_time_raw = cell.get("data-date")
        try:
            line_time = datetime.fromtimestamp(int(line_time_raw), timezone.utc).isoformat()
        except (ValueError, TypeError, OverflowError):
            line_time = None
        quotes.append({
            "event_id": event_id, "sport": "MLB", "bookmaker": "FanDuel", "market": "moneyline",
            "home_team": game["teams"]["home"]["team"]["name"],
            "away_team": game["teams"]["away"]["team"]["name"],
            "home_team_id": home_id, "away_team_id": away_id,
            "starts_at": official_start.isoformat(), "observed_at": now.isoformat(),
            "status": "open", "is_live": False,
            "decimal_home": dec_home, "decimal_away": dec_away,
            "american_home": prices["home"], "american_away": prices["away"],
            "source": {"uri": source_uri, "provider": "Covers public odds page",
                "verified": False, "verification_method": "Explicit FanDuel label and paired market; aggregator execution unverified",
                "historical": False, "synthetic": False, "response_sha256": digest,
                "source_event_id": source_id, "source_page_updated_at": updated_at.isoformat(),
                "source_line_time_raw": line_time_raw, "source_line_time_utc": line_time,
                "source_line_time_semantics": "Unverified line-change time; not a freshness heartbeat",
                "bookmaker_jurisdiction": "Unverified; public page naturally returned CA/ON settings"},
        })
    status = {"observed_at": now.isoformat(), "source_uri": source_uri, "response_sha256": digest,
        "source_page_updated_at": updated_at.isoformat() if updated_at else None,
        "source_page_update_raw": updated_raw, "source_fanduel_cells": len(cells),
        "structured_events": len(events), "fanduel_quotes": len(quotes),
        "verified_fanduel_quotes": 0, "skipped": dict(skipped),
        "status": "paper_observations_available" if quotes else "blocked",
        "reason": "aggregator_quotes_require_direct_verification" if quotes else "no_eligible_fanduel_quotes",
        "betting_alerts_enabled": False, "research_status": "unproven", "notifications_sent": 0}
    return quotes, status


def collect(output="state", source_file=None, schedule_file=None):
    root = Path(output); root.mkdir(parents=True, exist_ok=True)
    try:
        if source_file:
            payload = Path(source_file).read_bytes()
        else:
            with urlopen(Request(URL, headers={"User-Agent": "BeatingAnything-research/0.1"}), timeout=30) as response:
                payload = response.read(12 * 1024 * 1024)
        # Receipt time is captured immediately after odds response, before schedule I/O.
        observed = datetime.now(timezone.utc)
        today = observed.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        schedule_url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}&hydrate=probablePitcher"
        if schedule_file:
            schedule_bytes = Path(schedule_file).read_bytes()
        else:
            with urlopen(Request(schedule_url, headers={"User-Agent": "BeatingAnything-research/0.1"}), timeout=30) as response:
                schedule_bytes = response.read(12 * 1024 * 1024)
        quotes, status = parse_page(payload.decode("utf-8"), observed.isoformat(), URL, json.loads(schedule_bytes))
        if source_file or schedule_file:
            status.update({"offline_fixture": True, "reason": "offline_fixture_not_live"})
            for quote in quotes:
                quote["source"]["historical"] = True
        snapshots = root / "snapshots"; snapshots.mkdir(exist_ok=True)
        name = f'covers-{observed.strftime("%Y%m%dT%H%M%S%fZ")}-{hashlib.sha256(payload).hexdigest()[:12]}'
        gzip_path = snapshots / f"{name}.html.gz"
        with gzip.open(gzip_path, "wb") as stream:
            stream.write(payload)
        schedule_path = snapshots / f"{name}.schedule.json"
        schedule_path.write_bytes(schedule_bytes)
        status.update({"raw_snapshot": str(gzip_path), "schedule_snapshot": str(schedule_path),
            "schedule_source_uri": schedule_url, "schedule_sha256": hashlib.sha256(schedule_bytes).hexdigest()})
        (snapshots / f"{name}.json").write_text(json.dumps({"status": status, "quotes": quotes}, indent=2) + "\n")
        with (root / "quote-observations.jsonl").open("a") as stream:
            for quote in quotes:
                stream.write(json.dumps(quote, separators=(",", ":")) + "\n")
    except Exception as exc:
        quotes = []
        status = {"observed_at": datetime.now(timezone.utc).isoformat(), "source_uri": URL,
            "status": "blocked", "reason": "source_or_parser_unavailable", "error_type": type(exc).__name__,
            "fanduel_quotes": 0, "verified_fanduel_quotes": 0, "betting_alerts_enabled": False,
            "research_status": "unproven", "notifications_sent": 0}
    (root / "quotes.json").write_text(json.dumps(quotes, indent=2) + "\n")
    (root / "live-status.json").write_text(json.dumps(status, indent=2) + "\n")
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="state")
    parser.add_argument("--source-file", help="Offline parsing only; marks observations historical")
    parser.add_argument("--schedule-file", help="Offline schedule only; marks observations historical")
    args = parser.parse_args()
    print(json.dumps(collect(args.output, args.source_file, args.schedule_file), indent=2))


if __name__ == "__main__":
    main()
