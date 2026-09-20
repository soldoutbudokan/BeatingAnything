import json
from pathlib import Path
import tempfile
import unittest

from tools.probe_first_basket_history_followup import PLAN, catalog_inventory, run


class FollowupTests(unittest.TestCase):
    def test_all_windows_freeze_before_history_and_empty_window_is_not_replaced(self):
        class FakeClient:
            def __init__(self, output):
                self.output, self.calls, self.endpoints = output, 0, []

            def get(self, endpoint, params):
                self.calls += 1
                self.endpoints.append(endpoint)
                if endpoint == "fixtures":
                    if self.calls == 2:
                        return []
                    return [{"fixtureId": str(self.calls), "sportId": 11, "tournamentSlug": "nba",
                             "startTime": params["from"], "hasOdds": False}]
                frozen = json.loads((self.output / "selected-fixtures.json").read_text())
                assert [f["fixtureId"] for f in frozen["fixtures"]] == ["1", "3"]
                return {"fixtureId": params["fixtureId"], "bookmakers": {}}

        with tempfile.TemporaryDirectory() as tmp:
            client, waits = FakeClient(Path(tmp)), []
            result = run(client, [], wait=waits.append)
            self.assertEqual(client.endpoints, ["fixtures"] * 3 + ["historical-odds"] * 2)
            self.assertEqual(result["fixtures_probed"], 2)
            self.assertEqual(waits, [PLAN["fixture_cooldown_seconds"]] * 2)

    def test_unknown_markets_are_visible_and_player_timelines_count(self):
        history = {"bookmakers": {"fanduel": {"markets": {
            "1": {"outcomes": {"yes": {"players": {"44": []}}}},
            "2": {"outcomes": {"yes": {"players": {"0": []}}}},
        }}}}
        rows = catalog_inventory(history, [{"marketId": 1, "playerProp": True, "marketType": "players-firstpoint"}])
        self.assertEqual(rows[0]["unknown_market_ids"], ["2"])
        self.assertEqual(rows[0]["player_prop_market_count"], 1)
        self.assertEqual(rows[0]["nonzero_player_ids"], 1)


if __name__ == "__main__":
    unittest.main()
