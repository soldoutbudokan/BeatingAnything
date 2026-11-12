"""Shared paths and constants for the IPL ball-by-ball model."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "cricsheet"
PROC = ROOT / "data" / "processed" / "ipl"
EXPORT = ROOT / "docs" / "models" / "ipl" / "data"
STATIC = ROOT / "models" / "ipl" / "static"
FRAME = PROC / os.environ.get("IPL_FRAME", "frame.parquet")  # model frame (override only for side experiments)
for p in (RAW, PROC, EXPORT, STATIC):
    p.mkdir(parents=True, exist_ok=True)

ALL_ZIP = RAW / "all_male_json.zip"
PEOPLE = RAW / "people.csv"
STYLES = STATIC / "player_styles.csv"
# dates of birth: cricketdata::player_meta (github.com/robjhyndman/cricketdata), as fetched by the styles builder
DOB = ROOT / "data" / "raw" / "cricket_styles" / "gh" / "cricketdata_player_meta.csv"
PROJ_DATE = "2027-04-15"  # age reference date for 2027 projections

# Outcome classes (order is part of the export contract)
CLASSES = ["wide", "noball", "byes", "wicket", "runout", "r0", "r1", "r2", "r3", "r4", "r6"]
K = len(CLASSES)
REF = CLASSES.index("r0")  # reference class for the multinomial logit
BAT_RUNS = {"r0": 0, "r1": 1, "r2": 2, "r3": 3, "r4": 4, "r6": 6}

BOWLER_WICKETS = {"bowled", "caught", "lbw", "stumped", "caught and bowled", "hit wicket"}

# Competition tiers (used for hierarchical priors and league-strength reporting)
COMP_NAMES = {
    "IPL": "Indian Premier League", "T20I": "T20 Internationals (full members)",
    "T20I-A": "T20 Internationals (associates)", "BBL": "Big Bash League",
    "PSL": "Pakistan Super League", "CPL": "Caribbean Premier League", "SAT": "SA20",
    "ILT": "International League T20", "MLC": "Major League Cricket", "NTB": "T20 Blast",
    "BPL": "Bangladesh Premier League", "LPL": "Lanka Premier League",
    "SMA": "Syed Mushtaq Ali Trophy", "SSM": "Super Smash", "CTC": "CSA T20 Challenge",
    "PKS": "Pakistan National T20 Cup", "NPL": "Nepal Premier League",
    "MSL": "Mzansi Super League", "IPT": "Ireland Inter-Provincial T20",
    "MCL": "Global/other T20", "MCT": "Other T20", "MLT": "Other T20", "BWT": "Other T20",
    "ETPL": "Other T20", "PRO20": "Other T20", "OTHER": "Other T20",
}
FULL_MEMBERS = {"India", "Australia", "England", "South Africa", "New Zealand", "Pakistan",
                "Sri Lanka", "West Indies", "Bangladesh", "Zimbabwe", "Ireland", "Afghanistan"}
TIER_OF = {  # player prior-tier buckets
    "IPL": "ipl", "T20I": "intl", "BBL": "top_fr", "PSL": "top_fr", "CPL": "top_fr",
    "SAT": "top_fr", "ILT": "top_fr", "MLC": "top_fr", "NTB": "dom", "BPL": "fr2",
    "LPL": "fr2", "SMA": "india_dom", "SSM": "dom", "CTC": "dom", "PKS": "dom",
    "MSL": "top_fr", "NPL": "assoc", "T20I-A": "assoc",
}
TIERS = ["ipl", "intl", "top_fr", "fr2", "india_dom", "dom", "assoc"]

PHASES = ["pp", "mid", "death"]


def phase_of_over(o):
    """o is 0-based over index."""
    return 0 if o < 6 else (1 if o < 15 else 2)
