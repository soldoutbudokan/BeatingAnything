"""Public TennisExplorer acquisition for frozen N2/N3; no model evaluation.

Raw HTML, immutable sample pins and an append-only attempt ledger remain local.
Only the result table, match header and literal Pinnacle price histories are
parsed. Present-day rankings and player summaries are never model inputs.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
import time
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from lxml import html

SOURCE = "https://www.tennisexplorer.com"
VERSION = "tennisexplorer_n2_n3_v1"
PRAGUE = ZoneInfo("Europe/Prague")


def _classes(node):
    return set(node.get("class", "").split())


def _text(node):
    return " ".join(node.text_content().split())


def _plain(node):
    # XPath skips superscript text without changing the source tree.
    return "".join(node.xpath('.//text()[not(ancestor::sup)]')).strip()


def _player(node):
    links = node.xpath('.//a[starts-with(@href,"/player/")]/@href')
    if len(links) != 1:
        raise ValueError("missing_or_ambiguous_player_id")
    slug = urlparse(links[0]).path.strip("/").split("/")
    if len(slug) != 2 or not slug[1]:
        raise ValueError("invalid_player_id")
    return slug[1]


def _document(raw):
    if not isinstance(raw, (bytes, str)) or not raw:
        raise ValueError("empty_source")
    return html.fromstring(raw)


def _result_rows(raw, day):
    day = date.fromisoformat(day)
    doc = _document(raw)
    tabs = doc.xpath('//li[contains(concat(" ",normalize-space(@class)," ")," set ")]/span[@class="tab"]')
    dates = [re.sub(r"\s+", "", _text(t)) for t in tabs]
    if day.strftime("%d.%m.%Y") not in dates:
        raise ValueError("results_date_not_verified")
    selected = doc.xpath('//li[contains(concat(" ",normalize-space(@class)," ")," set ")]/a/@href')
    if not any(parse_qs(urlparse(link).query).get("type") == ["atp-single"] for link in selected):
        raise ValueError("atp_singles_filter_not_verified")
    tables = doc.xpath('//div[@id="center"]//table[contains(concat(" ",normalize-space(@class)," ")," result ")]')
    if not tables:
        if re.search(r"no matches|no results", _text(doc), re.I):
            return []
        raise ValueError("results_table_missing")
    result = []
    tournament = None
    for table in tables:
        for row in table.xpath('./tbody/tr|./tr'):
            if "head" in _classes(row):
                names = row.xpath('./td[contains(concat(" ",normalize-space(@class)," ")," t-name ")]')
                tournament = _text(names[0]) if names else None
                continue
            if row.xpath('./td/a[contains(@href,"/match-detail/")]'):
                result.append((tournament, row))
    return result


def parse_fixtures(raw, day: str) -> list[dict]:
    """Identify fixtures without reading score/odds cells; sampling uses this."""
    result = []
    seen = set()
    for tournament, row in _result_rows(raw, day):
        hrefs = row.xpath('./td/a[contains(@href,"/match-detail/")]/@href')
        values = parse_qs(urlparse(hrefs[0]).query).get("id", [])
        if len(values) != 1 or not values[0].isdigit():
            raise ValueError("invalid_match_id")
        match_id = values[0]
        if match_id in seen:
            raise ValueError("duplicate_fixture_id")
        seen.add(match_id)
        following = row.getnext()
        first_names = row.xpath('./td[contains(concat(" ",normalize-space(@class)," ")," t-name ")]')
        second_names = [] if following is None else following.xpath('./td[contains(concat(" ",normalize-space(@class)," ")," t-name ")]')
        record = {"event_id": "te:" + match_id, "match_id": match_id, "date": day,
                  "tournament": tournament, "challenger": bool(tournament and "challenger" in tournament.lower()),
                  "source_url": f"{SOURCE}/match-detail/?id={match_id}"}
        try:
            if len(first_names) != 1 or len(second_names) != 1:
                raise ValueError("unpaired_result_rows")
            if following.xpath('.//a[contains(@href,"/match-detail/")]'):
                raise ValueError("opponent_row_is_another_match")
            record.update(player1=_player(first_names[0]), player2=_player(second_names[0]))
            if record["player1"] == record["player2"]:
                raise ValueError("duplicate_player_id")
        except ValueError as exc:
            record["identity_error"] = str(exc)
        result.append(record)
    return result


def select_sample(fixtures: list[dict], day: str) -> list[dict]:
    """Frozen Tuesday/Friday maximum-12 sample; scores never enter the key."""
    if date.fromisoformat(day).weekday() not in (1, 4):
        return []
    candidates = [f for f in fixtures if f["challenger"]]
    selected = sorted(candidates, key=lambda f: hashlib.sha256(f"N2-v1|{f['match_id']}".encode()).hexdigest())[:12]
    return [{k: f[k] for k in ("event_id", "match_id", "date", "source_url")} for f in selected]


def _complete(sets):
    if len(sets) not in (2, 3):
        return False
    wins = [0, 0]
    for index, (one, two) in enumerate(sets):
        high, low = max(one, two), min(one, two)
        if not ((high == 6 and low <= 4) or (high == 7 and low in (5, 6))):
            return False
        wins[int(two > one)] += 1
        if max(wins) == 2:
            return index == len(sets) - 1
    return False


def parse_daily_results(raw, day: str) -> dict:
    fixtures = parse_fixtures(raw, day)
    result, errors = [], []
    for fixture, (_, row) in zip(fixtures, _result_rows(raw, day)):
        if fixture.get("identity_error"):
            errors.append({"event_id": fixture["event_id"], "reason": fixture["identity_error"]})
            continue
        other = row.getnext()
        cells = [r.xpath('./td[contains(concat(" ",normalize-space(@class)," ")," score ")]') for r in (row, other)]
        sets = []
        score_error = False
        gap = False
        for index in range(max(map(len, cells))):
            pair = [_plain(c[index]) if index < len(c) else "" for c in cells]
            if pair == ["", ""]:
                gap = True
            elif gap or any(not re.fullmatch(r"\d{1,2}", v) for v in pair):
                score_error = True
            else:
                sets.append([int(v) for v in pair])
        # Status is scoped to these two rows, not present-day page sidebars.
        statuses = " ".join([_text(row), _text(other)] + row.xpath('.//@title') + other.xpath('.//@title'))
        abnormal = bool(re.search(r"\b(ret\.?|retired|retirement|walkover|w\.?o\.?|cancelled|canceled|disqualified|default|abandoned)\b", statuses, re.I))
        summaries = [_text(r.xpath('./td[@class="result"]')[0]) if r.xpath('./td[@class="result"]') else "" for r in (row, other)]
        actual_wins = [sum(a > b for a, b in sets), sum(b > a for a, b in sets)]
        consistent_summary = summaries == [str(v) for v in actual_wins]
        completed = _complete(sets) and not abnormal and not score_error and consistent_summary
        record = {**fixture, "sets": sets, "completed": completed,
                  "source_status_abnormal": abnormal, "score_parse_error": score_error,
                  "score_summary_consistent": consistent_summary, "source_parser_version": VERSION}
        result.append(record)
        if score_error:
            errors.append({"event_id": fixture["event_id"], "reason": "ambiguous_set_cells"})
    return {"date": day, "records": result, "errors": errors, "fixture_count": len(fixtures)}


def _localize(naive: datetime) -> datetime:
    variants = []
    for fold in (0, 1):
        aware = naive.replace(tzinfo=PRAGUE, fold=fold)
        utc = aware.astimezone(timezone.utc)
        if utc.astimezone(PRAGUE).replace(tzinfo=None) == naive:
            variants.append(utc)
    variants = set(variants)
    if len(variants) != 1:
        raise ValueError("ambiguous_or_nonexistent_local_time")
    return variants.pop()


def parse_quote_time(literal: str, start_naive: datetime) -> str:
    """Resolve missing quote year by nearest date; preserve after-start errors."""
    match = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.\s+(\d{1,2}):(\d{2})", literal.strip())
    if not match:
        raise ValueError("missing_literal_quote_time")
    day, month, hour, minute = map(int, match.groups())
    choices = []
    for year in range(start_naive.year - 1, start_naive.year + 2):
        try:
            candidate = datetime(year, month, day, hour, minute)
        except ValueError:
            continue
        if abs(candidate - start_naive) <= timedelta(days=31):
            choices.append(candidate)
    if len(choices) != 1:
        raise ValueError("quote_year_unresolved")
    return _localize(choices[0]).isoformat()


def _price(text):
    try:
        value = float(text.strip())
    except (ValueError, AttributeError):
        return None
    return value if math.isfinite(value) and value > 1 else None


def _odds_cell(cell, start_naive):
    divs = cell.xpath('./div[contains(concat(" ",normalize-space(@class)," ")," odds-in ")]')
    result = {"active": "deactivated" not in _classes(cell), "final_price": None,
              "opening_price": None, "opening_time_raw": None, "opening_at": None,
              "final_time_raw": None, "final_at": None, "unchanged_opening": False,
              "errors": []}
    if len(divs) != 1:
        result["errors"].append("missing_odds_cell")
        return result
    div = divs[0]
    result["final_price"] = _price(div.text)
    rows = div.xpath('./div[contains(concat(" ",normalize-space(@class)," ")," odds-change-div ")]/table/tr')
    if not rows:
        rows = div.xpath('./div[contains(concat(" ",normalize-space(@class)," ")," odds-change-div ")]/table/tbody/tr')
    opening = False
    changes, opens = [], []
    for row in rows:
        if "opening odds" in _text(row).lower():
            opening = True
            continue
        values = row.xpath('./td')
        if len(values) >= 2:
            item = {"raw": _text(values[0]), "price": _price(_text(values[1]))}
            (opens if opening else changes).append(item)
    if len(opens) != 1:
        result["errors"].append("missing_or_ambiguous_opening_history")
    else:
        result["opening_price"], result["opening_time_raw"] = opens[0]["price"], opens[0]["raw"]
        try:
            result["opening_at"] = parse_quote_time(opens[0]["raw"], start_naive)
        except ValueError as exc:
            result["errors"].append(str(exc))
    if len(changes) == 1:
        if changes[0]["price"] != result["final_price"]:
            result["errors"].append("final_display_history_disagreement")
        else:
            result["final_time_raw"] = changes[0]["raw"]
            try:
                result["final_at"] = parse_quote_time(changes[0]["raw"], start_naive)
            except ValueError as exc:
                result["errors"].append(str(exc))
    elif not changes and len(opens) == 1 and result["final_price"] == result["opening_price"]:
        result["unchanged_opening"] = True
        result["final_time_raw"], result["final_at"] = result["opening_time_raw"], result["opening_at"]
    else:
        result["errors"].append("missing_or_ambiguous_final_history")
    return result


def _pinnacle_pair(doc, section, start_naive, total=None):
    rows = doc.xpath(f'//div[@id="{section}"]//table[contains(concat(" ",normalize-space(@class)," ")," result ")]/tbody/tr|//div[@id="{section}"]//table[contains(concat(" ",normalize-space(@class)," ")," result ")]/tr')
    found = []
    matching_rows = 0
    for row in rows:
        book = row.xpath('./td//span[@class="t"]')
        if not book or _text(book[0]).casefold() != "pinnacle":
            continue
        values = row.xpath('./td[@class="value"]')
        if total is not None and not any(_text(value) == str(total) for value in values):
            continue
        if total is None and values:
            continue
        matching_rows += 1
        if total is not None and len(values) != 1:
            continue
        cells = [row.xpath(f'./td[contains(concat(" ",normalize-space(@class)," ")," k{i} ")]') for i in (1, 2)]
        if all(len(c) == 1 for c in cells):
            found.append([_odds_cell(c[0], start_naive) for c in cells])
    if matching_rows != 1 or len(found) != 1:
        reason = "missing_market" if matching_rows == 0 else "duplicate_market" if matching_rows > 1 else "malformed_market"
        return {"present": False, "reason": reason}
    return {"present": True, "side1": found[0][0], "side2": found[0][1]}


def _entry_errors(pair, start_at, max_overround=.10):
    if not pair.get("present"):
        return [pair.get("reason", "missing_market")]
    sides = [pair["side1"], pair["side2"]]
    errors = []
    if any(s["opening_price"] is None for s in sides):
        errors.append("invalid_opening_price")
    times = [s["opening_at"] for s in sides]
    if any(t is None for t in times):
        errors.append("missing_opening_time")
    elif times[0] != times[1]:
        errors.append("unsynchronized_opening")
    elif any(datetime.fromisoformat(t) >= datetime.fromisoformat(start_at) for t in times):
        errors.append("opening_not_prestart")
    if max_overround is not None and all(s["opening_price"] is not None for s in sides):
        overround = sum(1 / s["opening_price"] for s in sides) - 1
        if not -1e-12 <= overround <= max_overround + 1e-12:
            errors.append("opening_overround_outside_protocol")
    return errors


def _closing_errors(pair, start_at):
    if not pair.get("present"):
        return ["missing_market"]
    sides = [pair["side1"], pair["side2"]]
    errors = []
    if not all(s["active"] for s in sides):
        errors.append("deactivated_final")
    if any(s["final_price"] is None for s in sides):
        errors.append("invalid_final_price")
    if any(s["final_at"] is None for s in sides):
        errors.append("missing_verified_final_time")
    elif any(datetime.fromisoformat(s["final_at"]) >= datetime.fromisoformat(start_at) for s in sides):
        errors.append("final_not_prestart")
    if any(s["final_at"] and s["opening_at"] and datetime.fromisoformat(s["final_at"]) < datetime.fromisoformat(s["opening_at"]) for s in sides):
        errors.append("final_before_opening")
    if all(s["final_price"] is not None for s in sides):
        if not -1e-12 <= sum(1 / s["final_price"] for s in sides) - 1 <= .15 + 1e-12:
            errors.append("final_overround_outside_protocol")
    return errors


def parse_match_detail(raw, match_id: str) -> dict:
    if not str(match_id).isdigit():
        raise ValueError("invalid_match_id")
    doc = _document(raw)
    canonical = doc.xpath('//meta[@property="og:url"]/@content')
    if len(canonical) != 1:
        raise ValueError("detail_event_id_unverified")
    if parse_qs(urlparse(canonical[0]).query).get("id") != [str(match_id)]:
        raise ValueError("detail_event_id_mismatch")
    headers = doc.xpath('//div[@id="center"]/div[contains(concat(" ",normalize-space(@class)," ")," boxBasic ")][span[@class="upper"]]')
    if len(headers) != 1:
        raise ValueError("missing_match_header")
    header_text = _text(headers[0])
    stamp = re.match(r"(\d{2}\.\d{2}\.\d{4}),\s*(\d{2}:\d{2})(?:,|\s)", header_text)
    if not stamp:
        raise ValueError("missing_literal_start_time")
    naive = datetime.strptime(" ".join(stamp.groups()), "%d.%m.%Y %H:%M")
    start_at = _localize(naive).isoformat()
    players = doc.xpath('//table[contains(concat(" ",normalize-space(@class)," ")," gDetail ")]/thead/tr/th[contains(concat(" ",normalize-space(@class)," ")," plName ")]')
    if len(players) != 2:
        raise ValueError("missing_detail_player_identity")
    p1, p2 = map(_player, players)
    totals = _pinnacle_pair(doc, "oddsMenu-2-data", naive, 21.5)
    moneyline = _pinnacle_pair(doc, "oddsMenu-1-data", naive)
    n3 = _entry_errors(totals, start_at)
    n2 = list(n3) + ["moneyline_" + e for e in _entry_errors(moneyline, start_at, max_overround=None)]
    if not n2 and totals["side1"]["opening_at"] != moneyline["side1"]["opening_at"]:
        n2.append("moneyline_totals_opening_unsynchronized")
    closing = _closing_errors(totals, start_at)
    return {"event_id": "te:" + str(match_id), "match_id": str(match_id),
            "date": naive.date().isoformat(), "player1": p1, "player2": p2,
            "source_start_local": " ".join(stamp.groups()), "start_at": start_at,
            "source_timezone": "Europe/Prague", "source_parser_version": VERSION,
            "totals_21_5": totals, "moneyline": moneyline,
            "entry_valid_n2": not n2, "entry_errors_n2": n2,
            "entry_valid_n3": not n3, "entry_errors_n3": n3,
            "closing_valid": not closing, "closing_errors": closing,
            "timestamp_status": "retrospective source-local opening/last-change times; execution unverified"}


def _write_once(path: Path, value):
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if json.loads(path.read_text()) != value:
            raise ValueError(f"immutable_file_conflict:{path}")
        return
    # Publish complete bytes atomically without replacing any existing pin.
    temporary = path.with_suffix(path.suffix + ".writing")
    temporary.write_text(text)
    try:
        os.link(temporary, path)
    except FileExistsError:
        if json.loads(path.read_text()) != value:
            raise ValueError(f"immutable_file_conflict:{path}")
    finally:
        temporary.unlink(missing_ok=True)


def _write_status(path: Path, value):
    """Replaceable progress index; historical attempts stay in acquisition.jsonl."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


