"""Append-only, fail-closed MLB moneyline paper monitor. No bet placement API."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
from typing import Any
from urllib.request import Request, urlopen

DEFAULT_CONFIG = {
    "max_quote_age_seconds": 90,
    "max_prediction_age_seconds": 900,
    "max_clock_skew_seconds": 5,
    "quote_expiry_seconds": 60,
    "close_window_seconds": 300,
    "min_expected_value": 0.03,
    "max_vig": 0.08,
    "min_decimal_odds": 1.2,
    "max_decimal_odds": 6.0,
    "webhook_enabled": False,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string with timezone")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite numeric")
    return float(value)


def nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def source_info(value: Any) -> dict:
    if not isinstance(value, dict):
        raise ValueError("source must be an object")
    for key in ("uri", "provider"):
        nonempty(value.get(key), f"source.{key}")
    if type(value.get("verified")) is not bool:
        raise ValueError("source.verified must be boolean")
    if value["verified"]:
        nonempty(value.get("verification_method"), "source.verification_method")
        if value.get("synthetic") or value.get("historical"):
            raise ValueError("synthetic/historical inputs cannot be current verified quotes")
    return value


class Monitor:
    def __init__(self, database: str | Path, config: dict | None = None):
        self.config = dict(DEFAULT_CONFIG)
        if config:
            unknown = set(config) - set(DEFAULT_CONFIG)
            if unknown:
                raise ValueError(f"unknown config keys: {sorted(unknown)}")
            self.config.update(config)
        for key, default in DEFAULT_CONFIG.items():
            value = self.config[key]
            if isinstance(default, bool):
                if type(value) is not bool:
                    raise ValueError(f"{key} must be boolean")
            elif number(value, key) < 0:
                raise ValueError(f"{key} cannot be negative")
        for key in ("max_quote_age_seconds", "max_prediction_age_seconds", "max_clock_skew_seconds", "quote_expiry_seconds", "close_window_seconds"):
            if self.config[key] > DEFAULT_CONFIG[key]:
                raise ValueError(f"{key} may be tightened but not relaxed")
        if self.config["min_expected_value"] < 0.03 or self.config["max_vig"] > 0.08:
            raise ValueError("config cannot weaken minimum EV 0.03 or maximum vig 0.08")
        if self.config["min_decimal_odds"] < 1.2 or self.config["max_decimal_odds"] > 6:
            raise ValueError("config odds bounds must stay within [1.2, 6]")
        if self.config["min_decimal_odds"] > self.config["max_decimal_odds"]:
            raise ValueError("invalid odds interval")
        self.db = sqlite3.connect(str(database))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA journal_mode = WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS models (
          model_id TEXT PRIMARY KEY, registered_at TEXT NOT NULL,
          research_status TEXT NOT NULL, artifact_sha256 TEXT, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS quotes (
          quote_id TEXT PRIMARY KEY, event_id TEXT NOT NULL, observed_at TEXT NOT NULL,
          ingested_at TEXT NOT NULL, starts_at TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS quotes_event ON quotes(event_id, observed_at);
        CREATE TABLE IF NOT EXISTS predictions (
          prediction_id TEXT PRIMARY KEY, event_id TEXT NOT NULL, model_id TEXT NOT NULL,
          generated_at TEXT NOT NULL, ingested_at TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS decisions (
          decision_id TEXT PRIMARY KEY, prediction_id TEXT NOT NULL REFERENCES predictions(prediction_id),
          quote_id TEXT REFERENCES quotes(quote_id), event_id TEXT NOT NULL,
          created_at TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS outbox (
          outbox_id TEXT PRIMARY KEY, event_id TEXT NOT NULL UNIQUE,
          decision_id TEXT NOT NULL REFERENCES decisions(decision_id), created_at TEXT NOT NULL,
          expires_at TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS dispatch_claims (
          outbox_id TEXT PRIMARY KEY REFERENCES outbox(outbox_id), claimed_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS deliveries (
          delivery_id INTEGER PRIMARY KEY AUTOINCREMENT, outbox_id TEXT NOT NULL REFERENCES outbox(outbox_id),
          attempted_at TEXT NOT NULL, success INTEGER NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settlements (
          settlement_id TEXT PRIMARY KEY, event_id TEXT NOT NULL UNIQUE,
          recorded_at TEXT NOT NULL, payload TEXT NOT NULL);
        """)
        for table in ("models", "quotes", "predictions", "decisions", "outbox", "dispatch_claims", "deliveries", "settlements"):
            for operation in ("UPDATE", "DELETE"):
                self.db.execute(
                    f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{operation.lower()} "
                    f"BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'append-only audit table'); END"
                )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def register_model(self, value: dict, now: datetime | None = None) -> dict:
        """Evidence is operator-reviewed metadata, not automatic proof of an edge."""
        now = now or utcnow()
        value = dict(value)
        model_id = nonempty(value.get("model_id"), "model_id")
        status = value.setdefault("research_status", "unproven")
        if status not in ("unproven", "prospectively_validated"):
            raise ValueError("unknown research_status")
        sha = value.get("artifact_sha256")
        if sha is not None and (not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha)):
            raise ValueError("artifact_sha256 must be lowercase SHA-256")
        if status == "prospectively_validated":
            if not sha:
                raise ValueError("validated registration requires artifact_sha256")
            evidence = value.get("evidence", {})
            for key in ("report_uri", "report_sha256", "protocol_uri", "protocol_sha256", "reviewed_by"):
                nonempty(evidence.get(key), f"evidence.{key}")
            for key in ("report_sha256", "protocol_sha256"):
                if len(evidence[key]) != 64 or any(c not in "0123456789abcdef" for c in evidence[key]):
                    raise ValueError(f"evidence.{key} must be lowercase SHA-256")
            start = parse_time(evidence["prospective_started_at"])
            end = parse_time(evidence["prospective_ended_at"])
            review = parse_time(evidence["reviewed_at"])
            frozen = parse_time(evidence["model_frozen_at"])
            if not frozen <= start < end <= review <= now:
                raise ValueError("evidence timestamps must show freeze, prospective window, then review")
            if not isinstance(evidence.get("n_events"), int) or isinstance(evidence["n_events"], bool) or evidence["n_events"] < 1:
                raise ValueError("evidence.n_events must be positive integer")
            if (end - start).total_seconds() < 90 * 86400:
                raise ValueError("promotion requires at least 90 days of forward observations")
            settled = evidence.get("n_settled_bets")
            if type(settled) is not int or settled < 1000:
                raise ValueError("promotion requires at least 1000 settled paper bets")
            if evidence["n_events"] < settled:
                raise ValueError("evidence.n_events cannot be less than n_settled_bets")
            if evidence.get("artifact_sha256") != sha:
                raise ValueError("evidence artifact must match the registered artifact")
            for key in ("forward_only", "verified_entry_quotes", "verified_prestart_closes", "immutable_predictions",
                        "fixed_analysis_checkpoints", "data_quality_passed", "frozen_model_and_policy",
                        "multiplicity_corrected"):
                if evidence.get(key) is not True:
                    raise ValueError(f"promotion requires evidence.{key}=true")
            confidence = number(evidence.get("confidence_level"), "evidence.confidence_level")
            if not 0.975 <= confidence < 1:
                raise ValueError("promotion requires corrected confidence level at least 0.975")
            if number(evidence.get("execution_net_winnings_haircut"), "execution_net_winnings_haircut") < 0.02:
                raise ValueError("promotion requires execution allowance at least 0.02")
            if number(evidence.get("roi_after_haircut_ci_lower"), "roi_after_haircut_ci_lower") <= 0:
                raise ValueError("promotion requires positive ROI lower confidence bound after haircut")
            if number(evidence.get("no_vig_close_ev_ci_lower"), "no_vig_close_ev_ci_lower") <= 0:
                raise ValueError("promotion requires positive no-vig close EV lower confidence bound")
            if number(evidence.get("paired_log_loss_delta_ci_upper"), "paired_log_loss_delta_ci_upper") >= 0:
                raise ValueError("promotion requires negative paired log-loss delta upper confidence bound")
            if evidence.get("approved_for_alerts") is not True:
                raise ValueError("validated registration requires explicit reviewed approval for alerts")
        trial = value.get("trial")
        if trial is not None:
            if not sha:
                raise ValueError("forward trial requires artifact_sha256")
            nonempty(trial.get("cohort_id"), "trial.cohort_id")
            protocol_sha = nonempty(trial.get("protocol_sha256"), "trial.protocol_sha256")
            if len(protocol_sha) != 64 or any(c not in "0123456789abcdef" for c in protocol_sha):
                raise ValueError("trial.protocol_sha256 must be lowercase SHA-256")
            if not parse_time(trial["model_frozen_at"]) <= now <= parse_time(trial["starts_at"]):
                raise ValueError("forward trial must be registered after model freeze and before trial start")
            trial["config_sha256"] = digest(self.config)
        existing = self.db.execute("SELECT payload FROM models WHERE model_id=?", (model_id,)).fetchone()
        if existing:
            if existing[0] == canonical(value):
                return {"model_id": model_id, "duplicate": True}
            raise ValueError("model_id already registered; create a new versioned model_id")
        with self.db:
            self.db.execute("INSERT INTO models VALUES (?,?,?,?,?)", (model_id, stamp(now), status, sha, canonical(value)))
        return {"model_id": model_id, "research_status": status, "duplicate": False}

    def ingest_quote(self, value: dict, now: datetime | None = None) -> dict:
        now = now or utcnow()
        value = dict(value)
        for key in ("event_id", "home_team", "away_team"):
            nonempty(value.get(key), key)
        if value["home_team"] == value["away_team"]:
            raise ValueError("teams must differ")
        for key, expected in (("sport", "MLB"), ("bookmaker", "FanDuel"), ("market", "moneyline")):
            if value.get(key) != expected:
                raise ValueError(f"{key} must be {expected}")
        if value.get("status") not in ("open", "suspended", "closed"):
            raise ValueError("status must be open, suspended or closed")
        if type(value.get("is_live")) is not bool:
            raise ValueError("is_live must be boolean")
        for key in ("decimal_home", "decimal_away"):
            value[key] = number(value.get(key), key)
            if value[key] <= 1:
                raise ValueError("decimal odds must exceed 1")
        for key in ("observed_at", "starts_at"):
            value[key] = stamp(parse_time(value[key]))
        source_info(value.get("source"))
        quote_id = digest(value)
        existing = self.db.execute("SELECT quote_id FROM quotes WHERE quote_id=?", (quote_id,)).fetchone()
        if existing:
            return {"quote_id": quote_id, "duplicate": True}
        # Prevent event identifiers being silently reused for different teams or markets.
        prior = self._latest_quote(value["event_id"])
        if prior:
            old = json.loads(prior["payload"])
            if any(old[k] != value[k] for k in ("home_team", "away_team", "bookmaker", "market", "sport")):
                raise ValueError("event identity mismatch; use a new event_id")
        with self.db:
            self.db.execute("INSERT INTO quotes VALUES (?,?,?,?,?,?)", (
                quote_id, value["event_id"], value["observed_at"], stamp(now), value["starts_at"], canonical(value)))
        return {"quote_id": quote_id, "duplicate": False}

    def _latest_quote(self, event_id: str) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM quotes WHERE event_id=? ORDER BY observed_at DESC, ingested_at DESC, rowid DESC LIMIT 1",
            (event_id,),
        ).fetchone()

    def _quote_blocks(self, quote: dict, now: datetime) -> list[str]:
        reasons = []
        age = (now - parse_time(quote["observed_at"])).total_seconds()
        if age > self.config["max_quote_age_seconds"]:
            reasons.append("stale_quote")
        if age < -self.config["max_clock_skew_seconds"]:
            reasons.append("future_quote")
        if quote["status"] != "open":
            reasons.append("market_" + quote["status"])
        if quote["is_live"]:
            reasons.append("live_market")
        if now >= parse_time(quote["starts_at"]):
            reasons.append("event_started")
        vig = 1 / quote["decimal_home"] + 1 / quote["decimal_away"] - 1
        if vig < 0 or vig > self.config["max_vig"] + 1e-12:
            reasons.append("vig_out_of_range")
        return reasons

    def predict(self, value: dict, now: datetime | None = None) -> dict:
        now = now or utcnow()
        value = dict(value)
        event_id = nonempty(value.get("event_id"), "event_id")
        nonempty(value.get("model_id"), "model_id")
        p = number(value.get("probability_home"), "probability_home")
        if not 0 < p < 1:
            raise ValueError("probability_home must be strictly between zero and one")
        generated = parse_time(value["generated_at"])
        cutoff = parse_time(value["feature_cutoff_at"])
        if cutoff > generated:
            raise ValueError("feature_cutoff_at cannot follow generated_at")
        value["generated_at"], value["feature_cutoff_at"] = stamp(generated), stamp(cutoff)
        prediction_id = digest(value)
        old = self.db.execute("SELECT payload FROM decisions WHERE prediction_id=? ORDER BY rowid LIMIT 1", (prediction_id,)).fetchone()
        if old:
            return {**json.loads(old[0]), "duplicate": True}
        row = self._latest_quote(event_id)
        reasons = []
        age = (now - generated).total_seconds()
        if age > self.config["max_prediction_age_seconds"]:
            reasons.append("stale_prediction")
        if age < -self.config["max_clock_skew_seconds"]:
            reasons.append("future_prediction")
        quote = json.loads(row["payload"]) if row else None
        if quote is None:
            reasons.append("no_quote_feed")
        else:
            reasons.extend(self._quote_blocks(quote, now))
            if value.get("market_quote_id") is not None and value["market_quote_id"] != row["quote_id"]:
                reasons.append("prediction_quote_mismatch")
            if generated >= parse_time(quote["starts_at"]):
                reasons.append("prediction_after_start")
        if self.db.execute("SELECT 1 FROM outbox WHERE event_id=?", (event_id,)).fetchone():
            reasons.append("event_already_signaled")
        if self.db.execute("SELECT 1 FROM settlements WHERE event_id=?", (event_id,)).fetchone():
            reasons.append("event_already_settled")
        model = self.db.execute("SELECT * FROM models WHERE model_id=?", (value["model_id"],)).fetchone()
        registration = json.loads(model["payload"]) if model else {}
        if (registration.get("market_conditioned") is True or
                registration.get("baseline") == "paired_fanduel_no_vig_moneyline") and not value.get("market_quote_id"):
            reasons.append("market_conditioned_prediction_requires_quote_id")
        validated = bool(model and model["research_status"] == "prospectively_validated" and
                         value.get("artifact_sha256") == model["artifact_sha256"])
        if validated and generated < parse_time(model["registered_at"]):
            validated = False
        evidence_blocks = []
        if not validated:
            evidence_blocks.append("model_not_prospectively_validated")
        if quote and not quote["source"]["verified"]:
            evidence_blocks.append("quote_not_verified")
        result = {
            "prediction_id": prediction_id, "event_id": event_id,
            "model_id": value["model_id"], "artifact_sha256": value.get("artifact_sha256"),
            "cohort_id": value.get("cohort_id"), "created_at": stamp(now),
            "quote_id": row["quote_id"] if row else None,
            "probability_home": p, "reasons": reasons, "evidence_blocks": evidence_blocks,
            "kind": "BLOCKED", "duplicate": False,
            "config_sha256": digest(self.config), "config": dict(self.config),
        }
        if quote:
            home_ev, away_ev = p * quote["decimal_home"] - 1, (1 - p) * quote["decimal_away"] - 1
            side = "home" if home_ev >= away_ev else "away"
            side_p = p if side == "home" else 1 - p
            price = quote["decimal_" + side]
            fair_home = (1 / quote["decimal_home"]) / (1 / quote["decimal_home"] + 1 / quote["decimal_away"])
            result.update(bookmaker=quote["bookmaker"], market=quote["market"], sport=quote["sport"],
                          home_team=quote["home_team"], away_team=quote["away_team"], source=quote["source"],
                          side=side, probability=side_p, decimal_odds=price,
                          expected_value=side_p * price - 1, market_probability_home=fair_home,
                          starts_at=quote["starts_at"], quote_observed_at=quote["observed_at"])
            if not self.config["min_decimal_odds"] <= price <= self.config["max_decimal_odds"]:
                reasons.append("odds_out_of_range")
            if result["expected_value"] < self.config["min_expected_value"] - 1e-12:
                reasons.append("edge_below_threshold")
            if not reasons:
                result["kind"] = "PAPER" if evidence_blocks else "ALERT_CANDIDATE"
                expiry = min(now + timedelta(seconds=self.config["quote_expiry_seconds"]),
                             parse_time(quote["observed_at"]) + timedelta(seconds=self.config["max_quote_age_seconds"]),
                             parse_time(quote["starts_at"]))
                result["expires_at"] = stamp(expiry)
        eligibility_reasons = []
        if not quote or not quote["source"]["verified"]:
            eligibility_reasons.append("unverified_entry")
        if quote and (quote["source"].get("synthetic") or quote["source"].get("historical")):
            eligibility_reasons.append("synthetic_or_historical_source")
        trial = registration.get("trial") or {}
        if not model or not trial:
            eligibility_reasons.append("forward_trial_not_registered")
        else:
            if value.get("artifact_sha256") != model["artifact_sha256"]:
                eligibility_reasons.append("artifact_mismatch")
            if value.get("cohort_id") != trial["cohort_id"]:
                eligibility_reasons.append("cohort_mismatch")
            if generated < parse_time(trial["starts_at"]) or generated < parse_time(model["registered_at"]):
                eligibility_reasons.append("forecast_precedes_trial")
            if trial["config_sha256"] != digest(self.config):
                eligibility_reasons.append("trial_policy_changed")
        if result["kind"] == "BLOCKED":
            eligibility_reasons.append("decision_blocked")
        result["forward_eligible"] = not eligibility_reasons
        result["eligibility_reasons"] = eligibility_reasons
        decision_id = digest(result)
        result["decision_id"] = decision_id
        # One transaction and a UNIQUE outbox event_id prevent concurrent duplicate signals.
        with self.db:
            self.db.execute("INSERT INTO predictions VALUES (?,?,?,?,?,?)", (
                prediction_id, event_id, value["model_id"], stamp(generated), stamp(now), canonical(value)))
            self.db.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?)", (
                decision_id, prediction_id, result["quote_id"], event_id, stamp(now), result["kind"], canonical(result)))
            if result["kind"] in ("PAPER", "ALERT_CANDIDATE"):
                self.db.execute("INSERT INTO outbox VALUES (?,?,?,?,?,?,?)", (
                    digest({"decision_id": decision_id}), event_id, decision_id,
                    stamp(now), result["expires_at"], result["kind"], canonical(result)))
        return result

    def pending(self, now: datetime | None = None) -> list[dict]:
        """Return deliverable snapshots; retain expired/repriced records in the audit DB."""
        now = now or utcnow()
        pending = []
        for row in self.db.execute("SELECT * FROM outbox ORDER BY created_at, rowid"):
            if parse_time(row["expires_at"]) <= now:
                continue
            if self.db.execute("SELECT 1 FROM dispatch_claims WHERE outbox_id=?", (row["outbox_id"],)).fetchone():
                continue
            value = json.loads(row["payload"])
            current = self._latest_quote(row["event_id"])
            if current is None:
                continue
            quote = json.loads(current["payload"])
            entry = json.loads(self.db.execute("SELECT payload FROM quotes WHERE quote_id=?", (value["quote_id"],)).fetchone()[0])
            if self._quote_blocks(quote, now):
                continue
            # Any change to price, event time, or verification invalidates the old notification.
            if any(quote[k] != entry[k] for k in ("decimal_home", "decimal_away", "starts_at")):
                continue
            revisions = self.db.execute(
                "SELECT payload FROM quotes WHERE event_id=? AND rowid > (SELECT rowid FROM quotes WHERE quote_id=?)",
                (row["event_id"], value["quote_id"]),
            ).fetchall()
            if any(any(json.loads(revision[0])[key] != entry[key] for key in
                       ("decimal_home", "decimal_away", "starts_at", "status", "is_live")) for revision in revisions):
                continue
            if value["kind"] == "ALERT_CANDIDATE" and (
                    not quote["source"]["verified"] or
                    any(not json.loads(revision[0])["source"]["verified"] for revision in revisions)):
                continue
            pending.append({"outbox_id": row["outbox_id"], **value})
        return pending

    def dispatch(self, execute: bool = False, now: datetime | None = None) -> list[dict]:
        fixed_clock = now is not None
        now = now or utcnow()
        pending = self.pending(now)
        if not execute:
            return pending
        if not self.config["webhook_enabled"]:
            raise ValueError("webhook_enabled is false; only dry-run notifications are configured")
        url = os.environ.get("BETTING_ALERT_WEBHOOK_URL", "")
        if not url.startswith("https://"):
            raise ValueError("set an HTTPS BETTING_ALERT_WEBHOOK_URL; URL never belongs in config or git")
        results = []
        for item in pending:
            if item["kind"] != "ALERT_CANDIDATE":
                continue
            current_time = now if fixed_clock else utcnow()
            if item["outbox_id"] not in {p["outbox_id"] for p in self.pending(current_time)}:
                continue
            try:
                with self.db:
                    self.db.execute("INSERT INTO dispatch_claims VALUES (?,?)", (item["outbox_id"], stamp(current_time)))
            except sqlite3.IntegrityError:
                continue  # Another worker claimed this exact notification.
            request = Request(url, data=canonical(item).encode(), method="POST", headers={
                "Content-Type": "application/json", "Idempotency-Key": item["outbox_id"]})
            success = False
            try:
                with urlopen(request, timeout=10) as response:
                    status = response.status
                    success = 200 <= status < 300
                delivery = {"http_status": status}
            except Exception as exc:
                # Do not leak credential-bearing webhook URLs through exception messages.
                delivery = {"error_type": type(exc).__name__}
            delivery.update(outbox_id=item["outbox_id"], success=success)
            with self.db:
                self.db.execute("INSERT INTO deliveries(outbox_id,attempted_at,success,payload) VALUES (?,?,?,?)", (
                    item["outbox_id"], stamp(current_time), int(success), canonical(delivery)))
            results.append(delivery)
        return results

    def settle(self, value: dict, now: datetime | None = None) -> dict:
        now = now or utcnow()
        value = dict(value)
        event_id = nonempty(value.get("event_id"), "event_id")
        if value.get("status") not in ("final", "void"):
            raise ValueError("settlement status must be final or void")
        if value["status"] == "final" and type(value.get("home_won")) is not bool:
            raise ValueError("final settlement needs boolean home_won")
        if value["status"] == "void":
            value["home_won"] = None
        source_info(value.get("source"))
        if not value["source"]["verified"]:
            raise ValueError("settlement source must be verified")
        value["settled_at"] = stamp(parse_time(value["settled_at"]))
        if parse_time(value["settled_at"]) > now:
            raise ValueError("settlement cannot be in the future")
        quote = self._latest_quote(event_id)
        if quote and parse_time(value["settled_at"]) < parse_time(quote["starts_at"]):
            raise ValueError("settlement precedes event start")
        settlement_id = digest(value)
        old = self.db.execute("SELECT settlement_id FROM settlements WHERE event_id=?", (event_id,)).fetchone()
        if old:
            if old[0] == settlement_id:
                return {"settlement_id": settlement_id, "duplicate": True}
            raise ValueError("event already settled; conflicting settlements require audited operator review")
        with self.db:
            self.db.execute("INSERT INTO settlements VALUES (?,?,?,?)", (settlement_id, event_id, stamp(now), canonical(value)))
        return {"settlement_id": settlement_id, "duplicate": False}

    def _closing_quote(self, event_id: str, entry: dict, now: datetime) -> dict | None:
        start = parse_time(entry["starts_at"])
        if now < start:
            return None
        for row in self.db.execute("SELECT * FROM quotes WHERE event_id=? ORDER BY observed_at DESC, ingested_at DESC, rowid DESC", (event_id,)):
            q = json.loads(row["payload"])
            observed, ingested = parse_time(q["observed_at"]), parse_time(row["ingested_at"])
            if q["bookmaker"] != "FanDuel" or not q["source"]["verified"] or q["is_live"] or q["status"] != "open":
                continue
            if q["starts_at"] != entry["starts_at"]:
                continue
            # Backfilled historical snapshots do not become verified prospective closing prices.
            if not start - timedelta(seconds=self.config["close_window_seconds"]) <= observed < start:
                continue
            if ingested >= start or not -self.config["max_clock_skew_seconds"] <= (ingested - observed).total_seconds() <= self.config["max_quote_age_seconds"]:
                continue
            if self._quote_blocks(q, observed):
                continue
            return {**q, "quote_id": row["quote_id"]}
        return None

    def forecast_report(self, now: datetime | None = None) -> dict:
        """First eligible captured forecast per model/artifact/event, regardless of EV."""
        now = now or utcnow()
        selected = {}
        query = """SELECT d.payload AS decision, p.payload AS prediction, p.ingested_at AS captured_at,
                          q.payload AS quote, q.ingested_at AS quote_captured_at
                   FROM decisions d JOIN predictions p USING(prediction_id)
                   JOIN quotes q USING(quote_id)
                   ORDER BY p.ingested_at, p.rowid"""
        for row in self.db.execute(query):
            decision, prediction, quote = (json.loads(row[k]) for k in ("decision", "prediction", "quote"))
            # Bet selection cannot change the probability-scoring population.
            selection_only = {"edge_below_threshold", "odds_out_of_range", "event_already_signaled", "vig_out_of_range"}
            if set(decision["reasons"]) - selection_only:
                continue
            implied_sum = 1 / quote["decimal_home"] + 1 / quote["decimal_away"]
            if not 1.0 <= implied_sum <= 1.25:
                continue
            start, capture = parse_time(quote["starts_at"]), parse_time(row["captured_at"])
            generated = parse_time(prediction["generated_at"])
            quote_capture = parse_time(row["quote_captured_at"])
            if not generated < start or not capture < start or capture > now:
                continue
            if quote_capture > capture or quote_capture >= start:
                continue
            if parse_time(quote["observed_at"]) > generated + timedelta(seconds=self.config["max_clock_skew_seconds"]):
                continue
            key = (prediction["model_id"], prediction.get("artifact_sha256"), prediction["event_id"])
            if key in selected:
                continue
            source = quote["source"]
            source_class = ("synthetic" if source.get("synthetic") else "historical" if source.get("historical") else
                            "verified" if source["verified"] else "aggregator_observational")
            eligible = not (set(decision["eligibility_reasons"]) - {"decision_blocked"})
            result = {"model_id": key[0], "artifact_sha256": key[1], "event_id": key[2],
                      "cohort_id": prediction.get("cohort_id"), "source_class": source_class,
                      "registered_forward_eligible": eligible,
                      "prediction_id": decision["prediction_id"], "quote_id": decision["quote_id"],
                      "generated_at": prediction["generated_at"], "captured_at": row["captured_at"],
                      "quote_observed_at": quote["observed_at"], "status": "pending",
                      "probability_home": decision["probability_home"],
                      "market_probability_home": decision["market_probability_home"]}
            settlement = self.db.execute("SELECT payload FROM settlements WHERE event_id=?", (key[2],)).fetchone()
            if settlement:
                settled = json.loads(settlement[0])
                if parse_time(settled["settled_at"]) <= now:
                    result["status"] = settled["status"]
                    if settled["status"] == "final":
                        y = int(settled["home_won"])
                        p, m = result["probability_home"], result["market_probability_home"]
                        model_loss, market_loss = -math.log(p if y else 1 - p), -math.log(m if y else 1 - m)
                        result.update(home_won=bool(y), model_log_loss=model_loss, market_log_loss=market_loss,
                                      paired_log_loss_delta=model_loss - market_loss,
                                      model_brier=(p - y) ** 2, market_brier=(m - y) ** 2)
            selected[key] = result
        groups = {}
        for event in selected.values():
            key = (event["model_id"], event["artifact_sha256"], event["cohort_id"],
                   event["source_class"], event["registered_forward_eligible"])
            groups.setdefault(key, []).append(event)
        cohorts = []
        for key, events in groups.items():
            graded = [event for event in events if event["status"] == "final"]
            means = {"mean_" + field: sum(event[field] for event in graded) / len(graded) if graded else None
                     for field in ("model_log_loss", "market_log_loss", "paired_log_loss_delta", "model_brier", "market_brier")}
            cohorts.append({"model_id": key[0], "artifact_sha256": key[1], "cohort_id": key[2],
                            "source_class": key[3], "registered_forward_eligible": key[4],
                            "forecasts": len(events), "graded_forecasts": len(graded), **means})
        return {"selection": "earliest eligible captured prestart forecast per model/artifact/event; ignores bet EV/selected-price/dedup policy; paired implied sum 1.00 through 1.25",
                "promotion": "none; descriptive observational results only",
                "cohorts": cohorts, "events": list(selected.values())}

    def report(self, now: datetime | None = None) -> dict:
        now = now or utcnow()
        rows = []
        for out in self.db.execute("SELECT payload FROM outbox ORDER BY created_at, rowid"):
            entry = json.loads(out[0])
            settled = self.db.execute("SELECT payload FROM settlements WHERE event_id=?", (entry["event_id"],)).fetchone()
            if not settled:
                continue
            settlement = json.loads(settled[0])
            record = {"event_id": entry["event_id"], "kind": entry["kind"], "side": entry["side"],
                      "model_id": entry["model_id"], "artifact_sha256": entry.get("artifact_sha256"),
                      "cohort_id": entry.get("cohort_id"), "forward_eligible": entry["forward_eligible"],
                      "eligibility_reasons": entry["eligibility_reasons"],
                      "entry_decimal": entry["decimal_odds"], "status": settlement["status"],
                      "hypothetical_profit_units": 0.0}
            if settlement["status"] == "final":
                y = int(settlement["home_won"])
                won = bool(y) if entry["side"] == "home" else not bool(y)
                p, m = entry["probability_home"], entry["market_probability_home"]
                record.update(home_won=bool(y), hypothetical_profit_units=entry["decimal_odds"] - 1 if won else -1,
                              model_log_loss=-math.log(p if y else 1 - p),
                              market_log_loss=-math.log(m if y else 1 - m))
            closing = self._closing_quote(entry["event_id"], entry, now)
            record.update(closing_quote_id=None, signed_probability_clv=None, price_clv=None, no_vig_close_ev=None)
            if closing:
                fair_home = (1 / closing["decimal_home"]) / (1 / closing["decimal_home"] + 1 / closing["decimal_away"])
                closing_fair = fair_home if entry["side"] == "home" else 1 - fair_home
                entry_fair = entry["market_probability_home"] if entry["side"] == "home" else 1 - entry["market_probability_home"]
                record.update(closing_quote_id=closing["quote_id"],
                              signed_probability_clv=closing_fair - entry_fair,
                              price_clv=entry["decimal_odds"] / closing["decimal_" + entry["side"]] - 1,
                              no_vig_close_ev=entry["decimal_odds"] * closing_fair - 1)
            rows.append(record)
        grouped = {}
        for row in rows:
            key = (row["model_id"], row["artifact_sha256"], row["cohort_id"], row["forward_eligible"])
            grouped.setdefault(key, []).append(row)
        cohorts = []
        mean = lambda field, data: sum(r[field] for r in data) / len(data) if data else None
        for (model_id, artifact, cohort_id, eligible), group in grouped.items():
            finals = [r for r in group if r["status"] == "final"]
            clv = [r for r in finals if r["closing_quote_id"]]
            cohorts.append({"model_id": model_id, "artifact_sha256": artifact, "cohort_id": cohort_id,
                            "forward_eligible": eligible,
                            "use": "registered forward trial" if eligible else "excluded from forward evidence",
                            "settled_signals": len(group), "graded_signals": len(finals), "clv_signals": len(clv),
                            "hypothetical_roi": mean("hypothetical_profit_units", finals),
                            "mean_model_log_loss": mean("model_log_loss", finals),
                            "mean_market_log_loss": mean("market_log_loss", finals),
                            "mean_signed_probability_clv": mean("signed_probability_clv", clv),
                            "mean_price_clv": mean("price_clv", clv),
                            "mean_no_vig_close_ev": mean("no_vig_close_ev", clv)})
        return {"assessment": "paper results are hypothetical; historical fit and small samples do not prove an edge",
                "scope": "selected signals only; full-universe model evaluation is separate; model cohorts are never pooled",
                "settled_signals": len(rows), "cohorts": cohorts, "events": rows,
                "all_forecasts": self.forecast_report(now)}



