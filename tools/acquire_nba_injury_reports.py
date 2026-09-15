#!/usr/bin/env python3
"""Acquire the fixed 2024-25 preceding-day NBA injury reports, without outcomes.

Dependencies: Python 3.10+, pypdf, and Poppler's pdftotext on PATH.
Run from any directory: python /path/to/repo/tools/acquire_nba_injury_reports.py
The existing schedule must match the pinned SHA-256 below. Its source is
https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_schedules
(asset 488098414, nba_stats_schedule_2024.csv). Injury PDFs and, if missing, the
recursive Git tree are fetched from akng8/nba-injury-scraper at the pinned commit.
Use at most four ordinary HTTPS workers, with no retries or access-block bypass.
Existing failures stay recorded, and original retrieval timestamps are preserved.
All downloaded third-party files and the acquisition manifest remain ignored.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.request

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/nba-creator-assists"
SOURCE = ROOT / "data/raw/nba-source-feasibility"
COMMIT = "02cfe44f7453182eb4a29283285a7af64f5e3c9a"
SCHEDULE_SHA256 = "ab5b7b5b978f0527a9e1ff4332b3e14d00c526964d2ea79b4d9f992f38eacb26"
TREE_URL = f"https://api.github.com/repos/akng8/nba-injury-scraper/git/trees/{COMMIT}?recursive=1"
MANIFEST = RAW / "injury-report-manifest.json"


def now():
    return datetime.now(timezone.utc).isoformat()


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "BeatingAnything-research/0.1"})
    with urllib.request.urlopen(req, timeout=35) as response:
        return response.read(), response.status


def selected_inputs():
    schedule = SOURCE / "nba_stats_schedule_2024.csv"
    if hashlib.sha256(schedule.read_bytes()).hexdigest() != SCHEDULE_SHA256:
        raise ValueError("Schedule differs from the pinned release asset")
    with schedule.open() as handle:
        game_dates = sorted({r["game_date"] for r in csv.DictReader(handle)
                             if r["game_id"].startswith("00224")})
    if not game_dates:
        raise ValueError("No fixed-season regular-season dates")
    tree_path = SOURCE / "injury-tree.json"
    if not tree_path.exists():
        tree_bytes, _ = fetch(TREE_URL)  # One ordinary request; no follow-up on 403.
        tree = json.loads(tree_bytes)
        if tree.get("sha") != COMMIT or tree.get("truncated", True):
            raise ValueError("Pinned recursive tree is incomplete or mismatched")
        tree_path.write_bytes(tree_bytes)
    else:
        tree = json.loads(tree_path.read_text())
    if tree.get("sha") != COMMIT or tree.get("truncated", True):
        raise ValueError("Pinned recursive tree is incomplete or mismatched")
    bydate = defaultdict(list)
    for item in tree["tree"]:
        match = re.fullmatch(r"pdfs/(\d{4}-\d{2}-\d{2})/Injury-Report_\1_(\d{2})(AM|PM)\.pdf", item["path"])
        if match:
            hour = int(match[2]) % 12 + (12 if match[3] == "PM" else 0)
            bydate[match[1]].append((hour, item))
    jobs, missing = [], []
    for day in sorted({str(date.fromisoformat(d) - timedelta(days=1)) for d in game_dates}):
        if bydate[day]:
            hour, item = max(bydate[day], key=lambda pair: (pair[0], pair[1]["path"]))
            jobs.append((day, hour, item))
        else:
            missing.append({"selected_date": day, "status": "missing_archive_date"})
    return game_dates, jobs, missing


def validate_pdf(dst, txt, data, expected_sha, selected_day):
    blob_sha = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if blob_sha != expected_sha:
        raise ValueError("Git blob SHA1 mismatch")
    subprocess.run(["pdftotext", "-raw", str(dst), str(txt)], check=True, capture_output=True)
    content = txt.read_text()
    pdf_pages = len(PdfReader(dst).pages)
    page_rows = [(int(a), int(b)) for a, b in re.findall(r"Page (\d+) of (\d+)", content)]
    if page_rows != [(n, pdf_pages) for n in range(1, pdf_pages + 1)]:
        raise ValueError("Extracted page sequence differs from PDF page count")
    if content.count("\f") != pdf_pages:
        raise ValueError("Text page separators differ from PDF page count")
    headers = re.findall(r"Injury Report:\s*(\d{2}/\d{2}/\d{2})\s+(\d{2}:\d{2}\s+[AP]M)", content)
    if len(headers) != pdf_pages:
        raise ValueError("Missing issue header on a PDF page")
    issue_times = sorted({datetime.strptime(f"{a} {b}", "%m/%d/%y %I:%M %p").isoformat() for a, b in headers})
    if len(issue_times) != 1 or issue_times[0][:10] != selected_day:
        raise ValueError("Actual report issue date/time is ambiguous or differs from selected day")
    target_day = (date.fromisoformat(selected_day) + timedelta(days=1)).strftime("%m/%d/%Y")
    return {
        "sha256": hashlib.sha256(data).hexdigest(), "git_blob_sha1": blob_sha,
        "bytes": len(data), "header_issue_strings": sorted({f"{a} {b}" for a, b in headers}),
        "header_issue_iso_local": issue_times, "page_count": pdf_pages,
        "target_next_day_date_present": target_day in content, "status": "validated",
    }


def acquire(job, prior):
    day, hour, item = job
    url = f"https://raw.githubusercontent.com/akng8/nba-injury-scraper/{COMMIT}/{item['path']}"
    dst = RAW / Path(item["path"]).name
    txt = dst.with_suffix(".txt")
    if prior and prior.get("status") == "failed" and ("HTTPError:" in prior.get("error", "") or not dst.exists()):
        return prior  # Never retry an HTTP error; local validation can be corrected.
    rec = dict(prior or {})
    fixed = {"selected_date": day, "selection_filename_hour_24": hour, "archive_path": item["path"],
             "archive_commit": COMMIT, "expected_git_blob_sha1": item["sha"], "url": url,
             "pdf_path": str(dst.relative_to(ROOT)), "text_path": str(txt.relative_to(ROOT))}
    for key, value in fixed.items():
        if key in rec and rec[key] != value:
            raise ValueError(f"Existing manifest selection changed: {day} {key}")
    rec.update(fixed)
    try:
        if dst.exists():
            data = dst.read_bytes()
            rec.setdefault("acquisition", "existing_local_unrecorded")
        else:
            requested_at = now()
            rec.setdefault("requested_at_utc", requested_at)
            if prior:
                rec.setdefault("reacquisition_requests_at_utc", []).append(requested_at)
            data, http_status = fetch(url)
            rec["http_status"] = http_status
            dst.write_bytes(data)
            rec.setdefault("acquisition", "ordinary_https_get")
        rec.update(validate_pdf(dst, txt, data, item["sha"], day))
        if "error" in rec:
            rec.setdefault("previous_validation_errors", []).append(rec.pop("error"))
    except Exception as exc:
        rec.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    return rec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    game_dates, jobs, missing = selected_inputs()
    old = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    if old and old.get("archive_commit") != COMMIT:
        raise ValueError("Existing acquisition manifest belongs to another source")
    old_records = {r["selected_date"]: r for r in old.get("records", [])}
    records = {r["selected_date"]: r for r in missing}
    payload = {"archive_repository": "akng8/nba-injury-scraper", "archive_commit": COMMIT,
               "selection": "For each fixed 2024-25 regular-season game date, select the preceding calendar day and latest available filename hour; validate actual header issue date equals that day. No outcomes used.",
               "schedule_sha256": SCHEDULE_SHA256, "game_date_count": len(game_dates),
               "first_game_date": game_dates[0], "last_game_date": game_dates[-1],
               "selected_date_count": len(jobs) + len(missing)}
    print(f"Fixed selection: {len(game_dates)} game dates, {len(jobs)} PDFs, {len(missing)} missing dates", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(acquire, job, old_records.get(job[0])) for job in jobs]
        for n, future in enumerate(as_completed(futures), 1):
            rec = future.result()
            records[rec["selected_date"]] = rec
            # Preserve existing completed entries while checkpointing a partial rerun.
            checkpoint = dict(old_records)
            checkpoint.update(records)
            payload["records"] = sorted(checkpoint.values(), key=lambda r: r["selected_date"])
            temporary = MANIFEST.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(payload, indent=2) + "\n")
            temporary.replace(MANIFEST)
            if n % 20 == 0 or rec["status"] != "validated":
                print(f"{n}/{len(jobs)} {rec['selected_date']}: {rec['status']}", flush=True)
    print(json.dumps(dict(Counter(r["status"] for r in records.values()))), flush=True)
    print(MANIFEST, flush=True)


if __name__ == "__main__":
    main()
