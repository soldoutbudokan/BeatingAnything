"""Acquire, audit, reconstruct, join and evaluate the declared experiment."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import numpy as np
import pandas as pd
import scipy
from .odds import fetch_archive, load_archive
from .mlb import download, load_games, load_appearances, load_venues
from .features import build_features, DIFF_FEATURES, FEATURE_VERSION
from .backtest import run


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir',default='data/raw/mlb')
    parser.add_argument('--archive',default='data/raw/mlb_odds_dataset.json')
    parser.add_argument('--output',default='reports')
    parser.add_argument('--download',action='store_true',help='Acquire missing public source files; cached files reused')
    args=parser.parse_args()
    source=Path(args.source_dir); output=Path(args.output); output.mkdir(parents=True,exist_ok=True)
    if args.download:
        fetch_archive(args.archive)
        download(source)
    odds,audit=load_archive(args.archive,sorted(source.glob('schedule_*.json')))
    games=load_games(source); appearances=load_appearances(source,games)
    features=pd.DataFrame(build_features(games,appearances,load_venues(source)))
    if not len(features): raise ValueError('No official feature data')
    # Compare independent identity/outcome sources before selecting feature-only columns.
    check=odds.merge(features[['game_pk','date','home_team_id','away_team_id','home_win']],
                     on='game_pk',suffixes=('_odds','_features'),validate='one_to_one')
    for field in ['date','home_team_id','away_team_id','home_win']:
        if not (check[field+'_odds']==check[field+'_features']).all():
            raise ValueError(f'Feature/odds identity mismatch: {field}')
    metadata=[c for c in ['feature_cutoff_date','feature_lag_days','feature_travel_complete'] if c in features]
    joined=odds.merge(features[['game_pk']+metadata+DIFF_FEATURES],on='game_pk',validate='one_to_one')
    if len(joined)!=len(odds): raise ValueError('Audited odds games missing feature rows')
    if not (pd.to_datetime(joined.feature_cutoff_date)<pd.to_datetime(joined.date)).all():
        raise ValueError('Feature cutoff not strictly earlier than target')
    Path('data/processed').mkdir(parents=True,exist_ok=True)
    joined.to_csv('data/processed/research.csv',index=False)
    audit['official_games']=len(games); audit['pitcher_appearances']=len(appearances)
    audit['joined_rows']=len(joined); audit['feature_version']=FEATURE_VERSION
    audit['target_venue_metadata_incomplete']=int((~joined.feature_travel_complete).sum()) if 'feature_travel_complete' in joined else None
    (output/'data-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    protocol=Path('docs/protocol.md').read_bytes()
    reproducibility={'python':platform.python_version(),'numpy':np.__version__,
                     'pandas':pd.__version__,'scipy':scipy.__version__,
                     'protocol_sha256':hashlib.sha256(protocol).hexdigest(),
                     'joined_csv_sha256':hashlib.sha256(Path('data/processed/research.csv').read_bytes()).hexdigest(),
                     'source_archive_sha256':audit['source_sha256'],
                     'feature_columns':DIFF_FEATURES,
                     'source_snapshot_note':'Official MLB endpoints are mutable; compare the recorded file hashes on rerun.'}
    (output/'reproducibility.json').write_text(json.dumps(reproducibility,indent=2)+'\n')
    manifest=source/'source_manifest.json'
    if manifest.exists(): shutil.copyfile(manifest,output/'mlb-source-manifest.json')
    metrics=run(joined,DIFF_FEATURES,output)
    print(json.dumps({'status':metrics['status'],'holdout':metrics['holdout']['physical']['pooled']},indent=2))


if __name__=='__main__': main()
