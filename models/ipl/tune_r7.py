"""Round-7 test: random-walk season environment (each league-season shrinks toward the previous season
instead of the league's long-run mean). The plain season block under-fits a trending run environment: with it
the latest training season of every league is under-predicted in-sample (runs +1.8%, sixes +4.3% pooled)."""
from models.ipl import tune
from models.ipl.config import PROC

tune.OUT = PROC / "tuning_r7.json"
BASE = dict(bat=40, bowl=100, bat_split=100, bowl_split=100, bat_type=150.0, chase_hi=1.0)
GRID = [(4.0, dict(BASE, cs_rw=200.0)), (4.0, dict(BASE, cs_rw=50.0)), (4.0, dict(BASE, bowl=200))]

if __name__ == "__main__":
    tune.run(GRID)
