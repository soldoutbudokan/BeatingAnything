"""Run the predeclared annual walk-forward evaluation on real input files."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .model import ResidualLogistic, losses
from .evaluate import summarize, betting_returns

PENALTIES = [0.001, 0.01, 0.1, 1.0]
MODELS = ['calibration', 'physical']


def run(frame, feature_columns, output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    frame = frame.sort_values(['date','game_pk']).reset_index(drop=True).copy()
    frame['date'] = pd.to_datetime(frame.date)
    frame['year'] = frame.date.dt.year
    if frame.game_pk.duplicated().any():
        raise ValueError('Duplicate official game IDs')
    if not np.isfinite(frame[feature_columns].to_numpy(float)).all():
        raise ValueError('Missing features must be handled upstream and audited')
    train = frame.year <= 2022
    validation = frame.year == 2023
    if train.sum() < 500 or validation.sum() < 500:
        raise ValueError('Insufficient development or validation observations')
    selected = {}; tuning = []
    probabilities = frame.loc[frame.year.isin([2024,2025]),
        ['game_pk','date','home_team_id','away_team_id','home_win',
         'fd_home_open_decimal','fd_away_open_decimal','fd_home_open_prob']].copy()
    probabilities['market'] = probabilities.fd_home_open_prob
    for name in MODELS:
        cols = feature_columns if name == 'physical' else []
        x = frame[cols].to_numpy(float)
        y = frame.home_win.to_numpy(float)
        market = frame.fd_home_open_prob.to_numpy(float)
        trials = []
        for penalty in PENALTIES:
            model = ResidualLogistic(penalty).fit(x[train],y[train],market[train])
            loss = float(losses(y[validation], model.predict_proba(x[validation], market[validation])).mean())
            record = {'model':name,'penalty':penalty,'validation_log_loss':loss}
            trials.append(record); tuning.append(record)
        choice = min(trials,key=lambda row:row['validation_log_loss'])
        selected[name] = choice
        for year in [2024,2025]:
            before, test = frame.year < year, frame.year == year
            if test.sum() == 0:
                raise ValueError(f'Missing holdout year {year}')
            model = ResidualLogistic(choice['penalty']).fit(x[before],y[before],market[before])
            probabilities.loc[frame.index[test],name] = model.predict_proba(x[test],market[test])
        # Final deployment fit is a distinct artifact, never used for historical scoring.
        final = ResidualLogistic(choice['penalty']).fit(x,y,market)
        artifact = {'schema_version':1,'model_name':name,'research_status':'unproven',
                    'training_through':str(frame.date.max().date()),'feature_columns':cols,
                    'baseline':'paired_fanduel_no_vig_moneyline','model':final.to_dict()}
        canonical = json.dumps(artifact,sort_keys=True).encode()
        artifact['model_id'] = hashlib.sha256(canonical).hexdigest()[:16]
        (output/f'{name}_model.json').write_text(json.dumps(artifact,indent=2)+'\n')
    metrics = {'status':'unproven','interpretation':'Exploratory opening-price simulation; quote availability unverified. No historical CLV.',
               'protocol':'docs/protocol.md','feature_columns':feature_columns,
               'split_counts':{str(k):int(v) for k,v in frame.groupby('year').size().items()},
               'validation_trials':tuning,'selected':selected,'holdout':{}}
    for name in ['market']+MODELS:
        metrics['holdout'][name] = {'pooled':summarize(probabilities,probabilities[name]),'by_year':{}}
        for year,sub in probabilities.groupby(probabilities.date.dt.year):
            metrics['holdout'][name]['by_year'][str(year)] = summarize(sub,sub[name])
        bets = betting_returns(probabilities,probabilities[name])
        probabilities[f'{name}_bet'] = bets['selected']
        probabilities[f'{name}_profit'] = bets['profit']
    metrics['promotion_allowed'] = False
    probabilities.to_csv(output/'predictions.csv',index=False)
    probabilities[['game_pk','date','home_team_id','away_team_id','home_win','market','calibration','physical']].to_csv(output/'holdout-forecasts.csv',index=False)
    (output/'metrics.json').write_text(json.dumps(metrics,indent=2,allow_nan=False)+'\n')
    return metrics


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input',required=True,help='Joined, audited feature/odds CSV')
    ap.add_argument('--output',default='reports')
    args = ap.parse_args()
    frame = pd.read_csv(args.input)
    features = [c for c in frame if c.startswith('diff_')]
    if not features:
        raise ValueError('No physical features supplied')
    metrics = run(frame,features,args.output)
    print(json.dumps({'status':metrics['status'],'counts':metrics['split_counts'],
                      'results':metrics['holdout']},indent=2))


if __name__ == '__main__':
    main()
