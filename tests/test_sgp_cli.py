"""Offline command boundaries, packaged replay and provider handoffs."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from beating.sgp import __main__ as cli
from beating.sgp.models import validate_manifest
from beating.sgp.providers import OpticOddsProvider


FIXTURES = Path(cli.__file__).with_name("fixtures")
AS_OF = "2026-10-09T19:30:30Z"


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def invoke(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main([str(arg) for arg in args])
        return code, stdout.getvalue(), stderr.getvalue()

    def write(self, name, data):
        path = self.directory / name
        path.write_text(json.dumps(data))
        return path

    def test_packaged_demo_reproduces_four_historical_variants_then_uses_cache(self):
        output = self.directory / "demo"
        with patch.object(cli, "OpticOddsProvider") as provider:
            code, out, err = self.invoke("demo", "--output", output)
            self.assertEqual((code, err), (0, ""))
            summary = json.loads(out)
            self.assertEqual(summary["historical_positive_variants"], 4)
            self.assertEqual(summary["live_opportunities"], 0)
            self.assertEqual(summary["stats"]["collection_calls"], 45)
            report = json.loads((output / "report.json").read_text())
            self.assertEqual(report["opportunities"], [])
            self.assertEqual(report["needs_confirmation"], [])
            self.assertEqual(len(report["historical_opportunities"]), 4)
            best = report["historical_opportunities"][0]
            self.assertEqual(best["american"], 1064)
            self.assertAlmostEqual(best["conservative_ev_lower"], .31806861, places=7)
            self.assertEqual(best["min_profitable_american"], 784)
            self.assertEqual(report["stats"]["positive_underlying_events"], 1)
            code, out, err = self.invoke("demo", "--output", output)
            self.assertEqual((code, err), (0, ""))
            cached = json.loads(out)
            self.assertEqual(cached["stats"]["cache_hits"], 45)
            self.assertEqual(cached["stats"].get("collection_calls", 0), 0)
            provider.assert_not_called()

    def test_historical_plan_is_rejected_before_live_provider_instantiation(self):
        plan_path = self.directory / "plan.json"
        code, _, err = self.invoke("plan", "--manifest", FIXTURES / "cmc-manifest.json", "--output", plan_path)
        self.assertEqual((code, err), (0, ""))
        capture_path = self.directory / "capture.json"
        with patch.object(cli, "OpticOddsProvider") as provider:
            code, out, err = self.invoke("capture", "--plan", plan_path, "--output", capture_path)
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
            self.assertIn("historical/replay plans", json.loads(err)["error"])
            provider.assert_not_called()
        self.assertFalse(capture_path.exists())

    def test_discover_without_key_does_not_call_transport(self):
        transport = Mock(side_effect=AssertionError("network must not be reached"))

        def provider(output, **kwargs):
            return OpticOddsProvider(output, transport=transport, **kwargs)

        with patch.dict(os.environ, {}, clear=True), patch.object(cli, "OpticOddsProvider", side_effect=provider):
            code, out, err = self.invoke("discover", "--league", "nfl", "--sportsbook", "theScore",
                                        "--output", self.directory / "discover")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("missing_OPTICODDS_API_KEY", json.loads(err)["error"])
        transport.assert_not_called()
        self.assertFalse((self.directory / "discover" / "snapshots.json").exists())

    def test_discover_passes_existing_key_and_marks_fixture_limit(self):
        provider = Mock()
        provider.discover_fixtures.return_value = [{"id": "one"}, {"id": "two"}]
        provider.snapshots.return_value = [{"data": []}]
        with patch.dict(os.environ, {"OPTICODDS_API_KEY": "offline-test-private-key"}), \
                patch.object(cli, "OpticOddsProvider", return_value=provider) as factory:
            code, out, err = self.invoke("discover", "--league", "nfl", "--sportsbook", "theScore",
                                        "--max-fixtures", "1", "--output", self.directory / "discover")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(factory.call_args.kwargs.get("api_key"), "offline-test-private-key")
        provider.snapshots.assert_called_once_with(["one"], ["theScore"])
        summary = json.loads(out)
        self.assertTrue(summary["truncated"])
        self.assertEqual(summary["jurisdiction"], "unverified")
        self.assertNotIn("offline-test-private-key", out + err)
        saved = (self.directory / "discover" / "snapshots.json").read_text()
        self.assertNotIn("offline-test-private-key", saved)

    def test_run_requires_historical_as_of_and_rejects_live_override(self):
        historical = json.loads((FIXTURES / "cmc-manifest.json").read_text())
        live = deepcopy(historical)
        live["mode"] = "live"
        for board in live["boards"]:
            board["starts_at"] = "2026-10-11T17:00:00Z"
        for mode, data in (("historical", historical), ("live", live)):
            path = self.write(f"{mode}.json", data)
            args = ["run", "--manifest", path, "--captures", self.directory / "not-read.json",
                    "--state", self.directory / "state.sqlite", "--output", self.directory / "report.json"]
            if mode == "live":
                args += ["--as-of", AS_OF]
            with self.subTest(mode=mode), patch.object(cli, "CaptureProvider") as captures:
                code, out, err = self.invoke(*args)
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertIn("historical runs require --as-of", json.loads(err)["error"])
                captures.assert_not_called()
        self.assertFalse((self.directory / "report.json").exists())
        self.assertFalse((self.directory / "state.sqlite").exists())

    def test_run_combines_separate_book_captures_without_double_counting(self):
        capture = json.loads((FIXTURES / "cmc-captures.json").read_text())
        paths = [self.write(f"{book}-captures.json", {**capture, "observations": [
            row for row in capture["observations"] if row["request"]["book"] == book]})
            for book in ("thescore", "fanduel")]
        code, out, err = self.invoke("run", "--manifest", FIXTURES / "cmc-manifest.json",
            "--captures", paths[0], "--captures", paths[1], "--as-of", AS_OF,
            "--state", self.directory / "run.sqlite", "--output", self.directory / "report.json",
            "--max-age", "300", "--comparison-skew", "180")
        self.assertEqual((code, err), (0, ""))
        summary = json.loads(out)
        self.assertEqual(summary["historical_positive_variants"], 4)
        self.assertEqual(summary["live_opportunities"], 0)
        self.assertEqual(summary["stats"]["positive_underlying_events"], 1)

    def test_normalize_output_is_a_valid_planner_input_with_exact_markets(self):
        captured = "2026-10-09T21:00:01Z"
        odds = []
        mapping = {"Player Rushing Yards": {"stat": "R"},
                   "Player Rushing + Receiving Yards": {"stat": "S"}}
        for book in ("theScore", "FanDuel"):
            for market, line in (("Player Rushing Yards", 49.5), ("Player Rushing + Receiving Yards", 89.5)):
                for side in ("over", "under"):
                    odds.append({"id": f"{book}-{market}-{side}", "sportsbook": book, "market": market,
                        "market_id": market, "player_id": "player", "selection": "Example Player",
                        "selection_line": side, "points": line, "price": -110,
                        "timestamp": "2026-10-09T21:00:00Z", "name": f"Example Player {side} {line}"})
        bundle = self.write("snapshots.json", {"mode": "live", "captured_at": captured, "snapshots": [
            {"collection": {"complete": True, "received_at": captured}, "data": [
                {"id": "fixture", "league": {"id": "nfl"}, "status": "unplayed",
                 "start_date": "2026-10-11T17:00:00Z", "odds": odds}]}]})
        market_map = self.write("market-map.json", mapping)
        manifest_path, plan_path = self.directory / "normalized.json", self.directory / "plan.json"
        code, _, err = self.invoke("normalize", "--snapshots", bundle, "--market-map", market_map,
            "--region", "CA-ON", "--settlement", "full-game-including-ot", "--output", manifest_path)
        self.assertEqual((code, err), (0, ""))
        normalized = validate_manifest(json.loads(manifest_path.read_text()))
        self.assertEqual(normalized["mode"], "live")
        self.assertEqual(len(normalized["boards"]), 1)
        code, out, err = self.invoke("plan", "--manifest", manifest_path, "--output", plan_path)
        self.assertEqual((code, err), (0, ""))
        summary = json.loads(out)
        self.assertEqual(summary["candidate_variants"], 4)
        self.assertEqual(summary["reference_partitions"], 1)
        self.assertEqual(summary["unique_quote_requests"], 8)


if __name__ == "__main__":
    unittest.main()
