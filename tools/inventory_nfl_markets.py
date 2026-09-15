#!/usr/bin/env python3
"""Read-only market/timestamp inventory; prints aggregates, never prices or outcomes."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import duckdb


def inventory(path: Path) -> dict:
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    connection = duckdb.connect(str(path), read_only=True)

    def query(sql):
        result = connection.execute(sql)
        names = [column[0] for column in result.description]
        return [dict(zip(names, row)) for row in result.fetchall()]

    result = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_file": path.name,
        "source_bytes": path.stat().st_size,
        "source_sha256": digest,
        "duckdb_version": duckdb.__version__,
        "scope": "raw_odds aggregates only; no outcomes, prices, model or promotion decision",
        "timestamp_note": "Naive source TIMESTAMP values represent UTC per publisher extraction code.",
        "schema": {row["column_name"]: row["column_type"]
                   for row in query("DESCRIBE raw_odds")},
        "coverage": query("""
            SELECT count(*) AS rows, count(DISTINCT event_id) AS events,
                   count(DISTINCT bookmaker_key) AS books,
                   count(DISTINCT captured_at) AS captures,
                   min(captured_at) AS first_capture, max(captured_at) AS last_capture,
                   min(loaded_at) AS first_load, max(loaded_at) AS last_load
            FROM raw_odds
        """)[0],
        "all_markets": query("""
            SELECT market_key, count(*) AS rows,
                   count(DISTINCT event_id) AS events,
                   count(DISTINCT bookmaker_key) AS books
            FROM raw_odds GROUP BY 1 ORDER BY 1
        """),
        "book_markets": query("""
            SELECT bookmaker_key, market_key, count(*) AS rows,
                   count(DISTINCT event_id) AS events,
                   count(DISTINCT captured_at) AS captures,
                   min(captured_at) AS first_capture, max(captured_at) AS last_capture,
                   sum(captured_at >= commence_time) AS rows_at_or_after_own_start,
                   count(DISTINCT event_id) FILTER (WHERE captured_at >= commence_time)
                       AS events_at_or_after_own_start
            FROM raw_odds WHERE bookmaker_key IN ('fanduel', 'pinnacle')
            GROUP BY 1, 2 ORDER BY 1, 2
        """),
        "book_update_age_seconds": query("""
            SELECT bookmaker_key,
                   count(*) FILTER (WHERE bookmaker_last_update IS NULL) AS missing,
                   count(*) FILTER (WHERE bookmaker_last_update > captured_at) AS future,
                   quantile_cont(epoch(captured_at-bookmaker_last_update), 0.5) AS median,
                   quantile_cont(epoch(captured_at-bookmaker_last_update), 0.9) AS p90,
                   quantile_cont(epoch(captured_at-bookmaker_last_update), 0.99) AS p99,
                   max(epoch(captured_at-bookmaker_last_update)) AS maximum,
                   max(epoch(captured_at-bookmaker_last_update))
                       FILTER (WHERE captured_at < commence_time) AS maximum_before_own_start
            FROM raw_odds WHERE bookmaker_key IN ('fanduel', 'pinnacle')
            GROUP BY 1 ORDER BY 1
        """),
        "fanduel_simultaneous_line_counts": query("""
            WITH lines AS (
                SELECT event_id, captured_at, market_key, outcome_name,
                       count(DISTINCT outcome_point) AS points
                FROM raw_odds WHERE bookmaker_key='fanduel'
                    AND market_key IN ('spreads', 'totals')
                GROUP BY event_id, captured_at, market_key, outcome_name
            )
            SELECT market_key, max(points) AS maximum_distinct_points_per_side,
                   count(*) AS snapshot_side_groups
            FROM lines GROUP BY 1 ORDER BY 1
        """),
        "capture_interval_hours": query("""
            WITH captures AS (SELECT DISTINCT captured_at FROM raw_odds),
            gaps AS (SELECT epoch(captured_at-lag(captured_at) OVER
                (ORDER BY captured_at))/3600 AS hours FROM captures)
            SELECT min(hours) AS minimum, quantile_cont(hours, 0.5) AS median,
                   max(hours) AS maximum FROM gaps
        """)[0],
        "lay_market_books": query("""
            SELECT bookmaker_key, count(*) AS rows FROM raw_odds
            WHERE market_key='h2h_lay' GROUP BY 1 ORDER BY 1
        """),
    }
    connection.close()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, nargs="?",
                        default=Path("data/raw/nfl-source-audit/nfl_odds.duckdb"))
    args = parser.parse_args()
    print(json.dumps(inventory(args.database), indent=2, default=str))
