"""Verify retained charting schemas, identities, hashes and dates only.

No game-result data, fitted probabilities or strategy returns are loaded.
The QS-to-CSV conversion itself requires the separately documented R check.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(value):
    try:
        number = Decimal(value)
        if number.is_finite():
            return number.normalize()
    except InvalidOperation:
        pass
    return value


def read_csv(path):
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Source retrieval dates must have an explicit timezone")
    return parsed.astimezone(timezone.utc)


def verify(root, update_report=False):
    report_path = root/"reports/nfl-charting-source-audit.json"
    report = json.loads(report_path.read_text())
    checks, failures = 0, []

    def check(condition, name):
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(name)

    def audit_rows(fields, rows, expected, label):
        keys = [(r["nflverse_game_id"], normalized(r["nflverse_play_id"])) for r in rows]
        check(len(rows) == expected["rows"], label+" rows")
        check(len({r["nflverse_game_id"] for r in rows}) == expected["games"], label+" games")
        check(len(keys)-len(set(keys)) == expected["duplicate_keys"], label+" duplicate keys")
        check(all(a and b != "" for a, b in keys), label+" nonmissing keys")
        check(len(fields) == 29, label+" 29 fields")
        days = dict(sorted(Counter(timestamp(r["date_pulled"]).date().isoformat() for r in rows).items()))
        check(days == expected["date_pulled_day_counts"], label+" date counts")
        for name, count in expected.get("missing", {}).items():
            check(sum(r[name].strip().lower() in {"", "na", "nan", "null"} for r in rows) == count,
                  label+" missing "+name)
        dates = [timestamp(r["date_pulled"]) for r in rows]
        return keys, {"earliest_date_pulled": min(dates).isoformat(),
                      "latest_date_pulled": max(dates).isoformat()}

    current, ranges = {}, {}
    for item in report["files"]:
        path = root/item["file"]
        meta_path = path.with_suffix(".meta.json")
        meta = json.loads(meta_path.read_text())
        check(digest(path) == item["sha256"] == meta["sha256"], path.name+" hash")
        check(path.stat().st_size == item["bytes"] == meta["bytes"], path.name+" bytes")
        fields, rows = read_csv(path)
        check(fields == item["columns"], path.name+" columns")
        check(sorted({int(r["week"]) for r in rows}) == item["weeks"], path.name+" weeks")
        keys, ranges[path.name] = audit_rows(fields, rows, item, path.name)
        current[item["year"]] = (fields, rows, keys)
        item.update(source_url=meta["url"], captured_at=meta["captured_at"],
                    metadata_file=str(meta_path.relative_to(root)), metadata_sha256=digest(meta_path),
                    http_last_modified=meta.get("last_modified"), http_etag=meta.get("etag"),
                    **ranges[path.name])

    old = report["older_qs_asset"]
    raw = root/"data/raw/nfl-source-audit/ftn_charting_2025.qs"
    converted = root/"data/raw/nfl-source-audit/ftn_charting_2025-from-qs.csv"
    meta_path = raw.with_suffix(".qs.meta.json")
    meta = json.loads(meta_path.read_text())
    check(digest(raw) == old["asset_sha256"] == meta["sha256"], "QS raw hash")
    check(raw.stat().st_size == meta["bytes"], "QS raw bytes")
    check(digest(converted) == old["decoded_csv_sha256"], "QS converted CSV hash")
    fields, rows = read_csv(converted)
    keys, ranges[converted.name] = audit_rows(fields, rows, old, "QS converted")
    for week, expected in old["by_week"].items():
        group = [r for r in rows if int(r["week"]) == int(week)]
        check(len(group) == expected["rows"], "QS week "+week+" rows")
        check(len({r["nflverse_game_id"] for r in group}) == expected["games"], "QS week "+week+" games")
        dates = [timestamp(r["date_pulled"]) for r in group]
        check(min(dates) == timestamp(expected["earliest_date_pulled"]), "QS week "+week+" earliest")
        check(max(dates) == timestamp(expected["latest_date_pulled"]), "QS week "+week+" latest")

    new_fields, new_rows, new_keys = current[2025]
    check(set(fields) == set(new_fields), "2025 schemas identical")
    check(len(set(new_keys)-set(keys)) == old["new_csv_only_keys"] == 0, "current-only keys")
    check(len(set(keys)-set(new_keys)) == old["old_qs_only_keys"] == 0, "QS-only keys")
    old_by_key, new_by_key = dict(zip(keys, rows)), dict(zip(new_keys, new_rows))
    changed, compared = {}, 0
    for name in fields:
        if name == "date_pulled":
            continue
        differences = sum(normalized(old_by_key[key][name]) != normalized(new_by_key[key][name])
                          for key in old_by_key if key in new_by_key)
        compared += len(set(old_by_key) & set(new_by_key))
        if differences:
            changed[name] = differences
    check(changed == old["changed_non_timestamp_fields_vs_current_csv"] == {}, "all normalized non-date values")
    for label, values in (("qs", rows), ("csv", new_rows)):
        check(dict(Counter(r["read_thrown"] for r in values)) == old["read_thrown_categories_"+label],
              "read_thrown category counts "+label)
    changed_dates = sum(timestamp(old_by_key[key]["date_pulled"]) != timestamp(new_by_key[key]["date_pulled"])
                        for key in old_by_key if key in new_by_key)
    old.update(source_url=meta["url"], captured_at=meta["captured_at"], raw_file=str(raw.relative_to(root)),
               raw_bytes=raw.stat().st_size, decoded_csv_file=str(converted.relative_to(root)),
               metadata_file=str(meta_path.relative_to(root)), metadata_sha256=digest(meta_path),
               **ranges[converted.name])
    result = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "command": "python3 tools/audit_nfl_charting.py", "verifier_sha256": digest(Path(__file__)),
              "checks": checks, "failed_checks": failures, "non_date_cells_compared": compared,
              "non_date_changed_fields": changed, "changed_date_pulled_rows": changed_dates,
              "exact_utc_ranges": ranges,
              "scope": "Local CSV schema/hash/key/date checks and non-date equality only. No outcomes or model evaluation. "
                       "GitHub created/updated timestamps are reported provenance, not independently revalidated by this offline tool."}
    if failures:
        raise AssertionError(json.dumps(result, indent=2))
    if update_report:
        report["independent_verification"] = result
        report_path.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--update-report", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify(args.root.resolve(), args.update_report), indent=2, allow_nan=False))
