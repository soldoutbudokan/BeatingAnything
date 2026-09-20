import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
import urllib.parse

from tools.acquire_nba_first_score_2026 import PLAN, resume_history, run
from tools.probe_first_basket_history import Client, ProbeStopped
from tests.test_first_basket_history_probe import FakeResponse


class AcquisitionTests(unittest.TestCase):
    def test_fixed_cohort_missing_history_resume_and_manifest_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "plan.json").write_text(json.dumps(PLAN))

            class Opener:
                def __init__(self):
                    self.fixture_calls = 0

                def open(self, request, timeout):
                    query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
                    if "/fixtures?" in request.full_url:
                        self.fixture_calls += 1
                        rows = [{"fixtureId": str(self.fixture_calls), "sportId": 11, "tournamentSlug": "nba",
                                 "startTime": query["from"][0], "hasOdds": False}]
                        return FakeResponse(json.dumps(rows).encode())
                    frozen = json.loads((output / "selected-fixtures.json").read_text())
                    assert len(frozen) == self.fixture_calls == 4
                    fixture = query["fixtureId"][0]
                    if fixture == "1":
                        body = {"error": {"code": "NOT_FOUND", "message": "No historical odds found for the specified filters."}}
                        raise urllib.error.HTTPError("https://example.invalid", 404, "not found", {}, io.BytesIO(json.dumps(body).encode()))
                    return FakeResponse(json.dumps({"fixtureId": fixture, "bookmakers": {}}).encode())

            client = Client("test-private-key", output, opener=Opener(), wait=lambda seconds: None,
                            max_requests=PLAN["max_requests"])
            result = run(client, [], wait=lambda seconds: None)
            self.assertEqual(result["fixtures"], 4)
            self.assertEqual(result["requests"], 8)
            fixtures, coverage, requests = resume_history(output, [])
            self.assertEqual(len(coverage), 4)
            self.assertEqual(coverage[0]["status"], "provider_explicit_no_history")
            self.assertEqual(requests, 8)
            fixtures[1]["participant1Name"] = "Changed name"
            (output / "selected-fixtures.json").write_text(json.dumps(fixtures))
            with self.assertRaises(ProbeStopped):
                resume_history(output, [])


if __name__ == "__main__":
    unittest.main()
