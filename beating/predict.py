"""Score explicit event-matched feature snapshots into the paper monitor.

Requires a new feature snapshot for each prediction. Does not claim to fetch
live features/news. No auto-matching by ambiguous team names or dates.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import numpy as np
from .model import ResidualLogistic
from .monitor import Monitor


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--model',default='reports/physical_model.json')
    ap.add_argument('--quotes',required=True)
    ap.add_argument('--features',required=True,help='JSON list: event_id, feature_cutoff_at, and feature values')
    ap.add_argument('--db',default='state/paper.sqlite3')
    args=ap.parse_args()
    artifact_bytes=Path(args.model).read_bytes(); artifact=json.loads(artifact_bytes)
    model=ResidualLogistic.from_dict(artifact['model'])
    quotes=json.loads(Path(args.quotes).read_text())
    snapshots=json.loads(Path(args.features).read_text())
    if not isinstance(quotes,list) or not isinstance(snapshots,list): raise ValueError('Inputs must be JSON lists')
    features={row['event_id']:row for row in snapshots}
    if len(features)!=len(snapshots): raise ValueError('Duplicate feature event IDs')
    Path(args.db).parent.mkdir(parents=True,exist_ok=True)
    monitor=Monitor(args.db)
    results=[]
    for quote in quotes:
        ingested=monitor.ingest_quote(quote)
        row=features.get(quote['event_id'])
        if row is None:
            results.append({'event_id':quote['event_id'],'status':'BLOCKED','reason':'missing_matched_feature_snapshot'})
            continue
        now=datetime.now(timezone.utc)
        cutoff=datetime.fromisoformat(row['feature_cutoff_at'].replace('Z','+00:00'))
        if cutoff.tzinfo is None or (now-cutoff).total_seconds()<0:
            raise ValueError('Feature cutoff must be timezone-aware and in the past')
        # At most 36 hours from the latest complete-date snapshot; fail on old manual data.
        if (now-cutoff).total_seconds()>36*3600:
            results.append({'event_id':quote['event_id'],'status':'BLOCKED','reason':'stale_feature_snapshot'})
            continue
        x=np.array([[float(row[name]) for name in artifact['feature_columns']]])
        dh,da=quote['decimal_home'],quote['decimal_away']
        market=(1/dh)/(1/dh+1/da)
        probability=float(model.predict_proba(x,[market])[0])
        prediction={'event_id':quote['event_id'],'model_id':artifact['model_id'],
                    'artifact_sha256':hashlib.sha256(artifact_bytes).hexdigest(),
                    'probability_home':probability,'generated_at':now.isoformat(),
                    'feature_cutoff_at':cutoff.isoformat(),'market_quote_id':ingested['quote_id']}
        results.append(monitor.predict(prediction))
    print(json.dumps(results,indent=2))
    monitor.close()


if __name__=='__main__': main()
