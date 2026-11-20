"""Score the process-backtest forecasts against the market price at the same information state.

python -m models.ipl.market.score          (needs process_<year>.parquet from models.ipl.process and a capture)
"""
# %% imports
import numpy as np
import pandas as pd

from models.ipl.config import PROC
from models.ipl.market.prices import STATE_OFFSET, join, load_series
from models.ipl.process import logloss

KALSHI_FEE = 0.07           # taker fee per contract = 0.07 * price * (1 - price)
BETFAIR_COMMISSION = 0.05   # of net winnings: Betfair's standard market base rate
POLY_HALF_SPREAD = 0.005    # the price history is a mid; assume a one-cent market
EDGES = (0.0, 0.03, 0.06)
PREDICTION = ("kalshi", "polymarket")   # prediction markets: pooled as in the first run (different seasons)
BOOKS = ("kalshi", "pinnacle", "betfair")   # compared on the matches all three price; the last is the reference


def se(x):
    return float(np.std(x, ddof=1) / np.sqrt(len(x))) if len(x) > 1 else np.nan


# %% model against each source


def accuracy(m):
    rows = []
    for (st, src), x in m.groupby(["state", "market_source"], sort=False):
        y = x["team1_won"].to_numpy()
        lm, lq = logloss(x["p_team1"], y), logloss(x["market_p_team1"], y)
        rows.append(dict(state=st, source=src, n=len(x), model=lm.mean(), market=lq.mean(), model_minus_market=(lm - lq).mean(),
                         se=se(lm - lq), market_minus_coin=(lq - np.log(2)).mean(), se_mc=se(lq - np.log(2)),
                         corr=float(np.corrcoef(x["p_team1"], x["market_p_team1"])[0, 1])))
    return pd.DataFrame(rows)


# %% sources against each other


def same_matches(m, sources=BOOKS):
    """Log loss of the model and of each source on the matches every source prices at that state, each minus the
    last source with a paired standard error, and the mean absolute gap between its price and the last source's."""
    key = ["match_id", "state"]
    w = m[m["market_source"].isin(sources)].pivot_table(index=key, columns="market_source", values="market_p_team1", sort=False)
    w = w.reindex(columns=list(sources)).dropna().join(m.drop_duplicates(key).set_index(key)[["p_team1", "team1_won"]])
    rows = []
    for st, x in w.groupby("state", sort=False):
        y, ref = x["team1_won"].to_numpy(), x[sources[-1]]
        lr = logloss(ref, y)
        for name, p in [("model", x["p_team1"])] + [(s, x[s]) for s in sources]:
            ll = logloss(p, y)
            last = name == sources[-1]
            rows.append(dict(state=st, n=len(x), forecast=name, logloss=ll.mean(), minus_coin=(ll - np.log(2)).mean(),
                             minus_ref=(ll - lr).mean(), se=np.nan if last else se(ll - lr),
                             gap=np.nan if last else float((p - ref).abs().mean())))
    return pd.DataFrame(rows)


# %% flat-stake bets


def bets(m, edge):
    """One unit staked on a side whenever the model's probability beats the price paid by more than `edge`.
    Price paid = mid + half the spread, which at Pinnacle is its quoted odds and at Betfair the best back price.
    Kalshi's taker fee and Betfair's commission on winnings come off the return. Decided matches only."""
    rows = []
    for r in m[m["team1_won"] != 0.5].itertuples():
        half = POLY_HALF_SPREAD if np.isnan(r.market_spread) else r.market_spread / 2
        for p, q, won in ((r.p_team1, r.market_p_team1, r.team1_won), (1 - r.p_team1, 1 - r.market_p_team1, 1 - r.team1_won)):
            ask = min(q + half, 0.99)
            if p - ask > edge:
                fee = KALSHI_FEE * ask * (1 - ask) if r.market_source == "kalshi" else 0.0
                profit = (1 - ask) * (1 - BETFAIR_COMMISSION if r.market_source == "betfair" else 1.0)
                rows.append(dict(state=r.state, source=r.market_source, year=r.year,
                                 ret=(won * profit - (1 - won) * ask - fee) / ask, edge=p - ask))
    return pd.DataFrame(rows)


# %% run


def main():
    files = sorted(PROC.glob("process_2*.parquet"))
    d = join(pd.concat([pd.read_parquet(f) for f in files]), load_series())
    d.to_parquet(PROC / "process_market.parquet", index=False)
    m = d.dropna(subset=["market_p_team1"])
    pd.set_option("display.width", 220)
    print(f"matches with a price: {m['match_id'].nunique()} of {d['match_id'].nunique()}")
    print(accuracy(m).round(4).to_string(index=False))
    pm = m[m["market_source"].isin(PREDICTION)]
    if pm["market_source"].nunique() > 1:
        print(accuracy(pm.assign(market_source="+".join(PREDICTION))).round(4).to_string(index=False))
    if set(BOOKS) <= set(m["market_source"]):
        print(f"same matches, minus_ref = minus {BOOKS[-1]}\n{same_matches(m).round(4).to_string(index=False)}")
    for e in EDGES:
        b = bets(m, e)
        if len(b):
            b["state"] = pd.Categorical(b["state"], list(STATE_OFFSET))   # earliest state first
            g = b.groupby(["state", "source"], observed=True)["ret"].agg(n="size", roi="mean", se=se)
            print(f"edge > {e:.2f}\n{g.round(4).to_string()}")
    return m


if __name__ == "__main__":
    main()
