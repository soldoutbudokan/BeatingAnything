import unittest

import numpy as np
import pandas as pd

from beating.model import ResidualLogistic
from beating.soccer import (CANDIDATES, SEASONS, early_features, fit_and_forecast,
                            invert_match_prices, poisson_match_probabilities, prepare_frames,
                            regular_season_audit)


def source_row():
    probabilities = poisson_match_probabilities([1.4, 0.9])
    home, draw, away = 1 / (probabilities * 1.04)
    return {"Date": "01/08/2019", "Time": "15:00", "HomeTeam": "Home", "AwayTeam": "Away",
            "B365>2.5": 2.1, "B365<2.5": 1.8, "Avg>2.5": 2.14, "Avg<2.5": 1.81,
            "B365H": home, "B365D": draw, "B365A": away,
            "AvgC>2.5": 2.0, "AvgC<2.5": 1.9, "B365C>2.5": 1.95, "B365C<2.5": 1.85,
            "FTHG": 2, "FTAG": 1}


class SoccerTests(unittest.TestCase):
    def test_inverse_recovers_known_goal_process(self):
        probabilities = poisson_match_probabilities([2.3, 0.7])
        prices = 1 / (probabilities * 1.04)
        home, away, over, error = invert_match_prices(*prices)
        np.testing.assert_allclose([home, away], [2.3, 0.7], atol=1e-6)
        self.assertLess(error, 1e-8)
        self.assertGreater(over, 0.5)

    def test_unrepresentable_probability_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "poisson_probability_mismatch"):
            invert_match_prices(200, 1.001, 200)

    def test_features_ignore_closes_results_and_other_postmatch_fields(self):
        row = source_row()
        original = early_features(row)
        row.update({"AvgC>2.5": float("nan"), "B365C<2.5": 500, "FTHG": 90,
                    "FTAG": 0, "Referee": "Future Official", "P>2.5": 999,
                    "PC<2.5": float("nan"), "HS": 500})
        self.assertEqual(original, early_features(row))

    def test_missing_close_preserves_event_and_prediction_universe(self):
        row = source_row()
        original, _ = prepare_frames([("E1", "1920", pd.DataFrame([row]))])
        row.update({"AvgC>2.5": None, "AvgC<2.5": None,
                    "B365C>2.5": None, "B365C<2.5": None})
        missing, audit = prepare_frames([("E1", "1920", pd.DataFrame([row]))])
        self.assertEqual(len(missing), 1)
        self.assertEqual(audit[0]["feature_accepted"], 1)
        self.assertEqual(original.event_id.iloc[0], missing.event_id.iloc[0])
        pd.testing.assert_frame_equal(original[list(CANDIDATES["structure"])],
                                      missing[list(CANDIDATES["structure"])])

    def test_extra_playoff_fixture_is_rejected(self):
        teams = [f"Team {index}" for index in range(24)]
        frame = pd.DataFrame([{"HomeTeam": home, "AwayTeam": away} for home in teams
                              for away in teams if home != away])
        audit = regular_season_audit(frame, "E1", "2324")
        self.assertEqual(audit["missing_directed_fixture_count"], 0)
        contaminated = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "playoff contamination"):
            regular_season_audit(contaminated, "E1", "2324")

    def test_future_data_cannot_change_selection_or_previous_fold(self):
        rng = np.random.default_rng(1729)
        rows = []
        for index, season in enumerate(SEASONS):
            for match in range(40):
                probability = rng.uniform(0.35, 0.65)
                rows.append({"season": season, "date": f"{2019+index}-08-{match % 25+1:02d}",
                             "market_p": probability, "p_average": probability + 0.01,
                             "market_logit": np.log(probability / (1-probability)),
                             "consensus_gap": rng.normal(0, .05), "structure_gap": rng.normal(0, .1),
                             "y": int(rng.random() < probability)})
        frame = pd.DataFrame(rows)
        predictions, fit, _ = fit_and_forecast(frame)
        changed = frame.copy()
        future = changed.season.isin(["2425", "2526"])
        changed.loc[future, "structure_gap"] = 1000
        changed.loc[future, "y"] = 1 - changed.loc[future, "y"]
        altered, altered_fit, _ = fit_and_forecast(changed)
        self.assertEqual(fit["validation_candidates"], altered_fit["validation_candidates"])
        self.assertEqual(fit["selected_candidate"], altered_fit["selected_candidate"])
        self.assertEqual(fit["annual_models"]["2324"], altered_fit["annual_models"]["2324"])
        columns = ["p_" + name for name in CANDIDATES]
        np.testing.assert_allclose(predictions.loc[predictions.season.eq("2324"), columns],
                                   altered.loc[altered.season.eq("2324"), columns])
        annual = fit["annual_models"]["2324"]
        self.assertEqual(annual["training_seasons"], list(SEASONS[:4]))
        for name, features in CANDIDATES.items():
            model = ResidualLogistic.from_dict(annual["models"][name])
            expected = frame.loc[frame.season.isin(SEASONS[:4]), list(features)].mean().to_numpy()
            np.testing.assert_allclose(model.mean_, expected)


if __name__ == "__main__":
    unittest.main()
