"""Round-6 test: finer required-rate resolution above 17 an over (20-24, 24+) in the chase-pressure block."""
from models.ipl import tune
from models.ipl.config import PROC

tune.OUT = PROC / "tuning_r6.json"
BASE = dict(bat=40, bowl=100, bat_split=100, bowl_split=100, bat_type=150.0)
GRID = [(4.0, dict(BASE, chase_hi=1.0))]

if __name__ == "__main__":
    tune.run(GRID)
