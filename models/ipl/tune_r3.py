"""Round-3 block tests on the forward holdout: per-batter bowling-type splits, batter x bowler head-to-head,
per-bowler batter-archetype split, and conditions (day game, pitch wear, toss decision). Each block is added on
its own to the round-2 best configuration. Run with IPL_FRAME=frame_r3.parquet until the frame is promoted."""
from models.ipl import tune
from models.ipl.config import PROC

tune.OUT = PROC / "tuning_r3.json"
BASE = dict(bat=40, bowl=100, bat_split=100, bowl_split=100)
GRID = [(4.0, dict(BASE, bat_type=150.0)), (4.0, dict(BASE, pair=300.0)), (4.0, dict(BASE, pair=1000.0)),
        (4.0, dict(BASE, bowl_arch=150.0)), (4.0, dict(BASE, day=1.0)), (4.0, dict(BASE, wear=1.0)),
        (4.0, dict(BASE, toss=1.0))]

if __name__ == "__main__":
    tune.run(GRID)
