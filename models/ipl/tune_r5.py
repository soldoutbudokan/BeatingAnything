"""Round-5 test: chase pressure x wickets in hand (richer required-rate x wickets x phase shape)."""
from models.ipl import tune
from models.ipl.config import PROC

tune.OUT = PROC / "tuning_r5.json"
BASE = dict(bat=40, bowl=100, bat_split=100, bowl_split=100, bat_type=150.0)
GRID = [(4.0, dict(BASE, chase_w=30.0)), (4.0, dict(BASE, chase_w=5.0))]
LABELS = ["chase x wickets-in-hand, penalty 30", "chase x wickets-in-hand, penalty 5"]

if __name__ == "__main__":
    tune.run(GRID)
