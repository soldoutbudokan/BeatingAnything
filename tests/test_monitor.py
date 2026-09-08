"""Contract and failure-mode tests; synthetic prices are never market evidence."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from beating.monitor import Monitor, stamp


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.monitor = Monitor(Path(self.tmp.name) / "monitor.sqlite3")
        self.now = datetime(2026, 9, 8, 18, tzinfo=timezone.utc)

    def tearDown(self):
        self.monitor.close()
        self.tmp.cleanup()

    def quote(self, **updates):
        result = {
            "event_id": "TEST-ONLY-001", "sport": "MLB", "bookmaker": "FanDuel", "market": "moneyline",
            "home_team": "Test Home", "away_team": "Test Away", "starts_at": stamp(self.now + timedelta(hours=2)),
            "observed_at": stamp(self.now), "status": "open", "is_live": False,
            "decimal_home": 1.91, "decimal_away": 1.91,
            "source": {"uri": "test://quotes", "provider": "unit-test fixture", "verified": False, "synthetic": True},
        }
        result.update(updates)
        return result

    def verified_source(self):
        # Only exercises gate behavior. This is not an actual FanDuel verification.
        return {"uri": "test://gate-assertion", "provider": "unit-test", "verified": True,
                "verification_method": "mock for a unit test only"}

    def prediction(self, **updates):
        result = {"event_id": "TEST-ONLY-001", "model_id": "unproven-test-v1", "probability_home": 0.60,
                  "generated_at": stamp(self.now), "feature_cutoff_at": stamp(self.now)}
        result.update(updates)
        return result

    def register_validated_fixture(self):
        self.monitor.register_model({
            "model_id": "reviewed-test-v1", "research_status": "prospectively_validated", "artifact_sha256": "a" * 64,
            "evidence": {"report_uri": "test://report", "report_sha256": "b" * 64,
                         "protocol_uri": "test://protocol", "protocol_sha256": "c" * 64,
                         "reviewed_by": "unit-test", "model_frozen_at": "2025-12-01T00:00:00Z",
                         "prospective_started_at": "2026-01-01T00:00:00Z",
                         "prospective_ended_at": "2026-07-01T00:00:00Z",
                         "reviewed_at": "2026-07-02T00:00:00Z", "n_events": 1000,
                         "approved_for_alerts": True, "n_settled_bets": 1000, "artifact_sha256": "a" * 64,
                         "forward_only": True, "verified_entry_quotes": True, "verified_prestart_closes": True,
                         "immutable_predictions": True, "fixed_analysis_checkpoints": True,
                         "data_quality_passed": True, "frozen_model_and_policy": True,
                         "multiplicity_corrected": True, "confidence_level": 0.975,
                         "execution_net_winnings_haircut": 0.02, "roi_after_haircut_ci_lower": 0.01,
                         "no_vig_close_ev_ci_lower": 0.01, "paired_log_loss_delta_ci_upper": -0.001},
        }, self.now - timedelta(days=1))

    def test_unproven_and_unverified_is_explicitly_paper(self):
        self.monitor.ingest_quote(self.quote(), self.now)
        result = self.monitor.predict(self.prediction(), self.now)
        self.assertEqual(result["kind"], "PAPER")
        self.assertIn("model_not_prospectively_validated", result["evidence_blocks"])
        self.assertIn("quote_not_verified", result["evidence_blocks"])
        self.assertAlmostEqual(result["expected_value"], 0.146)
        self.assertEqual(len(self.monitor.dispatch(now=self.now)), 1)

    def test_missing_feed_fails_closed(self):
        result = self.monitor.predict(self.prediction(), self.now)
        self.assertEqual(result["kind"], "BLOCKED")
        self.assertIn("no_quote_feed", result["reasons"])
        self.assertEqual(self.monitor.pending(self.now), [])

    def test_freshness_status_and_price_gates(self):
        examples = [
            ({"observed_at": stamp(self.now - timedelta(seconds=91))}, "stale_quote"),
            ({"observed_at": stamp(self.now + timedelta(seconds=6))}, "future_quote"),
            ({"status": "suspended"}, "market_suspended"),
            ({"status": "closed"}, "market_closed"),
            ({"is_live": True}, "live_market"),
            ({"starts_at": stamp(self.now)}, "event_started"),
            ({"decimal_home": 1.3, "decimal_away": 1.3}, "vig_out_of_range"),
            ({"decimal_home": 1.1, "decimal_away": 6.1}, "odds_out_of_range"),
            ({"decimal_home": 2.1, "decimal_away": 2.1}, "vig_out_of_range"),
        ]
        for index, (changes, reason) in enumerate(examples):
            with self.subTest(reason=reason):
                event = f"event-{index}"
                self.monitor.ingest_quote(self.quote(event_id=event, **changes), self.now)
                result = self.monitor.predict(self.prediction(event_id=event), self.now)
                self.assertEqual(result["kind"], "BLOCKED")
                self.assertIn(reason, result["reasons"])

    def test_prediction_timing_gates(self):
        self.monitor.ingest_quote(self.quote(), self.now)
        result = self.monitor.predict(self.prediction(generated_at=stamp(self.now - timedelta(seconds=901)),
                                     feature_cutoff_at=stamp(self.now - timedelta(seconds=901))), self.now)
        self.assertIn("stale_prediction", result["reasons"])
        future = self.now + timedelta(seconds=6)
        result = self.monitor.predict(self.prediction(generated_at=stamp(future)), self.now)
        self.assertIn("future_prediction", result["reasons"])
        with self.assertRaisesRegex(ValueError, "feature_cutoff_at"):
            self.monitor.predict(self.prediction(feature_cutoff_at=stamp(future)), self.now)

    def test_self_asserted_validated_prediction_cannot_bypass_registry(self):
        self.monitor.ingest_quote(self.quote(source=self.verified_source()), self.now)
        result = self.monitor.predict(self.prediction(research_status="prospectively_validated"), self.now)
        self.assertEqual(result["kind"], "PAPER")

    def test_validated_gate_requires_matching_artifact_and_verified_quote(self):
        self.register_validated_fixture()
        self.monitor.ingest_quote(self.quote(source=self.verified_source()), self.now)
        result = self.monitor.predict(self.prediction(model_id="reviewed-test-v1", artifact_sha256="a" * 64), self.now)
        self.assertEqual(result["kind"], "ALERT_CANDIDATE")
        self.assertEqual(result["evidence_blocks"], [])
        with self.assertRaisesRegex(ValueError, "webhook_enabled"):
            self.monitor.dispatch(execute=True, now=self.now)

    def test_model_registration_rejects_bad_chronology_and_changes(self):
        self.monitor.register_model({"model_id": "fixed"}, self.now)
        with self.assertRaisesRegex(ValueError, "already registered"):
            self.monitor.register_model({"model_id": "fixed", "artifact_sha256": "d" * 64}, self.now)
        with self.assertRaisesRegex(ValueError, "artifact_sha256"):
            self.monitor.register_model({"model_id": "invalid", "research_status": "prospectively_validated"}, self.now)
        self.register_validated_fixture()
        payload = json.loads(self.monitor.db.execute("SELECT payload FROM models WHERE model_id='reviewed-test-v1'").fetchone()[0])
        payload["model_id"] = "bad-window"
        payload["evidence"]["model_frozen_at"] = "2026-05-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "freeze"):
            self.monitor.register_model(payload, self.now)

    def test_quote_and_signal_deduplication(self):
        first = self.monitor.ingest_quote(self.quote(), self.now)
        second = self.monitor.ingest_quote(self.quote(), self.now)
        self.assertEqual(first["quote_id"], second["quote_id"])
        self.assertTrue(second["duplicate"])
        result = self.monitor.predict(self.prediction(), self.now)
        duplicate = self.monitor.predict(self.prediction(), self.now)
        self.assertEqual(result["decision_id"], duplicate["decision_id"])
        self.assertTrue(duplicate["duplicate"])
        another = self.monitor.predict(self.prediction(probability_home=0.65), self.now)
        self.assertIn("event_already_signaled", another["reasons"])
        self.assertEqual(self.monitor.db.execute("SELECT count(*) FROM outbox").fetchone()[0], 1)

    def test_repriced_market_cannot_reuse_old_notification_even_if_reverted(self):
        self.monitor.ingest_quote(self.quote(), self.now)
        self.monitor.predict(self.prediction(), self.now)
        later = self.now + timedelta(seconds=10)
        self.monitor.ingest_quote(self.quote(decimal_home=1.85, decimal_away=2.0, observed_at=stamp(later)), later)
        self.assertEqual(self.monitor.pending(later), [])
        later += timedelta(seconds=10)
        self.monitor.ingest_quote(self.quote(observed_at=stamp(later)), later)
        self.assertEqual(self.monitor.pending(later), [])
        self.assertEqual(self.monitor.db.execute("SELECT count(*) FROM outbox").fetchone()[0], 1)

    def test_notification_expiry_and_heartbeat(self):
        self.monitor.ingest_quote(self.quote(), self.now)
        self.monitor.predict(self.prediction(), self.now)
        later = self.now + timedelta(seconds=20)
        self.monitor.ingest_quote(self.quote(observed_at=stamp(later)), later)
        self.assertEqual(len(self.monitor.pending(later)), 1)
        self.assertEqual(self.monitor.pending(self.now + timedelta(seconds=60)), [])

    def test_market_conditioned_predictions_bind_the_quote(self):
        self.monitor.ingest_quote(self.quote(), self.now)
        result = self.monitor.predict(self.prediction(market_quote_id="wrong-quote"), self.now)
        self.assertIn("prediction_quote_mismatch", result["reasons"])
        self.assertEqual(result["kind"], "BLOCKED")

    def test_append_only_and_schema_validation(self):
        self.monitor.ingest_quote(self.quote(), self.now)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
            self.monitor.db.execute("DELETE FROM quotes")
        for bad in (float("nan"), float("inf"), True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.monitor.ingest_quote(self.quote(decimal_home=bad), self.now)
        with self.assertRaises(ValueError):
            self.monitor.ingest_quote(self.quote(is_live="false"), self.now)
        with self.assertRaises(ValueError):
            self.monitor.ingest_quote(self.quote(observed_at="2026-09-08T18:00:00"), self.now)
        with self.assertRaisesRegex(ValueError, "event identity"):
            self.monitor.ingest_quote(self.quote(home_team="Different Home"), self.now)
        with self.assertRaisesRegex(ValueError, "synthetic/historical"):
            self.monitor.ingest_quote(self.quote(source={**self.verified_source(), "synthetic": True}), self.now)

    def add_settlement(self, **updates):
        settlement = {"event_id": "TEST-ONLY-001", "status": "final", "home_won": True,
                      "settled_at": stamp(self.now + timedelta(hours=5)), "source": self.verified_source()}
        settlement.update(updates)
        return self.monitor.settle(settlement, self.now + timedelta(hours=6))

    def test_report_uses_verified_fresh_prestart_same_book_close(self):
        self.monitor.ingest_quote(self.quote(source=self.verified_source()), self.now)
        self.monitor.predict(self.prediction(), self.now)
        close_time = self.now + timedelta(hours=2) - timedelta(seconds=30)
        close = self.quote(observed_at=stamp(close_time), decimal_home=1.80, decimal_away=2.08, source=self.verified_source())
        closing = self.monitor.ingest_quote(close, close_time)
        self.add_settlement()
        result = self.monitor.report(self.now + timedelta(hours=6))
        self.assertEqual(result["cohorts"][0]["clv_signals"], 1)
        self.assertEqual(result["events"][0]["closing_quote_id"], closing["quote_id"])
        cohort = result["cohorts"][0]
        self.assertAlmostEqual(cohort["hypothetical_roi"], 0.91)
        self.assertAlmostEqual(cohort["mean_price_clv"], 1.91 / 1.80 - 1)
        self.assertAlmostEqual(cohort["mean_signed_probability_clv"], (1 / 1.80) / (1 / 1.80 + 1 / 2.08) - 0.5)
        self.assertAlmostEqual(cohort["mean_no_vig_close_ev"], 1.91 * (1 / 1.80) / (1 / 1.80 + 1 / 2.08) - 1)
        self.assertLess(cohort["mean_model_log_loss"], cohort["mean_market_log_loss"])

    def test_backfilled_or_unverified_close_cannot_create_clv(self):
        self.monitor.ingest_quote(self.quote(), self.now)
        self.monitor.predict(self.prediction(), self.now)
        close_time = self.now + timedelta(hours=2) - timedelta(seconds=30)
        self.monitor.ingest_quote(self.quote(observed_at=stamp(close_time)), close_time)
        after_start = self.now + timedelta(hours=3)
        self.monitor.ingest_quote(self.quote(observed_at=stamp(close_time), source=self.verified_source()), after_start)
        self.add_settlement()
        result = self.monitor.report(self.now + timedelta(hours=6))
        self.assertEqual(result["cohorts"][0]["clv_signals"], 0)
        self.assertIsNone(result["cohorts"][0]["mean_price_clv"])

    def test_away_side_clv_sign_and_void_handling(self):
        self.monitor.ingest_quote(self.quote(source=self.verified_source()), self.now)
        self.monitor.predict(self.prediction(probability_home=0.4), self.now)
        close_time = self.now + timedelta(hours=2) - timedelta(seconds=30)
        self.monitor.ingest_quote(self.quote(observed_at=stamp(close_time), decimal_home=2.08, decimal_away=1.8,
                                           source=self.verified_source()), close_time)
        self.add_settlement(home_won=False)
        report = self.monitor.report(self.now + timedelta(hours=6))
        self.assertGreater(report["cohorts"][0]["mean_signed_probability_clv"], 0)
        self.assertGreater(report["cohorts"][0]["mean_price_clv"], 0)
        with self.assertRaisesRegex(ValueError, "already settled"):
            self.add_settlement(home_won=True)
        self.monitor.ingest_quote(self.quote(event_id="void-event"), self.now)
        self.monitor.predict(self.prediction(event_id="void-event"), self.now)
        self.add_settlement(event_id="void-event", status="void")
        report = self.monitor.report(self.now + timedelta(hours=6))
        self.assertEqual(report["settled_signals"], 2)
        self.assertEqual(report["cohorts"][0]["graded_signals"], 1)

    def test_paper_cannot_send_webhook_even_when_configured(self):
        self.monitor.config["webhook_enabled"] = True
        self.monitor.ingest_quote(self.quote(), self.now)
        self.monitor.predict(self.prediction(), self.now)
        with patch.dict("os.environ", {"BETTING_ALERT_WEBHOOK_URL": "https://example.invalid/webhook"}), \
                patch("beating.monitor.urlopen") as network:
            self.assertEqual(self.monitor.dispatch(execute=True, now=self.now), [])
            network.assert_not_called()

    def test_config_cannot_relax_required_risk_and_freshness_gates(self):
        for config in ({"min_expected_value": 0.01}, {"max_vig": 0.1}, {"max_quote_age_seconds": 900},
                       {"quote_expiry_seconds": 300}, {"min_decimal_odds": 1.01}, {"max_decimal_odds": 8}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                Monitor(":memory:", config)

    def test_promotion_rejects_insufficient_or_nonpositive_evidence(self):
        self.register_validated_fixture()
        payload = json.loads(self.monitor.db.execute("SELECT payload FROM models WHERE model_id='reviewed-test-v1'").fetchone()[0])
        cases = [
            ("n_events", 1), ("n_settled_bets", 999), ("prospective_started_at", "2026-06-01T00:00:00Z"),
            ("roi_after_haircut_ci_lower", 0.0), ("no_vig_close_ev_ci_lower", -0.001),
            ("paired_log_loss_delta_ci_upper", 0.0), ("confidence_level", 0.95),
            ("execution_net_winnings_haircut", 0.01), ("forward_only", False),
            ("verified_entry_quotes", False), ("verified_prestart_closes", False),
            ("immutable_predictions", False), ("fixed_analysis_checkpoints", False),
            ("data_quality_passed", False), ("frozen_model_and_policy", False),
            ("multiplicity_corrected", False), ("artifact_sha256", "f" * 64),
        ]
        for index, (key, value) in enumerate(cases):
            with self.subTest(key=key):
                candidate = json.loads(json.dumps(payload))
                candidate["model_id"] = f"bad-promotion-{index}"
                candidate["evidence"][key] = value
                with self.assertRaises(ValueError):
                    self.monitor.register_model(candidate, self.now)

    def test_selected_side_odds_bounds_allow_short_unselected_favorite(self):
        # Selected 5.00 remains eligible when the opposite unselected price is 1.19.
        self.monitor.ingest_quote(self.quote(decimal_home=1.19, decimal_away=5.00), self.now)
        result = self.monitor.predict(self.prediction(probability_home=0.75), self.now)
        self.assertEqual(result["kind"], "PAPER")
        self.assertEqual(result["side"], "away")
        self.assertNotIn("odds_out_of_range", result["reasons"])

    def test_forward_cohorts_require_registration_and_are_not_pooled(self):
        self.monitor.register_model({
            "model_id": "forward-test-v1", "artifact_sha256": "e" * 64,
            "trial": {"cohort_id": "frozen-cohort", "protocol_sha256": "f" * 64,
                      "model_frozen_at": stamp(self.now - timedelta(hours=1)), "starts_at": stamp(self.now)},
        }, self.now - timedelta(minutes=30))
        self.monitor.ingest_quote(self.quote(source=self.verified_source()), self.now)
        decision = self.monitor.predict(self.prediction(model_id="forward-test-v1", artifact_sha256="e" * 64,
                                                       cohort_id="frozen-cohort"), self.now)
        self.assertTrue(decision["forward_eligible"])
        self.assertEqual(decision["kind"], "PAPER")
        self.add_settlement()
        self.monitor.ingest_quote(self.quote(event_id="unverified-event"), self.now)
        second = self.monitor.predict(self.prediction(event_id="unverified-event", model_id="forward-test-v1",
                                                      artifact_sha256="e" * 64, cohort_id="frozen-cohort"), self.now)
        self.assertFalse(second["forward_eligible"])
        self.add_settlement(event_id="unverified-event")
        report = self.monitor.report(self.now + timedelta(hours=6))
        self.assertEqual(len(report["cohorts"]), 2)
        self.assertEqual({c["forward_eligible"] for c in report["cohorts"]}, {True, False})
        self.assertNotIn("hypothetical_roi", report)
        self.assertEqual([c["graded_signals"] for c in report["cohorts"]], [1, 1])

    def test_registration_cannot_backdate_forward_trial(self):
        with self.assertRaisesRegex(ValueError, "before trial start"):
            self.monitor.register_model({
                "model_id": "backdated", "artifact_sha256": "e" * 64,
                "trial": {"cohort_id": "backdated", "protocol_sha256": "f" * 64,
                          "model_frozen_at": stamp(self.now - timedelta(days=2)),
                          "starts_at": stamp(self.now - timedelta(days=1))},
            }, self.now)

    def test_existing_trial_can_be_registered_again_after_its_start(self):
        registration = {
            "model_id": "idempotent-trial", "artifact_sha256": "e" * 64,
            "trial": {"cohort_id": "fixed", "protocol_sha256": "f" * 64,
                      "model_frozen_at": stamp(self.now - timedelta(hours=1)),
                      "starts_at": stamp(self.now)},
        }
        self.monitor.register_model(registration, self.now - timedelta(minutes=30))
        repeated = self.monitor.register_model(registration, self.now + timedelta(days=1))
        self.assertTrue(repeated["duplicate"])
        self.assertNotIn("config_sha256", registration["trial"])
        self.assertEqual(self.monitor.db.execute("SELECT count(*) FROM models").fetchone()[0], 1)

    def test_registered_artifact_mismatch_is_excluded_from_paper_scoring(self):
        self.monitor.register_model({"model_id": "frozen", "artifact_sha256": "a" * 64}, self.now)
        for event, artifact in (("missing-hash", None), ("wrong-hash", "b" * 64)):
            self.monitor.ingest_quote(self.quote(event_id=event), self.now)
            decision = self.monitor.predict(self.prediction(event_id=event, model_id="frozen",
                                            artifact_sha256=artifact), self.now)
            self.assertEqual(decision["kind"], "BLOCKED")
            self.assertIn("registered_model_artifact_mismatch", decision["reasons"])
        self.assertEqual(self.monitor.forecast_report(self.now)["events"], [])
        self.assertEqual(self.monitor.pending(self.now), [])

    def test_quote_conditioned_forecast_cannot_predate_input_capture(self):
        self.register_validated_fixture()
        captured = self.now + timedelta(seconds=30)
        quote = self.monitor.ingest_quote(self.quote(source=self.verified_source()), captured)
        decision = self.monitor.predict(self.prediction(model_id="reviewed-test-v1", artifact_sha256="a" * 64,
                                        market_quote_id=quote["quote_id"]), captured)
        self.assertEqual(decision["kind"], "BLOCKED")
        self.assertIn("market_conditioned_prediction_precedes_quote", decision["reasons"])
        self.assertEqual(self.monitor.forecast_report(captured)["events"], [])
        self.assertEqual(self.monitor.pending(captured), [])

    def test_reports_do_not_reveal_settlements_before_they_were_recorded(self):
        self.monitor.ingest_quote(self.quote(), self.now)
        self.monitor.predict(self.prediction(), self.now)
        self.add_settlement()  # Final at +5h, first recorded at +6h.
        for as_of in (self.now + timedelta(hours=4), self.now + timedelta(hours=5, minutes=30)):
            report = self.monitor.report(as_of)
            self.assertEqual(report["settled_signals"], 0)
            self.assertEqual(report["all_forecasts"]["events"][0]["status"], "pending")
        report = self.monitor.report(self.now + timedelta(hours=6))
        self.assertEqual(report["settled_signals"], 1)
        self.assertEqual(report["all_forecasts"]["events"][0]["status"], "final")

    def test_selected_signal_reports_separate_quote_source_classes(self):
        sources = {"verified": self.verified_source(),
                   "aggregator_observational": {"uri": "test://aggregator", "provider": "test", "verified": False},
                   "synthetic": self.quote()["source"]}
        for event, source in sources.items():
            self.monitor.ingest_quote(self.quote(event_id=event, source=source), self.now)
            self.monitor.predict(self.prediction(event_id=event), self.now)
            self.add_settlement(event_id=event)
        report = self.monitor.report(self.now + timedelta(hours=6))
        self.assertEqual(len(report["cohorts"]), 3)
        self.assertEqual({cohort["source_class"] for cohort in report["cohorts"]}, set(sources))
        self.assertTrue(all(cohort["graded_signals"] == 1 for cohort in report["cohorts"]))

    def test_webhook_claims_prevent_duplicate_sends_after_ambiguous_failure(self):
        self.register_validated_fixture()
        self.monitor.config["webhook_enabled"] = True
        self.monitor.ingest_quote(self.quote(source=self.verified_source()), self.now)
        self.monitor.predict(self.prediction(model_id="reviewed-test-v1", artifact_sha256="a" * 64), self.now)
        with patch.dict("os.environ", {"BETTING_ALERT_WEBHOOK_URL": "https://example.invalid/webhook"}), \
                patch("beating.monitor.urlopen", side_effect=TimeoutError("ambiguous receipt")) as network:
            first = self.monitor.dispatch(execute=True, now=self.now)
            second = self.monitor.dispatch(execute=True, now=self.now)
            self.assertEqual(network.call_count, 1)
            self.assertFalse(first[0]["success"])
            self.assertEqual(second, [])
        self.assertEqual(self.monitor.db.execute("SELECT count(*) FROM dispatch_claims").fetchone()[0], 1)

    def test_registered_market_conditioned_model_requires_quote_binding(self):
        self.monitor.register_model({"model_id": "residual-v1", "baseline": "paired_fanduel_no_vig_moneyline"}, self.now)
        quote = self.monitor.ingest_quote(self.quote(), self.now)
        missing = self.monitor.predict(self.prediction(model_id="residual-v1"), self.now)
        self.assertEqual(missing["kind"], "BLOCKED")
        self.assertIn("market_conditioned_prediction_requires_quote_id", missing["reasons"])
        bound = self.monitor.predict(self.prediction(model_id="residual-v1", market_quote_id=quote["quote_id"]), self.now)
        self.assertEqual(bound["kind"], "PAPER")

    def test_full_forecast_report_includes_zero_bet_predictions_and_first_only(self):
        self.monitor.ingest_quote(self.quote(source={"uri": "test://aggregator", "provider": "test", "verified": False}), self.now)
        first = self.monitor.predict(self.prediction(probability_home=0.51), self.now)
        second = self.monitor.predict(self.prediction(probability_home=0.52,
                                      generated_at=stamp(self.now + timedelta(seconds=1))), self.now + timedelta(seconds=1))
        self.assertEqual(first["reasons"], ["edge_below_threshold"])
        self.assertEqual(second["reasons"], ["edge_below_threshold"])
        self.assertEqual(self.monitor.pending(self.now), [])
        self.add_settlement()
        report = self.monitor.forecast_report(self.now + timedelta(hours=6))
        self.assertEqual(len(report["events"]), 1)
        self.assertEqual(report["events"][0]["prediction_id"], first["prediction_id"])
        self.assertEqual(report["cohorts"][0]["source_class"], "aggregator_observational")
        self.assertEqual(report["cohorts"][0]["graded_forecasts"], 1)
        self.assertLess(report["cohorts"][0]["mean_paired_log_loss_delta"], 0)

    def test_full_forecast_report_excludes_stale_live_and_late_captures(self):
        cases = [("stale", {"observed_at": stamp(self.now - timedelta(seconds=91))}, self.now),
                 ("live", {"is_live": True}, self.now),
                 ("late", {}, self.now + timedelta(hours=3))]
        for event, changes, captured in cases:
            self.monitor.ingest_quote(self.quote(event_id=event, **changes), self.now)
            self.monitor.predict(self.prediction(event_id=event, probability_home=0.51), captured)
            self.add_settlement(event_id=event)
        report = self.monitor.forecast_report(self.now + timedelta(hours=6))
        self.assertEqual(report["events"], [])

    def test_full_forecast_report_separates_verified_and_observational_sources(self):
        for event, source in (("verified", self.verified_source()),
                              ("observational", {"uri": "test://aggregator", "provider": "test", "verified": False})):
            self.monitor.ingest_quote(self.quote(event_id=event, source=source), self.now)
            self.monitor.predict(self.prediction(event_id=event, probability_home=0.51), self.now)
            self.add_settlement(event_id=event)
        report = self.monitor.forecast_report(self.now + timedelta(hours=6))
        self.assertEqual({c["source_class"] for c in report["cohorts"]}, {"verified", "aggregator_observational"})
        self.assertEqual(len(report["cohorts"]), 2)

    def test_full_forecasts_ignore_selected_odds_bounds_and_signal_dedup(self):
        self.monitor.ingest_quote(self.quote(decimal_home=1.18, decimal_away=5.9), self.now)
        # First model creates a selected-side paper signal; the second chooses an
        # ineligible favorite. Both probability forecasts still belong in scoring.
        first = self.monitor.predict(self.prediction(model_id="low-home", probability_home=0.75), self.now)
        second = self.monitor.predict(self.prediction(model_id="high-home", probability_home=0.90), self.now)
        self.assertEqual(first["kind"], "PAPER")
        self.assertIn("odds_out_of_range", second["reasons"])
        self.assertIn("event_already_signaled", second["reasons"])
        self.add_settlement()
        report = self.monitor.forecast_report(self.now + timedelta(hours=6))
        self.assertEqual(len(report["events"]), 2)
        self.assertEqual({event["model_id"] for event in report["events"]}, {"low-home", "high-home"})

    def test_full_forecasts_match_historical_structural_vig_range(self):
        for event, price in (("research-valid", 1.80), ("negative-vig", 2.10), ("excess-vig", 1.50)):
            self.monitor.ingest_quote(self.quote(event_id=event, decimal_home=price, decimal_away=price), self.now)
            result = self.monitor.predict(self.prediction(event_id=event), self.now)
            self.assertIn("vig_out_of_range", result["reasons"])
            self.add_settlement(event_id=event)
        report = self.monitor.forecast_report(self.now + timedelta(hours=6))
        self.assertEqual([event["event_id"] for event in report["events"]], ["research-valid"])


if __name__ == "__main__":
    unittest.main()