def read_json(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/monitor.sqlite3")
    parser.add_argument("--config")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    for name in ("ingest", "register-model", "predict", "settle"):
        command = sub.add_parser(name)
        command.add_argument("input", help="JSON object or array; no network feed is implied")
    sub.add_parser("report")
    outbox = sub.add_parser("outbox")
    outbox.add_argument("--send-webhook", action="store_true", help="explicitly send validated alert candidates only")
    args = parser.parse_args(argv)
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    monitor = Monitor(args.db, read_json(args.config) if args.config else None)
    try:
        if args.command == "init":
            output = {"database": args.db, "status": "initialized", "live_feed": "unavailable; supply a normalized feed"}
        elif args.command == "report":
            output = monitor.report()
        elif args.command == "outbox":
            output = monitor.dispatch(execute=args.send_webhook)
        else:
            operation = {"ingest": monitor.ingest_quote, "register-model": monitor.register_model,
                         "predict": monitor.predict, "settle": monitor.settle}[args.command]
            data = read_json(args.input)
            output = [operation(item) for item in data] if isinstance(data, list) else operation(data)
        print(json.dumps(output, indent=2, allow_nan=False))
        return 0
    except (ValueError, KeyError, sqlite3.IntegrityError) as exc:
        parser.exit(2, f"monitor: {exc}\n")
    finally:
        monitor.close()


if __name__ == "__main__":
    raise SystemExit(main())