class Collector:
    """Resumable ordinary HTTPS, global start-rate limit, all attempts recorded."""

    def __init__(self, root, interval=1.0, timeout=45, max_attempts=3):
        if interval < .5 or max_attempts < 1:
            raise ValueError("interval must be >= 0.5 seconds and attempts >= 1")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.interval, self.timeout, self.max_attempts = interval, timeout, max_attempts
        self._lock = threading.Lock()
        self._next_request = 0.0

    def _log(self, record):
        with self._lock:
            with (self.root / "acquisition.jsonl").open("a") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _pace(self):
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next_request - now)
            self._next_request = max(now, self._next_request) + self.interval
        if delay:
            time.sleep(delay)

    def fetch(self, relative: str, url: str) -> bytes | None:
        path = self.root / relative
        meta = path.with_suffix(path.suffix + ".meta.json")
        if path.exists() and meta.exists():
            raw = path.read_bytes()
            old = json.loads(meta.read_text())
            if hashlib.sha256(raw).hexdigest() != old["sha256"] or old["url"] != url:
                raise ValueError(f"cached_source_conflict:{relative}")
            self._log({"at": datetime.now(timezone.utc).isoformat(), "status": "cache_hit", "file": relative, "sha256": old["sha256"], "url": url})
            return raw
        # A source file without metadata is incomplete, not an available cache.
        path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(1, self.max_attempts + 1):
            self._pace()
            record = {"requested_at": datetime.now(timezone.utc).isoformat(), "url": url, "file": relative, "attempt": attempt}
            try:
                request = Request(url, headers={"User-Agent": "BeatingAnything research collector/1.0", "Accept": "text/html"})
                with urlopen(request, timeout=self.timeout) as response:
                    raw = response.read(5_000_001)
                    record.update(http_status=response.status, content_type=response.headers.get("Content-Type"))
                if len(raw) > 5_000_000:
                    raise ValueError("source_exceeds_5MB_cap")
                record.update(received_at=datetime.now(timezone.utc).isoformat(), status="downloaded", bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                temporary = path.with_suffix(path.suffix + ".tmp")
                temporary.write_bytes(raw)
                temporary.replace(path)
                _write_once(meta, record)
                self._log(record)
                return raw
            except Exception as exc:
                record.update(received_at=datetime.now(timezone.utc).isoformat(), status="failed", error=f"{type(exc).__name__}: {exc}")
                self._log(record)
                if isinstance(exc, HTTPError) and exc.code in (401, 403, 429):
                    # Do not retry around access denials or rate limits.
                    raise RuntimeError(f"source_access_or_rate_limit:{exc.code}") from exc
                if attempt < self.max_attempts:
                    time.sleep(min(30, 2 ** attempt))
        return None

    def collect_day(self, day: str):
        d = date.fromisoformat(day)
        url = f"{SOURCE}/results/?type=atp-single&year={d.year}&month={d.month:02d}&day={d.day:02d}"
        raw = self.fetch(f"daily/{day}.html", url)
        if raw is None:
            answer = {"date": day, "status": "download_failed", "sample_status": "unknown"}
            _write_status(self.root / "daily-status" / f"{day}.json", answer)
            self._log(answer)
            return answer
        try:
            fixtures = parse_fixtures(raw, day)
            pin = {"protocol": "N2-v1", "date": day, "source_sha256": hashlib.sha256(raw).hexdigest(),
                   "sample_rule": "Tue/Fri; ascending SHA256 N2-v1|match_id; max12 Challenger", "matches": select_sample(fixtures, day)}
            # Commit IDs before normalizing any result or downloading any detail.
            _write_once(self.root / "sample" / f"{day}.json", pin)
            parsed = parse_daily_results(raw, day)
            _write_once(self.root / "parsed-daily" / f"{day}.json", parsed)
            answer = {"date": day, "status": "parsed", "fixtures": len(fixtures), "history_records": len(parsed["records"]), "parse_errors": len(parsed["errors"]), "sampled": len(pin["matches"])}
        except Exception as exc:
            answer = {"date": day, "status": "parse_failed", "error": f"{type(exc).__name__}: {exc}"}
        self._log(answer)
        _write_status(self.root / "daily-status" / f"{day}.json", answer)
        return answer

    def collect_detail(self, fixture):
        match_id = fixture["match_id"]
        raw = self.fetch(f"details/{match_id}.html", fixture["source_url"])
        if raw is None:
            answer = {"event_id": fixture["event_id"], "status": "download_failed"}
            _write_status(self.root / "detail-status" / f"{match_id}.json", answer)
            self._log(answer)
            return answer
        try:
            parsed = parse_match_detail(raw, match_id)
            parsed["sample_date"] = fixture["date"]
            parsed["source_sha256"] = hashlib.sha256(raw).hexdigest()
            _write_once(self.root / "parsed-details" / f"{match_id}.json", parsed)
            answer = {"event_id": fixture["event_id"], "status": "parsed", "entry_valid_n2": parsed["entry_valid_n2"], "entry_valid_n3": parsed["entry_valid_n3"], "closing_valid": parsed["closing_valid"]}
        except Exception as exc:
            answer = {"event_id": fixture["event_id"], "status": "parse_failed", "error": f"{type(exc).__name__}: {exc}"}
        self._log(answer)
        _write_status(self.root / "detail-status" / f"{match_id}.json", answer)
        return answer


def _run_jobs(function, jobs, workers):
    done, failed = 0, 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(function, item) for item in jobs]
        try:
            for future in as_completed(futures):
                result = future.result()
                done += 1
                failed += result["status"] != "parsed"
                if done % 25 == 0 or result["status"] != "parsed":
                    print(json.dumps({"completed": done, "failed": failed, "last": result}), flush=True)
        except BaseException:
            for future in futures:
                future.cancel()
            raise
    return {"completed": done, "failed": failed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["daily", "details"])
    parser.add_argument("--source-dir", default="data/raw/tennisexplorer")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--workers", type=int, default=2, choices=[1, 2])
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    first, last = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if first > last:
        parser.error("start must precede end")
    collector = Collector(args.source_dir, interval=args.interval)
    dates = [(first + timedelta(days=n)).isoformat() for n in range((last - first).days + 1)]
    if args.action == "daily":
        summary = _run_jobs(collector.collect_day, dates, args.workers)
    else:
        fixtures = {}
        missing = []
        unknown = []
        for day in dates:
            path = collector.root / "sample" / f"{day}.json"
            if not path.exists():
                status = collector.root / "daily-status" / f"{day}.json"
                if status.exists() and json.loads(status.read_text()).get("status") in ("download_failed", "parse_failed"):
                    unknown.append(day)
                else:
                    missing.append(day)
                continue
            for record in json.loads(path.read_text())["matches"]:
                fixtures.setdefault(record["match_id"], record)
        if missing:
            raise ValueError(f"daily_sample_pins_missing:{len(missing)}; finish daily collection before details")
        summary = _run_jobs(collector.collect_detail, list(fixtures.values()), args.workers)
        summary["unknown_sample_dates"] = unknown
    summary.update(source_parser_version=VERSION, start=args.start, end=args.end,
                   finished_at=datetime.now(timezone.utc).isoformat())
    _write_status(collector.root / f"{args.action}-summary.json", summary)
    print(json.dumps({"action": args.action, **summary}), flush=True)


if __name__ == "__main__":
    main()
