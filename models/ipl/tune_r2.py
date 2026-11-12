"""Round-2 shrinkage check on the current design (phase environment, age, time-of-delivery experience):
bowler shrinkage and extra shrinkage of batters' dismissal coefficients, scored on the same forward holdout."""
from models.ipl import tune
from models.ipl.config import PROC

tune.OUT = PROC / "tuning_r2.json"
BASE = dict(bat=40, bowl=40, bat_split=100, bowl_split=100)
GRID = [(4.0, dict(BASE)), (4.0, dict(BASE, bowl=100)), (4.0, dict(BASE, bat_wkt_mult=3.0)),
        (4.0, dict(BASE, bowl=100, bat_wkt_mult=3.0))]

if __name__ == "__main__":
    tune.run(GRID)
