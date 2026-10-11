"""Run with ``python -m beating.sgp --help``. Live commands require an existing key."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from .models import timestamp, utc_now, validate_request
from .normalize import normalize_snapshots
from .pipeline import CaptureProvider, OpticCollector, Runner, plan
from .providers import OpticOddsProvider, ProviderError
from .store import QuoteStore


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    pending.replace(path)


def parser():
    app = argparse.ArgumentParser(description="Exact-selection SGP collection and conservative EV bounds; no bets.")
    commands = app.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="replay the historical McCaffrey observations offline")
    demo.add_argument("--output", default="data/raw/sgp-demo")
    for name in ("plan", "run"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--manifest", required=True)
        cmd.add_argument("--output", required=True)
        cmd.add_argument("--max-candidates", type=int, default=5000)
        cmd.add_argument("--max-references", type=int, default=32)
        cmd.add_argument("--max-legs", type=int, default=4)
        if name == "run":
            cmd.add_argument("--captures", action="append", required=True, help="exact-request capture JSON; repeat for separate book workers")
            cmd.add_argument("--state", default="state/sgp.sqlite")
            cmd.add_argument("--as-of", help="required for historical input; forbidden for live input")
            cmd.add_argument("--max-quotes", type=int, default=100)
            cmd.add_argument("--cache-ttl", type=float, default=30)
            cmd.add_argument("--max-age", type=float, default=120)
            cmd.add_argument("--partition-skew", type=float, default=30)
            cmd.add_argument("--comparison-skew", type=float, default=120)
    discover = commands.add_parser("discover", help="capture raw provider fixtures and batched market snapshots")
    discover.add_argument("--league", action="append", choices=("nfl", "ncaaf"), required=True)
    discover.add_argument("--sportsbook", action="append", choices=("theScore", "FanDuel"), required=True)
    discover.add_argument("--max-fixtures", type=int, default=10)
    discover.add_argument("--max-requests", type=int, default=20)
    discover.add_argument("--request-interval", type=float, default=0.5)
    discover.add_argument("--start-after")
    discover.add_argument("--start-before")
    discover.add_argument("--output", required=True)
    normalize = commands.add_parser("normalize", help="map exact documented markets; never infer by fuzzy names")
    normalize.add_argument("--snapshots", required=True)
    normalize.add_argument("--market-map", required=True)
    normalize.add_argument("--region", required=True)
    normalize.add_argument("--settlement", required=True)
    normalize.add_argument("--output", required=True)
    capture = commands.add_parser("capture", help="collect theScore SGP requests via OpticOdds; live plan only")
    capture.add_argument("--plan", required=True)
    capture.add_argument("--max-quotes", type=int, default=20)
    capture.add_argument("--request-interval", type=float, default=0.5)
    capture.add_argument("--max-age", type=float, default=120)
    capture.add_argument("--output", required=True)
    template = commands.add_parser("capture-template", help="create an unconfirmed capture-worker handoff for the exact quote queue")
    template.add_argument("--plan", required=True)
    template.add_argument("--book", choices=("thescore", "fanduel"))
    template.add_argument("--output", required=True)
    return app


def execute(args):
    if args.command == "demo":
        fixtures = Path(__file__).with_name("fixtures")
        manifest = read(fixtures / "cmc-manifest.json")
        captures = CaptureProvider(fixtures / "cmc-captures.json")
        work = plan(manifest)
        output = Path(args.output)
        write(output / "plan.json", work)
        store = QuoteStore(output / "quotes.sqlite")
        try:
            result = Runner(store, {"thescore": captures, "fanduel": captures},
                            now="2026-10-09T19:30:30Z", mode="historical", max_quotes=100,
                            cache_ttl=300, max_age=300, comparison_skew=180).run(work)
        finally:
            store.close()
        write(output / "report.json", result)
        return {"mode": "historical", "report": str(output / "report.json"), "stats": result["stats"],
                "historical_positive_variants": len(result["historical_opportunities"]), "live_opportunities": 0}
    if args.command in ("plan", "run"):
        manifest = read(args.manifest)
        work = plan(manifest, max_legs=args.max_legs, max_candidates=args.max_candidates, max_references=args.max_references)
        if args.command == "plan":
            write(args.output, work)
            return {"output": args.output, **work["stats"], "gaps": work["gaps"]}
        if (manifest["mode"] == "historical") != bool(args.as_of):
            raise ValueError("historical runs require --as-of; live runs must use the current clock")
        captures = CaptureProvider(args.captures)
        if captures.data["mode"] != manifest["mode"]:
            raise ValueError("capture and manifest modes must match")
        store = QuoteStore(args.state)
        try:
            result = Runner(store, {"thescore": captures, "fanduel": captures},
                            now=args.as_of or utc_now(), mode=manifest["mode"], max_quotes=args.max_quotes,
                            cache_ttl=args.cache_ttl, max_age=args.max_age,
                            partition_skew=args.partition_skew, comparison_skew=args.comparison_skew).run(work)
        finally:
            store.close()
        write(args.output, result)
        return {"output": args.output, "mode": result["mode"], "stats": result["stats"],
                "live_opportunities": len(result["opportunities"]), "needs_confirmation": len(result["needs_confirmation"]),
                "historical_positive_variants": len(result["historical_opportunities"])}
    if args.command == "discover":
        if args.max_fixtures < 1:
            raise ValueError("max-fixtures must be positive")
        output = Path(args.output)
        provider = OpticOddsProvider(output / "evidence", api_key=os.environ.get("OPTICODDS_API_KEY"),
                                    max_requests=args.max_requests, min_interval_seconds=args.request_interval)
        fixtures = provider.discover_fixtures(args.league, start_after=args.start_after, start_before=args.start_before)
        selected = fixtures[:args.max_fixtures]
        snapshots = provider.snapshots([f["id"] for f in selected], args.sportsbook) if selected else []
        result = {"schema_version": 1, "mode": "live", "captured_at": utc_now(), "snapshots": snapshots,
                  "fixtures": fixtures, "coverage": {"discovered_fixtures": len(fixtures), "selected_fixtures": len(selected),
                  "truncated": len(fixtures) > len(selected), "jurisdiction": "unverified"}}
        write(output / "snapshots.json", result)
        return {"output": str(output / "snapshots.json"), **result["coverage"]}
    if args.command == "normalize":
        bundle = read(args.snapshots)
        if bundle.get("mode") != "live":
            raise ValueError("normalize requires live snapshots with retained receipt clocks")
        result = normalize_snapshots(bundle["snapshots"], market_map=read(args.market_map), region=args.region,
                                     settlement=args.settlement, captured_at=bundle["captured_at"])
        write(args.output, result)
        return {"output": args.output, "coverage": result["coverage"]}
    work = read(args.plan)
    for request in work["requests"]:
        validate_request(request)
    if args.command == "capture-template":
        result = {"schema_version": 1, "mode": work["mode"], "observations": [
            {"request": request, "status": "unavailable", "american": None, "received_at": utc_now(),
             "source_at": None, "source": "capture_worker", "reason": "not_yet_captured",
             "exact_legs_verified": False, "confirmed": False, "region_verified": False,
             "freshness_verified": False, "evidence": None}
            for request in work["requests"] if not args.book or request["book"] == args.book]}
        write(args.output, result)
        return {"output": args.output, "unconfirmed_requests": len(result["observations"])}
    if work.get("mode") != "live":
        raise ValueError("historical/replay plans cannot be sent to a live provider")
    if args.max_quotes < 1:
        raise ValueError("max-quotes must be positive")
    # Fail before network on replay IDs or a malformed handoff.
    for request in work["requests"]:
        if request["fixture_id"].startswith("replay:"):
            raise ValueError("replay identities cannot be submitted to a provider")
        age = (timestamp(utc_now()) - timestamp(request["inventory_captured_at"])).total_seconds()
        if not 0 <= age <= args.max_age:
            raise ValueError("live capture requires a fresh inventory; rediscover the board")
    for job in work.get("jobs", []):
        if timestamp(job["board"]["starts_at"]) <= timestamp(utc_now()):
            raise ValueError("live capture supports pregame events only")
    provider = OpticOddsProvider(Path(args.output).parent / "evidence", max_requests=args.max_quotes,
                                api_key=os.environ.get("OPTICODDS_API_KEY"), min_interval_seconds=args.request_interval)
    collector = OpticCollector(provider)
    requested = [r for r in work["requests"] if r["book"] == "thescore"]
    # Price redundancy constructions first under a small budget. The plan
    # retains bases and every variant; this is scheduling, not price pruning.
    selected = sorted(requested, key=lambda r: -len(r["legs"]))[:args.max_quotes]
    result = {"schema_version": 1, "mode": "live", "observations": [], "coverage": {
        "planned_thescore": len(requested), "selected": len(selected), "truncated": len(requested) > len(selected),
        "fanduel_sgp": "unverified_no_requests", "jurisdiction": "unverified", "source_freshness": "unverified"}}
    # Checkpoint each successful response so a later rate limit/denial doesn't
    # lose earlier evidence. ProviderError terminates without automatic retry.
    write(args.output, result)
    for request in selected:
        observation = collector.collect(request, utc_now())
        result["observations"].append({"request": request, **observation})
        write(args.output, result)
    return {"output": args.output, "collected": len(result["observations"]), **result["coverage"]}


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = execute(args)
    except (ValueError, KeyError, TypeError, OSError, ProviderError) as exc:
        # ProviderError is sanitized by the provider. No full URLs/tracebacks.
        print(json.dumps({"status": "blocked", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
