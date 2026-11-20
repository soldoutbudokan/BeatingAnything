"""Shared paths and constants for the international ball-by-ball models (Test and ODI).

One pipeline, two formats. Everything that differs between them (innings structure, phases, buckets) lives in
the Fmt record so the fit, ratings, simulator and exports are written once.
"""
# %% imports
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "cricsheet"
STATIC = ROOT / "models" / "intl" / "static"
PEOPLE = RAW / "people.csv"
META_RDA = ROOT / "data" / "raw" / "cricket_styles" / "gh" / "player_meta.rda"  # cricketdata::player_meta
IPL_STYLES = ROOT / "models" / "ipl" / "static" / "player_styles.csv"
for p in (RAW, STATIC):
    p.mkdir(parents=True, exist_ok=True)

# %% outcome classes (same order as the T20 model: part of the export contract)
CLASSES = ["wide", "noball", "byes", "wicket", "runout", "r0", "r1", "r2", "r3", "r4", "r6"]
K = len(CLASSES)
REF = CLASSES.index("r0")
BOWLER_WICKETS = {"bowled", "caught", "lbw", "stumped", "caught and bowled", "hit wicket"}
SUBTYPES = ["pace_R", "pace_L", "OB", "LB", "SLA", "SLW", "pace_U", "spin_U"]
TYPES6 = SUBTYPES[:6]
AGE_EDGES = [0, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38]
AGE_LABELS = ["<20", "20-21", "22-23", "24-25", "26-27", "28-29", "30-31", "32-33", "34-35", "36-37", "38+", "unknown"]
ROLES_BAT = ["open", "top", "middle", "lower", "tail"]
ROLES_BOWL = ["pace_part", "pace_reg", "pace_front", "spin_part", "spin_reg", "spin_front"]
WK_GROUP = np.array([0, 0, 0, 0, 1, 1, 1, 2, 2, 2])  # wickets down 0-3, 4-6, 7-9

FULL_MEMBERS = ["Australia", "Bangladesh", "England", "India", "Ireland", "New Zealand", "Pakistan", "South Africa",
                "Sri Lanka", "West Indies", "Zimbabwe", "Afghanistan"]
TEAM_SHORT = {"Australia": "AUS", "Bangladesh": "BAN", "England": "ENG", "India": "IND", "Ireland": "IRE",
              "New Zealand": "NZ", "Pakistan": "PAK", "South Africa": "SA", "Sri Lanka": "SL", "West Indies": "WI",
              "Zimbabwe": "ZIM", "Afghanistan": "AFG", "Netherlands": "NED", "Scotland": "SCO", "Nepal": "NEP",
              "Namibia": "NAM", "United Arab Emirates": "UAE", "United States of America": "USA", "Oman": "OMA",
              "Canada": "CAN", "Papua New Guinea": "PNG", "Kenya": "KEN", "Hong Kong": "HKG", "Bermuda": "BER",
              "Jersey": "JER"}
# conditions groups: used to pick a side's likely XI for a fixture and to label environments
REGION = {"India": "asia", "Pakistan": "asia", "Sri Lanka": "asia", "Bangladesh": "asia", "United Arab Emirates": "asia",
          "Nepal": "asia", "Oman": "asia", "Afghanistan": "asia", "Malaysia": "asia", "Hong Kong": "asia",
          "Qatar": "asia", "England": "sena", "Australia": "sena", "South Africa": "sena", "New Zealand": "sena",
          "Ireland": "sena", "Scotland": "sena", "Netherlands": "sena", "Zimbabwe": "sena", "Namibia": "sena",
          "Kenya": "sena", "West Indies": "other", "United States of America": "other", "Canada": "other",
          "Papua New Guinea": "other", "Bermuda": "other"}


# %% format records


@dataclass(frozen=True)
class Fmt:
    key: str                     # "odi" | "test"
    name: str
    zip_name: str
    match_type: str
    n_inn: int                   # 2 or 4
    max_overs: int               # 50 for ODIs; 0 = unlimited
    max_bowler_overs: int        # 10 for ODIs; 0 = unlimited
    phase_labels: tuple          # 3 phases; index 1 is the reference in every phase split
    over_edges: tuple            # lower edges of the innings-over buckets of the situation table
    bf_edges: tuple              # lower edges of the balls-faced (settling) buckets
    bf_labels: tuple
    early_bf: int                # per-batter settling split: first N balls
    exp_edges: tuple             # balls faced / bowled before the delivery (experience prior)
    role_overs: tuple            # overs-per-match cut points for part / regular / frontline bowlers
    pool_since: str              # players active since this date are rated and exported
    ref_since: str               # reference deliveries for "true" stats
    cutoffs: tuple               # forward-holdout folds: (train before, score until)
    default_lam: dict = field(default_factory=dict)
    default_half_life: float = 5.0

    @property
    def proc(self):
        p = ROOT / "data" / "processed" / "intl" / self.key
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def export(self):
        p = ROOT / "docs" / "models" / self.key / "data"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def zip(self):
        return RAW / self.zip_name

    @property
    def n_ovb(self):
        return len(self.over_edges)

    def phase_of_over(self, o):
        """o: 0-based over of the innings (array or scalar) -> 0 / 1 / 2."""
        o = np.asarray(o)
        if self.key == "odi":
            return np.where(o < 10, 0, np.where(o < 40, 1, 2)).astype(np.int8)
        age = o % 80  # overs since the last new ball (the second new ball is taken at 80 overs)
        return np.where(age < 20, 0, np.where(age < 55, 1, 2)).astype(np.int8)

    def over_bucket(self, o):
        return (np.searchsorted(np.asarray(self.over_edges), np.asarray(o), side="right") - 1).astype(np.int16)


