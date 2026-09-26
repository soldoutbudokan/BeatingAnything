#!/usr/bin/env python3
"""Execute the frozen three-event NBA injury-report clock inventory.

Only selected quote metadata, team-name/abbreviation columns, and official injury
reports are read. No box scores, performance values, classifications or models.
Run with the existing research venv. --fetch permits the declared bounded requests;
without it, only already retained receipts are reused.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from email.parser import Parser
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/nba-injury-price-clocks-2026-09-26"
SELECTION = RAW / "selected-price-samples.json"
SELECTION_SHA = "c29f3ad0a12eb8a29c8d3823963a42c325bba44646c71e1a5e68abaec51e5a36"
DECLARATION = ROOT / "docs/nba-injury-price-clock-inventory-declaration-2026-09-26.md"
DECLARATION_SHA = "17bf18526af7bb7243772c47c2dbab8c5ce411e18a3b0d16bcf372d88ae61b93"
TEAMS = ROOT / "data/raw/nba-source-feasibility/nba_stats_schedule_2024.csv"
TEAMS_SHA = "ab5b7b5b978f0527a9e1ff4332b3e14d00c526964d2ea79b4d9f992f38eacb26"
REPORT = ROOT / "reports/nba-injury-price-clocks-2026-09-26.json"
NY = ZoneInfo("America/New_York")
UTC = timezone.utc
HEADER_RE = re.compile(r"Injury\s*Report\s*:\s*(\d{2}/\d{2}/\d{2})\s*(\d{2}:\d{2})\s*([AP]M)")
MATCH_RE = re.compile(r"\b([A-Z]{2,3})\s*@\s*([A-Z]{2,3})\b")
TIME_RE = re.compile(r"\b(\d{2}:\d{2})\s*([AP]M)?\s*\(ET\)")
STATUS_RE = re.compile(r"\b(Out|Doubtful|Questionable|Probable|Available)\b")


def iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_iso(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Timezone absent")
    return result


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative(path):
    return str(Path(path).relative_to(ROOT))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def norm(value):
    return re.sub(r"[^a-z0-9]", "", value.lower())


def candidate_urls(entry):
    latest = (entry.astimezone(NY) - timedelta(minutes=90)).replace(second=0, microsecond=0)
    latest = latest.replace(minute=(latest.minute // 30) * 30)
    result = []
    for i in range(6):
        slot = latest - timedelta(minutes=30 * i)
        day, hour, period = slot.strftime("%Y-%m-%d"), slot.strftime("%I"), slot.strftime("%p")
        names = [f"Injury-Report_{day}_{hour}_{slot.minute:02d}{period}.pdf"]
        if slot.minute == 30:
            names.append(f"Injury-Report_{day}_{hour}{period}.pdf")
        for name in names:
            result.append({"slot_et": slot.isoformat(), "filename_form": "minute" if "_" in name.split(day + "_")[1] else "hourly",
                           "url": "https://ak-static.cms.nba.com/referee/injury/" + name})
    assert len(result) == 9 and len({r["url"] for r in result}) == 9
    return result


def load_teams():
    import pandas as pd
    if sha(TEAMS) != TEAMS_SHA:
        raise ValueError("Team abbreviation source hash changed")
    # Deliberately never load schedule sporting values or actual participant fields.
    table = pd.read_csv(TEAMS, usecols=["team_name", "team_abbreviation"], dtype=str).drop_duplicates()
    groups = {}
    for row in table.to_dict("records"):
        groups.setdefault(row["team_name"], set()).add(row["team_abbreviation"])
    if any(len(v) != 1 for v in groups.values()):
        raise ValueError("Ambiguous retained team name")
    return {k: next(iter(v)) for k, v in groups.items()}


def fetch(url, permit_fetch):
    stem = url.rsplit("/", 1)[1][:-4]
    directory = RAW / "official-report-receipts"
    directory.mkdir(parents=True, exist_ok=True)
    receipt_path = directory / (stem + ".receipt.json")
    if receipt_path.exists():
        old = json.loads(receipt_path.read_text())
        if old["url"] != url:
            raise ValueError("Receipt URL collision")
        for key, expected_key in [("body_path", "body_sha256"), ("headers_path", "headers_sha256")]:
            if sha(ROOT / old[key]) != old[expected_key]:
                raise ValueError("Cached response changed")
        return old, False
    if not permit_fetch:
        raise RuntimeError("Missing receipt in offline mode: " + url)
    body = directory / (stem + ".body")
    headers = directory / (stem + ".headers")
    started = iso(datetime.now(UTC))
    # No retry, redirect following, challenge handling, alternate hosts or credentials.
    proc = subprocess.run(["curl", "-sS", "--max-time", "30", "--max-redirs", "0",
                           "-D", str(headers), "-o", str(body), "-w", "%{http_code}\n%{content_type}\n",
                           url], capture_output=True, text=True)
    finished = iso(datetime.now(UTC))
    fields = proc.stdout.splitlines()
    status = int(fields[0]) if fields and fields[0].isdigit() else None
    if not body.exists():
        body.write_bytes(b"")
    if not headers.exists():
        headers.write_bytes(b"")
    blocks = [b for b in headers.read_text(errors="replace").replace("\r\n", "\n").split("\n\n") if b.startswith("HTTP/")]
    message = Parser().parsestr("\n".join(blocks[-1].splitlines()[1:])) if blocks else Parser().parsestr("")
    if status == 200 and body.read_bytes().startswith(b"%PDF"):
        pdf = body.with_suffix(".pdf")
        body.rename(pdf)
        body = pdf
    result = {"url": url, "http_status": status, "curl_exit_code": proc.returncode,
              "request_started_at_utc": started, "received_at_utc": finished,
              "content_type": fields[1] if len(fields) > 1 else None, "curl_error": proc.stderr.strip(),
              "body_path": relative(body), "body_bytes": body.stat().st_size, "body_sha256": sha(body),
              "headers_path": relative(headers), "headers_sha256": sha(headers),
              "last_modified_raw": message.get_all("Last-Modified", []),
              "http_date_raw": message.get_all("Date", []), "etag": message.get_all("ETag", []),
              "receipt_path": relative(receipt_path)}
    write_json(receipt_path, result)
    return result, True


def clock_check(receipt, entry):
    from pypdf import PdfReader
    reasons, clocks = [], {}
    result = {"clock_qualified": False, "rejection_reasons": reasons}
    try:
        reader = PdfReader(ROOT / receipt["body_path"])
        metadata = reader.metadata
        result["pdf_metadata"] = dict(metadata or {})
        headers = []
        for page in reader.pages:
            found = HEADER_RE.findall(page.extract_text())
            if len(found) != 1:
                reasons.append("missing_or_ambiguous_page_header")
            headers.extend(found)
        result["printed_headers"] = [f"{d} {t} {a}" for d, t, a in headers]
        result["page_count"] = len(reader.pages)
        if not headers or len(set(headers)) != 1:
            reasons.append("inconsistent_report_headers")
            return result
        header = datetime.strptime(" ".join(headers[0]), "%m/%d/%y %I:%M %p")
        creation = metadata.creation_date if metadata else None
        if creation is None or creation.tzinfo is None or creation.utcoffset() is None:
            reasons.append("missing_timezone_bearing_creation")
            return result
        clocks["pdf_creation"] = creation
        local_creation_minute = creation.replace(tzinfo=None, second=0, microsecond=0)
        ny_creation_minute = creation.astimezone(NY).replace(tzinfo=None, second=0, microsecond=0)
        if local_creation_minute != header or ny_creation_minute != header:
            reasons.append("header_creation_eastern_minute_disagreement")
        corroborated_header = header.replace(tzinfo=creation.tzinfo)
        clocks["printed_header_latest_possible_second"] = corroborated_header + timedelta(minutes=1) - timedelta(microseconds=1)
        result["header_timezone_basis"] = "Inference from timezone-bearing CreationDate matching printed header and America/New_York to the minute; header itself lacks timezone."
        result["printed_header_utc"] = iso(corroborated_header)
        if metadata and metadata.get("/ModDate") is not None:
            mod = metadata.modification_date
            if mod is None or mod.tzinfo is None or mod.utcoffset() is None:
                reasons.append("ambiguous_pdf_modification_date")
            else:
                clocks["pdf_modification"] = mod
        xmp_raw = ""
        if reader.trailer["/Root"].get("/Metadata") is not None:
            xmp_raw = reader.trailer["/Root"]["/Metadata"].get_data().decode("utf-8", errors="strict")
        xmp_dates = []
        for name in ["CreateDate", "ModifyDate", "MetadataDate"]:
            values = re.findall(r"<(?:[\w.-]+:)?" + name + r"\b[^>]*>([^<]*)</", xmp_raw)
            values += re.findall(r"\b(?:[\w.-]+:)?" + name + r"\s*=\s*[\"']([^\"']*)[\"']", xmp_raw)
            for i, value in enumerate(values):
                xmp_dates.append({"field": name, "raw": value})
                try:
                    clocks[f"xmp_{name}_{i}"] = parse_iso(value.strip())
                except (ValueError, TypeError):
                    reasons.append("ambiguous_xmp_" + name)
        result["xmp_date_fields"] = xmp_dates
        result["http_last_modified_raw"] = receipt["last_modified_raw"]
        for i, value in enumerate(receipt["last_modified_raw"]):
            try:
                date = parsedate_to_datetime(value)
                if date.tzinfo is None or date.utcoffset() is None:
                    raise ValueError("Timezone absent")
                clocks[f"http_last_modified_{i}"] = date
            except (ValueError, TypeError):
                reasons.append("ambiguous_http_last_modified")
        maximum = max(clocks.values())
        age = (entry - maximum).total_seconds()
        result.update({"interpreted_clocks_utc": {k: iso(v) for k, v in clocks.items()},
                       "available_after_bound_utc": iso(maximum), "seconds_before_entry": age,
                       "current_retrieval_is_not_original_receipt": True})
        if not 3600 <= age <= 21600:
            reasons.append("source_clock_outside_60_minute_to_6_hour_window")
        result["clock_qualified"] = not reasons
        return result
    except Exception as exc:
        reasons.append("pdf_metadata_error:" + type(exc).__name__ + ":" + str(exc))
        return result


def printed_start_candidates(day, printed):
    if not day or not printed:
        return []
    match = re.fullmatch(r"(\d{2}):(\d{2})(?:\s*([AP]M))?", printed)
    if not match:
        return []
    hour, minute, ampm = int(match[1]), int(match[2]), match[3]
    if minute > 59 or hour > 23:
        return []
    if ampm:
        hours = [hour % 12 + (12 if ampm == "PM" else 0)]
    elif 1 <= hour <= 12:
        hours = sorted({hour % 12, hour % 12 + 12})
    else:
        hours = [hour]
    date = datetime.strptime(day, "%m/%d/%Y")
    return [iso(date.replace(hour=h, minute=minute, tzinfo=NY)) for h in hours]


def fixture_extract(pdf_path, sample, teams, month):
    import pypdfium2 as pdfium
    document = pdfium.PdfDocument(pdf_path)
    target_day = parse_iso(sample["provider_start_utc"]).astimezone(NY).strftime("%m/%d/%Y")
    away, home = teams[sample["away_team"]], teams[sample["home_team"]]
    target_matchup = away + "@" + home
    day = time = matchup = current_team = None
    rows, pages = [], set()
    states = {sample[k]: {"seen": False, "not_yet_submitted": False, "status_rows": []} for k in ["away_team", "home_team"]}
    printed_times = set()
    all_team_names = sorted(teams, key=len, reverse=True)
    for page_index in range(len(document)):
        page = document[page_index]
        textpage = page.get_textpage()
        text = textpage.get_text_range()
        for rawline in text.splitlines():
            line = " ".join(rawline.split())
            if not line or line.startswith("Injury Report:") or re.fullmatch(r"Page \d+ of \d+", line) or line.startswith("Game Date Game Time"):
                continue
            found_day = re.search(r"\b\d{2}/\d{2}/\d{4}\b", line)
            if found_day:
                day = found_day.group(0)
            found_time = TIME_RE.search(line)
            if found_time:
                time = found_time[1] + (" " + found_time[2] if found_time[2] else "")
            found_match = MATCH_RE.search(line)
            if found_match:
                matchup = found_match[1] + "@" + found_match[2]
                current_team = None
            names = [name for name in all_team_names if norm(name) in norm(line)]
            if len(names) == 1:
                current_team = names[0]
            if matchup != target_matchup or day != target_day:
                continue
            pages.add(page_index)
            if time:
                printed_times.add(time)
            rows.append({"page": page_index + 1, "raw_line": line, "team_context": current_team})
            if current_team not in states:
                continue
            state = states[current_team]
            state["seen"] = True
            if "NOTYETSUBMITTED" in re.sub(r"[^A-Z]", "", line.upper()):
                state["not_yet_submitted"] = True
            status = STATUS_RE.search(line)
            if status:
                prefix = line[:status.start()]
                prefix = re.sub(r"\b\d{2}/\d{2}/\d{4}\b", "", prefix)
                prefix = TIME_RE.sub("", prefix)
                prefix = MATCH_RE.sub("", prefix)
                # PDFium retains the rendered team wording; preserve the literal player suffix.
                for name in names:
                    prefix = re.sub(r"\s*".join(map(re.escape, name.split())), "", prefix, flags=re.I)
                player = prefix.strip()
                state["status_rows"].append({"player_literal": player, "status": status[1],
                                             "reason_first_line": line[status.end():].strip(), "page": page_index + 1})
        textpage.close()
        page.close()
    if not rows:
        state = "no_matching_fixture_date"
    elif all(s["status_rows"] and not s["not_yet_submitted"] for s in states.values()):
        state = "both_teams_have_submitted_status_rows"
    elif any(s["not_yet_submitted"] for s in states.values()):
        state = "explicit_not_yet_submitted_or_mixed"
    else:
        state = "matching_fixture_status_coverage_unresolved"
    starts = sorted({t for printed in printed_times for t in printed_start_candidates(target_day, printed)})
    entry, provider = parse_iso(sample["source_snapshot_utc"]), parse_iso(sample["provider_start_utc"])
    bound = min([provider] + [parse_iso(v) for v in starts]) if starts else None
    image_paths = []
    # For an absent fixture, render every page so absence can also be visually checked.
    for page_index in sorted(pages or set(range(len(document)))):
        out = RAW / "rendered" / f"{month}-page-{page_index + 1}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        document[page_index].render(scale=1.75).to_pil().save(out)
        image_paths.append({"page": page_index + 1, "path": relative(out), "sha256": sha(out)})
    document.close()
    return {"target_matchup": target_matchup, "target_game_date_et": target_day,
            "state": state, "matching_fixture_date_found": bool(rows), "teams": states,
            "matching_fixture_raw_lines": rows, "printed_game_time_et_values": sorted(printed_times),
            "printed_start_utc_candidates": starts, "printed_start_ampm_ambiguous": len(starts) > 1,
            "provider_start_utc_unchanged": sample["provider_start_utc"],
            "snapshot_before_provider_and_earliest_printed_candidate": entry < bound if bound else None,
            "conservative_start_bound_utc": iso(bound) if bound else None,
            "independent_start_status": "unresolved_printed_AM_PM" if len(starts) > 1 else ("printed_candidate_only_not_independent_NBA_ID_crosswalk" if starts else "missing"),
            "nba_game_id_crosswalk_independently_verified": False, "rendered_pages": image_paths,
            "visual_review_status": "pending_human_or_agent_review",
            "unlisted_players_treated_as_healthy": False}


def markdown(report):
    lines = ["# NBA injury-report / price-clock inventory", "",
             "The fixed three-event sample was checked in declared URL order. Report selection stopped at the first clock-qualified PDF, before using its statuses or fixture content. This is source feasibility, not a star-absence test or forecast.", "",
             "| Month | Publisher fixture (away at home) | Preliminary pairs | Requests | Report clock gate | Fixture/status result |",
             "|---|---|---:|---:|---|---|"]
    for r in report["events"]:
        sample = r["selected_price_metadata"]
        fixture = sample["away_team"] + " at " + sample["home_team"]
        state = r.get("fixture_evidence", {}).get("state", "not inspected; no clock-qualified PDF")
        lines.append(f"| {r['month']} | {fixture} | {len(sample['preliminary_pairs'])} | {r['distinct_attempted_urls']} | {r['stop_reason']} | {state} |")
    for r in report["events"]:
        lines += ["", f"## {r['month']}", "", f"Entry: `{r['selected_price_metadata']['source_snapshot_utc']}`. Provider start retained as `{r['selected_price_metadata']['provider_start_utc']}`."]
        for a in r["attempts"]:
            lines.append(f"- [{a['url'].rsplit('/',1)[-1]}]({a['url']}): HTTP {a['receipt']['http_status']}; {'cached' if a['reused_receipt'] else 'new receipt'}; " + ("clock qualified" if a.get("clock_check", {}).get("clock_qualified") else ", ".join(a.get("clock_check", {}).get("rejection_reasons", [])) or "event stopped or filename missing") + ".")
        if r.get("qualified_clock"):
            c, f = r["qualified_clock"], r["fixture_evidence"]
            lines += ["", f"Available-after bound: `{c['available_after_bound_utc']}`; {c['seconds_before_entry']/60:.6f} minutes before entry.",
                      "", "Printed Game Time (ET): " + ", ".join(f["printed_game_time_et_values"]) + ". UTC candidates: " + ", ".join(f["printed_start_utc_candidates"]) + ".",
                      "", f"Independent printed-start status: `{f['independent_start_status']}`. Snapshot before provider and the earliest printed candidate: `{f['snapshot_before_provider_and_earliest_printed_candidate']}`. No provider-assisted PM choice is called independent.", ""]
            for name, state in f["teams"].items():
                labels = "; ".join(v["player_literal"] + " — " + v["status"] for v in state["status_rows"])
                lines.append(f"- {name}: " + ("NOT YET SUBMITTED" if state["not_yet_submitted"] else labels or "no parseable status row; unknown") + ".")
            lines += ["", "Rendered pages: " + ", ".join(f"[page {p['page']}](../{p['path']})" for p in f["rendered_pages"]) + "."]
    lines += ["", "## Limits", ""] + ["- " + s for s in report["limitations"]]
    lines += ["", f"The [JSON audit]({REPORT.name}) retains every preliminary pair, original quote clocks, candidate URL order, receipts, clock components, literal fixture rows and source hashes. No box score or performance file was read.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="Permit only the fixed bounded requests; retained receipts are always reused")
    args = parser.parse_args()
    for path, expected in [(DECLARATION, DECLARATION_SHA), (SELECTION, SELECTION_SHA)]:
        if sha(path) != expected:
            raise ValueError("Frozen input changed: " + str(path))
    selected = json.loads(SELECTION.read_text())
    if list(selected["selected"]) != ["2025-10", "2026-01", "2026-04"]:
        raise ValueError("Frozen sample months changed")
    teams = load_teams()
    events, new_requests, all_urls = [], 0, set()
    for month, sample in selected["selected"].items():
        if sha(ROOT / sample["source_path"]) != sample["source_sha256"]:
            raise ValueError("Selected raw quote bytes changed")
        entry = parse_iso(sample["source_snapshot_utc"])
        event = {"month": month, "selected_price_metadata": sample, "candidate_urls": candidate_urls(entry), "attempts": [], "stop_reason": "bounded_slots_exhausted"}
        for candidate in event["candidate_urls"]:
            receipt, new = fetch(candidate["url"], args.fetch)
            new_requests += int(new)
            all_urls.add(candidate["url"])
            attempt = dict(candidate, receipt=receipt, reused_receipt=not new)
            event["attempts"].append(attempt)
            status = receipt["http_status"]
            if receipt["curl_exit_code"] != 0:
                event["stop_reason"] = "transport_failure_stop"
                break
            if status == 404:
                continue
            if status != 200:
                event["stop_reason"] = "access_denial_or_server_response_stop"
                break
            if not receipt["body_path"].endswith(".pdf"):
                event["stop_reason"] = "non_pdf_response_stop"
                break
            check = clock_check(receipt, entry)
            attempt["clock_check"] = check
            if check["clock_qualified"]:
                event["stop_reason"] = "first_clock_qualified_pdf"
                event["qualified_receipt"] = receipt
                event["qualified_clock"] = check
                # No fixture/status extraction occurs before this stopping decision.
                event["fixture_evidence"] = fixture_extract(ROOT / receipt["body_path"], sample, teams, month)
                break
        event["distinct_attempted_urls"] = len({a["url"] for a in event["attempts"]})
        assert event["distinct_attempted_urls"] <= 9
        events.append(event)
        print(json.dumps({"month": month, "attempts": event["distinct_attempted_urls"], "stop": event["stop_reason"], "fixture_state": event.get("fixture_evidence", {}).get("state")} ), flush=True)
    assert len(all_urls) <= 27
    report = {"prepared_at_utc": iso(datetime.now(UTC)), "declaration": {"path": relative(DECLARATION), "sha256": DECLARATION_SHA},
              "selection": {"path": relative(SELECTION), "sha256": SELECTION_SHA},
              "team_abbreviation_source": {"path": relative(TEAMS), "sha256": TEAMS_SHA, "read_columns": ["team_name", "team_abbreviation"]},
              "tool": {"path": relative(Path(__file__)), "sha256": sha(__file__)},
              "distinct_attempted_urls": len(all_urls), "network_requests_this_run": new_requests, "events": events,
              "summary": {"sampled_events": len(events), "preliminary_pairs": sum(len(e['selected_price_metadata']['preliminary_pairs']) for e in events),
                          "clock_qualified_reports": sum('qualified_clock' in e for e in events),
                          "exact_fixture_date_found": sum(e.get('fixture_evidence',{}).get('matching_fixture_date_found',False) for e in events)},
              "target_performance_read": False, "forecasts_or_returns_computed": False,
              "limitations": ["Three predetermined monthly samples do not establish whole-season availability or a qualified star-absence cohort.",
                  "Report header timezone is corroborated from offset-bearing CreationDate; Game Time (ET) alone is not publication-time evidence. The header minute’s upper endpoint is included conservatively in the clock maximum.",
                  "CreationDate is generation, not last revision. All interpretable modification/XMP/HTTP Last-Modified clocks are retained and maximized; a later clock cannot be discarded. Current source assertions are not original contemporaneous receipts or proof of immutable wording.",
                  "A 403, other denial, server/transport failure or non-PDF response stops that event; failed events are not rescued by alternate hosts or expanded searches.",
                  "Publisher NBA IDs and provider starts remain preliminary. Printed ordered matchup/date is reported separately and does not independently certify the NBA ID crosswalk. A printed time without AM/PM remains ambiguous; both UTC candidates are retained.",
                  "Status extraction uses PDFium visual-order text and retains raw lines plus rendered pages. An unlisted player is unknown, not healthy. Player name/ID and contemporaneous target-team membership joins have not been established.",
                  "No player scoring/minute values, star classifications, sporting outcomes, forecasts, selections, returns or threshold changes are included."]}
    write_json(REPORT, report)
    REPORT.with_suffix(".md").write_text(markdown(report))
    print(json.dumps(report["summary"]), flush=True)


if __name__ == "__main__":
    main()
