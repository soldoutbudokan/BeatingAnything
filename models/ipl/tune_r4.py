"""Round-4 test: a league-season x 2nd-innings block (chasing edge by season) on the forward holdout."""
from models.ipl import tune
from models.ipl.config import PROC

tune.OUT = PROC / "tuning_r4.json"
BASE = dict(bat=40, bowl=100, bat_split=100, bowl_split=100, bat_type=150.0)
GRID = [(4.0, dict(BASE, cs_i2=200.0)), (4.0, dict(BASE, cs_i2=50.0))]

if __name__ == "__main__":
    tune.run(GRID)