LAM_COMMON = dict(l0=1.0, cov=2.0, cell=30.0, comp=5.0, cs=200.0, rw=200.0, gs=20.0, venue=300.0, venue2=600.0,
                  bat=40.0, bat_split=100.0, bat_type=150.0, bowl=100.0, bowl_split=100.0, team=5.0, sit=3.0, xf=2.0)

ODI = Fmt(
    key="odi", name="One-day internationals", zip_name="odis_male_json.zip", match_type="ODI", n_inn=2, max_overs=50,
    max_bowler_overs=10, phase_labels=("Powerplay (1-10)", "Middle (11-40)", "Death (41-50)"),
    over_edges=tuple(range(50)),
    bf_edges=(0, 1, 3, 6, 10, 20, 40, 70, 110), bf_labels=("0", "1-2", "3-5", "6-9", "10-19", "20-39", "40-69", "70-109", "110+"),
    early_bf=15, exp_edges=(0, 120, 500, 1500, 4000, 8000), role_overs=(3.0, 7.0),
    pool_since="2022-11-01", ref_since="2023-01-01",
    cutoffs=(("2024-07-01", "2025-07-01"), ("2025-07-01", "2099-01-01")),
    default_lam=dict(LAM_COMMON, pp_old=1.0), default_half_life=5.0,
)
TEST = Fmt(
    key="test", name="Test cricket", zip_name="tests_male_json.zip", match_type="Test", n_inn=4, max_overs=0,
    max_bowler_overs=0, phase_labels=("New ball (overs 1-20 of a ball)", "Middle (21-55)", "Old ball (56-80)"),
    over_edges=(0, 5, 10, 20, 30, 45, 55, 80, 85, 100, 115, 135, 160),   # aligned with the ball-age phases
    bf_edges=(0, 1, 6, 15, 30, 60, 100, 150, 250), bf_labels=("0", "1-5", "6-14", "15-29", "30-59", "60-99", "100-149", "150-249", "250+"),
    early_bf=30, exp_edges=(0, 200, 800, 2500, 6000, 12000), role_overs=(8.0, 22.0),
    pool_since="2022-11-01", ref_since="2022-01-01",
    cutoffs=(("2024-07-01", "2025-07-01"), ("2025-07-01", "2099-01-01")),
    default_lam=dict(LAM_COMMON), default_half_life=6.0,
)
FORMATS = {"odi": ODI, "test": TEST}

# ODI chase pressure: required run rate buckets (2nd innings)
RRR_EDGES = [-1e9, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 10.0, 12.0, 15.0, 1e9]
RRR_LABELS = ["<3.5", "3.5-4.5", "4.5-5.5", "5.5-6.5", "6.5-7.5", "7.5-8.5", "8.5-10", "10-12", "12-15", "15+"]
# Test match situation buckets
MO_EDGES = [0, 30, 60, 90, 135, 180, 225, 270, 315, 360]          # overs already bowled in the match (pitch wear)
LEAD3_EDGES = [-1e9, -100, 0, 100, 200, 300, 400, 1e9]            # 3rd innings: batting side's lead
SCORE1_EDGES = [-1e9, 250, 350, 450, 550, 1e9]                    # 1st innings: runs on the board
LEAD2_EDGES = [-1e9, -200, -50, 50, 150, 1e9]                     # 2nd innings: batting side's lead
NEED4_EDGES = [-1e9, 25, 75, 150, 250, 350, 450, 1e9]             # 4th innings: runs still needed
RR4_EDGES = [-1e9, 2.0, 3.0, 4.0, 5.0, 7.0, 1e9]                  # 4th innings: runs needed per remaining over
REM4_EDGES = [-1e9, 20, 50, 100, 1e9]                             # 4th innings: overs left in the match
SPELL_EDGES = [0, 5, 10, 20, 30]                                   # overs the bowler has already bowled this innings
TEST_OVERS_NOMINAL = 450


def fmt_of(key):
    return FORMATS[key]
