"""Frozen N1: shared lower-division soccer total-2.5 research models.

The source designates early snapshots and closes, but has no individual quote
timestamps. This module cannot establish simultaneous availability or execution.
No Pinnacle field is used. See docs/protocol-narrow-v1.md for the frozen design.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import io
import json
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from scipy.special import logit
from scipy.stats import poisson, skellam

from .model import ResidualLogistic, losses


MIRROR = "huhao930422-debug/football-odds-mirror"
SOURCE_COMMIT = "c9b05a30eef50fe34abbf4134e6333fc5376d136"
PROTOCOL_SHA256 = "21c3d81b4fb9db4f38423435e0121719549835d1fc4e05880741a304f5a0e85f"
LEAGUES = {"E1": "championship", "E2": "league-one", "D2": "bundesliga-2",
           "F2": "ligue-2", "I2": "serie-b", "SP2": "la-liga-2"}
SEASONS = ("1920", "2021", "2122", "2223", "2324", "2425", "2526")
PENALTIES = (0.001, 0.01, 0.1, 1.0)
CANDIDATES = {
    "calibration": ("market_logit",),
    "consensus": ("market_logit", "consensus_gap"),
    "structure": ("market_logit", "consensus_gap", "structure_gap"),
}
EARLY_COLUMNS = ("B365>2.5", "B365<2.5", "Avg>2.5", "Avg<2.5",
                 "B365H", "B365D", "B365A")
CLOSE_COLUMNS = ("AvgC>2.5", "AvgC<2.5", "B365C>2.5", "B365C<2.5")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def _number(value) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return float("nan")


def fair_probabilities(prices) -> np.ndarray:
    prices = np.asarray(prices, dtype=float)
    if not np.isfinite(prices).all() or np.any(prices <= 1):
        raise ValueError("invalid_early_prices")
    implied = 1 / prices
    return implied / implied.sum()


def poisson_match_probabilities(rates) -> np.ndarray:
    """Home, draw, away probabilities, with both independent rates positive."""
    home, away = rates
    return np.array([skellam.sf(0, home, away), skellam.pmf(0, home, away),
                     skellam.cdf(-1, home, away)], dtype=float)


@lru_cache(maxsize=50000)
def invert_match_prices(home: float, draw: float, away: float) -> tuple[float, ...]:
    """Deterministic bounded 1X2 inversion; no result or close is an argument."""
    target = fair_probabilities([home, draw, away])
    result = least_squares(
        lambda rates: poisson_match_probabilities(rates) - target,
        x0=np.array([1.4, 1.1]), bounds=([0.05, 0.05], [6.0, 6.0]),
        ftol=1e-10, xtol=1e-10, gtol=1e-10,
    )
    if not result.success or not np.isfinite(result.x).all():
        raise ValueError("poisson_nonconvergent")
    error = float(np.max(np.abs(poisson_match_probabilities(result.x) - target)))
    if not np.isfinite(error) or error > 0.02:
        raise ValueError("poisson_probability_mismatch")
    over = float(poisson.sf(2, result.x.sum()))
    if not 0 < over < 1:
        raise ValueError("poisson_invalid_probability")
    return float(result.x[0]), float(result.x[1]), over, error


def early_features(row: dict) -> dict:
    """Accept and transform only the seven frozen early-price columns.

    In particular, this function must not read outcomes or closing fields, even
    to decide which rows are accepted. The shared universe is fixed here.
    """
    prices = {name: _number(row.get(name)) for name in EARLY_COLUMNS}
    if not np.isfinite(list(prices.values())).all() or min(prices.values()) <= 1:
        raise ValueError("invalid_early_prices")
    market = float(fair_probabilities([prices["B365>2.5"], prices["B365<2.5"]])[0])
    average = float(fair_probabilities([prices["Avg>2.5"], prices["Avg<2.5"]])[0])
    home, away, structure, error = invert_match_prices(
        prices["B365H"], prices["B365D"], prices["B365A"])
    market_logit = float(logit(market))
    return {
        "odds_a": prices["B365>2.5"], "odds_b": prices["B365<2.5"],
        "market_p": market, "p_average": average, "market_logit": market_logit,
        "consensus_gap": float(logit(average)) - market_logit,
        "structure_gap": float(logit(structure)) - market_logit,
        "poisson_home_rate": home, "poisson_away_rate": away,
        "poisson_over_probability": structure, "poisson_max_probability_error": error,
        "early_home_odds": prices["B365H"], "early_draw_odds": prices["B365D"],
        "early_away_odds": prices["B365A"],
    }


def regular_season_audit(frame: pd.DataFrame, league: str, season: str) -> dict:
    """Verify the files contain each directed league fixture at most once.

    Completed round robins contain exactly n*(n-1) fixtures; a playoff would
    repeat an already played pairing. The three incomplete source files are
    documented here from their schedule coverage, without inspecting scores.
    """
    expected_teams = {"E1": 24, "E2": 24, "D2": 18, "F2": 20, "I2": 20, "SP2": 22}[league]
    if league == "F2" and season in ("2425", "2526"):
        expected_teams = 18
    if league == "E2" and season == "1920":
        expected_teams = 23
    teams = set(frame.HomeTeam) | set(frame.AwayTeam)
    if len(teams) != expected_teams or frame.HomeTeam.eq(frame.AwayTeam).any():
        raise ValueError(f"Unexpected regular-season team coverage: {league} {season}")
    duplicates = int(frame.duplicated(["HomeTeam", "AwayTeam"]).sum())
    if duplicates:
        raise ValueError(f"Repeated directed fixture suggests playoff contamination: {league} {season}")
    complete_count = expected_teams * (expected_teams - 1)
    exceptions = {
        ("E2", "1920"): (400, "Curtailed 2019/20 regular season with 23 participating clubs."),
        ("F2", "1920"): (280, "Curtailed 2019/20 regular season after 28 rounds."),
        ("F2", "2324"): (379, "Source omits Troyes-Valenciennes, abandoned 2024-05-03."),
    }
    expected_count, note = exceptions.get((league, season), (complete_count, "Complete double round robin."))
    if len(frame) != expected_count:
        raise ValueError(f"Unexpected regular-season fixture count: {league} {season}")
    played = set(zip(frame.HomeTeam, frame.AwayTeam))
    missing = sorted((home, away) for home in teams for away in teams
                     if home != away and (home, away) not in played)
    appearances = pd.concat([frame.HomeTeam, frame.AwayTeam]).value_counts()
    if (league, season) == ("F2", "2324") and missing != [("Troyes", "Valenciennes")]:
        raise ValueError("Unexpected Ligue 2 2023/24 missing fixture")
    exception_sources = {
        ("E2", "1920"): "https://www.gillinghamfootballclub.com/news/2020/june/l1-decision",
        ("F2", "1920"): "https://www.conseil-etat.fr/fr/arianeweb/CE/decision/2020-10-23/440810",
        ("F2", "2324"): "https://www.lfp.fr/article/commission-de-discipline-les-decisions-du-22-mai-2024",
    }
    return {"expected_teams": expected_teams, "observed_teams": len(teams),
            "full_round_robin_rows": complete_count, "observed_rows": len(frame),
            "duplicate_directed_fixture_pairs": duplicates,
            "minimum_team_appearances": int(appearances.min()),
            "maximum_team_appearances": int(appearances.max()),
            "missing_directed_fixture_count": len(missing),
            "missing_directed_fixtures": [list(value) for value in missing], "note": note,
            "exception_source": exception_sources.get((league, season))}


def fetch_sources(raw_dir: Path, verify_primary: bool = True) -> tuple[list, list]:
    """Acquire all fixed files; primary comparison never silently changes pin."""
    raw_dir.mkdir(parents=True, exist_ok=True)

    def acquire(item):
        league, season = item
        source_path = f"data/{LEAGUES[league]}/season-{season}.csv"
        url = f"https://raw.githubusercontent.com/{MIRROR}/{SOURCE_COMMIT}/{source_path}"
        local = raw_dir / f"{league}-{season}.csv"
        metadata_file = raw_dir / f"{league}-{season}-source.json"
        cached = json.loads(metadata_file.read_text()) if metadata_file.exists() else {}
        if (local.exists() and cached.get("url") == url
                and cached.get("sha256") == sha256(local.read_bytes())):
            data = local.read_bytes()
        else:
            with urlopen(url, timeout=45) as response:
                data = response.read()
            local.write_bytes(data)
        frame = pd.read_csv(io.BytesIO(data))
        if "Div" not in frame or not frame["Div"].eq(league).all():
            raise ValueError(f"Source league mismatch: {league} {season}")
        missing = sorted(set(EARLY_COLUMNS + CLOSE_COLUMNS) - set(frame.columns))
        if missing:
            raise ValueError(f"Source schema missing {missing}: {league} {season}")
        numeric = frame[list(EARLY_COLUMNS + CLOSE_COLUMNS)].apply(pd.to_numeric, errors="coerce")
        audit = {
            "league": league, "season": season, "url": url, "source_commit": SOURCE_COMMIT,
            "sha256": sha256(data), "bytes": len(data), "rows": len(frame),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "valid_price_counts": {key: int((numeric[key].gt(1) & np.isfinite(numeric[key])).sum())
                                   for key in numeric.columns},
            "duplicate_identities": int(frame.duplicated(["Date", "HomeTeam", "AwayTeam"]).sum()),
            "regular_season_audit": regular_season_audit(frame, league, season),
        }
        if audit["duplicate_identities"]:
            raise ValueError(f"Duplicate event identities: {league} {season}")
        primary_url = f"https://football-data.co.uk/mmz4281/{season}/{league}.csv"
        audit["primary_url"] = primary_url
        if verify_primary:
            try:
                with urlopen(primary_url, timeout=25) as response:
                    primary = response.read()
                audit["primary_sha256"] = sha256(primary)
                audit["primary_matches_pinned_bytes"] = primary == data
                audit["primary_status"] = "matched" if primary == data else "different"
            except Exception as exc:
                audit["primary_status"] = "unavailable"
                audit["primary_error"] = str(exc)
        else:
            audit["primary_status"] = "not_requested"
        write_json(metadata_file, audit)
        return (league, season, frame), audit

    jobs = [(league, season) for league in LEAGUES for season in SEASONS]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(acquire, jobs))
    return [result[0] for result in results], [result[1] for result in results]


def prepare_frames(sources: list) -> tuple[pd.DataFrame, list]:
    """Separate frozen feature acceptance from settlement availability."""
    accepted, audits = [], []
    for league, season, frame in sources:
        reasons = Counter()
        missing_outcomes = 0
        feature_accepted = 0
        for row in frame.to_dict("records"):
            try:
                feature = early_features(row)
            except ValueError as exc:
                reasons[str(exc)] += 1
                continue
            feature_accepted += 1
            date = pd.to_datetime(row["Date"], dayfirst=True, errors="raise")
            if pd.isna(date):
                raise ValueError("Missing source date")
            home, away = str(row["HomeTeam"]), str(row["AwayTeam"])
            if not home or not away or home == "nan" or away == "nan" or home == away:
                raise ValueError("Invalid source event identity")
            identity = f"{league}|{date:%Y-%m-%d}|{home}|{away}"
            event_id = "soccer-" + sha256(identity.encode())[:24]
            goals = np.array([_number(row.get("FTHG")), _number(row.get("FTAG"))])
            # Missing settlements remain visible in the audit; none is imputed.
            settled = (np.isfinite(goals).all() and np.all(goals >= 0)
                       and np.equal(goals, np.floor(goals)).all())
            if not settled:
                missing_outcomes += 1
            accepted.append({
                "event_id": event_id, "date": date.strftime("%Y-%m-%d"),
                "season": season, "league": league, "home_team": home, "away_team": away,
                "kickoff_source_time": str(row.get("Time", "")),
                "y": int(goals.sum() > 2.5) if settled else float("nan"),
                **feature,
                "close_a": _number(row.get("AvgC>2.5")),
                "close_b": _number(row.get("AvgC<2.5")),
                "book_close_a": _number(row.get("B365C>2.5")),
                "book_close_b": _number(row.get("B365C<2.5")),
            })
        audits.append({"league": league, "season": season, "source_rows": len(frame),
                       "feature_accepted": feature_accepted,
                       "feature_rejection_counts": dict(reasons),
                       "accepted_missing_settlement": missing_outcomes})
    result = pd.DataFrame(accepted).sort_values(["date", "league", "event_id"]).reset_index(drop=True)
    if result.event_id.duplicated().any():
        raise ValueError("Cross-file duplicate event identity")
    return result, audits


def fit_candidate(frame: pd.DataFrame, name: str, penalty: float) -> ResidualLogistic:
    rows = frame.loc[frame.y.notna()]
    if rows.empty:
        raise ValueError("No settled training rows")
    return ResidualLogistic(penalty).fit(rows[list(CANDIDATES[name])].to_numpy(),
                                        rows.y.to_numpy(), rows.market_p.to_numpy())


def fit_and_forecast(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict, dict]:
    """Choose only on 2022/23, then refit on strictly preceding seasons."""
    if not set(frame.season.unique()).issubset(SEASONS):
        raise ValueError("Unregistered season")
    training = frame.loc[frame.season.isin(SEASONS[:3])]
    validation = frame.loc[frame.season.eq("2223") & frame.y.notna()]
    if training.empty or validation.empty:
        raise ValueError("Missing development or validation rows")
    validation_results, selected_penalties = {}, {}
    for name, features in CANDIDATES.items():
        candidate_results = []
        for penalty in PENALTIES:
            model = fit_candidate(training, name, penalty)
            predictions = model.predict_proba(validation[list(features)], validation.market_p)
            score = float(losses(validation.y, predictions).mean())
            candidate_results.append({"penalty": penalty, "log_loss": score,
                                      "model": model.to_dict()})
        best = min(candidate_results, key=lambda value: value["log_loss"])
        selected_penalties[name] = best["penalty"]
        validation_results[name] = {"grid": candidate_results,
                                    "selected_penalty": best["penalty"],
                                    "selected_log_loss": best["log_loss"]}
    selected_candidate = min(validation_results,
                             key=lambda name: validation_results[name]["selected_log_loss"])
    annual_models, forecasts = {}, []
    for season in SEASONS[4:]:
        prior_seasons = SEASONS[:SEASONS.index(season)]
        prior = frame.loc[frame.season.isin(prior_seasons)]
        target = frame.loc[frame.season.eq(season)].copy()
        if prior.empty or target.empty:
            raise ValueError(f"Missing annual fold: {season}")
        if prior.date.max() >= target.date.min():
            raise ValueError(f"Season date overlap: {season}")
        annual_models[season] = {"training_seasons": list(prior_seasons),
                                  "training_rows": int(prior.y.notna().sum()),
                                  "training_last_date": prior.date.max(),
                                  "forecast_rows": len(target), "models": {}}
        for name, features in CANDIDATES.items():
            model = fit_candidate(prior, name, selected_penalties[name])
            target[f"p_{name}"] = model.predict_proba(target[list(features)], target.market_p)
            annual_models[season]["models"][name] = model.to_dict()
        target["split"] = "replication" if season == "2526" else "holdout"
        forecasts.append(target)
    latest_models = {name: fit_candidate(frame, name, selected_penalties[name]).to_dict()
                     for name in CANDIDATES}
    model_artifact = {
        "experiment": "N1", "status": "research_unproven", "alerts_enabled": False,
        "market": "regular-season full-time total goals 2.5", "source_bookmaker": "Bet365",
        "source_price_type": "untimestamped_early_snapshot", "source_commit": SOURCE_COMMIT,
        "protocol_sha256": PROTOCOL_SHA256, "leagues": list(LEAGUES),
        "training_seasons": list(SEASONS), "training_last_date": frame.date.max(),
        "training_rows": int(frame.y.notna().sum()), "selected_candidate": selected_candidate,
        "candidate_features": {key: list(value) for key, value in CANDIDATES.items()},
        "selected_penalties": selected_penalties, "models": latest_models,
        "no_pinnacle_fields": True,
    }
    fit = {
        "experiment": "N1", "protocol_sha256": PROTOCOL_SHA256,
        "development_seasons": list(SEASONS[:3]), "development_rows": int(training.y.notna().sum()),
        "validation_season": "2223", "validation_rows": len(validation),
        "validation_market_log_loss": float(losses(validation.y, validation.market_p).mean()),
        "validation_average_log_loss": float(losses(validation.y, validation.p_average).mean()),
        "validation_candidates": validation_results, "selected_candidate": selected_candidate,
        "annual_models": annual_models,
        "note": "Candidate selection uses validation only; holdout metrics are evaluated separately.",
    }
    return pd.concat(forecasts, ignore_index=True), fit, model_artifact


def run(root: Path = Path("."), verify_primary: bool = True) -> dict:
    protocol = root / "docs/protocol-narrow-v1.md"
    if not protocol.exists() or sha256(protocol.read_bytes()) != PROTOCOL_SHA256:
        raise ValueError("Frozen protocol hash mismatch")
    sources, source_audits = fetch_sources(root / "data/raw/soccer", verify_primary)
    print(f"Acquired {len(sources)} fixed source files", flush=True)
    frame, acceptance = prepare_frames(sources)
    print(f"Accepted {len(frame)} events using early prices only", flush=True)
    forecasts, fit, artifact = fit_and_forecast(frame)
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    artifact["source_sha256"] = {f"{item['league']}-{item['season']}": item["sha256"]
                                 for item in source_audits}
    write_json(reports / "soccer-model.json", artifact)
    fit["model_artifact_sha256"] = sha256((reports / "soccer-model.json").read_bytes())
    forecasts.to_csv(reports / "soccer-forecasts.csv", index=False, float_format="%.15g")
    fit["forecast_sha256"] = sha256((reports / "soccer-forecasts.csv").read_bytes())
    write_json(reports / "soccer-fit.json", fit)
    audit = {"experiment": "N1", "protocol_sha256": PROTOCOL_SHA256, "sources": source_audits,
             "feature_acceptance": acceptance, "source_rows": sum(len(source[2]) for source in sources),
             "accepted_rows": len(frame), "forecast_rows": len(forecasts),
             "early_price_capture_timestamps_available": False,
             "closing_capture_timestamps_available": False,
             "closing_label_documentation": "https://football-data.co.uk/data.php",
             "execution_verified": False, "fanduel_historical_prices": False}
    write_json(reports / "soccer-source-audit.json", audit)
    return {"forecast_rows": len(forecasts), "selected_candidate": fit["selected_candidate"],
            "model_artifact_sha256": fit["model_artifact_sha256"],
            "forecast_sha256": fit["forecast_sha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--skip-primary-check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.root, verify_primary=not args.skip_primary_check), indent=2))


if __name__ == "__main__":
    main()
