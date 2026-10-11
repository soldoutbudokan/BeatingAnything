"""Inventory → exact quote queue → cached collection → conservative EV bounds.

No wagering or account actions. Book-specific SGP prices are never synthesized
from single-leg prices. Historical replays cannot produce live opportunities.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import time

from .math import evaluate, event_key, generate_candidates
from .models import CELLS, digest, number, quote_request, timestamp, utc_now, validate_manifest, validate_request


def reference_partitions(board, limit):
    inventory = board["books"].get("fanduel", {})
    pairs = {}
    for leg in inventory.get("legs", []):
        if leg["side"] not in ("over", "under") or float(leg["line"]).is_integer():
            continue  # Four cells cannot represent pushes.
        key = (leg["stat"], leg["line"], leg["market_id"])
        side = pairs.setdefault(key, {})
        if leg["side"] in side:
            raise ValueError("ambiguous duplicate FD over/under market")
        side[leg["side"]] = leg
    pairs = {k: v for k, v in pairs.items() if set(v) == {"over", "under"}}
    result, total = [], 0
    for (stat, line, _), combined in sorted(pairs.items()):
        if stat != "S":
            continue
        for (other, other_line, _), marginal in sorted(pairs.items()):
            if other not in ("R", "C"):
                continue
            total += 1
            if len(result) >= limit:
                continue
            requests = {cell: quote_request(board, "fanduel", [
                combined["over" if cell[0] == "O" else "under"],
                marginal["over" if cell[1] == "O" else "under"]], purpose="reference") for cell in CELLS}
            result.append({"id": digest([requests[c]["key"] for c in CELLS]),
                           "sum_line": line, "other": other, "other_line": other_line, "requests": requests})
    return result, total


def plan(manifest, *, max_legs=4, max_candidates=5000, max_references=32):
    validate_manifest(manifest)
    for value in (max_candidates, max_references):
        if type(value) is not int or value < 1:
            raise ValueError("plan limits must be positive integers")
    jobs, requests, gaps = [], {}, []
    for board in manifest["boards"]:
        if "thescore" not in board["books"]:
            gaps.append({"event_id": board["event_id"], "player_id": board["player_id"], "reason": "missing_thescore_inventory"})
            continue
        generated = generate_candidates(board["books"]["thescore"]["legs"], max_legs=max_legs, max_candidates=max_candidates)
        variants = [quote_request(board, "thescore", legs, purpose="candidate") for legs in generated["candidates"]]
        references, reference_total = reference_partitions(board, max_references)
        for request in variants + [req for ref in references for req in ref["requests"].values()]:
            requests[request["key"]] = request
        if not references:
            gaps.append({"event_id": board["event_id"], "player_id": board["player_id"], "reason": "no_complete_fanduel_partition"})
        jobs.append({"board": board, "variants": variants, "references": references,
                     "candidate_coverage": {k: v for k, v in generated.items() if k != "candidates"},
                     "reference_partitions_available": reference_total,
                     "reference_partitions_truncated": reference_total > len(references)})
    return {"schema_version": 1, "mode": manifest["mode"], "jobs": jobs,
            "requests": list(requests.values()), "gaps": gaps,
            "stats": {"boards": len(manifest["boards"]), "candidate_variants": sum(len(j["variants"]) for j in jobs),
                      "reference_partitions": sum(len(j["references"]) for j in jobs),
                      "unique_quote_requests": len(requests)}}


class CaptureProvider:
    """Import exact requests and observations from a capture worker or replay.

    Capture files are input evidence, not proof of a live integration. Unknown
    source freshness and unconfirmed captures remain ineligible for alerts.
    """
    def __init__(self, path):
        paths = path if isinstance(path, (list, tuple)) else [path]
        sources = [json.loads(Path(p).read_text()) for p in paths]
        if not sources or len({s.get("mode") for s in sources}) != 1:
            raise ValueError("capture files must have one matching mode")
        self.data = {"mode": sources[0]["mode"], "observations": [row for source in sources for row in source["observations"]]}
        self.cache_token = digest(self.data)
        if self.data.get("mode") not in ("historical", "live"):
            raise ValueError("capture file requires historical/live mode")
        self.rows = {}
        for row in self.data["observations"]:
            request = validate_request(row["request"])
            timestamp(row["received_at"])
            if row.get("source_at") is not None:
                timestamp(row["source_at"])
            if row.get("status") not in ("priced", "unavailable", "error"):
                raise ValueError("unknown capture quote status")
            if row["status"] == "priced" and abs(number(row.get("american"), "american odds")) < 100:
                raise ValueError("invalid American odds")
            # Ties prefer the last append; a suspension wins over an old quote.
            key = request["key"]
            old = self.rows.get(key)
            if old is None or timestamp(row["received_at"]) >= timestamp(old["received_at"]):
                self.rows[key] = row

    def collect(self, request, now):
        row = self.rows.get(request["key"])
        if row is None:
            return {"status": "unavailable", "american": None, "received_at": now,
                    "mode": self.data["mode"], "reason": "not_in_capture", "source": "capture_file"}
        return {k: v for k, v in row.items() if k != "request"} | {"mode": self.data["mode"]}


class OpticCollector:
    def __init__(self, provider):
        self.provider = provider
        self.cache_token = "opticodds-v1"

    def collect(self, request, now):
        if request["book"] != "thescore":
            return {"status": "unavailable", "american": None, "received_at": now, "mode": "live",
                    "source": "opticodds", "reason": "fanduel_sgp_coverage_unverified"}
        result = self.provider.quote(request["sportsbook"], [leg["provider"] for leg in request["legs"]])
        return {**result, "source_at": result.get("source_timestamp"), "mode": "live",
                "source": "opticodds", "confirmed": False, "region_verified": False,
                "freshness_verified": False}


class Runner:
    def __init__(self, store, collectors, *, now, mode, max_quotes=100, cache_ttl=30,
                 max_age=120, partition_skew=30, comparison_skew=120, clock=utc_now):
        if mode not in ("historical", "live"):
            raise ValueError("invalid run mode")
        timestamp(now)
        if type(max_quotes) is not int:
            raise ValueError("max_quotes must be an integer")
        for name, value in {"max_quotes": max_quotes, "cache_ttl": cache_ttl, "max_age": max_age,
                            "partition_skew": partition_skew, "comparison_skew": comparison_skew}.items():
            if number(value, name) <= 0:
                raise ValueError(f"{name} must be positive")
        self.store, self.collectors, self.now, self.mode = store, collectors, now, mode
        self.clock = clock
        self.max_quotes, self.cache_ttl, self.max_age = max_quotes, cache_ttl, max_age
        self.partition_skew, self.comparison_skew = partition_skew, comparison_skew
        self.metrics = Counter()
        self.results = {}

    def current_time(self):
        return self.clock() if self.mode == "live" else self.now

    def quote(self, request, *, force=False):
        key = request["key"]
        if not force and key in self.results:
            self.metrics["in_run_reuses"] += 1
            return self.results[key]
        now = self.current_time()
        collector = self.collectors.get(request["book"])
        token = getattr(collector, "cache_token", None)
        cached = None if force else self.store.get(request, now, self.cache_ttl)
        if cached and cached.get("mode") == self.mode and cached.get("collector_token") == token:
            self.metrics["cache_hits"] += 1
            self.results[key] = cached
            return cached
        if self.metrics["collection_calls"] >= self.max_quotes:
            self.metrics["budget_skips"] += 1
            return {"status": "unavailable", "received_at": self.now, "reason": "quote_budget_exhausted"}
        if collector is None:
            return {"status": "unavailable", "received_at": self.now, "reason": "no_collector_for_book"}
        attempt = self.store.begin(request, now)
        self.metrics["collection_calls"] += 1
        try:
            result = collector.collect(request, now)
            timestamp(result["received_at"])
            if result.get("status") not in ("priced", "unavailable", "error"):
                raise ValueError("unknown quote status")
            if result["status"] == "priced":
                if abs(number(result.get("american"), "american odds")) < 100:
                    raise ValueError("invalid American odds")
        except Exception as exc:
            # Exception text may contain credential-bearing URLs. Preserve only
            # its type; the provider retains sanitized request evidence.
            result = {"status": "error", "received_at": now, "mode": self.mode,
                      "reason": type(exc).__name__}
        result["request_key"] = key
        result["collector_token"] = token
        self.store.finish(attempt, result)
        self.results[key] = result
        self.metrics["quotes_" + result["status"]] += 1
        return result

    def valid(self, result):
        if result.get("status") != "priced":
            return False, result.get("reason") or result.get("error") or "quote_unavailable"
        if result.get("mode") != self.mode:
            return False, "historical_live_mode_mismatch"
        for field in ("received_at", "source_at"):
            if result.get(field) is None:
                continue
            age = (timestamp(self.current_time()) - timestamp(result[field])).total_seconds()
            if not 0 <= age <= self.max_age:
                return False, "stale_or_future_" + field
        if result.get("exact_legs_verified") is not True:
            return False, "exact_legs_unverified"
        return True, None

    @staticmethod
    def confirmation_gaps(results):
        gaps = set()
        for result in results:
            if result.get("confirmed") is not True:
                gaps.add("repeat_confirmation_missing")
            if result.get("region_verified") is not True:
                gaps.add("ontario_source_unverified")
            if result.get("freshness_verified") is not True or result.get("source_at") is None:
                gaps.add("source_freshness_unverified")
            if not result.get("evidence") and not result.get("raw_ref"):
                gaps.add("evidence_missing")
        return sorted(gaps)

    def run(self, work):
        if work["mode"] != self.mode:
            raise ValueError("plan/run mode mismatch")
        started = time.monotonic()
        for job in work["jobs"]:
            for book in job["board"]["books"]:
                self.metrics["inventory_invalidations"] += self.store.register(job["board"], book)
        rows, gaps = [], list(work["gaps"])
        for job in work["jobs"]:
            board = job["board"]
            if self.mode == "live" and timestamp(board["starts_at"]) <= timestamp(self.current_time()):
                gaps.append({"event_id": board["event_id"], "reason": "started_event_not_supported"})
                continue
            if self.mode == "live" and any(not 0 <= (timestamp(self.current_time()) - timestamp(inv["captured_at"])).total_seconds() <= self.max_age
                                           for inv in board["books"].values()):
                gaps.append({"event_id": board["event_id"], "player_id": board["player_id"], "reason": "stale_or_future_inventory"})
                continue
            refs = []
            for ref in job["references"]:
                quoted = {cell: self.quote(req) for cell, req in ref["requests"].items()}
                failures = [self.valid(q)[1] for q in quoted.values() if not self.valid(q)[0]]
                clocks = [timestamp(q["received_at"]) for q in quoted.values()]
                if not failures and (max(clocks) - min(clocks)).total_seconds() > self.partition_skew:
                    failures.append("incoherent_partition_capture_window")
                source_clocks = [timestamp(q["source_at"]) for q in quoted.values() if q.get("source_at")]
                if len(source_clocks) > 1 and (max(source_clocks) - min(source_clocks)).total_seconds() > self.partition_skew:
                    failures.append("incoherent_partition_source_window")
                if failures:
                    gaps.append({"reference_id": ref["id"], "reasons": sorted(set(failures))})
                    continue
                refs.append((ref, quoted))
            if not refs:
                continue  # Do not spend on TSB with no usable FD comparison.
            for request in job["variants"]:
                result = self.quote(request)
                okay, reason = self.valid(result)
                if not okay:
                    gaps.append({"request_key": request["key"], "reason": reason})
                    continue
                for ref, quoted in refs:
                    all_quotes = [result, *quoted.values()]
                    if not all(self.valid(q)[0] for q in all_quotes):
                        gaps.append({"request_key": request["key"], "reference_id": ref["id"], "reason": "quote_expired_during_scan"})
                        continue
                    clocks = [timestamp(q["received_at"]) for q in all_quotes]
                    if (max(clocks) - min(clocks)).total_seconds() > self.comparison_skew:
                        gaps.append({"request_key": request["key"], "reference_id": ref["id"], "reason": "cross_book_capture_skew"})
                        continue
                    source_clocks = [timestamp(q["source_at"]) for q in all_quotes if q.get("source_at")]
                    if len(source_clocks) > 1 and (max(source_clocks) - min(source_clocks)).total_seconds() > self.comparison_skew:
                        gaps.append({"request_key": request["key"], "reference_id": ref["id"], "reason": "cross_book_source_skew"})
                        continue
                    evaluation = evaluate(request["legs"], result["american"], {
                        "sum_line": ref["sum_line"], "other": ref["other"], "other_line": ref["other_line"],
                        "prices": {cell: q["american"] for cell, q in quoted.items()}})
                    row = {"request_key": request["key"], "event_id": board["event_id"],
                           "player_id": board["player_id"], "player_name": board["player_name"],
                           "league": board["league"], "region": board["region"],
                           "event_group": digest([board["event_id"], board["player_id"], board["settlement"], event_key(request["legs"])]),
                           "legs": request["legs"], "american": result["american"],
                           "quote_received_at": result["received_at"], "reference_id": ref["id"],
                           "reference_received_at": {cell: q["received_at"] for cell, q in quoted.items()},
                           "confirmation_gaps": self.confirmation_gaps(all_quotes),
                           "_quotes": all_quotes, "_starts_at": board["starts_at"], **evaluation}
                    positive = row["both_models_positive"]
                    row["status"] = ("historical_positive" if self.mode == "historical" else
                                     "needs_confirmation" if row["confirmation_gaps"] else "confirmed_live") if positive else "not_proven_positive"
                    rows.append(row)
        for row in rows:
            quotes = row.pop("_quotes")
            starts_at = row.pop("_starts_at")
            if self.mode == "live" and (not all(self.valid(q)[0] for q in quotes)
                                         or timestamp(starts_at) <= timestamp(self.current_time())):
                row["status"] = "expired_during_scan"
        rows.sort(key=lambda row: row.get("conservative_ev_lower") if row.get("conservative_ev_lower") is not None else -float("inf"), reverse=True)
        # Every offered construction remains visible, while equivalent events
        # count once in the summary rather than as independent betting edges.
        positives = [row for row in rows if row["status"] in ("confirmed_live", "historical_positive", "needs_confirmation")]
        return {"schema_version": 1, "mode": self.mode, "as_of": self.current_time(),
                "opportunities": [r for r in positives if r["status"] == "confirmed_live"],
                "historical_opportunities": [r for r in positives if r["status"] == "historical_positive"],
                "needs_confirmation": [r for r in positives if r["status"] == "needs_confirmation"],
                "evaluations": rows, "gaps": gaps,
                "coverage": [{"event_id": j["board"]["event_id"], "player_id": j["board"]["player_id"],
                              "candidates": j["candidate_coverage"], "reference_partitions_available": j["reference_partitions_available"],
                              "references_truncated": j["reference_partitions_truncated"]} for j in work["jobs"]],
                "stats": {**work["stats"], **dict(self.metrics), "evaluations": len(rows),
                          "positive_underlying_events": len({r["event_group"] for r in positives}),
                          "elapsed_seconds": time.monotonic() - started}}
