"""Score the process-backtest forecasts against the market price at the same information state.

python -m models.ipl.market.score          (needs process_<year>.parquet from models.ipl.process and a capture)
"""
# %% imports
import numpy as np
import pandas as pd

from models.ipl.config import PROC
from models.ipl.market.prices import join, load_series
from models.ipl.process import logloss

KALSHI_FEE = 0.07          # taker fee per contract = 0.07 * price * (1 - price)
POLY_HALF_SPREAD = 0.005   # the price history is a mid; assume a one-cent market
EDGES = (0.0, 0.03, 0.06)


def se(x):
    return float(np.std(x, ddof=1) / np.sqrt(len(x))) if len(x) > 1 else np.nan


def accuracy(m):
    rows = []
    for (st, src), x in m.groupby(["state", "market_source"], sort=False):
        y = x["team1_won"].to_numpy()
        lm, lq = logloss(x["p_team1"], y), logloss(x["market_p_team1"], y)
        rows.append(dict(state=st, source=src, n=len(x), model=lm.mean(), market=lq.mean(), model_minus_market=(lm - lq).mean(),
                         se=se(lm - lq), market_minus_coin=(lq - np.log(2)).mean(), se_mc=se(lq - np.log(2)),
                         corr=float(np.corrcoef(x["p_team1"], x["market_p_team1"])[0, 1])))
    return pd.DataFrame(rows)


def bets(m, edge):
    """One unit staked on a side whenever the model's probability beats the price paid by more than `edge`.
    Price paid = mid + half the spread; Kalshi's taker fee comes off the return. Decided matches only."""
    rows = []
    for r in m[m["team1_won"] != 0.5].itertuples():
        kal = r.market_source == "kalshi"
        half = (r.market_spread / 2 if kal and not np.isnan(r.market_spread) else POLY_HALF_SPREAD)
        for p, q, won in ((r.p_team1, r.market_p_team1, r.team1_won), (1 - r.p_team1, 1 - r.market_p_team1, 1 - r.team1_won)):
            ask = min(q + half, 0.99)
            if p - ask > edge:
                fee = KALSHI_FEE * ask * (1 - ask) if kal else 0.0
                rows.append(dict(state=r.state, source=r.market_source, year=r.year, ret=(won - ask - fee) / ask, edge=p - ask))
    return pd.DataFrame(rows)


def main():
    files = sorted(PROC.glob("process_2*.parquet"))
    d = join(pd.concat([pd.read_parquet(f) for f in files]), load_series())
    d.to_parquet(PROC / "process_market.parquet", index=False)
    m = d.dropna(subset=["market_p_team1"])
    pd.set_option("display.width", 220)
    print(f"matches with a price: {m['match_id'].nunique()} of {d['match_id'].nunique()}")
    print(accuracy(m).round(4).to_string(index=False))
    print(accuracy(m.assign(market_source="both")).round(4).to_string(index=False))
    for e in EDGES:
        b = bets(m, e)
        if len(b):
            g = b.groupby("state", sort=False)["ret"].agg(n="size", roi="mean", se=se)
            print(f"edge > {e:.2f}\n{g.round(4).to_string()}")
    return m


if __name__ == "__main__":
    main()
