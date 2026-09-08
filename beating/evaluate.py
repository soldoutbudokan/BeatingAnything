"""Fixed-policy historical simulation; terminal archive prices never enter."""
import numpy as np
import pandas as pd
from .model import losses


def betting_returns(frame, probability, threshold=0.03):
    p = np.asarray(probability)
    home = frame.fd_home_open_decimal.to_numpy(float)
    away = frame.fd_away_open_decimal.to_numpy(float)
    vig = 1/home + 1/away - 1
    evh, eva = p*home-1, (1-p)*away-1
    choose_home = evh >= eva
    odds = np.where(choose_home, home, away)
    ev = np.maximum(evh, eva)
    selected = (ev >= threshold) & (odds >= 1.2) & (odds <= 6) & (vig >= 0) & (vig <= .08)
    win = choose_home == frame.home_win.to_numpy(bool)
    profit = np.where(selected, np.where(win, odds-1, -1), 0.)
    haircut = np.where(selected, np.where(win, (odds-1)*.98, -1), 0.)
    return dict(selected=selected, home=choose_home, odds=odds, ev=ev,
                profit=profit, haircut_profit=haircut)


def block_interval(dates, numerator, denominator=None, confidence=.975, n_boot=4000, seed=1729):
    """Resample weeks; retain all games inside a sampled block."""
    dates = pd.to_datetime(dates)
    weeks = dates.dt.to_period('W-SUN').astype(str).to_numpy()
    numerator = np.asarray(numerator, dtype=float)
    denominator = np.ones(len(numerator)) if denominator is None else np.asarray(denominator, float)
    blocks = pd.DataFrame({'week':weeks,'num':numerator,'den':denominator}).groupby('week').sum()
    if len(blocks) < 2 or blocks.den.sum() == 0:
        return [None,None]
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(blocks), size=(n_boot,len(blocks)))
    totals = blocks.to_numpy()[idx].sum(axis=1)
    valid = totals[:,1] > 0
    if valid.sum() < n_boot*.95:
        return [None,None]
    stats = totals[valid,0]/totals[valid,1]
    alpha = (1-confidence)/2
    return np.quantile(stats, [alpha,1-alpha]).tolist()


def summarize(frame, probability):
    y = frame.home_win.to_numpy()
    p = np.asarray(probability)
    market = frame.fd_home_open_prob.to_numpy()
    b = betting_returns(frame,p)
    n = int(b['selected'].sum())
    cumulative = np.r_[0.,np.cumsum(b['profit'])]
    diff = losses(y,p)-losses(y,market)
    return {
        'games':len(frame),'log_loss':float(losses(y,p).mean()),
        'brier':float(np.mean((p-y)**2)),
        'log_loss_delta_vs_fanduel':float(diff.mean()),
        'log_loss_delta_97_5_ci':block_interval(frame.date,diff),
        'bets':n,'turnover_units':n,'profit_units':float(b['profit'].sum()),
        'roi':float(b['profit'].sum()/n) if n else None,
        'roi_97_5_ci':block_interval(frame.date,b['profit'],b['selected']),
        'roi_net_winnings_haircut_2pct':float(b['haircut_profit'].sum()/n) if n else None,
        'max_drawdown_units':float(np.max(np.maximum.accumulate(cumulative)-cumulative)),
        'historical_clv':None,
        'execution_verified':False,
    }
